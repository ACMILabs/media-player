from datetime import datetime
import dbus
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

    def __init__(self, omxplayer = None, playlist = [], current_playlist_position = 0):
        self.omxplayer = omxplayer
        self.playlist = playlist
        self.current_playlist_position = current_playlist_position


    def datetime_now_with_timezone_as_iso(self):
        return datetime.now(pytz_timezone).isoformat()


    def post_playback_to_xos(self):
        # TODO: Convert to dbus call
        while True:
            try:
                # Match playback filename with label id in media_playlist
                playback_position = self.omxplayer.position()
                currently_playing_label_id = None
                currently_playing_resource = os.path.basename(urlparse(str(self.omxplayer.get_filename())).path)
                for item in self.playlist:
                    item_filename = os.path.basename(urlparse(item['resource']).path)
                    if item_filename == currently_playing_resource:
                        currently_playing_label_id = int(item['label']['id'])

                media_player_status_json = {
                    "datetime": self.datetime_now_with_timezone_as_iso(),
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

            except (KeyError, requests.exceptions.HTTPError, requests.exceptions.ConnectionError, dbus.exceptions.DBusException, omxplayer.player.OMXPlayerDeadError) as e:
                template = 'An exception of type {0} occurred. Arguments:\n{1!r}'
                message = template.format(type(e).__name__, e.args)
                print(message)

            time.sleep(float(TIME_BETWEEN_PLAYBACK_STATUS))


    def download_file(self, url):
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


    def restart_media_player(self, player, exit_status):
        self.current_playlist_position += 1
        if self.current_playlist_position >= len(self.playlist):
            self.current_playlist_position = 0
        self.start_media_player()


    def start_media_player(self):
        text_playlist = self.generate_playlist()

        # Play the playlist in omxplayer
        print(f'Playing video {self.current_playlist_position}: {text_playlist[self.current_playlist_position]}')
        player_log = logging.getLogger("Media player 1")
        # TODO: Fix multiple file playing
        # import ipdb; ipdb.set_trace()
        self.omxplayer = OMXPlayer(Path(text_playlist[self.current_playlist_position]), dbus_name='org.mpris.MediaPlayer2.omxplayer1')
        self.omxplayer.exitEvent = self.restart_media_player



# Download playlist JSON from XOS
media_player = MediaPlayer()
try:
    response = requests.get(XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID)
    response.raise_for_status()
    playlist_labels = response.json()['playlist_labels']

    # Download resource if it isn't available locally
    for item in playlist_labels:
        resource_url = item['resource']
        video_filename = os.path.basename(urlparse(resource_url).path)
        local_video_path = 'resources/' + video_filename
        
        if not os.path.isfile(local_video_path):
            print(f'{video_filename} not available locally, attempting to download it now.')
            media_player.download_file(resource_url)
        
        # If it's now available locally, add it to the playlist to be played
        if os.path.isfile(local_video_path):
            # TODO: An array of dicts that has the label_id and resource
            item_dictionary = {
                'label': item['label'],
                'resource': local_video_path
            }
            media_player.playlist.append(item_dictionary)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')


media_player.start_media_player()

# Wait for Media Player to launch
time.sleep(2)

media_player.post_playback_to_xos()
