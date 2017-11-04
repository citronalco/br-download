#!/usr/bin/perl

use strict;
use warnings;
use WWW::Mechanize;
use HTML::TreeBuilder;
use XML::LibXML;
use JSON;
use MP3::Tag;
MP3::Tag->config(write_v24 => 1);
use utf8;

my $DESTDIR=$ARGV[0];
die ($0." <directory>\n") unless ($DESTDIR);
die ($DESTDIR." does not exist") unless ( -d $DESTDIR);

my $url="http://www.br.de/radio/bayern2/sendungen/zuendfunk/programm-nachhoeren/index.html";


my $mech=WWW::Mechanize->new();
$mech->get($url) or die($!);

# Auf der Seite $url kann man sich durch die letzten und kommenden Zündfunk-Sendungen klicken, die Daten dazu kommen aus einer JSON-Datei
my $tree=HTML::TreeBuilder->new_from_content($mech->content());
my $programDiv=$tree->look_down('_tag'=>'div','id'=>'program_stage');
my ($programJSON)=$programDiv->attr('class')=~/jsonUrl:\'(.+)\'/;
$mech->get($programJSON);

# JSON nach jeder verfügbaren Sendung durchgehen
my $decodedProgramJSON=JSON::decode_json($mech->content);
foreach (@{$decodedProgramJSON->{'channelBroadcasts'}}) {
	next unless (($_->{'broadcastStartDate'}) and ($_->{'broadcastEndDate'}));	# Sendung ist noch in der Zukunft

	my ($url)=$_->{'broadcastHtml'}=~/<a href=\"(.+?)\" title=\"/ or next;		# Seite einer Sendung
	$mech->get($url) or die($!);	# sendungsseite aufrufen

	# auf der Sendungsseite ist entweder direkt ein Player, oder auf einer oder mehrerer Unterseite, oder es gibt gar keinen
	my @possibleAudioPagesUrls=($url,map{ $_->url() } $mech->find_all_links('class_regex'=>qr/link_audio/));

	my @xmlUrls;
	foreach my $audioUrl (@possibleAudioPagesUrls) {
	    $mech->get($audioUrl);
	    my ($xmlUrl)=$mech->content()=~/dataURL:\'(\/.+xml)\'/;
	    if ($xmlUrl) {
		push(@xmlUrls,$xmlUrl);
	    }
	}
	next unless (@xmlUrls);

	# alle gefunden XML-Dateien der Sendung auf Audio-Links prüfen.
	my %longestAudio=('durationInSeconds'=>0);

	foreach my $xmlUrl (@xmlUrls) {
	    $mech->get($xmlUrl);
	    my $dom=XML::LibXML->load_xml(string=>$mech->content);

	    # Duration ist HH:MM:SS, bei kürzeren Sachen auch mal MM:SS
	    my $duration=$dom->findvalue('playlist/audio/duration');
	    my ($h,$m,$s)=split(/:/,$duration);
	    my $durationInSeconds=$s+($m*60)+($h*60*60);

	    # Duration muss mindestens 45 Minuten (=2700 Sekunden) sein, die längste Audiodatei wird gesucht
	    if (($durationInSeconds >= 2700) and ($durationInSeconds > $longestAudio{'durationInSeconds'})) {
		$longestAudio{'durationInSeconds'}	= $durationInSeconds;
		$longestAudio{'description'}		= $dom->findvalue('playlist/audio/desc');
		$longestAudio{'broadcastDate'}		= $dom->findvalue('playlist/audio/broadcastDate');
		$longestAudio{'title'}			= $dom->findvalue('playlist/audio/title');

		foreach ($dom->findnodes('playlist/audio/assets/asset/downloadUrl')) {
		    if ($_->to_literal=~/mp3$/) {
			$longestAudio{'downloadUrl'}=$_->to_literal;
			last;
		    }
		}
	    }
	}
	next unless ($longestAudio{'downloadUrl'});

	# wenn was gefunden wurde: herunterladen
	my $filename="Zündfunk ".join("-",reverse(split(/\./,$longestAudio{'broadcastDate'})))." - ".substr($longestAudio{'title'},0,80).".mp3";
	$filename=~s/[^\w\s\-\.]/_/g;

	if (-f $DESTDIR."/".$filename) {
	    print "File ".$filename." does already exist, skipping\n";
	    next;
	}

	print "Downloading ".$filename."... ";

	my $try=5;
	do {
	    $mech->get($longestAudio{'downloadUrl'});
	} while (--$try>0 and !$mech->success());
	if ($try==0) {
	    print "failed.\n";
	    next;
	}

	$mech->save_content($DESTDIR."/".$filename);

	my $mp3file=MP3::Tag->new($DESTDIR."/".$filename);
	$mp3file->get_tags();
	my $id3v2=($mp3file->{ID3v2} or $mp3file->new_tag("ID3v2"));
	$id3v2->artist("Zündfunk");
	$id3v2->title($longestAudio{'title'});
	$id3v2->comment($longestAudio{'desc'});
	$id3v2->write_tag();

	$mech->back();
	print "done.\n";
}
