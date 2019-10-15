import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

import alsaaudio
import pytz
import requests
import sentry_sdk
import vlc
from kombu import Connection, Exchange, Queue

import status_client

XOS_PLAYLIST_ENDPOINT = os.getenv('XOS_PLAYLIST_ENDPOINT')
PLAYLIST_ID = os.getenv('PLAYLIST_ID', '1')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES', '3'))
AMQP_URL = os.getenv('AMQP_URL')
VLC_URL = os.getenv('VLC_URL')
VLC_PASSWORD = os.getenv('VLC_PASSWORD')
TIME_BETWEEN_PLAYBACK_STATUS = os.getenv('TIME_BETWEEN_PLAYBACK_STATUS')
USE_PLS_PLAYLIST = os.getenv('USE_PLS_PLAYLIST')
DEVICE_NAME = os.getenv('BALENA_DEVICE_NAME_AT_INIT')
DEVICE_UUID = os.getenv('BALENA_DEVICE_UUID')
BALENA_APP_ID = os.getenv('BALENA_APP_ID')
BALENA_SERVICE_NAME = os.getenv('BALENA_SERVICE_NAME')
BALENA_SUPERVISOR_ADDRESS = os.getenv('BALENA_SUPERVISOR_ADDRESS')
BALENA_SUPERVISOR_API_KEY = os.getenv('BALENA_SUPERVISOR_API_KEY')
SENTRY_ID = os.getenv('SENTRY_ID')
SUBTITLES = os.getenv('SUBTITLES', 'true')
VLC_CONNECTION_RETRIES = int(os.getenv('VLC_CONNECTION_RETRIES', '3'))

# Setup Sentry
sentry_sdk.init(SENTRY_ID)

PYTZ_TIMEZONE = pytz.timezone('Australia/Melbourne')
QUEUE_NAME = f'mqtt-subscription-playback_{MEDIA_PLAYER_ID}'
ROUTING_KEY = f'mediaplayer.{MEDIA_PLAYER_ID}'

# Playback messaging
MEDIA_PLAYER_EXCHANGE = Exchange('amq.topic', 'direct', durable=True)
PLAYBACK_QUEUE = Queue(QUEUE_NAME, exchange=MEDIA_PLAYER_EXCHANGE, routing_key=ROUTING_KEY)

# Save resources to a persistent storage location
RESOURCES_PATH = '/data/'


class MediaPlayer():
    """
    A media player that communicates with XOS to download resources
    and update the message broker with its playback status.
    """

    def __init__(self):
        self.vlc_player = None
        self.playlist = []
        self.current_playlist_position = 0
        self.vlc_connection_attempts = 0

    @staticmethod
    def datetime_now():
        """
        Return a string representation of the current datetime with the
        timezone setting in an ISO 8601 format.
        """
        return datetime.now(PYTZ_TIMEZONE).isoformat()

    def post_playback_to_broker(self):  # pylint: disable=R0914
        """
        Sends current playback and player information to media broker and Prometheus
        exporter.
        """
        while True:
            try:
                # Get playback status from VLC
                session = requests.Session()
                session.auth = ('', VLC_PASSWORD)
                response = session.get(VLC_URL + 'requests/status.json')
                response.raise_for_status()
                vlc_status = response.json()

                # Match playback filename with label id in self.playlist
                currently_playing_label_id = None
                currently_playing_resource = os.path.basename(
                    urlparse(vlc_status['information']['category']['meta']['filename']).path
                )
                for idx, item in enumerate(self.playlist):
                    item_filename = os.path.basename(urlparse(item['resource']).path)
                    if item_filename == currently_playing_resource:
                        currently_playing_label_id = int(item['label']['id'])
                        if not self.current_playlist_position == idx:
                            self.current_playlist_position = idx
                            print(f'Playing video {self.current_playlist_position}: '
                                  f'{self.generate_playlist()[self.current_playlist_position]}')

                media_player_status = {
                    'datetime': self.datetime_now(),
                    'playlist_id': int(PLAYLIST_ID),
                    'media_player_id': int(MEDIA_PLAYER_ID),
                    'label_id': currently_playing_label_id,
                    'playlist_position': self.current_playlist_position,
                    'playback_position': vlc_status['position'],
                    'dropped_audio_frames': vlc_status['stats']['lostabuffers'],
                    'dropped_video_frames': vlc_status['stats']['lostpictures'],
                    'duration': vlc_status['length'],
                    'player_volume': \
                    # Player value 0-256
                    str(vlc_status['volume'] / 256 * 10),
                    'system_volume': \
                    # System value 0-100
                    str(alsaaudio.Mixer(alsaaudio.mixers()[0]).getvolume()[0] / 10),
                }

                status_client.set_status(
                    DEVICE_UUID,
                    DEVICE_NAME,
                    str(currently_playing_resource),
                    media_player_status,
                )

                # Publish to XOS broker
                with Connection(AMQP_URL) as conn:
                    producer = conn.Producer(serializer='json')
                    producer.publish(media_player_status,
                                     exchange=MEDIA_PLAYER_EXCHANGE,
                                     routing_key=ROUTING_KEY,
                                     declare=[PLAYBACK_QUEUE])

            except (
                    requests.exceptions.HTTPError,
                    requests.exceptions.ConnectionError,
            ) as exception:
                self.vlc_connection_attempts += 1
                if self.vlc_connection_attempts <= VLC_CONNECTION_RETRIES:
                    template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                    message = template.format(type(exception).__name__, exception.args)
                    print(message)
                    print(f'Can\'t connect to VLC player. Attempt {self.vlc_connection_attempts}')
                    sentry_sdk.capture_exception(exception)

            except (KeyError) as error:
                self.vlc_connection_attempts += 1
                if self.vlc_connection_attempts <= VLC_CONNECTION_RETRIES:
                    template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                    message = template.format(type(error).__name__, error.args)
                    print(message)
                    print(f'Current vlc_status: {vlc_status}')
                    sentry_sdk.capture_exception(error)

            except (TimeoutError) as error:
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

            self.playlist.append(item_dictionary)

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

    def generate_pls_playlist(self):
        """
        Generates a playlist.pls file and returns the filename.
        """
        pls_filename = RESOURCES_PATH + 'playlist.pls'
        pls_string = '[playlist]\n'
        for idx, item in enumerate(self.playlist, start=1):
            pls_string += (f"File{idx}={item['resource'].split('/')[-1]}\n")
        pls_string += f'NumberOfEntries={len(self.playlist)}\nVersion=2'
        with open(pls_filename, 'w') as open_file:
            open_file.write(pls_string)
        if Path(pls_filename).exists():
            return pls_filename

        return None

    def generate_playlist(self):
        """
        Generates a list of files to hand into the VLC call.
        """
        playlist = []
        for item in self.playlist:
            playlist.append(item['resource'])
        return playlist

    def start_vlc(self):
        """
        Starts VLC.
        """
        try:
            playlist = self.generate_playlist()

            print(f'Playing video {self.current_playlist_position}: '
                  f'{playlist[self.current_playlist_position]}')
            vlc_display_command = [
                'vlc',
                '--x11-display',
                ':0',
                '--quiet',
                '--loop',
                '--fullscreen',
                '--no-random',
                '--no-video-title-show',
                '--video-on-top',
                '--no-osd',
                '--extraintf',
                'http',
                '--http-password',
                VLC_PASSWORD,
            ]
            if int(USE_PLS_PLAYLIST) == 1:
                playlist = [self.generate_pls_playlist()]

            if SUBTITLES == 'false':
                vlc_display_command.extend([
                    '--no-sub-autodetect-file',
                ])

            subprocess.check_output(vlc_display_command + playlist)

        except subprocess.CalledProcessError as exception:
            template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
            message = template.format(type(exception).__name__, exception.args)
            print(message)
            sentry_sdk.capture_exception(exception)

        except IndexError as exception:
            template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
            message = template.format(type(exception).__name__, exception.args)
            print(message)
            print(f'Playlist seems to be empty: {playlist}')
            sentry_sdk.capture_exception(exception)

    def download_playlist_from_xos(self):
        """
        Downloads the playlist from XOS.
        """
        try:
            response = requests.get(XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID)
            response.raise_for_status()
            playlist_labels = response.json()['playlist_labels']

            # Delete unneeded files from the filesystem
            self.delete_unneeded_resources(playlist_labels)

            # Download resources if they aren't available locally
            for item in playlist_labels:
                self.download_resources(item)

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
            print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {exception}')
            sentry_sdk.capture_exception(exception)

        except KeyError as exception:
            message = f'Is there a resource for this playlist? \
                {XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID}'
            print(message)
            sentry_sdk.capture_exception(exception)


if __name__ == "__main__":
    # pylint: disable=invalid-name
    # Download playlist JSON from XOS
    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()

    # Check if vlc can play the media in self.playlist
    for playlist_item in media_player.playlist:
        video_resource = playlist_item['resource']
        media_player.vlc_player = vlc.MediaPlayer(video_resource)
        media = media_player.vlc_player.get_media()
        media.parse()
        if media.get_duration():
            # OK to play
            pass
        else:
            print(f'Video doesn\'t seem playable: \
                {video_resource}, removing from the playlist.')
            media_player.playlist.remove(playlist_item)

    vlc_thread = Thread(target=media_player.start_vlc)
    vlc_thread.start()

    # Wait for VLC to launch
    time.sleep(5)

    playback_time_thread = Thread(target=media_player.post_playback_to_broker)
    playback_time_thread.start()
