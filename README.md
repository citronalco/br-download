# Zündfunk download

The Bayerischer Rundfunk airs a pretty decent radio show called "Zündunk", featuring new music, politics and culture. For people who missed a show the Bayerischer Rundfunk provides recordings on its web page.
But only for less than one week. And only within a player, without a convenient download button.
That's why I wrote this script.

This script simply downloads all currently available Zündfunk recordings from the Bayerischer Rundfunk's web page and saves them in a directory.
The downloaded files get named with the show's date and title (e.g. "Zündfunk 2017-10-19 - Wahlen in Tschechien _ Das Mode-Comeback der Logos _ Band Interview Fink.mp3"), recordings already downloaded in a previous run get skipped.
The script also adds some ID3v2 tags to the MP3 files (artist: "Zündfunk", title: the show's title, comment: the show's description if available).

To create a personal archive of all Zündfunk shows just run this script once a day, e.g. with a cronjob.
