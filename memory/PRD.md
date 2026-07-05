# FreshCart - Grocery E-Commerce with Reliability-First Adaptive Healing

## Problem Statement
E-commerce platform with observability where **resilience (SRI) is the MEANS, business reliability is the GOAL**. The system uses SRI dips as signals, decomposes them into per-node per-signal attributions mapped to business impact (conversion, Apdex, revenue), and applies precision corrective actions that improve both infrastructure health AND business outcomes.

## Core Philosophy
> "Alerts guided by SRI dip, but attribution and emergent intelligence ensures business metrics and conversion funnel also show improvement."

## Architecture (distributed, Feb 2026)
Two FastAPI processes managed by supervisor in the same pod, sharing one MongoDB:

| Service | Port | Owns | Source file |
|---------|------|------|-------------|
| `backend` (main_app) | **8001** (public) | Auth, products, cart, orders, admin, observability proxy, fire-and-forget event emission | `/app/backend/server.py` (~670 lines) |
| `backend_obs` | **8002** (internal) | `MetricsAggregator`, `SRIInterpolator`, `ResilienceDebtAccumulator`, `CorrelationTracker`, `AutoPropagationDetector`, `HealingSequenceOptimizer`, `CustomerExperienceTracker`, `BusinessMetrics`, `SRIAttributionEngine`, `AlertManager`, `WebhookNotifier`, `HealingEngine`, auto_healing_loop, auto_propagation_loop, all `/api/metrics/*`, `/api/healing/*`, `/api/cx/*`, `/api/rum/*`, `/api/alerts*`, `/api/admin/webhooks/*`, `/api/grafana/*`, `/ws/alerts`, plus `/api/internal/events/{request,business}` receivers | `/app/backend/obs_server.py` (~4780 lines) |

- Frontend: React + TailwindCSS + Shadcn/UI (port 3000) — unchanged `REACT_APP_BACKEND_URL`.
- Database: MongoDB (shared by both services).
- Time-series: InfluxDB (optional).
- Visualization: Grafana (optional).

### Inter-service communication
1. **Reads**: main_app proxies any GET/POST under `/api/{metrics,healing,cx,rum,alerts,admin/webhooks,grafana}/...` synchronously to `http://localhost:8002/api/...` via a shared `httpx.AsyncClient`. Cookies/headers preserved, so auth (admin) works through the proxy.
2. **Request telemetry**: `_EventEmitMiddleware` in main_app emits `asyncio.create_task(httpx.post('/api/internal/events/request', ...))` for every `/api/*` request — fire-and-forget, swallowed errors.
3. **Business events**: cart_add / order_create / buy_now / get_products fire `emit_business('add_to_cart' | 'page_view' | 'checkout_start' | 'order_complete', value)` to `/api/internal/events/business`.
4. **WebSocket**: main_app's `/ws/alerts` bridges to obs `/ws/alerts` using the `websockets` library.

## Key Systems (unchanged math — now hosted in obs service)

### 1. Reliability Score (Business Outcome Metric)
Composite: 25% SRI + 35% Apdex + 25% Availability + 15% Conversion — `GET /api/metrics/reliability`.

### 2. SRI Attribution Engine
Decomposes SRI dips into per-node, per-signal contributions AND maps to business impact — `GET /api/metrics/attribution`.

### 3. Business Metrics Funnel
Tracks: page_view → add_to_cart → checkout_start → order_complete — `GET /api/metrics/business`.

### 4. Precision Adaptive Healing
Signal-aware action selection, business justification, steady pressure mode, critical override, escalation ladders, cross-node healing, stagnation detection — `GET /api/healing`, `POST /api/healing/trigger`, etc.

### Signal-to-Action Affinity Map
| Action | Latency | Errors | Saturation |
|--------|---------|--------|------------|
| cache_flush | 0.8 | 0.5 | 0.1 |
| rate_limit | 0.2 | 0.3 | 0.8 |
| circuit_breaker | 0.4 | 0.9 | 0.2 |
| connection_pool_reset | 0.7 | 0.2 | 0.6 |
| queue_drain | 0.5 | 0.1 | 0.7 |
| api_error_suppression | 0.3 | 0.9 | 0.1 |

### Signal-to-Business Impact Map
| Signal | Conversion | Apdex | Revenue |
|--------|-----------|-------|---------|
| latency | 0.4 | 0.6 | 0.3 |
| errors | 0.7 | 0.5 | 0.6 |
| saturation | 0.2 | 0.3 | 0.1 |

## API Endpoints (all reachable via main_app:8001 → ingress)
- **E-commerce (main_app)**: `/api/auth/*`, `/api/products`, `/api/categories`, `/api/cart/*`, `/api/orders`, `/api/orders/*`, `/api/orders/buy-now`, `/api/user/delivery-preferences`, `/api/admin/products`, `/api/admin/orders[/{id}/status]`
- **Observability (proxied to obs:8002)**: `/api/metrics/*`, `/api/healing/*`, `/api/cx/*`, `/api/rum/beacon`, `/api/alerts*`, `/api/admin/webhooks/*`, `/api/grafana/*`, `/ws/alerts`
- **Health**: `/health`, `/api/health` (both services answer locally)
- **Internal (obs only, not exposed via ingress)**: `POST /api/internal/events/request`, `POST /api/internal/events/business`

## Recently Shipped
- **Feb 2026 — Fastest Path-to-Ψ_s Planner (iter 45)** — *Greedy IPC forward-simulation through the healing ladder*
  - **Algorithm** (`HealingEngine.plan_path_to_stable`): per-node greedy forward simulation. At each step evaluates every applicable action, picks the highest **improvement-per-cost** (IPC = −Δd² / cost) where the projected state monotonically decreases d² to Ψ_s. Forward-projects the state and repeats. Stops on target reached (d² ≤ 0.001), no improving action found, or max_steps (default 5).
  - **One-sided distance metric**: Ψ_s is treated as a CEILING of safe operation, not a fixed target. Below it on any axis ⇒ d² = 0 ("stable, no healing needed"). Above it ⇒ d² > 0 and the planner computes a path back. This eliminates the degenerate case where natural states (below Ψ_s) would otherwise return "no path exists".
  - **Endpoints**: `GET /api/healing/path-to-stable?node=API&max_steps=5` returns a single plan; `GET /api/healing/path-to-stable` returns per-node plans + summary across all nodes. Admin-only `POST /api/healing/path-to-stable/execute` (with optional `dry_run`) fires the sequence via `healing_engine.execute_action` with `triggered_by="path_to_stable"` and per-step reason annotations.
  - **Frontend**: new `PathToStableCard.jsx` (mounted on System Health tab). Shows per-node plan as a sequence of action pills with Δd² + cost annotations, REACHES_Ψ_s / PARTIAL badges, and a stable-nodes footer. Header shows total actions + total cost across all nodes.
  - **Verified live**: card rendered with 3 plans:
    - Frontend (PARTIAL) — `scale_out_frontend` (Δd²=−0.2144) — 1 step $0.50
    - API (REACHES Ψ_s) — `rate_limit` (Δd²=−0.2025) — 1 step $0.15
    - Backend (REACHES Ψ_s) — `scale_out_backend` (Δd²=−0.1977) — 1 step $0.50
    - Cache/DB/Queue already at/below Ψ_s — no plan needed
  - Total system-wide healing cost to reach Ψ_s: **$1.15 for 3 actions**.
  - **Unit-tested**: with injected stressed state (l=5×baseline, m=0.85, q=0.50), API planner produced optimal 2-step path: `api_error_suppression`($0.05) → `rate_limit`($0.15), d²: 0.144 → 0.0003, REACHED Ψ_s.

- **Feb 2026 — Nomenclature Audit: Ψ_c → Ψ_s (Stable Operating Point) (iter 44)** — *Honest naming*
  - **Diagnosis**: In metallurgy, a true *eutectic point* is a topological triple-point where multiple phases meet at a single (composition, temperature) coordinate. The Sunder-paper-inspired Ψ_c at (M/M_cap=0.55, L/L₀=1.5) does NOT sit at a multi-phase meeting point — checking `PHASE_BOUNDS` in `obs/engines/phase_classifier.py`, Ψ_c only touches the L boundary of `stable_throughput` (other phases either fall above or below this M ratio). It's a stable operating *target*, not a topological triple-point.
  - **Fix**: User-facing surfaces now read **Ψ_s** (Stable Operating Point) instead of Ψ_c (Eutectic Point). Honest naming surfaces what the point actually is. Backend variable `EUTECTIC_POINT` is preserved for backward compatibility with ~12 files that reference it across the iter 37/41/42/43 wiring; new alias `STABLE_POINT = EUTECTIC_POINT` is the canonical name in new code.
  - **Files updated**: `phase_classifier.py` (comment + alias), all 5 user-facing dashboard cards (`FEATopologyHeatMap`, `PhaseDiagramView`, `PhaseTransitionCard`, `StabilityFunctionalCard`, `AggressiveHealingCard`). PhaseDiagramView's Ψ marker label updated from "Ψ_s (eutectic point)" to "Ψ_s (stable operating point)".
  - **Verified**: zero `Ψ_c` strings remain in the frontend; ~14 `Ψ_s` strings now present.

- **Feb 2026 — Resilience Debt D(t) Integral Curve (iter 43, Unified-Model Phase 1)** — *Live plot of E(t) = ∫₀ᵗ Φ(τ)dτ*
  - Extended `ResilienceDebtAccumulator` (`obs/trackers/core.py`) with a 720-sample (~1h) history deque appended on every `.record()` call. Each entry is `{t, phi, E, cost, sri}`.
  - New endpoint `GET /api/healing/resilience-debt/history?limit=240` returns the per-sample series for plotting.
  - Existing `ResilienceDebtCard.jsx` rewritten — preserves the 3-tile snapshot (Cum. Cost / Energy ∫Φdt / Burn rate ∝ 1/SRI) and adds two stacked live charts:
    - **Φ(t)** — instantaneous debt-rate curve (orange polyline)
    - **E(t) — D(t) INTEGRAL CURVE** (red polyline with **shaded area-under-curve** at 15 % opacity so the integration relationship is visually obvious — slope of E(t) IS Φ(t))
  - **Verified live**: card rendered with 8 samples, Cum. Cost $7.27, Energy=58.1063, Burn rate $0.050/s. Φ(t) range 0.0149–2.3758, E(t) range 0.0000–58.1063 (monotonically non-decreasing as expected). Both `data-testid="debt-chart-phi"` and `data-testid="debt-chart-E"` present in DOM. Linter clean. Backend logs clean.

- **Feb 2026 — Stability Functional Ψ (iter 42, Unified-Model Phase 2)** — *Lyapunov scalar over the phase-space*
  - New engine `obs/engines/stability_functional.py` computing `Ψ(t) = α·⟨d_n²⟩ + β·D_accum + γ·Var(d_n)` every 5 s. Read-only — measures stability, doesn't act (iter 41's unified eutectic-distance objective is what drives the system *toward* low Ψ).
  - Linear-least-squares dΨ/dt over the last 6 samples (~30 s). Classification: STABILISING (dΨ/dt < −0.003), STEADY (|dΨ/dt| ≤ 0.003), DESTABILISING (dΨ/dt > 0.003) — all env-tunable.
  - **Endpoints**: `GET /api/stability/{state,trend}` exposed via the gateway (`/stability` added to `_OBS_PROXY_PREFIXES`).
  - **Dashboard**: new `StabilityFunctionalCard.jsx` mounted next to `EconomicReliabilityCard` on System Health. Renders 4-tile headline (Ψ current / dΨ/dt / Ψ min 5m / Ψ max 5m), classification banner (green stabilising / yellow steady / red destabilising), 3-component decomposition (α-quadratic-dev / β-debt / γ-dispersion with their weights), 60-sample Ψ-trajectory sparkline (color follows current classification), and 6-cell per-node d_n grid.
  - **Verified live**: card rendered with 27 samples, Ψ=7.568, dΨ/dt=+4.93e-2, **DESTABILISING** banner correctly classified (debt accumulator term dominates because no scale-in path is active). Per-node d_n grid: Cache 0.199 (green), Queue 0.105 (green), Frontend 0.250, API 0.239, DB 0.273, Backend 0.216 (all amber).

- **Feb 2026 — Unified Eutectic-Distance Objective (iter 41)** — *Auto-heal's primary goal is now `minimize d(x, Ψ_c)²`*
  - **New `HealingEngine.simulate_eutectic_delta(node, action_id)`** — generic per-action simulator that projects how applying an action would shift `(L̂, Q, M, E)` for its target node, then returns `{cur_d², new_d², delta_d², target}`. Covers all 14 action types via `_ACTION_AXIS_EFFECTS` (dampeners attenuate L̂ and pull Q toward Ψ_c.Q; scale_* uses iter 37's boost math).
  - **`AggressiveHealingMode.rank_actions` scoring rewritten**: primary term is `eut_pull_score = -W_EUT · Δd²` (W_EUT=5.0, env-tunable). Business-residual `W_BIZ × (0.6·apdex + 0.4·conv)` (W_BIZ=0.20) captures what Ψ_c doesn't model. Cost penalty + cheap-first bias + plateau-relaxer all preserved.
  - **API surface**: `preview-ranking` now returns per-action `eut_target / eut_cur_d² / eut_new_d² / eut_delta_d² / eut_pull_score / biz_score`.
  - **Dashboard**: cheap-first panel header renamed "Cheap-First Escalation Order — Unified Objective: minimize d(x, Ψ_c)²". Each ranked action shows `Δd²` column (green if negative = pulls toward Ψ_c; red if positive = pushes away; grey if 0).
  - **Verified live**: 14 actions ranked, simulator reaches all 6 nodes (target column populated). Cold-start Δd²=0 across the board is mathematically correct (idle system is on the low side of Ψ_c; reducing L̂/M further can't help). Non-zero deltas surface the moment any node has actual stress — which is the only state the engine fires in anyway.

- **Feb 2026 — Cheap-First Auto-Heal Escalation (iter 40)** — *AggressiveHealingMode genuinely walks low-cost-high-improvement → higher-cost*
  - **`AGGR_LOW_COST_BIAS = 0.08`** scoring term added to `AggressiveHealingMode.rank_actions`: `score += BIAS × (1 − cost)`. Mirrors the iter 39 synthesizer-side complexity bias but acts on the aggressive engine's independent score (the engine that doesn't walk the synthesized ladder). Adds +0.076 for $0.05 actions, ~+0.032 for $0.60 actions — enough to order cheap-first when measured ΔSRI is comparable, never strong enough to override a costly action with clearly higher observed gain.
  - **Plateau-relaxer (env-tunable: `AGGR_PLATEAU_FIRES=3`, `AGGR_PLATEAU_THRESHOLD=0.002`, `AGGR_PLATEAU_RELAX=0.30`)**: when an action has been tried ≥ 3 times AND its recent mean |ΔSRI| sits below the noise floor (0.002), the cheap-first bias for that specific action multiplies by 0.30 — letting costlier alternatives become competitive. Drives natural escalation: cheap is tried first, escalates only when the cheap option proved insufficient.
  - **New endpoint** `GET /api/healing/aggressive/preview-ranking` — computes the current rank order on-demand so the dashboard can show the cheap-first escalation in real time, even when the engine isn't actively firing.
  - **Status surface**: `aggressive/status` now includes a `cheap_first_escalation` block with per-action `{cost, low_cost_bias, plateaued, recent_abs_delta}` from the last rank scoring.
  - **Dashboard**: `AggressiveHealingCard` adds a "Cheap-First Escalation Order (next fire)" panel — top-8 ranked actions with rank number, T1–T4 tier dot, name, plateaued badge ★, cost bar, $cost, and signed score. Header shows `bias=+0.08 · plateau<0.002`.
  - **Verified live**: 8 actions visible in rank order on the screenshot. api_error_suppression at rank 1 (+0.146), scale_in_* batch at $0.05 with +0.084 each, scale_out_cache_node at rank 7 ($0.40), cache_flush at rank 8 showing **★ PLATEAU** (already fired enough times to drop below noise floor — costlier alternatives now competitive).

- **Feb 2026 — Complexity-Sequenced Healing Ladders (iter 39)** — *Ladders read "low-complexity high-improvement first → escalating-complexity at position N"*
  - New per-action complexity score `_ACTION_COMPLEXITY` in `obs/engines/ladder_synthesizer.py` (range [0, 1]) — composite of cost, cooldown, persistence-duration, and blast radius. Four tiers:
    - **T1 simple** (≤ 0.25): cache_flush, api_error_suppression, rate_limit, queue_drain, scale_in_*
    - **T2** (0.25–0.50): connection_pool_reset, circuit_breaker
    - **T3** (0.50–0.75): scale_out_cache_node
    - **T4 complex** (> 0.75): scale_out_frontend, scale_out_backend, scale_out_db_read_replica
  - **Complexity-bias scoring term** in `compute_gain_matrix`: `score += LADDER_COMPLEXITY_BIAS × (1 − complexity)` (env-tunable, default 0.12). Adds up to +0.108 for the simplest actions, ~+0.018 for the most complex — enough to break ties between comparable observed gains, not strong enough to override actions with strong measured ΔSRI.
  - **API surface**: `/api/healing/ladder/current` now returns `complexity_ladder` (per-position complexity); `/api/healing/ladder/gain-matrix` returns the full `complexity` map + `complexity_bias` coefficient.
  - **Dashboard**: `LadderSynthesizerCard` renders a colored complexity dot on every action pill (green T1, cyan T2, amber T3, red T4) and a T1→T4 legend. Section header now reads "Synthesized Ladders (per node) — low-complexity high-improvement first".
  - **Verified live**: synthesized v285 produces ladders dominated by Tier-1 dampeners (e.g. Backend: rate_limit → cache_flush → api_error_suppression → queue_drain — all green T1). Scale-out (Tier 4) only appears at position 4 where Tier-1/2 actions don't deliver on the affected node (e.g. Queue position 4 = scale_out_cache_node).

- **Feb 2026 — Eutectic-Pull Badges on FEA Topology Heat Map (iter 38)** — *Operators can SEE the pull, not just read about it*
  - Every service node on `FEATopologyHeatMap` now renders a small `→Ψ_c d=0.XX [×N]` badge above the node, fetched from `/api/phase/state` (`eutectic_distance` per node) and `/api/healing/status` (active `capacity_boosts`).
  - Color thresholds: green < 0.20 (at/near Ψ_c), amber 0.20–0.40 (in transit), red > 0.40 (far, system actively pulling).
  - Optional `×N` multiplier renders when an active capacity boost is present, signalling the node is currently scaled by the eutectic-guided gate. Bold weight when boost > 1.05.
  - **New component**: `EutecticBadge` sub-component appended to `FEATopologyHeatMap.jsx`.
  - **Verified live**: 6/6 badges rendered with correct distance + boost values (Frontend d=0.07 ×2.00, Cache d=0.23 ×1.85, DB d=0.28 ×1.70, Backend d=0.08 ×1.75, API d=0.23, Queue d=0.09).

- **Feb 2026 — Eutectic-Guided Scaling + scale_in_* (iter 37)** — *Every scaling decision provably pulls toward Ψ_c*
  - **Four new `scale_in_*` actions** (Frontend, Cache, DB, Backend) — cheap (cost 0.05, cooldown 120 s) cost-saving actions that DRAIN the active capacity boost (multiplicative factor in (0, 1)). Symmetry: each of the four scalable components now has both a `scale_out_*` and a `scale_in_*` action.
  - **Eutectic-distance gate** in `HealingEngine._scale_pulls_to_eutectic(node, action_id)`: every scale_* trigger now passes through a simulator that projects the post-action `(L̂, M_ratio)` coordinates (both divide by `current_boost / new_boost`), computes the L2 distance to Ψ_c = (0.05, 0.30, 0.55, 0.02), and fires only if the projected distance is ≥ 1 % smaller than the current distance. This makes EVERY scaling decision provably toward Ψ_c:
    - `scale_out_*` blocked on idle nodes (would push *away* from M_ratio=0.55)
    - `scale_in_*` blocked on stressed nodes (would push toward M_ratio=1.0, away from Ψ_c)
    - `scale_in_*` blocked when no boost is active (already at baseline)
  - **Symmetric `MetricsAggregator.apply_capacity_drain(node, drain_factor, duration)`** mirrors `apply_capacity_boost`. Drains the active multiplier; if it falls below 1.05 the boost is cleared entirely.
  - **Verified by unit-math** (4 cases): stressed→scale_out cur² 0.249→0.009 ✓; idle→scale_out unchanged ✓; over-provisioned→scale_in 0.20→0.14 ✓; stressed→scale_in (wrong direction) 0.22→1.64 BLOCKED ✓.

- **Feb 2026 — Capacity-Boost Wiring + scale_out_backend (iter 36)** — *Fix for the "metallurgical yielding" state*
  - **Root cause**: scale-out actions (`scale_out_frontend`, `scale_out_cache_node`, `scale_out_db_read_replica`) carried a `saturation_reduction` *intent* in `HealingEngine._apply_healing_effect`, but `MetricsAggregator.apply_dampener` only modelled `latency_factor` + `error_suppression`. The capacity-reducing intent was never propagated, and `get_node_metrics` hard-coded `saturation = min(traffic / 100, 1.0)`. Frontend/Backend therefore stayed pinned at `saturation = 1.0` no matter how many scale-out actions fired — applying scaling stress produced no elastic response in the metric (the metallurgical yielding regime).
  - **Fix**: new parallel channel `MetricsAggregator.apply_capacity_boost(node, multiplier, duration)`. Boosts compound multiplicatively within the persistence window (cap `CAPACITY_BOOST_CEILING = 8.0`). `get_node_metrics` now computes `saturation = min(traffic / (100 × boost), 1.0)` and applies a queueing-theoretic latency divisor (`latency /= boost` for boost > 1.0). `HealingEngine._apply_healing_effect` invokes the new channel for all scale-out actions with `(multiplier, duration)` config: Frontend 2.0×/120 s, Cache 1.85×/120 s, DB 1.7×/120 s, Backend 1.75×/120 s.
  - **New action** `scale_out_backend` (cost 0.50, cooldown 200 s, sat-trigger > 70% OR latency > 150 ms). Backend was previously pinned at sat = 1.0 with no scaling option. Added to `escalation_ladder`, `_should_trigger`, `_apply_healing_effect`, `AggressiveHealingMode.action_cost`, `LadderSynthesizer.DEFAULT_LADDER`, `_ACTION_SIGNAL_EFFECTS`, and `action_cost`.
  - **Operator surface**: active boosts now surface live under `GET /api/healing/status.capacity_boosts` ({node: {multiplier, expires_in_s}}).
  - **Verified live**: after restart + traffic generation, Backend traffic=8 + boost=1.75× ⇒ sat = 8/(100×1.75) = **0.046** (matches reported per-node phase state exactly); Cache traffic=2 + boost=1.85× ⇒ sat = **0.011** (matches). Synthesizer auto-promoted `scale_out_backend` into Frontend's ladder v207 within 30 s of the deploy.

- **Feb 2026 — Economic Reliability (Unified-Model Phase 3)** (iter 35) — *Resilience-to-dollars visualisation*
  - New read-only tracker `obs.trackers.economic_reliability.EconomicReliabilityTracker` composes existing observables (`BusinessMetrics`, `MetricsAggregator`, `HealingEngine.history`, `PhaseClassifier`) into the RSM economic equations (Eqs. 51/57/58 of SRI_Whitepaper §11.5.1):
    - `R_econ = W / C_T` where `W = revenue_5min ÷ 5` (USD/min)
    - `R = W · R_S / C_T` where `R_S = ΣH_i / Σσ_i` (soft-capped at 100 to handle idle-system degeneracy)
    - `C_T = C_I + C_O + C_H + C_F` — infra (env flat rate), observability (event-rate × `$/Kevt`), healing (dampener actions × per-action + scale actions × per-scale-action), failure (`max(0, projected_revenue_per_min − W)`)
  - **Counterfactual heal-saved revenue/min** — when `actual_conv > modeled_conv` the uplift × traffic × avg_order_value is integrated over the last 12 ticks and surfaced as the dollars the healing engine is currently rescuing.
  - Tick loop runs every 5 s starting 20 s after server boot; 240-sample history (~20 min) kept in-memory.
  - **Endpoints** (proxied through main_app): `GET /api/economic-reliability/{state,trend}`.
  - **Frontend**: new `EconomicReliabilityCard.jsx` on System Health — headline R_econ / R / W($/min) / heal-saved/min, segmented C_T bar (C_I / C_O / C_H / C_F), R_econ + W sparklines, R_S / conversion / orders / revenue-5m strip.
  - Verified: `/api/economic-reliability/state` returns full payload through the external preview URL; card renders with live data.

- **Feb 2026 — Action Stagnation Guard (iter 34)** — *Inner-loop dynamic action removal*
  - New `obs/engines/action_stagnation.py` (~225 LOC). `ActionStagnationGuard` watches every `HealingEngine.execute_action` outcome via a `record(node, action, sri_delta)` call wired into the execution path. When the last `WINDOW=4` attempts for a `(node, action)` pair all show `|ΔSRI| < EPSILON=0.003`, the pair is **dynamically removed** from the available action set for `COOLDOWN=180s`, then auto-restored.
  - **Two integration hooks** (the synthesizer + auto-heal cycle both consult the registry):
    1. `HealingEngine._should_trigger` now returns `False` immediately if `guard.is_blocked(node, action)` — the classical escalation walk progresses past stagnant pairs without waiting for synthesis.
    2. `LadderSynthesizer._build_new_ladder` filters stagnant pairs out of the top-K selection per node — newly-synthesized ladders never re-introduce a pair the inner loop has just removed.
  - **Admin endpoints**: `GET /api/healing/stagnation/{state, events}`, `POST /api/healing/stagnation/{restore, reset}` (admin gating on writes).
  - **Dashboard card** `ActionStagnationCard.jsx` (~180 LOC) on System Health — removed-pair table with cooldown countdowns + per-row Restore buttons, recent-events stream (stagnated / restored), Reset All admin control.
  - **Verified end-to-end live**: ran 60 s of auto-heal cycles on healthy system → guard detected `Cache@cache_flush`, `API@rate_limit`, `Backend@circuit_breaker` as stagnant → next ladder synthesis v95 excluded all three pairs (Cache ladder became `queue_drain → circuit_breaker → rate_limit → connection_pool_reset`) → admin restore + auto-cooldown both verified working. Dashboard renders rows with live cooldown timers and event stream.

- **Feb 2026 — Scaling Actions (iter 33)** — *Engine can now add capacity, not just dampen demand*
  - Three new `HealingAction` entries: `scale_out_frontend` (cost 0.50, cooldown 180 s, latency −45 % / saturation −60 %), `scale_out_cache_node` (cost 0.40, cooldown 150 s, latency −50 % / saturation −65 %), `scale_out_db_read_replica` (cost 0.60, cooldown 240 s, latency −40 % / saturation −55 %).
  - **Frontend is now a healable node** — added to `HealingEngine.escalation_ladder`, `node_neighbors`, `node_primary_action`, `node_signal_importance`, the synthesizer's `ALL_NODES`, and `MetricsAggregator` node list.
  - **Sequence-aware**: full first-class participants in the §12.7 escalation walk, §12.9 RUM sequence mining, §13.1 cold-start ladders. They appear in synthesised ladders' top-4 automatically just from saturation-affinity + cost reasoning — no manual ordering. Live snapshot: v74 promoted `scale_out_cache_node` to position 3 of API + Backend, `scale_out_frontend` to position 2 of Cache, `scale_out_db_read_replica` to position 3 of DB.
  - **Cost-aware promotion**: scaling has 0.40–0.60 cost vs 0.05–0.35 for dampener actions → the synthesizer's cost penalty deprioritises them as last-resort unless the gain matrix sees positive ΔSRI in the history. Under `healing_saturation` phase the brake doubles (cost_boost = 2.0) → scale-out thrashing on top of dampener thrashing is structurally prevented.
  - **Long dampener persistence (120 s)** — reflects that added infrastructure persists across cycles, vs 20–30 s for demand-suppression dampeners.
  - **Endpoints**: `POST /api/healing/trigger` accepts the three new `action_id` values directly. Verified live: each fires correctly, returns full healing record with golden_signals_before/after.
  - **README.md** new "Scaling Actions" feature block + updated cold-start ladder table. **SRI_Whitepaper.md** new §13.4 (Scaling Actions v7) with 4 design-choice subsections, 13.4.1 sequence participation, 13.4.2 closure-of-§12-loop narrative + live v74 ladder snapshot. ToC entry added.

- **Feb 2026 — RUM Ladder Learner (iter 32)** — *Reliability graded by user-felt outcomes*
  - New `obs/engines/rum_ladder_learner.py` (~285 LOC). Mines healing-action **sequences** (chains of consecutive heals within 15 s) from `correlation_tracker._annotations`, aggregates real-user RUM deltas (page_load_ms, perceived_speed, error_shown_rate) from `cx_tracker._samples` over 30 s before/after, computes composite gain `0.4·Δperceived + 0.4·clamp(−Δpage_load/500, −1, +1) + 0.2·(−100·Δerror_rate)`, keeps top-30 sequences globally + per-node top-6.
  - **Closed-loop feedback** into `LadderSynthesizer.compute_gain_matrix`: per-node action bonus up to `RUM_BONUS_COEFF = 0.15` added to the gain term. Actions that real users responded well to climb the synthesised ladder. Full gain decomposition is now `0.7·obs + 0.3·affinity − 0.05·cost_boost·cost(a) + RUM_BONUS·rum_norm(a, n)`.
  - **Persisted** to MongoDB `rum_validated_sequences` `{node, chain, actions[], cx_delta{...}, rum_gain, first_seen_at, last_seen_at}`. Restored on obs boot — cumulative user-validated knowledge survives restarts.
  - **Endpoints** `GET /api/healing/rum-sequences/{top, status}`, `POST /api/healing/rum-sequences/run-now`.
  - **Dashboard card** `RumValidatedSequencesCard.jsx` (~180 LOC) on System Health — per-row colored node pill, gain score, 3 RUM deltas (heat-coloured by direction), full chain rendered with `→` arrows between action pills, provenance footer.
  - **README.md** new feature block + 3 endpoint table rows. **SRI_Whitepaper.md** new §12.9 (sub-sections 1-7 covering sequence mining Eq. 12.9.1, composite RUM gain Eq. 12.9.2-4, persistence, closed-loop feedback Eq. 12.9.5-6, sequences-vs-actions rationale, operational surface, end-to-end loop diagram). ToC updated.
  - **Verified end-to-end live**: pumped real HTTP traffic + sequenced heals → learner produced 6 validated sequences (top_total=11), per-node bonuses visible in `LadderSynthesizer.compute_gain_matrix`, dashboard renders 10 rows with full chains (e.g. `circuit_breaker → queue_drain → connection_pool_reset → rate_limit → cache_flush → api_error_suppression` on Backend node).

- **Feb 2026 — Citation: Sunder's phase-transition framework** (iter 31 cont.)
  - `SRI_Whitepaper.md` §23 References gained three new entries: **[14]** Sunder, "Towards a New Physics of Software Systems: A Finite Element and Spectral Framework for Distributed Architectures", IJSR, March 2026 (https://www.ijsr.net/getabstract.php?paperid=MR26323100538); **[15]** Sunder, "Physics of Software Systems Part II: Stability Potential, Compute Energy, and Operational Cost in Enterprise Systems", SSRN preprint (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6580058); **[16]** Sunder, "Physics of Software Systems: A Spectral-Element Derivation of Resilience from Enterprise System Observables", SSRN preprint, 2026 (Scholar profile https://scholar.google.com/citations?user=dPKHEF8AAAAJ).
  - Inline citations added at the opening of §12.8 and §12.8.6 — phase taxonomy → [14], eutectic Ψ_c construction → [15].
  - README.md Operational Phase Classifier feature block now carries a one-line attribution pointing to §23 refs [14], [15].

- **Feb 2026 — Documentation: iron-carbide phase diagram** (iter 31 cont.)
  - `README.md` (793 → 796 lines): "Operational Phase Classifier" feature block expanded to describe both dashboard cards — the textual `PhaseTransitionCard` and the new 2D `PhaseDiagramView`. Eutectic point Ψ_c value corrected (L̂ = 0.05 ⇒ L/L₀ ≈ 1.5). Project Structure listing now mentions the new component file. Modularization table gained an "iter 31 — phase classifier" row.
  - `SRI_Whitepaper.md` (1623 → 1679 lines): §12.8.3 Ψ_c coordinate corrected (Eq. 12.8.6); §12.8.5 expanded to describe both `PhaseTransitionCard` and `PhaseDiagramView` as complementary visualisations; brand-new sub-section **§12.8.6 "Iron-Carbide-Style Phase Diagram"** maps metallurgy axes onto operational ones (carbon → M/M_cap, temperature → L/L₀, eutectic → Ψ_c) and motivates four diagram design decisions: √-scaled Y, why retry-amp & heal-sat aren't drawn as regions, dot+ring+tail per service, Ψ_c as the engine's gravitational centre. TOC entry updated.

- **Feb 2026 — Phase Diagram View (iron-carbide style)** (iter 31 cont.)
  - New `PhaseDiagramView.jsx` (~290 LOC) — 2D phase diagram with **X = M/M_cap** (memory saturation), **Y = L/L₀** (latency ratio, √-scaled). Renders the seven operational phases as filled regions, draws boundary lines, marks the Ψ_c eutectic point, plots each service as a labeled colored dot at its live (M/M_cap, L/L₀) position with a fading 20-sample trajectory trail, and overlays retry-amplification / healing-saturation regime banners (since those are temporal, not positional).
  - Backend tweak: `EUTECTIC_POINT.L_ratio` corrected from `0.50` (which mapped to 750 ms — unrealistic) to `0.05` (≈75 ms ⇒ L/L₀ ≈ 1.5) with accurate comment. `flags` now exposes `latency_baseline_ms`, `latency_ceiling_ms`, and `eutectic_l_over_l0` for the frontend to position the Ψ_c marker without re-deriving the unit conversion.
  - Verified live on `/dashboard` System Health tab: all 6 services plotted (Frontend in JVM Saturation, API on M_cap boundary, Cache/DB/Queue in Cold Start), trajectories visible, Ψ_c marker correctly placed at (0.55, 1.50).

- **Feb 2026 — Operational Phase Classifier (iter 31)**
  - New `obs/engines/phase_classifier.py` (~450 LOC). Computes per-service composite stress σ = αL + βQ + γM + δE every 5 s, classifies each node into one of 7 phases (`cold_start`, `warm_runtime`, `stable_throughput`, `jvm_saturation`, `retry_amplification`, `healing_saturation`, `cascading_collapse`) from (L/L₀, M/M_cap, σ, rate-of-change), and reports per-node eutectic-distance to Ψ_c.
  - **Two cross-system feedback brakes that gate other engines (the core value-add):**
    1. **Retry amplification** (traffic↑ ∧ errors↑ ∧ latency↑ over 30 s) → `AggressiveHealingMode.rank_actions()` returns `[]`, refusing to add load to the positive-feedback loop. Direct reduction in resilience-debt usage cost.
    2. **Healing saturation** (heals/min ÷ mean |ΔSRI| > 25) → `LadderSynthesizer` doubles its cost-penalty so cheap actions (`cache_flush`, `rate_limit`) outrank heavyweight ones (`circuit_breaker`, `connection_pool_reset`) on the next synth pass. Direct enabler of faster recovery.
  - **Phase-tagged ladder versions** (`phase_at_swap` in `synthesized_ladders` collection) — enables future cross-phase ladder learning (build reliability per improvement cycle).
  - **Endpoints**: `GET /api/phase/state`, `GET /api/phase/history?limit=N`. Added `/phase` to `_OBS_PROXY_PREFIXES` in main `server.py`.
  - **Frontend**: new `PhaseTransitionCard.jsx` (~225 LOC) on System Health tab — system-worst phase pill, σ + Ψ_c distance stats, retry-amp/heal-sat policy-effect banners, per-service rows with mini 2D phase-space dots at (L/L₀, M/M_cap) against the Ψ_c reference marker, σ trajectory sparkline.
  - **Verified end-to-end live**: classifier reports `worst_phase=healing_saturation`, `composite_sigma=0.260`, all 6 nodes classified, `synth_cost_penalty_boost=2.0` flowing into the next ladder synthesis — visible on dashboard.

- **Feb 2026 — Documentation: code-review quality pass** (iter 30 cont.)
  - `README.md`: new test-credential env vars (`ADMIN_TEST_EMAIL`/`PASSWORD`, `USER_TEST_EMAIL`/`PASSWORD`) added to the Environment Variables Reference; Running Tests section shows their usage; modularization table gained an iter-30 "quality pass" row covering the test-cred swap, `console.error` on previously-silent catches, `key={idx}` → stable keys, and `useMemo` on three hot JSX paths.
  - `SRI_Whitepaper.md`: modularization table mirrors the quality-pass row; new sub-section **"Static-analysis surface"** inside §6.1.5b documents the three recurring false positives the singleton-binding pattern triggers ("circular import", "undefined variable references", "dynamic-import security risk") with the architectural reality for each — so future CI lint failures don't trigger pattern-unwinding "fixes".

- **Feb 2026 — Code review fixes (P0/P1 surgical)** (iter 30 cont.)
  - **Security**: hardcoded admin/test credentials in `tests/test_iteration{14,18,19}_*.py` swapped to env-var reads (`ADMIN_TEST_EMAIL`, `ADMIN_TEST_PASSWORD`, `USER_TEST_EMAIL`, `USER_TEST_PASSWORD`) with current values as defaults so existing CI continues to pass.
  - **Error visibility**: 7 silent `catch {}` blocks across `DashboardPage.jsx`, `ProductsPage.jsx`, `OrdersPage.jsx`, `CheckoutPage.jsx`, `AggressiveHealingCard.jsx` now emit `console.error` (or `console.warn` for the per-item reorder skip + 404-on-no-prefs case). User-facing toasts preserved where they already existed.
  - **React reconciliation**: 10+ `key={idx}` occurrences replaced with stable content-derived keys (`stat.label`, `step.label`, `item.label`, `service.name`, `h.action_id`, `record.timestamp-action_id`, `${step.action_id}-${step.target_node}-${i}`, `${node}-${sig}`, `${s.name}-${s.method}-${s.path}-${i}`, etc.) across `DashboardPage`, `ActivePropagationsPanel`, `CustomerExperiencePanel`.
  - **Perf**: `useMemo` applied to `Object.entries().flatMap()` permanent-fix list in `AggressiveHealingCard`, and to `filter().slice().map()` chain on `data.annotations` (twice) in `CustomerExperiencePanel` (`chartAnnotations`, `healingImpacts`).
  - **Verified**: lint clean across all touched files, dashboard smoke test confirms Overview + System Health (Ladder Synthesizer + Aggressive + CX cards) render correctly with no console errors beyond the now-visible WebSocket-upgrade-not-supported message in preview env.
  - **Rejected (false positives, documented for posterity)**: the linter-flagged "circular import" between `obs/trackers/core.py` ↔ `obs_server.py` and "dynamic import security risk" in `ladder_synthesizer.py` are the documented singleton-binding pattern (whitepaper §6.1.5b). The 4 `__import__("obs.engines.core", fromlist=[...])` calls take a hardcoded module name — no user input, no injection surface. The "18 undefined variable references" are the forward-declared `None` placeholders rebound at runtime by `wire_runtime()`.

- **Feb 2026 — Documentation: README.md + SRI_Whitepaper.md** (iter 30 cont.)
  - `README.md`: new "Ladder Synthesizer · Programs Writing Programs" feature block, `Project Structure` rewritten to show full `obs/{trackers,engines}/core.py` + `obs/engines/ladder_synthesizer.py` layout + a modularization summary table, 6 new endpoints added to the Healing API table, `Escalation Ladders` table re-titled "cold-start" with pointer to live synth.
  - `SRI_Whitepaper.md`: new §12.7 "Ladder Synthesizer — Programs Writing Programs (v4, iter 30)" — 8 sub-sections covering the static-ladder problem, gain matrix (Eq. 12.7.1–.5), synthesis operator (Eq. 12.7.6), atomic swap + versioning + Mongo persistence, scheduled + stagnation triggers, rollback guard (Eq. 12.7.7), operational surface, and the meta-programming framing. §13.1 retitled "cold-start" and links to §12.7. ToC updated. New §6.1.5b "In-process Modularization of obs_server.py (iter 27–30)" added with the singleton-binding pattern + phase-by-phase table.

- **Feb 2026 — Ladder Synthesizer · "Programs Writing Programs"** (iter 30)
  - New `obs/engines/ladder_synthesizer.py` (~360 lines). `LadderSynthesizer` builds a per-(node, action) gain matrix from `healing_engine.history` (mean & recency-weighted ΔSRI) + golden-signal-urgency affinity, ranks actions per node, and **atomically rewrites `healing_engine.escalation_ladder`** — the engine's primary action-selection program. Each rewrite is a new "version" persisted to MongoDB collection `synthesized_ladders` `{version, timestamp, reason, ladder, previous_ladder, diff, gain_matrix, sri_baseline}`.
  - **Background loop** `synthesis_loop()`: every 10 s checks for SRI stagnation (Δ<0.005 over 60 s and mean<0.85 → fire); also fires on a 120 s scheduled cadence. Loop also runs a **rollback guard**: ROLLBACK_WINDOW_S=60 after each swap, if SRI regresses by `> 0.02` vs the at-swap baseline, the previous ladder is auto-restored.
  - **On boot**, `load_persisted()` re-applies the latest synthesized ladder from Mongo, making the engine self-modifying across process restarts.
  - **New endpoints** (admin gating on writes): `GET /api/healing/ladder/{current,history,gain-matrix}`, `POST /api/healing/ladder/{synthesize,rollback,toggle}`.
  - **Frontend**: new `LadderSynthesizerCard` on the System Health tab — version pill, per-node synthesized ladder with gain-score chips (heat-colored by sign), `was: …` diff line on rewritten nodes, AUTO/SYNTH/ROLLBACK admin buttons. Verified live: synthesizer reached v3 within 30 s of boot, rewrote ladders on all 5 nodes, MongoDB persistence + rollback verified end-to-end.

- **Feb 2026 — obs_server.py Modularization Phase 3** (iter 29)
  - **Physically extracted 7 more classes** (2,416 lines):
    - To `obs/trackers/core.py`: `CustomerExperienceTracker`, `BusinessMetrics`, `AlertManager`
    - To `obs/engines/core.py` (new): `HealingEngine` (1,543 lines), `HealingSequenceOptimizer`, `AggressiveHealingMode`, `PermanentFunnelHealer`
  - **`obs_server.py` shrunk 4,911 → 2,539 lines (−2,372 / −48%)**. Cumulative across Phase 2+3: **5,623 → 2,539 (−55%)**.
  - **Mechanism (no class-body edits)**: each extracted module forward-declares singletons as `None`/`{}`; `obs_server.py._wire_extracted_modules()` runs after singleton instantiation and `setattr`'s the real instances into the extracted modules' globals dicts. Class methods resolve names via function-globals (i.e. extracted module namespace), so they find live singletons at call-time.
  - Forward declarations cover all singletons + `TOPOLOGY_SCHEMA`, `PERMANENT_FIX_REGISTRY`, `compute_sri_from_metrics`, `db`, `write_api`, `INFLUX_BUCKET`, `INFLUX_ORG`, `ws_manager`, and 4 threshold constants (`SRI_CRITICAL_THRESHOLD`, `SRI_WARNING_THRESHOLD`, `LATENCY_CRITICAL_THRESHOLD`, `ERROR_RATE_CRITICAL_THRESHOLD`).
  - Verified: all background loops running, every endpoint (/api/metrics/real, /api/healing, /api/healing/aggressive/status, /api/healing/permanent-fixes, /api/cx/metrics) responds correctly. Zero regressions.

- **Feb 2026 — obs_server.py Modularization Phase 2** (iter 28)
  - **Physically extracted 8 standalone tracker classes** to `obs/trackers/core.py` (772 lines): `MetricsAggregator`, `SRIInterpolator`, `ResilienceDebtAccumulator`, `CorrelationTracker`, `AutoPropagationDetector`, `SRIAttributionEngine`, `WebhookNotifier`, `HealingAction`.
  - `obs_server.py` shrunk **5,623 → 4,911 lines (−712 / −12.7%)**.
  - `obs/trackers/__init__.py` and `obs/engines/__init__.py` use **PEP 562 module-level `__getattr__`** to lazy-resolve names still living in `obs_server.py` (singletons + the 7 not-yet-extracted classes), breaking the circular import that would otherwise occur because `obs_server` imports from `obs.trackers.core` at line 85 (before singletons are instantiated).
  - `MetricsAggregator.get_node_metrics` references `PERMANENT_FIX_REGISTRY` via a late-import inside the method body — safe because the global is defined in `obs_server.py` at line 77, well before any method call.
  - Verified: 3 background loops running, all `/api/metrics/*`, `/api/healing/*`, `/api/healing/aggressive/status`, `/api/healing/permanent-fixes` endpoints respond correctly. No regressions.
  - Phase 3 (future) will extract the remaining 7 classes (HealingEngine 1,543 lines + AggressiveHealingMode, PermanentFunnelHealer, HealingSequenceOptimizer, CustomerExperienceTracker, BusinessMetrics, AlertManager) using a DI refactor of the singleton mesh.

- **Feb 2026 — obs_server.py modularization Phase 1** (iter 27)
  - New `/app/backend/obs/` package with `engines/`, `routes/`, `trackers/` subpackages. Each subpackage's `__init__.py` re-exports the relevant classes + module-level singletons from `obs_server.py` so callers can already write:
    - `from obs.trackers import MetricsAggregator, metrics_aggregator, business_metrics`
    - `from obs.engines import HealingEngine, AggressiveHealingMode, healing_engine, permanent_funnel_healer, TOPOLOGY_SCHEMA, PERMANENT_FIX_REGISTRY`
    - `from obs.routes import api_router, app`
  - **No physical class moves yet** — the cross-singleton dependency graph (HealingEngine ↔ metrics_aggregator ↔ TOPOLOGY_SCHEMA ↔ PERMANENT_FIX_REGISTRY ↔ attribution_engine, etc.) requires a dependency-injection refactor to break. Phase 1 ships the directory structure + import contracts with zero runtime risk; Phase 2 will physically extract bodies into `obs/trackers/core.py` and `obs/engines/core.py` with proper DI.
  - Verified: all imports resolve, service health unchanged, no regressions to `/api/metrics/real`, `/api/healing/aggressive/status`, `/api/healing/permanent-fixes`.

- **Feb 2026 — Permanent Funnel Healer + Self-Correcting Decay** (iter 25–26)
  - **iter 25** — `PermanentFunnelHealer` class + 30-s loop detects funnel stagnation, traces root cause via `attribution_engine.attribute_dip`, installs a per-node-per-signal stiffness multiplier `m ∈ [0, 0.85]` persisted in MongoDB. `MetricsAggregator.get_node_metrics` applies `latency × (1−0.6m)`, `errors × (1−0.7m)`, `saturation × (1−0.5m)` — permanently lowering dE/dt.
  - **iter 26 (Auto-Decay)** — When no stagnation is detected, every loop tick multipliers shrink by `decay_factor` (default 0.995 → ~50 min half-life; admin-tunable). Multipliers below `decay_floor=0.01` are dropped from memory **and** deleted from Mongo. Persistence is throttled (every ~10 ticks / on removal) to keep Mongo writes bounded.
  - **Verified full cycle**: install at 0.15 → decay over 6 ticks at factor 0.6 → 0.0116 → cross floor → removed from both in-memory registry AND `permanent_fixes` collection.
  - **API**: `GET /api/healing/permanent-fixes`, `POST /toggle` (admin, now accepts `decay_factor`), `DELETE /{node}/{signal}` (admin manual revert).
  - **Frontend**: "PERMANENT FUNNEL FIXES" section in `AggressiveHealingCard` shows live registry and rationale.

- **Feb 2026 — dE/dt scoring term + counterfactual reliability** (iter 24)
  - **5th score term**: `+ 0.10 · clip(phi_reduction_mean, -0.05, +0.05)` added to `AggressiveHealingMode.rank_actions`. Phi-reduction is observed by comparing `current_phi` 5 s after each proactive fire vs at fire-time. Tracked per-action and exposed in `/api/healing/aggressive/status.phi_reduction_per_action`.
  - **Counterfactual reliability**: `cumulative_proactive_sri_lift` accumulates positive `sri_delta` from aggressive fires; counterfactual reliability = `current_reliability − 0.25 × Σ lift` (0.25 = SRI's weight in the composite). Surfaced as `counterfactual.{current_reliability, counterfactual_reliability, reliability_saved}` in the status payload.
  - **Frontend**: `AggressiveHealingCard` grew a 4th tile ("Reliability Saved" with "vs counterfactual X%") and a new "Φ-Reduction per Action (debt-rate Δ)" panel. Live demo shows `+28.86%` reliability gain (60s), `+2.55%` saved vs counterfactual 92.1%, and `api_error_suppression ↓ 331.66` Φ-reduction.

- **Feb 2026 — Tier-3 dampening for `auto-dampen-wave`** (iter 23)
  - 3-line plumbing: `auto_dampen_wave` + `_simulate_with_cut` now accept `granularity='endpoint'`, using `TOPOLOGY_SCHEMA["endpoint_edges"]` for adjacency. API guard relaxed.
  - Tested: `POST /api/healing/auto-dampen-wave {source:"API.auth.login",granularity:"endpoint"}` returns `wave_arrested=true`, `cut_edge={API.auth.login → API.auth.register}`, `recommended_action=rate_limit @ API`, 7 critical arrivals. Tier-2 regression clean.

- **Feb 2026 — Aggressive / Reliability-aware Auto-Healing** (iter 22)
  - New `AggressiveHealingMode` engine + background loop (every 5 s) that fires *proactively* before SRI dips. Triggers on (a) `dE/dt > debt_rate_threshold`, (b) predicted SRI dip (velocity & acceleration both negative), (c) baseline drift (sri<0.985 & debt accumulating), or (d) preemptive pressure (any service pressure > 0.008).
  - **Multi-objective action scoring**: `score = 0.30·ΔSRI + 0.30·ΔApdex + 0.20·ΔAvail + 0.15·ΔConv − 0.05·cost`. ΔApdex/Avail/Conv derived from `golden_signals_before/after` in healing history (latency↘ → +Apdex; errors↘ → +Avail & +Conv). Untried actions get a small positive prior so they're not blocked solely by cost.
  - **New endpoints (obs, proxied via main_app)**: `GET /api/healing/aggressive/status`, `POST /api/healing/aggressive/toggle` (admin-only — `{enabled, debt_rate_threshold, min_lift_threshold}`).
  - **Frontend**: new `AggressiveHealingCard` on the System Health tab showing proactive fire count, 60-s reliability gain, debt threshold, and the last 10 proactive heals.
  - Self-tested: live demo shows 3 proactive fires firing within 25 s of traffic generation (`api_error_suppression@DB`, `cache_flush@DB`) on debt_rate trigger.

- **Feb 2026 — Tier-3 endpoint granularity + denser mesh** (iter 21)
  - Mesh now has **3 tiers**: 6 services → 46 components → 101 endpoints. Inter-edges 6→8, fine-edges 26→84, new endpoint-edges 139.
  - `GET /api/healing/topology/schema` returns `version=2` and adds `endpoints`, `endpoint_edges`, and a `tier_counts` summary.
  - `GET /api/healing/fea?granularity=endpoint` decorates each component with `endpoints` and `endpoint_edges` arrays so the dashboard can render the full 3-tier mesh in one call.
  - `POST /api/healing/fault-propagation` accepts `granularity='endpoint'` and runs Laplacian diffusion on the 101-leaf graph (~200 ms).
  - `POST /api/healing/auto-dampen-wave` still tier-2 only; returns a clear "not yet supported for endpoint" 400 error.
  - Frontend `FEATopologyHeatMap`: double-click a service → ring of 6–9 component dots; double-click any component → inner ring of 1–4 endpoint dots with intra-component edges. MESH GRANULARITY tile reflects the current depth (`6 services` → `46 components` → `101 endpoints`).
  - Tested (iter 21): 14/14 backend pytest pass, frontend dashboard verified rendering all 3 tiers via Playwright.

- **Feb 2026 — Distributed microservice split** (iter 20)
  - `server.py` (5302 lines) split into `server.py` (~670 lines, e-commerce + proxy + event emission) and `obs_server.py` (~4780 lines, every observability engine + endpoint).
  - Supervisor program `backend_obs` added (`/etc/supervisor/conf.d/backend_obs.conf`) — uvicorn `obs_server:app` on port 8002.
  - Frontend untouched; `REACT_APP_BACKEND_URL` still points at the ingress on port 8001.
  - Tested: 44/44 backend pytest pass (`tests/test_iteration20_microservice_split.py`), 1 skipped (WSS through preview ingress — pre-existing limitation). Dashboard renders SRI=0.988, Apdex=0.96, Availability=98.97%, all charts live via proxy.

- iter 19 — Frontend as full SRI participant + browser RUM beacon (6 services in topology, `POST /api/rum/beacon`, rate-limited 1/s per session)
- iter 18 — Customer Experience panel + synthetic user journey
- iter 17 — Auto-propagation detector + path-based autonomous heal + sequence optimizer
- iter 16 — Strict-FEA terminology + SRI↔Conversion correlation + Auto-Dampener
- iter 15 — Fault propagation + non-recoverable detector + resilience-debt + cascade-risk
- iter 14 — Slack/Discord webhooks + topology schema endpoint
- iter 13 — Zoomable intra/inter-service FEA topology

## Backlog
- P1: Modularize `obs_server.py` into `engines/`, `routes/`, `trackers/` subpackages (file is still ~4780 lines — much improved from 5302 but can be split for clarity).
- P1: Stripe payment gateway for checkout.
- P2: Tooltip on Add-to-Cart tile clarifying derivation from page_load × 0.4.
- P2: Persist correlation + resilience-debt + CX samples + propagation history across restarts.
- P2: Sanitize obs-unreachable 502 detail before returning to clients (don't leak OBS_BASE).
- P2: Add shared-secret header on `/api/internal/events/*` (currently safe only because port 8002 isn't exposed).
- P2: Add explicit allow-list guard to the catch-all proxy in `server.py` so future e-commerce routes added after `include_router` aren't silently shadowed.
- P3: Document or auto-tune `critical_arrival_threshold` for source='Frontend' (sparse outgoing edges → fast diffusion attenuation).
- P3: Deduplicate component payload field names.
- Minor: `wss://.../ws/alerts` ingress rewrite (pre-existing — preview-env limitation).
- Minor: Fix Recharts ResponsiveContainer parent sizing (silences `width(-1) and height(-1)` warnings).
