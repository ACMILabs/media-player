from datetime import datetime
import os
from pathlib import Path
import requests
import subprocess
from threading import Thread
import time
from urllib.parse import urlparse

from kombu import Connection, Exchange, Queue
import pytz
import sentry_sdk
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
BALENA_APP_ID = os.getenv('BALENA_APP_ID')
BALENA_SERVICE_NAME = os.getenv('BALENA_SERVICE_NAME')
BALENA_SUPERVISOR_ADDRESS = os.getenv('BALENA_SUPERVISOR_ADDRESS')
BALENA_SUPERVISOR_API_KEY = os.getenv('BALENA_SUPERVISOR_API_KEY')
SENTRY_ID = os.getenv('SENTRY_ID')

# Setup Sentry
sentry_sdk.init(SENTRY_ID)

pytz_timezone = pytz.timezone('Australia/Melbourne')
vlc_playlist = []  # An array of dictionaries with label id & resource
queue_name = f'mqtt-subscription-playback_{MEDIA_PLAYER_ID}'
routing_key = f'mediaplayer.{MEDIA_PLAYER_ID}'

# Playback messaging
media_player_exchange = Exchange('amq.topic', 'direct', durable=True)
playback_queue = Queue(queue_name, exchange=media_player_exchange, routing_key=routing_key)


def datetime_now():
    return datetime.now(pytz_timezone).isoformat()


def post_playback_to_xos():
    while True:
        try:
            # Get playback status from VLC
            session = requests.Session()
            session.auth = ('', VLC_PASSWORD)
            response = session.get(VLC_URL + 'requests/status.json')
            response.raise_for_status()
            vlc_status = response.json()

            # Match playback filename with label id in vlc_playlist
            playback_position = vlc_status['position']
            currently_playing_label_id = None
            currently_playing_resource = os.path.basename(urlparse(vlc_status['information']['category']['meta']['filename']).path)
            for item in vlc_playlist:
                item_filename = os.path.basename(urlparse(item['resource']).path)
                if item_filename == currently_playing_resource:
                    currently_playing_label_id = int(item['label']['id'])

            media_player_status_json = {
                "datetime": datetime_now(),
                "playlist_id": int(PLAYLIST_ID),
                "media_player_id": int(MEDIA_PLAYER_ID),
                "label_id": currently_playing_label_id,
                "playback_position": playback_position
                #"vlc_status": vlc_status
            }

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

            restart_app_container()
        
        time.sleep(float(TIME_BETWEEN_PLAYBACK_STATUS))


def restart_app_container():
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


def download_file(url):
    for _ in range(DOWNLOAD_RETRIES):
        try:
            local_filename = urlparse(url).path.split('/')[-1]

            # Make the resources directory if it doesn't exist
            if not os.path.exists('resources'):
                os.makedirs('resources')

            # NOTE the stream=True parameter below
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open('resources/' + local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        if chunk: # filter out keep-alive new chunks
                            f.write(chunk)
                            # f.flush()
            return local_filename
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            print(f'Failed to download the file {local_filename} with error {e}')
            sentry_sdk.capture_exception(e)
    print(f'Tried to download {url} {DOWNLOAD_RETRIES} times, giving up.')


def generate_pls_playlist():
    # Generates a playlist.pls file and returns the filename
    pls_filename = 'resources/playlist.pls'
    pls_string = '[playlist]\n'
    for idx, item in enumerate(vlc_playlist, start=1):
        pls_string += (f"File{idx + 1}={item['resource'].split('/')[-1]}\n")
    pls_string += f'NumberOfEntries={len(vlc_playlist)}\nVersion=2'
    with open(pls_filename, 'w') as f:
        f.write(pls_string)
    if Path(pls_filename).exists():
        return pls_filename
    else:
        return None


def generate_playlist():
    # Generates a list of files to hand into the VLC call
    playlist = []
    for item in vlc_playlist:
        playlist.append(item['resource'])
    return playlist


def start_vlc():
    try:
        # TODO: Use vlc python bindings.
        # Play the playlist in vlc
        print('Starting VLC...')
        vlc_display_command = ['vlc', '--x11-display', ':0', '--quiet', '--loop', '--fullscreen', '--no-random', '--no-video-title-show', '--video-on-top', '--no-osd' '--extraintf', 'http', '--http-password', VLC_PASSWORD]
        playlist = generate_playlist()
        if int(USE_PLS_PLAYLIST) == 1:
            playlist = [generate_pls_playlist()]
        subprocess.check_output(vlc_display_command + playlist)
    except subprocess.CalledProcessError as e:
        template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
        message = template.format(type(e).__name__, e.args)
        print(message)
        sentry_sdk.capture_exception(e)


# Download playlist JSON from XOS
try:
    response = requests.get(XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID)
    response.raise_for_status()
    playlist = response.json()['playlist_labels']

    # Download resource if it isn't available locally
    for item in playlist:
        resource_url = item['resource']
        video_filename = os.path.basename(urlparse(resource_url).path)
        local_video_path = 'resources/' + video_filename
        
        if not os.path.isfile(local_video_path):
            print(f'{video_filename} not available locally, attempting to download it now.')
            download_file(resource_url)
        
        # If it's now available locally, add it to the playlist to be played
        if os.path.isfile(local_video_path):
            # TODO: An array of dicts that has the label_id and resource
            item_dictionary = {
                'label': item['label'],
                'resource': local_video_path
            }
            vlc_playlist.append(item_dictionary)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')
    sentry_sdk.capture_exception(e)


# Check if vlc can play the media in vlc_playlist
try:
    for item in vlc_playlist:
        video_resource = item['resource']
        player = vlc.MediaPlayer(video_resource)
        media = player.get_media() 
        media.parse()
        if media.get_duration():
            # OK to play
            pass
        else:
            print(f'Video doesn\'t seem playable: {video_resource}, removing from the playlist.')
            vlc_playlist.remove(item)
except Exception as e:
    print(f'Video playback test failed with error {e}')
    sentry_sdk.capture_exception(e)


vlc_thread = Thread(target=start_vlc)
vlc_thread.start()

# Wait for VLC to launch
time.sleep(5)

playback_time_thread = Thread(target=post_playback_to_xos)
playback_time_thread.start()
