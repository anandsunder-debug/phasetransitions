#!/usr/bin/env perl
use strict;
use warnings;

use Getopt::Long qw(GetOptions);
use JSON::PP;
use HTTP::Tiny;
use File::Path qw(make_path);

my $base_url = 'http://localhost:8001';
my $report = 'report.json';
my $out = 'artifacts/perl-fea/runtime-inputs.json';
my $timeout = 5;

GetOptions(
    'base-url=s' => \$base_url,
    'report=s' => \$report,
    'out=s' => \$out,
    'timeout=i' => \$timeout,
) or die "Invalid arguments\n";

my $json = JSON::PP->new->utf8->canonical->pretty;
my $http = HTTP::Tiny->new(timeout => $timeout);

sub read_json_file {
    my ($path) = @_;
    return undef if !-f $path;
    open my $fh, '<', $path or return undef;
    local $/ = undef;
    my $raw = <$fh>;
    close $fh;
    return eval { JSON::PP::decode_json($raw) };
}

sub fetch_json {
    my ($url) = @_;
    my $res = $http->get($url);
    return undef if !$res->{success};
    return eval { JSON::PP::decode_json($res->{content}) };
}

my $report_data = read_json_file($report) // {};
my $topology = fetch_json("$base_url/api/healing/topology/schema") // {};
my $metrics_real = fetch_json("$base_url/api/metrics/real") // {};
my $reliability = fetch_json("$base_url/api/metrics/reliability") // {};
my $healing_status = fetch_json("$base_url/api/healing/status") // {};

my $payload = {
    generated_at => scalar gmtime(),
    base_url => $base_url,
    report => $report_data,
    topology_schema => $topology,
    metrics_real => $metrics_real,
    reliability => $reliability,
    healing_status => $healing_status,
};

my ($dir) = ($out =~ m{^(.*)[/\\][^/\\]+$});
if (defined $dir && length $dir) {
    make_path($dir) if !-d $dir;
}

open my $fh, '>', $out or die "Failed to write $out: $!\n";
print {$fh} $json->encode($payload);
close $fh;

print "Wrote runtime inputs to $out\n";
