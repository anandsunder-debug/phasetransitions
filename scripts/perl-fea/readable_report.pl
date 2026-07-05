#!/usr/bin/env perl
use strict;
use warnings;

use FindBin qw($RealBin);

my $target = "$RealBin/05_generate_readable_report.pl";

if (!-f $target) {
    die "Missing target script: $target\n";
}

exec $^X, $target, @ARGV or die "Failed to execute $target: $!\n";
