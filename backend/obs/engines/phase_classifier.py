"""Operational Phase Classifier (iter 31) — implements the Operational
Phase-Transition Diagram for Distributed Software Systems.

For each service node, this module computes:
  * the **composite operational stress** σ = αL + βQ + γM + δE,
  * an **operational phase** ∈ {cold_start, warm_runtime, stable_throughput,
    jvm_saturation, retry_amplification, healing_saturation, cascading_collapse},
  * the **eutectic distance** ‖x − Ψ_c‖ in normalised (L, Q, M, E) space.

It also exposes two cross-system detectors that gate downstream engines:

  * `is_retry_amplifying()`   — traffic↑ ∧ errors↑ ∧ latency↑ over a 30-s window
                                (positive-feedback retry storm). When this fires,
                                `AggressiveHealingMode.rank_actions()` returns an
                                empty list so the engine refuses to add load.
  * `is_healing_saturated()`  — heal_rate_per_min / mean_ΔSRI_per_heal exceeds a
                                threshold; healing itself is generating stress.
                                When this fires, the ladder synthesizer applies
                                a cost-penalty boost so cheap actions are
                                preferred over heavyweight ones.

No new persistence and no new instrumentation: stress and phase are recomputed
from the live `MetricsAggregator` golden signals on every 5-s tick. M (memory
saturation) is proxied from the existing `saturation` channel; Q (queue depth)
from `Queue.saturation` × current traffic.
"""
from __future__ import annotations

import logging
import math
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
#  Tunable constants  (env overrides keep production tunable
#  without code edits)
# ============================================================

# Stress coefficients — must sum to 1.0
ALPHA_L  = float(os.environ.get("PHASE_ALPHA_L",  "0.30"))  # latency weight
BETA_Q   = float(os.environ.get("PHASE_BETA_Q",   "0.20"))  # queue weight
GAMMA_M  = float(os.environ.get("PHASE_GAMMA_M",  "0.25"))  # memory weight
DELTA_E  = float(os.environ.get("PHASE_DELTA_E",  "0.25"))  # error weight

# Baselines used to normalise raw signals into [0, 1]
LATENCY_BASELINE_MS    = float(os.environ.get("PHASE_L0",     "50.0"))   # L_0
LATENCY_CEILING_MS     = float(os.environ.get("PHASE_L_CEIL", "1500.0")) # L/L_0 max
MEM_CAP_THRESHOLD      = float(os.environ.get("PHASE_M_CAP",  "0.80"))   # M/M_cap GC stall

# Phase boundaries (M/M_cap, L/L_0 ratios)
PHASE_BOUNDS = {
    "cold_start":          {"m_max": 0.20, "l_max": 0.40, "min_traffic": 0,    "rule": "low_traffic"},
    "warm_runtime":        {"m_max": 0.40, "l_max": 0.80, "min_traffic": 5,    "rule": "moderate"},
    "stable_throughput":   {"m_max": 0.60, "l_max": 1.50, "min_traffic": 20,   "rule": "healthy_load"},
    "jvm_saturation":      {"m_max": 0.85, "l_max": 4.00, "min_traffic": 0,    "rule": "memory_pressure"},
    "retry_amplification": {"m_max": 0.95, "l_max": 12.0, "min_traffic": 0,    "rule": "positive_feedback"},
    "healing_saturation":  {"m_max": 0.95, "l_max": 20.0, "min_traffic": 0,    "rule": "heal_overhead"},
    "cascading_collapse":  {"m_max": 99.0, "l_max": 999.0, "min_traffic": 0,   "rule": "overflow"},
}

# Stable Point Ψ_s (ideal operating coordinates in normalised space)
#
# NOTE on nomenclature (iter 44 audit): in metallurgy a "eutectic point"
# is a topological triple-point where multiple phases meet at a single
# (composition, temperature) coordinate. The point below, at
# (M/M_cap=0.55, L/L₀=1.5), only touches the L boundary of the
# `stable_throughput` phase — it is NOT a true multi-phase meeting
# point. We therefore call it a **Stable Operating Point Ψ_s** in
# user-facing surfaces and docs. The variable name `EUTECTIC_POINT`
# is preserved for backward compatibility with the iter 37/41/42
# wiring that references it across ~12 files; `STABLE_POINT` below
# is the canonical alias.
#
# L_ratio is L̂ = L/L_ceil (normalised to the ceiling defined above), NOT L/L₀.
# L̂=0.05 ⇒ L≈75 ms ⇒ L/L₀≈1.5 — comfortable headroom over baseline.
EUTECTIC_POINT = {
    "L_ratio":      0.05,  # L̂ = L/L_ceil — comfortable headroom over baseline
    "Q_norm":       0.30,  # normalised queue depth
    "M_ratio":      0.55,  # M/M_cap — below GC-stall danger zone
    "E_norm":       0.02,  # 2 % error rate
}
# Canonical alias — the same coordinates, named honestly. Use this in
# new code and any user-facing label.
STABLE_POINT = EUTECTIC_POINT

# Retry-amplification detector
RETRY_WINDOW_S        = 30
RETRY_TRAFFIC_SURGE   = 1.6   # current traffic ≥ 1.6× window mean
RETRY_ERROR_RISING    = 0.15  # error rate growing > 15 % over window
RETRY_LATENCY_RISING  = 1.4   # latency growing 1.4× over window

# Healing-saturation detector
HEAL_SAT_WINDOW_S     = 60
HEAL_SAT_MIN_HEALS    = 5     # need ≥ 5 heals in the window before evaluating
HEAL_SAT_RATIO        = 25.0  # heals/min ÷ mean_ΔSRI > 25 → saturated

# History caps
HISTORY_SIZE          = 200

NODES = ["Frontend", "API", "Cache", "DB", "Queue", "Backend"]


# ============================================================
#  Data structures
# ============================================================

@dataclass
class PhaseSample:
    """A single per-node observation."""
    node: str
    timestamp: float
    traffic: float
    latency: float
    error: float
    saturation: float
    sigma: float
    l_ratio: float
    m_ratio: float
    phase: str
    eutectic_distance: float


@dataclass
class SystemPhaseSnapshot:
    """Cross-system view computed once per tick."""
    timestamp: float
    composite_sigma: float
    worst_node: str
    worst_phase: str
    per_node: Dict[str, PhaseSample] = field(default_factory=dict)
    retry_amplification: bool = False
    healing_saturation: bool = False
    eutectic_distance: float = 0.0  # mean across nodes
    flags: Dict[str, Any] = field(default_factory=dict)


# ============================================================
#  Forward-declared singletons — bound by wire_runtime
# ============================================================

metrics_aggregator = None
healing_engine = None
compute_sri_from_metrics = None


# ============================================================
#  Classifier
# ============================================================

class PhaseClassifier:
    """Stateless-ish classifier (small ring buffers for trend detection)."""

    def __init__(self):
        self.lock = Lock()
        # rolling history per node for retry-amplification detection
        self._node_samples: Dict[str, deque] = {n: deque(maxlen=60) for n in NODES}
        # rolling heal events (timestamp, sri_delta) for healing-saturation detection
        self._heal_events: deque = deque(maxlen=200)
        self._heal_history_len_seen = 0
        # snapshots
        self.latest: Optional[SystemPhaseSnapshot] = None
        self.history: deque = deque(maxlen=HISTORY_SIZE)
        # phase-aware policy state (exposed to other engines)
        self.aggressive_braked = False
        self.synth_cost_penalty_boost = 1.0
        # weights snapshot for /api/phase/state
        self.weights = {"alpha_L": ALPHA_L, "beta_Q": BETA_Q,
                        "gamma_M": GAMMA_M, "delta_E": DELTA_E}

    # -------------------- stress + classification --------------------

    def _normalise(self, m: Dict[str, float], q_proxy: float) -> Tuple[float, float, float, float, float, float]:
        """Return (L_norm, Q_norm, M_ratio, E_norm, l_ratio, sigma)."""
        L = float(m.get("latency", 0.0))
        E = float(m.get("error", 0.0))
        M_ratio = max(0.0, min(1.0, float(m.get("saturation", 0.0))))  # already 0-1

        # L/L_0 ratio (clamped) — visualisation axis
        l_ratio = max(0.0, L / LATENCY_BASELINE_MS) if LATENCY_BASELINE_MS > 0 else 0.0
        # normalised to [0, 1] for σ
        L_norm = min(1.0, l_ratio / (LATENCY_CEILING_MS / LATENCY_BASELINE_MS))
        Q_norm = max(0.0, min(1.0, q_proxy))
        E_norm = max(0.0, min(1.0, E / 0.20))  # 20 % is saturated

        sigma = (ALPHA_L * L_norm + BETA_Q * Q_norm
                 + GAMMA_M * M_ratio + DELTA_E * E_norm)
        return L_norm, Q_norm, M_ratio, E_norm, l_ratio, round(sigma, 4)

    def _classify(self, m: Dict[str, float], l_ratio: float, m_ratio: float,
                  sigma: float, retry_amp: bool, heal_sat: bool) -> str:
        traffic = float(m.get("traffic", 0.0))
        # explicit detectors take precedence
        if heal_sat:
            return "healing_saturation"
        if retry_amp:
            return "retry_amplification"
        # cascading collapse: extreme stress on multiple signals
        if sigma > 0.85 and (m_ratio > 0.95 or l_ratio > 20):
            return "cascading_collapse"
        # ladder: tightest bounds first
        if traffic < 1 and m_ratio < 0.25 and l_ratio < 0.5:
            return "cold_start"
        if m_ratio > MEM_CAP_THRESHOLD or l_ratio > 4.0:
            return "jvm_saturation"
        if m_ratio < 0.40 and l_ratio < 0.80:
            return "warm_runtime"
        # default operating band
        return "stable_throughput"

    def _eutectic_distance(self, l_ratio: float, q_norm: float,
                           m_ratio: float, e_norm: float) -> float:
        """L2 distance from Ψ_c in normalised 4D space (each axis in [0, ~2])."""
        # normalise l_ratio onto [0,1] using ceiling so axes are comparable
        l_n = min(1.0, l_ratio / (LATENCY_CEILING_MS / LATENCY_BASELINE_MS))
        d = math.sqrt(
            (l_n      - EUTECTIC_POINT["L_ratio"]) ** 2 +
            (q_norm   - EUTECTIC_POINT["Q_norm"])  ** 2 +
            (m_ratio  - EUTECTIC_POINT["M_ratio"]) ** 2 +
            (e_norm   - EUTECTIC_POINT["E_norm"])  ** 2
        )
        # normalise to [0, 1] (max possible distance in unit hypercube = 2)
        return round(min(1.0, d / 2.0), 4)

    # -------------------- detectors --------------------

    def _detect_retry_amplification(self, node: str, m: Dict[str, float]) -> bool:
        """Window check: traffic, errors, latency all rising simultaneously."""
        now = time.time()
        hist = self._node_samples[node]
        window = [s for s in hist if now - s["t"] <= RETRY_WINDOW_S]
        if len(window) < 6:
            return False
        recent = window[-3:]
        baseline = window[:-3]
        if not baseline:
            return False

        cur_traffic = statistics.fmean(s["traffic"] for s in recent)
        base_traffic = statistics.fmean(s["traffic"] for s in baseline) or 1e-6
        cur_errors = statistics.fmean(s["error"] for s in recent)
        base_errors = statistics.fmean(s["error"] for s in baseline) or 1e-6
        cur_lat = statistics.fmean(s["latency"] for s in recent)
        base_lat = statistics.fmean(s["latency"] for s in baseline) or 1e-6

        traffic_surge = cur_traffic > RETRY_TRAFFIC_SURGE * base_traffic
        errors_rising = cur_errors > base_errors * (1 + RETRY_ERROR_RISING) and cur_errors > 0.05
        latency_rising = cur_lat > RETRY_LATENCY_RISING * base_lat and cur_lat > 100
        return bool(traffic_surge and errors_rising and latency_rising)

    def _detect_healing_saturation(self) -> Tuple[bool, Dict[str, Any]]:
        """heals/min ÷ mean_ΔSRI > HEAL_SAT_RATIO → healing itself is adding stress."""
        if healing_engine is None:
            return False, {"reason": "no_engine"}
        # poll the engine for new history items
        hist = list(getattr(healing_engine, "history", []) or [])
        now = time.time()
        # parse each record's timestamp (ISO) lazily
        recent_window = []
        for rec in hist[-60:]:
            ts_str = rec.get("timestamp")
            if not ts_str:
                continue
            try:
                # cheap parse: rely on isoformat. If parse fails, fall back to "now"
                # so we don't crash; the resulting bias is negligible.
                from datetime import datetime
                t = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if now - t <= HEAL_SAT_WINDOW_S:
                d = rec.get("sri_delta")
                if d is not None:
                    try:
                        recent_window.append((t, float(d)))
                    except (TypeError, ValueError):
                        pass

        if len(recent_window) < HEAL_SAT_MIN_HEALS:
            return False, {"recent_heals": len(recent_window)}

        heals_per_min = 60.0 * len(recent_window) / HEAL_SAT_WINDOW_S
        mean_abs_delta = statistics.fmean(abs(d) for _, d in recent_window) or 1e-6
        ratio = heals_per_min / mean_abs_delta

        saturated = ratio > HEAL_SAT_RATIO
        return saturated, {
            "heals_per_min": round(heals_per_min, 2),
            "mean_abs_sri_delta": round(mean_abs_delta, 5),
            "ratio": round(ratio, 2),
            "threshold": HEAL_SAT_RATIO,
        }

    # -------------------- tick (called by background loop) --------------------

    def tick(self) -> Optional[SystemPhaseSnapshot]:
        if metrics_aggregator is None:
            return None
        node_metrics = metrics_aggregator.get_all_metrics()
        now = time.time()

        # 1) global healing-saturation flag (cheap, computed once)
        heal_sat, heal_sat_info = self._detect_healing_saturation()

        per_node: Dict[str, PhaseSample] = {}
        worst_sigma = -1.0
        worst_node = "API"
        worst_phase = "stable_throughput"
        composite_sigma_acc = 0.0
        eutectic_acc = 0.0
        composite_count = 0

        # queue-depth proxy: use Queue node's saturation × overall traffic
        queue_m = node_metrics.get("Queue", {})
        q_proxy_global = float(queue_m.get("saturation", 0.0))

        # 2) per-node sampling / classification
        for node in NODES:
            m = node_metrics.get(node) or {}
            # update ring buffer (used by detector)
            self._node_samples[node].append({
                "t": now,
                "traffic": float(m.get("traffic", 0.0)),
                "latency": float(m.get("latency", 0.0)),
                "error":   float(m.get("error", 0.0)),
                "saturation": float(m.get("saturation", 0.0)),
            })
            retry_amp_node = self._detect_retry_amplification(node, m)
            L_norm, Q_norm, M_ratio, E_norm, l_ratio, sigma = self._normalise(m, q_proxy_global)
            phase = self._classify(m, l_ratio, M_ratio, sigma,
                                   retry_amp=retry_amp_node, heal_sat=heal_sat)
            eut = self._eutectic_distance(l_ratio, Q_norm, M_ratio, E_norm)
            per_node[node] = PhaseSample(
                node=node, timestamp=now,
                traffic=float(m.get("traffic", 0.0)),
                latency=float(m.get("latency", 0.0)),
                error=float(m.get("error", 0.0)),
                saturation=float(m.get("saturation", 0.0)),
                sigma=sigma, l_ratio=round(l_ratio, 3), m_ratio=round(M_ratio, 3),
                phase=phase, eutectic_distance=eut,
            )
            composite_sigma_acc += sigma
            eutectic_acc += eut
            composite_count += 1
            if sigma > worst_sigma:
                worst_sigma = sigma
                worst_node = node
                worst_phase = phase

        # 3) cross-system retry-amplification: ANY node in retry_amp triggers it
        retry_amp_global = any(p.phase == "retry_amplification" for p in per_node.values())

        composite_sigma = (composite_sigma_acc / max(composite_count, 1)) if composite_count else 0.0
        eutectic_mean = (eutectic_acc / max(composite_count, 1)) if composite_count else 0.0

        snapshot = SystemPhaseSnapshot(
            timestamp=now,
            composite_sigma=round(composite_sigma, 4),
            worst_node=worst_node,
            worst_phase=worst_phase,
            per_node=per_node,
            retry_amplification=retry_amp_global,
            healing_saturation=heal_sat,
            eutectic_distance=round(eutectic_mean, 4),
            flags={
                "heal_sat_info": heal_sat_info,
                "weights": dict(self.weights),
                "eutectic_target": dict(EUTECTIC_POINT),
                "m_cap_threshold": MEM_CAP_THRESHOLD,
                "latency_baseline_ms": LATENCY_BASELINE_MS,
                "latency_ceiling_ms": LATENCY_CEILING_MS,
                "eutectic_l_over_l0": round(EUTECTIC_POINT["L_ratio"] * (LATENCY_CEILING_MS / LATENCY_BASELINE_MS), 3),
            },
        )

        with self.lock:
            self.latest = snapshot
            self.history.append(snapshot)
            # policy outputs consumed by other engines
            self.aggressive_braked = retry_amp_global
            # healing saturation → boost cost penalty 2× so synthesizer favors
            # cheaper actions for the next synthesis pass
            self.synth_cost_penalty_boost = 2.0 if heal_sat else 1.0

        return snapshot

    # -------------------- read API --------------------

    def status(self) -> Dict[str, Any]:
        snap = self.latest
        if snap is None:
            return {"ready": False}
        return {
            "ready": True,
            "timestamp": snap.timestamp,
            "composite_sigma": snap.composite_sigma,
            "worst_node": snap.worst_node,
            "worst_phase": snap.worst_phase,
            "retry_amplification": snap.retry_amplification,
            "healing_saturation": snap.healing_saturation,
            "eutectic_distance": snap.eutectic_distance,
            "aggressive_braked": self.aggressive_braked,
            "synth_cost_penalty_boost": self.synth_cost_penalty_boost,
            "per_node": {
                n: {
                    "phase": p.phase,
                    "sigma": p.sigma,
                    "l_ratio": p.l_ratio,
                    "m_ratio": p.m_ratio,
                    "eutectic_distance": p.eutectic_distance,
                    "traffic": p.traffic,
                    "latency": p.latency,
                    "error": p.error,
                    "saturation": p.saturation,
                } for n, p in snap.per_node.items()
            },
            "flags": snap.flags,
        }

    def history_snapshot(self, limit: int = 60) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.history)[-limit:]
        return [
            {
                "timestamp": s.timestamp,
                "composite_sigma": s.composite_sigma,
                "worst_node": s.worst_node,
                "worst_phase": s.worst_phase,
                "retry_amplification": s.retry_amplification,
                "healing_saturation": s.healing_saturation,
                "eutectic_distance": s.eutectic_distance,
                "per_node": {
                    n: {"phase": p.phase, "sigma": p.sigma,
                        "l_ratio": p.l_ratio, "m_ratio": p.m_ratio}
                    for n, p in s.per_node.items()
                },
            }
            for s in items
        ]


# Module-level singleton, bound by obs_server._wire_extracted_modules()
classifier: Optional[PhaseClassifier] = None


# ============================================================
#  Background loop
# ============================================================

import asyncio  # noqa: E402

async def phase_classifier_loop():
    """Recompute phase state every 5 s."""
    logger.info("phase_classifier_loop started")
    await asyncio.sleep(20)  # let metrics warm up
    while True:
        try:
            if classifier is not None:
                classifier.tick()
        except Exception as e:
            logger.debug(f"phase_classifier_loop tick error: {e}")
        await asyncio.sleep(5)
