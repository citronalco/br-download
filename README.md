# BR Downloader
Download your favourite radio shows from Bayerischer Rundfunk!

## Description
This is a Python 3 command line script to download shows from any channel from Bayerischer Rundfunk's "Live" web site.
The shows are saved in MP3 format and get tagged with all available information, including chapter markers, logos etc.

## Requirements
Python 3 with modules "av", "mutagen" and "requests".
(On Debian/Ubuntu: `sudo apt install python3 python3-mutagen python3-requests python3-av`)

## Usage
```
usage: br-download.py [-h] [-n] Channel ShowTitle [TargetDirectory]

Find all availabe recordings of a show in Bayerischer Rundfunk's player, download them as MP3 files and save the shows' metadata in the ID3 tags.

positional arguments:
  Channel          The channel's name (e.g. "bayern 2", "BR-Klassik", "Puls")
  ShowTitle        The show's title as shown on https://www.br.de/radio/live/ (e.g. "Bayern 2 Zündfunk")
  TargetDirectory  Directory to save the files in (default: current directory)

options:
  -h, --help       show this help message and exit
  -n, --newest     Download newest broadcast only (default: False)
```

`ShowTitle` may contain Regular Expressions.

### Examples
##### Download newest "Zündfunk" episode from Bayern 2:
"Zündfunk" is called "Bayern 2 Zündfunk" on https://www.br.de/radio/live/bayern2/programm/:

```./br-download.py -n "bayern 2" "bayern 2 zündfunk" "/data/recordings"```

This would download the newest episode of "Bayern 2 Zündfunk" from Bayern 2 and save it with full ID3 tags in the "/data/recordings" directory.

##### Download all available episodes of "Startrampe" from Puls:
"Startrampe" is named differently from episode to episode, e.g. "Startrampe: Alternative", "Startrampe: Neue Deutsche Welle", "Startrampe: HipHop". All names begin with "Startrampe", so use "Startrampe.*" as ShowTitle to get all episodes.

```./br-download.py "puls" "startrampe.*" "/data/recordings"```


## ID3 Tags
This script not only downloads the recordings, but also automatically extracts all metadata provided by Bayerischer Rundfunk and saves it in appropriate ID3v2.3 tags of the downloaded MP3 files.
The tracklist gets translated into ID3 chapters.

Unfortunately, most generic media players only support basic ID3 tags. Your chances are much higher with Podcast players.
Here's a simple MP3 player with proper support for chapters: https://mp3chapters.github.io/player/

## Limitations
* Shows aired very recently can't get downloaded. \
While all shows look the same on Bayerischer Rundfunk's website, the most recent shows usually have wrong cut marks, which means they start several minutes too early or too late and the chapter markers are wrong.
Some minutes/hours after the show's end Bayerischer Rundfunk fixes all this and moves the show internally from "live stream" to the "relive".
This script downloads shows only from "relive".

### See also
If you want to listen to the downloaded shows with your podcast player: https://github.com/citronalco/mp3-to-rss2feed creates a RSS2 feed from MP3 files.
