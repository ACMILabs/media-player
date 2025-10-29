#!/bin/bash
set -euo pipefail

sed -i 's/geteuid/getppid/' /usr/bin/vlc || true
rm -f /tmp/.X0-lock

export DISPLAY=":0"
export XAUTHLOCALHOSTNAME="localhost"
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket
export XDG_RUNTIME_DIR="/run/user/0"
mkdir -p "${XDG_RUNTIME_DIR}"; chmod 700 "${XDG_RUNTIME_DIR}"
touch /root/.Xauthority

# optional (Qt apps)
export QT_QPA_PLATFORM=xcb

if [ ! -e /dev/dri/card0 ]; then
  echo "ERROR: /dev/dri/card0 not found. Ensure privileged service and /dev/dri mapped."
  sleep 3; exit 1
fi

echo "STARTING X"

# persistent client (Openbox or fallback)
if ! command -v openbox >/dev/null 2>&1; then
  echo "Openbox not found; using xsetroot as persistent X client"
  CLIENT="/usr/bin/xsetroot -solid black"
else
  CLIENT="/usr/bin/openbox"
fi

(xinit $CLIENT -- "${DISPLAY}" -keeptty -nolisten tcp -nocursor vt1 ) &
# cleanup background helpers on exit
cleanup() { pkill -f "unclutter -display ${DISPLAY}" || true; }
trap cleanup EXIT

# wait for X
for i in $(seq 1 20); do
  echo "Waiting for X to start..."
  xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1 && break
  sleep 0.5
done
if ! xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
  echo "X did not start, last 10 lines of /var/log/Xorg.0.log (if present):"
  tail -n 10 /var/log/Xorg.0.log || true
  # exit 1
fi

echo "Displays in use after starting X"
echo "DISPLAY=${DISPLAY}"

# no blanking / no DPMS; hide cursor
xset -display "${DISPLAY}" s off -dpms s noblank
unclutter -display "${DISPLAY}" -idle 0.1 &

# rotate if requested
if [[ -n "${ROTATE_DISPLAY:-}" ]]; then
  echo "Rotating display: ${ROTATE_DISPLAY}"
  (sleep 2 && xrandr -display "${DISPLAY}" -o "${ROTATE_DISPLAY}") &
fi

# set or detect resolution
if [[ -n "${SCREEN_WIDTH:-}" && -n "${SCREEN_HEIGHT:-}" && -n "${FRAMES_PER_SECOND:-}" ]]; then
  echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT} @${FRAMES_PER_SECOND}"
  xrandr -display "${DISPLAY}" -s "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" -r "${FRAMES_PER_SECOND}" || true
elif [[ -n "${SCREEN_WIDTH:-}" && -n "${SCREEN_HEIGHT:-}" ]]; then
  echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
  xrandr -display "${DISPLAY}" -s "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" || true
else
  CURR=$(xrandr -display "${DISPLAY}" -q | awk -F'current' -F',' 'NR==1 {gsub("( |current)","");print $2}')
  export SCREEN_WIDTH="${CURR%x*}"
  export SCREEN_HEIGHT="${CURR#*x}"
  echo "Screen resolution parsed as: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
fi

if [[ -z "${DISPLAY}" || -z "${SCREEN_WIDTH}" || -z "${SCREEN_HEIGHT}" ]]; then
  echo "ERROR: DISPLAY/SCREEN_WIDTH/SCREEN_HEIGHT not set; restarting service."
  for i in {1..3}; do
    echo "Attempt ${i} to restart mediaplayer in 30 seconds..."
    sleep 30
    curl -s -H "Content-Type: application/json" \
      -d "{\"serviceName\":\"$BALENA_SERVICE_NAME\"}" \
      "$BALENA_SUPERVISOR_ADDRESS/v2/applications/$BALENA_APP_ID/restart-service?apikey=$BALENA_SUPERVISOR_API_KEY" >/dev/null || true
  done
  exit 1
fi

exec python3 media_player.py
