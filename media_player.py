import os
import time
from datetime import datetime
from threading import Thread
from urllib.parse import urlparse

import alsaaudio
import pytz
import requests
import sentry_sdk
import vlc
from kombu import Connection, Exchange, Queue

import network
import status_client

XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT')
XOS_PLAYLIST_ENDPOINT = f'{XOS_API_ENDPOINT}playlists/'
XOS_PLAYLIST_ID = os.getenv('XOS_PLAYLIST_ID', '1')
XOS_MEDIA_PLAYER_ID = os.getenv('XOS_MEDIA_PLAYER_ID', '1')
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
VLC_CONNECTION_RETRIES = int(os.getenv('VLC_CONNECTION_RETRIES', '3'))

SYNC_CLIENT_TO = os.getenv('SYNC_CLIENT_TO')
SYNC_IS_SERVER = os.getenv('SYNC_IS_SERVER', 'false') == 'true'
SYNC_DRIFT_THRESHOLD = os.getenv('SYNC_DRIFT_THRESHOLD', '40')  # threshold in milliseconds
IS_SYNCED_PLAYER = SYNC_CLIENT_TO or SYNC_IS_SERVER

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


class MediaPlayer():
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
        flags = ['--quiet']
        if SUBTITLES == 'false':
            flags.append('--no-sub-autodetect-file')
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
    def datetime_now():
        """
        Return a string representation of the current datetime with the
        timezone setting in an ISO 8601 format.
        """
        return datetime.now(PYTZ_TIMEZONE).isoformat()

    def get_media_player_status(self):
        """
        Compile the media player status into a dictionary.
        """
        media = self.vlc['player'].get_media()
        if not media:
            # playlist is empty
            raise ValueError('No playable items in playlist')
        stats = vlc.MediaStats()
        media.get_stats(stats)
        playlist_position = self.vlc['playlist'].index_of_item(media)
        try:
            label_id = self.playlist[playlist_position]['label']['id']
        except TypeError:
            # No label ID for this playlist item
            label_id = None
        return {
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
            str(alsaaudio.Mixer(alsaaudio.mixers()[0]).getvolume()[0] / 10),
        }

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
                with Connection(AMQP_URL) as conn:
                    producer = conn.Producer(serializer='json')
                    producer.publish(media_player_status,
                                     exchange=MEDIA_PLAYER_EXCHANGE,
                                     routing_key=ROUTING_KEY,
                                     declare=[PLAYBACK_QUEUE])

            except KeyError as error:
                vlc_connection_attempts += 1
                if vlc_connection_attempts <= VLC_CONNECTION_RETRIES:
                    template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                    message = template.format(type(error).__name__, error.args)
                    print(message)
                    print(f'Current vlc_status: {media_player_status}')
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
            balena_api_url = f'{BALENA_SUPERVISOR_ADDRESS}/v2/applications/{BALENA_APP_ID}/\
                restart-service?apikey={BALENA_SUPERVISOR_API_KEY}'
            json = {
                'serviceName': BALENA_SERVICE_NAME
            }
            response = requests.post(balena_api_url, json=json)
            response.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
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
            except TypeError:
                subtitles = None
            if subtitles:
                resources_from_playlist.append(subtitles)

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
            subtitles_filename = os.path.basename(urlparse(subtitles_url).path)
            local_subtitles_path = RESOURCES_PATH + subtitles_filename

            if subtitles_url and self.resource_needs_downloading(local_subtitles_path):
                self.download_file(subtitles_url)

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
    def download_file(url):
        """
        Downloads the file at the specified URL.
        """
        for _ in range(DOWNLOAD_RETRIES):
            try:
                local_filename = urlparse(url).path.split('/')[-1]

                # Make the resources directory if it doesn't exist
                if not os.path.exists(RESOURCES_PATH):
                    os.makedirs(RESOURCES_PATH)

                with requests.get(url, stream=True) as response:
                    response.raise_for_status()
                    with open(RESOURCES_PATH + local_filename, 'wb') as open_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:  # filter out keep-alive new chunks
                                open_file.write(chunk)
                                # open_file.flush()
                return local_filename
            except (
                    requests.exceptions.HTTPError,
                    requests.exceptions.ConnectionError,
            ) as exception:
                message = f'Failed to download the file {local_filename} with error {exception}'
                print(message)
                sentry_sdk.capture_exception(exception)
        message = f'Tried to download {url} {DOWNLOAD_RETRIES} times, giving up.'
        print(message)

    def download_playlist_from_xos(self):
        """
        Downloads the playlist from XOS.
        """
        try:
            response = requests.get(XOS_PLAYLIST_ENDPOINT + XOS_PLAYLIST_ID)
            response.raise_for_status()
            playlist_labels = response.json()['playlist_labels']

            # Delete unneeded files from the filesystem
            self.delete_unneeded_resources(playlist_labels)

            # Download resources if they aren't available locally
            for playlist_label in playlist_labels:
                local_playlist_label = self.download_resources(playlist_label)
                if not local_playlist_label:
                    print(f'Invalid video resource: {playlist_label["resource"]}, skipping.')
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

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
            print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {exception}')
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
        vlc_time = self.vlc['player'].get_time() # get VLC's reported time

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

    def run_timer(self):
        """
        Constantly call get_current_time to have an accurate time whenever get_current_time
        is called elsewhere.
        """
        while True:
            self.get_current_time()

    def sync_to_server(self):
        """
        For client players, look for data from the server, check if syncing is needed and sync.
        For server players, send the player's current time every second.
        """
        if SYNC_CLIENT_TO:
            while True:
                server_time = self.client.receive()
                if not server_time:
                    continue
                client_time = self.get_current_time()
                print(server_time, client_time)
                if abs(client_time - server_time) > int(SYNC_DRIFT_THRESHOLD):
                    print('Drifted, syncing...')
                    self.vlc['player'].set_time(server_time)

        if SYNC_IS_SERVER:
            while True:
                time.sleep(1)
                self.server.send(self.get_current_time())


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

    # Wait for VLC to launch
    time.sleep(5)

    playback_time_thread = Thread(target=media_player.post_playback_to_broker)
    playback_time_thread.start()
