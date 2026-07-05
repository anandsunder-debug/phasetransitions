#!/usr/bin/env perl
use strict;
use warnings;

use Getopt::Long qw(GetOptions);
use JSON::PP;
use File::Path qw(make_path);

my $out = 'artifacts/perl-fea/corrected-payloads.json';
my $examples = 'artifacts/perl-fea/corrected-curl-examples.sh';
my $base_url = 'http://localhost:8001';

GetOptions(
    'out=s' => \$out,
    'examples=s' => \$examples,
    'base-url=s' => \$base_url,
) or die "Invalid arguments\n";

my @corrections = (
    {
        endpoint => '/api/orders/buy-now',
        method => 'POST',
        failure_pattern => '422/400 from sending JSON body instead of query params',
        corrected => {
            query => {
                product_id => '<product_id>',
                quantity => 1,
            },
            body => undef,
        },
    },
    {
        endpoint => '/api/rum/beacon',
        method => 'POST',
        failure_pattern => '422 from deprecated keys: fcp_ms/lcp_ms/long_tasks/js_errors:number',
        corrected => {
            body => {
                session_id => 'load_rx',
                page => 'checkout',
                page_load_ms => 1800,
                first_contentful_paint_ms => 900,
                largest_contentful_paint_ms => 1800,
                long_tasks_count => 1,
                api_calls => [
                    {
                        path => '/api/orders',
                        duration_ms => 420,
                        status => 200,
                        error => JSON::PP::false,
                    },
                ],
                js_errors => [],
            },
        },
    },
    {
        endpoint => '/api/healing/path-to-stable/execute',
        method => 'POST',
        failure_pattern => '422 missing required node and wrong delay_seconds field',
        corrected => {
            body => {
                node => 'API',
                max_steps => 3,
                dry_run => JSON::PP::false,
            },
        },
    },
    {
        endpoint => '/api/healing/trigger',
        method => 'POST',
        failure_pattern => '422 when using node field; endpoint expects action_id',
        corrected => {
            body => {
                action_id => 'queue_drain',
            },
        },
    },
    {
        endpoint => '/api/healing/fault-propagation',
        method => 'POST',
        failure_pattern => '422 from source_node key mismatch',
        corrected => {
            body => {
                source => 'API',
                granularity => 'service',
                steps => 5,
                fault_strength => 0.6,
            },
        },
    },
    {
        endpoint => '/api/healing/auto-dampen-wave',
        method => 'POST',
        failure_pattern => '422 missing required source',
        corrected => {
            body => {
                source => 'API',
                granularity => 'service',
                steps => 6,
                fault_strength => 0.7,
                critical_arrival_threshold => 0.3,
                auto_execute => JSON::PP::false,
            },
        },
    },
    {
        endpoint => '/api/healing/optimize-sequence',
        method => 'POST',
        failure_pattern => '422 from max_steps-only payload; requires stressed_nodes',
        corrected => {
            body => {
                stressed_nodes => [
                    { node => 'API', pressure => 0.82, yield_exceeded => JSON::PP::true },
                    { node => 'DB', pressure => 0.73, yield_exceeded => JSON::PP::true },
                ],
                source => 'API',
                granularity => 'service',
            },
        },
    },
    {
        endpoint => '/api/healing/execute-sequence',
        method => 'POST',
        failure_pattern => '422 from using delay_seconds instead of delay_ms',
        corrected => {
            body => {
                sequence => [
                    {
                        action_id => 'queue_drain',
                        target_node => 'API',
                    },
                ],
                delay_ms => 0,
            },
        },
    },
    {
        endpoint => '/api/metrics/simulate',
        method => 'POST',
        failure_pattern => '422 from unsupported scenario/duration_seconds fields',
        corrected => {
            body => {
                traffic_scale => 1200,
                latency_scale => 90,
                error_rate => 0.12,
                saturation => 0.6,
                failure_mode => 'Latency Spike',
            },
        },
    },
);

my $doc = {
    generated_at => scalar gmtime(),
    base_url => $base_url,
    corrected_payloads => \@corrections,
};

for my $target ($out, $examples) {
    my ($dir) = ($target =~ m{^(.*)[/\\][^/\\]+$});
    if (defined $dir && length $dir) {
        make_path($dir) if !-d $dir;
    }
}

my $json = JSON::PP->new->utf8->canonical->pretty;
open my $fh, '>', $out or die "Failed to write $out: $!\n";
print {$fh} $json->encode($doc);
close $fh;

open my $sh, '>', $examples or die "Failed to write $examples: $!\n";
print {$sh} "#!/usr/bin/env bash\n";
print {$sh} "set -euo pipefail\n\n";
print {$sh} "BASE_URL=\"$base_url\"\n";
print {$sh} "COOKIE=\"\${1:-cookie.txt}\"\n\n";
print {$sh} "curl -s -X POST \"\$BASE_URL/api/orders/buy-now?product_id=<product_id>&quantity=1\" -b \"\$COOKIE\" -c \"\$COOKIE\"\n\n";
print {$sh} "curl -s -X POST \"\$BASE_URL/api/rum/beacon\" -b \"\$COOKIE\" -c \"\$COOKIE\" -H \"Content-Type: application/json\" -d '{\"session_id\":\"load_rx\",\"page\":\"checkout\",\"page_load_ms\":1800,\"first_contentful_paint_ms\":900,\"largest_contentful_paint_ms\":1800,\"long_tasks_count\":1,\"api_calls\":[{\"path\":\"/api/orders\",\"duration_ms\":420,\"status\":200,\"error\":false}],\"js_errors\":[]}'\n\n";
print {$sh} "curl -s -X POST \"\$BASE_URL/api/healing/path-to-stable/execute\" -b \"\$COOKIE\" -c \"\$COOKIE\" -H \"Content-Type: application/json\" -d '{\"node\":\"API\",\"max_steps\":3,\"dry_run\":false}'\n\n";
print {$sh} "curl -s -X POST \"\$BASE_URL/api/healing/fault-propagation\" -b \"\$COOKIE\" -c \"\$COOKIE\" -H \"Content-Type: application/json\" -d '{\"source\":\"API\",\"granularity\":\"service\",\"steps\":5,\"fault_strength\":0.6}'\n\n";
print {$sh} "curl -s -X POST \"\$BASE_URL/api/healing/optimize-sequence\" -b \"\$COOKIE\" -c \"\$COOKIE\" -H \"Content-Type: application/json\" -d '{\"stressed_nodes\":[{\"node\":\"API\",\"pressure\":0.82,\"yield_exceeded\":true},{\"node\":\"DB\",\"pressure\":0.73,\"yield_exceeded\":true}],\"source\":\"API\",\"granularity\":\"service\"}'\n";
close $sh;

print "Wrote corrected payload catalog to $out\n";
print "Wrote curl examples to $examples\n";
