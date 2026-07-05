# FreshCart — Grocery E-Commerce with Adaptive Spectral Resilience & Self-Healing

A production-grade online grocery platform with a full observability stack built around a novel **Spectral Resilience Index (SRI)** — a graph-theoretic metric that models system health as algebraic connectivity across infrastructure nodes. The platform features **Finite Element Analysis (FEA)** of the system graph, **polynomial SRI interpolation** for predictive degradation detection, and an **adaptive self-learning auto-healing engine** that identifies root causes, escalates through action ladders, and never repeats ineffective corrective actions.

> **Distributed by design (Feb 2026).** The backend is split into **two FastAPI microservices** running side-by-side under Supervisor in the same pod:
> - **`backend` (main_app, port 8001)** — the public service. Owns auth, products, cart, orders, admin, and a transparent proxy to obs.
> - **`backend_obs` (port 8002)** — the observability "brain". Owns every metric/SRI/FEA/healing/CX engine and the auto-healing background loops. Not exposed externally.
>
> They communicate via **fire-and-forget HTTP for writes** (`POST /api/internal/events/{request,business}`) and **synchronous HTTP proxy for reads** (`/api/metrics/*`, `/api/healing/*`, `/api/cx/*`, `/api/rum/*`, `/api/alerts*`, `/api/admin/webhooks/*`, `/api/grafana/*`, `/ws/alerts`). The frontend is unaware of the split — `REACT_APP_BACKEND_URL` still points only at port 8001.

> **3-tier topology mesh (Feb 2026, iter 21).** The service graph now has **three granularity tiers** — 6 services → 46 components → 101 endpoints (with 8 + 84 + 139 edges respectively). FEA, SRI, fault propagation, and auto-dampening all accept `granularity ∈ {service, component, endpoint}`. Double-click a service on the dashboard to drill into components, double-click again to drill into endpoints.

> **Aggressive / Reliability-aware Auto-Healing (Feb 2026, iter 22).** A second healing loop runs every 5 s and fires **proactively** (before SRI dips) when resilience debt is accumulating, a dip is predicted, or any service pressure exceeds 0.008. Action selection uses a **multi-objective score** mining `golden_signals_before/after` history: `0.30·ΔSRI + 0.30·ΔApdex + 0.20·ΔAvail + 0.15·ΔConv − 0.05·cost`. Toggle via `POST /api/healing/aggressive/toggle` (admin only).

---

## Table of Contents

- [Key Concepts](#key-concepts)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Local Setup](#local-setup)
- [Running the App](#running-the-app)
- [Default Credentials](#default-credentials)
- [API Reference](#api-reference)
- [Spectral Resilience Index (SRI)](#spectral-resilience-index-sri)
- [Finite Element Analysis (FEA)](#finite-element-analysis-fea)
- [SRI Interpolation & Trend Prediction](#sri-interpolation--trend-prediction)
- [Adaptive Auto-Healing Engine](#adaptive-auto-healing-engine)
- [Escalation Ladders & Cross-Node Healing](#escalation-ladders--cross-node-healing)
- [Golden Signals](#golden-signals)
- [Customer Experience Metrics](#customer-experience-metrics)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Key Concepts

| Concept | What It Is |
|---------|-----------|
| **Distributed split** | Two FastAPI services in one pod: `backend` (e-commerce + proxy, port 8001) and `backend_obs` (observability engines, port 8002). Shared MongoDB. |
| **3-tier mesh** | Topology is hierarchical: 6 services → 46 components → 101 endpoints (with 8 + 84 + 139 edges). FEA / propagation / dampening all accept `granularity ∈ {service, component, endpoint}`. |
| **Aggressive healing** | Proactive 5-second loop that fires before SRI dips, using multi-objective scoring (ΔSRI + ΔApdex + ΔAvail + ΔConv − cost) mined from golden_signals_before/after in history. Toggleable per admin. |
| **SRI** | Spectral Resilience Index — measures system connectivity via Laplacian eigenvalues across 6 service nodes |
| **FEA** | Finite Element Analysis — treats the system graph as a structural mesh, computes strain energy and Von-Mises stress per node to identify yielding components |
| **SRI Interpolation** | Quadratic polynomial fit over SRI time series: computes velocity (dSRI/dt), acceleration, and predicted future SRI |
| **Adaptive Healing** | Self-learning action selector that tracks effectiveness, detects healing stagnation, and auto-escalates through action ladders |
| **Escalation Ladder** | Per-node ordered list of corrective actions. When primary action is exhausted (0 effect), system escalates to next |
| **Cross-Node Healing** | When ALL actions for a node are exhausted, heals neighbor nodes via graph adjacency |
| **Multi-CA** | Fires corrective actions at multiple yield-exceeded nodes simultaneously |
| **Golden Signals** | The 4 pillars of SRE monitoring: Latency, Traffic, Errors, Saturation |
| **Fiedler Value (lambda_2)** | Second-smallest eigenvalue of the graph Laplacian — quantifies algebraic connectivity |
| **Von-Mises Stress** | Equivalent stress combining displacement and load — nodes exceeding yield threshold trigger CAs |
| **Correction Factor** | Measures how effectively a healing action improved a specific golden signal (0-100%) |
| **Healing Stagnation** | Detected when an action produces 0 SRI improvement for 5+ consecutive executions |

---

## Features

### E-Commerce (Frictionless Store)
- Product catalog with 16 seeded grocery items (Fruits, Vegetables, Dairy, Bakery, Meat, Seafood)
- **"Buy Now" one-click purchase** — instant order using saved delivery preferences
- **Reorder button** on Order History — re-adds all items to cart and navigates to checkout
- **Product prefetch on hover** — detail page loads instantly from cache when user clicks
- **Auto-saved delivery preferences** — address and phone remembered, auto-filled on checkout
- **Quick checkout shortcut** — "Checkout (N)" button in header when cart has items
- Shopping cart with optimistic UI updates (instant feedback)
- Checkout with inline order confirmation, Order history per user
- JWT cookie-based auth with admin and customer roles

### Observability & Business Reliability
- **6-node service mesh topology** with hierarchical sub-components: `Frontend, API, Cache, DB, Queue, Backend` (19 sub-components, 25 fine edges)
- **Reliability Score** — composite metric: 20% SRI + 30% Apdex + 25% Availability + 25% Conversion Health
- **SRI ↔ Conversion correlation** — live dual-axis chart with healing annotations + Pearson r
- **Customer Experience scorecard** — page_load, add-to-cart, error rate, conversion %, perceived speed (0-100)
- **Browser RUM beacon** (`/api/rum/beacon`) — Frontend is a first-class topology node fed by real browser timings (FCP, LCP, long tasks, axios latency, JS errors)
- **Synthetic User journey** — runnable end-user flow (Landing → Product → Filter → Checkout) with verdict pill
- **SRI Attribution Engine** — decomposes SRI dips into per-node per-signal contributions
- **4 Golden Signals** with per-signal health score and SRI contribution weight
- **InfluxDB** time-series storage + **Grafana** dashboard embedded via reverse proxy
- **WebSocket** real-time alert stream + **Slack/Discord webhooks** for critical alerts

### Strict-FEA Engine on the Service Mesh
- Solves `K · u = F` per element → element strain `ε`, stress `σ`, **von-Mises** `σvm`, yield check
- Software-friendly term mapping: σ↔Service Pressure, ε↔Service Drift, K↔Connection Strength, σy↔Failure Threshold
- **Hierarchical FEA** — `/api/healing/fea?granularity=service|component|endpoint` returns nested mesh with intra-service edges; tier-3 surfaces 101 endpoints / 139 endpoint-edges
- **Cascade Risk** per edge (HaiQ-inspired propagation probability `w_ij · pressure / Σ_in`)
- Polynomial interpolation: velocity dSRI/dt, acceleration, 30s/60s SRI predictions
- **Non-Recoverable State detector** — `d(SRI)/dt ≈ 0 ∧ SRI < threshold` (Eq. 7 SRI/SAI paper)
- **Resilience Debt** — `E(t) = ∫₀ᵗ Φ(t) dt` + cost-equivalent `Cost ∝ 1/SRI`

### Failure Propagation, Auto-Detection, and Auto-Dampening
- **Animated fault propagation** — Laplacian diffusion `ẋ = −α·L·x` with chaos-mode click-to-inject
- **Auto-Propagation Detector** — background scan every 8s identifies stressed services and pre-computes downstream cascades
- **Path-based autonomous healing** — alerts fire + (optional) auto-execute optimizer-chosen actions along the propagation path
- **Auto-Dampener** (`POST /api/healing/auto-dampen-wave`) — finds the highest-cascade-risk cut-edge, simulates BEFORE/AFTER, executes the cooldown-aware healing action. **Now supports tier-3 endpoint granularity** (e.g. cuts `API.auth.login → API.auth.register`).
- **Auto-Arrest mode** in the dashboard — every fault is automatically dampened before it cascades

### Adaptive Auto-Healing & Sequence Optimizer
- 6 corrective actions targeting specific nodes (cache_flush, connection_pool_reset, circuit_breaker, queue_drain, rate_limit, api_error_suppression)
- **Signal-aware action selection** — matches action affinity to the dominant failing signal
- **Adaptive selector** — tracks effectiveness, skips exhausted actions, escalation ladders per node
- **Cross-node healing** via graph adjacency when node actions are exhausted
- **Healing Sequence Optimizer** (`POST /api/healing/optimize-sequence`) — produces ordered plan via `score = sri_gain × readiness − cascade_overlap`, BFS-depth ordered (root cause first)
- **Sequence executor** (`POST /api/healing/execute-sequence`) — runs the plan with delay between steps; cooldown skips reported per step
- Background precision loop every 7s + auto-propagation loop every 8s

### Aggressive / Reliability-aware Healing (iter 22)
- **Proactive 5-second loop** (`AggressiveHealingMode`) that fires *before* SRI dips. Triggers on (a) `dE/dt > debt_rate_threshold`, (b) negative SRI velocity & acceleration (predicted dip), (c) baseline drift (SRI < 0.985 with debt growing), or (d) preemptive service pressure > 0.008.
- **Multi-objective action scoring** mining `golden_signals_before/after` in healing history:
  `score = 0.30·ΔSRI + 0.30·ΔApdex + 0.20·ΔAvail + 0.15·ΔConv − 0.05·cost`
  ΔApdex / ΔAvail / ΔConv are derived from latency↘ → +Apdex and errors↘ → +Avail & +Conv. Untried actions get a small positive prior so cost alone doesn't block discovery.
- **Admin toggle** — `POST /api/healing/aggressive/toggle {enabled, debt_rate_threshold, min_lift_threshold}` (admin only).
- **Dashboard card** ("Aggressive Reliability Heal") on the System Health tab — shows proactive fire count, 60-s reliability gain, debt threshold, and the last 10 proactive heals.
- Business context in every healing record (reliability score, business justification)

### Ladder Synthesizer · "Programs Writing Programs" (iter 30)
- **Meta-engine that rewrites the healing engine's own config.** Every 120 s (or on SRI stagnation < 0.005 Δ over 60 s) `LadderSynthesizer` analyses `healing_engine.history`, builds a per-(node, action) **gain matrix** = `0.7 · (0.6·mean_ΔSRI + 0.4·recency_ΔSRI) + 0.3 · golden-signal affinity − cost-penalty`, ranks actions per node by gain, and **atomically swaps the result into `healing_engine.escalation_ladder`**.
- **Versioned + persistent**: each rewrite increments `version` and is stored to MongoDB collection `synthesized_ladders` `{version, timestamp, reason, ladder, previous_ladder, diff, gain_matrix, sri_baseline, phase_at_swap}`. On obs boot, the latest persisted ladder is restored — the engine is self-modifying across restarts.
- **Rollback guard**: 60 s after each swap, if SRI has regressed by > 0.02 vs the at-swap baseline, the previous ladder is auto-restored.
- **Endpoints**: `GET /api/healing/ladder/{current, history, gain-matrix}`, `POST /api/healing/ladder/{synthesize, rollback, toggle}` (admin gating on writes).
- **Dashboard card** ("Ladder Synthesizer · Programs Writing Programs") on System Health — version pill, per-node synthesized ladder with heat-coloured gain-score chips (green > 0.20, lime > 0.10, amber > 0, red ≤ 0), `was: …` diff line on rewritten nodes, AUTO / SYNTH / ROLLBACK admin buttons.

### Scaling Actions (iter 33, capacity-boost wiring iter 36, eutectic-guided iter 37)
*Engine can now add capacity, not just dampen demand — scaling actions actually move the saturation denominator (iter 36) — and every scaling decision is now provably eutectic-pulling (iter 37).*

- **Eight scale-* actions** (iter 37): 4 `scale_out_*` (Frontend, Cache, DB, Backend) + 4 `scale_in_*` (Frontend, Cache, DB, Backend). `scale_in_*` are cheap, fast (120 s cooldown) cost-saving actions that DRAIN the active capacity boost (multiplicative factor in (0, 1)) — modelling replica decommissioning.
- **Eutectic-guided trigger gate** (iter 37): every scale_* trigger now passes through `HealingEngine._scale_pulls_to_eutectic(node, action_id)`. The gate simulates the action's effect on the boost (`new_boost = current × factor`, clamped to `[1.0, CAPACITY_BOOST_CEILING]`), projects the resulting `(L̂, M_ratio)` coordinates (both divide by boost via M/M/c queueing), computes the new L2 distance to Ψ_c = (0.05, 0.30, 0.55, 0.02), and **fires only if the projected distance is ≥ 1% smaller than the current distance**. This means:
  - `scale_out_*` won't fire on an idle node (would push *away* from Ψ_c's M_ratio=0.55).
  - `scale_in_*` won't fire on a stressed node (would push *toward* M_ratio=1.0, away from Ψ_c).
  - `scale_in_*` won't fire when there's no active boost to drain (already at baseline).
- **All four components now traverse toward Ψ_c**: Frontend, Cache, DB, and Backend each get one `scale_out_*` and one `scale_in_*` action — the system can bidirectionally regulate every scalable node toward the eutectic point.
- **Capacity-boost mechanism (iter 36 fix for the "metallurgical yielding" state)**: scale-out actions previously had a `saturation_reduction` *intent* in `_apply_healing_effect` but the intent was never propagated to `MetricsAggregator` — the persistent dampener carried only `latency_factor` + `error_suppression`, and `get_node_metrics` hard-coded `saturation = min(traffic / 100, 1.0)`. Frontend/Backend therefore stayed pinned at `saturation = 1.0` no matter how many scale-outs fired. The fix adds a parallel `apply_capacity_boost(node, multiplier, duration)` channel that compounds multiplicatively within the persistence window (capped at 8× by `CAPACITY_BOOST_CEILING`), feeds into `get_node_metrics` as `saturation = traffic / (100 × boost)`, and applies a queueing-theoretic latency divisor (`latency /= boost`). scale_out_* fires now bind boosts of **1.85–2.0× for 120 s** (config in `HealingEngine._apply_healing_effect.capacity_boost_config`). The matching `apply_capacity_drain(node, drain_factor, duration)` channel powers `scale_in_*` — boost shrinks by `drain_factor ∈ (0,1)` and is cleared entirely when it drops below 1.05. Active boosts surface live on `GET /api/healing/status.capacity_boosts`.
*Added three capacity-expansion actions to the engine — the first actions in the system that **add infrastructure** rather than dampen demand.*

| Action | Target node | Cost | Cooldown | Effect |
|--------|-------------|------|----------|--------|
| `scale_out_frontend`       | Frontend | 0.50 | 180 s | latency −45%, saturation −60% (capacity boost 2.0× / 120 s) |
| `scale_out_cache_node`     | Cache    | 0.40 | 150 s | latency −50%, saturation −65% (capacity boost 1.85× / 120 s) |
| `scale_out_db_read_replica`| DB       | 0.60 | 240 s | latency −40%, saturation −55% (capacity boost 1.7× / 120 s) |
| `scale_out_backend`        | Backend  | 0.50 | 200 s | latency −40%, saturation −55% (capacity boost 1.75× / 120 s) — *iter 36* |

- **Frontend is now a healable node** (it was previously only observable via the Phase Classifier). Frontend was added to `escalation_ladder`, `node_neighbors`, `node_primary_action`, `node_signal_importance`, `MetricsAggregator` node list, and the synthesizer's `ALL_NODES`.
- **Cost-aware integration**: scaling has the highest action costs in the system (0.40–0.60 vs 0.05–0.35 for dampener actions). The synthesizer's cost-penalty term keeps them as last-resort options under healthy operations. Under `healing_saturation` phase (§12.8.5), the cost penalty doubles → scaling is *further* deprioritised when the system is already over-healing — preventing scale-out thrashing on top of dampener thrashing.
- **Long-lived dampeners**: scale-out dampener durations are 120 s vs 20–30 s for dampener actions, reflecting that added capacity persists across multiple healing cycles.
- **Sequence-aware**: actions are full first-class participants in the §12.7 escalation walk, the §12.9 RUM-validated sequence mining, and the §12.7 ladder synthesis. They appear in synthesized ladders' top-4 automatically (e.g. v74 promoted `scale_out_cache_node` to position 3 of API and Backend ladders just from affinity + cost reasoning).
- **Sample synthesized ladder (v74, live)**: Frontend = `queue_drain → rate_limit → scale_out_cache_node → scale_out_db_read_replica`; Queue = `scale_out_cache_node → scale_out_frontend → scale_out_db_read_replica → rate_limit`. Auto-emergent — no manual ordering.

### RUM Ladder Learner — Reliability from User-Felt Outcomes (iter 32)
*Closes the reliability loop with real-user telemetry: every healing-action **sequence** is graded against the actual page_load / perceived_speed / error_shown_rate deltas captured by the `rum/beacon` ingest path.*

- **Sequence mining**: every 15 s, `RumLadderLearner` groups `correlation_tracker._annotations` into contiguous chains (consecutive heals within `SEQ_WINDOW_S = 15 s`). Singleton actions are skipped — §12.7's per-action ΔSRI mean already covers them.
- **Composite RUM gain** per sequence:
  `gain = 0.4·(Δperceived_speed/100) + 0.4·clamp(−Δpage_load_ms / 500, −1, 1) + 0.2·(−100·Δerror_shown_rate)`
  computed over 30 s before the first action and 30 s after the last action.
- **Persistent top-K**: top 30 sequences globally + per-node top 6 stored in MongoDB collection `rum_validated_sequences`, restored on boot.
- **Closed-loop feedback**: `LadderSynthesizer.compute_gain_matrix` queries `learner.best_action_bonuses(node)` per node and adds up to `RUM_BONUS_COEFF = 0.15` to actions appearing in validated sequences — actions that *real users* responded well to climb the synthesised ladder.
- **Endpoints**: `GET /api/healing/rum-sequences/{top,status}`, `POST /api/healing/rum-sequences/run-now` (admin).
- **Dashboard card** ("RUM-Validated Healing Sequences") on System Health — per-node colored pills, full action chain with arrows, three RUM delta values (`page_load Δ`, `perceived Δ`, `err_rate Δ`) heat-colored by direction, samples-before/after counts.

### Operational Phase Classifier (iter 31)
*Operational-phase taxonomy and the composite-stress / eutectic construction follow Sunder, "Towards a New Physics of Software Systems" (IJSR, Mar 2026) and "Physics of Software Systems Part II" (SSRN). See SRI_Whitepaper §23 refs [14], [15].*

- **Implements the Operational Phase-Transition Diagram.** Computes per-service **composite stress σ = αL + βQ + γM + δE** (α=0.30, β=0.20, γ=0.25, δ=0.25 — env-tunable) and classifies each node into one of seven phases: `cold_start`, `warm_runtime`, `stable_throughput`, `jvm_saturation`, `retry_amplification`, `healing_saturation`, `cascading_collapse`. Eutectic point Ψ_c = (L̂=0.05 ⇒ L/L₀≈1.5, Q=0.30, M/M_cap=0.55, E=0.02) — the optimal balance target. The system reports per-node distance to Ψ_c.
- **Two cross-system detectors that gate downstream engines:**
  1. **Retry amplification** — traffic↑ ∧ errors↑ ∧ latency↑ over rolling 30 s window. When this fires, `AggressiveHealingMode.rank_actions()` returns an empty list and refuses to add load to the positive-feedback loop.
  2. **Healing saturation** — `heal_actions_per_min ÷ mean_|ΔSRI|_per_heal > 25`. When this fires, `LadderSynthesizer` doubles the cost-penalty in its gain matrix so cheap actions (`cache_flush`, `rate_limit`) outrank heavyweight ones (`circuit_breaker`, `connection_pool_reset`), breaking the heal-rate positive feedback.
- **Every ladder version is tagged with the phase it was synthesized in** (`phase_at_swap`) — the synthesizer learns "this action @ this phase = +ΔSRI" instead of phase-blind.
- **Endpoints (read-only)**: `GET /api/phase/state`, `GET /api/phase/history?limit=N`.
- **Two dashboard cards** on System Health:
  1. **Operational Phase Transition** — system-worst phase pill, σ + Ψ_c distance stats, retry-amp/heal-sat banners with their exact policy effect spelled out, per-service phase chips with mini 2D phase-space dot, σ trajectory sparkline.
  2. **Operational Phase Diagram** (iron-carbide-style, iter 31 cont.) — full 2D phase chart with **X = M/M_cap** (memory saturation, ≈ carbon content) and **Y = L/L₀** (latency ratio, √-scaled, ≈ temperature). Colored filled regions for each geometric phase, `M_cap = 0.80` dashed reference, Ψ_c eutectic marker at (0.55, 1.50), every service plotted as a colored labeled dot ringed by its current-phase color, fading 20-sample trajectory trail per service, regime-override banners on top (since `retry_amplification` and `healing_saturation` are temporal, not positional). The 2D layout makes phase-boundary proximity immediately legible — operators see *which boundary each service is closest to* at a glance.

### Action Stagnation Guard (iter 34)
*Inner-loop dampener pruner — dynamically removes (node, action) pairs whose recent attempts produce |ΔSRI| below the noise floor, so the synthesizer and aggressive-heal mode stop wasting picks on them.*

- **Rolling window** of last `WINDOW = 4` attempts per (node, action), tracked from the live `correlation_tracker._annotations` stream.
- **Stagnation condition**: if every attempt in the window has `|ΔSRI| < EPSILON (= 0.003)` the pair is **removed** from the live ladder pool and entered into a `COOLDOWN_S = 180 s` quarantine.
- **Auto-restore** on cooldown expiry — the pair re-enters the pool and is given a fresh chance to prove itself.
- **Synthesizer + auto-heal consult the guard** before picking an action — the gain matrix simply drops removed pairs to gain = 0, so picks shift to actions that are *currently effective in this phase*.
- **Endpoints**: `GET /api/healing/stagnation/state`, `POST /api/healing/stagnation/{restore,reset}` (admin).
- **Dashboard card** on System Health — currently-removed pair list with per-pair mean |ΔSRI| and cooldown countdown, manual restore button, recent stagnation/restore events feed.

### Runtime Stiffness Tensor (RST)
*Models each service node as a structural element obeying Hooke's Law: ε = σ / K_eff. Provides a complementary resilience lens to the SRI: where SRI measures global spectral connectivity, RST localises the structural cause of fragility into 6 mechanically-interpretable components per service.*

Each service is characterised by a **6-component stiffness tensor K**:
| Component | Physical analogy | Derivation |
|-----------|-----------------|-----------|
| **K_A** | Availability stiffness | `1 − error_rate` — resistance to error-driven yielding |
| **K_H** | Healing stiffness | Gain-matrix score — how well corrective actions take hold |
| **K_S** | Saturation stiffness | `1 − saturation` — capacity headroom |
| **K_D** | Dependency stiffness | Normalised graph degree — structural connectivity |
| **K_F** | Fault stiffness | `1 / (1 + ln(L/L₀))` — resistance to latency-driven fault propagation |
| **K_R** | Resilience stiffness | `exp(−d²)` where d² = eutectic distance from PhaseClassifier |

**Effective stiffness** (weighted geometric mean):
```
K_eff = K_A^0.20 · K_H^0.15 · K_S^0.20 · K_D^0.15 · K_F^0.15 · K_R^0.15
```

**Stress σ** — operational stress derived from latency ratio, error rate and saturation.  
**Strain ε = σ / K_eff** — how much the node deforms under that stress. High K_eff → low ε (node absorbs load without yielding).

**Spectral view** — the stiffness-weighted graph Laplacian `L = D − W` (edge weight = harmonic mean of K_eff of endpoints) exposes:
- **λ₂** (Fiedler value) — algebraic connectivity; → 0 means the stiffness mesh is near-disconnected.
- **λmax** — spectral radius.
- **RST-SRI** = λ₂ / λmax — a structural connectivity index in [0, 1].

**Built-in scenarios** (applied via API or dashboard selector, expire after 60 s):
- `normal` — baseline
- `db_failure` — DB availability collapses; fault propagates to Backend and Cache
- `cache_miss_storm` — Cache saturation; DB and Backend absorb the overflow
- `healing_saturation` — healing actions are generating load; K_H drops system-wide
- `api_latency_spike` — API latency spike; upstream Frontend and downstream stressed

**Backend**:
- `backend/obs/engines/rst_engine.py` — `RSTEngine` class; 5 s background tick; 240-sample history (~20 min)
- `GET /api/rst/state` — current tensor snapshot (all nodes + spectral)
- `GET /api/rst/history?limit=N` — rolling history for trend charts
- `POST /api/rst/scenario` — inject a stress scenario `{name, overrides, duration_s}`
- `DELETE /api/rst/scenario` — clear active scenario

**Frontend (RST tab on Dashboard)**:
- **Stiffness Tensor Composition** — colour-coded heatmap of K_A … K_R per service
- **Stress & Strain Panel** — live bar chart + time-series σ/ε per service
- **Structural Twin Graph** — service mesh with node size ∝ K_eff and edge thickness ∝ harmonic-mean K_eff
- **Spectral Resilience Panel** — λ₂, λmax, RST-SRI gauge with trend AreaChart
- **Physical Analogy View** — spring-damper diagram; spring amplitude ∝ 1/K_eff, damper fill ∝ ε

**Tests**: `backend/tests/test_rst.py` — 28 unit tests covering all tensor components, K_eff formula, stress/strain physics, spectral math, scenario mechanics, and live API contract tests (skipped when `REACT_APP_BACKEND_URL` is unset).

### Economic Reliability — Unified-Model Phase 3 (iter 35)
*Closes the resilience↔business-value loop: visualises **how many dollars of conversion the healing system is currently saving per minute** and the cost it pays to do so. Implements Eqs. 51–58 of Sunder's "Resilience Software Models" (SRI_Whitepaper §14.3).*

- **Economic resilience** `R_econ = W / C_T` (Eq. 57) — value-per-cost ratio.
- **Resilience-weighted economic value** `R = W · R_S / C_T` (Eq. 58) where `R_S = ΣH / Σσ` (healing potential over composite stress, soft-capped to 100 to keep the metric sensible under idle conditions).
- **Total cost decomposition** `C_T = C_I + C_O + C_H + C_F` (Eq. 51):
  - `C_I` — flat infrastructure rate (env: `PHASE3_INFRA_COST_USD_PER_MIN`)
  - `C_O` — observability cost, proxied from event-rate × `PHASE3_OBS_USD_PER_KEVT`
  - `C_H` — healing cost: count of healing actions in last 60 s × per-action rate (`PHASE3_HEAL_COST_PER_ACTION` for dampeners, `PHASE3_SCALE_COST_PER_ACTION` for scale-out)
  - `C_F` — failure cost: revenue gap vs. the modelled-conversion ceiling produced by `BusinessMetrics.modeled_conversion.projected_revenue_per_min`
- **Counterfactual heal-saved revenue/min** — when actual conversion outperforms the modelled-conversion ceiling (i.e. the system has been healed *above* its degraded baseline) the integrated uplift × traffic × avg-order-value is reported as the dollars the healing engine just saved.
- **Endpoints (read-only)**: `GET /api/economic-reliability/{state,trend}`.
- **Dashboard card** on System Health — headline R_econ / R / W($/min) / heal-saved/min, segmented cost-decomposition bar (C_I / C_O / C_H / C_F), R_econ trend + W trend sparklines, R_S / conversion / orders / revenue-5m strip.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TailwindCSS, Shadcn/UI, Recharts, Lucide Icons |
| Backend | FastAPI (Python 3.11+), Uvicorn |
| Database | MongoDB (via Motor async driver) |
| Time-Series | InfluxDB 2.7 (optional — app works without it) |
| Dashboards | Grafana 10.4 (optional — embedded via proxy) |
| Auth | JWT with httpOnly cookies, bcrypt |
| Real-time | WebSocket (FastAPI native) |
| Math | NumPy (Laplacian eigendecomposition, pseudo-inverse FEA solver, polyfit interpolation) |

---

## Architecture

FreshCart runs as **two FastAPI microservices** in the same pod managed by Supervisor, sharing one MongoDB. The frontend points only at the **main app** (port 8001) — observability traffic is transparently proxied to the **observability service** (port 8002) internally.

```
+---------------------------------------------------------------+
|                        React Frontend                          |
|  +----------+ +----------+ +----------+ +-----------------+   |
|  |  Store   | |  Cart    | | Checkout | |   Dashboard     |   |
|  |  Pages   | |  Context | |  Flow    | |  (6 tabs)       |   |
|  +----------+ +----------+ +----------+ +-----------------+   |
+----------------------------+----------------------------------+
                             | HTTPS to REACT_APP_BACKEND_URL
                             | (single origin, port 8001)
+----------------------------v----------------------------------+
|         backend  (main_app, port 8001 — public)                |
|   /api/auth/*  /api/products  /api/cart/*  /api/orders/*       |
|   /api/admin/products  /api/admin/orders                       |
|   +----------------------------------------------------------+ |
|   |       Event-Emit Middleware (fire-and-forget)            | |
|   |  every /api/* -> POST /api/internal/events/request       | |
|   |  cart/order  -> POST /api/internal/events/business       | |
|   +----------------------------------------------------------+ |
|   +----------------------------------------------------------+ |
|   |  Observability Proxy (synchronous httpx.AsyncClient)     | |
|   |  /api/metrics/*  /api/healing/*  /api/cx/*  /api/rum/*   | |
|   |  /api/alerts*  /api/admin/webhooks/*  /api/grafana/*     | |
|   |  /ws/alerts (WebSocket bridge)                           | |
|   +-----------------------+----------------------------------+ |
+---------------------------|------------------------------------+
                            | localhost HTTP / WS
+---------------------------v------------------------------------+
|   backend_obs  (obs_server, port 8002 — internal only)         |
|   +----------------------------------------------------------+ |
|   |  Engines & Trackers                                      | |
|   |  +----------+ +-----------+ +---------+ +-------------+ | |
|   |  | Metrics  | | SRI       | | FEA     | | Healing     | | |
|   |  | Aggreg.  | | Interp.   | | Solver  | | Engine      | | |
|   |  +----------+ +-----------+ +---------+ +-------------+ | |
|   |  +----------+ +-----------+ +---------+ +-------------+ | |
|   |  | CX       | | Business  | | Attrib. | | Webhook     | | |
|   |  | Tracker  | | Metrics   | | Engine  | | Notifier    | | |
|   |  +----------+ +-----------+ +---------+ +-------------+ | |
|   |  +----------------+ +-------------------------+         | |
|   |  | AutoPropag.    | | ResilienceDebt Accum.   |         | |
|   |  | Detector       | | (∫Φ dt, cost ∝ 1/SRI)   |         | |
|   |  +----------------+ +-------------------------+         | |
|   +----------------------------------------------------------+ |
|   Internal receivers (only obs binds these):                   |
|     POST /api/internal/events/request                          |
|     POST /api/internal/events/business                         |
|   Background loops:                                             |
|     auto_healing_loop (7 s)   auto_propagation_loop (8 s)      |
+--------+----------------------------+--------------------------+
         |                            |
    +----v-----+              +-------v------+
    | MongoDB  |              |   InfluxDB   |--> Grafana
    | (shared) |              |  (metrics)   |   (port 3002)
    +----------+              +--------------+
```

**Key properties:**
- **One public surface, two processes.** The frontend doesn't know there are two services — `REACT_APP_BACKEND_URL` still points at port 8001 only.
- **Fire-and-forget telemetry.** The main app never blocks on the observability service: request/business events are emitted via `asyncio.create_task(httpx.post(...))` and all errors are swallowed. If obs is down, the storefront keeps shopping.
- **Synchronous proxy reads.** Observability GETs (and admin POSTs) are forwarded synchronously so the dashboard always sees fresh data; cookies/headers are preserved so admin auth works through the proxy.
- **Shared MongoDB, separate memory.** Both services share users/products/orders/carts; the observability in-memory state (rolling SRI windows, healing history, RL adaptation matrix) lives only in `backend_obs`.
- **WebSocket bridge.** `/ws/alerts` on the main app opens a server-side WS to obs and forwards messages both directions using the `websockets` library.

**Service Mesh Topology** (modelled by the SRI engine, 6 services, 6 inter-edges, 19 sub-components, 25 fine edges):

```
   Frontend ---> API ---> Cache
                  | \      |
                  |  \     v
                  v   v    DB
                 Queue --> Backend
```

The Frontend node receives RUM beacons from real browsers. Frontend stress flows to API
(via `Frontend.api_calls → API.{auth, catalog, cart, checkout}`), and downstream to
Cache/DB/Queue/Backend. All 6 nodes participate equally in SRI computation, FEA stress
analysis, fault propagation, and the auto-dampener cut-edge selection.

---

## Local Setup (from GitHub)

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend runtime |
| Yarn | 1.22+ | Package manager |
| MongoDB | 6+ | Primary database |
| InfluxDB | 2.7 (optional) | Time-series metrics |
| Grafana | 10.4 (optional) | Dashboard visualization |

### 1. Clone the Repository

```bash
git clone https://github.com/<your-org>/delivery-metrics-hub.git
cd delivery-metrics-hub
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env  # Or create manually (see below)
```

**Create `backend/.env`:**

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=freshcart
JWT_SECRET=your-secure-random-secret-key-here
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=your-influxdb-token
INFLUX_ORG=freshcart
INFLUX_BUCKET=metrics
```

> **Note:** `INFLUX_*` variables are optional. The app works without InfluxDB — metrics will use in-memory storage only.

**Start the backend (both services):**

Production-style (recommended — what runs in the deployed pod):

```bash
# Supervisor runs two FastAPI processes from /etc/supervisor/conf.d/
#   backend       -> uvicorn server:app     --port 8001  (public, e-commerce + proxy)
#   backend_obs   -> uvicorn obs_server:app --port 8002  (internal, observability)
sudo supervisorctl reread && sudo supervisorctl update
sudo supervisorctl status backend backend_obs
```

Local dev (two terminals):

```bash
# Terminal 1 — observability service (must start first so the proxy has somewhere to forward to)
uvicorn obs_server:app --host 0.0.0.0 --port 8002 --reload

# Terminal 2 — main e-commerce app + proxy
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

On first run the **main app** will:
- Connect to MongoDB and seed 16 products + the admin account
- Write `/app/memory/test_credentials.md`
- Start emitting fire-and-forget request/business events to obs

The **observability service** will:
- Start the auto-healing loop (every 7 s) and auto-propagation loop (every 8 s)
- Initialize InfluxDB if `INFLUX_TOKEN` is set
- Listen on `/api/internal/events/{request,business}` for telemetry from main_app

> The frontend only talks to **port 8001** — all `/api/metrics/*`, `/api/healing/*`, `/api/cx/*`, `/api/rum/*`, `/api/alerts*`, `/api/admin/webhooks/*`, `/api/grafana/*`, and `/ws/alerts` are proxied internally.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
yarn install

# Create environment file
cp .env.example .env  # Or create manually
```

**Create `frontend/.env`:**

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

**Start the frontend:**

```bash
yarn start
```

The app will be available at `http://localhost:3000`.

### 4. (Optional) InfluxDB + Grafana

For full observability dashboard with persistent metrics:

```bash
# Install InfluxDB
# See: https://docs.influxdata.com/influxdb/v2/install/

# Start InfluxDB
influxd

# Create bucket and token via InfluxDB UI (http://localhost:8086)
# Add the token to backend/.env as INFLUX_TOKEN

# Install Grafana
# See: https://grafana.com/docs/grafana/latest/setup-grafana/installation/

# Start Grafana (default port 3000 conflicts — use 3002)
grafana-server --homepath /usr/share/grafana --config /etc/grafana/grafana.ini web cfg:server.http_port=3002
```

### 5. Verify Installation

```bash
# Health check — both services answer their own /health
curl http://localhost:8001/health     # main_app
curl http://localhost:8002/health     # observability (internal only)
# Expected: {"status": "healthy", "timestamp": "..."}

# E-commerce (served by main_app)
curl http://localhost:8001/api/products
# Expected: JSON array with 16 products

# Observability (served by obs but reachable via main_app proxy)
curl http://localhost:8001/api/metrics/real
curl http://localhost:8001/api/healing
# Expected: JSON with sri, golden_signals, mode, RCA, FEA data

# Confirm the proxy is actually forwarding (compare main vs direct)
diff <(curl -s http://localhost:8001/api/healing/topology/schema) \
     <(curl -s http://localhost:8002/api/healing/topology/schema)
# Expected: no diff

# Frontend
open http://localhost:3000
```

### 6. Running Tests

```bash
cd backend

# Set test environment
export REACT_APP_BACKEND_URL=http://localhost:8001

# Optional — override seeded test credentials (defaults match local seed)
# export ADMIN_TEST_EMAIL=admin@freshcart.com
# export ADMIN_TEST_PASSWORD=admin123
# export USER_TEST_EMAIL=test@freshcart.com
# export USER_TEST_PASSWORD=testpass123

# Run all tests
pytest tests/ -v

# Run specific test suite
pytest tests/test_freshcart_api.py -v
pytest tests/test_iteration12_adaptive_healing.py -v
```

### Project Structure

```
delivery-metrics-hub/
├── backend/
│   ├── server.py          # MAIN APP (port 8001): auth, products, cart, orders,
│   │                      #   admin endpoints, event-emit middleware, obs proxy,
│   │                      #   /ws/alerts bridge. ~670 lines.
│   ├── obs_server.py      # OBSERVABILITY SERVICE (port 8002): app/router,
│   │                      #   singleton wiring (wire_runtime), background loops
│   │                      #   (auto_healing / auto_propagation / aggressive /
│   │                      #   permanent_funnel / ladder_synthesis),
│   │                      #   /api/internal/events/* receivers, healing endpoints.
│   │                      #   ~2,540 lines (down from 5,623 — see modularization).
│   ├── obs/               # Modularized observability package (iter 27–30)
│   │   ├── __init__.py
│   │   ├── trackers/
│   │   │   ├── __init__.py            # PEP-562 lazy re-exports
│   │   │   └── core.py                # 11 standalone tracker classes:
│   │   │                              #   MetricsAggregator, SRIInterpolator,
│   │   │                              #   ResilienceDebtAccumulator,
│   │   │                              #   CorrelationTracker, AutoPropagationDetector,
│   │   │                              #   SRIAttributionEngine, WebhookNotifier,
│   │   │                              #   HealingAction, CustomerExperienceTracker,
│   │   │                              #   BusinessMetrics, AlertManager. ~1,240 lines.
│   │   ├── engines/
│   │   │   ├── __init__.py            # PEP-562 lazy re-exports
│   │   │   ├── core.py                # 4 heavyweight engines:
│   │   │   │                          #   HealingEngine (~1,540 lines),
│   │   │   │                          #   HealingSequenceOptimizer,
│   │   │   │                          #   AggressiveHealingMode,
│   │   │   │                          #   PermanentFunnelHealer. ~2,070 lines.
│   │   │   └── ladder_synthesizer.py  # "Programs writing programs":
│   │   │                              #   LadderSynthesizer + synthesis_loop.
│   │   │                              #   ~360 lines.
│   │   └── routes/
│   │       └── __init__.py            # Reserved for Phase 4 (route extraction)
│   ├── requirements.txt   # Python dependencies (motor, fastapi, httpx, websockets,
│   │                      #   numpy, bcrypt, pyjwt, influxdb_client)
│   ├── .env               # Shared env vars for both services (create locally)
│   └── tests/             # Pytest test suites (incl. test_iteration20_microservice_split.py)
├── frontend/
│   ├── src/
│   │   ├── App.js         # Router + layout
│   │   ├── components/    # Reusable UI (ProductCard, Header, Footer, dashboard/*
│   │   │                  #   incl. LadderSynthesizerCard.jsx,
│   │   │                  #   PhaseTransitionCard.jsx, PhaseDiagramView.jsx)
│   │   ├── contexts/      # AuthContext, CartContext
│   │   ├── lib/           # productCache.js, rumBeacon.js
│   │   └── pages/         # Route pages (Home, Products, Cart, Checkout, Dashboard)
│   ├── package.json       # Node dependencies
│   └── .env               # Frontend env (REACT_APP_BACKEND_URL → port 8001 only)
├── /etc/supervisor/conf.d/
│   ├── supervisord.conf   # Runs `backend` (uvicorn server:app on 8001)
│   └── backend_obs.conf   # Runs `backend_obs` (uvicorn obs_server:app on 8002)
├── memory/                # Development context files (PRD.md, test_credentials.md)
├── README.md              # This file
└── SRI_Whitepaper.md      # Technical whitepaper
```

#### Modularization & the singleton-binding pattern (iter 27–30)

`obs_server.py` historically grew to 5,623 lines. Across three phases its
heavyweight class bodies were **physically extracted** into the `obs/`
subpackage without touching the method bodies themselves:

| Phase | iter | Extracted | `obs_server.py` size |
|-------|------|-----------|----------------------|
| 1 (scaffolding) | 27 | New package layout + re-export `__init__.py`s | 5,623 lines |
| 2 | 28 | 8 standalone trackers → `obs/trackers/core.py` | 4,911 lines (-12.7 %) |
| 3 | 29 | 7 more (HealingEngine + 3 engines + CX/Business/Alert trackers) → `obs/{trackers,engines}/core.py` | 2,539 lines (-55 %) |
| 4 (synthesizer) | 30 | `obs/engines/ladder_synthesizer.py` added | 2,540 lines |
| 4 (quality pass) | 30 cont. | Code-review surgical fixes: test creds → env vars, silent `catch {}` → `console.error`, `key={idx}` → stable keys, `useMemo` for expensive JSX (`AggressiveHealingCard`, `CustomerExperiencePanel`) | 2,540 lines |
| 5 (phase classifier) | 31 | `obs/engines/phase_classifier.py` added — σ, 7-phase classifier, retry-amp + heal-sat detectors, policy hooks into `AggressiveHealingMode.rank_actions` & `LadderSynthesizer.compute_gain_matrix`. Frontend gained `PhaseTransitionCard` + iron-carbide-style `PhaseDiagramView`. | 2,560 lines |

The non-trivial part of phases 2 & 3 is that engine and tracker bodies
freely reference the **singletons** that live in `obs_server.py`
(`metrics_aggregator`, `business_metrics`, `healing_engine`, …) and the
module-level constants (`TOPOLOGY_SCHEMA`, `PERMANENT_FIX_REGISTRY`,
`compute_sri_from_metrics`, threshold constants, …). To break the
import cycle without editing every method:

1. Each extracted module **forward-declares** all referenced singletons
   as `None`/`{}` at the top of the file.
2. `obs_server.py._wire_extracted_modules()` runs *after* singleton
   instantiation and `setattr`s the real instances back into the
   extracted modules' `globals()` dicts.
3. Method bodies resolve names via function-globals (i.e. the extracted
   module's namespace), so by the time any method is called the names
   point at live singletons.

The same pattern is used for the new `LadderSynthesizer`: it imports
`metrics_aggregator` and `compute_sri_from_metrics` lazily through
`__import__("obs.engines.core", fromlist=[...])` inside its own methods,
avoiding any new import-time coupling.

### Environment Variables Reference

| Variable | Location | Required | Description |
|----------|----------|----------|-------------|
| `MONGO_URL` | backend/.env | Yes | MongoDB connection string (shared by both services) |
| `DB_NAME` | backend/.env | Yes | Database name (shared by both services) |
| `JWT_SECRET` | backend/.env | Yes | Secret for JWT token signing (must be identical for both services so the obs proxy can authenticate admin requests) |
| `OBS_SERVICE_URL` | backend/.env | No | Base URL the main app uses to reach obs. Default `http://localhost:8002`. |
| `OBS_PORT` | supervisor env (`backend_obs.conf`) | No | Port the obs service binds to. Default `8002`. |
| `INFLUX_URL` | backend/.env | No | InfluxDB URL (used by obs only) |
| `INFLUX_TOKEN` | backend/.env | No | InfluxDB auth token (obs only) |
| `INFLUX_ORG` | backend/.env | No | InfluxDB organization (obs only) |
| `INFLUX_BUCKET` | backend/.env | No | InfluxDB bucket (obs only) |
| `SLACK_WEBHOOK_URL` | backend/.env | No | Slack incoming webhook URL — fires on critical SRI alerts (obs only) |
| `DISCORD_WEBHOOK_URL` | backend/.env | No | Discord webhook URL — fires on critical SRI alerts (obs only) |
| `WEBHOOK_COOLDOWN_SEC` | backend/.env | No | Cooldown between same-key webhook sends (default 120s) |
| `REACT_APP_BACKEND_URL` | frontend/.env | Yes | Backend API URL — points at the **main app** (port 8001) only |
| `ADMIN_TEST_EMAIL` | shell env (tests only) | No | Override admin email used by `tests/test_iteration{14,18,19}_*.py`. Default `admin@freshcart.com`. |
| `ADMIN_TEST_PASSWORD` | shell env (tests only) | No | Override admin password for the same test suites. Default `admin123`. |
| `USER_TEST_EMAIL` | shell env (tests only) | No | Override non-admin user email used by `tests/test_iteration14_webhooks_schema.py`. Default `test@freshcart.com`. |
| `USER_TEST_PASSWORD` | shell env (tests only) | No | Override non-admin user password for the same test suite. Default `testpass123`. |

---

## Default Credentials

| Account | Email | Password |
|---------|-------|----------|
| Admin | admin@freshcart.com | admin123 |
| Test User | (register via /register) | any |

---

## API Reference

> **Routing note:** All endpoints below are reached on a single base URL — `REACT_APP_BACKEND_URL` (port 8001).
> The **main app** answers E-Commerce/Auth/Admin endpoints directly; **Observability / Healing / CX / RUM / Alerts / Webhooks / Grafana** endpoints are transparently proxied to the observability service on port 8002.
> Cookies and `Authorization` headers are forwarded, so admin-protected endpoints work through the proxy unchanged.

### E-Commerce  *(served by main_app)*
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/register | Register user |
| POST | /api/auth/login | Login |
| GET | /api/auth/me | Current user |
| GET | /api/user/delivery-preferences | Get saved delivery address/phone |
| GET | /api/products | List products |
| GET | /api/products/:id | Product detail |
| GET | /api/categories | List categories |
| GET/POST/PUT/DELETE | /api/cart/* | Cart operations |
| POST | /api/orders | Place order (saves delivery prefs) |
| POST | /api/orders/buy-now | One-click buy (skip cart, uses saved prefs) |
| GET | /api/orders | User's orders |

### Observability & Business  *(served by obs, proxied through main_app)*
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/metrics/real | Real-time per-node metrics + SRI (6 nodes incl. Frontend) |
| GET | /api/metrics/golden-signals | 4 Golden Signals |
| GET | /api/metrics/customer-experience | Apdex, P50/P95/P99, Error Budget |
| GET | /api/metrics/business | Conversion funnel + revenue |
| GET | /api/metrics/reliability | Reliability Score (SRI + Apdex + Availability + Conversion) |
| GET | /api/metrics/attribution | SRI dip attribution per node per signal with business impact |
| GET | /api/metrics/correlation?window_seconds= | SRI ↔ Conversion time series + Pearson r + healing annotations |

### Customer Experience & Frontend RUM
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/cx/metrics?window_seconds= | CX metrics + healing before/after deltas |
| POST | /api/cx/synthetic-user/run | Run a synthetic user journey through the portal |
| POST | /api/rum/beacon | Browser RUM beacon — feeds Frontend node (rate-limited 1/sec/session) |

### Healing (Adaptive + Topology + Propagation)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/healing | Overview (mode, SRI, RCA, FEA, adaptation) |
| GET | /api/healing/status | Full engine status |
| GET | /api/healing/fea?granularity=service\|component\|endpoint | Strict FEA with terminology mapping (hierarchical, 3 tiers) |
| GET | /api/healing/rca | Root Cause Analysis (spectral + FEA) |
| GET | /api/healing/trend | SRI interpolation + non_recoverable detection (Eq. 7) |
| GET | /api/healing/resilience-debt | E(t) = ∫Φ dt + Cost ∝ 1/SRI |
| GET | /api/healing/adaptation | Adaptive selector state (exhausted/effective) |
| GET | /api/healing/recommendations | Ranked actions with recovery path |
| GET | /api/healing/history | Execution log with effectiveness tracking |
| GET | /api/healing/topology/schema | Single source of truth for services/components/endpoints/edges (3 tiers, version=2) |
| GET | /api/healing/active-propagations | Auto-detected real failure propagations |
| POST | /api/healing/auto-propagation/config | Enable/disable detection + autonomous heal |
| POST | /api/healing/fault-propagation | Simulate Laplacian fault diffusion from a source (`granularity ∈ {service,component,endpoint}`) |
| POST | /api/healing/auto-dampen-wave | Auto-compute + execute the dampening cut-edge action (`granularity ∈ {service,component,endpoint}`) |
| POST | /api/healing/optimize-sequence | Compute ordered healing plan (BFS-depth + score) |
| POST | /api/healing/execute-sequence | Run an ordered healing plan with delay between steps |
| POST | /api/healing/toggle | Enable/disable engine |
| POST | /api/healing/trigger | Manually execute an action |
| GET  | /api/healing/aggressive/status | Aggressive (proactive) healing mode status + last 10 fires |
| POST | /api/healing/aggressive/toggle | Admin-only: `{enabled, debt_rate_threshold, min_lift_threshold}` |
| GET  | /api/healing/ladder/current | Live escalation ladder + version + last-synth metadata + rollback-guard state |
| GET  | /api/healing/ladder/history?limit=20 | Version timeline of synthesized ladders (each entry includes diff vs prior) |
| GET  | /api/healing/ladder/gain-matrix | Current per-(node, action) gain scores driving the synthesizer's ranking |
| POST | /api/healing/ladder/synthesize | Admin-only: force an immediate synth pass (no waiting for scheduled tick) |
| POST | /api/healing/ladder/rollback | Admin-only: revert to the previous ladder version |
| POST | /api/healing/ladder/toggle | Admin-only: `{enabled: true/false}` — disable auto-synth |
| GET  | /api/healing/rum-sequences/top?limit=N | Top RUM-validated healing sequences, ranked by composite user-felt gain |
| GET  | /api/healing/rum-sequences/status | Learner state (top_total, nodes covered, last pass) |
| POST | /api/healing/rum-sequences/run-now | Admin-only: force an immediate mining pass |
| GET  | /api/phase/state | Current per-service operational phase, composite σ, eutectic distance, retry-amp & healing-sat flags |
| GET  | /api/phase/history?limit=60 | Per-tick σ + phase trajectory (for the dashboard sparkline) |
| GET  | /api/healing/stagnation/state | Action Stagnation Guard: currently-removed (node, action) pairs, per-pair mean |ΔSRI|, cooldown countdowns, recent events |
| POST | /api/healing/stagnation/restore | Admin-only: `{node, action}` — manually restore a quarantined pair |
| POST | /api/healing/stagnation/reset | Admin-only: clear the entire stagnation list |
| GET  | /api/economic-reliability/state | Phase 3 / Unified-Model economic metrics — R_econ, R = W·R_S/C_T, cost decomposition (C_I/C_O/C_H/C_F), counterfactual heal-saved revenue/min, R_S |
| GET  | /api/economic-reliability/trend?limit=60 | Per-tick economic trajectory for sparklines (W, C_T, R_econ, R, R_S, conversion) |
| GET  | /api/rst/state | Current RST snapshot — per-node K_A…K_R, K_eff, σ, ε + spectral (λ₂, λmax, RST-SRI) |
| GET  | /api/rst/history?limit=60 | Rolling RST history for trend charts |
| POST | /api/rst/scenario | Inject a stress scenario `{name, overrides: {node: {K_A…}}, duration_s}` |
| DELETE | /api/rst/scenario | Clear the active RST scenario |

### Admin (Slack/Discord webhooks)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/admin/webhooks/status | Webhook config status |
| POST | /api/admin/webhooks/test | Send a test alert to all configured webhooks |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Kubernetes liveness probe (served locally by whichever service answers — main_app on 8001, obs on 8002) |
| GET | /api/health | API health check (main_app) |

### Internal (obs only, not exposed via ingress)

These endpoints are bound on port 8002 and are called *only* by the main app's middleware. They are not reachable from the public ingress.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/internal/events/request | `{path, method, latency, is_error}` — main_app middleware fires this per request; obs feeds it into the `MetricsAggregator`, alert ticks, SRI interpolator, and resilience-debt accumulator |
| POST | /api/internal/events/business | `{event_type, value}` — main_app emits this on `page_view`, `add_to_cart`, `checkout_start`, `order_complete`; obs feeds it into `BusinessMetrics` (funnel + revenue) |

---

## Spectral Resilience Index (SRI)

The SRI is derived from the **algebraic connectivity** of the infrastructure graph:

1. **Edge weights** encode link health: `w_ij = (Traffic / Latency) * (1 - Saturation) * (1 - Error)`
2. **Laplacian matrix** L is constructed from these weights
3. **Eigenvalues** are computed: `SRI = lambda_2 / lambda_max`
4. **Fiedler vector** (2nd eigenvector) identifies spectrally isolated (degraded) nodes

A high SRI means all service links are healthy. A low SRI means the graph is close to partitioning — some component is disconnecting from the healthy cluster.

---

## Finite Element Analysis (FEA)

The system graph is treated as a **structural mesh** for mechanical stress analysis:

| Concept | Mapping |
|---------|---------|
| Stiffness Matrix K | Graph Laplacian (edge weights as spring constants) |
| Load Vector f | Node degradation (30% latency + 45% error + 25% saturation) |
| Displacement u | Solved via pseudo-inverse: u = K_pinv * f |
| Strain Energy | SE_i = 0.5 * |u_i| * K_ii * |u_i| |
| Von-Mises Stress | Combined direct stress and load magnitude |
| Yield Threshold | Adaptive: mean(VM) + 0.5*std(VM), floor 0.15 |

Nodes exceeding the yield threshold are **actively failing** and receive corrective actions.

---

## SRI Interpolation & Trend Prediction

A **quadratic polynomial** is fitted to SRI history (last 200 samples):

- **Velocity** (dSRI/dt): rate of change at current time
- **Acceleration** (d2SRI/dt2): whether degradation is accelerating
- **Prediction**: projected SRI at T+30s and T+60s
- **Trend Classification**:
  - `critical_degrading`: velocity < -0.005 AND acceleration < -0.0001
  - `degrading`: velocity < -0.002
  - `recovering`: velocity > 0.002
  - `stable`: otherwise

This drives healing urgency: critical_degrading fires ALL yield-node CAs simultaneously.

---

## Adaptive Auto-Healing Engine

### The Problem
Naive auto-healing repeats the same action even when it produces zero improvement. Example: `rate_limit` fired 47 times on API with `sri_delta = 0.0` each time. This is **healing stagnation** — the system is active but not effective.

### The Solution: Self-Learning Action Selector

1. **Effectiveness Tracking**: Every execution records its `sri_delta`. If the last 5 executions all produced delta < 0.001, the action is marked **"exhausted"**.

2. **Adaptive Selection**: `_select_adaptive_action(node)` walks the escalation ladder, skipping exhausted and cooldown-blocked actions.

3. **Auto-Reset**: If an exhausted action later produces a positive delta (conditions changed), exhaustion clears automatically.

4. **Stagnation Alert**: When ALL strategies produce nothing, broadcasts `healing_stagnation` event for human intervention.

### 3-Tier Healing Strategy

```
Tier 1: FEA Multi-CA (multiple yield-exceeded nodes, all get adaptive actions)
  |-- If multiple nodes are stressed, fire CAs on all of them
  |-- Count depends on trend: critical=all, degrading=top3, stable=top2
  
Tier 2: RCA Adaptive (single root cause node, walk its escalation ladder)
  |-- If primary action is exhausted, auto-escalate to next
  
Tier 3: Threshold Fallback (any triggerable non-exhausted action)
  |-- Last resort scan of all actions
  
Tier FAIL: Stagnation Alert (all exhausted, need human)
```

---

## Escalation Ladders & Cross-Node Healing

### Escalation Ladders

Each node has an ordered list of alternative actions. When the primary is exhausted, the system auto-escalates. The values below are the **cold-start** ladders shipped in source; the **Ladder Synthesizer** (iter 30) continuously rewrites them at runtime from observed reliability gains — query the current ladder with `GET /api/healing/ladder/current`.

| Node | Cold-start Escalation Ladder |
|------|------------------------------|
| Frontend | scale_out_frontend |
| API | rate_limit -> circuit_breaker -> api_error_suppression -> cache_flush |
| Cache | cache_flush -> scale_out_cache_node -> connection_pool_reset -> rate_limit |
| Backend | circuit_breaker -> rate_limit -> queue_drain -> connection_pool_reset |
| DB | connection_pool_reset -> scale_out_db_read_replica -> cache_flush -> circuit_breaker |
| Queue | queue_drain -> rate_limit -> connection_pool_reset |

### Cross-Node Healing

When ALL actions in a node's ladder are exhausted, the system tries healing **neighbor nodes** (graph adjacency):

| Node | Neighbors |
|------|-----------|
| API | Cache, DB, Queue |
| Cache | API, DB |
| Backend | Queue |
| DB | API, Cache |
| Queue | API, Backend |

The full neighbor escalation ladder is walked (not just primary action).

---

## Golden Signals

| Signal | What It Measures | Health Formula |
|--------|-----------------|----------------|
| Latency | Average response time (ms) | 1 - min(avg/threshold, 1) |
| Traffic | Requests per minute | min(rpm/target, 1) |
| Errors | Error rate (%) | 1 - min(rate/threshold, 1) |
| Saturation | Capacity utilization (%) | 1 - min(util/threshold, 1) |

Each signal contributes to SRI with weights: Errors (40%), Latency (30%), Saturation (20%), Traffic (10%).

---

## Customer Experience Metrics

| Metric | Description |
|--------|-------------|
| Apdex | (Satisfied + Tolerating*0.5) / Total. T=200ms |
| P50/P95/P99 | Latency percentiles |
| Availability | % of non-error responses |
| Error Budget | Based on 99.5% SLO target |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend won't start | Check `MONGO_URL` in backend/.env |
| Frontend blank | Ensure `REACT_APP_BACKEND_URL` is set to the main app URL (port 8001) |
| `/api/metrics/*` returns `502 Observability service unreachable` | The obs service (port 8002) is down or unreachable. Run `sudo supervisorctl status backend_obs` and `tail -50 /var/log/supervisor/backend_obs.err.log`. The main app keeps serving e-commerce even when obs is down. |
| Dashboard shows stale data but storefront works | Same as above — obs is degraded but main app is healthy. Telemetry continues to be sent (fire-and-forget) and will resume once obs is back. |
| Admin endpoints return 401 through proxy | Cookies are forwarded but `JWT_SECRET` must be identical in the env that both processes read. Confirm with `grep JWT_SECRET /app/backend/.env`. |
| `/ws/alerts` doesn't push in production | Confirm the cluster ingress allows HTTP Upgrade for `/ws/*`. Dashboard panels still update via REST polling regardless. |
| Grafana not loading | Grafana is optional; set `INFLUX_TOKEN` in .env |
| SRI always 0.85 | Generate traffic (browse products, place orders) to complete warmup |
| Healing not firing | Auto-healing is ON by default; check `/api/healing/status` |
| All actions exhausted | System needs time for metrics to change; or adjust `stagnation_threshold` |

---

## License

Proprietary. All rights reserved. See `SRI_Whitepaper.md` for intellectual property notice.
