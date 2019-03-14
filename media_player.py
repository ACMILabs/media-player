import os
import requests
import subprocess
from datetime import datetime
from urllib.parse import urlparse

import pytz
import vlc


XOS_PLAYLIST_ENDPOINT = os.getenv('XOS_PLAYLIST_ENDPOINT')
XOS_PLAYBACK_STATUS_ENDPOINT = os.getenv('XOS_PLAYBACK_STATUS_ENDPOINT')
PLAYLIST_ID = os.getenv('PLAYLIST_ID')
DOWNLOAD_RETRIES = int(os.getenv('DOWNLOAD_RETRIES'))

pytz_timezone = pytz.timezone('Australia/Melbourne')
vlc_playlist = []


def datetime_now():
    return datetime.now(pytz_timezone).isoformat()


def post_status_to_xos():
    # TODO: POST the current playback status to XOS
    data = {
        'status_datetime': datetime_now()  # ISO8601 format
    }
    try:
        response = requests.post(XOS_PLAYBACK_STATUS_ENDPOINT, json=data)
        response.raise_for_status()
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
        print(f'Failed to connect to {XOS_PLAYBACK_STATUS_ENDPOINT} with error: {e}')


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


# Download playlist JSON from XOS
try:
    response = requests.get(XOS_PLAYLIST_ENDPOINT + PLAYLIST_ID)
    response.raise_for_status()
    playlist = response.json()['playlist_labels']

    # Download resource if it isn't available locally
    for item in playlist:
        resource_url = item['resource']
        video_filename = os.path.basename(urlparse(resource_url).path)
        
        if not os.path.isfile('resources/' + video_filename):
            print(f'{video_filename} not available locally, attempting to download it now.')
            download_file(resource_url)
        
        # If it's now available locally, add it to the playlist to be played
        if os.path.isfile('resources/' + video_filename):
            vlc_playlist.append('resources/' + video_filename)

except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
    print(f'Failed to connect to {XOS_PLAYLIST_ENDPOINT} with error: {e}')


# Check if vlc can play the media in vlc_playlist
try:
    for video in vlc_playlist:
        player = vlc.MediaPlayer(video)
        media = player.get_media() 
        media.parse()
        if media.get_duration():
            # OK to play
            pass
        else:
            print(f'Video doesn\'t seem playable: {video}, removing from the playlist.')
            vlc_playlist.remove(video)
except Exception as error:
    print(f'Video playback test failed with error {error}')


# TODO: Use vlc python bindings.
# Play the playlist in vlc
vlc_display_command = ['vlc', '--loop', '--fullscreen', '--no-random', '--no-spu', '--no-osd', '--no-input-fast-seek', '--no-interact', '--no-video-title-show', '--video-on-top']
print(subprocess.check_output(vlc_display_command + vlc_playlist))
