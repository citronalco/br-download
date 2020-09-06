# Zündfunk Download

Bayerischer Rundfunk airs a pretty decent radio show called "Zündunk", featuring new music, politics and culture.
For people who missed a show, Bayerischer Rundfunk provides recordings on its web page.

But only for less than one week. And only within a player, without a convenient download button.
That's why I wrote this Python 3 script.

This Python 3 script is a simple command line tool to downloads all currently available Zündfunk episodes from Bayerischer Rundfunk's web page as MP3 files.

### Requirements
Python 3 with modules "mutagen", "urllib3" and "requests".
(On Debian/Ubuntu: `sudo apt install python3 python3-mutagen python3-urllib3 python3-requests`)

### Usage
```./zuendfunk-download.py <TargetDirectory>```

The script searches Bayerischer Rundfunk's "Zündfunk" web site for recordings and downloads all currently available episodes into the given target directory.
Files aready present get skipped, so it is well suited for cron jobs.

The show's metadata gets stored in the downloaded MP3 file's ID3 tags (see below).


**Example:**

```./zuendfunk-download.py Downloads/Zündfunk```

This would download all available Zündfunk episodes and save them with correct ID3 tags in the "Downloads/Zündfunk" directory.

