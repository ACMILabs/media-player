from prometheus_client import Counter, Gauge, Info, start_http_server

DEVICE_INFO = Info('device', 'Device')
FILENAME_INFO = Info('filename', 'Filename')
DURATION_GAUGE = Gauge('duration', 'Duration')
PLAYBACK_POSITION_GAUGE = Gauge('playback_position', 'Playback position')
LOOP_COUNTER = Counter('number_loops', 'Number of loops')
POSITION_PLAYLIST_GAUGE = Gauge('position_playlist', 'Position in playlist')
LABEL_INFO = Info('label', 'Label')
DROPPED_AUDIO_FRAMES_GAUGE = Gauge('dropped_audio_frames', 'Dropped audio frames')
DROPPED_VIDEO_FRAMES_GAUGE = Gauge('dropped_video_frames', 'Dropped video frames')
PLAYER_VOLUME_GAUGE = Gauge('player_volume', 'VLC volume')
SYSTEM_VOLUME_GAUGE = Gauge('system_volume', 'System volume')


def set_status(
        uuid,
        device_name,
        filename,
        duration,
        playback_position,
        position_playlist,
        label_id,
        dropped_audio_frames,
        dropped_video_frames,
        player_volume,
        system_volume,
        ):  # pylint: disable=R0913
    """
    Sets values in the prometheus client's gauges and info metrics.
    """
    DEVICE_INFO.info({
        'uuid': str(uuid),
        'name': device_name
    })
    FILENAME_INFO.info({'filename': str(filename)})
    DURATION_GAUGE.set(duration)
    PLAYBACK_POSITION_GAUGE.set(playback_position)
    POSITION_PLAYLIST_GAUGE.set(position_playlist)
    LABEL_INFO.info({'id': str(label_id)})
    if dropped_audio_frames:
        DROPPED_AUDIO_FRAMES_GAUGE.set(dropped_audio_frames)
    if dropped_video_frames:
        DROPPED_VIDEO_FRAMES_GAUGE.set(dropped_video_frames)
    PLAYER_VOLUME_GAUGE.set(player_volume)
    SYSTEM_VOLUME_GAUGE.set(system_volume)


start_http_server(1007)
