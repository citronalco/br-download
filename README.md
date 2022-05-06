# BR Downloader

Download your favourite radio shows from Bayerischer Rundfunk!

This is a Python 3 command line script to download shows from any channel from Bayerischer Rundfunk's "Live" web site.
The shows are saved in MP3 format and get tagged with all available information, including chapter markers, logos etc.

### Requirements
Python 3 with modules "pydub", "mutagen" and "requests".
(On Debian/Ubuntu: `sudo apt install python3 python3-mutagen python3-requests pydub`)

### Usage
```./br-download.py <Channel> <Show> <TargetDirectory>```

* `TargetDirectory` is the directory you want the MP3 files get saved in
* `Show` is the show's title as displayed in BR's "Live" player (https://www.br.de/radio/live/)
* `Channel` can be something like "bayern 2", "br-klassik", "br24", "puls". If an invalid Channel is given, all valid channel names get displayed.

`Show` and `Channel` are case insensitive. \
Episodes aready downloaded get skipped, so this script is well suited for cron jobs.

**Example:**
```./br-download.py "bayern 2" "IQ - Wissenschaft und forschung" "/data/recordings```

This would download all available "IQ - Wissenschaft und Forschung" episodes from Bayern 2 and save them with full ID3 tags in the "/data/recordings" directory.

### Limitations
* Shows aired very recently can't get downloaded. \
While all shows look the same on Bayerischer Rundfunk's website, the most recent shows usually have wrong cut marks, which means they start several minutes too early or too late and the chapter markers are wrong.
Some minutes/hours after the show's end Bayerischer Rundfunk fixes all this and moves the show internally from "live stream" to the "relive".
This script downloads shows only from "relive".

### See also
If you want to listen to the downloaded shows with your podcast player: https://github.com/citronalco/mp3-to-rss2feed creates a RSS2 feed from MP3 files.

