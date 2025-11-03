# playback_backend.py
import os
import vlc as _vlc  # keep available for VLC backend
import mpv as _mpv
import threading
import time

class VLCBackend:
    """Adapter exposing the few methods your code uses."""
    def __init__(self, flags):
        self.instance = _vlc.Instance(flags)
        self._list = self.instance.media_list_new()
        self._list_player = self.instance.media_list_player_new()
        self._player = self._list_player.get_media_player()
        self._list_player.set_media_list(self._list)

    # methods your code expects:
    def set_fullscreen(self, enable: bool):
        self._player.set_fullscreen(enable)

    def set_loop(self):
        self._list_player.set_playback_mode(_vlc.PlaybackMode.loop)

    def new_media(self, path: str):
        m = self.instance.media_new(path)
        m.parse()
        return m

    def media_get_duration(self, media):
        return media.get_duration()

    def playlist_add_media(self, media):
        self._list.add_media(media)

    def playlist_set(self):
        # already set in ctor
        pass

    def play(self):
        self._list_player.play()

    def play_item_at_index(self, idx: int):
        self._list_player.play_item_at_index(idx)

    def player_get_media(self):
        return self._player.get_media()

    def playlist_index_of_item(self, media):
        return self._list.index_of_item(media)

    def player_get_position(self):
        return self._player.get_position()

    def player_get_length(self):
        return self._player.get_length()

    def player_audio_get_volume(self):
        return self._player.audio_get_volume()

    def player_set_time(self, ms: int):
        self._player.set_time(ms)

class MPVBackend:
    """
    Drop-in replacement using mpv (ffmpeg) with DRM PRIME (hwdec on Pi 5).
    We emulate the subset of VLC calls your code uses.
    """
    def __init__(self, flags):
        # Allow optional override via env for debugging:
        hwdec = os.getenv('MPV_HWDEC', 'drm')           # 'drm' is correct for Pi 5 (V4L2-request/DRM PRIME)
        vo    = os.getenv('MPV_VO', 'gpu-next')         # modern VO (fallback to 'gpu' if needed)
        # NOTE: do NOT pass gpu_context to avoid the -7 error

        self._player = _mpv.MPV(
            hwdec=hwdec,
            vo=vo,
            fullscreen=True,
            profile='low-latency',
            osc=False,
            cursor_autohide='always',
            keep_open_pause=False,
            keep_open=False,
            msg_level='ffmpeg=info',
        )

        self._mpv = _mpv
        self._playlist = []
        self._index = -1
        self._dur_cache = {}
        self._position = 0.0
        self._length_ms = 0
        self._lock = threading.Lock()

        @self._player.property_observer('time-pos')
        def _(name, value):
            with self._lock:
                if value is None or self._length_ms <= 0:
                    self._position = 0.0
                else:
                    self._position = max(0.0, min(1.0, (value * 1000.0) / self._length_ms))

        @self._player.property_observer('duration')
        def _dur(name, value):
            with self._lock:
                self._length_ms = int((value or 0) * 1000)

        self._loop_thread = None
        self._loop_enabled = False

    # parity with VLC-backed calls your code makes:
    def set_fullscreen(self, enable: bool):
        self._player.fullscreen = bool(enable)

    def set_loop(self):
        self._loop_enabled = True

    def new_media(self, path: str):
        # For VLC parity we return the path as a "media" handle
        return path

    def media_get_duration(self, media):
        # quick probe by loading lightly then stopping
        path = media
        if path in self._dur_cache:
            return self._dur_cache[path]
        # Use demuxer to probe duration without playback if possible
        try:
            # Spawn a temp mpv instance to probe (fast)
            p = _mpv.MPV(quiet=True, msg_level='all=no', audio='no', video='no', cache_no_inotify=True)
            p.command('loadfile', path, 'replace')
            # give it a moment to demux
            time.sleep(0.2)
            dur = p.duration or 0
            p.command('stop')
            p.terminate()
        except Exception:
            dur = 0
        dur_ms = int(dur * 1000)
        self._dur_cache[path] = dur_ms
        return dur_ms

    def playlist_add_media(self, media):
        self._playlist.append(media)

    def playlist_set(self):
        pass

    def _play_current(self):
        if not (0 <= self._index < len(self._playlist)):
            return
        path = self._playlist[self._index]
        # set expected duration if known
        self._length_ms = self._dur_cache.get(path, 0)
        self._player.command('loadfile', path, 'replace')
        # ensure fullscreen
        self._player.fullscreen = True

    def _next_index(self):
        if not self._playlist:
            return -1
        nxt = self._index + 1
        if nxt >= len(self._playlist):
            nxt = 0 if self._loop_enabled else len(self._playlist) - 1
        return nxt

    def play(self):
        if not self._playlist:
            return
        if self._index < 0:
            self._index = 0
        self._play_current()

        # keep auto-advance if loop enabled
        if self._loop_thread is None:
            def looper():
                while True:
                    self._player.wait_for_playback()  # blocks until end-of-file
                    n = self._next_index()
                    if n < 0 or n == self._index:
                        # no loop or single item
                        continue
                    self._index = n
                    self._play_current()
            self._loop_thread = threading.Thread(target=looper, daemon=True)
            self._loop_thread.start()

    def play_item_at_index(self, idx: int):
        if 0 <= idx < len(self._playlist):
            self._index = idx
            self._play_current()

    def player_get_media(self):
        if 0 <= self._index < len(self._playlist):
            return self._playlist[self._index]
        return None

    def playlist_index_of_item(self, media):
        try:
            return self._playlist.index(media)
        except ValueError:
            return -1

    def player_get_position(self):
        with self._lock:
            return float(self._position)

    def player_get_length(self):
        with self._lock:
            return int(self._length_ms)

    def player_audio_get_volume(self):
        # mpv volume is 0..100
        try:
            return int(float(self._player.volume) / 100.0 * 256.0)
        except Exception:
            return 0

    def player_set_time(self, ms: int):
        self._player.command('seek', ms/1000.0, 'absolute')
