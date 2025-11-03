#!/bin/bash

# Load environment variables
source ./config.env

# Start the media player
source ./venv/bin/activate && python media_player.py &
