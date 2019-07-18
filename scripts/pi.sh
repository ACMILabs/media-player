#!/bin/bash

# Allow VLC to run under root
sed -i 's/geteuid/getppid/' /usr/bin/vlc

# Start X
rm /tmp/.X0-lock &>/dev/null || true
echo "Starting X in 2 seconds"
sleep 2
startx &
sleep 2

# Hide the cursor
unclutter -display :0 -idle 0.1 &

python media_player.py
