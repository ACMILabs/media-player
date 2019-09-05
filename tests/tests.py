import json
import os
import re
from unittest.mock import patch

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

    if args[0].startswith('https://museumos-prod.acmi.net.au/api/playlists/'):
        return MockResponse(file_to_string_strip_new_lines('data/playlist.json'), 200)

    return MockResponse(None, 404)


def test_media_player():
    """
    Test the Media Player class initialises.
    """

    media_player = MediaPlayer()
    assert not media_player.vlc_player
    assert media_player.playlist == []
    assert media_player.current_playlist_position == 0
    assert media_player.vlc_connection_attempts == 0


def test_datetime_now():
    """
    Test datetime_now() returns a valid date.
    """

    # https://stackoverflow.com/questions/41129921/validate-an-iso-8601-datetime-string-in-python
    # flake8: noqa: E501
    regex = r'^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$'  # pylint: disable=C0301
    match_iso8601 = re.compile(regex).match

    datetime = MediaPlayer().datetime_now()
    assert match_iso8601(datetime)


@patch('requests.get', side_effect=mocked_requests_get)
def test_download_playlist_from_xos(mock_get):
    """
    Test download_playlist_from_xos() returns a valid playlist.
    """

    media_player = MediaPlayer()
    media_player.download_playlist_from_xos()
    playlist = media_player.playlist

    assert len(playlist) == 3
    assert playlist[0]['resource'] == 'resources/sample.mp4'
    assert playlist[0]['subtitles'] == 'resources/sample.srt'
