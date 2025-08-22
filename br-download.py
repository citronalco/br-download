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
import json
from io import BytesIO
from pydub import AudioSegment
import argparse

# Some basic URLs discovered within browser
audioBroadcastServicesUrl="https://brradio.br.de/radio/v4?query=query broadcastServices{audioBroadcastServices{trackingInfos{pageVars}nodes{id dvbServiceId name slug logo(type:SQUARE){url}logoSVG:logo(type:SQUARE,format:SVG){url}url sophoraLivestreamDocuments{sophoraId streamingUrl title reliveUrl trackingInfos{mediaVars}}}}}"
epgUrl='https://brradio.br.de/radio/v4?query=query broadcastDayProgram($stationSlug:String!,$day:MangoDay){audioBroadcastService(slug:$stationSlug){... on AudioBroadcastService{epg(day:$day){broadcastEvent{id start end trackingInfos{pageVars mediaVars}items{guid start duration class title ... on NewsElement{author}... on MusicElement{performer composer}}excludedTimeRanges{start end}isSeekableNews publicationOf{id kicker title description defaultTeaserImage{url}... on MangoProgramme{canonicalUrl title kicker}}}}}}}&variables={"stationSlug":"%s","day":"%s"}'

# Note:
# New broadcasts are available under streamingUrl, but with wrong timestamps, and start and end are mostly cut wrong.
# After a few hours the are available corrected under reliveUrl.
# So we only care about reliveUrl

def getSegmentUrls(startDT,endDT,reliveUrlTemplate):
  segmentsList = []
  segmentsListEnd = startDT

  while segmentsListEnd < endDT:
    reliveStartDT = segmentsListEnd.replace(minute=0)
    # fill placeholders in reliveUrl (playlists always start at full hour and last a full hour)
    reliveUrl = str(reliveUrlTemplate)
    reliveUrl = reliveUrl.replace('{yMd}', reliveStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime('%Y%m%d'))
    reliveUrl = reliveUrl.replace('{H}', reliveStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime('%H'))
    reliveUrl = reliveUrl.replace("+{Z}00", reliveStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime('%z'))

    # fetch M3U playlist from reliveUrl
    relivePlaylist = requests.get(reliveUrl).text
    # this first playlist only contains names of the real playlists (aka media streams)
    mediaStreams = re.findall(r'^(?!#)(.+)\n', relivePlaylist, re.MULTILINE)

    # media streams and TS snippets have relative URLs to the reliveUrl
    reliveBaseUrl = re.sub(r'([^\/]+?)\/?$','', reliveUrl)

    # get real M3U8 playlist with TS paths from the last media stream (streams are sorted by bitrate, last one has the highest)
    playlistUrl = reliveBaseUrl + mediaStreams[-1]
    response = requests.get(playlistUrl)
    if response.status_code == 404:
      # show not yet in relive, so skip it
      return None

    tsM3U8 = response.text

    # retrieve information about TS stream from m38u
    tsData = {
      # duration of each TS snippet
      'targetDuration': int(re.search(r'^#EXT-X-TARGETDURATION:\s*(\d+)$', tsM3U8, re.MULTILINE).group(1)),
      # URLs to all TS snippets
      'segments': list(map(lambda x: reliveBaseUrl + x, re.findall(r'^(?!#)(.*)\n', tsM3U8, re.MULTILINE)))
    }
    try:
      # datetime of oldest TS snippet (missing in relive playlists)
      tsData['programDateTime'] = parse(re.search(r'^#EXT-X-PROGRAM-DATE-TIME:\s*(.+)$', tsM3U8, re.MULTILINE).group(1))
    except AttributeError:
      # relive playlists always start at full hour
      tsData['programDateTime'] = reliveStartDT.replace(minute=0)

    # calculate first TS snippets for this broadcast in this relive playlist
    ts_first = floor((startDT - tsData['programDateTime']).total_seconds() / tsData['targetDuration'])
    if ts_first < 0:
      ts_first = 0

    segIdx = ts_first

    try:
      while segmentsListEnd < endDT:
        segmentsList.append(tsData['segments'][segIdx])
        segmentsListEnd = segmentsListEnd + timedelta(seconds=tsData['targetDuration'])
        segIdx+=1
    except IndexError:
      continue

  return segmentsList


# download and tag a broadcast
def download(broadcast, targetDir, reliveUrlTemplate):
  broadcastStartDT = parse(broadcast['start'])
  broadcastEndDT = parse(broadcast['end'])

  # build filename from channel, show title and broadcast datetime, while escaping "bad" characters
  filename = os.path.join(
      targetDir,
      re.sub(
          '[^\w\s\-\.\[\]]', '_',
          broadcast['trackingInfos']['pageVars']['broadcast_service'] + ' ' + broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y-%m-%d %H:%M") + ' ' + broadcast['trackingInfos']['pageVars']['topline']
      ) + ".mp3"
  )

  # skip broadcast if file is already exists
  if os.path.isfile(filename) and os.path.getsize(filename)>0:
    print("%s already exists, skipping." % filename, flush=True)
    return

  # get links to all audio segments of this broadcast
  segmentUrls = getSegmentUrls(broadcastStartDT, broadcastEndDT, reliveUrlTemplate)
  if segmentUrls is None:
    # skip broadcast if no segments available
    print("Skipping %s, not yet in relive" % filename)
    return

  # dowload all ts segments, and convert them to mp3
  print("Downloading %s ..." % filename, end=" ", flush=True)

  try:
    sound = AudioSegment.empty()
    for i in segmentUrls:
      sound += AudioSegment.from_file(BytesIO(urlopen(i).read()))
    sound.export(filename, format="mp3")
  except:
    print("failed.", flush=True)
    return
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
  #tags.add(TIT2(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y-%m-%d %H:%M")]))
  tags.add(TIT2(text=[broadcast['publicationOf']['title']]))
  tags.add(COMM(lang="deu", desc="desc", text=[broadcast['publicationOf']['description']]))
  tags.add(TYER(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y")]))
  tags.add(TDAT(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%d%m")]))
  tags.add(TIME(text=[broadcastStartDT.astimezone(pytz.timezone('Europe/Berlin')).strftime("%H%M")]))
  tags.add(TLEN(text=[int((broadcastEndDT - broadcastStartDT).total_seconds() * 1000)]))
  tags.add(WOAS(url=broadcast['publicationOf']['canonicalUrl']))
  tags.add(WORS(url="https://www.br.de/radio/"))

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
  response = requests.get(broadcast['publicationOf']['defaultTeaserImage']['url'], timeout=5)
  if response.status_code == 200:
    tags.add(APIC(mime=response.headers['content-type'], desc="Front Cover", data=response.content))

  # save ID3 tags
  tags.save(filename,v2_version=3)


def main():
  parser = argparse.ArgumentParser(
    description = "Find all availabe recordings of a show in Bayerischer Runfunk's player, download them as MP3 files and save the shows' metadata in the ID3 tags.",
  )
  parser.add_argument("Channel", help="The channel's name (e.g. \"bayern 2\", \"BR-Klassik\", \"Puls\")")
  parser.add_argument("ShowTitle", help="The show's title (e.g. \"Zündfunk\")")
  parser.add_argument("Directory", help="The directory to save the files in (e.g. \"Downloads/Zündfunk Recordings\")")
  args = parser.parse_args()

  channelName = args.Channel
  show = args.ShowTitle
  targetDir = args.Directory

  # check if targetDir exists
  if not os.path.isdir(targetDir):
    print("Directory %s does not exist!" % targetDir, file=sys.stderr)
    sys.exit(1)

  # get reliveUrlTemplate and slug for given station name
  audioBroadcastServicesPage=requests.get(audioBroadcastServicesUrl, timeout=5).text
  audioBroadcastServicesJson=json.loads(audioBroadcastServicesPage)
  channelList = []
  for node in audioBroadcastServicesJson['data']['audioBroadcastServices']['nodes']:
    channelList.append(node['name'].lower())
    if channelName.lower() == node['name'].lower():
      reliveUrlTemplate = node['sophoraLivestreamDocuments'][0]['reliveUrl']
      slug = node['slug']
      break

  # if we have not found a reliveUrlTemplate, most likely the given channel name is wrong.
  # So display the list of available channel names
  try:
    reliveUrlTemplate
  except NameError:
    print("Channel %s not found!" % channelName, file=sys.stderr)
    print("Valid channels are: %s" % ", ".join(channelList))
    sys.exit(1)

  # Loop through last week, starting from today
  today = date.today()
  for dateDelta in range(0,8):
    thisDay = today - timedelta(days = dateDelta)

    # fetch EPG of this day
    try:
      epgPage = requests.get(epgUrl % (slug, thisDay.strftime("%Y-%m-%d")), timeout=5).text
      epgData = json.loads(epgPage)
    except:
      print("Error: Could not download program information for %s. Please try again later." % thisDay.strftime("%Y-%m-%d"), file=sys.stderr)
      continue

    # search in EPG for broadcasts of requested show
    for broadcast in reversed(epgData['data']['audioBroadcastService']['epg']):
      # skip empty entries
      if broadcast['broadcastEvent'] is None:
        continue
      # skip broadcasts not having ended yet
      if parse(broadcast['broadcastEvent']['end']) > datetime.now(tz=pytz.timezone('Europe/Berlin')):
        continue

      match = re.search('^\s*' + show + '\s*$', broadcast['broadcastEvent']['trackingInfos']['pageVars']['topline'], flags=re.IGNORECASE)
      if match:
        download(broadcast['broadcastEvent'], targetDir, reliveUrlTemplate)

if __name__ == "__main__":
  main()
