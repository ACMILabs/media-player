from datetime import datetime
import os
from pathlib import Path
import requests
import subprocess
from threading import Thread
import time
from urllib.parse import urlparse

import alsaaudio
from kombu import Connection, Exchange, Queue
import pytz
import sentry_sdk
import status_client
import vlc


XOS_PLAYLIST_ENDPOINT = os.getenv('XOS_PLAYLIST_ENDPOINT')
PLAYLIST_ID = os.getenv('PLAYLIST_ID')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES'))
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

# Setup Sentry
sentry_sdk.init(SENTRY_ID)

pytz_timezone = pytz.timezone('Australia/Melbourne')
queue_name = f'mqtt-subscription-playback_{MEDIA_PLAYER_ID}'
routing_key = f'mediaplayer.{MEDIA_PLAYER_ID}'

# Playback messaging
media_player_exchange = Exchange('amq.topic', 'direct', durable=True)
playback_queue = Queue(queue_name, exchange=media_player_exchange, routing_key=routing_key)


class MediaPlayer():
    """
    A media player that communicates with XOS to download resources
    and update the message broker with its playback status.
    """

    def __init__(self, vlc = None, playlist = [], current_playlist_position = 0):
        self.vlc = vlc
        self.playlist = playlist
        self.current_playlist_position = current_playlist_position


    def datetime_now(self):
        return datetime.now(pytz_timezone).isoformat()


    def post_playback_to_xos(self):
        while True:
            try:
                # Get playback status from VLC
                session = requests.Session()
                session.auth = ('', VLC_PASSWORD)
                response = session.get(VLC_URL + 'requests/status.json')
                response.raise_for_status()
                vlc_status = response.json()

                # Match playback filename with label id in self.playlist
                playback_position = vlc_status['position']
                duration = vlc_status['length']
                currently_playing_label_id = None
                currently_playing_resource = os.path.basename(urlparse(vlc_status['information']['category']['meta']['filename']).path)
                for idx, item in enumerate(self.playlist):
                    item_filename = os.path.basename(urlparse(item['resource']).path)
                    if item_filename == currently_playing_resource:
                        currently_playing_label_id = int(item['label']['id'])
                        if not self.current_playlist_position == idx:
                            self.current_playlist_position = idx
                            print(f'Playing video {self.current_playlist_position}: {self.generate_playlist()[self.current_playlist_position]}')

                # Read the system volume
                mixer = alsaaudio.Mixer(alsaaudio.mixers()[0])
                system_volume = str(mixer.getvolume()[0] / 10) # System value 0-100

                # Read the player volume
                player_volume = str(vlc_status['volume'] / 256 * 10) # Player value 0-256

                media_player_status_json = {
                    "datetime": self.datetime_now(),
                    "playlist_id": int(PLAYLIST_ID),
                    "media_player_id": int(MEDIA_PLAYER_ID),
                    "label_id": currently_playing_label_id,
                    "playback_position": playback_position,
                    "player_volume": player_volume,
                    "system_volume": system_volume,
                }

                status_client.set_status(
                    DEVICE_UUID,
                    DEVICE_NAME,
                    currently_playing_resource,
                    duration,
                    media_player_status_json['playback_position'],
                    self.current_playlist_position,
                    media_player_status_json['label_id'],
                    0, # TODO: Audio buffer
                    0, # TODO: Video buffer
                    media_player_status_json['player_volume'],
                    media_player_status_json['system_volume'],
                )

                # Publish to XOS broker
                with Connection(AMQP_URL) as conn:
                    producer = conn.Producer(serializer='json')
                    producer.publish(media_player_status_json,
                                    exchange=media_player_exchange, routing_key=routing_key,
                                    declare=[playback_queue])

            except (KeyError, requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
                template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                message = template.format(type(e).__name__, e.args)
                print(message)
                sentry_sdk.capture_exception(e)

            except (Exception, TimeoutError) as e:
                template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                message = template.format(type(e).__name__, e.args)
                print(message)
                sentry_sdk.capture_exception(e)

                self.restart_app_container()

            time.sleep(float(TIME_BETWEEN_PLAYBACK_STATUS))


    def restart_app_container(self):
        try:
            balena_api_url = f'{BALENA_SUPERVISOR_ADDRESS}/v2/applications/{BALENA_APP_ID}/restart-service?apikey={BALENA_SUPERVISOR_API_KEY}'
            json = {
                "serviceName": BALENA_SERVICE_NAME
            }
            response = requests.post(balena_api_url, json=json)
            response.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            message = f'Failed to restart the Media Player container with error: {e}'
            print(message)
            sentry_sdk.capture_exception(e)


    def resource_needs_downloading(self, resource_path):
        return (not os.path.isfile(resource_path)) or (os.path.isfile(resource_path) and not (os.stat(resource_path).st_size > 0))


    def download_resources(self, playlist_label):
        resources_path = 'resources/'
        try:
            resource_url = playlist_label.get('resource')
            video_filename = os.path.basename(urlparse(resource_url).path)
            local_video_path = resources_path + video_filename

            if resource_url and self.resource_needs_downloading(local_video_path):
                print(f'{video_filename} not available locally, attempting to download it now.')
                self.download_file(resource_url)

        except TypeError as e:
            pass

        try:
            subtitles_url = playlist_label.get('subtitles')
            subtitles_filename = os.path.basename(urlparse(subtitles_url).path)
            local_subtitles_path = resources_path + subtitles_filename

            if subtitles_url and self.resource_needs_downloading(local_subtitles_path):
                self.download_file(subtitles_url)

        except TypeError as e:
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


    def download_file(self, url):
        for _ in range(DOWNLOAD_RETRIES):
            try:
                local_filename = urlparse(url).path.split('/')[-1]

                # Make the resources directory if it doesn't exist
                if not os.path.exists('resources'):
                    os.makedirs('resources')

                with requests.get(url, stream=True) as r:
                    r.raise_for_status()
                    with open('resources/' + local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk: # filter out keep-alive new chunks
                                f.write(chunk)
                                # f.flush()
                return local_filename
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
                message = f'Failed to download the file {local_filename} with error {e}'
                print(message)
                sentry_sdk.capture_exception(e)
        message = f'Tried to download {url} {DOWNLOAD_RETRIES} times, giving up.'
        print(message)


    def generate_pls_playlist(self):
        # Generates a playlist.pls file and returns the filename
        pls_filename = 'resources/playlist.pls'
        pls_string = '[playlist]\n'
        for idx, item in enumerate(self.playlist, start=1):
            pls_string += (f"File{idx + 1}={item['resource'].split('/')[-1]}\n")
        pls_string += f'NumberOfEntries={len(self.playlist)}\nVersion=2'
        with open(pls_filename, 'w') as f:
            f.write(pls_string)
        if Path(pls_filename).exists():
            return pls_filename
        else:
            return None


    def generate_playlist(self):
        # Generates a list of files to hand into the VLC call
        playlist = []
        for item in self.playlist:
            playlist.append(item['resource'])
        return playlist


    def start_vlc(self):
        try:
            playlist = self.generate_playlist()

            print(f'Playing video {self.current_playlist_position}: {playlist[self.current_playlist_position]}')
            vlc_display_command = ['vlc', '--x11-display', ':0', '--quiet', '--loop', '--fullscreen', '--no-random', '--no-video-title-show', '--video-on-top', '--no-osd', '--extraintf', 'http', '--http-password', VLC_PASSWORD]
            if int(USE_PLS_PLAYLIST) == 1:
                playlist = [generate_pls_playlist()]

            if SUBTITLES == 'false':
                vlc_display_command.extend([
                    '--no-sub-autodetect-file',
                ])

            subprocess.check_output(vlc_display_command + playlist)

        except subprocess.CalledProcessError as e:
            template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
            message = template.format(type(e).__name__, e.args)
            print(message)
            sentry_sdk.capture_exception(e)


# Download playlist JSON from XOS
media_player = MediaPlayer()
try:
    response = requests.get(XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID)
    response.raise_for_status()
    playlist_labels = response.json()['playlist_labels']

    # Download resources if they aren't available locally
    for item in playlist_labels:
        media_player.download_resources(item)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')
    sentry_sdk.capture_exception(e)

except KeyError as e:
    message = f'Is there a resource for this playlist? {XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID}'
    print(message)
    sentry_sdk.capture_exception(e)


# Check if vlc can play the media in self.playlist
try:
    for item in media_player.playlist:
        video_resource = item['resource']
        media_player.vlc = vlc.MediaPlayer(video_resource)
        media = media_player.vlc.get_media()
        media.parse()
        if media.get_duration():
            # OK to play
            pass
        else:
            print(f'Video doesn\'t seem playable: {video_resource}, removing from the playlist.')
            media_player.playlist.remove(item)
except Exception as e:
    print(f'Video playback test failed with error {e}')
    sentry_sdk.capture_exception(e)


vlc_thread = Thread(target=media_player.start_vlc)
vlc_thread.start()

# Wait for VLC to launch
time.sleep(5)

playback_time_thread = Thread(target=media_player.post_playback_to_xos)
playback_time_thread.start()
