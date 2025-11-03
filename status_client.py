import os

from prometheus_client import Counter, Gauge, Info, start_http_server

DEVICE_INFO = Info('device', 'Device')
FILENAME_INFO = Info('filename', 'Filename')
DURATION_GAUGE = Gauge('duration', 'Duration')
PLAYBACK_POSITION_GAUGE = Gauge('playback_position', 'Playback position')
LOOP_COUNTER = Counter('number_loops', 'Number of loops')
PLAYLIST_POSITION_GAUGE = Gauge('position_playlist', 'Position in playlist')
LABEL_INFO = Info('label', 'Label')
DROPPED_AUDIO_FRAMES_GAUGE = Gauge('dropped_audio_frames', 'Dropped audio frames')
DROPPED_VIDEO_FRAMES_GAUGE = Gauge('dropped_video_frames', 'Dropped video frames')
PLAYER_VOLUME_GAUGE = Gauge('player_volume', 'VLC volume')
SYSTEM_VOLUME_GAUGE = Gauge('system_volume', 'System volume')
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "1007"))


def set_status(
        uuid,
        device_name,
        filename,
        media_player_status,
        ):
    """
    Sets values in the prometheus client's gauges and info metrics.
    """
    DEVICE_INFO.info({
        'uuid': uuid,
        'name': device_name
    })
    FILENAME_INFO.info({'filename': str(filename)})
    DURATION_GAUGE.set(media_player_status['duration'])
    PLAYBACK_POSITION_GAUGE.set(media_player_status['playback_position'])
    PLAYLIST_POSITION_GAUGE.set(media_player_status['playlist_position'])
    LABEL_INFO.info({'id': str(media_player_status['label_id'])})
    if media_player_status['dropped_audio_frames']:
        DROPPED_AUDIO_FRAMES_GAUGE.set(media_player_status['dropped_audio_frames'])
    if media_player_status['dropped_video_frames']:
        DROPPED_VIDEO_FRAMES_GAUGE.set(media_player_status['dropped_video_frames'])
    PLAYER_VOLUME_GAUGE.set(media_player_status['player_volume'])
    SYSTEM_VOLUME_GAUGE.set(media_player_status['system_volume'])


start_http_server(PROMETHEUS_PORT)
