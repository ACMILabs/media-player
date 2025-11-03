#!/usr/bin/env bash
set -Eeuo pipefail

# Load env file:
set -a
source /home/pi/Code/media-player/config.env
set +a

cd /home/pi/Code/media-player
exec /home/pi/Code/media-player/venv/bin/python /home/pi/Code/media-player/media_player.py
