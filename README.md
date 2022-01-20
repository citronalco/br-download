# BR Downloader

Download your favourite radio shows from Bayerischer Rundfunk!

This is a Python 3 command line script to download shows from any channel from Bayerischer Rundfunk's "Live" web site.
The shows are saved in MP3 format and get tagged with all available information, including chapter markers.

### Requirements
Python 3 with modules "pydub", "mutagen", "beautifulsoup4" and "requests".
(On Debian/Ubuntu: `sudo apt install python3 python3-mutagen python3-requests python3-bs4 pydub`)

### Usage
```./br-download.py <Channel> <Show> <TargetDirectory>```

* `TargetDirectory` is the directory you want the MP3 files get saved in
* `Show` is the show's title as displayed in BR's "Live" (player https://www.br.de/radio/live/)
* `Channel` can be something like "bayern2", "br-klassik", "br24", "puls", as seen in the URL of the "Live" player.

`Show` and `Channel` are case insensitive. \
Episodes aready downloaded get skipped, so this script is well suited for cron jobs.

**Example:**
```./br-download.py bayern2 "IQ - Wissenschaft und forschung" "/data/aufnahmen```

This would download all available "IQ - Wissenschaft und Forschung" episodes from Bayern 2 and save them with full ID3 tags in the "/data/aufnahmen" directory.

### Limitations
* As of January 2021 Bayerischer Rundfunk only offers the last 5 hours of its program as recordings, not the last 7 days
* Timestamps are way off. This means shows start earlier or later than expected and chapter markers are wrong. As it's the same on Bayerischer Rundfunk's "Live" web page it's most likely their fault.

### See also
If you want to listen to the downloaded shows with your podcast player: https://github.com/citronalco/mp3-to-rss2feed creates a RSS2 feed from MP3 files.

