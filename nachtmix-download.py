#!/usr/bin/env python3

import requests
import sys
import urllib.parse
import urllib.request
import os.path
import re
from datetime import datetime, date
import time
from mutagen.id3 import ID3,ID3NoHeaderError,TRSN,TPE1,TALB,TRCK,TIT2,COMM,TYER,TDAT,TIME,TLEN,WOAS,WORS,TLAN,APIC
import shutil
from tempfile import NamedTemporaryFile
import lxml
from bs4 import BeautifulSoup
#import pprint

baseUrl="https://www.br.de/radio/bayern2/sendungen/nachtmix/index.html";

def download(url: str, attempts=4):
    tmpfile = NamedTemporaryFile(delete=False)
    for attempt in range (1,attempts+1):
        try:
            if attempt > 1:
                time.sleep(3)
            #urllib.request.urlretrieve(url, tmpfile.name)
            stream = urllib.request.urlopen(url)
            shutil.copyfileobj(stream, tmpfile)
            return tmpfile.name
        except:
            pass
    return None

if len(sys.argv) != 2:
    print("Usage:", file=sys.stderr)
    print("%s <DownloadDir>\n" % sys.argv[0], file=sys.stderr)
    print("Example:", file=sys.stderr)
    print("%s 'Downloads/Nachtmix Recordings'\n" % sys.argv[0], file=sys.stderr)
    sys.exit(1)

DESTDIR = sys.argv[1]

if not os.path.isdir(DESTDIR):
    print("Directory %s does not exist!" % DESTDIR, file=sys.stderr)
    sys.exit(1)


def time2seconds(timestr: str):
    # return duration of HH:MM:SS in seconds
    parts = re.split(":", timestr)
    return int(parts[0])*3600+int(parts[1])*60+int(parts[2])

def safe_text_get(l: list, idx: int, default=None):
    # return text attribute of list item, or default value if it does not exist
    try:
        return l[idx].text
    except IndexError:
        return default


html = requests.get(baseUrl, timeout=5).text
soup = BeautifulSoup(html, 'lxml')

# extract Json URL
jsonUrl = None
for className in soup.find('div', id='program_stage')['class']:
    match = re.match('.*jsonUrl:\s*[\'\"](.+?)[\'\"]',className)
    if match:
        jsonUrl = match.group(1)
        # jsonUrl is relative, make it absolute
        jsonUrl = urllib.parse.urljoin(baseUrl, jsonUrl)

if jsonUrl == None:
    print ("ERROR: Could not find JSON file containing the broadcasts", file=sys.stderr)
    sys.exit(1)

# fetch Json
broadcastJson = requests.get(jsonUrl, timeout=5).json()

# a "channelBroadcast" is a episode of a radio show
for bc in broadcastJson['channelBroadcasts']:
    if not bc['broadcastStartDate'] or not bc['broadcastEndDate']:
        # show's in the future, skip it
        continue

    # the link to the episode's web page is in the "broadcastHTML" attribute - within HTML
    bcSoup = BeautifulSoup(bc['broadcastHtml'], 'lxml')
    episodeUrl = bcSoup.find('div', class_='broadcast').find('a', href=True)['href']
    episodeUrl = urllib.parse.urljoin(baseUrl, episodeUrl)

    episodePage = requests.get(episodeUrl, timeout=5).text
    episodePageSoup = BeautifulSoup(episodePage, 'lxml')

    # the episode's web page either contains a player, links to websites with a player, or nothing of interest.
    # we collect a list of URLs of all those sites
    candidates = [ episodeUrl ]
    for url in list(link['href'] for link in episodePageSoup.find_all('a',class_=re.compile('link_audio'), href=True)):
        candidates.append(urllib.parse.urljoin(baseUrl, url))

    # on each of this pages try to find the player link (<a id="avPlayer_...) and extract the dataURL from the "onlick" parameter
    # dataURL points to a XML ressource. Fetch them!
    xmls = []

    for url in candidates:
        page = requests.get(url, timeout=5).text
        pageSoup = BeautifulSoup(page, 'lxml')

        for player in pageSoup.find_all('a', id=re.compile('^avPlayer'), onclick=True):
            match = re.match('^.*dataURL:\s*[\'\"](.+?)[\'\"]',player['onclick'])
            if match:
                dataUrl = match.group(1)
                dataUrl = urllib.parse.urljoin(baseUrl, dataUrl)

                # dataURL is the URL to a XML file with metadata for the media
                #xmls.append(lxml.etree.parse(dataUrl))
                # lxml does not support HTTPS
                xmls.append(lxml.etree.parse(urllib.request.urlopen(dataUrl)))

    # if nothing was found: continue with next episode
    if len(xmls) == 0:
        continue

    # Figure out best matching XML
    ## sort XMLs according to audio length, longest first
    xmls = sorted(xmls, key=lambda x: time2seconds(x.xpath('./audio/duration')[0].text), reverse=True)

    # extract metadata from XML with longest audio
    XMLmeta = {
        'topline': safe_text_get(xmls[0].xpath("./audio/topline"),0),
        'title': re.sub("^Jetzt nachhören: ","", safe_text_get(xmls[0].xpath("./audio/title"),0)),
        'shareTitle': safe_text_get(xmls[0].xpath("./audio/shareTitle"),0),
        'duration': safe_text_get(xmls[0].xpath("./audio/duration"),0),
        'channel': safe_text_get(xmls[0].xpath("./audio/channel"),0,"BAYERN 2"),
        'broadcast': safe_text_get(xmls[0].xpath("./audio/broadcast"),0),
        'broadcastDate': safe_text_get(xmls[0].xpath("./audio/broadcastDate"),0,date.today().strftime("%d.%m.%Y")),
        'author': safe_text_get(xmls[0].xpath("./audio/author"),0),
        'desc': safe_text_get(xmls[0].xpath("./audio/desc"),0),
        'permalink': safe_text_get(xmls[0].xpath("./audio/permalink"),0),
        'homepageUrl': safe_text_get(xmls[0].xpath("./audio/homepageUrl"),0,"https://www.br.de/index.html"),
        'imageUrl': "https://br.de" + safe_text_get(xmls[0].xpath("./audio/teaserImage/variants/variant[@name='image512']/url"),0),
        'agf_c9': safe_text_get(xmls[0].xpath("./audio/agf-tracking/c9"),0),
    }

#    pprint.PrettyPrinter(indent=4).pprint(XMLmeta)
#    continue

    # our own metadata
    meta = {
        'downloadUrl': None,
        'broadcastDate_dt': None,
        'filename': None,
        'filepath': None,
        'duration_ms': time2seconds(XMLmeta['duration']) * 1000,
    }

    ## Filter out some episodes
    # I know that a real Nachtmix episode is longer than 45 minutes. Skip this episode if it is shorter
    if meta['duration_ms']  < 45 * 60 * 1000:
        continue
    # Skip all non "Nachtmix" broadcasts
    if XMLmeta['broadcast'].lower() != 'nachtmix':
        continue


    # build filename
    filename = XMLmeta['broadcast'] + " " + '-'.join(reversed(XMLmeta['broadcastDate'].split('.'))) + " - " + XMLmeta['title'][0:80] + ".mp3"
    # in filename replace bad characters
    meta['filename'] = re.sub('[^\w\s\-\.\[\]]','_', filename)

    # filename with path
    meta['filepath'] = os.path.join(DESTDIR, meta['filename'])

    # continue with next episode if file already exists
    if os.path.isfile(meta['filepath']) and os.path.getsize(meta['filepath'])>0:
        print("%s already exists, skipping." % meta['filename'], flush=True)
        continue


    ## Populate values in "meta" dict
    # agf_c9 looks like "Nachtmix_Nachtmix_27.08.2020_23:05"
    # so it can be used to extract the episode's exact broadcast time
    try:
        parts = XMLmeta['agf_c9'].split('_')
        meta['broadcastDate_dt'] = datetime.strptime(parts[2] + " " + parts[3], "%d.%m.%Y %H:%M")
    except:
        meta['broadcastDate_dt'] = datetime.strptime(XMLmeta['broadcastDate'], "%d.%m.%Y")


    # from the XML with the longest audio, get all MP3 audio tracks ("assets")
    mp3Assets = xmls[0].xpath("./audio/assets/asset/codecAudio[contains(.,'mp3') or contains(.,'MP3')]/..")
    # from all MP3 audio tracks select the one with the highest bitrate...
    highestBitrateMp3Asset = sorted(mp3Assets, key=lambda x: int(x.xpath('./bitrateAudio')[0].text), reverse=True)[0]
    # ...and get its downloadURL
    meta['downloadUrl'] = "https:" + highestBitrateMp3Asset.xpath("./downloadUrl")[0].text


    # download file in temporary dir
    print("Downloading %s..." % meta['filename'], end=" ", flush=True)
    tmpFile = download(meta['downloadUrl'])
    if tmpFile is None:
        print ("failed.", flush=True)
        print ("ERROR: Could not download %s" % url, file=sys.stderr)
        sys.exit(1)

    # set ID3 tag
    try:
        tag = ID3(tmpFile)
        tag.delete()
    except ID3NoHeaderError:
        tag = ID3()

    tag.add(TRSN(text=[XMLmeta['channel']]))
    tag.add(TPE1(text=[XMLmeta['channel']]))
    tag.add(TALB(text=[XMLmeta['broadcast']]))
    tag.add(TRCK(text=["1/1"]))
    #tag.add(TIT2(text=[meta['broadcastDate_dt'].strftime("%Y-%m-%d") + ": "+XMLmeta['title']]))
    tag.add(TIT2(text=[XMLmeta['title']]))
    tag.add(COMM(lang="deu", desc="desc", text=[XMLmeta['desc']]))
    tag.add(TYER(text=[meta['broadcastDate_dt'].strftime("%Y")]))
    tag.add(TDAT(text=[meta['broadcastDate_dt'].strftime("%d%m")]))
    tag.add(TIME(text=[meta['broadcastDate_dt'].strftime("%H%M")]))
    tag.add(TLEN(text=[meta['duration_ms']]))
    tag.add(WOAS(url=XMLmeta['permalink']))
    tag.add(WORS(url=XMLmeta['homepageUrl']))
    tag.add(TLAN(text=["deu"]))

    # add cover image
    if XMLmeta['imageUrl'] is not None:
        try:
            response = requests.get(XMLmeta['imageUrl'], timeout=5)
            if response.status_code == 200:
                imageData = response.content
                imageMime = response.headers['content-type']
                if imageData is not None and imageMime is not None:
                    tag.add(APIC(mime=imageMime, desc="Front Cover", data=imageData))
        except:
            pass


    # save ID3 tag
    tag.save(tmpFile,v2_version=3)

    # done
    shutil.move(tmpFile, meta['filepath'])
    print("done.", flush=True)
