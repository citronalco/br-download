#!/usr/bin/env python3

import sys
from math import floor, ceil
import os.path
import re
from time import sleep
import argparse
import json
from datetime import datetime, date, timedelta
from dateutil.parser import parse
import pytz
from mutagen.id3 import ID3,ID3NoHeaderError,TRSN,TPE1,TALB,TRCK,TIT2,COMM,TYER,TDAT,TIME,TLEN,CTOC,CHAP,WOAS,WORS,APIC,TRSO,TCON,CTOCFlags
import av
import requests


# Some basic URLs discovered within browser
AUDIO_BROADCAST_SERVICES_URL = """
  https://brradio.br.de/radio/v4?query=query broadcastServices{audioBroadcastServices{trackingInfos{pageVars}
  nodes{id dvbServiceId name slug logo(type:SQUARE){url}logoSVG:logo(type:SQUARE,format:SVG){url}url sophoraLivestreamDocuments
  {sophoraId streamingUrl title reliveUrl trackingInfos{mediaVars}}}}}
  """

EPG_URL = """
  https://brradio.br.de/radio/v4?query=query broadcastDayProgram($stationSlug:String!,$day:MangoDay){audioBroadcastService(slug:$stationSlug)
  {... on AudioBroadcastService{epg(day:$day){broadcastEvent{id start end trackingInfos{pageVars mediaVars}items{guid start duration class
  title ... on NewsElement{author}... on MusicElement{performer composer}}excludedTimeRanges{start end}isSeekableNews publicationOf
  {id kicker title description defaultTeaserImage{url}... on MangoProgramme{canonicalUrl title kicker}}}}}}}&variables={"stationSlug":"%s","day":"%s"}
  """

# Note:
# New broadcasts are available under streamingUrl, but with wrong timestamps, and start and end are mostly cut wrong.
# After a few hours the are available corrected under relive_url.
# So we only care about relive_url

def get_segment_urls(start_dt, end_dt, relive_url_template):
  """
  return list of URLs of all ts segments within a given timeframe
  """
  segments_urls = []
  current_dt = start_dt

  while current_dt < end_dt:
    relive_start_dt = current_dt.replace(minute=0)
    # fill placeholders in relive_url_template (playlists always start at full hour and lasts a full hour)
    relive_url = str(relive_url_template)
    relive_url = relive_url.replace('{yMd}', relive_start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime('%Y%m%d'))
    relive_url = relive_url.replace('{H}', relive_start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime('%H'))
    relive_url = relive_url.replace("+{Z}00", relive_start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime('%z'))

    # fetch M3U playlist from relive_url
    relive_playlist = requests.get(relive_url, timeout=5).text

    # this first playlist only contains names of the real playlists (aka media streams)
    mediastreams = re.findall(r'^(?!#)(.+)\n', relive_playlist, re.MULTILINE)

    # media streams and TS snippets have relative URLs to the relive_url
    relive_base_url = re.sub(r'([^\/]+?)\/?$','', relive_url)

    # get real M3U8 playlist with TS paths from the last media stream (streams are sorted by bitrate, last one has the highest)
    playlist_url = relive_base_url + mediastreams[-1]
    response = requests.get(playlist_url, timeout=5)
    if response.status_code == 404:
      # show not yet in relive, so skip it
      return None

    ts_m3u8 = response.text

    # retrieve information about TS stream from m38u
    ts_data = {
      # duration of each TS snippet
      'targetDuration': int(re.search(r'^#EXT-X-TARGETDURATION:\s*(\d+)$', ts_m3u8, re.MULTILINE).group(1)),
      # URLs to all TS snippets
      'segments': list(map(lambda x: relive_base_url + x, re.findall(r'^(?!#)(.*)\n', ts_m3u8, re.MULTILINE)))
    }
    try:
      # datetime of oldest TS snippet (missing in relive playlists)
      ts_data['programDateTime'] = parse(re.search(r'^#EXT-X-PROGRAM-DATE-TIME:\s*(.+)$', ts_m3u8, re.MULTILINE).group(1))
    except AttributeError:
      # relive playlists always start at full hour
      ts_data['programDateTime'] = relive_start_dt.replace(minute=0)

    # calculate first TS snippets for this broadcast in this relive playlist
    ts_first = floor((start_dt - ts_data['programDateTime']).total_seconds() / ts_data['targetDuration'])
    ts_first = max(0, ts_first)

    segment_index = ts_first
    try:
      while current_dt < end_dt:
        segments_urls.append(ts_data['segments'][segment_index])
        current_dt = current_dt + timedelta(seconds=ts_data['targetDuration'])
        segment_index+=1
    except IndexError:
      continue

  return segments_urls


def download(broadcast_event, target_directory, segment_urls):
  """
  download and tag a broadcast
  """
  start_dt = parse(broadcast_event['start'])
  end_dt = parse(broadcast_event['end'])

  # build filename from channel, show title and broadcast datetime, while escaping "bad" characters
  filename = os.path.join(
      target_directory,
      re.sub(
          r'[^\w\s\-\.\[\]]', '_',
          ' '.join([
              broadcast_event['trackingInfos']['pageVars']['broadcast_service'],  # "Bayern 2"
              start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y-%m-%d %H:%M"), # "2025-08-12 12_45"
              broadcast_event['trackingInfos']['pageVars']['topline'] # "Nachrichten, Wetter, Verkehr"
          ])
      ) + ".mp3"
  )

  # Skip broadcast if file is already exists
  if os.path.isfile(filename) and os.path.getsize(filename)>0:
    print(f"{filename} already exists, skipping.", flush=True)
    return True

  # Download all ts segments, and convert them to mp3
  with av.open(filename + '.temp', 'w', format='mp3') as output_container:
    output_stream = output_container.add_stream('mp3', bit_rate=192000, rate=44100)

    for i, segment_url in enumerate(segment_urls):
      print(f"\rDownloading {filename} ... {(i+1)/len(segment_urls)*100:.1f}%", end=" ", flush=True)
      success = False
      retries_left = 3

      while not success and retries_left:
        try:

          with av.open(segment_url, timeout=5) as input_container:
            input_stream = input_container.streams.audio[0]
            try:
              for frame in input_container.decode(input_stream):
                for packet in output_stream.encode(frame):
                  output_container.mux(packet)

            except av.error.InvalidDataError:
              # skip broken frames
              #print(f"Broken Frame in {segment_url}")
              pass

        except av.error.OSError:
          # Download error
          #print(f"Download problem {segment_url}, retrying")
          sleep(3)
          retries_left -= 1
        else:
          success = True

      if not success:
        print(f"\rERROR: Could not download {filename}", file=sys.stderr)
        return False


    # Flush encoder
    output_container.mux(output_stream.encode(None))
    print("done")


  # ID3: remove all tags
  try:
    tags = ID3(filename + '.temp')
    tags.delete()
  except ID3NoHeaderError:
    tags = ID3()

  # ID3: save as much information as possible in the ID3 tags
  tags.add(TRSN(text=[broadcast_event['trackingInfos']['pageVars']['broadcast_service']]))   # Internet radio station name
  tags.add(TRSO(text=['Bayerischer Rundfunk']))                                             # Internet radio station owner
  tags.add(WOAS(url=broadcast_event['publicationOf']['canonicalUrl']))                       # Official audio source webpage
  tags.add(WORS(url="https://www.br.de/radio/"))                                            # Official Internet radio station homepage
  tags.add(TCON(text=["Radio Recording"]))                                                  # Content Description
  tags.add(TPE1(text=[broadcast_event['trackingInfos']['pageVars']['broadcast_service']]))   # Lead performer(s)/Soloist(s) -> CHANNEL
  tags.add(TALB(text=[ " - ".join(list(                                                     # Album/Movie/Show title
    dict.fromkeys([ broadcast_event['trackingInfos']['pageVars']['topline'],
                   broadcast_event['trackingInfos']['pageVars']['title'] ])
    ))]))
  tags.add(TRCK(text=['1/1']))                                                              # Track number/Position in set
  tags.add(TIT2(text=[                                                                      # Title/songname/content description
    f"{broadcast_event['publicationOf']['title']} [{start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime('%Y-%m-%d %H:%M')}]"
  ]))
  tags.add(COMM(lang="deu", desc="desc", text=[broadcast_event['publicationOf']['description']]))  # Comments
  tags.add(TYER(text=[start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime("%Y")]))       # Year of broadcast
  tags.add(TDAT(text=[start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime("%d%m")]))     # Month and day of broadcast
  tags.add(TIME(text=[start_dt.astimezone(pytz.timezone('Europe/Berlin')).strftime("%H%M")]))     # Time of broadcast
  tags.add(TLEN(text=[int((end_dt - start_dt).total_seconds() * 1000)]))                          # Duration in ms

  # ID3: chapters
  chapter_number = 0
  chapter_ids = []
  for chapter in broadcast_event['items']:
    chapter_start_dt = parse(chapter['start'])

    chapter_duration = chapter.get('duration')
    if chapter_duration:
      chapter_end_dt = chapter_start_dt + timedelta(seconds = chapter_duration)
    else:
      chapter_end_dt = end_dt

    # if chapter begins in this broadcast, but ends way after it: skip it!
    if chapter_end_dt > end_dt and (end_dt - chapter_start_dt < chapter_end_dt - end_dt):
      continue

    artists = []
    for i in [ 'performer', 'author' ]:
      if i in chapter and chapter[i] is not None and len(chapter[i])>0:
        artists.append(chapter[i])

    titles = []
    for i in [ 'title' ]:
      if i in chapter and chapter[i] is not None and len(chapter[i])>0:
        titles.append(chapter[i])

    chapter_id = f'ch{chapter_number}'

    tags.add(CHAP(
      element_id = chapter_id,
      start_time = floor((chapter_start_dt - start_dt).total_seconds() * 1000),
      end_time = ceil((chapter_end_dt - start_dt).total_seconds() * 1000),
      sub_frames = [TIT2(text=[ ' - '.join(filter(None,
        [" ".join(artists) if artists else None, " ".join(titles) if titles else None]
      ))])]
    ))

    chapter_ids.append(chapter_id)
    chapter_number += 1

  tags.add(CTOC(
    element_id = "toc",
    flags = CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
    child_element_ids = chapter_ids,
    sub_frames = [TIT2(text=["Table Of Contents"])]
  ))

  # ID3: cover image
  response = requests.get(broadcast_event['publicationOf']['defaultTeaserImage']['url'], timeout=5)
  if response.status_code == 200:
    tags.add(APIC(
      mime = response.headers['content-type'],
      desc="Front Cover",
      data = response.content
    ))

  # save ID3 tags
  tags.save(filename + '.temp', v2_version=3)
  os.rename(filename + '.temp', filename)
  return True


def main():
  parser = argparse.ArgumentParser(
    description = """
      Find all availabe recordings of a show in Bayerischer Rundfunk's player, download them as MP3 files and save the shows' metadata in the ID3 tags.
    """,
  )
  parser.add_argument("-n", "--newest", help='Download newest broadcast only (default: %(default)s)', default=False, action='store_true')
  parser.add_argument("Channel", help="The channel's name (e.g. \"bayern 2\", \"BR-Klassik\", \"Puls\")")
  parser.add_argument("ShowTitle", help="The show's title as shown on https://www.br.de/radio/live/ (e.g. \"Bayern 2 Zündfunk\")")
  parser.add_argument("TargetDirectory", help='Directory to save the files in (default: %(default)s)', nargs='?', default=os.getcwd())
  args = parser.parse_args()

  ONLY_NEWEST = args.newest
  CHANNEL = args.Channel.strip()
  SHOW = args.ShowTitle.strip()
  DESTDIR = args.TargetDirectory

  # Check if DESTDIR exists
  if not os.path.isdir(DESTDIR):
    print(f"Directory {DESTDIR} does not exist!", file=sys.stderr)
    sys.exit(1)

  # For given station name: get relive_url_template and slug
  # while doing so, remember all channels to be able display all valid channel names if no channel matched
  audio_broadcast_services_page = requests.get(AUDIO_BROADCAST_SERVICES_URL, timeout=5).text
  audio_broadcast_services_json = json.loads(audio_broadcast_services_page)

  channel_list = []
  for node in audio_broadcast_services_json['data']['audioBroadcastServices']['nodes']:
    if CHANNEL.lower() == node['name'].lower():
      relive_url_template = node['sophoraLivestreamDocuments'][0]['reliveUrl']
      slug = node['slug']
      break
    channel_list.append(node['name'].lower())

  # If we have not found a relive_url_template, most likely the given channel name is wrong.
  # So display the list of available channel names
  try:
    relive_url_template
  except NameError:
    print(f"Channel '{CHANNEL}' not found!", file=sys.stderr)
    print(f"Valid channels are: {', '.join(channel_list)}", file=sys.stderr)
    sys.exit(1)

  # Loop through EPG of last 8 days, going backwards from today
  today = date.today()
  for day_delta in range(0,8):
    current_day = today - timedelta(days = day_delta)

    # Fetch EPG of this day
    try:
      epg_page = requests.get(EPG_URL % (slug, current_day.strftime("%Y-%m-%d")), timeout=5).text
      epg_data = json.loads(epg_page)
    except:
      print(f"Error: Could not download program information for {current_day.strftime("%Y-%m-%d")}. Please try again later.", file=sys.stderr)
      continue

    # Search in this day's EPG for broadcasts of requested show
    for broadcast in reversed(epg_data['data']['audioBroadcastService']['epg']):
      # Skip empty entries
      if broadcast['broadcastEvent'] is None:
        continue
      # Skip broadcasts not having ended yet
      if parse(broadcast['broadcastEvent']['end']) > datetime.now(tz=pytz.timezone('Europe/Berlin')):
        continue

      if re.search(r'^\s*' + SHOW + r'\s*$', broadcast['broadcastEvent']['trackingInfos']['pageVars']['topline'], flags=re.IGNORECASE):
        # Get links to all audio segments of this broadcast
        segment_urls = get_segment_urls(parse(broadcast['broadcastEvent']['start']), parse(broadcast['broadcastEvent']['end']), relive_url_template)

        # skip broadcast if no segments available (probably not yet in relive)
        if segment_urls is None:
          continue

        download(broadcast['broadcastEvent'], DESTDIR, segment_urls)
        if ONLY_NEWEST:
          sys.exit()


if __name__ == "__main__":
  main()
