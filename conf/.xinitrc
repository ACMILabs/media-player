# Hide the cursor
unclutter -display :0 -idle 0.1 &

# Set X background image
xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/workspace0/last-image --set /code/resources/acmi-1920x1080.png

# Hide X icons
xfconf-query -c xfce4-desktop -np '/desktop-icons/style' -t 'int' -s '0'

# Hide X panel
xfce4-panel -q

# Unmute system audio
# amixer -c 0 set Master playback 100% unmute

python media_player.py
