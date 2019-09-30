#!/bin/bash

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

rm /tmp/.X0-lock &>/dev/null || true

export DISPLAY=:0
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
