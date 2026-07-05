# SPECTRAL RESILIENCE INDEX (SRI)
## A Novel Graph-Theoretic Approach to Infrastructure Health Monitoring with Finite Element Analysis and Adaptive Autonomous Remediation

---

**Author:** Anand Sunder
**Affiliation:** Capgemini Technology Services, Hyderabad, India
**Classification:** Proprietary & Confidential
**Document Type:** Technical Whitepaper
**Version:** 2.3
**Date:** February 2026
**Status:** Pre-Publication Draft — All Rights Reserved

**Changelog**
- **2.3 (Feb 2026)** — added §6.2 *Three-Tier Topology Granularity* (services → components → endpoints, with 6 / 46 / 101 nodes and 8 / 84 / 139 edges) and §12.5 *Aggressive / Reliability-Aware Auto-Healing* (proactive 5-s loop with multi-objective action scoring `0.30·ΔSRI + 0.30·ΔApdex + 0.20·ΔAvail + 0.15·ΔConv − 0.05·cost`). Tier-3 dampening for `auto-dampen-wave` confirmed.
- **2.2 (Feb 2026)** — added §6.1 *Distributed Deployment Topology*: the reference implementation is now split into two FastAPI microservices (main app + observability) coordinated via fire-and-forget event emission and synchronous proxy reads. Every analytical formulation in this paper is invariant to the split; only the runtime locus of computation changes.
- **2.1** — added §7.4 *Browser/Frontend as a First-Class Topology Node*; expanded §7B–§7H with strict-FEA terminology, propagation, auto-dampener, sequence optimizer, CX layer, and non-recoverable state detection.

---

> **NOTICE:** This document describes proprietary methodology, algorithms, and system architecture developed by the author. The concepts, formulations, and composite system design herein constitute original intellectual property. No part of this document may be reproduced, distributed, or used to create derivative works without explicit written permission from the author.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Prior Art & Limitations](#3-prior-art--limitations)
4. [Novel Contribution](#4-novel-contribution)
5. [Theoretical Foundation](#5-theoretical-foundation)
6. [System Overview](#6-system-overview)
   - 6.1. [Distributed Deployment Topology](#61-distributed-deployment-topology)
   - 6.2. [Three-Tier Topology Granularity](#62-three-tier-topology-granularity)
7. [SRI — Spectral Resilience Index](#7-sri--spectral-resilience-index)
   - 7.4. [Browser/Frontend as a First-Class Topology Node](#74-browserfrontend-as-a-first-class-topology-node)
7B. [Strict-FEA Engine on the Service Mesh](#7b-strict-fea-engine-on-the-service-mesh)
7C. [Failure Propagation Simulator](#7c-failure-propagation-simulator)
7D. [Auto-Dampener — Wave-Arresting Cut Edges](#7d-auto-dampener--wave-arresting-cut-edges)
7E. [Auto-Propagation Detection + Path-Based Autonomous Healing](#7e-auto-propagation-detection--path-based-autonomous-healing)
7F. [Healing Sequence Optimizer](#7f-healing-sequence-optimizer)
7G. [Customer Experience Layer](#7g-customer-experience-layer)
7H. [Non-Recoverable State Detection](#7h-non-recoverable-state-detection)
8. [Finite Element Analysis (FEA) Engine](#8-finite-element-analysis-fea-engine)
9. [SRI Polynomial Interpolation](#9-sri-polynomial-interpolation)
10. [Golden Signal Integration](#10-golden-signal-integration)
11. [Customer Experience Layer](#11-customer-experience-layer)
12. [Adaptive Autonomous Remediation Engine](#12-adaptive-autonomous-remediation-engine)
    - 12.6. [Aggressive / Reliability-Aware Mode (v3)](#126-aggressive--reliability-aware-mode-v3-iter-22)
    - 12.7. [Ladder Synthesizer — Programs Writing Programs (v4)](#127-ladder-synthesizer--programs-writing-programs-v4-iter-30)
    - 12.8. [Operational Phase Classifier (v5) + Iron-Carbide-Style Diagram](#128-operational-phase-classifier-v5-iter-31)
    - 12.9. [RUM Ladder Learner — Reliability from User-Felt Outcomes (v6)](#129-rum-ladder-learner--reliability-from-user-felt-outcomes-v6-iter-32)
13. [Escalation Ladders & Cross-Node Healing](#13-escalation-ladders--cross-node-healing)
    - 13.4. [Scaling Actions (v7, iter 33)](#134-scaling-actions-v7-iter-33)
13. [Escalation Ladders & Cross-Node Healing](#13-escalation-ladders--cross-node-healing)
14. [Healing Stagnation Detection](#14-healing-stagnation-detection)
15. [Correction Factor Model](#15-correction-factor-model)
16. [Closed-Loop Architecture](#16-closed-loop-architecture)
17. [Baseline Calibration](#17-baseline-calibration)
18. [Results & Observations](#18-results--observations)
19. [Comparison with Existing Solutions](#19-comparison-with-existing-solutions)
20. [Applications & Extensibility](#20-applications--extensibility)
21. [Conclusion](#21-conclusion)
22. [Intellectual Property Notice](#22-intellectual-property-notice)
23. [References](#23-references)

---

## 1. Executive Summary

Modern distributed systems are monitored through isolated metrics — CPU usage, error rates, latency percentiles — that fail to capture the **systemic interdependencies** between infrastructure components. A database slowdown doesn't just affect queries; it cascades through caches, queues, and API layers in ways that per-component monitoring cannot predict or quantify.

This paper introduces the **Spectral Resilience Index (SRI)**, a composite health metric derived from **spectral graph theory** that models an infrastructure topology as a weighted graph and quantifies its resilience through the algebraic connectivity of its Laplacian matrix. Unlike threshold-based alerting, SRI captures emergent degradation patterns across the entire service mesh before individual component metrics breach their thresholds.

The paper further describes three major advances beyond the original SRI formulation:

1. **Finite Element Analysis (FEA)** — treating the system graph as a structural mesh to compute strain energy and Von-Mises stress per node, identifying components under mechanical "yield" that require corrective action

2. **SRI Polynomial Interpolation** — fitting a quadratic polynomial to the SRI time series to compute velocity (dSRI/dt), acceleration (d2SRI/dt2), and predicted future values, enabling proactive healing before degradation reaches critical levels

3. **Adaptive Self-Learning Remediation** — a healing engine that tracks per-action effectiveness, detects healing stagnation (actions producing zero improvement), automatically escalates through action ladders per node, and falls back to cross-node healing via graph adjacency — solving the fundamental problem of naive auto-healing that repeats ineffective actions indefinitely

This composite system represents the first **closed-loop spectral-structural observability platform** with self-learning autonomous remediation.

---

## 2. Problem Statement

Infrastructure monitoring today operates in silos:

- **Metric tools** (Prometheus, Datadog) collect per-component telemetry but require humans to correlate signals across services
- **Alerting systems** (PagerDuty, OpsGenie) fire on threshold breaches but cannot distinguish between isolated incidents and systemic degradation
- **Auto-scaling** (Kubernetes HPA, AWS Auto Scaling) responds to individual resource metrics but doesn't account for cross-service dependencies
- **AIOps platforms** use statistical anomaly detection but lack a theoretical framework for quantifying **system-level connectivity**

The fundamental gap: **no existing approach models the infrastructure as an interconnected system and derives a mathematically grounded, single metric that captures its holistic resilience.**

Furthermore, when remediation is attempted, there is no standardized way to measure **how effectively** a corrective action improved each dimension of system health.

---

## 3. Prior Art & Limitations

### 3.1 Google SRE Golden Signals (2016)

Betsy Beyer et al. established four key signals for monitoring: Latency, Traffic, Errors, and Saturation [1]. This framework is widely adopted but:
- Signals are monitored independently
- No composite index is derived
- No formal model for how signals interact across service boundaries
- Remediation is manual and human-driven

### 3.2 Apdex Standard (2005)

The Application Performance Index [2] quantifies user satisfaction as a ratio of satisfactory to total requests. Limitations:
- Single-dimensional (latency-only)
- No infrastructure awareness
- No remediation capability

### 3.3 Spectral Graph Theory in Network Science

Earlier research by scholars like Fan Chung (1997) [4] and Miroslav Fiedler (1973) [3] established that eigenvalues of a Laplacian matrix relate to a graph's "robustness". However, these studies were largely theoretical or focused on physical infrastructure (e.g., power grids). Sunder's contribution was the specific mapping of software telemetry (latency, throughput, error rates) to these spectral properties, creating a standardized "Index" for real-time Site Reliability Engineering (SRE).

Key gaps that remained prior to this work:
- Spectral properties were not applied to infrastructure monitoring in production software systems
- No prior work connects Laplacian eigenvalues to SRE golden signals (latency, traffic, errors, saturation)
- No feedback loop from spectral analysis to automated remediation existed
- The theoretical relationship between algebraic connectivity and system resilience was not operationalized into a deployable metric

### 3.6 Foundational Work: The Spectral Resilience Index

The term **Spectral Resilience Index (SRI)** and its formal definition as a metric for distributed software systems was first introduced by Anand Sunder in the peer-reviewed publication:

> Sunder, A. (2025). "Spectral Signatures of Distributed Software Systems: Eigenvalue Profiling for Enterprise-Scale Proactive Resilience Engineering." *Asian Journal of Mathematical Sciences (AJMS)*, Vol. 9, No. 03. DOI: [10.22377/ajms.v9i03.618](https://doi.org/10.22377/ajms.v9i03.618)

In that work [10], Sunder develops a rigorous spectral framework for profiling distributed software systems at enterprise scale. The paper:

1. Represents a distributed system as a discretized assemblage of computational elements and constructs complexity-aware stiffness and mass matrices
2. Performs spectral decomposition of the resulting generalized eigenproblem to extract **spectral signatures** — normalized sets of eigenvalues and derived statistics that characterize system resilience, bottlenecks, and failure propagation dynamics
3. Formally defines the **Spectral Resilience Index (SRI)** as a quantitative metric derived from these spectral signatures
4. Introduces vertical-grade functions for different enterprise domains (finance, healthcare, retail, telecommunications)
5. Overlays a Hidden Markov Model (HMM) that maps observed telemetry to latent resilience states, refining deterministic spectral predictions
6. Validates the methodology using public datasets (DORA metrics, Death Star Bench traces, and Google SRE reports)

The present whitepaper builds upon Sunder's foundational SRI formulation by extending it with:
- A physical model of software systems (flow dynamics, energy functional, stability conditions)
- Finite Element Analysis for per-service stress quantification
- Polynomial interpolation for predictive trend analysis
- An adaptive self-learning remediation engine with multi-objective optimization
- Real-time deployment in a production e-commerce platform with business outcome correlation

### 3.4 Chaos Engineering (Netflix, 2011)

Chaos Monkey and related tools [5] inject failures to test resilience but:
- Destructive by nature (inject faults, observe)
- No continuous health metric
- No autonomous remediation — purely observational

### 3.5 AIOps Platforms (Moogsoft, BigPanda)

Machine learning for alert correlation and noise reduction. Limitations:
- Black-box models with limited explainability
- Require large training datasets
- No graph-theoretic foundation
- Correlation ≠ causation in their signal grouping

---

## 4. Novel Contribution

This work introduces the following original contributions:

| # | Contribution | Novelty |
|---|-------------|---------|
| 1 | **Spectral Resilience Index** | First application of Laplacian algebraic connectivity (lambda_2/lambda_max) as a real-time infrastructure health metric |
| 2 | **Fiedler Vector Bottleneck Detection** | Using the eigenvector of lambda_2 to identify weak edges in production infrastructure |
| 3 | **Finite Element Analysis of Service Graphs** | Novel application of structural mechanics (stiffness matrix, load vector, pseudo-inverse displacement, Von-Mises stress) to identify yielding infrastructure components |
| 4 | **SRI Polynomial Interpolation** | Quadratic polyfit over SRI time series for velocity, acceleration, and predictive trend classification |
| 5 | **Adaptive Self-Learning Action Selector** | Effectiveness tracking with stagnation detection, escalation ladders, and cross-node healing via graph adjacency |
| 6 | **Signal-Aware Precision Healing** | Matching corrective actions to dominant failing signal via affinity scoring (not just node targeting) |
| 7 | **Business Reliability Model** | Formal composite: SRI + Apdex + Availability + Conversion Health, connecting infrastructure resilience to business outcomes |
| 8 | **SRI Attribution Engine** | Per-node per-signal decomposition of SRI dips mapped to business metric impact (conversion/apdex/revenue) |
| 9 | **Healing Dampeners** | Persistent post-CA metric improvement via future-request dampening (models real infra improvement) |
| 10 | **Multi-CA Simultaneous Execution** | FEA-driven parallel corrective actions at all yield-exceeded nodes based on trend severity |
| 11 | **Golden Signal Decomposition of SRI** | Weighted mapping from 4 golden signals to graph edge weights |
| 12 | **Correction Factor Model** | Quantitative measure of per-signal remediation effectiveness |
| 13 | **Alert-to-Heal Closed Loop with Feedback** | Complete autonomous cycle: metric -> spectral + FEA analysis -> RCA -> adaptive action selection -> correction measurement -> feedback |
| 14 | **Healing Stagnation Detection** | Formal identification of diminishing returns zones where repeated actions have no marginal benefit |
| 15 | **Baseline Calibration via Warmup Blending** | Addressing the cold-start problem through progressive blending |

The composition of these elements into a single, deployable system is the core intellectual property described herein.

---

## 5. Theoretical Foundation

### 5.1 Graph Representation

An infrastructure topology is modeled as a weighted undirected graph **G = (V, E, W)** where:
- **V** = set of infrastructure nodes (services, databases, caches, queues, etc.)
- **E** = set of edges representing communication/dependency paths between nodes
- **W: E → ℝ⁺** = edge weight function derived from operational telemetry

### 5.2 Edge Weight Derivation

Edge weights encode the **health of the link between two nodes**. The weight function incorporates multiple operational dimensions — traffic volume, response quality, capacity utilization, and reliability — into a single scalar that increases when the link is performing well and decreases under degradation.

The specific formulation is proprietary, but the key properties are:
- **Monotonically increasing** with throughput quality
- **Monotonically decreasing** with error rates and saturation
- **Bounded below** by a positive minimum to maintain graph connectivity
- **Derived from real-time telemetry**, not static configuration

### 5.3 Laplacian Matrix

The **graph Laplacian** L is constructed from the weighted adjacency matrix. The Laplacian is a well-studied object in spectral graph theory with known properties [3][4]:
- L is symmetric and positive semi-definite
- The smallest eigenvalue is always 0 (connected to the all-ones vector)
- The second-smallest eigenvalue **λ₂** is the **algebraic connectivity** (Fiedler value)

### 5.4 Algebraic Connectivity as Resilience

The Fiedler value λ₂ has a precise physical interpretation: it measures **how well-connected the graph is** — how difficult it is to partition into disconnected components. In our context:
- **High λ₂** → all service links are healthy, the system is resilient
- **Low λ₂** → some links are degraded, the system is fragile and approaching partition
- **λ₂ = 0** → the graph is disconnected (complete system failure)

### 5.5 SRI Definition

The Spectral Resilience Index normalizes the Fiedler value against the maximum eigenvalue to produce a scale-invariant metric in [0, 1]:

```
SRI = λ₂ / λ_max
```

This normalization ensures SRI is comparable across systems of different sizes and topologies.

### 5.6 Fiedler Vector for Bottleneck Identification

The **eigenvector** corresponding to λ₂ (the Fiedler vector) partitions the graph into two groups. Edges where the Fiedler vector components differ most are the **weakest links** — the edges whose removal would most reduce connectivity. This directly identifies which service-to-service links are degraded.

---

## 6. System Overview

The complete system operates as a continuous feedback loop with four layers:

```
Layer 1: TELEMETRY
    Per-request metrics collection across all service nodes
    ↓
Layer 2: ANALYSIS
    Spectral decomposition → SRI + Fiedler vector
    Golden signal computation → per-signal health
    Customer experience aggregation → Apdex, percentiles, error budget
    ↓
Layer 3: DETECTION & ALERTING
    Threshold evaluation against SRI and individual signals
    Real-time alert broadcast to operators and remediation engine
    ↓
Layer 4: REMEDIATION & FEEDBACK
    Alert-to-action mapping → targeted corrective action
    Before/after golden signal capture → Correction Factor computation
    SRI re-computation → feedback into Layer 2
```

Each layer operates in real-time with sub-second latency.

---

### 6.1 Distributed Deployment Topology

The reference implementation deploys the four analytical layers across **two coordinated FastAPI microservices** in the same pod, sharing one MongoDB. This separation is *operational*, not *theoretical*: every equation in §5 and §7–§9 is invariant under the split. What changes is the **runtime locus** of each computation and the **boundary of trust** between business-critical request handling and observability inference.

#### 6.1.1 Service Decomposition

```
┌───────────────────────────────────────────────────────────────────┐
│                       FRONTEND (browser)                           │
│                  REACT_APP_BACKEND_URL → :8001                     │
└───────────────────────────────┬───────────────────────────────────┘
                                │
                ┌───────────────▼──────────────┐
                │  Main App  (server.py, :8001) │
                │  ───────────────────────────  │
                │   • Auth, products, cart,     │
                │     orders, admin             │
                │   • Event-Emit Middleware     │  fire-and-forget
                │     (async telemetry)         │  ───────────►
                │   • Observability Proxy       │  synchronous
                │     (httpx.AsyncClient)       │  ◄───────────►
                │   • /ws/alerts bridge         │
                └───────────────┬──────────────┘
                                │ localhost
                ┌───────────────▼─────────────────┐
                │ Observability Service           │
                │ (obs_server.py, :8002, internal)│
                │ ─────────────────────────────── │
                │   Layer 2 Analysis (§7–§9):     │
                │     SRI, FEA, polyfit interp.   │
                │   Layer 3 Detection (§14):      │
                │     thresholds, attribution     │
                │   Layer 4 Remediation (§12–13): │
                │     healing engine, sequence    │
                │     optimizer, auto-dampener    │
                │   Background loops:             │
                │     auto-heal (7s),             │
                │     auto-propagation (8s)       │
                │   /api/internal/events/*        │
                │     receivers (Layer 1 sink)    │
                └───────────────┬─────────────────┘
                                │
                       ┌────────▼────────┐
                       │    MongoDB      │  (shared, persistent)
                       └─────────────────┘
```

#### 6.1.2 Inter-Service Coordination

Two transport patterns are used, each chosen to preserve a specific invariant:

| Pattern | Direction | Purpose | Failure Mode |
|---------|-----------|---------|--------------|
| **Fire-and-forget HTTP POST** | main_app → obs | Telemetry emission: every request (`/api/internal/events/request` with `{path, method, latency, is_error}`) and every business event (`/api/internal/events/business` with `{event_type, value}`). Wrapped in `asyncio.create_task(httpx.post(...))` with all exceptions swallowed. | If obs is unreachable, no request handler ever blocks or fails. Telemetry samples are dropped; the storefront keeps serving. |
| **Synchronous HTTP proxy** | obs → main_app (response path) | Read endpoints (`/api/metrics/*`, `/api/healing/*`, `/api/cx/*`, `/api/rum/*`, `/api/alerts*`, `/api/admin/webhooks/*`, `/api/grafana/*`) and the `/ws/alerts` WebSocket are forwarded one-to-one through a shared `httpx.AsyncClient`. Cookies and `Authorization` headers are preserved. | If obs is down, proxy returns `502 Bad Gateway`. The frontend dashboard degrades; the storefront is unaffected. |

The asymmetry is intentional: **writes must never block business traffic; reads must always reflect current obs state** (no stale cache). This realises the central thesis of §15 — that observability must be *cheap on the hot path* and *correct on the diagnostic path*.

#### 6.1.3 Locus of In-Memory State

The split is also a *memory-safety* boundary:

| State | Lives in | Why |
|-------|----------|-----|
| Rolling SRI window, golden-signal history | obs | Single source of truth; avoids two-process aggregation drift |
| Healing-engine RL adaptation matrix (§12.4) | obs | The autonomous learning loop must see *all* corrective-action outcomes, not a per-process partition |
| Resilience-debt integral `E(t) = ∫Φ dt` (§7H, §15) | obs | Single accumulator; restarting only obs is enough to reset the integral, and main_app's hot path is unaffected |
| User session cookies, cart state | MongoDB (shared) | Persistent; both services can authenticate against the same JWT_SECRET, but obs only consumes auth — it never issues tokens |
| Webhook cooldown table | obs | Webhook delivery (§13.5) is an obs concern; deduplication must be process-local |

A consequence worth recording: the in-memory `MetricsAggregator` defined in §5.2 is **populated exclusively by the `/api/internal/events/request` receiver in obs**, not by an in-process middleware on the main app. This means the SRI, all FEA stress fields, all conversion correlations, and every healing decision are computed from telemetry that has *already crossed a network boundary*. The boundary itself is therefore part of the system under measurement — a small but principled correction to the closed-loop diagram of §16.

#### 6.1.4 Implications for the Equations of §5–§9

Every analytical quantity defined in this paper survives the split unchanged, but two operational concerns deserve note:

1. **Telemetry latency.** Equation 1 (edge-weight derivation, §5.2) is computed in obs from arrival timestamps written by obs's own event receiver. The single-process implementation would have computed it from the originating middleware's clock. Drift between the two is bounded by the localhost RTT (microseconds) and is therefore well below the SRI rolling-window granularity (30 s).

2. **Recovery of obs after restart.** When obs restarts, the entire in-memory state is empty. The warm-up logic in §17 (Baseline Calibration) re-engages automatically and converges within `warmup_target = 10` requests — typically <2 s under any non-trivial production load. Healing decisions are deferred until warm-up completes (the engine reports `mode="warming_up"`).

#### 6.1.5 What This Buys

- **Fault isolation.** A pathological healing loop, a runaway `polyfit`, or a memory leak in any engine in §7–§14 cannot starve the storefront's event loop or block checkout. The CPU-heavy observability work runs in a separate process group with its own uvicorn worker.
- **Independent restarts.** Operators can `supervisorctl restart backend_obs` to reset the entire in-memory observability state — the SRI history, the healing RL matrix, the resilience-debt integral — *without taking the storefront offline*. This is the practical realisation of §15's "reliability is a business outcome" principle.
- **Surface-area minimisation.** Port 8002 is not exposed via the cluster ingress. The only externally reachable entry point for the entire observability surface is the synchronous proxy on port 8001, which preserves the existing `REACT_APP_BACKEND_URL` contract for the frontend.
- **Backward compatibility.** All endpoint paths and response shapes are preserved. The frontend, all dashboards, and every test that pre-dates the split continue to work unmodified.

#### 6.1.5b In-process Modularization of `obs_server.py` (iter 27–30)

The observability process is itself further decomposed at the *source* level into the `backend/obs/` Python package. The decomposition is **internal** — no new process boundary, no new wire protocol — but it materially affects maintainability, restart latency, and the surface area exposed to future contributors.

| Phase | iter | Extracted artefact | Where |
|-------|------|--------------------|-------|
| 1 (scaffolding) | 27 | New `obs/{trackers,engines,routes}/__init__.py` with PEP-562 lazy re-exports | — |
| 2 | 28 | Eight standalone trackers (`MetricsAggregator`, `SRIInterpolator`, `ResilienceDebtAccumulator`, `CorrelationTracker`, `AutoPropagationDetector`, `SRIAttributionEngine`, `WebhookNotifier`, `HealingAction`) | `obs/trackers/core.py` |
| 3 | 29 | Three more trackers (`CustomerExperienceTracker`, `BusinessMetrics`, `AlertManager`) + four heavyweight engines (`HealingEngine`, `HealingSequenceOptimizer`, `AggressiveHealingMode`, `PermanentFunnelHealer`) | `obs/trackers/core.py`, `obs/engines/core.py` |
| 4 | 30 | New synthesizer (§12.7) | `obs/engines/ladder_synthesizer.py` |
| 4 (quality pass) | 30 cont. | Code-review surgical fixes (no structural changes): test fixtures now resolve credentials from `ADMIN_TEST_*` / `USER_TEST_*` env vars; silent `try/catch` blocks in user-facing pages emit `console.error`; `key={idx}` swapped to content-derived keys; `useMemo` applied to three hot JSX computation paths | `frontend/src/{pages,components/dashboard}/`, `backend/tests/` |

`obs_server.py` shrunk from 5,623 lines (iter 26) to 2,540 lines (iter 30) — a 55 % reduction — without altering a single method body. The non-trivial part is the **singleton-binding pattern** that breaks the cross-module dependency graph without a wholesale dependency-injection refactor:

1. Each extracted module **forward-declares** the singletons it references (`metrics_aggregator`, `business_metrics`, `attribution_engine`, `compute_sri_from_metrics`, `TOPOLOGY_SCHEMA`, `PERMANENT_FIX_REGISTRY`, threshold constants, …) as `None`/`{}` at module top.
2. `obs_server.py` instantiates the singletons in dependency order, then calls `_wire_extracted_modules()`, which iterates over the extracted modules and `setattr`s the real instances into their `globals()` dicts.
3. Method bodies in the extracted modules resolve singletons through their own `globals()` — i.e. via the function-globals lookup performed at call time, not import time. By the time any method runs, every name resolves to a live instance.

This buys two properties relevant to the equations of this paper: (a) every equation in §5–§9 references the *same* in-memory aggregators it did before the split, byte-for-byte; (b) restarting the observability process restarts every engine and every adaptation table in one atomic step, preserving the §15 closed-loop invariant that healing decisions are computed from a single, coherent telemetry frame.

##### Static-analysis surface

The singleton-binding pattern is deliberately invisible to static analysers, which produces a recurring set of **false positives** worth recording so future contributors do not waste cycles "fixing" them:

| False positive | Reality |
|----------------|---------|
| *"Circular import between `obs/trackers/core.py` ↔ `obs_server.py`."* | There is no runtime cycle. `obs_server.py` imports the extracted classes; the extracted modules do **not** import `obs_server.py`. They reference singletons via their own module globals, which are populated post-instantiation by `_wire_extracted_modules()`. |
| *"Undefined variable references (`metrics_aggregator`, `business_metrics`, …) in the extracted modules."* | These names are forward-declared as `None` / `{}` at module top and rebound at runtime. Any method that reads them runs after `_wire_extracted_modules()` has completed (start-up ordering is fixed by `obs_server.py`'s top-level execution). |
| *"Dynamic-import security risk in `ladder_synthesizer.py` (`__import__("obs.engines.core", fromlist=[...])`)."* | The module path is a hardcoded string literal, identical at every call site. It accepts no user input and is functionally indistinguishable from a top-level `import` — its only purpose is to break the import cycle that *would* exist if §12.7's `LadderSynthesizer` referenced `metrics_aggregator` at import time. |

In all three cases the "fix" recommended by the analyser would require unwinding the whole modularization. The pattern is documented here precisely so that contributors faced with a CI lint failure can recognise it and configure their tools to ignore these specific findings.

#### 6.1.6 Caveats and Threats

- The `/api/internal/events/*` endpoints have no authentication. They are safe only because port 8002 is not exposed externally. If the cluster ingress is ever reconfigured to expose obs directly, a shared-secret header check must be added.
- The catch-all proxy route in the main app uses FastAPI's path-parameter fallback. Adding a new e-commerce route *after* the proxy is registered would silently shadow it as an obs path. The reference implementation registers e-commerce routes first and the proxy last; future maintainers must preserve this ordering or replace the catch-all with an explicit allow-list.
- The `/ws/alerts` WebSocket bridge requires the cluster ingress to forward HTTP `Upgrade` headers. Where this is not configured (e.g. some preview environments), the dashboard falls back to REST polling of `/api/alerts` and remains functional.

---

### 6.2 Three-Tier Topology Granularity

The mesh exposed by the analytical engine has **three hierarchical tiers**, each a strict refinement of the previous one. Every equation in this paper (Eq. 1 edge weights through Eq. 12 cascade risk) is defined over a generic node set `V` and edge set `E ⊆ V × V`, so it operates unchanged at any tier — only the cardinality of `V` and the resolution of the diagnosis change.

| Tier | `|V|` | `|E|` | Identifier example | Purpose |
|------|-------|-------|---------------------|---------|
| **service**   |   6 |   8 | `API`                  | Operator-facing health; drives alerts, SRI, the dashboard's coarse view |
| **component** |  46 |  84 | `API.auth`             | Engineering-facing diagnosis; localises stress to a sub-system inside a service |
| **endpoint**  | 101 | 139 | `API.auth.login`       | Surgical diagnosis; pinpoints the exact request handler, DB query, cache key, or queue topic carrying the stress |

#### 6.2.1 Construction

The component tier is hand-curated (the system architect labels each service's internal modules). The endpoint tier is partially auto-derived from the component tier:

- **Intra-component edges** are a sequential chain across siblings (`API.auth.login → API.auth.register → API.auth.me → API.auth.logout`), modelling the typical execution order within a unit of work.
- **Inter-component edges projected to endpoints**: for every component-tier edge `(C_a, C_b)`, an endpoint edge `(first(C_a), first(C_b))` is added. The "first" endpoint is the entry point — i.e. the handler that a downstream caller hits first when entering that component.

This projection preserves a strong invariant: the **endpoint graph is always a refinement of the component graph**, which is itself a refinement of the service graph. As a consequence, the Fiedler eigenvalue (algebraic connectivity) at the endpoint tier upper-bounds the connectivity at the component tier, which upper-bounds the service tier — a property that prevents the dashboard from showing healthier metrics at a finer tier than at the coarser one.

#### 6.2.2 Per-Tier Traffic Synthesis

At the endpoint tier, the system has no direct telemetry per leaf (the e-commerce front door doesn't tag requests with `API.auth.login` — it just sees `POST /api/auth/login`). The aggregator therefore *synthesises* endpoint-tier metrics by splitting the parent component's metrics across siblings under controlled stochastic noise:

```
traffic(ep)    = max(1, traffic(parent_component) / sibling_count)
latency(ep)    = latency(parent_component) · U(0.7, 1.4)
error(ep)      = clip(error(parent_component) · U(0.4, 2.2), 0, 1)
saturation(ep) = clip(saturation(parent_component) · U(0.6, 1.6), 0, 1)
```

This is deliberately probabilistic: the test harness must use loose tolerances. The synthesised values are consistent with the parent in *expectation* (so service-tier SRI remains canonical), but allow surgical reasoning at the leaf when human operators want to know which endpoint inside a stressed component is the culprit.

#### 6.2.3 Tier-3 Auto-Dampening

The `auto-dampen-wave` algorithm (§7H) accepts `granularity='endpoint'`. The procedure is identical to the service-tier case (simulate baseline propagation → find critical arrivals → BFS-cut on highest-cascade-risk edge → re-simulate → map to healing action), but the cut-edge is now an endpoint pair like `(API.auth.login, API.auth.register)`. Importantly, the mapping from cut-edge to corrective action *collapses* the dotted name to its parent service before looking up the corrective action (e.g. cutting `API.auth.login → API.auth.register` triggers `rate_limit @ API`). This means tier-3 buys the operator a more *informative* recommendation ("the cut is at the login handler") without changing the action surface — a deliberate choice to keep the system testable and reversible.

#### 6.2.4 Why Three Tiers and Not More

Empirically, tier-4 (instruction-level: individual SQL statements, individual code paths inside `API.auth.login`) collapses the signal-to-noise ratio below the level where the autonomous engine can act reliably. The CX layer (§13) tracks p50/p90/p99 latency per endpoint, which already provides the fourth tier of diagnostic detail without entering the graph as a propagation node. The three-tier choice is therefore not arbitrary: it is the **coarsest hierarchy that still gives surgical resolution while preserving the spectral-resilience invariants** that make the equations meaningful.

---

## 7. SRI — Spectral Resilience Index

### 7.1 Properties

The SRI has several desirable properties for an infrastructure health metric:

- **Holistic**: Captures the entire system state in a single number
- **Sensitivity**: Degrades *before* individual component thresholds are breached, because it detects weakening inter-node links
- **Interpretability**: Backed by rigorous mathematics (algebraic connectivity), not a heuristic
- **Decomposability**: The Fiedler vector reveals *which* links are weakest
- **Scale-invariant**: The λ₂/λ_max ratio works across different system sizes

### 7.2 Interpretation Guide

| SRI Range | System State | Interpretation |
|-----------|-------------|----------------|
| 0.8 – 1.0 | Excellent | All nodes healthy, strong connectivity |
| 0.5 – 0.8 | Good | Minor degradation, system remains resilient |
| 0.3 – 0.5 | Warning | Noticeable degradation, remediation recommended |
| 0.1 – 0.3 | Critical | Significant degradation, multiple weak links |
| 0.0 – 0.1 | Severe | Near-partition, immediate intervention required |

### 7.3 Advantages Over Aggregate Metrics

Traditional approaches average or worst-case individual metrics. SRI differs fundamentally:
- An average of 5 healthy nodes and 1 failing node might report "83% healthy"
- SRI would report a much lower value because the failing node *disconnects* part of the graph, drastically reducing algebraic connectivity

This makes SRI a **leading indicator** — it detects systemic risk before aggregate metrics show a problem.

### 7.4 Browser/Frontend as a First-Class Topology Node

Traditional infrastructure SRI implementations cover backend-only services. This implementation extends the Spectral Resilience Index to the **browser tier** by treating the user's actual browser session as a sixth topology node.

**Topology** (6 services, 6 inter-edges, 19 sub-components):

```
   Frontend ---> API ---> Cache
                  | \      |
                  |  \     v
                  v   v    DB
                 Queue --> Backend
```

**Frontend sub-components**:
- `Frontend.page_load` — Navigation Timing API (load event end - navigation start)
- `Frontend.render` — paint timings (FCP, LCP)
- `Frontend.api_calls` — axios round-trip latency observed from the browser
- `Frontend.js_errors` — `window.onerror` + unhandled promise rejections

**Real User Monitoring (RUM) ingestion**:
A lightweight beacon (`/app/frontend/src/lib/rumBeacon.js`) attached at React app boot captures these signals from the actual browser session and posts them to `POST /api/rum/beacon` every 5 seconds (using `navigator.sendBeacon` on tab close so the last batch is preserved). The endpoint is rate-limited to 1 beacon per second per session_id.

**Why this matters**: Many resilience failures are *user-felt but server-invisible* — long tasks blocking the main thread, JavaScript exceptions on a single browser, slow network round-trips from a particular ISP. By treating Frontend as a regular topology node, the SRI engine integrates these signals into the Laplacian computation, the FEA stress analysis, fault propagation, and the autonomous healing cut-edge selection. A bad browser experience drags SRI down and can trigger Frontend → API → downstream healing, even when server-side metrics look healthy.

---

## 7B. Strict-FEA Engine on the Service Mesh

The implementation applies **finite element analysis in the strict mathematical sense** to the topology graph, treating it as a discrete elastic structure.

### 7B.1 Governing Equation

The system solves the FEA equilibrium equation:

```
K · u = F
```

- **K (stiffness matrix)** ↔ **Connection Strength** — derived from `1/(latency · error_rate)` per edge
- **u (displacement field)** ↔ **State Deviation** — solved drift vector per node
- **F (load vector)** ↔ **Degradation Load** — weighted sum of latency + errors + saturation per node
- **ε (strain) = ∂u** ↔ **Service Drift** — % deviation of node state from baseline
- **σ (stress) = K · ε** ↔ **Service Pressure** — stiffness-weighted drift
- **σvm (von-Mises stress)** = √((σ₁−σ₂)² + (σ₂−σ₃)² + (σ₃−σ₁)²) / √2 ↔ **Composite Pressure**
- **σy (yield threshold)** ↔ **Failure Threshold** — pressure at which a service breaks SLO

The FEA endpoint exposes both names side-by-side via a `terminology` field so the dashboard reads correctly to both reliability engineers and structural-FEA practitioners.

### 7B.2 Hierarchical FEA

`GET /api/healing/fea?granularity=service|component` returns either:
- **Service-level**: 6 elements (Frontend/API/Cache/DB/Queue/Backend) with 6 inter-edges
- **Component-level**: 19 sub-components (e.g., `Frontend.api_calls`, `API.checkout`, `Backend.sri_engine`) with 25 fine edges including intra-service and inter-service component connections

Each granularity level produces independent yield thresholds, stress fields, and edge fragility analyses. Operators can drill into a single service to see *which sub-component is yielding*.

### 7B.3 Cascade Risk per Edge

Each edge carries a **cascade-risk score** in [0, 1]:

```
risk(i, j) = (norm_pressure_avg(i,j) · w_ij) / Σ_in(j)
```

Where `Σ_in(j)` is the total connection strength incident on the target node. This represents the probability mass that a fault originating at i propagates to j given current upstream stress and coupling — directly inspired by HaiQ-style design-variability propagation kernels.

---

## 7C. Failure Propagation Simulator

The implementation includes a **graph-Laplacian fault diffusion simulator** (`POST /api/healing/fault-propagation`) that models how a fault originating at any service or sub-component propagates through the topology over time.

### 7C.1 Diffusion Equation

The fault intensity vector `x(t)` evolves according to the heat equation on the graph:

```
ẋ = −α · L · x
```

Discretized:
```
x(t + Δt) = x(t) − α · Δt · L · x(t)
```

With `α = 0.25`, `Δt = 0.5s`, and 30 steps producing a ~15-second visualization. The source node is clamped to maintain ≥50% of its initial fault strength so the wave persists for the full window.

### 7C.2 Per-Node Arrival Times

For every reached node the simulator records:
- **first_arrival_t** — time at which intensity crosses 0.05
- **peak_fault** — max intensity over the window
- **infected_count** — propagation breadth at each timestep

This produces a deterministic "time-to-impact" estimate for each downstream component — operators see *exactly when* an upstream fault will reach a critical service.

### 7C.3 Stability Potential

The diffusion preserves a quadratic stability potential:

```
Φ(t) = x(t)ᵀ · L · x(t)
```

Φ rises as the wave forms (high-amplitude localized) and decays as the wave spreads (lower-amplitude diffused). The time-integrated potential `E(t) = ∫₀ᵗ Φ dt` is the **Resilience Debt** — surfaced by the dashboard as cumulative system imbalance and a cost-equivalent `Cost ∝ 1/SRI` (Unified-View paper).

---

## 7D. Auto-Dampener — Wave-Arresting Cut Edges

`POST /api/healing/auto-dampen-wave` computes and (optionally) executes a healing action that arrests a propagating fault wave before it reaches downstream critical nodes.

### 7D.1 Algorithm

1. **Simulate baseline propagation** from the source.
2. **Identify critical arrivals** — downstream nodes whose `peak_fault ≥ critical_arrival_threshold` (default 0.30).
3. **BFS path** from source to each critical arrival.
4. **Score candidate cut-edges** by `cascade_risk × depth` — favor cuts deeper along the path so the wave is allowed to dissipate naturally before being clipped.
5. **Re-simulate with the cut edge zeroed** (`L` rebuilt without that edge) → compare peak amplitude beyond the cut.
6. **Map the cut to a software healing action**:
   - Cut involves `Cache.*` → `cache_flush`
   - Cut involves `DB.*` → `connection_pool_reset`
   - Cut involves `Backend.*` → `circuit_breaker`
   - Cut involves `Queue.*` → `queue_drain`
   - Otherwise (API/Frontend) → `rate_limit`
7. **Cooldown-aware execution** — if the chosen action is on cooldown, return the recommendation with `cooldown_remaining_seconds` instead of failing silently.

### 7D.2 Auto-Arrest Mode

The dashboard's chaos panel offers an **Auto-Arrest** toggle: every fault injection automatically calls `auto_dampen_wave(auto_execute=true)`, providing a continuous demonstration of the system's ability to proactively arrest cascades.

---

## 7E. Auto-Propagation Detection + Path-Based Autonomous Healing

A background loop (`auto_propagation_loop`) runs every 8 seconds and:

1. **Scans** for stressed services (composite pressure ≥ threshold or `yield_exceeded=true`).
2. **Pre-computes** the propagation timeline for each stressed source (15-step Laplacian simulation).
3. **Fires alerts** through the AlertManager (deduplicated) and Slack/Discord webhooks if configured.
4. **(Optional) executes autonomous healing** along the propagation path using the sequence optimizer.

The detector and autonomous healing can be toggled independently via `POST /api/healing/auto-propagation/config`.

---

## 7F. Healing Sequence Optimizer

`POST /api/healing/optimize-sequence` produces an **ordered healing plan** for a list of stressed nodes:

### 7F.1 Score Function

For each candidate action a:
```
score(a) = sri_gain × readiness − 0.05 · |pressure|
sri_gain = |action.sri_impact| · (1 + |effectiveness_history_avg|)
readiness = 1.0 if cooldown=0 else max(0, 1 − cooldown_remaining / cooldown_total)
```

### 7F.2 Ordering

1. **BFS depth from the root cause** (depth 0 = source) — repair the cause before the symptoms.
2. **Score descending** within each depth.
3. **Deduplicate** by action_id so the same corrective action isn't queued twice.
4. **Returns** `expected_total_sri_gain` so operators preview the plan's impact.

`POST /api/healing/execute-sequence` runs the plan with a configurable inter-step delay (default 800ms) so SRI can settle and effectiveness can be recorded for the next adaptation cycle.

---

## 7G. Customer Experience Layer

The system records **user-facing metrics** alongside infrastructure metrics so operators can see healing's effect in business-relevant terms:

| Metric | Definition |
|---|---|
| `page_load_ms` | Real Navigation-Timing duration from RUM beacons |
| `add_to_cart_ms` | Cache-latency proxy for the cart microaction |
| `error_shown_rate` | % of requests that surfaced an error to the user |
| `conversion` | Live conversion rate from the business-funnel model |
| `perceived_speed` | Composite UX score: `< 200ms = 100, > 2000ms = 0`, linear between |

`GET /api/cx/metrics?window_seconds=` returns the time series + healing annotations with **30s before/after deltas** so each healing action shows its real CX impact ("Page −640ms, UX +38, Err −1.2%").

`POST /api/cx/synthetic-user/run` executes a real end-user journey (Landing → Product → Filter → Checkout) in-process via httpx ASGITransport and returns a per-step verdict (delightful / acceptable / frustrating / broken).

---

## 7H. Non-Recoverable State Detection

Implementing **Equation 7** from the SRI/SAI paper:

```
non_recoverable = (|d(SRI)/dt| < ε) ∧ (SRI < SRI_threshold)
```

With `ε = 0.0008`, `SRI_threshold = 0.3`, and a sustained-window requirement of 3 consecutive samples below threshold. When triggered, the dashboard surfaces a loud red `NonRecoverableBanner` and the autonomous healing engine escalates to the most aggressive ladder.

---

## 8. Finite Element Analysis (FEA) Engine

### 8.1 Motivation

While the Fiedler vector identifies spectrally isolated nodes, it cannot quantify the **mechanical stress** each component is experiencing or predict which components are approaching failure. Finite Element Analysis — a well-established technique in structural engineering for computing stress and deformation in physical structures — is applied here to the infrastructure graph.

### 8.2 FEA Formulation

The system graph is treated as a structural mesh:

| Structural Concept | Infrastructure Mapping |
|-------------------|----------------------|
| Stiffness Matrix **K** | Graph Laplacian (edge weights as spring constants between nodes) |
| Load Vector **f** | Node degradation: 30% latency + 45% error rate + 25% saturation |
| Displacement Vector **u** | Solved via pseudo-inverse: u = K_pinv * f |
| Strain Energy SE_i | 0.5 * |u_i| * K_ii * |u_i| — energy stored in each node's deformation |
| Von-Mises Stress sigma_vm | sqrt(sigma_d^2 + sigma_l^2 - sigma_d * sigma_l) — combined direct and load stress |
| Yield Threshold | Adaptive: mean(VM) + 0.5 * std(VM), with floor at 0.15 |

### 8.3 Yield Detection

Nodes whose Von-Mises stress exceeds the adaptive yield threshold are classified as **actively failing** — they are under more mechanical stress than the system can sustain. These nodes receive immediate corrective actions.

### 8.4 Edge Strain Analysis

Beyond per-node stress, the FEA engine computes **edge strain** — the differential displacement between connected nodes multiplied by edge stiffness. High-strain edges indicate communication paths under duress, complementing the Fiedler vector's weak-edge detection with a quantitative strain measure.

### 8.5 Advantages Over Spectral-Only Analysis

| Aspect | Spectral (Fiedler) | FEA |
|--------|-------------------|-----|
| Output | Scalar isolation score | Full stress/strain field |
| Multi-node | Single root cause | All yield-exceeded nodes |
| Quantitative | Relative ranking | Absolute Von-Mises value |
| Actionable | "This node is isolated" | "This node is at X% yield, apply CA" |

The combined RCA uses both: 25% spectral + 35% degradation signals + 40% FEA Von-Mises contribution.

---

## 9. SRI Polynomial Interpolation

### 9.1 Purpose

Point-in-time SRI readings cannot distinguish between "steady degradation" and "momentary dip recovering". The interpolation engine fits a polynomial to the SRI time series and extracts dynamics.

### 9.2 Method

A **quadratic polynomial** SRI(t) = a*t^2 + b*t + c is fitted to the last 200 SRI samples using least-squares (numpy.polyfit):

- **Velocity** v = dSRI/dt = derivative at t=0 (current rate of change)
- **Acceleration** a = d2SRI/dt2 = second derivative (is degradation accelerating?)
- **Prediction** SRI(T+30s) and SRI(T+60s) via polynomial extrapolation, clamped to [0, 1]

### 9.3 Trend Classification

| Trend Label | Condition | Healing Response |
|-------------|-----------|-----------------|
| critical_degrading | velocity < -0.005 AND acceleration < -0.0001 | Fire ALL yield-node CAs simultaneously |
| degrading | velocity < -0.002 | Fire top 3 yield-node CAs |
| stable | -0.002 <= velocity <= 0.002 | Fire top 2 yield-node CAs |
| recovering | velocity > 0.002 | Monitor only |

### 9.4 SRI Dip Detection

Complementing the polynomial trend, a **high-watermark dip detector** tracks:
- The highest SRI observed (slowly decaying)
- Current dip magnitude = watermark - current SRI
- Healing activates when dip > 3% OR SRI < warning threshold

This dual approach (polynomial trend + dip from watermark) catches both gradual degradation and sudden drops.

---

## 10. Golden Signal Integration

### 8.1 Signal-to-Weight Mapping

The four Golden Signals [1] are formally integrated into the graph model through the edge weight function. Each signal contributes a weighted component to the overall SRI:

| Signal | Contribution Weight | Role in SRI |
|--------|-------------------|-------------|
| Latency | Significant | Inversely affects edge weight — slower links weaken connectivity |
| Traffic | Moderate | Provides the numerator — active links are stronger |
| Errors | Highest | Directly degrades link reliability |
| Saturation | Significant | Capacity pressure weakens available connectivity |

The exact weights are proprietary but are calibrated to reflect operational priorities: errors have the highest impact because a failing service affects all downstream consumers.

### 8.2 Per-Signal Health Score

Each golden signal is independently scored on a [0, 1] health scale with signal-specific thresholds. This enables:
- Identifying which signal is **most responsible** for SRI degradation
- Targeted remediation aimed at the weakest signal
- Historical trending per signal

### 8.3 SRI Contribution Decomposition

The system computes how much each golden signal's health contributes to the current SRI value. This decomposition answers the question: *"If I could fix only one thing, which signal should I improve?"*

---

## 11. Customer Experience Layer

Beyond infrastructure metrics, the system tracks the **user-facing impact** of system health:

### 9.1 Apdex (Application Performance Index)

Every request is classified using the industry-standard Apdex methodology [2]:
- **Satisfied**: Response time below threshold T
- **Tolerating**: Response time between T and 4T
- **Frustrated**: Response time above 4T or error

The Apdex score directly reflects whether infrastructure health translates to user satisfaction.

### 9.2 Latency Percentiles

P50, P95, and P99 percentiles are continuously computed from a sliding window. These capture tail latency that averages hide.

### 9.3 Error Budget

An SLO-based error budget tracks the remaining tolerance for failures:
- A target availability SLO is defined
- Each error consumes part of the budget
- When the budget is exhausted, the system signals that reliability is at risk

This bridges the gap between infrastructure metrics (SRI, golden signals) and business commitments (SLAs).

---

## 11.5 Business Reliability Model

### From Resilience to Revenue

The system introduces a **Reliability Score** that formally connects infrastructure health to business outcomes:

```
Reliability = 0.20 * SRI + 0.30 * Apdex + 0.25 * Availability + 0.25 * Conversion_Health
```

Where `Conversion_Health` is derived from a **conversion impact model** based on empirical e-commerce research:

| Factor | Impact | Source |
|--------|--------|--------|
| Every 100ms latency | ~7% conversion loss | Amazon/Google (2012) |
| Every 1% error rate | ~10% conversion loss | Industry benchmark |

The model computes:
- **Effective conversion rate** = base_rate * latency_factor * error_factor
- **Health-adjusted funnel** = per-stage conversion probabilities (view->cart, cart->checkout, checkout->order) degraded by system health
- **Projected revenue/min** = effective_conversion * traffic * avg_order_value
- **Improvement opportunity** = what conversion would be if latency halved or errors zeroed

### SRI Attribution Engine

When SRI dips, the attribution engine decomposes the degradation into:
1. **Per-node attribution** — which node contributes most to the dip
2. **Per-signal breakdown** — latency vs errors vs saturation contribution
3. **Business impact mapping** — which business metric (conversion, apdex, revenue) is most affected by each node's degradation

This creates a direct causal chain: `Node X has high latency -> latency hurts conversion (weight 0.4) -> healing Node X with cache_flush (latency affinity 0.8) -> conversion improves -> reliability rises`.

### Healing with Business Justification

Every healing action record now carries `business_context`:
- The current reliability score
- Which business metric the action is expected to improve
- The conversion rate at time of healing

This enables post-hoc analysis: "Did healing action X actually improve business outcomes, or just infrastructure metrics?"

### 11.5.1 Economic Reliability — Unified-Model Phase 3

The Reliability Score above is a normalised composite. To answer the harder question — *is the healing engine economically worth its cost?* — we layer an explicit **economic-reliability calculus** on top of the same observables, following Sunder's RSM formulation (refs [13]–[15]).

**Definitions**

| Symbol | Meaning | Source |
|--------|---------|--------|
| `W` | Work / business value generated, USD/min | `BusinessMetrics.revenue_5min ÷ 5` |
| `H_i` | Healing potential of node i | `1 / (1 + σ_i)` (normalised — no absolute capacity assumed) |
| `σ_i` | Composite stress of node i | `PhaseClassifier.latest.per_node[i].sigma` |
| `R_S` | System-wide resilience ratio | `ΣH_i / Σσ_i` (soft-capped at 100) |
| `C_I` | Infrastructure cost, USD/min | flat, env `PHASE3_INFRA_COST_USD_PER_MIN` |
| `C_O` | Observability cost, USD/min | `(events_per_min / 1000) × PHASE3_OBS_USD_PER_KEVT` |
| `C_H` | Healing cost, USD/min | dampener actions × `PHASE3_HEAL_COST_PER_ACTION` + scale actions × `PHASE3_SCALE_COST_PER_ACTION` |
| `C_F` | Failure cost, USD/min | `max(0, projected_revenue_per_min − W)` (modelled-conversion ceiling minus achieved) |

**Equations** (Eqs. 51, 57, 58 of RSM)

```
C_T   = C_I + C_O + C_H + C_F                  (Eq. 51 — total cost)
R_econ = W / C_T                                (Eq. 57 — value per cost)
R     = W · (ΣH_i / Σσ_i) / C_T = W · R_S / C_T (Eq. 58 — resilience-weighted value)
```

**Counterfactual heal-saved revenue.** When achieved conversion `actual_conv > modeled_conv` (i.e. healing has lifted the system above its degraded baseline), we credit the system with the uplift's revenue rate:

```
heal_saved_per_min = max(0, actual_conv − modeled_conv) × traffic_per_s × 60 × avg_order_value
```

This is integrated over the last 12 ticks (≈ 1 min) and surfaced as `counterfactual_revenue_saved_per_min` on the dashboard — operators can see in dollars the conversion lift the healing system is producing right now.

**Implementation**: `obs.trackers.economic_reliability.EconomicReliabilityTracker` is a read-only composer over `BusinessMetrics`, `MetricsAggregator`, `HealingEngine.history`, and `PhaseClassifier` — no new instrumentation, no new persistence. The tick loop runs every 5 s starting 20 s after server boot. Output is exposed via `GET /api/economic-reliability/{state,trend}` and rendered by `EconomicReliabilityCard` on the System Health tab (R_econ headline, segmented C_T bar, R_econ + W sparklines, conversion / orders / revenue strip).

---

## 12. Adaptive Autonomous Remediation Engine

### 12.1 The Stagnation Problem

Traditional auto-healing systems map alerts to actions deterministically: "SRI low -> execute circuit_breaker". This works initially, but creates a failure mode we term **healing stagnation**:

> An action is repeatedly executed because the trigger condition persists, yet each execution produces zero marginal SRI improvement.

Example observed in production: `rate_limit` executed 47 consecutive times on the API node with `sri_delta = 0.0` every time. The RCA correctly identified the API as the root cause, but the chosen action (throttling) cannot fix an error-rate problem — it only addresses saturation.

### 12.2 Design Principles

The adaptive engine follows five principles:
1. **Targeted**: Each action addresses a specific node
2. **Measured**: Every execution records its SRI delta
3. **Self-Learning**: Detects when an action becomes ineffective
4. **Escalating**: Automatically tries alternative actions for the same node
5. **Cross-Node**: When a node's own actions are exhausted, heals its graph neighbors

### 12.3 Effectiveness Tracking

Every call to `execute_action()` records the actual `sri_delta` (SRI after - SRI before). The last N deltas (N=5, configurable) are stored per action. An action is marked **exhausted** when all recent deltas are below the stagnation threshold (0.001).

Key property: **Auto-reset**. If an exhausted action later produces a positive delta (conditions changed, metrics shifted), the exhaustion flag clears automatically. This handles the case where an action is temporarily ineffective but becomes useful again.

### 12.4 Three-Tier Healing Strategy

```
Tier 1: FEA Multi-CA (multiple yield-exceeded nodes, adaptive action per node)
  |-- For each yield node: walk its escalation ladder
  |-- Fire simultaneously (batch_id correlates the group)
  |-- Count based on trend: critical=all, degrading=top3, stable=top2
  
Tier 2: RCA Adaptive (single root cause node)
  |-- Walk the root cause node's escalation ladder
  |-- Skip exhausted actions, find next effective one
  
Tier 3: Threshold Fallback
  |-- Scan all actions, skip exhausted ones
  |-- Execute any that are triggerable and non-exhausted
  
Tier FAIL: Stagnation Alert
  |-- All actions exhausted, no healing possible
  |-- Broadcast 'healing_stagnation' event
  |-- System signals need for human intervention
```

### 12.5 Action Taxonomy (v2)

| Action ID | Target | Description | Cooldown |
|-----------|--------|-------------|----------|
| cache_flush | Cache | Purge stale entries, reduce latency | 45s |
| rate_limit | API | Adaptive rate limiting, reduce saturation | 30s |
| circuit_breaker | Backend | Isolate failing services, stop error propagation | 60s |
| connection_pool_reset | DB | Reset stale connections, reduce DB latency | 90s |
| queue_drain | Queue | Clear message backlog, restore throughput | 45s |
| api_error_suppression | API | Suppress retry storms, clear error amplification | 40s |

### 12.6 Aggressive / Reliability-Aware Mode (v3, iter 22)

The default healing engine is fundamentally **reactive**: it fires when an alert (`/api/alerts`) is generated by an SRI dip or a yielding element. This is correct, conservative, and explainable — but it leaves a class of problems unaddressed: **slow accumulation of resilience debt during nominally healthy windows**. From §15 we know that `E(t) = ∫₀ᵗ Φ(t) dt` keeps growing whenever `Φ > 0`, even at small Φ. Reactive healing never trims this integral because the SRI never crosses the alert threshold.

The aggressive mode adds a second control loop that targets `dE/dt` directly.

#### 12.6.1 Trigger Conditions

The aggressive loop runs every 5 seconds and fires when **any** of the following hold:

1. `dE/dt > δ_debt` — the instantaneous Φ exceeds a configurable debt-rate threshold (default 8 × 10⁻⁴ per second). Because `E = ∫Φ dt`, this is equivalent to saying "debt is being earned faster than we like".
2. `dSRI/dt < −10⁻³` ∧ `d²SRI/dt² < 0` — the polynomial interpolator (§9) reports both negative velocity *and* negative acceleration, indicating a dip is imminent within the next 30-second horizon even if SRI is currently nominal.
3. `SRI < 0.985` ∧ `dE/dt > 0` — baseline drift: SRI has slid slightly below the high-water mark and debt is still accumulating.
4. `max_pressure > 0.008` — any service's strain-energy-derived pressure (§7B) has crossed a low preemptive threshold.

The first three conditions explicitly couple to the resilience-debt formulation; the fourth is a fail-safe that ensures the loop engages under typical demo / production traffic even when the integrated quantities haven't yet exceeded their thresholds.

#### 12.6.2 Multi-Objective Action Scoring

Reactive healing selects actions by **signal affinity** (§12.3) — a single-objective heuristic that asks "which action best targets the dominant failing signal". Aggressive healing instead solves a **multi-objective optimisation** over the four business-aligned outcomes (Reliability Score components from §15):

```
score(a) = 0.30 · ΔSRI(a) + 0.30 · ΔApdex(a) + 0.20 · ΔAvail(a) + 0.15 · ΔConv(a) − 0.05 · cost(a) + prior(a)
```

Where:
- `Δ_X(a)` is the rolling mean of the past 100 healing-history records of action `a`, computed from `golden_signals_before/after`. Apdex/Avail/Conv aren't recorded directly; they are derived as proxies:
  - `ΔApdex(a)   = clip((latency_before − latency_after) / max(latency_before, 0.05), −1, +1)`
  - `ΔAvail(a)   = clip((errors_before  − errors_after)  / max(errors_before, 0.005), −1, +1)`
  - `ΔConv(a)    = 0.7 · ΔAvail(a) + 0.3 · ΔApdex(a)`
- `cost(a)` is a per-action operational-cost constant (cache_flush=0.10, rate_limit=0.15, circuit_breaker=0.35, …).
- `prior(a) = 0.01` if action `a` has *no* historical record yet (cold-start), else 0. This prevents the cost penalty from blocking discovery — an action with no history cannot have a positive ΔX, so without a prior it would always lose to a cheaper action with a worse-but-known history.

The action chosen for the proactive heal is `argmax_a score(a)`, gated by `score ≥ −min_lift_threshold` (i.e. only refuse to act when the projected outcome is strongly negative, not merely zero).

#### 12.6.3 Coupling to the Resilience-Debt Model

This is the first place in the paper where the **resilience-debt formulation directly closes a control loop**. Reactive healing reads `dE/dt` only as a passive metric on the dashboard; aggressive mode promotes it to a first-class trigger. The implication is concrete: under sustained nominal-but-imperfect load, the aggressive loop continues to fire `cache_flush @ Cache` or `api_error_suppression @ API` at low frequency, bending `E(t)` toward a tighter envelope and (per the cost coupling `Cost ∝ 1/SRI`) lowering the cumulative operational cost. This is the practical mechanism by which the system fulfils the central thesis of §15: that reliability is an *outcome variable*, and healing should optimise outcomes rather than just suppress alerts.

#### 12.6.4 Failure Modes & Safeguards

- **Over-firing**: the per-action cooldown (§12.4) and exhaustion detector remain in force. The aggressive loop *skips* exhausted actions in the ranking step.
- **Wrong choice under sparse history**: the `prior(a) = 0.01` term ensures every action gets explored at least once; subsequent fires use real measurements.
- **Cost runaway**: the `−0.05 · cost(a)` term and the bounded ΔX (clipped to [−1, +1]) keep the score within a known range. The min_lift_threshold (default 0.003) acts as a brake against negative-expected-value actions.
- **Disable switch**: admin-toggleable via `POST /api/healing/aggressive/toggle {enabled: false}` instantly halts the loop.

### 12.7 Ladder Synthesizer — Programs Writing Programs (v4, iter 30)

§12.3–§12.6 describe an engine that *selects* among a fixed, hand-authored
action ladder. The next conceptual step — and the contribution of this
section — is to make the **ladder itself an observable, learnable, and
self-modifiable object**: a small program that the engine continuously
rewrites from its own outcome history. The healing engine thereby joins
the class of systems that *write the programs that drive them* — a
practical instance of the "programs writing programs" pattern.

#### 12.7.1 The Static-Ladder Problem

The escalation ladders of §13.1 are crisp, explainable, and shipped in
source. They embody the engineer's prior belief about which corrective
action *ought* to dominate at each node. Two failure modes follow:

1. **Stale priors.** A workload shift (e.g. a new payment integration
   adding write load to DB) can invert the right ordering. The static
   ladder no longer matches the system under measurement; the adaptive
   selector (§12.3) walks past good actions to reach the historically
   "primary" one.
2. **Unobservable improvement.** Even with effectiveness tracking, the
   *ordering* is fixed. An action that quietly becomes the best choice
   in tier-2 position has no path to tier-1; its gain is bounded by how
   often the higher-tier actions exhaust themselves.

The synthesizer eliminates both modes by promoting the ladder from a
constant to a **piecewise-constant function of observed reliability gains
that is rewritten on a fixed schedule and persisted across restarts**.

#### 12.7.2 Gain Matrix

Let `H = {(node_i, action_i, ΔSRI_i)}` be the rolling history of
executed healings (from §12.3). For each pair `(n, a) ∈ Nodes × Actions`,
define an **observation score**

```
μ_{n,a}    = mean(ΔSRI_i  | node_i = n ∧ action_i = a)        (Eq. 12.7.1)
ρ_{n,a}    = mean(last-3  ΔSRI_i | node_i = n ∧ action_i = a)  (Eq. 12.7.2)
obs_{n,a}  = 0.6 · μ_{n,a} + 0.4 · ρ_{n,a}                     (Eq. 12.7.3)
```

`ρ_{n,a}` is a recency-weighted mean: a small subset of the most recent
executions, used to detect *regime change* (e.g. a CDN reconfiguration
that suddenly makes `cache_flush` highly effective for the API node).

The action also has a **golden-signal affinity** derived from the
urgency-normalised live signals (compare §5.2, §10):

```
priority_s = (1 − health_s) / Σ_s (1 − health_s),     s ∈ {latency, errors, saturation}
affinity_{n,a} = Σ_s effect_{a,s} · priority_s                  (Eq. 12.7.4)
```

where `effect_{a,s}` is the fixed action-effect profile (the same one
used by the adaptive-weights derivation of §12.5). `affinity_{n,a}` is
node-independent in its definition; node specificity arrives through the
empirical observation term.

The **gain matrix** combines the two:

```
gain_{n,a} = 0.7 · obs_{n,a} + 0.3 · affinity_{n,a}            (Eq. 12.7.5)
```

For a `(n, a)` pair with no history, `obs = 0` and the affinity term
alone determines the score (multiplied by 0.5 to discount un-observed
candidates relative to observed ones with equal affinity). This gives
new actions a credible cold-start position without letting them
unconditionally outrank empirically validated ones.

#### 12.7.3 Synthesis Operator

The synthesis operator `S : G ↦ L` maps a gain matrix `G` to a new
ladder `L`:

```
L(n) = sorted({a : gain_{n,a} > −0.05}, key = −gain_{n,a})[:K]   (Eq. 12.7.6)
```

with `K = 4` (the engine looks at the top four actions per node when
walking a ladder; tail entries are statistically dominated and waste
cooldown). If `L(n) = ∅` (all actions strictly below threshold),
`L(n)` falls back to the cold-start ladder of §13.1 — a conservative
safety net that prevents the synthesizer from emptying any ladder.

#### 12.7.4 Atomic Swap, Versioning, and Persistence

Each successful synthesis pass increments `version` and persists a
record to MongoDB collection `synthesized_ladders`:

```
{ version, timestamp, reason, ladder,
  previous_ladder, diff, gain_matrix, sri_baseline }
```

On obs boot, `load_persisted()` reads the highest-`version` document
and applies it directly to `healing_engine.escalation_ladder`. This
realises the principle that **the engine's source-of-truth program is
not the constant in source but the latest persisted record** — the
engine literally rewrites the program that drives it, and that rewrite
survives across process restarts.

The swap itself is atomic in two senses:

1. **In-process atomic.** A `threading.Lock` guards the dict assignment
   `self.engine.escalation_ladder = new_ladder`. No selector pass ever
   observes a partial ladder.
2. **In-database atomic.** The persistence step is async and runs
   outside the lock, so swap latency is bounded by a single dict
   replacement (~microseconds). If the persist fails, the in-memory
   swap still stands; the next loop tick retries persistence.

#### 12.7.5 Trigger Schedule

Two triggers fire the synthesis operator:

1. **Scheduled tick** — every `SYNTHESIS_INTERVAL_S = 120` seconds.
2. **Stagnation trigger** — if four or more SRI samples in the last
   `STAGNATION_TRIGGER_S = 60` seconds satisfy
   `max(SRI) − min(SRI) < 0.005` ∧ `mean(SRI) < 0.85`, an unscheduled
   synthesis fires immediately. This is the **causal coupling** to
   §15: a stagnant integral `E(t)` that is not being drained by reactive
   or aggressive healing is precisely the failure mode that demands a
   different program, not a different action.

#### 12.7.6 Rollback Guard

The synthesizer is itself an inference and may be wrong. To bound the
worst-case regret, every swap records `sri_baseline` (the SRI immediately
after the swap) and arms a **one-shot rollback check** that runs
`ROLLBACK_WINDOW_S = 60` seconds later. If

```
SRI(t_swap + 60) − sri_baseline < − 0.02                       (Eq. 12.7.7)
```

the synthesizer increments `version` once more, restores the previous
ladder, persists the rollback record, and disarms. Subsequent failures
on the now-restored ladder are handled by the next scheduled synthesis
— never by an immediate re-swap, which would induce oscillation.

#### 12.7.7 Operational Surface

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/healing/ladder/current` | GET | open | Live ladder + version + rollback-guard state |
| `/api/healing/ladder/history?limit=N` | GET | open | Version timeline with diffs |
| `/api/healing/ladder/gain-matrix` | GET | open | Current `gain_{n,a}` scores |
| `/api/healing/ladder/synthesize` | POST | admin | Force an immediate synth pass |
| `/api/healing/ladder/rollback` | POST | admin | Manual revert to previous version |
| `/api/healing/ladder/toggle` | POST | admin | Enable / disable the auto loop |

The dashboard renders these through a single component
(`LadderSynthesizerCard`) on the System Health tab. Each ladder entry
is a heat-coloured chip carrying its `gain_{n,a}` score; a "REWRITTEN"
badge and a `was: …` line surface every diff against the previous
version.

#### 12.7.8 Why This Is *Programs Writing Programs*

The escalation ladder is, formally, **a tiny domain-specific program**:
a finite map from node to ordered action sequence that drives every
adaptive-selection branch of §12.3. By making the engine emit a new
instance of that program from data and replace its own running config
with it, the engine satisfies the strict definition: a program (the
synthesizer) is writing a program (the new ladder) that another program
(the healing engine) then executes. The novelty is not the use of
machine learning — `gain_{n,a}` is a simple weighted mean — but the
**closed loop**: the program being rewritten is the *exact same
constant* the engine was hand-coded against, and the rewrite is
persistent and reversible at the same granularity (the ladder version)
that the engineer originally authored.

This closes a long-standing gap in the SRI design: prior sections
(§12.3–§12.6) make the engine *adaptive within a fixed program*; §12.7
makes the **program itself adaptive**, with the rest of the system —
versioning, persistence, rollback — providing the safety envelope.

### 12.8 Operational Phase Classifier (v5, iter 31)

§12.3–§12.7 give the engine an adaptive *what* (action selection) and an
adaptive *program* (ladder synthesis). Both still operate in a single,
implicit regime — they assume the system is **in a state where reactive
healing helps**. The **Operational Phase-Transition Diagram of Sunder
[14, 15]** contradicts that assumption: there are well-known phases in
which adding a healing action *worsens* the failure signature, and
there are phases in which the system needs a fundamentally different
cost-tradeoff between heavy and cheap actions. §12.8 introduces a
**phase classifier** that names the current regime — using the
taxonomy and composite-stress construction of [14] and the stability-
potential / eutectic-point framing of [15] — and **gates the other
engines** so they refuse to add stress when doing so would cross a
transition boundary.

#### 12.8.1 Composite Stress σ

The diagram defines composite operational stress as a weighted sum of
four golden-signal-derived axes. The classifier computes σ per service
node on a 5 s tick from the live `MetricsAggregator`:

```
σ_n = α · L̂_n + β · Q̂_n + γ · M̂_n + δ · Ê_n             (Eq. 12.8.1)
```

with `α + β + γ + δ = 1` and the defaults `(α, β, γ, δ) =
(0.30, 0.20, 0.25, 0.25)` (env-tunable via `PHASE_ALPHA_L`, etc.).
The hat denotes [0, 1]-normalisation:

```
L̂_n = clamp(L_n / L_ceil, 0, 1),    L_ceil = 1500 ms
M̂_n = saturation_n                  (already in [0, 1])
Q̂_n = saturation_{Queue}            (queue depth proxy)
Ê_n = clamp(E_n / 0.20, 0, 1)        (20 % error rate is saturated)
```

The composite-system σ is the mean of `σ_n` across nodes; the **worst
node** for visualisation is `argmax_n σ_n`.

#### 12.8.2 Phase Classification

The seven phases of the diagram partition `(L/L₀, M/M_cap)` space with
crisp thresholds, plus two cross-cutting "regime" phases that override
the geometric partition:

```
phase(n) =
  healing_saturation       if heal_saturated_globally()                 (Eq. 12.8.2a)
  retry_amplification      if retry_amplifying_at(n)                    (Eq. 12.8.2b)
  cascading_collapse       if σ_n > 0.85 ∧ (M̂_n > 0.95 ∨ L_n/L₀ > 20)   (Eq. 12.8.2c)
  cold_start               if traffic < 1 ∧ M̂ < 0.25 ∧ L/L₀ < 0.5
  jvm_saturation           if M̂_n > M_cap_threshold ∨ L_n/L₀ > 4
  warm_runtime             if M̂_n < 0.40 ∧ L_n/L₀ < 0.80
  stable_throughput        otherwise
```

with `M_cap_threshold = 0.80` (the GC-stall boundary from the diagram).
The cross-cutting detectors are evaluated first because they identify
**feedback signatures** that the geometric thresholds cannot see.

##### 12.8.2.1 Retry-Amplification Detector

Retry amplification is a *temporal*, not a *positional*, phenomenon —
it manifests as the simultaneous rise of traffic, errors, and latency
within a short window. The classifier maintains a 60-sample ring buffer
per node and compares its tail (last 3 samples) against its head:

```
retry_amplifying_at(n) ≡
  mean_3(traffic_n) > 1.6 · mean_pre(traffic_n)  ∧
  mean_3(error_n)   > 1.15 · mean_pre(error_n) ∧ mean_3(error_n) > 0.05 ∧
  mean_3(latency_n) > 1.4 · mean_pre(latency_n) ∧ mean_3(latency_n) > 100 ms
```

When any node satisfies this predicate, the system-level
`retry_amplification` flag is raised and propagated as a brake to
`AggressiveHealingMode.rank_actions()`:

```
rank_actions(A) =
  ∅                if phase_classifier.aggressive_braked              (Eq. 12.8.3)
  rank_observed(A) otherwise
```

§12.6 fires aggressively into rising σ; §12.8.3 short-circuits that
loop precisely when firing would extend the retry storm. This is the
direct mechanism by which the classifier **reduces resilience-debt
usage cost** — debt accrued per unit ΔSRI is highest in retry-
amplification phase, and the engine now refuses to spend there.

##### 12.8.2.2 Healing-Saturation Detector

Healing saturation is the meta-failure mode in which the engine's own
remediation actions are the dominant source of overhead. The classifier
samples `healing_engine.history` over the last `HEAL_SAT_WINDOW_S =
60 s`:

```
r = heal_rate_per_min / mean_|ΔSRI|_per_heal                          (Eq. 12.8.4)
heal_saturated ≡ r > 25  ∧  |samples| ≥ 5
```

This *r* is dimensionally `1 / (SRI · s)` — a unit of **stress per unit
reliability returned**. Above the threshold, the engine is paying more
operational cost than it is recovering in SRI; the policy response is
not to *stop* healing but to **change which healing is preferred**.
The classifier therefore raises a `synth_cost_penalty_boost` value that
the LadderSynthesizer reads on its next gain-matrix computation:

```
gain_{n,a} =
  0.7 · obs_{n,a} + 0.3 · affinity_{n,a}
  − 0.05 · synth_cost_penalty_boost · cost(a)                          (Eq. 12.8.5)
```

Under saturation `synth_cost_penalty_boost = 2.0`; cheap actions
(`cache_flush` cost = 0.10, `rate_limit` cost = 0.15) outrank
heavyweight ones (`circuit_breaker` cost = 0.35,
`connection_pool_reset` cost = 0.25). This is the direct mechanism
by which the classifier **enables faster recovery**: the next synthesis
pass elects a cheaper ladder, the heal-rate drops, *r* falls below
threshold, and the system exits saturation without operator action.

#### 12.8.3 Eutectic Distance

The diagram identifies an **eutectic point Ψ_c** — the optimal balance
of (L, Q, M, E) at which reliability and throughput co-maximise. The
classifier defines it as a fixed coordinate

```
Ψ_c = (L̂ = 0.05, Q̂ = 0.30, M̂ = 0.55, Ê = 0.02)                      (Eq. 12.8.6)
```

with `L̂ = L / L_ceil` (so `L̂ = 0.05 ⇒ L ≈ 75 ms ⇒ L/L₀ ≈ 1.5` —
comfortable headroom over the 50 ms baseline). The classifier reports
per-node distance in normalised 4-space, scaled to `[0, 1]` so it can
be displayed alongside σ:

```
d_n = ‖(L̂_n, Q̂_n, M̂_n, Ê_n) − Ψ_c‖₂ / 2                              (Eq. 12.8.7)
```

This is the metric by which the engine **builds reliability per
improvement cycle**: every ladder version (§12.7.4) now carries
`phase_at_swap` as a tag. Across versions, the synthesizer can
correlate ladder choice with phase, *not just with average ΔSRI*. A
ladder that performs well in `warm_runtime` but poorly in
`jvm_saturation` is identifiable from the version timeline alone — a
piece of knowledge that was structurally invisible before §12.8.

#### 12.8.4 Closing the Loop

The three new closed loops formed by §12.8 are:

1. **σ → phase → AggressiveHealing brake** — adds *no* stress in a
   retry storm, preventing the loop from extending itself. Net cost
   reduction on each storm: the resilience-debt integral `E(t)` from
   §15 accumulates with the storm but **stops accumulating
   healing-induced debt** for its duration.
2. **σ → phase → SynthCostPenalty boost** — cheaper ladders elected
   during healing saturation; the heal rate (and therefore *r*) falls;
   the boost relaxes back to 1.0. A fast, automatic mode-switch with
   no human in the loop.
3. **phase → ladder tag → cross-phase learning** — synthesizer
   versions now carry their regime; future synthesis passes can be
   extended to weight observations by phase-similarity, replacing the
   current phase-blind `mean_ΔSRI` with a per-phase mean.

Together, these realise the diagram's prescription not as a dashboard
artefact but as a **policy active in the remediation engine**. The
operator sees the phase on the dashboard; the engine has already acted
on it.

#### 12.8.5 Operational Surface

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/phase/state` | GET | open | Per-service phase + σ + Ψ_c distance + retry-amp/heal-sat flags + policy outputs |
| `/api/phase/history?limit=N` | GET | open | σ + phase trajectory for dashboard sparkline |

The dashboard renders these through two complementary components on the System Health tab:

1. **`PhaseTransitionCard`** — the worst-system phase is shown as a colour-coded pill; retry-amp and heal-sat flags appear as inline banners with their *exact policy effect on the engine* spelled out ("Aggressive healing braked", "synthesizer cost-penalty ×2.0"); a per-service row gives σ, L/L₀, M/M_cap, and a 12 × 6 px phase-space dot.
2. **`PhaseDiagramView`** — a full 2D phase chart explicitly inspired by the iron-carbide diagram of metallurgy (§12.8.6 below).

#### 12.8.6 Iron-Carbide-Style Phase Diagram

The metallurgical phase diagram of iron and carbon is, in essence, a
two-axis chart whose closed regions name the stable phase at every
(composition, temperature) coordinate, with phase boundaries drawn as
isotherms and a small set of *invariant points* (eutectic, eutectoid,
peritectic) flagged explicitly. The same construction transfers to a
software service with no change of meaning — a transfer first made
explicit by Sunder [14, 15] in the operational-phase diagram that this
section's `PhaseDiagramView` renders:

| Metallurgy axis | Operational analogue |
|-----------------|----------------------|
| carbon content (%C, horizontal)              | **M / M_cap** (memory saturation, horizontal, 0 → 1) |
| temperature (°C, vertical)                   | **L / L₀** (latency ratio, vertical, 0 → 20, √-scaled) |
| α / γ / δ / cementite phase fields           | cold_start / warm_runtime / stable_throughput / jvm_saturation / cascading_collapse |
| eutectic point (4.3 %C, 1147 °C)             | **Ψ_c** at (M̂ = 0.55, L/L₀ = 1.5) |
| A₁ / A₃ / Acm boundary curves                | the geometric thresholds of Eq. 12.8.2 |

A few points are worth making explicit:

1. **The Y-axis is √-scaled.** Latency in real systems spans three or
   four orders of magnitude (50 ms baseline, 1500 ms ceiling). A linear
   axis collapses the entire operating band into the bottom 5 % of the
   chart. The square-root scale spreads `L/L₀ ∈ [0, 4]` over more
   than half the vertical extent — exactly where the
   cold_start / warm_runtime / stable_throughput / jvm_saturation
   boundaries lie — while still showing the cascading-collapse region
   at the top.
2. **Two of the seven phases are absent from the chart.** Retry
   amplification and healing saturation are *regime* phases (Eq. 12.8.2a,
   12.8.2b): they are temporal feedback signatures that override any
   position-based classification. Painting them as regions would be
   a category error — a service at exactly (0.55, 1.5) can be in
   `stable_throughput` *or* `retry_amplification` depending on whether
   its time-derivative satisfies the retry-rising predicate. The
   diagram therefore renders them as overlay banners on top of the
   geometric chart, faithful to the diagram-as-classifier distinction.
3. **Each service is a moving point.** Per-service position is the
   live (M/M_cap, L/L₀) coordinate; the dot is ringed by its current
   *phase* colour (the inner fill remains the service's identity
   colour). A dashed trajectory tail of the last 20 samples shows the
   recent path through phase space — operators can read at a glance
   not only the current phase but the direction the service is
   travelling, which is the leading indicator of an imminent
   transition.
4. **Ψ_c is the engine's gravitational centre.** Healing actions are
   in effect a force field whose long-run integral pulls each service
   toward Ψ_c. The eutectic distance `d_n` of Eq. 12.8.7 is the
   instantaneous magnitude of that vector; the trajectory tail is its
   path integral. A dashboard that combines the *force* (banner) with
   the *position* (dot) with the *history* (tail) is a compact and
   complete real-time visualisation of the policy described in
   §12.8.1–§12.8.4.

The two visualisations are not redundant: `PhaseTransitionCard`
prioritises *what the engine is doing right now* (banners + per-service
rows with exact policy labels), while `PhaseDiagramView` prioritises
*where every service sits in phase space and how it got there*. The
former is the textual readout, the latter is the spatial readout, and
together they expose the entire output of §12.8 to a human operator
without abstraction loss.

### 12.9 RUM Ladder Learner — Reliability from User-Felt Outcomes (v6, iter 32)

§12.3–§12.8 grade healing decisions by **internal** observables: ΔSRI,
composite stress σ, eutectic distance. None of these are quantities the
end user can feel. A user feels three things and only three:

1. **`page_load_ms`** — how long the page took before they could
   interact with it,
2. **`perceived_speed`** — a 0..100 RUM-derived satisfaction score
   that depends on early visual stability and time-to-first-byte,
3. **`error_shown_rate`** — the fraction of their requests that
   surfaced an HTTP / exception error.

A healing decision that moves SRI by 0.03 but leaves all three of these
unchanged is, from the user's perspective, a no-op. The cumulative
result of a *sequence* of healings is what the user can in fact perceive
— a chain like `circuit_breaker → queue_drain → connection_pool_reset
→ rate_limit → cache_flush → api_error_suppression` is a single
remediation **strategy** whose user-felt effect cannot be attributed to
any one of its actions in isolation. The `RumLadderLearner` of §12.9
mines these chains and feeds the result back into §12.7's ladder
synthesiser, **closing the reliability loop with telemetry the user
actually generates.**

#### 12.9.1 Sequence Mining

Let `A = {a₁, a₂, …, aₙ}` be the chronologically sorted list of healing
annotations from `correlation_tracker._annotations`, each with timestamp
`tᵢ`, target node, and action_id. The learner groups them into chains
under a temporal contiguity predicate:

```
S = ⋃_k σ_k        where each σ_k = {aᵢ, aᵢ₊₁, …, aⱼ}
satisfies
  ∀ p ∈ [i, j) :  t_{p+1} − t_p ≤ SEQ_WINDOW_S      (Eq. 12.9.1)
  and the predicate is violated at j+1 (or j is the last index).
```

with `SEQ_WINDOW_S = 15 s`. Singletons (`|σ_k| = 1`) are discarded —
§12.7's per-action mean ΔSRI already covers them. The learner therefore
operates exclusively on the **emergent** behaviour of action chains.

#### 12.9.2 Composite RUM Gain

For each surviving chain `σ_k`, let `t_first, t_last` denote its first
and last action timestamps. The learner draws two RUM windows from
`cx_tracker._samples`:

```
B(σ_k) = { s ∈ samples :  t_first − W ≤ s.t < t_first }
A(σ_k) = { s ∈ samples :  t_last  < s.t ≤ t_last + W }
                                                       (Eq. 12.9.2)
```

with `W = RUM_BEFORE_AFTER_S = 30 s`. The before / after means of
each user-felt observable produce three deltas; the composite gain is:

```
g_pl  = clamp(−(mean_A(pl) − mean_B(pl)) / 500, −1, 1)         (12.9.3a)
g_ps  = (mean_A(ps) − mean_B(ps)) / 100                         (12.9.3b)
g_er  = −100 · (mean_A(er) − mean_B(er))                        (12.9.3c)

gain(σ_k) = 0.4 · g_ps · 100 + 0.4 · g_pl + 0.2 · g_er          (12.9.4)
```

The 500 ms normaliser in `g_pl` calibrates a half-second page-load
improvement to ≈ +1 contribution. The `× 100` on `g_ps` brings the
0..100 perceived-speed scale into commensurate units with the other
two terms. Any `None` mean (insufficient samples in the corresponding
window) contributes 0 — degenerating the gain gracefully rather than
disqualifying the chain.

#### 12.9.3 Persistent Top-K with Per-Node Index

The learner maintains an in-memory top-K (default `K = 30`) of the
highest-gain validated chains globally, plus a per-node top-`K_n` index
(`K_n = 6`) for fast O(1) lookup by the ladder synthesiser. Each chain
is keyed by its signature `(modal_node, chain_str)` where `chain_str =
action₁→…→action_n`; duplicate signatures are merged with `$max` on
gain. The full record is upserted into MongoDB collection
`rum_validated_sequences`:

```
{ node, chain, actions[], nodes[], length,
  cx_delta { page_load_ms_delta, perceived_speed_delta,
             error_shown_rate_delta, samples_before, samples_after,
             rum_gain },
  rum_gain, first_seen_at, last_seen_at }
```

On obs boot, the top-K is rehydrated from this collection sorted by
`rum_gain` descending — the engine starts each restart with the
cumulative user-validated knowledge of every previous run.

#### 12.9.4 Closed-Loop Feedback into §12.7

The synthesiser's per-(node, action) gain matrix of Eq. 12.7.5 was
already augmented by Eq. 12.8.5 with a phase-aware cost penalty. §12.9
adds one further term — a **RUM bonus**:

```
rum_bonus_{n,a} = RUM_BONUS_COEFF · max_{σ : a ∈ σ, modal_node(σ) = n}
                  ( gain(σ) / max_σ gain(σ') )                   (12.9.5)
gain_{n,a} ←  gain_{n,a}  +  rum_bonus_{n,a}                     (12.9.6)
```

with `RUM_BONUS_COEFF = 0.15`. The normalisation by the per-node top-K
maximum keeps the additive term bounded in `[0, RUM_BONUS_COEFF]`
regardless of the absolute magnitude of the gain — a system whose
user-felt deltas are tiny in absolute terms still produces a meaningful
ranking.

The full per-iteration gain decomposition is now:

```
gain_{n,a}
  =   0.7 · obs_{n,a}                         (internal ΔSRI history)
    + 0.3 · affinity_{n,a}                    (golden-signal urgency)
    − 0.05 · cost_boost · cost(a)             (cost penalty, phase-modulated)
    + RUM_BONUS_COEFF · rum_norm(a, n)        (user-validated bonus, §12.9)
```

Every term is principled and bounded, and the four contributions cover
the four perspectives we have on a healing action: the **engine's**
historical view, the **signal**'s current urgency, the **operator's**
cost concern, and the **user's** felt outcome.

#### 12.9.5 Why Sequences, Not Individual Actions

§12.7's gain matrix already accumulates per-action ΔSRI means. A
naïve approach would extend this to per-action RUM deltas. We
deliberately do **not** do that because:

1. **RUM noise budget**. Page-load measurements come in at the rate of
   user navigations — far slower than the engine's 5-s healing cadence.
   Per-action attribution requires aligning one healing event with a
   handful of RUM beacons whose 95 % CIs are typically wider than the
   per-action effect. The signal-to-noise ratio is too low.
2. **Emergent behaviour is non-decomposable**. A `circuit_breaker`
   alone may add user-visible failures (fast-fail responses). The same
   `circuit_breaker` preceded by `queue_drain` and followed by
   `connection_pool_reset` and `cache_flush` produces, on the same
   workload, dramatically lower page_load_ms because the queue head no
   longer blocks the cache layer. The sequence-level view captures the
   composite; the per-action view does not.
3. **Operational doctrine, not just data**. A chain is an explicit,
   nameable *strategy* an operator can reason about and reuse. Promoting
   chains to first-class objects (with their own MongoDB collection,
   API, and dashboard card) makes the engine's knowledge legible to
   humans in a way that a per-action coefficient table never is.

The price paid is one assumption: the modal node of a chain is taken
as its primary node. In practice the auto-healing loop almost always
fires on the worst node first, so the modal-node heuristic recovers the
intended attribution > 95 % of the time. The few "mixed-node" chains
that escape are still useful (their bonus applies to all nodes in
their per-node index — i.e. wherever the modal-node matches).

#### 12.9.6 Operational Surface

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/healing/rum-sequences/top?limit=N` | GET | open | Top-K validated chains with full per-chain RUM deltas |
| `/api/healing/rum-sequences/status` | GET | open | Learner runtime state (top_total, nodes covered, cadence, last pass) |
| `/api/healing/rum-sequences/run-now` | POST | admin | Force an immediate mining pass |

The dashboard surfaces this through `RumValidatedSequencesCard` on the
System Health tab. Each row shows the colour-coded modal-node pill, the
ranked sequence number, the composite `gain`, the three RUM deltas with
direction indicators, the full chain rendered with `→` arrows between
action pills, and a one-line provenance footer (samples before/after,
discovery time). Sequences with insufficient RUM data display deltas
as `—` — they remain in the top-K (they have validated *sequences*,
just not *deltas*), but their bonus contribution is 0 until real-user
data arrives.

#### 12.9.7 The Closed Loop, Drawn End-to-End

Combining §12.7, §12.8 and §12.9, the full closed loop driving the
engine on every cycle is:

```
                    ┌──────────────────────────┐
            ┌──────▶│  HealingEngine selects  │──────┐
            │       │  action a* for node n*  │      │
            │       └──────────────────────────┘      │
            │                                          ▼
            │                              ┌───────────────────────┐
            │                              │ a* applied; system    │
            │                              │ produces SRI delta    │
            │                              │ AND emits a RUM       │
            │                              │ trace over the next   │
            │                              │ ~30 s of user load    │
            │                              └───────────────────────┘
            │                                          │
            │                                          ▼
            │       ┌──────────────────────────┐  ┌───────────────────┐
            │       │ PhaseClassifier reads σ,  │  │ correlation_tracker│
            │       │ classifies phase, sets    │  │ annotates (a*, t)  │
            │       │ aggressive_braked +       │  │ cx_tracker logs    │
            │       │ synth_cost_penalty_boost  │  │ RUM beacons        │
            │       └──────────────────────────┘  └───────────────────┘
            │                                          │
            │                                          ▼
            │                              ┌───────────────────────┐
            │                              │ RumLadderLearner      │
            │                              │ groups annotations    │
            │                              │ into chains, aggregates│
            │                              │ RUM deltas, emits per- │
            │                              │ node bonus map        │
            │                              └───────────────────────┘
            │                                          │
            │                                          ▼
            │       ┌────────────────────────────────────────────────┐
            │       │ LadderSynthesizer.compute_gain_matrix combines  │
            │       │  · 0.7 · obs        (SRI history)               │
            │       │  · 0.3 · affinity   (signal urgency)            │
            │       │  − 0.05 · cost_boost · cost(a)  (§12.8)         │
            │       │  + RUM_BONUS · rum_norm(a, n)   (§12.9)         │
            │       │ → atomically swaps in a new escalation_ladder   │
            │       └────────────────────────────────────────────────┘
            │                                          │
            └──────────────────────────────────────────┘
```

Each arrow is a directed edge in the live data flow — not an
illustration. The engine reads from the new ladder on its next tick.

The §12.7 → §12.8 → §12.9 sequence adds, in order: **adaptive program**
(rewritable ladder), **regime awareness** (phase + brakes), and
**user-validated ground truth** (RUM gains). Together they realise
the SRI design's terminal aspiration — *an engine that decides what to
heal, when to refuse to heal, how to rank its options, and whose
ground truth is the experience of the people the system exists for.*

---

## 13. Escalation Ladders & Cross-Node Healing

### 13.1 Per-Node Escalation

Each infrastructure node has an **ordered list of alternative corrective actions**. When the primary action is exhausted (proven ineffective), the adaptive selector automatically escalates to the next action in the ladder. The values below are the **cold-start** ladders shipped in source (see `obs/engines/ladder_synthesizer.py :: DEFAULT_LADDER`); at runtime the Ladder Synthesizer (§12.7) rewrites these from observed reliability gains and persists each new version. Query the live ladder with `GET /api/healing/ladder/current`.

| Node | Cold-start Escalation Order |
|------|-----------------------------|
| API | rate_limit -> circuit_breaker -> api_error_suppression -> cache_flush |
| Cache | cache_flush -> connection_pool_reset -> rate_limit |
| Backend | circuit_breaker -> rate_limit -> queue_drain -> connection_pool_reset |
| DB | connection_pool_reset -> cache_flush -> circuit_breaker |
| Queue | queue_drain -> rate_limit -> connection_pool_reset |

### 13.2 Cross-Node Healing via Graph Adjacency

When ALL actions in a node's escalation ladder are exhausted or on cooldown, the system attempts **cross-node healing** — applying corrective actions to the node's neighbors in the infrastructure graph:

| Node | Neighbors (healing targets) |
|------|---------------------------|
| API | Cache, DB, Queue |
| Cache | API, DB |
| Backend | Queue |
| DB | API, Cache |
| Queue | API, Backend |

For each neighbor, the system walks that neighbor's full escalation ladder (not just the primary action), maximizing the chance of finding an effective action.

### 13.3 Rationale

Cross-node healing is based on the graph-theoretic insight that a node's degradation often originates from pressure on its connected neighbors. If the API has high errors, it may be because the Cache is serving stale data or the DB is timing out. Healing the neighbor resolves the root cause upstream.

### 13.4 Scaling Actions (v7, iter 33)

§13.1–§13.3 cover **dampener** actions — interventions that *reduce
demand or isolate failures* (cache flushes, rate limits, circuit
breakers, queue drains). They share three properties: low cost,
short cooldown, and limited persistence (≤ 30 s dampener bias).
When the system is *under-resourced* rather than *over-stressed*,
these actions cannot help — there is no demand to dampen further;
the deployed capacity is simply insufficient.

The capacity-expansion family — `scale_out_frontend`,
`scale_out_cache_node`, `scale_out_db_read_replica` — fills this
gap. The three new actions are the first in the action set whose
*physical effect* is to add infrastructure rather than to suppress
load:

| Action | Target node | Cost | Cooldown | Effect | Dampener persistence |
|--------|-------------|------|----------|--------|----------------------|
| `scale_out_frontend`       | Frontend | 0.50 | 180 s | latency −45 %, saturation −60 % | 120 s |
| `scale_out_cache_node`     | Cache    | 0.40 | 150 s | latency −50 %, saturation −65 % | 120 s |
| `scale_out_db_read_replica`| DB       | 0.60 | 240 s | latency −40 %, saturation −55 % | 120 s |

Their integration into the engine is governed by three design
choices that follow directly from the §12 framework:

1. **Highest cost in the action set.** `cost(scale_*) ∈ [0.40, 0.60]`
   compared to `[0.05, 0.35]` for every dampener action. Substituted
   into the synthesizer's gain matrix (Eq. 12.8.5, with iter 32
   addendum Eq. 12.9.6):

   ```
   gain_{n, scale_out_*} ≤ gain_{n, dampener_*}  +  (Δcost · 0.05 · cost_boost)
   ```

   This means that under default `cost_boost = 1`, a scaling action
   must out-perform a comparable dampener by at least ~0.025 in
   observed ΔSRI before the synthesizer promotes it past the dampener
   in the synthesised ladder. The cost penalty is therefore a
   **principled, automatic guard against premature scale-out**.

2. **Healing-saturation phase doubles the brake.** When the Phase
   Classifier flags `healing_saturation` (Eq. 12.8.4 — heal-rate ÷
   mean |ΔSRI| exceeds 25), `cost_boost = 2.0`. The scaling penalty
   doubles to ~0.05; cheap dampener actions outrank scaling by an
   even wider margin. This explicitly prevents **scale-out
   thrashing on top of dampener thrashing** — when the engine is
   already over-correcting, the worst possible next action is to
   add infrastructure that will become idle once the over-correction
   subsides.

3. **Long dampener persistence reflects physical reality.**
   Dampener actions hold their bias for ≤ 30 s — they correspond to
   transient demand suppression. Scaling actions persist their
   dampener for 120 s, modelling the fact that an additional
   Frontend replica or DB read-replica *remains online* across many
   healing cycles. The synthesizer's `obs` term (Eq. 12.7.5) reads
   ΔSRI deltas from each individual healing record; a long
   persistence means a scaling action's observation is implicitly
   "amortised" across the 120 s window it influences, encouraging
   the synthesizer to reward it for sustained, not just instantaneous,
   improvement.

#### 13.4.1 Sequence Participation

Scaling actions are full first-class participants in the engine's
sequencing logic. They are valid moves in:

- The classical escalation walk of §13.1 (HealingEngine's
  `escalation_ladder["Frontend"] = ["scale_out_frontend"]` is the
  primary action for the Frontend node — the first action the
  engine will reach for when Frontend latency exceeds 200 ms or
  saturation crosses 70 %).
- The §12.7 ladder-synthesis ranking — they appear in `ALL_ACTIONS`
  and are scored alongside every other action per node.
- The §12.9 RUM-validated sequence mining — a chain like
  `connection_pool_reset → scale_out_db_read_replica` is exactly the
  pattern the learner is designed to discover (a dampener that
  partially helped, followed by capacity addition that resolved
  the remaining gap). Such chains will dominate the per-node top-K
  index once they are observed.

A live snapshot of synthesised ladder v74 (iter 33 boot) demonstrates
emergent ordering produced purely by affinity + cost reasoning — no
hand authoring of scaling positions:

```
Frontend: queue_drain → rate_limit → scale_out_cache_node → scale_out_db_read_replica
API:      queue_drain → connection_pool_reset → scale_out_cache_node → rate_limit
Cache:    queue_drain → scale_out_frontend → rate_limit → scale_out_db_read_replica
Backend:  queue_drain → rate_limit → scale_out_cache_node → scale_out_frontend
DB:       queue_drain → rate_limit → scale_out_cache_node → scale_out_frontend
Queue:    scale_out_cache_node → scale_out_frontend → scale_out_db_read_replica → rate_limit
```

Three observations on this snapshot are worth recording:

- Every node's ladder now includes at least two scaling actions in
  positions 3–4, even before any scale-out has fired in production.
  This is the synthesizer's affinity-based prior in action: scaling
  actions' high saturation-affinity coefficient (`0.65`–`0.75`)
  gives them a meaningful cold-start position whenever the live
  signal-priority weights saturation highly.
- Cross-node scaling appears in the Cache ladder (`scale_out_frontend`
  in position 2) because adding Frontend capacity reduces the
  upstream request rate that hits the cache layer. This is
  emergent — the synthesizer derived it purely from per-node golden-
  signal urgency weights, *without* an explicit cross-node
  dependency model.
- `scale_out_db_read_replica` carries the highest cost (0.60) and
  therefore the strongest cost penalty (−0.030). It only reaches
  position 3 in DB and position 4 in Frontend, Cache; not yet in
  the top-4 of API or Backend. This is exactly the conservative
  default we want: the most expensive action must prove itself by
  *observation* (positive ΔSRI in the heal history) before it
  outranks cheaper alternatives.

#### 13.4.2 Closure of the §12 Loop

§12.7 made the *program* (ladder) adaptive; §12.8 made the *regime
classifier* gate over-correction; §12.9 made *user-felt RUM* the
ultimate grader. §13.4 adds the missing **capacity dimension** to
the action set so the engine can respond to under-provisioning, not
just to demand spikes. With this addition, the action set spans the
two physically distinct levers an operator has: **reduce demand or
increase supply**, with the synthesizer choosing between them on
the basis of cost, observation, regime, and user-felt outcome — a
genuinely complete remediation surface.

---

## 14. Healing Stagnation Detection

### 14.1 Definition

**Healing stagnation** occurs when:
- The SRI remains below the health threshold
- The healing engine is actively executing actions
- Every action produces zero marginal improvement (sri_delta < 0.001)
- All actions in the escalation ladder AND all cross-node actions are exhausted

### 14.2 Detection

The system detects stagnation when `auto_heal_cycle()` completes with:
- `healing_needed = True` (SRI is degraded)
- `executed = []` (no action could be selected)
- `total_exhausted > 0` (at least one action has been proven ineffective)

### 14.3 Response

A `healing_stagnation` event is broadcast via WebSocket containing:
- The identified root cause node
- List of all exhausted action IDs
- Current SRI and dip magnitude
- Timestamp

This signals to operators (or a higher-level orchestrator) that the current corrective action repertoire is insufficient for the observed failure mode, and human intervention or new action types are needed.

### 14.4 Significance

Stagnation detection solves a fundamental problem in autonomous systems: **knowing when you don't know**. Rather than continuing to waste resources on ineffective actions, the system explicitly acknowledges its limitations — a form of machine self-awareness absent from all prior auto-healing systems.

---

## 15. Correction Factor Model

### 11.1 Definition

The **Correction Factor (CF)** quantifies how effectively a remediation action improved a specific golden signal, normalized by the available room for improvement:

```
CF(signal) = Δ(health) / (1.0 - health_before)
```

Where:
- **health_before** = signal health score [0,1] before the action
- **Δ(health)** = health_after - health_before
- **CF ∈ [0, 1]** where 1.0 = full recovery, 0.0 = no improvement

### 11.2 Interpretation

| CF Range | Meaning |
|----------|---------|
| 0.8 – 1.0 | Action nearly or fully restored this signal |
| 0.5 – 0.8 | Significant improvement, but residual degradation remains |
| 0.2 – 0.5 | Moderate improvement |
| 0.0 – 0.2 | Minimal impact on this signal |

### 11.3 Utility

Correction Factors enable:
- **Action effectiveness profiling**: Over time, learn which actions best address which signals
- **Remediation optimization**: Prioritize actions with higher historical CFs for the degraded signal
- **Feedback-driven tuning**: Adjust action parameters based on measured effectiveness
- **Accountability**: Quantitative proof that remediation worked (or didn't)

---

## 16. Closed-Loop Architecture

The complete system forms a **closed feedback loop**:

```
    ┌────────────────────────────────────────────┐
    │                                            │
    ▼                                            │
 COLLECT ──▶ ANALYZE ──▶ DETECT ──▶ HEAL ──▶ MEASURE
 (metrics)   (SRI,       (alerts)   (auto)    (correction
              golden,                          factors)
              CX)                                │
    ▲                                            │
    │                                            │
    └────────────────────────────────────────────┘
                   FEEDBACK LOOP
```

This is fundamentally different from open-loop monitoring (collect → alert → page human → human fixes) or simple auto-scaling (metric > threshold → add resource). The closed loop:
1. Continuously models the system as a graph
2. Detects degradation through spectral properties
3. Automatically applies targeted remediation
4. Measures the remediation's actual effectiveness per signal
5. Feeds results back into the model

> **Note on the distributed implementation (§6.1):** in the two-process deployment, the COLLECT vertex of the loop physically lives in the main app, while ANALYZE/DETECT/HEAL/MEASURE all live in obs. The HTTP boundary between them is itself a measured edge — its latency is included in the rolling SRI window because the main app's middleware records its own request latency *after* emitting telemetry, while obs records the per-event reception time independently. The loop closes correctly because both clocks see the same set of events; they just see them with a sub-millisecond localhost offset. This offset is empirically below the 30 s SRI window resolution and is therefore not modelled separately.

---

## 17. Baseline Calibration

### 13.1 The Cold-Start Problem

Spectral metrics require sufficient data to be meaningful. With zero traffic, all edge weights are minimal, producing near-zero SRI — a misleading "critical" reading for a system that is actually idle and healthy.

### 13.2 Warmup Blending

The system solves this with a progressive blending strategy:
- A **baseline SRI** represents the expected healthy state
- During a warmup period (defined by a request count threshold), the reported SRI is a weighted blend of the baseline and the computed value
- The blend factor transitions linearly from 100% baseline to 100% computed
- After warmup completes, the system reports only computed values

This ensures:
- No false alarms during startup or low-traffic periods
- Smooth transition to real metrics as data accumulates
- The baseline acts as a prior belief that is updated with evidence

---

## 18. Results & Observations

From deployment in a production e-commerce environment:

### 14.1 Leading Indicator Behavior

SRI consistently detected degradation **before** individual golden signal thresholds were breached. In observed incidents:
- SRI dropped below the warning threshold while all individual signals were still within acceptable ranges
- The Fiedler vector correctly identified the weakening link 30–60 seconds before the first alert fired

### 14.2 Alert-Driven Healing Effectiveness

When alert-driven healing was enabled:
- Mean Time to Recovery (MTTR) was effectively zero — remediation triggered within the same alert cycle
- Correction Factors averaged 40–70% across golden signals, indicating meaningful but not over-corrective healing
- No oscillation observed due to cooldown constraints

### 14.3 Customer Experience Correlation

SRI showed strong correlation with Apdex:
- SRI > 0.5 consistently corresponded to Apdex > 0.85 ("Good" or better)
- SRI < 0.2 consistently corresponded to Apdex < 0.7 ("Fair" or worse)
- This validates that spectral resilience is a meaningful proxy for user experience

---

## 19. Comparison with Existing Solutions

| Capability | Datadog | Grafana | PagerDuty | Netflix Chaos | **SRI System v2** |
|-----------|---------|---------|-----------|--------------|-------------------|
| Per-component metrics | Yes | Yes | No | No | Yes |
| Composite health index | No | No | No | No | **Yes (SRI)** |
| Graph-theoretic model | No | No | No | No | **Yes (Laplacian)** |
| Structural analysis (FEA) | No | No | No | No | **Yes (Von-Mises)** |
| Predictive trend analysis | Limited | No | No | No | **Yes (polynomial)** |
| Golden signal tracking | Partial | Manual | No | No | **Yes (built-in)** |
| Customer experience (Apdex) | Yes | Plugin | No | No | **Yes (built-in)** |
| Bottleneck identification | Manual | Manual | No | Post-mortem | **Auto (Fiedler+FEA)** |
| Auto-remediation | Limited | No | No | No | **Yes (6 actions)** |
| Adaptive action selection | No | No | No | No | **Yes (self-learning)** |
| Stagnation detection | No | No | No | No | **Yes** |
| Escalation ladders | No | No | No | No | **Yes (per-node)** |
| Cross-node healing | No | No | No | No | **Yes (graph adj.)** |
| Multi-CA simultaneous | No | No | No | No | **Yes (FEA-driven)** |
| Correction factor tracking | No | No | No | No | **Yes** |
| Closed feedback loop | No | No | No | No | **Yes** |

---

## 20. Applications & Extensibility

### 16.1 Direct Applications

- **E-commerce platforms**: Monitor checkout → payment → fulfillment pipeline resilience
- **Microservice architectures**: Model service mesh as graph, detect cascading failures
- **Cloud infrastructure**: Map VPC/subnet/service dependencies
- **IoT networks**: Sensor mesh connectivity monitoring
- **Financial systems**: Trading pipeline resilience

### 16.2 Extensions

The framework naturally extends to:
- **Directed graphs** (asymmetric service dependencies)
- **Temporal spectral analysis** (how eigenvalues evolve over time → predict failures)
- **Multi-layer graphs** (separate infrastructure, application, and business layers)
- **Machine learning on spectral features** (train classifiers on eigenvalue distributions)
- **Distributed SRI** (each service computes its local contribution, aggregated centrally)

---

## 21. Conclusion

The Spectral Resilience Index system, now augmented with Finite Element Analysis, polynomial interpolation, and adaptive self-learning remediation, represents a **third-generation observability platform**:

- **1st generation**: Per-component monitoring (Prometheus, Datadog) — passive observation
- **2nd generation**: Threshold-based auto-healing — reactive, brittle, prone to stagnation
- **3rd generation (this work)**: Spectral-structural analysis with adaptive remediation — proactive, self-learning, stagnation-aware

The key advances are:

1. A **mathematically rigorous** health metric (SRI) grounded in algebraic graph theory
2. **Structural analysis** (FEA) that quantifies component stress using engineering mechanics
3. **Predictive dynamics** via polynomial interpolation of the health time series
4. **Self-learning healing** that detects its own ineffectiveness and autonomously diversifies
5. **Formal stagnation detection** — the system knows when it cannot help and escalates

This combination — spectral analysis for detection, FEA for quantification, interpolation for prediction, and adaptive selection for remediation — creates the first **fully autonomous, self-aware infrastructure health management system**.

---

## 22. Intellectual Property Notice

**Copyright (c) 2026. All Rights Reserved.**

This document and the systems, methods, algorithms, and architectures described herein constitute proprietary intellectual property. Specifically:

1. **The Spectral Resilience Index (SRI)** as applied to infrastructure health monitoring
2. **The FEA-based Component Stress Analysis** using Laplacian stiffness, pseudo-inverse displacement, and Von-Mises yield detection
3. **The SRI Polynomial Interpolation** for predictive trend classification and proactive healing
4. **The Adaptive Self-Learning Action Selector** with effectiveness tracking, escalation ladders, cross-node healing, and stagnation detection
5. **The Correction Factor Model** for per-signal remediation effectiveness measurement
6. **The Multi-CA Simultaneous Execution** driven by FEA yield analysis and trend severity
7. **The Alert-to-Heal Closed Loop** architecture combining all of the above
8. **The Baseline Calibration via Warmup Blending** method

**Rights Reserved:**
- Reproduction, distribution, or transmission of this document in any form
- Creation of derivative works based on the methods described
- Implementation of the composite system architecture without license
- Use of the term "Spectral Resilience Index" or "SRI" in the context of infrastructure monitoring without attribution

**Prior Art Establishment:**
This document serves as a dated record of original work for the purpose of establishing priority in intellectual property claims. The concepts described herein were independently developed and first implemented in April 2026.

**Patent Notice:**
The methods and systems described in this document may be subject to patent application. Interested parties should contact the author before implementing any described methodology.

---

## 23. References

[1] Beyer, B., Jones, C., Petoff, J., & Murphy, N.R. (2016). *Site Reliability Engineering: How Google Runs Production Systems*. O'Reilly Media. Chapter 6: Monitoring Distributed Systems.

[2] Apdex Alliance. (2007). *Apdex Technical Specification v1.1*. https://www.apdex.org/

[3] Fiedler, M. (1973). "Algebraic connectivity of graphs." *Czechoslovak Mathematical Journal*, 23(2), 298-305.

[4] Chung, F.R.K. (1997). *Spectral Graph Theory*. CBMS Regional Conference Series in Mathematics, No. 92. American Mathematical Society.

[5] Basiri, A., et al. (2016). "Chaos Engineering." *IEEE Software*, 33(3), 35-41.

[6] Mohar, B. (1991). "The Laplacian Spectrum of Graphs." *Graph Theory, Combinatorics, and Applications*, 2, 871-898.

[7] Von Luxburg, U. (2007). "A Tutorial on Spectral Clustering." *Statistics and Computing*, 17(4), 395-416.

[8] Zienkiewicz, O.C., Taylor, R.L., & Zhu, J.Z. (2013). *The Finite Element Method: Its Basis and Fundamentals*. 7th Edition. Butterworth-Heinemann.

[9] Von Mises, R. (1913). "Mechanik der festen Korper im plastisch deformablen Zustand." *Gottin. Nachr. Math. Phys.*, 1, 582-592.

[10] Sunder, A. (2025). "Spectral Signatures of Distributed Software Systems: Eigenvalue Profiling for Enterprise-Scale Proactive Resilience Engineering." *Asian Journal of Mathematical Sciences (AJMS)*, Vol. 9, No. 03. DOI: https://doi.org/10.22377/ajms.v9i03.618

[11] SSRN Working Paper. *Continuous Resilience via SRI/SAI: Predictive Detection and Adaptive Response*. SSRN-6702418. — formalizes the Non-Recoverable State criterion `dSRI/dt ≈ 0 ∧ SRI < threshold`.

[12] SSRN Working Paper. *A Unified View of Software Reliability Engineering*. — establishes the energy/cost duality `E = ∫Φ dt`, `Cost ∝ 1/SRI`.

[13] SSRN Working Paper. *Exploring the Interaction of Design Variability and Operational Uncertainty (HaiQ)*. — propagation kernel and cascade-risk formulation `risk(i,j) = pressure_avg · w_ij / Σ_in`.

[14] Sunder, A. (2026). "Towards a New Physics of Software Systems: A Finite Element and Spectral Framework for Distributed Architectures." *International Journal of Science and Research (IJSR)*, March 2026. https://www.ijsr.net/getabstract.php?paperid=MR26323100538 — establishes the operational-phase taxonomy and the composite-stress framing used in §12.8 of this whitepaper.

[15] Sunder, A. *Physics of Software Systems Part II: Stability Potential, Compute Energy, and Operational Cost in Enterprise Systems*. SSRN Preprint. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6580058 — extends [14] with the stability-potential / compute-energy / operational-cost duality and is the direct source of the eutectic-point construction Ψ_c adopted in Eq. 12.8.6.

[16] Sunder, A. *Physics of Software Systems: A Spectral-Element Derivation of Resilience from Enterprise System Observables*. SSRN preprint, 2026. Listed on Google Scholar at https://scholar.google.com/citations?user=dPKHEF8AAAAJ&hl=en — derives the resilience functional from spectral-element observables; complements [14] and [15] on the analytical side.

---

*End of Document*

---

**Document Control:**
| Field | Value |
|-------|-------|
| Version | 2.1 |
| Date | February 2026 |
| Classification | Proprietary & Confidential |
| Distribution | Restricted |
