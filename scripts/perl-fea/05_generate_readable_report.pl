#!/usr/bin/env perl
use strict;
use warnings;

use FindBin qw($RealBin);
use File::Path qw(make_path);
use Getopt::Long qw(GetOptions);
use JSON::PP qw(decode_json);
use List::Util qw(max min sum);
use POSIX qw(strftime);

my $in_file  = "scripts/perl-fea/artifacts/perl-fea/runtime-inputs.json";
my $out_file = "scripts/perl-fea/artifacts/perl-fea/readable-report.md";
my $title    = "Bounded Reliability Readable Report";

GetOptions(
    "in=s"    => \$in_file,
    "out=s"   => \$out_file,
    "title=s" => \$title,
) or die "Usage: perl scripts/perl-fea/05_generate_readable_report.pl --in <runtime-inputs.json> --out <readable-report.md> --title <report-title>\n";

my $repo_root = "$RealBin/../..";
$in_file  = resolve_input_path($in_file, $RealBin, $repo_root);
$out_file = resolve_output_path($out_file, $repo_root);

my $doc = read_json_file($in_file);

my $metrics     = $doc->{metrics_real} || {};
my $reliability = $doc->{reliability} || {};
my $healing     = $doc->{healing_status} || {};
my $topology    = $doc->{topology_schema} || {};
my $nodes       = $metrics->{nodes} || [];
my $weak_edges  = $metrics->{weak_edges} || [];
my $trend       = $reliability->{trend} || {};
my $golden      = $metrics->{golden_signals} || {};

my $raw_sri     = to_num($metrics->{raw_sri});
my $bounded_sri = clamp01($raw_sri);

my @node_rows;
for my $n (@$nodes) {
    my $id      = $n->{id} // "unknown";
    my $lat_ms  = to_num($n->{latency});
    my $sat     = to_num($n->{saturation});
    my $err     = to_num($n->{error});
    my $traffic = to_num($n->{traffic});

    # Bounded FEA-inspired node scores with simple interpretable weighting.
    my $lat_norm  = clamp01($lat_ms / 200.0);
    my $func      = clamp01(1.0 - (0.70 * $err + 0.30 * $lat_norm));
    my $nonfunc   = clamp01(1.0 - (0.60 * $sat + 0.20 * $lat_norm + 0.20 * $err));
    my $composite = clamp01(0.55 * $func + 0.45 * $nonfunc);

    push @node_rows,
      {
        id         => $id,
        latency    => $lat_ms,
        saturation => $sat,
        error      => $err,
        traffic    => $traffic,
        functional => $func,
        nonfunc    => $nonfunc,
        composite  => $composite,
      };
}

my @latencies   = map { $_->{latency} } @node_rows;
my @saturations = map { $_->{saturation} } @node_rows;
my @errors      = map { $_->{error} } @node_rows;
my @composites  = map { $_->{composite} } @node_rows;

my $lat_stats  = stats(\@latencies);
my $sat_stats  = stats(\@saturations);
my $err_stats  = stats(\@errors);
my $cmp_stats  = stats(\@composites);
my $corr_table = analyze_corrections($healing->{correction_history} || []);

ensure_parent_dir($out_file);

my $now = strftime("%Y-%m-%d %H:%M:%S", localtime());
open my $out, ">", $out_file or die "Cannot write $out_file: $!";

print {$out} "# $title\n\n";
print {$out} "Generated: $now\n\n";

print {$out} "## 1) Executive Summary\n\n";
print {$out} "- Base URL: " . ($doc->{base_url} // "n/a") . "\n";
print {$out} "- Raw SRI: " . fmt($raw_sri, 6) . "\n";
print {$out} "- Bounded SRI [0,1]: " . fmt($bounded_sri, 6) . "\n";
print {$out} "- Reliability label: " . ($reliability->{label} // "n/a") . "\n";
print {$out} "- Reliability score: " . fmt(to_num($reliability->{score}), 4) . "\n";
print {$out} "- Trend: " . ($trend->{trend} // "n/a")
  . ", velocity=" . fmt(to_num($trend->{velocity}), 6)
  . ", acceleration=" . fmt(to_num($trend->{acceleration}), 6) . "\n";
print {$out} "- Total healing actions executed: "
  . (defined $healing->{total_actions_executed} ? $healing->{total_actions_executed} : "n/a") . "\n\n";

print {$out} "## 2) Bounded Node Models\n\n";
print {$out} "| Node | Traffic | Latency(ms) | Saturation | Error | Functional | NonFunctional | Composite |\n";
print {$out} "|---|---:|---:|---:|---:|---:|---:|---:|\n";
for my $r (@node_rows) {
    print {$out} "| $r->{id}"
      . " | " . fmt($r->{traffic}, 0)
      . " | " . fmt($r->{latency}, 3)
      . " | " . fmt($r->{saturation}, 4)
      . " | " . fmt($r->{error}, 6)
      . " | " . fmt($r->{functional}, 4)
      . " | " . fmt($r->{nonfunc}, 4)
      . " | " . fmt($r->{composite}, 4) . " |\n";
}
print {$out} "\n";

print {$out} "## 3) Statistical Model\n\n";
print {$out} "| Metric | Mean | Median | StdDev | Min | Max |\n";
print {$out} "|---|---:|---:|---:|---:|---:|\n";
print {$out} stat_row("Latency(ms)",  $lat_stats);
print {$out} stat_row("Saturation",   $sat_stats);
print {$out} stat_row("Error",        $err_stats);
print {$out} stat_row("CompositeRel", $cmp_stats);
print {$out} "\n";

print {$out} "## 4) Correction Factor Analysis\n\n";
if (@{$corr_table->{rows}}) {
    print {$out} "| Action | Signal | Samples | Avg Delta | Min Delta | Max Delta |\n";
    print {$out} "|---|---|---:|---:|---:|---:|\n";
    for my $row (@{$corr_table->{rows}}) {
        print {$out} "| $row->{action} | $row->{signal} | $row->{n}"
          . " | " . fmt($row->{avg}, 6)
          . " | " . fmt($row->{min}, 6)
          . " | " . fmt($row->{max}, 6) . " |\n";
    }
} else {
    print {$out} "No correction history found.\n";
}
print {$out} "\n";

print {$out} "## 5) Golden Signals Snapshot\n\n";
print {$out} "| Signal | Value | Threshold | Health |\n";
print {$out} "|---|---:|---:|---:|\n";
for my $k (qw(latency errors saturation traffic)) {
    my $g = $golden->{$k} || {};
    print {$out} "| $k"
      . " | " . fmt(to_num($g->{value}), 4)
      . " | " . fmt(to_num($g->{threshold}), 4)
      . " | " . fmt(to_num($g->{health}), 4) . " |\n";
}
print {$out} "\n";

print {$out} "## 6) Topology + Structural Indicators\n\n";
print {$out} "- Service count: " . safe_count($topology->{services}) . "\n";
print {$out} "- Component groups: " . safe_count_hash($topology->{components}) . "\n";
print {$out} "- Endpoint groups: " . safe_count_hash($topology->{endpoints}) . "\n";
print {$out} "- Inter-service edges: " . safe_count($topology->{inter_edges}) . "\n";
print {$out} "- Weak edges detected: " . scalar(@$weak_edges) . "\n";
if (@$weak_edges) {
    for my $e (@$weak_edges) {
        print {$out} "  - " . ($e->{source} // "?") . " -> " . ($e->{target} // "?") . "\n";
    }
}
print {$out} "\n";

print {$out} "## 7) Reliability Components\n\n";
my $comps = $reliability->{components} || {};
print {$out} "| Component | Value | Weight | Contribution |\n";
print {$out} "|---|---:|---:|---:|\n";
for my $name (sort keys %$comps) {
    my $c = $comps->{$name} || {};
    print {$out} "| $name"
      . " | " . fmt(to_num($c->{value}), 4)
      . " | " . fmt(to_num($c->{weight}), 4)
      . " | " . fmt(to_num($c->{contribution}), 4) . " |\n";
}
print {$out} "\n";

print {$out} "## 8) Notes\n\n";
print {$out} "- All bounded values are clamped to [0,1].\n";
print {$out} "- Functional and non-functional node models are heuristic and can be tuned.\n";
print {$out} "- Correction-factor analysis is derived from observed healing correction deltas.\n";

close $out;
print "Report generated: $out_file\n";
exit 0;

sub read_json_file {
    my ($path) = @_;
    open my $fh, "<", $path or die "Cannot open $path: $!";
    local $/;
    my $json = <$fh>;
    close $fh;
    my $obj = eval { decode_json($json) };
    die "Invalid JSON in $path: $@\n" if $@;
    return $obj;
}

sub ensure_parent_dir {
    my ($path) = @_;
    my $dir = $path;
    $dir =~ s{[/\\][^/\\]+$}{};
    return if $dir eq $path || $dir eq '';
    make_path($dir) if !-d $dir;
}

sub clamp01 {
    my ($x) = @_;
    $x = 0 if !defined $x;
    return 0 if $x < 0;
    return 1 if $x > 1;
    return $x;
}

sub to_num {
    my ($x) = @_;
    return 0 if !defined $x;
    return $x + 0;
}

sub fmt {
    my ($x, $d) = @_;
    $d = 4 if !defined $d;
    return sprintf("%.*f", $d, to_num($x));
}

sub median {
    my ($arr) = @_;
    return 0 unless @$arr;
    my @s = sort { $a <=> $b } @$arr;
    my $n = scalar @s;
    return $s[int($n / 2)] if $n % 2;
    return ($s[$n / 2 - 1] + $s[$n / 2]) / 2;
}

sub stats {
    my ($arr) = @_;
    return { mean => 0, median => 0, std => 0, min => 0, max => 0 } unless @$arr;

    my $n    = scalar @$arr;
    my $sumv = sum(@$arr);
    my $mean = $sumv / $n;
    my $med  = median($arr);
    my $mn   = min(@$arr);
    my $mx   = max(@$arr);

    my $var = 0;
    for my $v (@$arr) {
        $var += ($v - $mean) ** 2;
    }
    $var /= $n;

    return {
        mean   => $mean,
        median => $med,
        std    => sqrt($var),
        min    => $mn,
        max    => $mx,
    };
}

sub stat_row {
    my ($name, $s) = @_;
    return "| $name"
      . " | " . fmt($s->{mean}, 6)
      . " | " . fmt($s->{median}, 6)
      . " | " . fmt($s->{std}, 6)
      . " | " . fmt($s->{min}, 6)
      . " | " . fmt($s->{max}, 6) . " |\n";
}

sub analyze_corrections {
    my ($history) = @_;
    my %bucket;

    for my $h (@$history) {
        my $action = $h->{action_id} // "unknown_action";
        my $corr   = $h->{corrections} || {};
        for my $signal (keys %$corr) {
            my $delta = to_num($corr->{$signal}{delta});
            push @{$bucket{$action}{$signal}}, $delta;
        }
    }

    my @rows;
    for my $action (sort keys %bucket) {
        for my $signal (sort keys %{$bucket{$action}}) {
            my $vals = $bucket{$action}{$signal};
            my $n    = scalar @$vals;
            my $avg  = $n ? sum(@$vals) / $n : 0;
            push @rows,
              {
                action => $action,
                signal => $signal,
                n      => $n,
                avg    => $avg,
                min    => min(@$vals),
                max    => max(@$vals),
              };
        }
    }

    return { rows => \@rows };
}

sub safe_count {
    my ($arr) = @_;
    return 0 unless ref($arr) eq 'ARRAY';
    return scalar @$arr;
}

sub safe_count_hash {
    my ($h) = @_;
    return 0 unless ref($h) eq 'HASH';
    return scalar keys %$h;
}

sub resolve_input_path {
    my ($path, $script_dir, $repo_root) = @_;
    return $path if -f $path;

    my @candidates;
    push @candidates, "$repo_root/$path";
    push @candidates, "$script_dir/$path";

    if ($path =~ m{^scripts/perl-fea/(.+)$}) {
        my $tail = $1;
        push @candidates, "$script_dir/$tail";
    }

    for my $candidate (@candidates) {
        return $candidate if -f $candidate;
    }

    die "Cannot open $path: No such file or directory\n"
      . "Tried:\n"
      . join("\n", map { "- $_" } ($path, @candidates))
      . "\n";
}

sub resolve_output_path {
    my ($path, $repo_root) = @_;
    return $path if $path =~ m{^(?:[A-Za-z]:)?[/\\]};

    if ($path =~ m{^scripts/perl-fea/}) {
        return "$repo_root/$path";
    }

    return $path;
}
