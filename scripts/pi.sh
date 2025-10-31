#!/bin/bash
set -euo pipefail

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# Helpful logs
echo "[entrypoint] Booting seatd + weston (Wayland) + VLC Python player"

# Wayland runtime dir
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/0}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Environment hints to keep things on Wayland/DRM and ALSA
export QT_QPA_PLATFORM=wayland
export SDL_VIDEODRIVER=wayland
export MOZ_ENABLE_WAYLAND=1
export LIBSEAT_BACKEND=logind,seatd

# Start seatd so weston can access input/tty without full systemd
# (ignore error if already running in a multi-service stack)
if ! pgrep -x seatd >/dev/null 2>&1; then
  echo "[entrypoint] starting seatd"
  seatd -g video &
fi

# Start Weston (DRM backend, fullscreen shell). Logs go to stdout.
# --tty=1 is typical for single-seat kiosk; drop it if it conflicts in your stack.
echo "[entrypoint] starting weston"
weston --backend=drm-backend.so \
       --socket=wayland-0 \
       --log=/dev/stdout \
       --tty=1 \
       --idle-time=0 &
WESTON_PID=$!

# Wait for Wayland socket
echo -n "[entrypoint] waiting for wayland-0 socket"
for i in $(seq 1 50); do
  if [ -S "$XDG_RUNTIME_DIR/wayland-0" ]; then
    echo " ...ready"
    break
  fi
  echo -n "."
  sleep 0.1
done

# Make sure ALSA sees cards; useful debug line
aplay -l || true

# Prefer hardware decoding + full-screen Wayland output; your Python builds its own VLC flags,
# so we append via env var and read it inside (merge in your code or export here for libvlc)
export VLC_ARGS="${VLC_HW_ARGS}"

# rotate screen if env variable is set [normal, inverted, left or right]
# if [[ -n "${ROTATE_DISPLAY:-}" ]]; then
#   echo "Rotating display: ${ROTATE_DISPLAY}"
#   (sleep 3 && xrandr -display "${DISPLAY}" -o "${ROTATE_DISPLAY}") &
# fi

# Set or parse screen resolution
# if [[ -n "${SCREEN_WIDTH:-}" && -n "${SCREEN_HEIGHT:-}" && -n "${FRAMES_PER_SECOND:-}" ]]; then
#   echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT} @${FRAMES_PER_SECOND}"
#   xrandr -display "${DISPLAY}" -s "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" -r "${FRAMES_PER_SECOND}" || true
# elif [[ -n "${SCREEN_WIDTH:-}" && -n "${SCREEN_HEIGHT:-}" ]]; then
#   echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
#   xrandr -display "${DISPLAY}" -s "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" || true
# else
#   CURR=$(xrandr -display "${DISPLAY}" -q | awk -F'current' -F',' 'NR==1 {gsub("( |current)","");print $2}')
#   export SCREEN_WIDTH="${CURR%x*}"
#   export SCREEN_HEIGHT="${CURR#*x}"
#   echo "Screen resolution parsed as: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
# fi

# If DISPLAY, SCREEN_WIDTH or SCREEN_HEIGHT still isn't set, restart the mediaplayer container
# if [[ -z "${DISPLAY}" || -z "${SCREEN_WIDTH}" || -z "${SCREEN_HEIGHT}" ]]; then
#   echo "ERROR: DISPLAY/SCREEN_WIDTH/SCREEN_HEIGHT not set; restarting service."
#   for i in {1..3}; do
#     echo "Attempt ${i} to restart mediaplayer in 30 seconds..."
#     sleep 30
#     curl -s -H "Content-Type: application/json" \
#       -d "{\"serviceName\":\"$BALENA_SERVICE_NAME\"}" \
#       "$BALENA_SUPERVISOR_ADDRESS/v2/applications/$BALENA_APP_ID/restart-service?apikey=$BALENA_SUPERVISOR_API_KEY" >/dev/null || true
#   done
#   exit 1
# fi

# Unmute system audio
# ./scripts/unmute.sh

exec python3 media_player.py
