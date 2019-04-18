from datetime import datetime
import logging
import os
from pathlib import Path
import requests
import subprocess
from threading import Thread
import time
from urllib.parse import urlparse

from kombu import Connection, Exchange, Queue
from omxplayer.player import OMXPlayer
import pytz


XOS_PLAYLIST_ENDPOINT = os.getenv('XOS_PLAYLIST_ENDPOINT')
PLAYLIST_ID = os.getenv('PLAYLIST_ID')
MEDIA_PLAYER_ID = os.getenv('MEDIA_PLAYER_ID')
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES'))
AMQP_URL = os.getenv('AMQP_URL')
VLC_URL = os.getenv('VLC_URL')
VLC_PASSWORD = os.getenv('VLC_PASSWORD')
TIME_BETWEEN_PLAYBACK_STATUS = os.getenv('TIME_BETWEEN_PLAYBACK_STATUS')
USE_PLS_PLAYLIST = os.getenv('USE_PLS_PLAYLIST')

pytz_timezone = pytz.timezone('Australia/Melbourne')
media_playlist = []  # An array of dictionaries with label id & resource
queue_name = f'mqtt-subscription-playback_{MEDIA_PLAYER_ID}'
routing_key = f'mediaplayer.{MEDIA_PLAYER_ID}'

# Playback messaging
media_player_exchange = Exchange('amq.topic', 'direct', durable=True)
playback_queue = Queue(queue_name, exchange=media_player_exchange, routing_key=routing_key)


def datetime_now():
    return datetime.now(pytz_timezone).isoformat()


def post_playback_to_xos():
    # TODO: Convert to dbus call
    while True:
        try:
            # Get playback status from VLC
            session = requests.Session()
            session.auth = ('', VLC_PASSWORD)
            response = session.get(VLC_URL + 'requests/status.json')
            response.raise_for_status()
            vlc_status = response.json()

            # Match playback filename with label id in media_playlist
            playback_position = vlc_status['position']
            currently_playing_label_id = None
            currently_playing_resource = os.path.basename(urlparse(vlc_status['information']['category']['meta']['filename']).path)
            for item in media_playlist:
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
        
        time.sleep(float(TIME_BETWEEN_PLAYBACK_STATUS))


def download_file(url):
    for _ in range(DOWNLOAD_RETRIES):
        try:
            local_filename = url.split('/')[-1]

            # Does the remote file exist?
            response = requests.head(url, allow_redirects=True)
            response.raise_for_status()

            # Make the resources directory if it doesn't exist
            if not os.path.exists('resources'):
                os.makedirs('resources')

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


def generate_pls_playlist():
    # Generates a playlist.pls file and returns the filename
    pls_filename = 'resources/playlist.pls'
    pls_string = '[playlist]\n'
    for idx, item in enumerate(media_playlist, start=1):
        pls_string += (f"File{idx + 1}={item['resource'].split('/')[-1]}\n")
    pls_string += f'NumberOfEntries={len(media_playlist)}\nVersion=2'
    with open(pls_filename, 'w') as f:
        f.write(pls_string)
    if Path(pls_filename).exists():
        return pls_filename
    else:
        return None


def generate_playlist():
    # Generates a list of files to hand into the VLC call
    playlist = []
    for item in media_playlist:
        playlist.append(item['resource'])
    return playlist


def start_media_player():
    playlist = generate_playlist()
    if int(USE_PLS_PLAYLIST) == 1:
        playlist = [generate_pls_playlist()]

    # Play the playlist in omxplayer
    print('Starting Omxplayer...')
    player_log = logging.getLogger("Media player 1")
    # TODO: Fix multiple file playing
    # import ipdb; ipdb.set_trace()
    player = OMXPlayer(Path(playlist[0]), dbus_name='org.mpris.MediaPlayer2.omxplayer1')
    # player.playEvent += lambda _: player_log.info("Play")
    # player.pauseEvent += lambda _: player_log.info("Pause")
    # player.stopEvent += lambda _: player_log.info("Stop")
    # it takes about this long for omxplayer to warm up and start displaying a picture on a rpi3
    time.sleep(2.5)
    player.set_aspect_mode('stretch')
    player.set_video_pos(0, 0, 200, 200)
    player.play()


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
            media_playlist.append(item_dictionary)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')


start_media_player()
# media_player_thread = Thread(target=start_media_player)
# media_player_thread.start()

# Wait for Media Player to launch
time.sleep(5)

# playback_time_thread = Thread(target=post_playback_to_xos)
# playback_time_thread.start()
