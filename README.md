Media player
============

A media player using Python to launch VLC.

####Features:
* Shows a black background if no videos are found
* Downloads a playlist of videos (with optional subtitles) from XOS and saves these locally so that playback can take place after reboot without an internet connection
* Posts playback & volume information to a broker (see [Message Broker](#message-broker))
* Synchronises playback with additional media players if configured (See Synchronised playback)

####Configuration
The media player expects the following configuration variables:

```
AMQP_URL
DOWNLOAD_RETRIES
SENTRY_ID
TIME_BETWEEN_PLAYBACK_STATUS
TIME_BETWEEN_READINGS
USE_PLS_PLAYLIST
VLC_PASSWORD
VLC_URL
XOS_API_ENDPOINT
XOS_MEDIA_PLAYER_ID
XOS_PLAYLIST_ID
AUDIO_DEVICE_REGEX
SYNC_CLIENT_T0
SYNC_IS_SERVER
```


####Endpoints
The media player makes a get request to a playlist endpoint and expects a response with the following shape:
```.env
{
    "id": 1,
    "title": "Default playlist",
    "playlist_labels": [
        {
            "label": {
                "id": 44,
                "works": [
                    60889
                ],
                "work": {
                    "id": 60889,
                },
            },
            "resource": "MP4_VIDEO_FILE_URL",
            "subtitles": "SRT_SUBTITLE_FILE_URL",
        },
    ],
}

```


####Monitoring:
Includes a Prometheus client which exports scrapable data at the following ports: 
* playback & volume information at port `1007`
* Balena node exporter at port `1005`

####Error reporting:
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

##Message Broker

The media player sends playback information to a RabbitMQ server. This playback information is then consumed by a Playlist Label using an AMQP consumer.

###Setting up a RabbitMQ server and user

A RabbitMQ server can be run on a Ubuntu Server and setup to start the `rabbitmq-server` service at boot with this command: `sudo update-rc.d rabbitmq-server defaults`, but to manually start/stop the server use: `sudo service rabbitmq-server stop/start/restart`

To setup a user:

* Create a new user `sudo rabbitmqctl add_user username password`
* Give it the permissions needed `sudo rabbitmqctl set_permissions username ".*" ".*" ".*"` - where ".*" is all permissions for configuration/write/read.
* List the user permissions `sudo rabbitmqctl list_user_permissions username`

The address of the AMQP service is then: `amqp://username:password@172.16.80.105:5672//`

##Synchronised Playback
Several media players may be configured to play video files of the exact same length in synchronised time with each other. This is done be setting one media player to be the 'synchronisation server', by setting the config variable `SYNC_IS_SERVER` to True. The remaining media players should be set to track the server by setting the config variable `SYNC_CLIENT_TO` to the IP address of the synchronisation server. 