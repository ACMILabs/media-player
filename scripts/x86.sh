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
echo "Starting X"
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

# If DISPLAYS doesn't include 0.0 set the new display
if [[ $DISPLAYS == *":0.0"* ]]; then
  echo "Display includes 0.0 so let's launch..."
else
  LAST_DISPLAY=`ps -u $(id -u) -o pid= | \
    while read pid; do
      cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep '^DISPLAY=:'
    done | sort -u | tail -n1`
  echo "0.0 is missing, so setting display to: ${LAST_DISPLAY}"
  export $LAST_DISPLAY
fi

# Prevent blanking and screensaver
xset s off -dpms

# Hide the cursor
unclutter -idle 0.1 &

# Set X background image
xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/workspace0/last-image --set /code/resources/blank-1920x1080.png

# Hide X icons
xfconf-query -c xfce4-desktop -np '/desktop-icons/style' -t 'int' -s '0'

# Hide X panel
xfce4-panel -q

# rotate screen if env variable is set [normal, inverted, left or right]
if [[ ! -z "$ROTATE_DISPLAY" ]]; then
  echo "Rotating display ${ROTATE_DISPLAY}"
  (sleep 3 && xrandr -o $ROTATE_DISPLAY) &
fi

# Set display size and frames-per-second refresh rate
# Note: SCREEN_WIDTH and SCREEN_HEIGHT also tell VLC to play the video at that size too
if [[ ! -z "$SCREEN_WIDTH" ]] && [[ ! -z "$SCREEN_HEIGHT" ]] && [[ ! -z "$FRAMES_PER_SECOND" ]]; then
  echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT} @${FRAMES_PER_SECOND}"
  xrandr -s "$SCREEN_WIDTH"x"$SCREEN_HEIGHT" -r $FRAMES_PER_SECOND
elif [[ ! -z "$SCREEN_WIDTH" ]] && [[ ! -z "$SCREEN_HEIGHT" ]]; then
  echo "Setting screen to: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
  xrandr -s "$SCREEN_WIDTH"x"$SCREEN_HEIGHT"
fi

# Unmute system audio
# ./scripts/unmute.sh

python media_player.py
