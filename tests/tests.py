import json
import os
from shutil import copyfile
from unittest.mock import MagicMock, patch

import requests

from media_player import MediaPlayer


def file_to_string_strip_new_lines(filename):
    """
    Read file and return as string with new line characters stripped
    :param filename: a filename relative to the current working directory.
    e.g. 'xml_files/example.xml' or 'example.xml'
    :return: a string representation of the contents of filename, with new line characters removed
    """
    # get current working directory
    cwd = os.path.dirname(__file__)
    file_as_string = ""

    # open filename assuming filename is relative to current working directory
    with open(os.path.join(cwd, filename), 'r') as file_obj:
        # strip new line characters
        file_as_string = file_obj.read().replace('\n', '')
    # return string
    return file_as_string


def mocked_requests_get(*args, **kwargs):
    """
    Thanks to https://stackoverflow.com/questions/15753390/how-can-i-mock-requests-and-the-response
    """
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.content = json.loads(json_data)
            self.status_code = status_code

        def json(self):
            return self.content

        def raise_for_status(self):
            return None

    if args[0].startswith('https://xos.acmi.net.au/api/playlists/'):
        return MockResponse(file_to_string_strip_new_lines('data/playlist.json'), 200)

    return MockResponse(None, 404)


def test_media_player():
    """
    Test the Media Player class initialises.
    """

    media_player = MediaPlayer()
    assert media_player.playlist == []
    assert len(media_player.vlc) == 4
    for vlc_var in media_player.vlc.values():
        assert vlc_var is not None


@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
@patch('media_player.CACHED_PLAYLIST_JSON', 'test_cached_playlist.json')
def test_download_playlist_from_xos():
    """
    Test download_playlist_from_xos() returns a valid playlist.
    """

    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()
    playlist = media_player.playlist

    assert len(playlist) == 3
    assert playlist[0]['resource'] == '/data/resources/sample.mp4'
    assert playlist[0]['subtitles'] == '/data/resources/sample.srt'


@patch('os.remove', MagicMock())
@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
def test_delete_unneeded_resources():
    """
    Test delete_unneeded_resources() deletes the expected files.
    """

    media_player = MediaPlayer()
    playlist = json.loads(
        file_to_string_strip_new_lines('data/playlist.json')
    )['playlist_labels']
    files_deleted = media_player.delete_unneeded_resources(playlist)

    assert len(files_deleted) == 0

    playlist_2 = json.loads(
        file_to_string_strip_new_lines('data/playlist-2.json')
    )['playlist_labels']
    files_deleted_2 = media_player.delete_unneeded_resources(playlist_2)

    assert len(files_deleted_2) == 2
    assert 'sample.mp4' in files_deleted_2
    assert 'sample.srt' in files_deleted_2


@patch('alsaaudio.Mixer', MagicMock())
@patch('alsaaudio.mixers', MagicMock())
def test_get_media_player_status():
    """
    Test get_media_player_status correctly outputs playback data.
    """
    media_player = MediaPlayer()
    media_player.playlist = [
        {
            'label': {
                'id': 123
            }
        },
        {
            'label': {
                'id': 456
            }
        },
        {
            'label': None
        },
    ]

    mock_vlc_player = MagicMock()
    mock_vlc_player.get_media = MagicMock(return_value=MagicMock())
    media_player.vlc['player'] = mock_vlc_player

    mock_vlc_playlist = MagicMock()
    mock_vlc_playlist.index_of_item = MagicMock(return_value=1)
    media_player.vlc['playlist'] = mock_vlc_playlist
    status = media_player.get_media_player_status()

    mock_vlc_playlist.index_of_item = MagicMock(return_value=2)
    media_player.vlc['playlist'] = mock_vlc_playlist
    status_two = media_player.get_media_player_status()

    assert 'datetime' in status.keys()
    assert status['playlist_position'] == 1
    assert status['label_id'] == 456
    assert status_two['label_id'] is None


@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
@patch('media_player.CACHED_PLAYLIST_JSON', 'test_cached_playlist.json')
def test_cache_playlist():
    """
    Test that a downloaded playlist is cached.
    """

    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()
    playlist = media_player.playlist

    with open('test_cached_playlist.json', encoding='utf-8') as json_file:
        json_data = json.load(json_file)
        playlist_labels = json_data['playlist_labels']

        expected_resource = os.path.basename(playlist_labels[0]['resource'])
        resource = os.path.basename(playlist[0]['resource'])
        assert resource == expected_resource

        subtitles = os.path.basename(playlist[0]['subtitles'])
        expected_subtitles = os.path.basename(playlist_labels[0]['subtitles'])
        assert subtitles == expected_subtitles

    os.remove('test_cached_playlist.json')


@patch('requests.get', MagicMock(side_effect=requests.exceptions.ConnectionError()))
@patch('media_player.CACHED_PLAYLIST_JSON', 'test_cached_playlist.json')
def test_still_plays_if_cannot_reach_xos():
    """
    Test that a playlist is not empty even if XOS is unreachable.
    """
    copyfile('tests/data/test_cached_playlist.json', 'test_cached_playlist.json')
    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()

    assert len(media_player.playlist) == 9

    os.remove('test_cached_playlist.json')


@patch('requests.get', MagicMock(side_effect=requests.exceptions.ConnectionError()))
@patch('media_player.CACHED_PLAYLIST_JSON', 'test_cached_playlist.json')
def test_empty_playlist_if_cannot_reach_xos_and_no_cache():
    """
    Test that if XOS is unreachable and there is no cache, the playlist is empty.
    """
    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()

    assert not media_player.playlist
