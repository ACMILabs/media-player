#!/bin/bash

log() {
  echo "[x86] $*"
}

dump_xorg_logs() {
  local found=false
  local logfile

  for logfile in \
    /var/log/Xorg.0.log \
    /var/log/Xorg.0.log.old \
    /root/.local/share/xorg/Xorg.0.log \
    /root/.local/share/xorg/Xorg.0.log.old; do
    if [[ -f "$logfile" ]]; then
      found=true
      log "Last 250 lines of ${logfile}:"
      tail -n 250 "$logfile"
    fi
  done

  if [[ "$found" == false ]]; then
    log "No Xorg log file was found"
  fi
}

dump_diagnostics() {
  log "System: $(uname -a)"
  log "Python: $(python --version 2>&1)"
  log "Display environment: DISPLAY=${DISPLAY:-unset}, XAUTHORITY=${XAUTHORITY:-unset}, XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-unset}"

  log "DRM devices:"
  ls -la /dev/dri 2>&1 || true

  log "Display hardware:"
  lspci -nnk 2>&1 | grep -A3 -Ei 'vga|display|3d' || true

  log "X sockets and locks:"
  ls -la /tmp/.X11-unix /tmp/.X*-lock 2>&1 || true

  log "Relevant processes:"
  ps -ef 2>&1 | grep -E '[X]org|[x]init|[s]tartx|[x]fce|[v]lc|media_player' || true
}

fail_startup() {
  log "ERROR: $*"
  sleep 1
  dump_diagnostics
  dump_xorg_logs
  exit 1
}

X_PID=
PLAYER_PID=

terminate_children() {
  if [[ -n "$PLAYER_PID" ]] && kill -0 "$PLAYER_PID" 2>/dev/null; then
    kill "$PLAYER_PID" 2>/dev/null || true
  fi
  if [[ -n "$X_PID" ]] && kill -0 "$X_PID" 2>/dev/null; then
    kill "$X_PID" 2>/dev/null || true
  fi
}

trap 'terminate_children; exit 143' TERM INT

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# Set the display to use
export DISPLAY=:0
export XAUTHORITY=/root/.Xauthority

# Set the DBUS address for sending around system messages
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

# XDG_RUNTIME_DIR must be one absolute, user-owned directory with mode 0700.
export XDG_RUNTIME_DIR=/tmp/xdg-runtime-root
install -d -m 0700 "$XDG_RUNTIME_DIR"

# Create Xauthority
touch "$XAUTHORITY"
chmod 0600 "$XAUTHORITY"

# Remove stale display state left by an unclean container restart. Do not
# disturb a live X server if one is already listening on the expected display.
if ! xset -q >/dev/null 2>&1; then
  if [[ -f /tmp/.X0-lock ]]; then
    LOCK_PID=$(tr -cd '0-9' < /tmp/.X0-lock)
    if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
      fail_startup "Display ${DISPLAY} is locked by live process ${LOCK_PID}"
    fi
    log "Removing stale X lock /tmp/.X0-lock"
    rm -f /tmp/.X0-lock
  fi
  if [[ -S /tmp/.X11-unix/X0 ]]; then
    log "Removing stale X socket /tmp/.X11-unix/X0"
    rm -f /tmp/.X11-unix/X0
  fi
fi

dump_diagnostics

# Start desktop manager
log "Starting X on ${DISPLAY}"
startx -- "$DISPLAY" -nocursor &
X_PID=$!
log "startx process is ${X_PID}"

# Wait up to 30 seconds for the X server to accept authenticated clients.
X_READY=false
for attempt in $(seq 1 60); do
  if xset -q >/dev/null 2>&1; then
    X_READY=true
    log "X is ready on ${DISPLAY} after ${attempt} probe(s)"
    break
  fi

  if ! kill -0 "$X_PID" 2>/dev/null; then
    wait "$X_PID"
    fail_startup "X exited before becoming ready (status $?)"
  fi

  sleep 0.5
done
if [[ "$X_READY" != true ]]; then
  fail_startup "X did not become ready within 30 seconds"
fi

# X accepting clients does not guarantee that the Xfce session is ready.
XFCE_READY=false
for attempt in $(seq 1 60); do
  if pgrep -x xfce4-session >/dev/null 2>&1; then
    XFCE_READY=true
    log "Xfce session is ready after ${attempt} probe(s)"
    break
  fi
  if ! kill -0 "$X_PID" 2>/dev/null; then
    fail_startup "X exited while waiting for the Xfce session"
  fi
  sleep 0.5
done
if [[ "$XFCE_READY" != true ]]; then
  fail_startup "Xfce did not become ready within 30 seconds"
fi

# Give Xfce services a short opportunity to finish registering with D-Bus.
sleep 2

# Prevent blanking and screensaver
xset s off -dpms || fail_startup "Unable to disable display blanking"

# Hide the cursor
unclutter -idle 0.1 &

# Set X background image
if ! xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/workspace0/last-image --set /code/resources/blank-1920x1080.png; then
  log "WARNING: Unable to set the Xfce background image"
fi

# Hide X icons
if ! xfconf-query -c xfce4-desktop -np '/desktop-icons/style' -t 'int' -s '0'; then
  log "WARNING: Unable to hide Xfce desktop icons"
fi

# Hide X panel
if pgrep -x xfce4-panel >/dev/null 2>&1; then
  xfce4-panel -q || log "WARNING: Unable to stop the Xfce panel"
else
  log "Xfce panel is not running"
fi

log "Connected displays and modes:"
xrandr --query || fail_startup "Unable to query connected displays"

log "OpenGL renderer:"
timeout 10 glxinfo -B 2>&1 || log "WARNING: glxinfo did not complete successfully"

log "VA-API capabilities:"
timeout 10 vainfo --display x11 2>&1 || log "WARNING: vainfo did not complete successfully"

# rotate screen if env variable is set [normal, inverted, left or right]
if [[ ! -z "$ROTATE_DISPLAY" ]]; then
  log "Rotating display ${ROTATE_DISPLAY}"
  (sleep 3 && xrandr -o $ROTATE_DISPLAY) &
fi

# Set display size and frames-per-second refresh rate
# Note: SCREEN_WIDTH and SCREEN_HEIGHT also tell VLC to play the video at that size too
if [[ ! -z "$SCREEN_WIDTH" ]] && [[ ! -z "$SCREEN_HEIGHT" ]] && [[ ! -z "$FRAMES_PER_SECOND" ]]; then
  log "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT} @${FRAMES_PER_SECOND}"
  xrandr -s "$SCREEN_WIDTH"x"$SCREEN_HEIGHT" -r $FRAMES_PER_SECOND
elif [[ ! -z "$SCREEN_WIDTH" ]] && [[ ! -z "$SCREEN_HEIGHT" ]]; then
  log "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
  xrandr -s "$SCREEN_WIDTH"x"$SCREEN_HEIGHT"
fi

# If headphones audio is selected, we need to unmute Master audio
if [[ ! -z "$AUDIO_DEVICE_REGEX" ]] && [[ $AUDIO_DEVICE_REGEX == "headphones" ]]; then
  log "Headphones selected, so un-muting master audio..."
  ./scripts/unmute.sh
  log "Setting AUDIO_DEVICE_REGEX to 'analog' for Optiplex 3070..."
  export AUDIO_DEVICE_REGEX=analog
fi

log "Starting media player"
python media_player.py &
PLAYER_PID=$!
log "Media player process is ${PLAYER_PID}"

# Keep the container tied to both the player and the display. Three failed X
# probes avoid restarting on a single transient error.
X_FAILURES=0
while kill -0 "$PLAYER_PID" 2>/dev/null; do
  if ! kill -0 "$X_PID" 2>/dev/null; then
    log "ERROR: X exited while the media player was running"
    terminate_children
    dump_diagnostics
    dump_xorg_logs
    exit 1
  fi

  if xset -q >/dev/null 2>&1; then
    X_FAILURES=0
  else
    X_FAILURES=$((X_FAILURES + 1))
    log "WARNING: X health probe failed (${X_FAILURES}/3)"
    if [[ "$X_FAILURES" -ge 3 ]]; then
      log "ERROR: X is no longer accepting clients"
      terminate_children
      dump_diagnostics
      dump_xorg_logs
      exit 1
    fi
  fi

  sleep 5
done

wait "$PLAYER_PID"
PLAYER_STATUS=$?
log "Media player exited with status ${PLAYER_STATUS}"
terminate_children
exit "$PLAYER_STATUS"
