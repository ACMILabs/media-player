#!/bin/bash

export ARCHITECTURE=`uname -m`

if [[ $ARCHITECTURE == "x86_64" ]]; then
  # Blank background on Intel devices
  xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/workspace0/last-image --set /code/resources/blank-1920x1080.png
else
  # Blank background on Raspberry Pis
  pcmanfm --set-wallpaper /code/resources/blank-1920x1080.png
fi
