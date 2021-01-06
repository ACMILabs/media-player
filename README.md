Media player
============

A media player using Python to launch and control VLC on low-cost hardware.

## Features:
* Runs on Raspberry Pi 4 and Intel small-form-factor PCs.
* Downloads a playlist of videos (with optional subtitles) from XOS and saves these locally so that playback can take place after reboot without an internet connection
* Plays the downloaded playlist fullscreen in an endless loop through the first HDMI output
* Supports content and captions playable by VLC on the given hardware
* Posts playback & volume information to a broker (see [Message Broker](#message-broker)) to allow integration with synchronised systems
* Synchronises playback with additional media players if configured (See Synchronised playback)
* Communicates over Ethernet (Wifi configuration and control is not yet tested)
* Deployable and configurable at scale via Docker and Balena
* Communicates with Nodel and Prometheus for status/availability/resource monitoring.
* Outputs audio through the first audio device with a name that matches the AUDIO_DEVICE_REGEX environment variable
* Shows a black background if no videos are found

### Target video specs
* H264 now - but we hope to enable H265 in future
* 1080p or less in most instances, but 4k in exceptional instances
* 25-30fps almost entirely but up to 60fps in exceptional instances
* mp4 container
* Downloaded and cached, rather than streamed over the network

## Hardware
The media player is designed to run on the following hardware:

### Raspberry Pi 4
ACMI uses Rapberry Pis for most standard players in its exhibitions. This will output 1080p video to most screens, and in future should be able to play 4k video.

#### Sample kit list:
* Raspberry Pi 4, Model B, 2GB
* Official USB C Power supply
* Mini-HDMI to HDMI cable
* Sandisk 16GB SD Card
* Network cable
* Screen for display (we like Panasonic professional screens)
* For audio, we use an Audinate Dante USB dongle
* For temperature monitoring, we use a DFRobot DHT22 Sensor

### Small-form-factor PC
We use small-form-factor PCs such as Dell Optiplex Micro or Intel NUC in places where we need 4k video or synced video.

#### Sample kit list:
* Dell Optiplex 3070 Micro i3, minimum RAM and storage
* Screen for display
* Network cable
* For audio, we use an Audinate Dante USB dongle

## Installation on developer machine

* Clone this repository.

* `$ cd development`
* Build the development container `$ docker-compose up`
* `cp dev.tmpl.env dev.env`
* Edit the `dev.env` with any required values (a default playlist will be used otherwise)
* Run `cd development && docker-compose up`

## Testing and linting

`$ docker exec -it mediaplayer make linttest`

## Configuration
The media player expects the following configuration variables:

```
AMQP_URL
DOWNLOAD_RETRIES
SENTRY_ID
TIME_BETWEEN_PLAYBACK_STATUS
XOS_API_ENDPOINT
XOS_MEDIA_PLAYER_ID
XOS_PLAYLIST_ID
AUDIO_DEVICE_REGEX
SYNC_CLIENT_TO
SYNC_IS_SERVER
```

Optional variables:

```.env
SYNC_DRIFT_THRESHOLD # Defaults to 40. (milliseconds)
SYNC_LATENCY # Defaults to 30. (milliseconds)
SUBTITLES # Set to true will display subtitles
SUBTITLES_FONT_SIZE # Set a subtitle size value of 0-4096
SUBTITLES_FONT_WEIGHT # Set the font weight to regular or bold
DEBUG # Set to true to see more output on the console
SCREEN_WIDTH # Set the screen width
SCREEN_HEIGHT # Set the screen height
FRAMES_PER_SECOND # Set the screen refresh rate
```

### Endpoints
The media player makes a get request to a playlist endpoint and expects a response with the following shape:
```bash
{
    "id": 1,
    "playlist_labels": [
        {
            "label": {
                "id": 44
            },
            "video": {
                "id": 12,
                "resource": "MP4_VIDEO_FILE_URL"
            },
            "resource": "MP4_VIDEO_FILE_URL",
            "subtitles": "SRT_SUBTITLE_FILE_URL"
        }
    ]
}

```

### Monitoring:
Includes a Prometheus client which exports scrapable data at the following ports: 
* playback & volume information at port `1007`

### Error reporting:
* Posts exceptions and errors to Sentry


## Troubleshooting

When booting up for the first time:

* If you see the Balena loading image (a rounded cube), and don't see your device in Balena Cloud or XOS, then the media player probably doesn't have any internet access. Check the ethernet connection, and reboot the device.
* If you see the ACMI logo on a black background, then the device has access to the internet and is trying to download video files from XOS. Check the Balena Cloud logs to verify that it's downloading the files you expect, large files take a little while to download. Also verify that you can reach the [XOS playlist API](https://xos.acmi.net.au/api/playlists/1/).
* If a default video starts playing with the title ACMI Media Player, then your device is running correctly and can access both XOS & Balena. You can now configure your device to load the content you'd like.

## Deploying via Balena for both x86 and ARM

### x86

$ balena deploy appName --build --buildArg 'IS_X86=true'

### ARM

$ balena deploy appName

### Multiple balena remotes

Alternatively you can add multiple `balena` remotes to push to, so to add both the intel and arm applications the commands to run would be:

```bash
$ git remote set-url balena --push --add <username>@git.balena-cloud.com:<username>/<pi balena app name>.git

$ git remote set-url balena --push --add <username>@git.balena-cloud.com:<username>/<x86 balena app name>.git
```

## Message Broker

The media player sends playback information to a RabbitMQ server. This playback information is then consumed by a Playlist Label using an AMQP consumer.

The message broker post has this shape:
```bash
{
  "datetime": "2020-04-23T10:12:30.537576+10:00",
  "playlist_id": 9,
  "media_player_id": 80,
  "label_id": 40,
  "playlist_position": 3,
  "playback_position": 0.5821805000305176,
  "dropped_audio_frames": 0,
  "dropped_video_frames": 0,
  "duration": 100229,
  "player_volume": "3.90625",
  "system_volume": "9.6"
}
```

### Setting up a RabbitMQ server and user

A RabbitMQ server can be run on a Ubuntu Server and setup to start the `rabbitmq-server` service at boot with this command: `sudo update-rc.d rabbitmq-server defaults`, but to manually start/stop the server use: `sudo service rabbitmq-server stop/start/restart`

To setup a user:

* Create a new user `sudo rabbitmqctl add_user username password`
* Give it the permissions needed `sudo rabbitmqctl set_permissions username ".*" ".*" ".*"` - where ".*" is all permissions for configuration/write/read.
* List the user permissions `sudo rabbitmqctl list_user_permissions username`

The address of the AMQP service is then: `amqp://username:password@172.16.80.105:5672//`

## Synchronised Playback

Several media players may be configured to play video files of the exact same length in synchronised time with each other. This is done be setting one media player to be the 'synchronisation server', by setting the config variable `SYNC_IS_SERVER` to True. The remaining media players should be set to track the server by setting the config variable `SYNC_CLIENT_TO` to the IP address of the synchronisation server.

To tune the synchronisation settings, try these optional variables:

* `SYNC_DRIFT_THRESHOLD` - the number of milliseconds playback difference between the server and client before attempting to re-sync the playback
* `SYNC_LATENCY` - the number of milliseconds your hardware device takes to seek the new playback position
