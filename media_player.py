from datetime import datetime
import os
import requests
import subprocess
from threading import Thread
import time
from urllib.parse import urlparse

from kombu import Connection, Exchange, Queue
import pytz
import vlc


XOS_PLAYLIST_ENDPOINT = os.getenv('XOS_PLAYLIST_ENDPOINT')
PLAYLIST_ID = os.getenv('PLAYLIST_ID')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES'))
AMQP_URL = os.getenv('AMQP_URL')
VLC_URL = os.getenv('VLC_URL')
VLC_PASSWORD = os.getenv('VLC_PASSWORD')
TIME_BETWEEN_PLAYBACK_STATUS = os.getenv('TIME_BETWEEN_PLAYBACK_STATUS')

pytz_timezone = pytz.timezone('Australia/Melbourne')
vlc_playlist = []  # An array of dictionaries with label id & resource
queue_name = f'playback_{MEDIA_PLAYER_ID}'

# Playback messaging
media_player_exchange = Exchange('media_player', 'direct', durable=True)
playback_queue = Queue(queue_name, exchange=media_player_exchange, routing_key=queue_name)


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
                    currently_playing_label_id = int(item['id'])

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
                                exchange=media_player_exchange, routing_key=queue_name,
                                declare=[playback_queue])

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            print(f'Failed to connect to {VLC_URL} with error: {e}')
        
        time.sleep(int(TIME_BETWEEN_PLAYBACK_STATUS))


def download_file(url):
    for _ in range(DOWNLOAD_RETRIES):
        try:
            local_filename = url.split('/')[-1]

            # Does the remote file exist?
            response = requests.head(url, allow_redirects=True)
            response.raise_for_status()

            # NOTE the stream=True parameter below
            with requests.get(url, stream=True) as r:
                with open('resources/' + local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): 
                        if chunk: # filter out keep-alive new chunks
                            f.write(chunk)
                            # f.flush()
            return local_filename
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            print(f'Failed to download the file {local_filename} with error {e}')
    print(f'Tried to download {url} {DOWNLOAD_RETRIES} times, giving up.')


def start_vlc():
    # TODO: Use vlc python bindings.
    # Play the playlist in vlc
    print('Starting VLC...')
    vlc_display_command = ['vlc', '--quiet', '--loop', '--fullscreen', '--no-random', '--no-video-title-show', '--video-on-top']
    playlist_of_resources = []
    for item in vlc_playlist:
        playlist_of_resources.append(item['resource'])
    subprocess.check_output(vlc_display_command + playlist_of_resources)


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
                'id': item['label'],
                'resource': local_video_path
            }
            vlc_playlist.append(item_dictionary)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')


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
except Exception as error:
    print(f'Video playback test failed with error {error}')


vlc_thread = Thread(target=start_vlc)
vlc_thread.start()

# Wait for VLC to launch
time.sleep(5)

playback_time_thread = Thread(target=post_playback_to_xos)
playback_time_thread.start()
