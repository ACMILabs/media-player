#!/bin/bash

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# Remove the X server lock file so ours starts cleanly
rm /tmp/.X0-lock &>/dev/null || true

# Set the display to use
export DISPLAY=:0

# Set the DBUS address for sending around system messages
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

# Set XDG_RUNTIME_DIR
mkdir -pv ~/.cache/xdgr
export XDG_RUNTIME_DIR=$PATH:~/.cache/xdgr

# Create Xauthority
touch /root/.Xauthority

# Start desktop manager
echo "STARTING X"
startx -- -nocursor &

# TODO: work out how to detect X has started
sleep 5

# Print all of the current displays used by running processes
echo "Displays in use after starting X"
DISPLAYS=`ps -u $(id -u) -o pid= | \
  while read pid; do
    cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep '^DISPLAY=:'
  done | sort -u`
echo $DISPLAYS

# Always set display to last display
LAST_DISPLAY=`ps -u $(id -u) -o pid= | \
  while read pid; do
    cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep '^DISPLAY=:'
  done | sort -u | tail -n1`
echo "Setting display to: ${LAST_DISPLAY}"
export $LAST_DISPLAY

# Prevent blanking and screensaver
xset s off -dpms

# Hide the cursor
unclutter -idle 0.1 &

# rotate screen if env variable is set [normal, inverted, left or right]
if [[ ! -z "$ROTATE_DISPLAY" ]]; then
  echo "Rotating display: ${ROTATE_DISPLAY}"
  (sleep 3 && xrandr -o $ROTATE_DISPLAY) &
fi

# Parse screen resolution for smaller screens
export SCREEN_WIDTH=`xrandr -q | awk -F'current' -F',' 'NR==1 {gsub("( |current)","");print $2}' | cut -d 'x' -f1`
export SCREEN_HEIGHT=`xrandr -q | awk -F'current' -F',' 'NR==1 {gsub("( |current)","");print $2}' | cut -d 'x' -f2`
echo "Display resolution: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"

# Unmute system audio
# ./scripts/unmute.sh

python3 media_player.py
