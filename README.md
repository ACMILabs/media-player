Media player
============

A media player using Python to launch VLC.

#### Features:
* Plays the downloaded playlist fullscreen in an endless loop through the first HDMI output
* Supports content playable by VLC on the given hardware
* Outputs audio through the first audio device with a name that matches the AUDIO_DEVICE_REGEX environment variable
* Displays captions using VLC
* Shows a black background if no videos are found
* Downloads a playlist of videos (with optional subtitles) from XOS and saves these locally so that playback can take place after reboot without an internet connection
* Posts playback & volume information to a broker (see [Message Broker](#message-broker))
* Synchronises playback with additional media players if configured (See Synchronised playback)
* Communicates over Ethernet (Wifi configuration and control is not yet tested)

### Hardware
The media player is designed to run on the following hardware:

#### Raspberry Pi 4
ACMI uses Rapberry Pis for most standard players in its exhibitions. This will output 1080p video to most screens, and in future should be able to play 4k video.

##### Sample kit list:
* Raspberry Pi 4, Model B, 2GB
* Official USB C Power supply
* Mini-HDMI to HDMI cable
* Sandisk 16GB SD Card
* Network cable
* Screen for display (we like Panasonic professional screens)
* For audio, we use an Audinate Dante USB dongle
* For temperature monitoring, we use a DFRobot DHT22 Sensor

#### Small-form-factor PC
We use small-form-factor PCs such as Dell Optiplex Micro or Intel NUC in places where we need 4k video or synced video.

##### Sample kit list:
* Dell Optiplex 3070 Micro i3, minimum RAM and storage
* Screen for display
* Network cable
* For audio, we use an Audinate Dante USB dongle

#### Configuration
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
SUBTITLES # Set to true will display subtitles
SUBTITLES_FONT_SIZE # Set a subtitle size value of 0-4096
SUBTITLES_FONT_WEIGHT # Set the font weight to regular or bold
DEBUG # Set to true to see more output on the console

```

#### Endpoints
The media player makes a get request to a playlist endpoint and expects a response with the following shape:
```bash
{
    "id": 1,
    "playlist_labels": [
        {
            "label": {
                "id": 44,
            },
            "resource": "MP4_VIDEO_FILE_URL",
            "subtitles": "SRT_SUBTITLE_FILE_URL",
        },
    ],
}

```


#### Monitoring:
Includes a Prometheus client which exports scrapable data at the following ports: 
* playback & volume information at port `1007`

#### Error reporting:
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

## Installation on developer machine

* Clone this repository.

* `$ cd development`
* Build the development container `$ docker-compose up`
* `cp dev.tmpl.env dev.env`
* Edit the `dev.env` with any required values (a default playlist will be used otherwise)
* Run `cd development && docker-compose up`

## Testing and linting

`$ docker exec -it mediaplayer make linttest`


## Installation on Windows

(These instructions are provided for Legacy purposes - we've switched to Balena-only deployment)

* Install [Git for Windows](https://git-scm.com/download/win).
* In an admin PowerShell:
  * Install [Chocolatey](https://chocolatey.org) package manager.
  * Install VLC `choco install vlc`
  * Install Python3 `choco install python`
* In Git Bash shell:
  * Clone this repository.
  * `pip install -r requirements.txt`
  * `mv config.tmpl.env config.env`
  * Create a Playlist in XOS with resources.
  * Edit the `config.env` to point to the ID of your Playlist in Django.
  * Run `source config.env` to load environment variables.
  * Turn on the http server: VLC > Preferences > http web interface > tick the box & set the password you saved to `config.env`.
  * Run `python media_player.py`

### To make this autorun at startup:

* Create a batch file called `media-player.bat` which is a text file that includes:

```batch
C:
cd /Users/<username>/media-player-nuc
start "" "%SYSTEMDRIVE%\Program Files\Git\bin\sh.exe" --login -i -c "source config.env && python media_player.py"
```

* Right click on the batch file and create a shortcut.
* Press the Windows button and type Run.
* In the Run dialog type: `shell:startup`
* Cut and paste the shortcut into this folder.

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
