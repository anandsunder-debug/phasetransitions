# Bounded Reliability Readable Report

Generated: 2026-07-04 17:55:20

## 1) Executive Summary

- Base URL: http://localhost:8001
- Raw SRI: 0.992455
- Bounded SRI [0,1]: 0.992455
- Reliability label: excellent
- Reliability score: 0.9610
- Trend: stable, velocity=0.000016, acceleration=0.000000
- Total healing actions executed: 363

## 2) Bounded Node Models

| Node | Traffic | Latency(ms) | Saturation | Error | Functional | NonFunctional | Composite |
|---|---:|---:|---:|---:|---:|---:|---:|
| API | 172 | 26.216 | 1.0000 | 0.000000 | 0.9607 | 0.3738 | 0.6966 |
| Cache | 20 | 1.332 | 0.1081 | 0.000000 | 0.9980 | 0.9338 | 0.9691 |
| DB | 1 | 3.627 | 0.0100 | 0.000000 | 0.9946 | 0.9904 | 0.9927 |
| Queue | 30 | 2.554 | 0.3000 | 0.000000 | 0.9962 | 0.8174 | 0.9157 |
| Backend | 152 | 4.662 | 1.0000 | 0.006579 | 0.9884 | 0.3940 | 0.7209 |
| Frontend | 104 | 63.503 | 1.0000 | 0.000000 | 0.9047 | 0.3365 | 0.6490 |

## 3) Statistical Model

| Metric | Mean | Median | StdDev | Min | Max |
|---|---:|---:|---:|---:|---:|
| Latency(ms) | 16.982492 | 4.144623 | 22.482302 | 1.331578 | 63.503224 |
| Saturation | 0.569685 | 0.650000 | 0.438662 | 0.010000 | 1.000000 |
| Error | 0.001096 | 0.000000 | 0.002452 | 0.000000 | 0.006579 |
| CompositeRel | 0.824012 | 0.818337 | 0.138684 | 0.649033 | 0.992676 |

## 4) Correction Factor Analysis

| Action | Signal | Samples | Avg Delta | Min Delta | Max Delta |
|---|---|---:|---:|---:|---:|
| queue_drain | errors | 7 | 0.000357 | -0.006400 | 0.008900 |
| queue_drain | latency | 7 | 0.000557 | 0.000300 | 0.000800 |
| queue_drain | saturation | 7 | 0.060014 | 0.001700 | 0.091600 |
| queue_drain | traffic | 7 | 0.000000 | 0.000000 | 0.000000 |
| scale_out_cache_node | errors | 2 | -0.009100 | -0.018200 | 0.000000 |
| scale_out_cache_node | latency | 2 | 0.001050 | 0.001000 | 0.001100 |
| scale_out_cache_node | saturation | 2 | 0.066300 | 0.038400 | 0.094200 |
| scale_out_cache_node | traffic | 2 | 0.000000 | 0.000000 | 0.000000 |
| scale_out_db_read_replica | errors | 1 | 0.000000 | 0.000000 | 0.000000 |
| scale_out_db_read_replica | latency | 1 | 0.001300 | 0.001300 | 0.001300 |
| scale_out_db_read_replica | saturation | 1 | 0.000600 | 0.000600 | 0.000600 |
| scale_out_db_read_replica | traffic | 1 | 0.000000 | 0.000000 | 0.000000 |

## 5) Golden Signals Snapshot

| Signal | Value | Threshold | Health |
|---|---:|---:|---:|
| latency | 16.9800 | 200.0000 | 0.9660 |
| errors | 0.1100 | 10.0000 | 0.9945 |
| saturation | 56.9700 | 80.0000 | 0.4303 |
| traffic | 479.0000 | 20.0000 | 1.0000 |

## 6) Topology + Structural Indicators

- Service count: 6
- Component groups: 6
- Endpoint groups: 46
- Inter-service edges: 8
- Weak edges detected: 1
  - API -> Queue

## 7) Reliability Components

| Component | Value | Weight | Contribution |
|---|---:|---:|---:|
| availability | 0.9929 | 0.2500 | 0.2482 |
| conversion_health | 0.9771 | 0.2500 | 0.2443 |
| customer_apdex | 0.8999 | 0.3000 | 0.2700 |
| resilience_sri | 0.9924 | 0.2000 | 0.1985 |

## 8) Notes

- All bounded values are clamped to [0,1].
- Functional and non-functional node models are heuristic and can be tuned.
- Correction-factor analysis is derived from observed healing correction deltas.
