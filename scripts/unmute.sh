#!/bin/bash

# Unmute system audio on Intel devices
amixer -c 0 set Master playback 100% unmute

# Unmute system audio on Raspberry Pis
amixer set PCM unmute
