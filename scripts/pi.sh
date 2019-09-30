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

# uncomment to start x without mouse cursor
# startx -- -nocursor &

# uncomment to open an application instead of the desktop
# startx xterm 

# Hide the cursor
unclutter -display :0 -idle 0.1 &

# Set background image
export DISPLAY=:0
pcmanfm --set-wallpaper /code/resources/acmi-1920x1080.png

# Set X background image
# xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/workspace0/last-image --set /code/resources/acmi-1920x1080.png

# Hide X icons
# xfconf-query -c xfce4-desktop -np '/desktop-icons/style' -t 'int' -s '0'

# Hide X panel
# xfce4-panel -q

# Unmute system audio
# ./scripts/unmute.sh

python3 media_player.py
