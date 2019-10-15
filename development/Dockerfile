FROM python:3.7.2

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
        vlc vlc-plugin-* g++ \
        xserver-xorg \
        xserver-xorg-input-evdev \
        xinit \
        xfce4 \
        xfce4-terminal \
        x11-xserver-utils \
        dbus-x11 \
        matchbox-keyboard \
        xterm \
        # For system volume
        libasound2-dev \
        # Audio
        alsa-utils

# Intel GPU drivers for VLC
ARG IS_X86
RUN if [ "$IS_X86" = "true" ]; \
  then install_packages i965-va-driver vainfo; \
  fi

# Disable screen from turning it off
RUN echo "#!/bin/bash" > /etc/X11/xinit/xserverrc \
  && echo "" >> /etc/X11/xinit/xserverrc \
  && echo 'exec /usr/bin/X -s 0 dpms' >> /etc/X11/xinit/xserverrc

# Avoid requesting XFCE4 question on X start
ENV XFCE_PANEL_MIGRATE_DEFAULT=1

ENV PYTHONUNBUFFERED 1

# Enable udevd so that plugged dynamic hardware devices show up in our container.
ENV UDEV 1

# Set dbus environment variables
ENV DISPLAY :0
ENV DBUS_SYSTEM_BUS_ADDRESS unix:path=/host/run/dbus/system_bus_socket

COPY ./requirements/base.txt /code/requirements/base.txt
COPY ./requirements/test.txt /code/requirements/test.txt
RUN pip install -Ur /code/requirements/test.txt

RUN mkdir /data
COPY ./resources/*.mp4 /data/
COPY ./resources/*.srt /data/

COPY . /code/
WORKDIR /code/

# main.py will run when container starts up on the device
CMD ["bash"]
# CMD ["bash","scripts/pi.sh"]
