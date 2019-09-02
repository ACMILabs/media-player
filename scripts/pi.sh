#!/bin/bash

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# export DISPLAY=:0.0
export DISPLAY=:0
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/host/run/dbus/system_bus_socket

# start desktop manager
echo "STARTING X"
startx &

# uncomment to start x without mouse cursor
# startx -- -nocursor &

# uncomment to open an application instead of the desktop
# startx xterm 

# Unmute system audio
amixer -c 0 set Master playback 100% unmute

python media_player.py
