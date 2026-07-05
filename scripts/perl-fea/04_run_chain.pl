#!/usr/bin/env perl
use strict;
use warnings;

use Getopt::Long qw(GetOptions);
use File::Basename qw(dirname);
use File::Spec;
use File::Path qw(make_path);

my $base_url = 'http://localhost:8001';
my $report = 'report.json';
my $out_dir = 'artifacts/perl-fea';

GetOptions(
    'base-url=s' => \$base_url,
    'report=s' => \$report,
    'out-dir=s' => \$out_dir,
) or die "Invalid arguments\n";

make_path($out_dir) if !-d $out_dir;

my $self_dir = dirname(__FILE__);
my $step1 = File::Spec->catfile($self_dir, '01_collect_inputs.pl');
my $step2 = File::Spec->catfile($self_dir, '02_build_bounded_fea_model.pl');
my $step3 = File::Spec->catfile($self_dir, '03_correct_failing_payloads.pl');

my $inputs_out = File::Spec->catfile($out_dir, 'runtime-inputs.json');
my $model_out = File::Spec->catfile($out_dir, 'bounded-fea-model.json');
my $payloads_out = File::Spec->catfile($out_dir, 'corrected-payloads.json');
my $examples_out = File::Spec->catfile($out_dir, 'corrected-curl-examples.sh');

sub run_step {
    my (@cmd) = @_;
    my $rc = system(@cmd);
    if ($rc != 0) {
        die "Step failed: @cmd\n";
    }
}

run_step($^X, $step1,
    '--base-url', $base_url,
    '--report', $report,
    '--out', $inputs_out,
);

run_step($^X, $step2,
    '--in', $inputs_out,
    '--out', $model_out,
);

run_step($^X, $step3,
    '--base-url', $base_url,
    '--out', $payloads_out,
    '--examples', $examples_out,
);

print "Perl FEA chain complete\n";
print " - inputs:   $inputs_out\n";
print " - model:    $model_out\n";
print " - payloads: $payloads_out\n";
print " - examples: $examples_out\n";
