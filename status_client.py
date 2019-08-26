from prometheus_client import Counter, Gauge, Info, start_http_server


device_info = Info('device', 'Device')
filename_info = Info('filename', 'Filename')
duration_gauge = Gauge('duration', 'Duration')
playback_position_gauge = Gauge('playback_position', 'Playback position')
loop_counter = Counter('number_loops', 'Number of loops')
position_playlist_gauge = Gauge('position_playlist', 'Position in playlist')
label_info = Info('label', 'Label')
audio_buffer_gauge = Gauge('audio_buffer', 'Audio buffer')
video_buffer_gauge = Gauge('video_buffer', 'Video buffer')
player_volume_gauge = Gauge('player_volume', 'VLC volume')
system_volume_gauge = Gauge('system_volume', 'System volume')

def set_status(uuid, device_name, filename, duration, playback_position,
    position_playlist, label_id, audio_buffer, video_buffer, player_volume, system_volume):
        """
        Sets values in the prometheus client's gauges and info metrics
        """
        device_info.info({
            'uuid': str(uuid),
            'name': device_name
        })
        filename_info.info({'filename': str(filename)})
        duration_gauge.set(duration)
        playback_position_gauge.set(playback_position)
        position_playlist_gauge.set(position_playlist)
        label_info.info({'id': str(label_id)})
        if audio_buffer:
            audio_buffer_gauge.set(audio_buffer)
        if video_buffer:
            video_buffer_gauge.set(video_buffer)
        player_volume_gauge.set(player_volume)
        system_volume_gauge.set(system_volume)


start_http_server(1007)
