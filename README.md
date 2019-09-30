Media player
============

A media player using Python to launch VLC.

Features:
* Downloads a playlist of videos (with optional subtitles) from XOS
* Posts playback & volume information to a broker

Monitoring:
* Includes a Prometheus client exporting playback & volume information

Error reporting:
* Posts exceptions and errors to Sentry

## Deploying via Balena for both x86 and ARM

### x86

$ balena deploy appName --build --buildArg 'IS_X86=true'

### ARM

$ balena deploy appName

### Multiple balena remotes

Alternatively you can add multiple `balena` remotes to push to, so to add both the intel and arm applications the commands to run would be:

```bash
$ git remote set-url balena --push --add g_acmi_developer@git.balena-cloud.com:g_acmi_developer/s__media-player-pi-4.git

$ git remote set-url balena --push --add g_acmi_developer@git.balena-cloud.com:g_acmi_developer/e__media-player-x86.git
```

## Testing and linting

1. Build the development container `$ docker-compose up --build`
2. Run testing & linting: `$ docker exec -it mediaplayer make linttest`

## Installation on macOS

* Clone this repository.
* Install VLC `brew cask install vlc`
* `pip install -r requirements.txt`
* `mv config.tmpl.env config.env`
* Create a Playlist in XOS with resources.
* Edit the `config.env` to point to the ID of your Playlist in Django.
* Run `source config.env` to load environment variables.
* Turn on the http server: VLC > Preferences > http web interface > tick the box & set the password you saved to `config.env`.
* Run `python media_player.py`

## Installation on Windows

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

## Setup RabbitMQ user

There's a demo RabbitMQ server setup on our Ubuntu Server. It's setup to start the `rabbitmq-server` service at boot. I used this command to do that: `sudo update-rc.d rabbitmq-server defaults`, but to manually start/stop the server use: `sudo service rabbitmq-server stop/start/restart`

To setup a user:

* Create a new user `sudo rabbitmqctl add_user username password`
* Give it the permissions needed `sudo rabbitmqctl set_permissions username ".*" ".*" ".*"` - where ".*" is all permissions for configuration/write/read.
* List the user permissions `sudo rabbitmqctl list_user_permissions username`

The address of the AMQP service is then: `amqp://username:password@172.16.80.105:5672//`

## Sample AMQP consumer

There's a sample consumer to see the output from the `mewdia_player.py` vlc http server, run it with: `python consumer.py`.

You'll need to have the config variables loaded: `source config.env`
