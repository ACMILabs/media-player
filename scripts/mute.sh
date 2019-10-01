#!/bin/bash

# Mute system audio on Intel devices
amixer -c 0 set Master playback 100% mute

# Mute system audio on Raspberry Pis
amixer set PCM mute
