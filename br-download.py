#!/usr/bin/env python3

import requests
import sys
from math import floor, ceil
import os.path
import re
from datetime import datetime, date, timedelta
from dateutil.parser import parse
import pytz
from mutagen.id3 import ID3,ID3NoHeaderError,TRSN,TPE1,TALB,TRCK,TIT2,COMM,TYER,TDAT,TIME,TLEN,CTOC,CHAP,WOAS,WORS,APIC,CTOCFlags
from urllib.request import urlopen
from bs4 import BeautifulSoup
import json
from io import BytesIO
from pydub import AudioSegment
import argparse


parser = argparse.ArgumentParser(
    description = "Find all availabe recordings of a show in Bayerischer Runfunk's player, download them as MP3 files and save the shows' metadata in the ID3 tags.",
)
parser.add_argument("Channel", help="The channel's name (e.g. \"Bayern2\", \"BR-Klassik\", \"Puls\")")
parser.add_argument("ShowTitle", help="The show's title (e.g. \"Zündfunk\")")
parser.add_argument("Directory", help="The directory to save the files in (e.g. \"Downloads/Zündfunk Recordings\")")
args = parser.parse_args()

CHANNEL = args.Channel
SHOW = args.ShowTitle
DESTDIR = args.Directory
if not os.path.isdir(DESTDIR):
    print("Directory %s does not exist!" % DESTDIR, file=sys.stderr)
    sys.exit(1)

baseUrl="https://www.br.de/radio/live/%s/programm/" % CHANNEL.lower()

# Fetch program information of the current day and fetch M3U8 data
day = date.today()
try:
  html = requests.get(baseUrl + '/' + day.strftime("%Y-%m-%d") + '/', timeout=5).text

  # extract JSON data embedded into HTML page
  soup = BeautifulSoup(html, 'lxml')
  jsonData = json.loads(soup.find('script', id='__NEXT_DATA__').encode_contents())

  # get M3U8 with paths to media streams
  streamsM3U8url = jsonData['props']['pageProps']['stationData']['audioBroadcastService']['sophoraLivestreamDocuments'][0]['streamingUrl']
  streamsM3U8 = requests.get(streamsM3U8url).text

  # retrieve all media stream paths from M3U8
  streams = re.findall(r'^(?!#)(.*)\n', streamsM3U8, re.MULTILINE)

  # get M3U8 with TS paths from media stream (streams are sorted by bitrate, last one has the highest)
  tsBaseUrl = re.sub(r'([^\/]+?)\/?$','', streamsM3U8url)
  tsM3U8 = requests.get(tsBaseUrl + streams[-1]).text
except:
  print("Error: Could fetch download program information from %s" % baseUrl + '/' + day.strftime("%Y-%m-%d") + '/', file=sys.stderr)
  exit(1)

# retrieve information about TS stream from M3U8
tsData = {
    # name of the first TS snippet
    'mediaSequence': int(re.search(r'^#EXT-X-MEDIA-SEQUENCE:\s*(\d+)$', tsM3U8, re.MULTILINE).group(1)),
    # duration of each TS snippet
    'targetDuration': int(re.search(r'^#EXT-X-TARGETDURATION:\s*(\d+)$', tsM3U8, re.MULTILINE).group(1)),
    # datetime of oldest TS snippet
    'programDateTime': parse(re.search(r'^#EXT-X-PROGRAM-DATE-TIME:\s*(.+)$', tsM3U8, re.MULTILINE).group(1)),
    # URLs to all TS snippets
    'segments': list(map(lambda x: tsBaseUrl + x, re.findall(r'^(?!#)(.*)\n', tsM3U8, re.MULTILINE)))
}


# search for broadcasts of requested show
foundBroadcasts = []
while True:
  # loop broadcasts from new to old
  for broadcast in reversed(jsonData['props']['pageProps']['stationDayProgramData']['audioBroadcastService']['epg']):

    # stop on any broadcast too dated
    if parse(broadcast['broadcastEvent']['start']) < tsData['programDateTime']:
      break

    # skip broadcasts not having ended yet
    if parse(broadcast['broadcastEvent']['end']) > datetime.now(tz=pytz.timezone('Europe/Berlin')):
      continue

    match = re.search('^\s*' + SHOW + '\s*$', broadcast['broadcastEvent']['trackingInfos']['pageVars']['topline'], flags=re.IGNORECASE)
    if match:
      foundBroadcasts.append(broadcast['broadcastEvent'])

  else:
    # no "break" happened above? -> get data of previous day and continue searching!
    day = day - timedelta(days = 1)
    html = requests.get(baseUrl + '/' + day.strftime("%Y-%m-%d") + '/', timeout=5).text
    soup = BeautifulSoup(html, 'lxml')
    jsonData = json.loads(soup.find('script', id='__NEXT_DATA__').encode_contents())
    continue

  # broadcasts are too dated already ("break" happened above), don't go further in the past
  break


# download broadcasts, from old to new
for broadcast in reversed(foundBroadcasts):

  broadcastStartDT = parse(broadcast['start'])
  broadcastEndDT = parse(broadcast['end'])

  # build filename from channel, show title and broadcast datetime, while escaping "bad" characters
  filename = os.path.join(
      DESTDIR,
      re.sub(
          '[^\w\s\-\.\[\]]', '_',
          broadcast['trackingInfos']['pageVars']['broadcast_service'] + ' ' + broadcast['trackingInfos']['pageVars']['topline'] + ' ' + broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y-%m-%d %H:%M")
      ) + ".mp3"
  )


  # skip broadcast if file is already exists
  if os.path.isfile(filename) and os.path.getsize(filename)>0:
    print("%s already exists, skipping." % filename, flush=True)
    continue

  # calculate TS snippets for this broadcast
  ts_first = floor( (broadcastStartDT - tsData['programDateTime']).total_seconds() / tsData['targetDuration'])
  ts_last = ceil( (broadcastEndDT - tsData['programDateTime']).total_seconds() / tsData['targetDuration'])

  # dowload all ts segments, and convert them to mp3
  print("Downloading %s ..." % filename, end=" ", flush=True)

  try:
    sound = AudioSegment.empty()
    for i in range(ts_first, ts_last):
      sound += AudioSegment.from_file(BytesIO(urlopen(tsData['segments'][i]).read()))
    sound.export(filename, format="mp3")
  except:
    print("failed.", flush=True)
    continue
  else:
    print("done.", flush=True)

  # ID3: remove all tags
  try:
    tags = ID3(filename)
    tags.delete()
  except ID3NoHeaderError:
    tags = ID3()

  # ID3: save as much information as possible in the ID3 tags
  tags.add(TRSN(text=[broadcast['trackingInfos']['pageVars']['broadcast_service']]))
  tags.add(TPE1(text=[broadcast['trackingInfos']['pageVars']['broadcast_service']]))
  tags.add(TALB(text=[ " - ".join(list(dict.fromkeys([ broadcast['trackingInfos']['pageVars']['topline'], broadcast['trackingInfos']['pageVars']['title'] ])))]))
  tags.add(TRCK(text=['1/1']))
  tags.add(TIT2(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y-%m-%d %H:%M")]))
  tags.add(COMM(lang="deu", desc="desc", text=[ broadcast['publicationOf']['description'] ]))
  tags.add(TYER(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y")]))
  tags.add(TDAT(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%d%m")]))
  tags.add(TIME(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%H%M")]))
  tags.add(TLEN(text=[int((broadcastEndDT - broadcastStartDT).total_seconds() * 1000)]))
  tags.add(WOAS(url=broadcast['publicationOf']['canonicalUrl']))
  tags.add(WORS(url=baseUrl))

  # ID3: chapters
  chapterNr = 0
  for chapter in broadcast['items']:
    chapterStartDT = parse(chapter['start'])

    if 'duration' in chapter and chapter['duration'] is not None:
      chapterEndDT = chapterStartDT + timedelta(seconds = chapter['duration'])
    else:
      chapterEndDT = broadcastEndDT

    artists = []
    for i in [ 'performer', 'author' ]:
      if i in chapter and chapter[i] is not None and len(chapter[i])>0:
        artists.append(chapter[i])

    titles = []
    for i in [ 'title' ]:
      if i in chapter and chapter[i] is not None and len(chapter[i])>0:
        titles.append(chapter[i])

    tags.add(CHAP(
      element_id = chapterNr,
      start_time = floor((chapterStartDT - broadcastStartDT).total_seconds() * 1000),
      end_time = ceil((chapterEndDT - broadcastStartDT).total_seconds() * 1000),
      sub_frames = [TIT2(text=[ " - ".join([" ".join(artists), " ".join(titles) ])])]
    ))
    chapterNr += 1


  tocList = ",".join([ str(i) for i in range(0,chapterNr) ])

  tags.add(CTOC(
    element_id = "toc",
    flags = CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
    child_element_ids = [tocList],
    sub_frames = [TIT2(text=["Table Of Contents"])]
  ))

  # ID3: cover image
  response = requests.get(broadcast['publicationOf']['defaultTeaserImage']['url'])
  if response.status_code == 200:
    tags.add(APIC(mime=response.headers['content-type'], desc="Front Cover", data=response.content))

  # save ID3 tags
  tags.save(filename,v2_version=3)

exit()
