#!/bin/bash

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# Remove the X server lock file so ours starts cleanly
rm /tmp/.X0-lock &>/dev/null || true

# Set the display to use
export DISPLAY=:0

# Set the DBUS address for sending around system messages
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

# start desktop manager
echo "STARTING X"
startx &

# TODO: work out how to detect X has started
sleep 5

# Hide the cursor
unclutter -display :0 -idle 0.1 &

# Unmute system audio
# ./scripts/unmute.sh


python3 media_player.py
