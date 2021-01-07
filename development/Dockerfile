# Built from Dockerfile.development
# To rebuild:
# docker build --file development/Dockerfile.development -t acmilabs/mediaplayer-development:v1 .
# docker push acmilabs/mediaplayer-development:v1
FROM acmilabs/mediaplayer-development:v1

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
RUN mkdir /data/resources
COPY ./resources/*.mp4 /data/resources/
COPY ./resources/*.srt /data/resources/

COPY . /code/
WORKDIR /code/

# main.py will run when container starts up on the device
CMD ["bash"]
#CMD ["bash","scripts/pi.sh"]
