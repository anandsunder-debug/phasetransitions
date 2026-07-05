#!/usr/bin/env perl
use strict;
use warnings;

use Getopt::Long qw(GetOptions);
use JSON::PP;
use File::Path qw(make_path);

my $in = 'artifacts/perl-fea/runtime-inputs.json';
my $out = 'artifacts/perl-fea/bounded-fea-model.json';

GetOptions(
    'in=s' => \$in,
    'out=s' => \$out,
) or die "Invalid arguments\n";

sub clamp {
    my ($v, $lo, $hi) = @_;
    $v = $lo if $v < $lo;
    $v = $hi if $v > $hi;
    return $v;
}

sub average {
    my (@vals) = @_;
    return 0 if !@vals;
    my $sum = 0;
    $sum += $_ for @vals;
    return $sum / scalar @vals;
}

sub read_json_file {
    my ($path) = @_;
    open my $fh, '<', $path or die "Failed to read $path: $!\n";
    local $/ = undef;
    my $raw = <$fh>;
    close $fh;
    my $decoded = eval { JSON::PP::decode_json($raw) };
    die "Invalid JSON in $path\n" if !$decoded;
    return $decoded;
}

my $data = read_json_file($in);
my $topology = $data->{topology_schema} // {};
my $metrics_real = $data->{metrics_real} // {};
my $reliability = $data->{reliability} // {};

my @services = map { ref($_) eq 'HASH' ? ($_->{name} // ()) : () } @{ $topology->{services} // [] };

my %node_metrics = ();
for my $n (@{ $metrics_real->{nodes} // [] }) {
    next if ref($n) ne 'HASH';
    my $id = $n->{id};
    next if !defined $id || $id eq '';
    $node_metrics{$id} = $n;
}

if (!@services) {
    @services = sort keys %node_metrics;
}

my @edges = @{ $topology->{inter_edges} // [] };
if (!@edges) {
    @edges = (
        ['Frontend', 'API'],
        ['API', 'Cache'],
        ['API', 'DB'],
        ['API', 'Queue'],
        ['Queue', 'Backend'],
        ['Cache', 'DB'],
    );
}

my %node_scores = ();
for my $node (@services) {
    my $m = $node_metrics{$node} // {};
    my $error = clamp(0 + ($m->{error} // 0), 0, 1);
    my $sat = clamp(0 + ($m->{saturation} // 0), 0, 1);
    my $lat = 0 + ($m->{latency} // 0);
    my $lat_ms = $lat > 10 ? $lat : ($lat * 1000);
    my $lat_norm = clamp($lat_ms / 2500, 0, 1);

    my $functional = clamp(1 - (0.75 * $error + 0.25 * $sat), 0, 1);
    my $nonfunctional = clamp(1 - (0.70 * $lat_norm + 0.30 * $sat), 0, 1);
    my $overall = clamp(0.55 * $functional + 0.45 * $nonfunctional, 0, 1);

    $node_scores{$node} = {
        functional => sprintf('%.6f', $functional) + 0,
        nonfunctional => sprintf('%.6f', $nonfunctional) + 0,
        overall => sprintf('%.6f', $overall) + 0,
        observed => {
            latency_ms => sprintf('%.3f', $lat_ms) + 0,
            error_rate => sprintf('%.6f', $error) + 0,
            saturation => sprintf('%.6f', $sat) + 0,
        },
    };
}

my $energy = 0;
my $energy_bound = 0;
my @edge_terms = ();

for my $e (@edges) {
    next if ref($e) ne 'ARRAY' || scalar(@$e) < 2;
    my ($a, $b) = ($e->[0], $e->[1]);
    next if !exists $node_scores{$a} || !exists $node_scores{$b};

    my $da = 1 - $node_scores{$a}->{overall};
    my $db = 1 - $node_scores{$b}->{overall};
    my $stiffness = clamp(($node_scores{$a}->{overall} + $node_scores{$b}->{overall}) / 2, 0.05, 1.0);
    my $term = $stiffness * (($da - $db) ** 2);

    $energy += $term;
    $energy_bound += $stiffness;

    push @edge_terms, {
        source => $a,
        target => $b,
        stiffness => sprintf('%.6f', $stiffness) + 0,
        strain_term => sprintf('%.6f', $term) + 0,
    };
}

$energy_bound = 1 if $energy_bound <= 0;
my $fea_reliability = clamp(1 - ($energy / $energy_bound), 0, 1);

my @functional_nodes = map { $node_scores{$_}->{functional} } @services;
my @nonfunctional_nodes = map { $node_scores{$_}->{nonfunctional} } @services;

my $functional_system = clamp(average(@functional_nodes), 0, 1);
my $nonfunctional_system = clamp(average(@nonfunctional_nodes), 0, 1);
my $composite = clamp(
    0.45 * $functional_system +
    0.45 * $nonfunctional_system +
    0.10 * $fea_reliability,
    0,
    1,
);

my $label =
    $composite >= 0.95 ? 'excellent' :
    $composite >= 0.85 ? 'strong' :
    $composite >= 0.70 ? 'degrading' :
    'critical';

my $model = {
    generated_at => scalar gmtime(),
    bounds => {
        node_reliability => [0, 1],
        edge_stiffness => [0.05, 1],
        functional_reliability => [0, 1],
        nonfunctional_reliability => [0, 1],
        composite_reliability => [0, 1],
    },
    inputs => {
        node_count => scalar @services,
        edge_count => scalar @edge_terms,
        reliability_endpoint_score => $reliability->{score},
        reliability_endpoint_label => $reliability->{label},
    },
    node_scores => \%node_scores,
    fea_terms => {
        energy => sprintf('%.6f', $energy) + 0,
        energy_bound => sprintf('%.6f', $energy_bound) + 0,
        edge_terms => \@edge_terms,
        fea_reliability => sprintf('%.6f', $fea_reliability) + 0,
    },
    system_reliability => {
        functional => sprintf('%.6f', $functional_system) + 0,
        nonfunctional => sprintf('%.6f', $nonfunctional_system) + 0,
        composite => sprintf('%.6f', $composite) + 0,
        label => $label,
    },
};

my ($dir) = ($out =~ m{^(.*)[/\\][^/\\]+$});
if (defined $dir && length $dir) {
    make_path($dir) if !-d $dir;
}

my $json = JSON::PP->new->utf8->canonical->pretty;
open my $fh, '>', $out or die "Failed to write $out: $!\n";
print {$fh} $json->encode($model);
close $fh;

print "Wrote bounded FEA model to $out\n";
