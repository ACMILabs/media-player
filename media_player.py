import json
import os
import re
import subprocess
import time
from datetime import datetime
from threading import Thread
from urllib.parse import urlparse

import alsaaudio
import pytz
import requests
import sentry_sdk
import vlc
from kombu import Connection
from kombu.entity import Exchange, Queue

import network
import status_client

XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT')
XOS_PLAYLIST_ENDPOINT = f'{XOS_API_ENDPOINT}playlists/'
XOS_PLAYLIST_ID = os.getenv('XOS_PLAYLIST_ID', '1')
XOS_MEDIA_PLAYER_ID = os.getenv('XOS_MEDIA_PLAYER_ID', '1')
AUDIO_DEVICE_REGEX = re.compile(os.getenv('AUDIO_DEVICE_REGEX', ''), flags=re.IGNORECASE)
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES', '3'))
AMQP_URL = os.getenv('AMQP_URL')
TIME_BETWEEN_PLAYBACK_STATUS = os.getenv('TIME_BETWEEN_PLAYBACK_STATUS', '0.1')
DEVICE_NAME = os.getenv('BALENA_DEVICE_NAME_AT_INIT')
DEVICE_UUID = os.getenv('BALENA_DEVICE_UUID')
BALENA_APP_ID = os.getenv('BALENA_APP_ID')
BALENA_SERVICE_NAME = os.getenv('BALENA_SERVICE_NAME')
BALENA_SUPERVISOR_ADDRESS = os.getenv('BALENA_SUPERVISOR_ADDRESS')
BALENA_SUPERVISOR_API_KEY = os.getenv('BALENA_SUPERVISOR_API_KEY')
SENTRY_ID = os.getenv('SENTRY_ID')
SUBTITLES = os.getenv('SUBTITLES', 'true')
SUBTITLES_FONT_SIZE = os.getenv('SUBTITLES_FONT_SIZE')  # options: 0-4096
SUBTITLES_FONT_WEIGHT = os.getenv('SUBTITLES_FONT_WEIGHT', 'regular')  # options: 'regular', 'bold'
VLC_CONNECTION_RETRIES = int(os.getenv('VLC_CONNECTION_RETRIES', '3'))

SYNC_CLIENT_TO = os.getenv('SYNC_CLIENT_TO')
SYNC_IS_SERVER = os.getenv('SYNC_IS_SERVER', 'false') == 'true'
SYNC_DRIFT_THRESHOLD = os.getenv('SYNC_DRIFT_THRESHOLD', '40')  # threshold in milliseconds
SYNC_LATENCY = os.getenv('SYNC_LATENCY', '30')  # latency to sync a client in milliseconds
SYNC_IGNORE_THRESHOLD = os.getenv('SYNC_IGNORE_THRESHOLD', '2000')  # threshold in milliseconds
IS_SYNCED_PLAYER = SYNC_CLIENT_TO or SYNC_IS_SERVER
DEBUG = os.getenv('DEBUG', 'false') == 'true'
SCREEN_WIDTH = os.getenv('SCREEN_WIDTH')
SCREEN_HEIGHT = os.getenv('SCREEN_HEIGHT')

# Setup Sentry
sentry_sdk.init(SENTRY_ID)

PYTZ_TIMEZONE = pytz.timezone('Australia/Melbourne')
QUEUE_NAME = f'mqtt-subscription-playback_{XOS_MEDIA_PLAYER_ID}'
ROUTING_KEY = f'mediaplayer.{XOS_MEDIA_PLAYER_ID}'

# Playback messaging
MEDIA_PLAYER_EXCHANGE = Exchange('amq.topic', 'direct', durable=True)
PLAYBACK_QUEUE = Queue(QUEUE_NAME, exchange=MEDIA_PLAYER_EXCHANGE, routing_key=ROUTING_KEY)

# Save resources to a persistent storage location
RESOURCES_PATH = '/data/resources/'

# Cached playlist name
CACHED_PLAYLIST_JSON = '/data/cached_playlist.json'

# Parse the output of `aplay -l`
APLAY_REGEX = re.compile(r'card (?P<card_id>\d+): (.+), device (?P<device_id>\d+): (.+)')


class MediaPlayer():  # pylint: disable=too-many-branches,too-many-instance-attributes
    """
    A media player that communicates with XOS to download resources
    and update the message broker with its playback status.
    """

    def __init__(self):
        self.playlist = []
        self.vlc = {
            'instance': None,
            'player': None,
            'list_player': None,
            'playlist': None,
        }
        self.init_vlc()

        # Variables used to interpolate the play time in get_current_time.
        # Holds the last time reported by VLC.
        self.last_vlc_time = 0
        # Holds the last clock time when VLC was asked for play time.
        self.time_at_last_poll = 0

        if IS_SYNCED_PLAYER:
            self.setup_sync()

    def init_vlc(self):
        """
        Initialise the VLC variables:
            - The VLC instance
            - A MediaListPlayer for playing playlists
            - A MediaPlayer for controlling playback
            - A MediaList to load in the MediaListPlayer
        Documentation for these can be found here:
            http://www.olivieraubert.net/vlc/python-ctypes/doc/
        """
        flags = ['--quiet'] + MediaPlayer.get_audio_flags()
        if SUBTITLES == 'false':
            flags.append('--no-sub-autodetect-file')
        if (SUBTITLES_FONT_SIZE and
                int(SUBTITLES_FONT_SIZE) >= 0 and
                int(SUBTITLES_FONT_SIZE) <= 4096):
            flags.append(f'--freetype-fontsize={SUBTITLES_FONT_SIZE}')
        if SUBTITLES_FONT_WEIGHT == 'bold':
            flags.append('--freetype-bold')
        flags.append('--freetype-font=FaktPro')
        flags.append('--freetype-background-opacity=255')
        flags.append('--freetype-background-color=0')
        if SCREEN_WIDTH and SCREEN_HEIGHT:
            self.print_debug(f'Attempting to set media player screen '
                             f'resolution to: {SCREEN_WIDTH}x{SCREEN_HEIGHT}')
            flags.append(f'--width={SCREEN_WIDTH}')
            flags.append(f'--height={SCREEN_HEIGHT}')
        self.vlc['instance'] = vlc.Instance(flags)
        self.vlc['list_player'] = self.vlc['instance'].media_list_player_new()
        self.vlc['player'] = self.vlc['list_player'].get_media_player()
        self.vlc['playlist'] = self.vlc['instance'].media_list_new()

        self.vlc['player'].set_fullscreen(True)
        self.vlc['list_player'].set_playback_mode(vlc.PlaybackMode.loop)

    def setup_sync(self):
        """
        Initialises variables and network objects needed to sync players.
        """
        if SYNC_IS_SERVER:
            self.server = network.Server('', port=10000)

        if SYNC_CLIENT_TO:
            self.client = network.Client(SYNC_CLIENT_TO, port=10000)

    @staticmethod
    def print_debug(message):
        """
        Print debug output if DEBUG is set true.
        """
        if DEBUG:
            print(message)

    @staticmethod
    def datetime_now():
        """
        Return a string representation of the current datetime with the
        timezone setting in an ISO 8601 format.
        """
        return datetime.now(PYTZ_TIMEZONE).isoformat()

    @staticmethod
    def get_audio_flags():
        """
        Examine the AUDIO_DEVICE_REGEX value and, if given and not 'mute', compare with the
        output from `aplay -l` to determine the audio device to use, and return the flags to
        tell VLC to use that output. If we can't find a match, use the default VLC settings.

        Useful values, that should work on Raspberry Pi|Dell:

        dante|USB Audio # a USB Dante device
        hdmi|hdmi 0 # the first hdmi device
        hdmi1|hdmi 1 # the second hdmi device

        If the value is 'mute', 'disabled', or 'no-audio' the `--no-audio` flag is used with VLC.

        If the value is 'null' or 'none', or not given, the default VLC settings are used.
        """
        if not AUDIO_DEVICE_REGEX.pattern or AUDIO_DEVICE_REGEX.pattern.lower() in ('null', 'none'):
            print('No AUDIO_DEVICE_REGEX setting provided. Using default audio settings.')
            return []

        if AUDIO_DEVICE_REGEX.pattern.lower() in ('mute', 'disable', 'disabled', 'no-audio'):
            print('Disabling Audio')
            return ['--no-audio']

        audio_devices = subprocess.check_output(['aplay', '-l']).decode('utf-8').splitlines()
        print(f'Scanning audio devices for match to {AUDIO_DEVICE_REGEX.pattern}')
        for device in audio_devices:
            mtch = APLAY_REGEX.match(device)
            if mtch:  # this line describes a device (not a subdevice)
                print(f'{device} ... ', end='')
                if AUDIO_DEVICE_REGEX.search(device):
                    print('Y')
                    return [
                        '--aout=alsa',
                        f'--alsa-audio-device=hw:{mtch.group("card_id")},{mtch.group("device_id")}'
                    ]
                print('n')
        print(
            f'AUDIO_DEVICE_REGEX {AUDIO_DEVICE_REGEX.pattern} did not match any audio devices. '
            'Using default audio settings instead.'
        )
        return []

    def get_media_player_status(self):
        """
        Compile the media player status into a dictionary.
        """
        media = self.vlc['player'].get_media()
        if media:
            stats = vlc.MediaStats()
            media.get_stats(stats)
            playlist_position = self.vlc['playlist'].index_of_item(media)
            try:
                label_id = self.playlist[playlist_position]['label']['id']
            except TypeError:
                # No label ID for this playlist item
                label_id = None
            try:
                system_volume = str(alsaaudio.Mixer(alsaaudio.mixers()[0]).getvolume()[0] / 10)
            except (alsaaudio.ALSAAudioError, IndexError):
                system_volume = 0
            media_player_status = {
                'datetime': self.datetime_now(),
                'playlist_id': int(XOS_PLAYLIST_ID),
                'media_player_id': int(XOS_MEDIA_PLAYER_ID),
                'label_id': label_id,
                'playlist_position': playlist_position,
                'playback_position': self.vlc['player'].get_position(),
                'dropped_audio_frames': stats.lost_abuffers,
                'dropped_video_frames': stats.lost_pictures,
                'duration': self.vlc['player'].get_length(),
                'player_volume': \
                # Player value 0-256
                str(self.vlc['player'].audio_get_volume() / 256 * 10),
                'system_volume': \
                # System value 0-100
                system_volume,
            }
        else:
            # playlist is empty
            message = f'No playable items in playlist {int(XOS_PLAYLIST_ID)} '\
                      f'on mediaplayer {int(XOS_MEDIA_PLAYER_ID)}'
            media_player_status = {
                'error': message,
            }
        return media_player_status

    def post_playback_to_broker(self):  # pylint: disable=R0914
        """
        Sends current playback and player information to media broker and Prometheus
        exporter.
        """
        playlist_position = -1
        vlc_connection_attempts = 0
        while True:
            try:
                media_player_status = self.get_media_player_status()

                if media_player_status['playlist_position'] != playlist_position:
                    playlist_position = media_player_status['playlist_position']
                    print(f'Playing video {playlist_position}: '
                          f'{self.playlist[playlist_position]["resource"]}')

                status_client.set_status(
                    DEVICE_UUID,
                    DEVICE_NAME,
                    str(os.path.basename(
                        urlparse(self.playlist[playlist_position]['resource']).path
                    )),
                    media_player_status,
                )

                # Publish to XOS broker
                if AMQP_URL:
                    with Connection(AMQP_URL) as conn:
                        producer = conn.Producer(serializer='json')
                        producer.publish(media_player_status,
                                        exchange=MEDIA_PLAYER_EXCHANGE,
                                        routing_key=ROUTING_KEY,
                                        declare=[PLAYBACK_QUEUE])

            except KeyError as error:
                vlc_connection_attempts += 1
                template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                message = template.format(type(error).__name__, error.args)
                if vlc_connection_attempts < VLC_CONNECTION_RETRIES:
                    print(message)
                    print(f'Current vlc_status: {media_player_status}')
                elif vlc_connection_attempts == VLC_CONNECTION_RETRIES:
                    print(f'Tried {VLC_CONNECTION_RETRIES} times. '
                          f'Giving up and posting error to Sentry...')
                    sentry_sdk.capture_exception(error)

            except (TimeoutError, ValueError) as error:
                template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                message = template.format(type(error).__name__, error.args)
                print(message)
                sentry_sdk.capture_exception(error)

                self.restart_app_container()

            time.sleep(float(TIME_BETWEEN_PLAYBACK_STATUS))

    @staticmethod
    def restart_app_container():
        """
        Posts to the Balena supervisor to restart the media player service.
        """
        try:
            balena_api_url = f'{BALENA_SUPERVISOR_ADDRESS}/v2/applications/{BALENA_APP_ID}/'\
                             f'restart-service?apikey={BALENA_SUPERVISOR_API_KEY}'
            json_data = {
                'serviceName': BALENA_SERVICE_NAME
            }
            response = requests.post(balena_api_url, json=json_data, timeout=60)
            response.raise_for_status()
        except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError
        ) as exception:
            message = f'Failed to restart the Media Player container with exception: {exception}'
            print(message)
            sentry_sdk.capture_exception(exception)

    @staticmethod
    def delete_unneeded_resources(playlist):
        """
        Deletes unneeded resources from old playlists.
        """
        # Make the resources directory if it doesn't exist
        if not os.path.exists(RESOURCES_PATH):
            os.makedirs(RESOURCES_PATH)

        resources_on_filesystem = []
        for item in os.listdir(RESOURCES_PATH):
            if os.path.isfile(os.path.join(RESOURCES_PATH, item)):
                resources_on_filesystem.append(item)

        resources_from_playlist = []
        for item in playlist:
            try:
                resource = urlparse(item.get('resource')).path.split('/')[-1]
            except TypeError:
                resource = None
            if resource:
                resources_from_playlist.append(resource)
            try:
                subtitles = urlparse(item.get('subtitles')).path.split('/')[-1]
                _subtitles_filename = os.path.basename(subtitles)
                subtitles_filename = (
                    resource[:resource.rfind('.')]
                    + _subtitles_filename[_subtitles_filename.rfind('.'):]
                )
            except TypeError:
                subtitles = None
            if subtitles:
                resources_from_playlist.append(subtitles_filename)

        unneeded_files = list(set(resources_on_filesystem) - set(resources_from_playlist))
        for item in unneeded_files:
            file_to_delete = os.path.join(RESOURCES_PATH, item)
            print(f'Deleting unneeded media file: {file_to_delete}')
            os.remove(file_to_delete)
        return unneeded_files

    @staticmethod
    def resource_needs_downloading(resource_path):
        """
        Checks whether the resource exists.
        """
        return (not os.path.isfile(resource_path)) \
            or (os.path.isfile(resource_path)
                and not os.stat(resource_path).st_size > 0)

    def download_resources(self, playlist_label):
        """
        Downloads the resources for the specified playlist label.
        """
        try:
            resource_url = playlist_label.get('resource')
            video_filename = os.path.basename(urlparse(resource_url).path)
            local_video_path = RESOURCES_PATH + video_filename

            if resource_url and self.resource_needs_downloading(local_video_path):
                print(f'{video_filename} not available locally, attempting to download it now.')
                self.download_file(resource_url)

        except TypeError:
            pass

        try:
            subtitles_url = playlist_label.get('subtitles')
            # Modify the subtitles filename to match the video filename (for VLC)
            _subtitles_filename = os.path.basename(urlparse(subtitles_url).path)
            subtitles_filename = (
                video_filename[:video_filename.rfind('.')]
                + _subtitles_filename[_subtitles_filename.rfind('.'):]
            )

            local_subtitles_path = RESOURCES_PATH + subtitles_filename

            if subtitles_url and self.resource_needs_downloading(local_subtitles_path):
                self.download_file(subtitles_url, subtitles_filename)

        except TypeError:
            pass

        # If the video is available locally, add it to the playlist to be played
        if resource_url and os.path.isfile(local_video_path):
            # An array of dicts that has the label_id, resource & subtitles
            item_dictionary = {
                'label': playlist_label['label'],
                'resource': local_video_path,
            }

            if subtitles_url and os.path.isfile(local_subtitles_path):
                item_dictionary['subtitles'] = local_subtitles_path

            return item_dictionary
        return None

    @staticmethod
    def download_file(url, filename=None):
        """
        Downloads the file at the specified URL.
        """
        for _ in range(DOWNLOAD_RETRIES):
            try:
                if filename:
                    local_filename = filename
                else:
                    local_filename = urlparse(url).path.split('/')[-1]

                # Make the resources directory if it doesn't exist
                if not os.path.exists(RESOURCES_PATH):
                    os.makedirs(RESOURCES_PATH)

                with requests.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    with open(RESOURCES_PATH + local_filename, 'wb') as open_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:  # filter out keep-alive new chunks
                                open_file.write(chunk)
                                # open_file.flush()
                return local_filename
            except (
                    requests.exceptions.HTTPError,
                    requests.exceptions.ConnectionError
            ) as exception:
                message = f'Failed to download the file {local_filename} with error {exception}'
                print(message)
                sentry_sdk.capture_exception(exception)
        message = f'Tried to download {url} {DOWNLOAD_RETRIES} times, giving up.'
        print(message)
        return None

    def download_playlist_from_xos(self):
        """
        Downloads the playlist from XOS.
        """
        playlist_json_data = {}
        try:
            response = requests.get(XOS_PLAYLIST_ENDPOINT + XOS_PLAYLIST_ID + '/', timeout=5)
            response.raise_for_status()
            playlist_json_data = response.json()

        except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout
        ) as exception:
            print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT}, looking for local files.')
            sentry_sdk.capture_exception(exception)

            try:
                with open(CACHED_PLAYLIST_JSON, encoding='utf-8') as json_file:
                    playlist_json_data = json.load(json_file)
            except FileNotFoundError as file_exception:
                message = 'Cannot reach XOS and local cache does not exist'
                print(message)
                sentry_sdk.capture_exception(file_exception)
                return

        try:
            playlist_labels = playlist_json_data['playlist_labels']

            # Delete unneeded files from the filesystem
            self.delete_unneeded_resources(playlist_labels)

            # Download resources if they aren't available locally
            for playlist_label in playlist_labels:
                local_playlist_label = self.download_resources(playlist_label)
                if not local_playlist_label:
                    print(f'Invalid video resource: {playlist_label["video"]}, skipping.')
                    continue
                local_resource = local_playlist_label['resource']
                media = self.vlc['instance'].media_new(local_resource)
                media.parse()
                if media.get_duration():
                    # OK to play
                    self.vlc['playlist'].add_media(media)
                    self.playlist.append(local_playlist_label)
                else:
                    print(f'Video doesn\'t seem playable: {local_resource}, skipping.')

            self.vlc['list_player'].set_media_list(self.vlc['playlist'])

            # cache playlist
            with open(CACHED_PLAYLIST_JSON, 'w', encoding='utf-8') as outfile:
                json.dump(playlist_json_data, outfile)

        except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError
        ) as exception:
            print(f'Unable to connect to {XOS_PLAYLIST_ENDPOINT} and \
                resources not available locally. Error: {exception}')
            sentry_sdk.capture_exception(exception)

        except KeyError as exception:
            message = f'Is there a resource for this playlist? \
                {XOS_PLAYLIST_ENDPOINT + XOS_PLAYLIST_ID}'
            print(message)
            sentry_sdk.capture_exception(exception)

    def get_current_time(self):
        """
        Function to interpolate VLC player's play time.
        This is to overcome the limitation where the get_time() function only returns
        a value every 250 ms. We get VLC's reported play time using get_time() and add
        to that the time elapsed since the last correct VLC time report.
        """
        vlc_time = self.vlc['player'].get_time()  # get VLC's reported time

        # If VLC's reported time hasn't changed, add to that the time elapsed
        # since the last time it did change.
        if self.last_vlc_time == vlc_time and self.last_vlc_time != 0:
            vlc_time += int(vlc.libvlc_clock() / 1000) - self.time_at_last_poll
        # If VLC's reported time did change, then it is the correct time and we
        # reset time_at_last_poll to calculate the elapsed time from this point on.
        else:
            self.last_vlc_time = vlc_time
            self.time_at_last_poll = int(vlc.libvlc_clock() / 1000)
        return vlc_time

    def get_current_playlist_position(self):
        """
        Returns the integer of the position that the currently playing media file is in the
        playlist of items being played.
        """
        media = self.vlc['player'].get_media()
        if media:
            stats = vlc.MediaStats()
            media.get_stats(stats)
            playlist_position = self.vlc['playlist'].index_of_item(media)
            return playlist_position
        return None

    def run_timer(self):
        """
        Constantly call get_current_time to have an accurate time whenever get_current_time
        is called elsewhere.
        """
        while True:
            self.get_current_time()

    def sync_check(self):
        """
        Determine whether we should try and setup the sync again.
        """
        self.client.sync_attempts += 1
        if self.client.sync_attempts > 3:
            self.print_debug('No server_time received, attempting to re-setup sync...')
            self.setup_sync()
            self.print_debug(f'Sync attempts reset to: {self.client.sync_attempts}')
        else:
            self.print_debug(
                'No server_time received, sync_attempts: '
                f'{self.client.sync_attempts}'
            )

    def sync_to_server(self):
        """
        For client players, look for data from the server, check if syncing is needed and sync.
        For server players, send the player's current time every second.
        """
        if SYNC_CLIENT_TO:
            while True:
                server_state = self.client.receive()
                try:
                    server_playlist_position = server_state[0]
                    server_time = server_state[1]
                    if server_time:
                        self.client.sync_attempts = 0
                    else:
                        self.sync_check()
                        continue

                    client_time = self.get_current_time()
                    if server_time == 0 or client_time == 0:
                        # Avoid syncing at the beginning of videos
                        continue

                    self.sync_playlist(server_playlist_position, server_time, client_time)
                    self.sync_playback(server_time, client_time)

                except (IndexError, TypeError) as exception:
                    print(f'Unexpected server_state data: {server_state}, exception: {exception}')
                    self.sync_check()
                    continue

        if SYNC_IS_SERVER:
            while True:
                time.sleep(1)
                current_playlist_position = self.get_current_playlist_position()
                if current_playlist_position is None:
                    self.print_debug(
                        f'Failed to get current playlist position: {current_playlist_position}. '
                        'Skipping this sync...'
                    )
                else:
                    self.server.send(f'{current_playlist_position},{self.get_current_time()}')
                    self.print_debug(f'Clients: {self.server.clients}')

    def sync_playlist(self, server_playlist_position, server_time, client_time):
        """
        Sync playlists between server and client if necessary.
        """
        client_playlist_position = self.get_current_playlist_position()
        self.print_debug(
            f'Server playlist/time: {server_playlist_position}/{server_time}, '
            f'client playlist/time: {client_playlist_position}/{client_time}, '
            f'drift: {abs(client_time - server_time)}'
        )

        if client_playlist_position is None:
            self.print_debug(
                f'Failed to get current playlist position: {client_playlist_position}. '
                'Skipping this sync...'
            )
        else:
            if client_playlist_position != server_playlist_position:
                self.print_debug(
                    f'Server playlist {server_playlist_position} is different to '
                    f'client {client_playlist_position}, syncing now...'
                )
                self.vlc['list_player'].play_item_at_index(server_playlist_position)
                client_time = self.get_current_time()
                client_playlist_position = server_playlist_position
                self.print_debug(
                    f'Client now at: {client_playlist_position}/{client_time}'
                )

    def sync_playback(self, server_time, client_time):
        """
        Sync playback position between server and client if necessary.
        """
        if abs(client_time - server_time) > int(SYNC_DRIFT_THRESHOLD):
            sync = True
            target_time = server_time + int(SYNC_LATENCY)
            video_length = int(self.vlc['player'].get_length())
            # Avoid syncing when the video length is zero
            if video_length != 0:
                video_time_remaining = video_length - target_time
                self.print_debug(
                    f'Drifted, syncing with server: {server_time} '
                    f'plus sync latency of {SYNC_LATENCY}. '
                    f'Target: {target_time}, video length: {video_length}'
                )
                if video_time_remaining < int(SYNC_IGNORE_THRESHOLD):
                    sync = False
                    self.print_debug(
                        f'Only {video_time_remaining}/{video_length} remaining, '
                        f'(threashold {SYNC_IGNORE_THRESHOLD}) so ignoring sync...'
                    )
                if target_time > video_length:
                    sync = False
                    self.print_debug(
                        f'Target time {target_time} is greater than the length '
                        f'of this video: {video_length}, ignoring sync...'
                    )
                if sync:
                    self.vlc['player'].set_time(target_time)


if __name__ == "__main__":
    # pylint: disable=invalid-name

    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()
    media_player.vlc['list_player'].play()

    if IS_SYNCED_PLAYER:
        run_timer_thread = Thread(target=media_player.run_timer)
        run_timer_thread.start()

        sync_thread = Thread(target=media_player.sync_to_server)
        sync_thread.start()

    if media_player.playlist:
        # Wait for VLC to launch
        time.sleep(5)
        playback_time_thread = Thread(target=media_player.post_playback_to_broker)
        playback_time_thread.start()
    else:
        print('The playlist appears to be empty... not attempting to post playback status.')
        while True:
            pass
