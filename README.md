Media player
============

A media player prototype using Python to launch VLC.

## Installation on macOS

* Clone this repository.
* Install VLC `brew cask install vlc`
* `pip install -r requirements.txt`
* `mv config.tmpl.env config.env`
* Create a Playlist in XOS with resources.
* Edit the `config.env` to point to the ID of your Playlist in Django.
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
