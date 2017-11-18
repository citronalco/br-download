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

my $browser=WWW::Mechanize->new();
$browser->get($url) or die($!);

# Auf der Seite $url kann man sich durch die letzten und kommenden Zündfunk-Sendungen klicken, die Daten dazu kommen aus einer JSON-Datei
my $tree=HTML::TreeBuilder->new_from_content($browser->content());
my $programDiv=$tree->look_down('_tag'=>'div','id'=>'program_stage');
my ($programJSON)=$programDiv->attr('class')=~/jsonUrl:\'(.+)\'/;
$browser->get($programJSON);

# JSON nach jeder verfügbaren Sendung durchgehen
my $decodedProgramJSON=JSON::decode_json($browser->content);
foreach (@{$decodedProgramJSON->{'channelBroadcasts'}}) {
	next unless (($_->{'broadcastStartDate'}) and ($_->{'broadcastEndDate'}));	# Sendung ist noch in der Zukunft

	my ($url)=$_->{'broadcastHtml'}=~/<a href=\"(.+?)\" title=\"/ or next;		# Seite einer Sendung
	$browser->get($url) or die($!);	# sendungsseite aufrufen

	# auf der Sendungsseite ist entweder direkt ein Player, oder auf einer oder mehrerer Unterseite, oder es gibt gar keinen
	my @possibleAudioPagesUrls=($url,map{ $_->url() } $browser->find_all_links('class_regex'=>qr/link_audio/));

	my @xmlUrls;
	foreach my $audioUrl (@possibleAudioPagesUrls) {
	    $browser->get($audioUrl);
	    my ($xmlUrl)=$browser->content()=~/dataURL:\'(\/.+xml)\'/;
	    if ($xmlUrl) {
		push(@xmlUrls,$xmlUrl);
	    }
	}
	next unless (@xmlUrls);

	# alle gefunden XML-Dateien der Sendung auf Audio-Links prüfen.
	my %longestAudio=('durationInSeconds'=>0);

	foreach my $xmlUrl (@xmlUrls) {
	    $browser->get($xmlUrl);
	    my $dom=XML::LibXML->load_xml(string=>$browser->content);

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
	my ($tries,@parameters,$FD);
	$tries=4;
	@parameters=(
	    $longestAudio{'downloadUrl'},     # URL
	    ":content_cb" => sub {
		my ($chunk) = @_;
		print $FD $chunk;
	    }
	);
	while ($tries) {
	    open($FD,">>".$DESTDIR."/".$filename.".part");

	    my $bytes=-s $DESTDIR."/".$filename.".part";
	    if ($bytes > 0) {
		push(@parameters,"Range"=>"bytes=".$bytes."-");
	    }
	    my $result=$browser->get(@parameters);
	    close $FD;

	    last if ($result->is_success or $result->code == 416);
	    $tries--;
	}
	if ($tries eq 0) {
	    print "failed.\n";
	    next;
	}

	rename $DESTDIR."/".$filename.".part",$DESTDIR."/".$filename;

	my $mp3file=MP3::Tag->new($DESTDIR."/".$filename);
	$mp3file->get_tags();
	my $id3v2=($mp3file->{ID3v2} or $mp3file->new_tag("ID3v2"));
	$id3v2->artist("Zündfunk");
	$id3v2->title($longestAudio{'title'});
	$id3v2->comment($longestAudio{'desc'});
	$id3v2->write_tag();

	$browser->back();
	print "done.\n";
}
