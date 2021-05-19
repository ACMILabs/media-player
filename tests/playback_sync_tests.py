import signal
from unittest.mock import MagicMock, patch

import pytest

from media_player import MediaPlayer

TIMEOUT_SECS = 5


def assert_called_in_infinite_loop(func_called, func_infinite):
    """
    Helper function that asserts whether a function is called within an infinite loop.
    """
    def infinite_loop_terminator(signum, frame):
        raise TimeoutError('Infinite loop has run for too long.')
    signal.signal(signal.SIGALRM, infinite_loop_terminator)

    func_mock = MagicMock(side_effect=AssertionError(f'{func_called} is called'))
    with patch(func_called, func_mock):
        try:
            signal.alarm(TIMEOUT_SECS)
            func_infinite()
            print(f'Error: Function {func_called} was not called.')
            assert False
        except TimeoutError:
            signal.alarm(0)
            assert False
        except AssertionError as ex:
            signal.alarm(0)
            assert f'{func_called} is called' in str(ex)


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_client_set_up():
    """
    Check that the client is correctly set up.
    """
    player = MediaPlayer()
    assert player.client is not None
    assert getattr(player, 'server', None) is None


@patch('media_player.network.Server', MagicMock())
@patch('media_player.SYNC_IS_SERVER', 'true')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_server_set_up():
    """
    Check that the server is correctly set up.
    """
    player = MediaPlayer()
    assert player.server is not None
    assert getattr(player, 'client', None) is None


@patch('media_player.vlc.libvlc_clock', MagicMock(
    side_effect=[0, 10 * (10 ** 3), 20 * (10 ** 3)]
))
def test_get_current_time_interpolates():
    """
    Check that get_current_time interpolates the time from vlc.
    """
    player = MediaPlayer()
    mock_player = MagicMock()
    mock_player.get_time = MagicMock(return_value=250)
    player.vlc['player'] = mock_player
    assert player.get_current_time() == 250
    assert player.get_current_time() == 260
    assert player.get_current_time() == 270


def test_run_timer():
    """
    Check that the get_current_time method gets called when running the timer.
    """
    player = MediaPlayer()
    assert_called_in_infinite_loop(
        'media_player.MediaPlayer.get_current_time',
        player.run_timer
    )


@patch('media_player.network.Server', MagicMock())
@patch('media_player.SYNC_IS_SERVER', 'true')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_server_sends_time_to_client():
    """
    Check that the server sends data to the clients.
    """
    player = MediaPlayer()
    player.get_current_playlist_position = MagicMock(return_value=1)
    assert_called_in_infinite_loop(
        'media_player.MediaPlayer.get_current_time',
        player.sync_to_server
    )

    with pytest.raises(AssertionError):
        player.get_current_playlist_position = MagicMock(return_value=None)
        assert_called_in_infinite_loop(
            'media_player.MediaPlayer.get_current_time',
            player.sync_to_server
        )


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_client_receives_time_from_server():
    """
    Check that the client receives data from the server.
    """
    player = MediaPlayer()
    assert_called_in_infinite_loop(
        'media_player.MediaPlayer.get_current_time',
        player.sync_to_server
    )


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_client_drifts_from_server():
    """
    Check that if the time drifts, the client calls set_time on its player.
    """
    player = MediaPlayer()
    player.client.receive = MagicMock(return_value=[1, 50])
    player.get_current_time = MagicMock(return_value=100)
    player.get_current_playlist_position = MagicMock(return_value=1)
    player.vlc['player'].get_length = MagicMock(return_value=3000)
    assert_called_in_infinite_loop(
        'vlc.MediaPlayer.set_time',
        player.sync_to_server
    )
    with pytest.raises(AssertionError):
        # Assert playlist sync isn't called
        assert_called_in_infinite_loop(
            'vlc.MediaListPlayer.play_item_at_index',
            player.sync_to_server
        )

    # Assert sync isn't called within 2 seconds of the end of the current video
    with pytest.raises(AssertionError):
        player.client.receive = MagicMock(return_value=[1, 2500])
        player.get_current_time = MagicMock(return_value=2000)
        assert_called_in_infinite_loop(
            'vlc.MediaPlayer.set_time',
            player.sync_to_server
        )


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_client_drifts_from_server_sets_playlist_position():
    """
    Check that if the time drifts on a server playing a playlist,
    the client calls play_item_at_index on its player.
    """
    player = MediaPlayer()
    player.client.receive = MagicMock(return_value=[2, 50])
    player.get_current_time = MagicMock(return_value=100)
    player.get_current_playlist_position = MagicMock(return_value=1)
    player.vlc['player'].get_length = MagicMock(return_value=3000)
    assert_called_in_infinite_loop(
        'vlc.MediaListPlayer.play_item_at_index',
        player.sync_to_server
    )


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_client_playlist_position_set_without_drift():
    """
    Check that a client's playlist position is set even if
    the client hasn't drifted from the server.
    """
    player = MediaPlayer()
    player.client.receive = MagicMock(return_value=[2, 95])
    player.get_current_time = MagicMock(return_value=100)
    player.get_current_playlist_position = MagicMock(return_value=1)
    player.vlc['player'].get_length = MagicMock(return_value=3000)
    assert_called_in_infinite_loop(
        'vlc.MediaListPlayer.play_item_at_index',
        player.sync_to_server
    )

    with pytest.raises(AssertionError):
        # Assert playlist sync isn't called
        player.get_current_playlist_position = MagicMock(return_value=2)
        assert_called_in_infinite_loop(
            'vlc.MediaListPlayer.play_item_at_index',
            player.sync_to_server
        )


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_sync_check():
    """
    Test that setup_sync is called as expected in sync_check.
    """
    player = MediaPlayer()
    with patch.object(MediaPlayer, 'setup_sync', wraps=player.setup_sync) as mock_setup_sync:
        player.client.sync_attempts = 1
        player.sync_check()
        assert mock_setup_sync.call_count == 0
        player.client.sync_attempts = 4
        player.sync_check()
        assert mock_setup_sync.call_count == 1


@patch('media_player.network.Client', MagicMock())
@patch('media_player.SYNC_CLIENT_TO', '100.100.100.100')
@patch('media_player.IS_SYNCED_PLAYER', True)
def test_sync_to_server():
    """
    Test that sync_to_server successfully resyncs for exceptions.
    """
    player = MediaPlayer()
    player.client.receive = MagicMock(return_value=None)
    player.client.sync_attempts = 1
    assert_called_in_infinite_loop(
        'media_player.MediaPlayer.sync_check',
        player.sync_to_server,
    )

    player.client.receive = MagicMock(return_value=[0, 0])
    player.client.sync_attempts = 1
    assert_called_in_infinite_loop(
        'media_player.MediaPlayer.sync_check',
        player.sync_to_server,
    )
