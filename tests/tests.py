import pytest
import re

from media_player import MediaPlayer


def test_media_player():
    """
    Test the Media Player class initialises.
    """

    m = MediaPlayer()
    assert not m.vlc
    assert m.playlist == []
    assert m.current_playlist_position == 0
    assert m.vlc_connection_attempts == 0


def test_datetime_now():
    """
    Test datetime_now() returns a valid date.
    """

    # From https://stackoverflow.com/questions/41129921/validate-an-iso-8601-datetime-string-in-python
    regex = r'^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$'
    match_iso8601 = re.compile(regex).match

    datetime = MediaPlayer().datetime_now()
    assert match_iso8601(datetime)


def test_download_playlist_from_xos():
    """
    Test download_playlist_from_xos() returns a valid playlist.
    """

    m = MediaPlayer()
    m.download_playlist_from_xos()
    playlist = m.playlist

    assert len(playlist) == 3
    assert playlist[0]['resource'] == 'resources/dracula.mp4'
    assert playlist[0]['subtitles'] == 'resources/dracula.srt'
