# Zündfunk Download / Nachtmix Download

Bayerischer Rundfunk airs a pretty decent radio show called "Zündunk", featuring new music, politics and culture.
For people who missed a show, Bayerischer Rundfunk provides recordings on its web page.

But only for less than one week. And only within a player, without a convenient download button.
That's why I wrote this Python 3 script.

This Python 3 script is a simple command line tool to downloads all currently available Zündfunk episodes from Bayerischer Rundfunk's web page as MP3 files.

The script "download-nachtmix.py" works the same way as "download-zuendfunk.py"

### Requirements
Python 3 with modules "mutagen", "beautifulsoup4" and "requests".
(On Debian/Ubuntu: `sudo apt install python3 python3-mutagen python3-requests python3-bs4`)

### Usage
```./zuendfunk-download.py <TargetDirectory>```

The script searches Bayerischer Rundfunk's web site and downloads all currently available "Zündfunk" episodes into the given target directory.
Episodes aready downloaded get skipped, so it is well suited for cron jobs.

The episode's metadata gets stored in the downloaded MP3 file's ID3 tag.
If a playlist is available for the episode it gets written in ID3 tag's "Comment" field.

**Example:**

```./zuendfunk-download.py Downloads/Zündfunk```

This would download all available Zündfunk episodes and save them with correct ID3 tags in the "Downloads/Zündfunk" directory.

### See also
If you want to listen to the downloaded shows with your podcast player: https://github.com/citronalco/mp3-to-rss2feed creates a RSS2 feed from MP3 files.
