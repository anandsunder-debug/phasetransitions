"""Healing engines — Phase 3 physical extraction (iter 29).

Class bodies for the four heavyweight engines now physically live here:
  - HealingEngine               (~1543 lines)
  - HealingSequenceOptimizer    (~122 lines)
  - AggressiveHealingMode       (~131 lines)
  - PermanentFunnelHealer       (~187 lines)

Their methods reference singletons (`metrics_aggregator`, `business_metrics`,
`attribution_engine`, `resilience_debt`, `sri_interpolator`, …) that are
instantiated *in obs_server.py after this module is imported*. To break
that cycle without editing class bodies, this module forward-declares
them as `None`; obs_server.py calls `wire_runtime(this_module)` after
instantiation, which reassigns the names in this module's globals dict.

Class method bodies look up the names in their function-globals (i.e.
this module's namespace) at call time, so they see the real instances.

Re-exported via obs.engines.__init__ for ergonomic access.
"""
from __future__ import annotations

import os
import time
import asyncio
import json
import math
import random
import logging
import secrets
import statistics
import hashlib
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Dict, List, Optional, Tuple, Any, Set

import numpy as np
import httpx

# HealingAction is a data class extracted to obs.trackers.core in Phase 2;
# HealingEngine's __init__ needs it at instantiation time.
from obs.trackers.core import HealingAction

logger = logging.getLogger(__name__)

# === Forward declarations: bound at runtime by obs_server.wire_runtime() ===
# These mirror obs_server's module-level singletons / globals. References
# inside class bodies (e.g. `metrics_aggregator.foo()`) resolve through this
# module's globals dict; obs_server.py writes the real instances here after
# instantiating its singletons. Initial None values are placeholders and
# will be replaced before any class method is called at runtime.
metrics_aggregator = None
sri_interpolator = None
resilience_debt = None
correlation_tracker = None
auto_propagation_detector = None
cx_tracker = None
business_metrics = None
attribution_engine = None
alert_manager = None
webhook_notifier = None
healing_engine = None
sequence_optimizer = None
aggressive_healing = None
permanent_funnel_healer = None
TOPOLOGY_SCHEMA: dict = {}
PERMANENT_FIX_REGISTRY: dict = {}
compute_sri_from_metrics = None
db = None
write_api = None
INFLUX_BUCKET = None
INFLUX_ORG = None
ws_manager = None
# Phase classifier (iter 31) — bound at runtime by obs_server.wire_runtime
phase_classifier_instance = None
# Action stagnation guard (iter 34) — bound at runtime by obs_server.wire_runtime
action_stagnation_guard = None
# Numeric thresholds shared from obs_server.py
SRI_CRITICAL_THRESHOLD = 0.1
SRI_WARNING_THRESHOLD = 0.3
LATENCY_CRITICAL_THRESHOLD = 200
ERROR_RATE_CRITICAL_THRESHOLD = 0.1


class HealingEngine:
    def __init__(self):
        self.lock = Lock()
        self.enabled = True
        self.alert_driven = True
        self.history = []
        self.active_healers = {}
        self.actions = self._init_actions()
        self._healing_task = None
        self.last_sri = 0.85
        self.sri_dip_threshold = 0.02
        self.sri_high_watermark = 0.85
        self.alert_action_map = {
            "sri": ["circuit_breaker", "rate_limit"],
            "latency": ["cache_flush", "connection_pool_reset"],
            "error": ["circuit_breaker", "rate_limit"],
            "saturation": ["queue_drain", "rate_limit", "connection_pool_reset"]
        }

        # === ADAPTIVE ACTION SELECTOR ===
        self.action_effectiveness = defaultdict(lambda: [])
        self.effectiveness_window = 5
        self.stagnation_threshold = 0.001

        self.escalation_ladder = {
            "Frontend": ["scale_out_frontend"],
            "API":     ["rate_limit", "api_error_suppression", "circuit_breaker", "cache_flush"],
            "Cache":   ["cache_flush", "scale_out_cache_node", "connection_pool_reset", "rate_limit"],
            "Backend": ["circuit_breaker", "scale_out_backend", "rate_limit", "queue_drain", "connection_pool_reset"],
            "DB":      ["connection_pool_reset", "scale_out_db_read_replica", "cache_flush", "circuit_breaker"],
            "Queue":   ["queue_drain", "rate_limit", "connection_pool_reset"],
        }

        self.node_neighbors = {
            "Frontend": ["API"],
            "API":     ["Frontend", "Cache", "DB", "Queue"],
            "Cache":   ["API", "DB"],
            "Backend": ["Queue"],
            "DB":      ["API", "Cache"],
            "Queue":   ["API", "Backend"],
        }

        self.node_primary_action = {
            "Frontend": "scale_out_frontend",
            "Cache": "cache_flush", "API": "rate_limit",
            "Backend": "circuit_breaker", "DB": "connection_pool_reset",
            "Queue": "queue_drain",
        }

        # === EMERGENT INTELLIGENCE: Golden-Signal-Derived Adaptive Weights ===
        # Weights are NOT hardcoded — they are DERIVED from live golden signals.
        # Each hop reinforces using multi-objective golden signal deltas.
        self.learned_affinity = {}
        self.learning_rate = 0.15
        self.total_hops = 0
        self._weights_initialized = False

        # Per-node learned signal importance (starts uniform, learns from golden signals)
        self.node_signal_importance = {
            node: {"latency": 0.33, "errors": 0.34, "saturation": 0.33}
            for node in ["Frontend", "API", "Cache", "DB", "Queue", "Backend"]
        }

        # Multi-objective weights: what we optimize for
        self.objective_weights = {
            "sri": 0.35,          # Infrastructure resilience
            "reliability": 0.35,  # Business reliability (Apdex + Availability + Conversion)
            "conversion": 0.30,   # Direct business outcome
        }

    def _derive_weights_from_golden_signals(self):
        """Derive action-signal affinity weights from LIVE golden signals.
        This is the core of 'adaptive by architecture' — weights come from
        observing which signals are degraded and which actions historically
        improved them. Called once on first hop and periodically recalibrated."""
        golden = metrics_aggregator.get_golden_signals()

        # Extract signal health scores (0=bad, 1=perfect)
        lat_health = golden.get("latency", {}).get("health", 0.5)
        err_health = golden.get("errors", {}).get("health", 0.5)
        sat_health = golden.get("saturation", {}).get("health", 0.5)

        # Inverse health = urgency (more degraded = higher urgency)
        lat_urgency = max(1 - lat_health, 0.05)
        err_urgency = max(1 - err_health, 0.05)
        sat_urgency = max(1 - sat_health, 0.05)
        total_urgency = lat_urgency + err_urgency + sat_urgency

        # Normalize urgencies to get signal priority weights
        sig_priority = {
            "latency": lat_urgency / total_urgency,
            "errors": err_urgency / total_urgency,
            "saturation": sat_urgency / total_urgency,
        }

        # Action-signal affinity: how well each action addresses each signal
        # This is derived from the action's EFFECT profile (what it actually reduces)
        action_effects = {
            "cache_flush":           {"latency": 0.6, "errors": 0.7, "saturation": 0.1},
            "rate_limit":            {"latency": 0.2, "errors": 0.5, "saturation": 0.5},
            "circuit_breaker":       {"latency": 0.5, "errors": 0.8, "saturation": 0.2},
            "connection_pool_reset": {"latency": 0.5, "errors": 0.3, "saturation": 0.4},
            "queue_drain":           {"latency": 0.5, "errors": 0.1, "saturation": 0.6},
            "api_error_suppression": {"latency": 0.3, "errors": 0.85, "saturation": 0.1},
        }

        # Combine: affinity = action_effect * signal_priority
        # Higher priority signal + higher effect = higher affinity weight
        for action_id, effects in action_effects.items():
            for signal in ["latency", "errors", "saturation"]:
                effect = effects[signal]
                priority = sig_priority[signal]
                # Weight = effect capability * how urgently this signal needs fixing
                weight = round(effect * (0.5 + priority), 4)
                weight = max(0.01, min(1.0, weight))
                # Only update if no learned value yet, or on recalibration
                key = (action_id, signal)
                if key not in self.learned_affinity:
                    self.learned_affinity[key] = weight

        self._weights_initialized = True
        return sig_priority

    @property
    def action_signal_affinity(self):
        """Dynamically computed from golden-signal-derived learned weights."""
        if not self._weights_initialized:
            self._derive_weights_from_golden_signals()
        result = {}
        all_actions = ["cache_flush", "rate_limit", "circuit_breaker",
                       "connection_pool_reset", "queue_drain", "api_error_suppression"]
        for action_id in all_actions:
            result[action_id] = {}
            for signal in ["latency", "errors", "saturation"]:
                result[action_id][signal] = round(
                    self.learned_affinity.get((action_id, signal), 0.1), 4)
        return result

    def _reinforce(self, action_id: str, signal: str, node: str, sri_delta: float):
        """Multi-objective reinforcement: adjust weights using golden signal deltas.
        Measures improvement across SRI, reliability, and conversion — not just SRI."""
        self.total_hops += 1

        # Recalibrate from golden signals every 10 hops (adaptive architecture)
        if self.total_hops % 10 == 0:
            self._derive_weights_from_golden_signals()

        key = (action_id, signal)
        old_w = self.learned_affinity.get(key, 0.5)

        # Multi-objective reward: combine SRI delta with golden signal improvements
        golden = metrics_aggregator.get_golden_signals()
        cx = metrics_aggregator.get_customer_experience()
        funnel = business_metrics.get_funnel()

        # Signal-specific reward: did THIS signal improve?
        signal_health = {
            "latency": golden.get("latency", {}).get("health", 0.5),
            "errors": golden.get("errors", {}).get("health", 0.5),
            "saturation": golden.get("saturation", {}).get("health", 0.5),
        }
        target_signal_health = signal_health.get(signal, 0.5)

        # Multi-objective composite reward
        sri_reward = sri_delta * 10  # Amplify small deltas
        reliability_reward = (cx.get("apdex", 0) - 0.5) * 0.5  # Positive when apdex > 0.5
        conversion_reward = funnel.get("modeled_conversion", {}).get("effective_conversion_rate", 0) * 5

        composite_reward = (
            self.objective_weights["sri"] * sri_reward +
            self.objective_weights["reliability"] * reliability_reward +
            self.objective_weights["conversion"] * conversion_reward
        )

        # Normalize reward to [-0.3, 0.3] range
        reward = max(-0.3, min(0.3, composite_reward))

        # Apply if the action had no effect, still penalize slightly
        if abs(sri_delta) < 0.001 and target_signal_health > 0.8:
            reward = -0.01  # Tiny penalty: signal is healthy, action was unnecessary
        elif abs(sri_delta) < 0.001:
            reward = -0.03  # Moderate penalty: signal is degraded but action didn't help

        new_w = old_w + self.learning_rate * reward
        new_w = max(0.01, min(1.0, new_w))
        self.learned_affinity[key] = round(new_w, 4)

        # Update per-node signal importance from golden signals
        if node in self.node_signal_importance:
            imp = self.node_signal_importance[node]
            # Weight shift toward whichever signal is most degraded on this node
            for s in ["latency", "errors", "saturation"]:
                health = signal_health.get(s, 0.5)
                # More degraded (lower health) = more important
                imp[s] = imp[s] * 0.9 + (1 - health) * 0.1
            # Normalize
            total = sum(imp.values()) or 1
            for s in imp:
                imp[s] = round(imp[s] / total, 4)

    def get_intelligence_state(self) -> Dict:
        """Export the current state of the emergent intelligence."""
        golden = metrics_aggregator.get_golden_signals()
        sig_priority = {
            "latency": round(1 - golden.get("latency", {}).get("health", 0.5), 4),
            "errors": round(1 - golden.get("errors", {}).get("health", 0.5), 4),
            "saturation": round(1 - golden.get("saturation", {}).get("health", 0.5), 4),
        }

        return {
            "total_hops": self.total_hops,
            "learning_rate": self.learning_rate,
            "objective_weights": self.objective_weights,
            "golden_signal_urgency": sig_priority,
            "current_affinities": self.action_signal_affinity,
            "node_signal_importance": dict(self.node_signal_importance),
            "weights_source": "golden_signals_derived",
            "recalibration_interval": "every 10 hops",
        }

    def _init_actions(self) -> Dict[str, HealingAction]:
        return {
            "cache_flush": HealingAction(
                "cache_flush", "Cache Flush", "Cache",
                "Purge stale cache entries to reduce cache latency and errors",
                "Cache latency > 60ms OR Cache error rate > 3%",
                "Reduces Cache node latency by ~40%, clears stale data",
                sri_impact=0.08, cooldown=45
            ),
            "rate_limit": HealingAction(
                "rate_limit", "Rate Limiter", "API",
                "Activate adaptive rate limiting to reduce API overload",
                "API saturation > 60% OR API error rate > 7%",
                "Reduces API saturation by ~30%, prevents cascading failures",
                sri_impact=0.12, cooldown=30
            ),
            "circuit_breaker": HealingAction(
                "circuit_breaker", "Circuit Breaker", "Backend",
                "Open circuit breaker to isolate failing backend services",
                "Backend error rate > 8% OR Backend latency > 150ms",
                "Isolates failing services, prevents error propagation across nodes",
                sri_impact=0.15, cooldown=60
            ),
            "connection_pool_reset": HealingAction(
                "connection_pool_reset", "Connection Pool Reset", "DB",
                "Reset and resize database connection pool",
                "DB saturation > 50% OR DB latency > 100ms",
                "Frees stale DB connections, reduces latency by ~35%",
                sri_impact=0.10, cooldown=90
            ),
            "queue_drain": HealingAction(
                "queue_drain", "Queue Drain", "Queue",
                "Drain backlogged queue messages and reset consumers",
                "Queue saturation > 60% OR Queue latency > 70ms",
                "Clears message backlog, restores processing throughput",
                sri_impact=0.07, cooldown=45
            ),
            "api_error_suppression": HealingAction(
                "api_error_suppression", "API Error Suppression", "API",
                "Suppress retry storms and error amplification on API layer",
                "API error rate > 5% AND rate_limit is exhausted",
                "Clears error backlog, resets failed request counters",
                sri_impact=0.10, cooldown=40
            ),
            # ===== SCALING ACTIONS (iter 33) =====
            # These add capacity rather than dampen demand — used when
            # the engine has run through cheaper actions and demand
            # genuinely exceeds the deployed footprint. Cost is high
            # (real infrastructure spin-up), cooldown is long (prevents
            # scaling thrashing). The synthesizer's cost-penalty term
            # (§12.8.5) naturally deprioritises these unless the gain
            # observation justifies the spend.
            "scale_out_frontend": HealingAction(
                "scale_out_frontend", "Scale Out Frontend", "Frontend",
                "Add a Frontend replica to absorb client-facing load",
                "Frontend latency > 200ms OR Frontend saturation > 70%",
                "Adds compute capacity; reduces Frontend latency ~45% and saturation ~60%",
                sri_impact=0.13, cooldown=180
            ),
            "scale_out_cache_node": HealingAction(
                "scale_out_cache_node", "Scale Out Cache Node", "Cache",
                "Add a Cache node and rebalance keyspace (sharding)",
                "Cache saturation > 70% OR Cache latency > 90ms",
                "Adds cache capacity; reduces Cache latency ~50% and saturation ~65%",
                sri_impact=0.11, cooldown=150
            ),
            "scale_out_db_read_replica": HealingAction(
                "scale_out_db_read_replica", "Scale Out DB Read Replica", "DB",
                "Provision an additional DB read replica and route reads through it",
                "DB latency > 120ms AND DB saturation > 65%",
                "Splits read load across replicas; reduces DB latency ~40% and saturation ~55%",
                sri_impact=0.14, cooldown=240
            ),
            "scale_out_backend": HealingAction(
                "scale_out_backend", "Scale Out Backend", "Backend",
                "Add a Backend worker replica to spread compute + IO load",
                "Backend saturation > 70% OR Backend latency > 150ms",
                "Adds compute capacity; reduces Backend latency ~40% and saturation ~55%",
                sri_impact=0.13, cooldown=200
            ),
            # ---- scale_in_* (iter 37) — eutectic-guided cost-saving actions ----
            # Fire only when (a) the node is currently boosted AND (b) the
            # projected post-action eutectic distance is *smaller* than
            # the current eutectic distance (i.e. removing capacity pulls
            # us TOWARD Ψ_c, not away). cooldown is short — these are
            # cheap reversible actions.
            "scale_in_frontend": HealingAction(
                "scale_in_frontend", "Scale In Frontend", "Frontend",
                "Drop a Frontend replica when over-provisioned (M/M_cap << 0.55)",
                "Frontend boosted AND saturation < 25% AND latency < 50ms — eutectic-pulled",
                "Returns capacity to the pool; M/M_cap and L/L₀ rise toward Ψ_c targets (0.55, 1.5)",
                sri_impact=-0.02, cooldown=120
            ),
            "scale_in_cache_node": HealingAction(
                "scale_in_cache_node", "Scale In Cache Node", "Cache",
                "Decommission a Cache node when over-provisioned",
                "Cache boosted AND saturation < 25% — eutectic-pulled",
                "Returns cache capacity; M/M_cap rises toward Ψ_c target 0.55",
                sri_impact=-0.02, cooldown=120
            ),
            "scale_in_db_read_replica": HealingAction(
                "scale_in_db_read_replica", "Scale In DB Read Replica", "DB",
                "Drop a DB read replica when over-provisioned",
                "DB boosted AND saturation < 25% AND latency < 50ms — eutectic-pulled",
                "Returns DB capacity; M/M_cap rises toward Ψ_c target 0.55",
                sri_impact=-0.02, cooldown=120
            ),
            "scale_in_backend": HealingAction(
                "scale_in_backend", "Scale In Backend", "Backend",
                "Drop a Backend replica when over-provisioned",
                "Backend boosted AND saturation < 25% AND latency < 50ms — eutectic-pulled",
                "Returns compute capacity; M/M_cap rises toward Ψ_c target 0.55",
                sri_impact=-0.02, cooldown=120
            ),
        }

    def _should_trigger(self, action_id: str, node_metrics: Dict) -> bool:
        """Check if a healing action should trigger based on component metrics.
        Uses lower thresholds to be proactive rather than reactive."""
        # Stagnation guard (iter 34): if this action's target node has the
        # action marked stagnant, suppress the trigger so the engine
        # progresses to the next action in the escalation walk.
        action_obj = self.actions.get(action_id)
        if action_obj is not None and action_stagnation_guard is not None:
            if action_stagnation_guard.is_blocked(action_obj.target_node, action_id):
                return False
        m = node_metrics
        if action_id == "cache_flush":
            cache = m.get("Cache", {})
            return cache.get("latency", 0) > 60 or cache.get("error", 0) > 0.03
        elif action_id == "rate_limit":
            api = m.get("API", {})
            return api.get("saturation", 0) > 0.6 or api.get("error", 0) > 0.07
        elif action_id == "circuit_breaker":
            backend = m.get("Backend", {})
            return backend.get("error", 0) > 0.08 or backend.get("latency", 0) > 150
        elif action_id == "connection_pool_reset":
            db_m = m.get("DB", {})
            return db_m.get("saturation", 0) > 0.5 or db_m.get("latency", 0) > 100
        elif action_id == "queue_drain":
            queue = m.get("Queue", {})
            return queue.get("saturation", 0) > 0.6 or queue.get("latency", 0) > 70
        elif action_id == "scale_out_frontend":
            fe = m.get("Frontend", {})
            base = fe.get("latency", 0) > 200 or fe.get("saturation", 0) > 0.70
            return base and self._scale_pulls_to_eutectic("Frontend", "scale_out_frontend")
        elif action_id == "scale_out_cache_node":
            cache = m.get("Cache", {})
            base = cache.get("saturation", 0) > 0.70 or cache.get("latency", 0) > 90
            return base and self._scale_pulls_to_eutectic("Cache", "scale_out_cache_node")
        elif action_id == "scale_out_db_read_replica":
            db_m = m.get("DB", {})
            base = db_m.get("latency", 0) > 120 and db_m.get("saturation", 0) > 0.65
            return base and self._scale_pulls_to_eutectic("DB", "scale_out_db_read_replica")
        elif action_id == "scale_out_backend":
            be = m.get("Backend", {})
            base = be.get("saturation", 0) > 0.70 or be.get("latency", 0) > 150
            return base and self._scale_pulls_to_eutectic("Backend", "scale_out_backend")
        elif action_id == "scale_in_frontend":
            fe = m.get("Frontend", {})
            base = fe.get("saturation", 0) < 0.25 and fe.get("latency", 0) < 50
            return base and self._scale_pulls_to_eutectic("Frontend", "scale_in_frontend")
        elif action_id == "scale_in_cache_node":
            cache = m.get("Cache", {})
            base = cache.get("saturation", 0) < 0.25
            return base and self._scale_pulls_to_eutectic("Cache", "scale_in_cache_node")
        elif action_id == "scale_in_db_read_replica":
            db_m = m.get("DB", {})
            base = db_m.get("saturation", 0) < 0.25 and db_m.get("latency", 0) < 50
            return base and self._scale_pulls_to_eutectic("DB", "scale_in_db_read_replica")
        elif action_id == "scale_in_backend":
            be = m.get("Backend", {})
            base = be.get("saturation", 0) < 0.25 and be.get("latency", 0) < 50
            return base and self._scale_pulls_to_eutectic("Backend", "scale_in_backend")
        return False

    # ---------------- iter 37: eutectic-guided scaling ----------------

    # multipliers mirror capacity_boost_config in _apply_healing_effect /
    # apply_capacity_drain — kept in one place for the simulator.
    _SCALE_BOOST_FACTORS = {
        "scale_out_frontend":         2.00,
        "scale_out_cache_node":       1.85,
        "scale_out_db_read_replica":  1.70,
        "scale_out_backend":          1.75,
        # scale_in_* DRAINS the boost (multiplicative factor < 1.0)
        "scale_in_frontend":          0.55,
        "scale_in_cache_node":        0.60,
        "scale_in_db_read_replica":   0.65,
        "scale_in_backend":           0.60,
    }

    def _scale_pulls_to_eutectic(self, node: str, action_id: str) -> bool:
        """Return True iff applying `action_id` to `node` would *reduce*
        the node's eutectic distance ‖x − Ψ_c‖. This is the core gate
        that makes every scaling decision provably pull toward Ψ_c —
        scale_out and scale_in are both filtered through the same rule.

        Uses the PhaseClassifier's normalised (L̂, Q, M, E) coordinates
        plus the simulator: scaling multiplies M_ratio and L̂ by
        boost/boost' (added capacity reduces both proportionally, M/M/c
        steady-state approximation). When PhaseClassifier hasn't yet
        produced a snapshot we fail open (return True) so cold-start
        behaviour matches the pre-iter-37 baseline.
        """
        if phase_classifier_instance is None:
            return True
        snap = getattr(phase_classifier_instance, "latest", None)
        if snap is None or node not in snap.per_node:
            return True
        try:
            from obs.engines.phase_classifier import (
                EUTECTIC_POINT, LATENCY_CEILING_MS, LATENCY_BASELINE_MS,
            )
        except Exception:
            return True
        p = snap.per_node[node]
        # Current normalised coordinates
        l_n_max = LATENCY_CEILING_MS / LATENCY_BASELINE_MS
        l_n  = min(1.0, p.l_ratio / l_n_max) if l_n_max > 0 else 0.0
        m    = max(0.0, min(1.0, p.m_ratio))
        # Q and E aren't published per-node on the snapshot; we use their
        # ψ_c-targeted values as a wash term (they don't move under
        # scaling). This keeps the simulator focussed on the axes scaling
        # actually moves.
        q    = EUTECTIC_POINT["Q_norm"]
        e    = EUTECTIC_POINT["E_norm"]
        # Current boost (from MetricsAggregator's live state)
        try:
            current_boost = metrics_aggregator.get_capacity_boost(node)
        except Exception:
            current_boost = 1.0
        factor = self._SCALE_BOOST_FACTORS.get(action_id, 1.0)
        if action_id.startswith("scale_out_"):
            new_boost = min(current_boost * factor, getattr(metrics_aggregator, "CAPACITY_BOOST_CEILING", 8.0))
        elif action_id.startswith("scale_in_"):
            if current_boost <= 1.0:
                return False  # can't scale in below baseline — already at floor
            new_boost = max(1.0, current_boost * factor)
        else:
            return True
        if new_boost == current_boost:
            return False
        # Project the new coordinates: M_ratio and L̂ both scale by
        # boost/boost'. Saturation = traffic/(100·boost), latency /= boost.
        scale = current_boost / new_boost
        new_l = l_n * scale
        new_m = m   * scale
        # L2 distance to Ψ_c — same metric the classifier uses
        def _dist(l, qq, mm, ee):
            return ((l  - EUTECTIC_POINT["L_ratio"]) ** 2
                  + (qq - EUTECTIC_POINT["Q_norm"])  ** 2
                  + (mm - EUTECTIC_POINT["M_ratio"]) ** 2
                  + (ee - EUTECTIC_POINT["E_norm"])  ** 2)
        cur_d = _dist(l_n,  q, m,     e)
        new_d = _dist(new_l, q, new_m, e)
        # Require a meaningful pull (≥ 1 % reduction in squared distance)
        # to avoid firing on numerical noise.
        return new_d < cur_d * 0.99

    # ---------------- iter 41: unified eutectic-distance objective ----------------

    # Generic effect map: per action, what (Δl_ratio_factor, Δerror_factor,
    # Δm_ratio_factor) does the action apply ON THE TARGET NODE?
    # Numbers in (0, 1] reduce the corresponding coordinate (multiplicative).
    # 1.0 = no effect. >1.0 = pushes up (only relevant in pathological cases).
    # Source: HealingEngine._apply_healing_effect's `effects` and
    # `dampener_config` — the multipliers reflect the steady-state pull
    # the action puts on its target node.
    _ACTION_AXIS_EFFECTS: Dict[str, Tuple[str, float, float, float]] = {
        # action_id: (target_node, l_factor, err_factor, m_factor)
        "cache_flush":            ("Cache",    0.40, 0.30, 1.00),
        "rate_limit":             ("API",      0.50, 0.50, 0.50),
        "circuit_breaker":        ("Backend",  0.50, 0.20, 1.00),
        "connection_pool_reset":  ("DB",       0.50, 1.00, 0.60),
        "queue_drain":            ("Queue",    0.50, 1.00, 0.40),
        "api_error_suppression":  ("API",      0.70, 0.15, 1.00),
        # scale_out actions — modeled via _SCALE_BOOST_FACTORS below; entry
        # here gives the residual non-boost effect (no further dampening).
        "scale_out_frontend":         ("Frontend", 1.00, 1.00, 1.00),
        "scale_out_cache_node":       ("Cache",    1.00, 1.00, 1.00),
        "scale_out_db_read_replica":  ("DB",       1.00, 1.00, 1.00),
        "scale_out_backend":          ("Backend",  1.00, 1.00, 1.00),
        # scale_in symmetric — boost-driven only
        "scale_in_frontend":          ("Frontend", 1.00, 1.00, 1.00),
        "scale_in_cache_node":        ("Cache",    1.00, 1.00, 1.00),
        "scale_in_db_read_replica":   ("DB",       1.00, 1.00, 1.00),
        "scale_in_backend":           ("Backend",  1.00, 1.00, 1.00),
    }

    def simulate_eutectic_delta(self, node: Optional[str], action_id: str) -> Dict[str, float]:
        """Return the simulated change in eutectic-distance² for applying
        `action_id` to `node` (or its default target if node is None).

        Output:
            {
              "cur_d2":   current squared distance,
              "new_d2":   projected squared distance,
              "delta_d2": new_d2 − cur_d2  (negative = pull toward Ψ_c),
              "target":   effective target node,
              "applicable": True/False (False if classifier not ready or no effect),
            }

        Used by AggressiveHealingMode.rank_actions as the DOMINANT scoring
        term so the unified objective becomes "minimize d(x, Ψ_c)²".
        """
        info = {"cur_d2": 0.0, "new_d2": 0.0, "delta_d2": 0.0, "target": node or "", "applicable": False}
        if phase_classifier_instance is None:
            return info
        snap = getattr(phase_classifier_instance, "latest", None)
        if snap is None:
            return info
        # Resolve target node
        eff = self._ACTION_AXIS_EFFECTS.get(action_id)
        if eff is None and node is None:
            return info
        target = node or (eff[0] if eff else None)
        if not target or target not in snap.per_node:
            return info
        try:
            from obs.engines.phase_classifier import (
                EUTECTIC_POINT, LATENCY_CEILING_MS, LATENCY_BASELINE_MS,
            )
        except Exception:
            return info
        info["target"] = target
        p = snap.per_node[target]
        # Current normalised coordinates
        l_n_max = LATENCY_CEILING_MS / LATENCY_BASELINE_MS
        l_n  = min(1.0, p.l_ratio / l_n_max) if l_n_max > 0 else 0.0
        m    = max(0.0, min(1.0, p.m_ratio))
        # Q is per-system normalised error-rate proxy; use the snapshot's
        # composite Q_norm if present, else fall back to Ψ_c's target.
        q    = float(getattr(snap, "Q_norm", EUTECTIC_POINT["Q_norm"]))
        e    = EUTECTIC_POINT["E_norm"]
        # Boost simulation (if scale_*) — reuses iter 37 math
        new_l = l_n
        new_m = m
        new_q = q
        # 1) Scale boost effect on (L̂, M)
        try:
            current_boost = metrics_aggregator.get_capacity_boost(target)
        except Exception:
            current_boost = 1.0
        factor = self._SCALE_BOOST_FACTORS.get(action_id)
        if factor is not None:
            if action_id.startswith("scale_out_"):
                new_boost = min(current_boost * factor,
                                getattr(metrics_aggregator, "CAPACITY_BOOST_CEILING", 8.0))
            else:  # scale_in_*
                if current_boost <= 1.0:
                    # can't drain below baseline — no effect at all
                    new_boost = current_boost
                else:
                    new_boost = max(1.0, current_boost * factor)
            if new_boost != current_boost:
                scale = current_boost / new_boost
                new_l = l_n * scale
                new_m = m   * scale
        # 2) Dampener effect on (L̂, Q) — dampeners attenuate latency and
        # errors; Q follows the error trajectory since it's the
        # normalised error-rate component of Ψ_c.
        if eff is not None:
            l_factor, err_factor, m_factor = eff[1], eff[2], eff[3]
            new_l *= l_factor
            new_m *= m_factor
            # Pull Q toward its Ψ_c target by (1 − err_factor):
            #   err_factor=0.15 ⇒ 85 % attenuation toward Ψ_c.Q
            target_q = EUTECTIC_POINT["Q_norm"]
            attenuation = 1.0 - err_factor
            new_q = q * (1.0 - attenuation) + target_q * attenuation
        new_l = max(0.0, min(1.0, new_l))
        new_m = max(0.0, min(1.0, new_m))
        new_q = max(0.0, min(1.0, new_q))
        # L2 squared distance to Ψ_c
        def _d2(l, qq, mm, ee):
            return ((l  - EUTECTIC_POINT["L_ratio"]) ** 2
                  + (qq - EUTECTIC_POINT["Q_norm"])  ** 2
                  + (mm - EUTECTIC_POINT["M_ratio"]) ** 2
                  + (ee - EUTECTIC_POINT["E_norm"])  ** 2)
        cur_d2 = _d2(l_n, q,     m,     e)
        new_d2 = _d2(new_l, new_q, new_m, e)
        info["cur_d2"]   = round(cur_d2, 6)
        info["new_d2"]   = round(new_d2, 6)
        info["delta_d2"] = round(new_d2 - cur_d2, 6)
        info["applicable"] = True
        # iter 45 — return projected (L̂, Q, M, boost) so multi-step
        # planners can chain forward without re-querying the classifier
        info["next_state"] = {
            "l_norm":   round(new_l, 6),
            "q_norm":   round(new_q, 6),
            "m_ratio":  round(new_m, 6),
            "boost":    round(locals().get("new_boost", current_boost), 4),
        }
        info["cost"] = float({
            "cache_flush": 0.10, "rate_limit": 0.15, "queue_drain": 0.20,
            "connection_pool_reset": 0.30, "circuit_breaker": 0.35,
            "api_error_suppression": 0.05,
            "scale_out_frontend": 0.50, "scale_out_cache_node": 0.40,
            "scale_out_db_read_replica": 0.60, "scale_out_backend": 0.50,
            "scale_in_frontend": 0.05, "scale_in_cache_node": 0.05,
            "scale_in_db_read_replica": 0.05, "scale_in_backend": 0.05,
        }.get(action_id, 0.20))
        return info

    # ---------------- iter 45: fastest-path-to-stable planner ----------------

    def plan_path_to_stable(
        self,
        node: str,
        max_steps: int = 5,
        target_d2: float = 0.001,
    ) -> Dict[str, Any]:
        """Greedy forward-simulation planner: returns the shortest sequence
        of healing actions that takes `node` from its current phase-space
        coordinates toward Ψ_s (stable operating point), minimising
        cumulative cost while monotonically decreasing d².

        Algorithm:
          1. Start from current (L̂, Q, M, boost) for the node.
          2. At each step, evaluate every action applicable to this node
             (or with no target i.e. system-wide); pick the one with the
             best `improvement_per_cost = (−Δd²) / cost`.
          3. Forward-project the state and repeat.
          4. Stop when d² ≤ target_d2, or no action improves further, or
             max_steps reached.

        Returns:
          {
            "node": str,
            "start_d2": float,
            "stable_target_d2": float (target_d2),
            "steps": [
              {"step": int, "action": str, "cost": float,
               "cur_d2": float, "next_d2": float, "delta_d2": float,
               "improvement_per_cost": float},
              ...
            ],
            "final_d2": float,
            "reached_target": bool,
            "total_cost": float,
            "total_actions": int,
          }
        """
        if phase_classifier_instance is None:
            return {"node": node, "applicable": False, "reason": "phase_classifier not ready"}
        snap = getattr(phase_classifier_instance, "latest", None)
        if snap is None or node not in snap.per_node:
            return {"node": node, "applicable": False, "reason": f"no per-node data for {node}"}
        try:
            from obs.engines.phase_classifier import (
                EUTECTIC_POINT, LATENCY_CEILING_MS, LATENCY_BASELINE_MS,
            )
        except Exception:
            return {"node": node, "applicable": False, "reason": "classifier import failed"}

        # Initial state
        l_n_max = LATENCY_CEILING_MS / LATENCY_BASELINE_MS
        p = snap.per_node[node]
        l_n  = min(1.0, p.l_ratio / l_n_max) if l_n_max > 0 else 0.0
        m    = max(0.0, min(1.0, p.m_ratio))
        q    = float(getattr(snap, "Q_norm", EUTECTIC_POINT["Q_norm"]))
        e    = EUTECTIC_POINT["E_norm"]
        try:
            boost = metrics_aggregator.get_capacity_boost(node)
        except Exception:
            boost = 1.0

        def d2(l_, q_, m_):
            # iter 45 — ONE-SIDED distance: Ψ_s is a CEILING of safe
            # operation, not a fixed target. Below it on any axis = stable
            # (no healing needed). Above it = debt-accumulating. Healing
            # actions only DECREASE stress, so the natural pull is from
            # above Ψ_s back down to the ceiling. This avoids the
            # degenerate "no path exists" result when the system is
            # already operating below the stable target.
            return (max(0.0, l_ - EUTECTIC_POINT["L_ratio"]) ** 2
                  + max(0.0, q_ - EUTECTIC_POINT["Q_norm"])  ** 2
                  + max(0.0, m_ - EUTECTIC_POINT["M_ratio"]) ** 2
                  + max(0.0, e  - EUTECTIC_POINT["E_norm"])  ** 2)

        # Candidate actions: those that target THIS node or are node-agnostic
        candidates = [
            aid for aid, eff in self._ACTION_AXIS_EFFECTS.items()
            if eff[0] == node or eff[0] == ""
        ]
        # If none target this node directly, include all actions and let
        # the simulator's resolve-to-default-target logic narrow it down.
        if not candidates:
            candidates = list(self._ACTION_AXIS_EFFECTS.keys())

        start_d2 = d2(l_n, q, m)
        cur_d2_local = start_d2
        steps: List[Dict[str, Any]] = []
        used_actions: set = set()  # avoid firing the same action twice in a single plan

        for step in range(1, max_steps + 1):
            if cur_d2_local <= target_d2:
                break
            best = None  # (improvement_per_cost, aid, projected state)
            for aid in candidates:
                if aid in used_actions:
                    continue
                # Simulate forward from CURRENT local state (not classifier!)
                eff = self._ACTION_AXIS_EFFECTS.get(aid)
                if eff is None:
                    continue
                new_l, new_m, new_q = l_n, m, q
                new_boost = boost
                # 1) scaling effect
                factor = self._SCALE_BOOST_FACTORS.get(aid)
                if factor is not None:
                    if aid.startswith("scale_out_"):
                        new_boost = min(boost * factor,
                                        getattr(metrics_aggregator, "CAPACITY_BOOST_CEILING", 8.0))
                    else:
                        new_boost = boost if boost <= 1.0 else max(1.0, boost * factor)
                    if new_boost != boost:
                        scale = boost / new_boost
                        new_l = l_n * scale
                        new_m = m   * scale
                # 2) dampener
                l_factor, err_factor, m_factor = eff[1], eff[2], eff[3]
                new_l *= l_factor
                new_m *= m_factor
                attenuation = 1.0 - err_factor
                new_q = new_q * (1.0 - attenuation) + EUTECTIC_POINT["Q_norm"] * attenuation
                new_l = max(0.0, min(1.0, new_l))
                new_m = max(0.0, min(1.0, new_m))
                new_q = max(0.0, min(1.0, new_q))
                next_d2 = d2(new_l, new_q, new_m)
                delta = next_d2 - cur_d2_local
                if delta >= 0:
                    continue  # action does not improve (or worsens)
                cost = self.aggressive_action_cost(aid)
                if cost <= 0:
                    continue
                ipc = -delta / cost  # improvement-per-cost (positive)
                if best is None or ipc > best[0]:
                    best = (ipc, aid, new_l, new_q, new_m, new_boost, next_d2, delta, cost)
            if best is None:
                break  # no action improves further
            ipc, aid, new_l, new_q, new_m, new_boost, next_d2, delta, cost = best
            steps.append({
                "step":   step,
                "action": aid,
                "cost":   round(cost, 4),
                "cur_d2": round(cur_d2_local, 6),
                "next_d2":round(next_d2, 6),
                "delta_d2": round(delta, 6),
                "improvement_per_cost": round(ipc, 4),
            })
            # commit forward state
            l_n, m, q, boost = new_l, new_m, new_q, new_boost
            cur_d2_local = next_d2
            used_actions.add(aid)

        return {
            "node": node,
            "start_d2": round(start_d2, 6),
            "stable_target_d2": target_d2,
            "steps": steps,
            "final_d2": round(cur_d2_local, 6),
            "reached_target": cur_d2_local <= target_d2,
            "total_cost": round(sum(s["cost"] for s in steps), 4),
            "total_actions": len(steps),
            "applicable": True,
        }

    @staticmethod
    def aggressive_action_cost(aid: str) -> float:
        """Single-place lookup for the action-cost table used by the
        planner. Mirrors AggressiveHealingMode.action_cost but kept
        static so the planner can call it without an instance dep."""
        return {
            "cache_flush": 0.10, "rate_limit": 0.15, "queue_drain": 0.20,
            "connection_pool_reset": 0.30, "circuit_breaker": 0.35,
            "api_error_suppression": 0.05,
            "scale_out_frontend": 0.50, "scale_out_cache_node": 0.40,
            "scale_out_db_read_replica": 0.60, "scale_out_backend": 0.50,
            "scale_in_frontend": 0.05, "scale_in_cache_node": 0.05,
            "scale_in_db_read_replica": 0.05, "scale_in_backend": 0.05,
        }.get(aid, 0.20)

    def _detect_sri_dip(self, current_sri: float) -> Dict:
        """Detect SRI dips by comparing against high watermark.
        Returns dip magnitude and whether healing should activate."""
        # Update high watermark (slowly rising)
        if current_sri > self.sri_high_watermark:
            self.sri_high_watermark = current_sri
        elif current_sri > self.sri_high_watermark - 0.01:
            # Decay watermark slightly so it tracks reality
            self.sri_high_watermark = self.sri_high_watermark * 0.995 + current_sri * 0.005

        dip = self.sri_high_watermark - current_sri
        velocity_drop = self.last_sri - current_sri  # per-cycle drop
        self.last_sri = current_sri

        return {
            "current_sri": round(current_sri, 4),
            "high_watermark": round(self.sri_high_watermark, 4),
            "dip_magnitude": round(dip, 4),
            "velocity_drop": round(velocity_drop, 6),
            "healing_needed": dip > self.sri_dip_threshold or current_sri < SRI_WARNING_THRESHOLD,
        }

    def _apply_healing_effect(self, action_id: str):
        """Apply corrective healing — both immediate reduction AND persistent dampener.
        The dampener ensures future requests to this node show improvement (faster SRI rise)."""
        effects = {
            "cache_flush": ("Cache", {"latency_reduction": 0.6, "error_reduction": 0.7}),
            "rate_limit": ("API", {"saturation_reduction": 0.5, "error_reduction": 0.5}),
            "circuit_breaker": ("Backend", {"error_reduction": 0.8, "latency_reduction": 0.5}),
            "connection_pool_reset": ("DB", {"latency_reduction": 0.5, "saturation_reduction": 0.4}),
            "queue_drain": ("Queue", {"saturation_reduction": 0.6, "latency_reduction": 0.5}),
            "api_error_suppression": ("API", {"error_reduction": 0.85, "latency_reduction": 0.3}),
            # Scaling actions add capacity → strong latency + saturation reduction.
            "scale_out_frontend": ("Frontend", {"latency_reduction": 0.45, "saturation_reduction": 0.60}),
            "scale_out_cache_node": ("Cache", {"latency_reduction": 0.50, "saturation_reduction": 0.65}),
            "scale_out_db_read_replica": ("DB", {"latency_reduction": 0.40, "saturation_reduction": 0.55}),
            "scale_out_backend": ("Backend", {"latency_reduction": 0.40, "saturation_reduction": 0.55}),
        }
        # Dampener config: (latency_factor, error_suppression, duration_seconds)
        # More aggressive for faster SRI improvement
        dampener_config = {
            "cache_flush": (0.3, 0.7, 25),
            "rate_limit": (0.5, 0.5, 20),
            "circuit_breaker": (0.4, 0.85, 30),
            "connection_pool_reset": (0.35, 0.4, 25),
            "queue_drain": (0.4, 0.6, 22),
            "api_error_suppression": (0.6, 0.9, 25),
            # Scaling persists much longer — added capacity stays online until
            # an explicit scale-in. Use 120 s "persistence" so the dampener
            # bias survives multiple healing cycles.
            "scale_out_frontend":         (0.55, 0.5, 120),
            "scale_out_cache_node":       (0.50, 0.5, 120),
            "scale_out_db_read_replica":  (0.60, 0.4, 120),
            "scale_out_backend":          (0.60, 0.5, 120),
        }
        # Capacity-boost config: (multiplier, duration_seconds) — only for
        # scale_out_* actions. Multipliers compound within the persistence
        # window (capped by MetricsAggregator.CAPACITY_BOOST_CEILING),
        # modelling each fire as "+1 replica" with diminishing returns.
        # This is the fix for the metallurgical-yielding state where
        # scale-out actions previously had zero effect on saturation
        # because the capacity denominator was hard-coded at 100 req/min.
        capacity_boost_config = {
            "scale_out_frontend":         (2.0, 120),
            "scale_out_cache_node":       (1.85, 120),
            "scale_out_db_read_replica":  (1.7, 120),
            "scale_out_backend":          (1.75, 120),
        }
        # iter 37: capacity-drain config for scale_in_* actions
        # (multiplicative factor in (0, 1)). Drains the active boost by
        # the factor; if the result drops below 1.05 the boost is removed
        # (node returns to baseline single-replica capacity).
        capacity_drain_config = {
            "scale_in_frontend":         (0.55, 120),
            "scale_in_cache_node":       (0.60, 120),
            "scale_in_db_read_replica":  (0.65, 120),
            "scale_in_backend":          (0.60, 120),
        }
        # scale_in_* don't appear in `effects` (they don't reduce
        # latency/errors on the immediate window) — handle them up front
        # and return early.
        drain = capacity_drain_config.get(action_id)
        if drain:
            scale_in_node = self.actions[action_id].target_node
            metrics_aggregator.apply_capacity_drain(scale_in_node, drain[0], drain[1])
            return
        node, reductions = effects.get(action_id, (None, {}))
        if node:
            # Immediate reduction on existing window data
            with metrics_aggregator.lock:
                data = metrics_aggregator.metrics[node]
                if "latency_reduction" in reductions and data["latencies"]:
                    factor = 1 - reductions["latency_reduction"]
                    data["latencies"] = [l * factor for l in data["latencies"]]
                if "error_reduction" in reductions and data["errors"]:
                    count_to_fix = int(len(data["errors"]) * reductions["error_reduction"])
                    for i in range(min(count_to_fix, len(data["errors"]))):
                        if data["errors"][i] == 1:
                            data["errors"][i] = 0
                if "saturation_reduction" in reductions and data["requests"]:
                    count_to_remove = int(len(data["requests"]) * reductions.get("saturation_reduction", 0))
                    if count_to_remove > 0:
                        for key in ["requests", "latencies", "errors", "timestamps"]:
                            data[key] = data[key][count_to_remove:]
            
            # Persistent dampener for future requests
            damp = dampener_config.get(action_id)
            if damp:
                metrics_aggregator.apply_dampener(node, damp[0], damp[1], damp[2])

            # Capacity boost for scale-out actions — this is the persistent
            # term that actually moves the saturation/latency denominator
            # (vs. the dampener which only attenuates errors+latency).
            cap = capacity_boost_config.get(action_id)
            if cap:
                metrics_aggregator.apply_capacity_boost(node, cap[0], cap[1])

    def execute_action(self, action_id: str, triggered_by: str = "manual", trigger_alert: dict = None, target_signal: str = None, target_node_override: str = None) -> dict:
        """Execute a healing action with golden signal tracking and correction factor"""
        with self.lock:
            action = self.actions.get(action_id)
            if not action:
                return {"success": False, "error": "Unknown action"}
            if not action.can_execute():
                remaining = action.cooldown - (datetime.now(timezone.utc) - action.last_executed).total_seconds()
                return {"success": False, "error": f"Cooldown active ({int(remaining)}s remaining)"}

            # Capture golden signals BEFORE healing
            golden_before = metrics_aggregator.get_golden_signals()
            node_metrics = metrics_aggregator.get_all_metrics()
            sri_before = compute_sri_from_metrics(node_metrics)["sri"]

            # Apply healing effect
            self._apply_healing_effect(action_id)

            # Capture golden signals AFTER healing
            golden_after = metrics_aggregator.get_golden_signals()
            node_metrics_after = metrics_aggregator.get_all_metrics()
            sri_after = compute_sri_from_metrics(node_metrics_after)["sri"]

            now = datetime.now(timezone.utc)
            action.last_executed = now
            action.execution_count += 1

            # Mark as active healer
            self.active_healers[action_id] = now + timedelta(seconds=action.cooldown)

            # Compute correction factors per golden signal
            correction_factors = {}
            for signal_key in ["latency", "traffic", "errors", "saturation"]:
                before_val = golden_before[signal_key]["health"]
                after_val = golden_after[signal_key]["health"]
                delta = after_val - before_val
                # Correction factor: how much this action improved the signal (0-1 scale)
                factor = delta / max(1 - before_val, 0.01) if before_val < 1 else 0
                correction_factors[signal_key] = {
                    "before": round(before_val, 4),
                    "after": round(after_val, 4),
                    "delta": round(delta, 4),
                    "correction_factor": round(min(max(factor, 0), 1), 4)
                }

            # Store correction in aggregator history
            metrics_aggregator.correction_history.append({
                "action_id": action_id,
                "corrections": correction_factors,
                "sri_before": round(sri_before, 4),
                "sri_after": round(sri_after, 4),
                "timestamp": now.isoformat()
            })
            if len(metrics_aggregator.correction_history) > 100:
                metrics_aggregator.correction_history = metrics_aggregator.correction_history[-100:]

            record = {
                "action_id": action_id,
                "action_name": action.name,
                "target_node": action.target_node,
                "triggered_by": triggered_by,
                "trigger_alert": trigger_alert.get("category") if trigger_alert else None,
                "sri_before": round(sri_before, 4),
                "sri_after": round(sri_after, 4),
                "sri_delta": round(sri_after - sri_before, 4),
                "golden_signals_before": {k: v["value"] for k, v in golden_before.items()},
                "golden_signals_after": {k: v["value"] for k, v in golden_after.items()},
                "correction_factors": correction_factors,
                "timestamp": now.isoformat(),
                "status": "success",
                "effect": action.effect_description
            }

            # === Track effectiveness for adaptive action selection ===
            sri_delta = sri_after - sri_before
            self.action_effectiveness[action_id].append(round(sri_delta, 6))
            if len(self.action_effectiveness[action_id]) > self.effectiveness_window * 2:
                self.action_effectiveness[action_id] = self.action_effectiveness[action_id][-self.effectiveness_window * 2:]

            # === Annotate the SRI ↔ conversion correlation chart ===
            try:
                correlation_tracker.annotate_healing(
                    action_id=action_id,
                    sri_before=sri_before,
                    sri_after=sri_after,
                    target_node=target_node_override or action.target_node,
                )
            except Exception as e:
                logger.debug(f"Correlation annotation error: {e}")

            is_exhausted = self._is_action_exhausted(action_id)
            record["effectiveness"] = {
                "sri_delta": round(sri_delta, 6),
                "recent_deltas": self.action_effectiveness[action_id][-self.effectiveness_window:],
                "is_exhausted": is_exhausted,
            }

            # === EMERGENT INTELLIGENCE: Reinforce learned weights ===
            eff_signal = target_signal or record.get("target_signal")
            eff_node = target_node_override or action.target_node
            if eff_signal:
                old_affinity = self.learned_affinity.get((action_id, eff_signal), 0.5)
                self._reinforce(action_id, eff_signal, eff_node, sri_delta)
                new_affinity = self.learned_affinity.get((action_id, eff_signal), 0.5)
                record["intelligence"] = {
                    "hop": self.total_hops,
                    "action": action_id,
                    "signal": eff_signal,
                    "node": eff_node,
                    "weight_before": round(old_affinity, 4),
                    "weight_after": round(new_affinity, 4),
                    "weight_delta": round(new_affinity - old_affinity, 4),
                    "sri_delta": round(sri_delta, 6),
                }

            self.history.append(record)
            if len(self.history) > 200:
                self.history = self.history[-200:]

            # Stagnation guard (iter 34): record outcome so the guard can
            # dynamically remove this (node, action) pair after N
            # consecutive zero-effect attempts.
            try:
                if action_stagnation_guard is not None:
                    action_stagnation_guard.record(
                        node=target_node_override or action.target_node,
                        action=action_id,
                        sri_delta=sri_delta,
                    )
            except Exception as e:
                logger.debug(f"stagnation_guard.record: {e}")

            return {"success": True, "record": record}

    def get_recommendations(self, node_metrics: Dict, current_sri: float) -> list:
        """Generate ranked healing recommendations based on current state"""
        recs = []
        for action_id, action in self.actions.items():
            if not self._should_trigger(action_id, node_metrics):
                continue

            target_node = action.target_node
            node_data = node_metrics.get(target_node, {})

            # Calculate urgency based on how bad the node metrics are
            urgency = 0
            if node_data.get("error", 0) > 0.1:
                urgency += 3
            elif node_data.get("error", 0) > 0.05:
                urgency += 1
            if node_data.get("latency", 0) > 150:
                urgency += 2
            elif node_data.get("latency", 0) > 80:
                urgency += 1
            if node_data.get("saturation", 0) > 0.8:
                urgency += 2
            elif node_data.get("saturation", 0) > 0.6:
                urgency += 1

            projected_sri = min(current_sri + action.sri_impact, 1.0)

            recs.append({
                "action_id": action_id,
                "action_name": action.name,
                "target_node": target_node,
                "description": action.description,
                "effect": action.effect_description,
                "urgency": urgency,
                "priority": "critical" if urgency >= 5 else "high" if urgency >= 3 else "medium",
                "current_sri": round(current_sri, 4),
                "projected_sri": round(projected_sri, 4),
                "sri_improvement": round(action.sri_impact, 4),
                "can_execute": action.can_execute(),
                "node_metrics": {
                    "latency": round(node_data.get("latency", 0), 1),
                    "error_rate": round(node_data.get("error", 0) * 100, 1),
                    "saturation": round(node_data.get("saturation", 0) * 100, 1),
                    "traffic": node_data.get("traffic", 0)
                }
            })

        recs.sort(key=lambda r: (-r["urgency"], -r["sri_improvement"]))
        return recs

    def _is_action_exhausted(self, action_id: str) -> bool:
        """An action is 'exhausted' if last N executions all produced ~0 SRI improvement.
        Resets if a positive delta is observed (action became effective again)."""
        recent = self.action_effectiveness.get(action_id, [])[-self.effectiveness_window:]
        if len(recent) < 3:
            return False
        # If the most recent execution was effective, clear exhaustion
        if recent and recent[-1] > self.stagnation_threshold:
            return False
        return all(abs(d) < self.stagnation_threshold for d in recent)

    def _select_adaptive_action(self, target_node: str, node_metrics: Dict) -> Optional[str]:
        """Adaptive action selector: walks the escalation ladder for a node,
        skipping exhausted actions. If all node actions exhausted, tries
        cross-node healing on neighbors."""

        # Phase 1: Walk this node's escalation ladder
        ladder = self.escalation_ladder.get(target_node, [])
        for action_id in ladder:
            action = self.actions.get(action_id)
            if not action:
                continue
            if not action.can_execute():
                continue
            if self._is_action_exhausted(action_id):
                continue
            return action_id

        # Phase 2: Cross-node healing — try neighbor nodes' escalation ladders
        neighbors = self.node_neighbors.get(target_node, [])
        for neighbor in neighbors:
            neighbor_ladder = self.escalation_ladder.get(neighbor, [])
            for action_id in neighbor_ladder:
                action = self.actions.get(action_id)
                if not action:
                    continue
                if not action.can_execute():
                    continue
                if self._is_action_exhausted(action_id):
                    continue
                return action_id

        return None

    def get_adaptation_status(self) -> Dict:
        """Return current state of the adaptive action selector."""
        exhausted = []
        effective = []
        for action_id in self.actions:
            recent = self.action_effectiveness.get(action_id, [])[-self.effectiveness_window:]
            is_exh = self._is_action_exhausted(action_id)
            avg_delta = round(sum(recent) / max(len(recent), 1), 6)
            entry = {
                "action_id": action_id,
                "recent_deltas": recent,
                "avg_sri_delta": avg_delta,
                "executions_tracked": len(self.action_effectiveness.get(action_id, [])),
                "is_exhausted": is_exh,
            }
            if is_exh:
                exhausted.append(entry)
            else:
                effective.append(entry)

        return {
            "exhausted_actions": exhausted,
            "effective_actions": effective,
            "total_exhausted": len(exhausted),
            "total_effective": len(effective),
            "stagnation_threshold": self.stagnation_threshold,
            "effectiveness_window": self.effectiveness_window,
        }

    async def auto_heal_cycle(self):
        """Emergent Intelligence: ALWAYS attempt to increase SRI.

        No gating — every cycle evaluates the topology, finds the weakest
        point, and applies the action with the highest LEARNED affinity
        for that point's dominant signal. Weights evolve after each hop.

        Strategy:
        1. Compute current SRI and topology state
        2. If SRI < 1.0 (always true), find what's holding it back
        3. Pick the best action using LEARNED weights (not static)
        4. Execute, measure delta, reinforce weights
        5. Critical mode (<0.1): multi-CA burst
        """
        if not self.enabled:
            return []

        node_metrics = metrics_aggregator.get_all_metrics()
        sri_data = compute_sri_from_metrics(node_metrics)
        current_sri = sri_data["sri"]
        trend = sri_interpolator.analyze()
        dip = self._detect_sri_dip(current_sri)

        executed = []

        # === ALWAYS HEAL: find the node that's dragging SRI down ===
        rca = self.perform_rca(node_metrics, sri_data)
        root_node = rca.get("root_cause_node")
        if not root_node:
            return []

        root_metrics = node_metrics.get(root_node, {})

        # Use per-node learned signal importance to pick dominant signal
        node_imp = self.node_signal_importance.get(root_node, {})
        signal_scores = {}
        for signal in ["latency", "errors", "saturation"]:
            raw = self._signal_severity(root_metrics, signal)
            importance = node_imp.get(signal, 0.33)
            signal_scores[signal] = raw * importance
        dominant_signal = max(signal_scores, key=signal_scores.get)

        # --- CRITICAL MODE: SRI < 0.1 -> multi-CA burst ---
        if current_sri < SRI_CRITICAL_THRESHOLD:
            fea = self.perform_fea(node_metrics, sri_data)
            yield_nodes = fea.get("yield_nodes", [])
            batch_id = f"critical_{datetime.now(timezone.utc).timestamp()}"
            for yn in yield_nodes[:3]:
                yn_m = node_metrics.get(yn["node"], {})
                yn_imp = self.node_signal_importance.get(yn["node"], {})
                yn_scores = {s: self._signal_severity(yn_m, s) * yn_imp.get(s, 0.33) for s in ["latency", "errors", "saturation"]}
                yn_signal = max(yn_scores, key=yn_scores.get)
                action_id = self._select_signal_aware_action(yn["node"], yn_signal, node_metrics)
                if action_id:
                    result = self.execute_action(action_id, triggered_by="emergent_critical", target_signal=yn_signal, target_node_override=yn["node"])
                    if result["success"]:
                        result["record"]["rca_root_cause"] = root_node
                        result["record"]["target_signal"] = yn_signal
                        result["record"]["dip"] = dip
                        result["record"]["trend"] = trend["trend"]
                        result["record"]["batch_id"] = batch_id
                        result["record"]["selection_method"] = "emergent_learned"
                        executed.append(result["record"])
                        await alert_manager.broadcast({"type": "healing", "record": result["record"]})
            if executed:
                return executed

        # --- STEADY PRESSURE: best learned action on root cause ---
        action_id = self._select_signal_aware_action(root_node, dominant_signal, node_metrics)
        if action_id:
            result = self.execute_action(action_id, triggered_by="emergent_steady", target_signal=dominant_signal, target_node_override=root_node)
            if result["success"]:
                attribution = attribution_engine.attribute_dip(node_metrics, sri_data, metrics_aggregator.get_golden_signals())
                cx = metrics_aggregator.get_customer_experience()
                reliability = business_metrics.compute_reliability_score(sri=current_sri, apdex=cx["apdex"], availability=cx["availability"])

                result["record"]["rca_root_cause"] = root_node
                result["record"]["rca_confidence"] = rca["confidence"]
                result["record"]["rca_score"] = rca["rca_score"]
                result["record"]["target_signal"] = dominant_signal
                result["record"]["dip"] = dip
                result["record"]["trend"] = trend["trend"]
                result["record"]["selection_method"] = "emergent_learned"
                result["record"]["business_context"] = {
                    "reliability_score": reliability["score"],
                    "business_justification": attribution["healing_priority"]["business_justification"],
                    "conversion_rate": business_metrics.get_funnel()["conversion_rates"]["overall"],
                    "apdex": cx["apdex"],
                }
                executed.append(result["record"])
                await alert_manager.broadcast({"type": "healing", "record": result["record"]})
                return executed

        # --- CROSS-NODE FALLBACK ---
        action_id = self._select_adaptive_action(root_node, node_metrics)
        if action_id:
            result = self.execute_action(action_id, triggered_by="emergent_crossnode", target_signal=dominant_signal, target_node_override=root_node)
            if result["success"]:
                result["record"]["rca_root_cause"] = root_node
                result["record"]["target_signal"] = dominant_signal
                result["record"]["selection_method"] = "emergent_crossnode"
                executed.append(result["record"])
                await alert_manager.broadcast({"type": "healing", "record": result["record"]})

        return executed

    def _signal_severity(self, node_metrics: Dict, signal: str) -> float:
        """Raw severity of a signal on a node (0 to 1)."""
        if signal == "errors":
            return min(node_metrics.get("error", 0) / 0.1, 1.0)
        elif signal == "latency":
            return min(node_metrics.get("latency", 0) / 150.0, 1.0)
        else:
            return node_metrics.get("saturation", 0)

    def _select_signal_aware_action(self, target_node: str, dominant_signal: str, node_metrics: Dict) -> Optional[str]:
        """Select the action with highest affinity for the dominant failing signal
        on the target node. Skips exhausted and cooldown-blocked actions.
        This is the PRECISION component — matching the right tool to the right problem."""

        ladder = self.escalation_ladder.get(target_node, [])
        # Score each action by its affinity for the dominant signal
        scored = []
        for action_id in ladder:
            action = self.actions.get(action_id)
            if not action or not action.can_execute():
                continue
            if self._is_action_exhausted(action_id):
                continue
            affinity = self.action_signal_affinity.get(action_id, {}).get(dominant_signal, 0)
            scored.append((action_id, affinity))

        # Sort by affinity descending — pick the most precise action
        scored.sort(key=lambda x: -x[1])

        if scored:
            return scored[0][0]

        # Cross-node fallback
        neighbors = self.node_neighbors.get(target_node, [])
        for neighbor in neighbors:
            neighbor_ladder = self.escalation_ladder.get(neighbor, [])
            for action_id in neighbor_ladder:
                action = self.actions.get(action_id)
                if not action or not action.can_execute():
                    continue
                if self._is_action_exhausted(action_id):
                    continue
                affinity = self.action_signal_affinity.get(action_id, {}).get(dominant_signal, 0)
                if affinity > 0.3:
                    return action_id

        return None

    def analyze_topology(self, node_metrics: Dict, sri_data: Dict, granularity: str = "service") -> Dict:
        """Service Mesh Topology Analysis with dynamic granularity.

        Analyzes the infrastructure graph as a service mesh, computing per-service
        load pressure, health debt, and connection strength to identify which
        services are under critical load and which paths are fragile.

        Granularity:
        - 'service':   6 nodes (Frontend, API, Cache, DB, Queue, Backend)
        - 'component': ~50 sub-components below each service ('fine' is also accepted)
        - 'endpoint':  ~100+ leaf endpoints (queries / cache-keys / queue-topics)
                       — synthesised by splitting parent traffic across endpoints
        """
        # Build node list based on granularity
        gran = granularity
        if gran == "endpoint":
            endpoints_map = TOPOLOGY_SCHEMA["endpoints"]
            components_map = TOPOLOGY_SCHEMA["components"]
            fine_edges = [tuple(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]]
            ep_metrics = {}
            # First, derive a noisy per-component metric from its parent service
            comp_to_parent = {c: parent for parent, comps in components_map.items() for c in comps}
            for ep_list in endpoints_map.values():
                for ep in ep_list:
                    component = ".".join(ep.split(".")[:2])  # "API.auth.login" → "API.auth"
                    parent = comp_to_parent.get(component, ep.split(".")[0])
                    pm = node_metrics.get(parent, {})
                    sibling_count = max(len(endpoints_map.get(component, [])), 1)
                    noise = random.uniform(0.7, 1.4)
                    ep_metrics[ep] = {
                        "traffic": max(1, int(pm.get("traffic", 1) / sibling_count)),
                        "latency": pm.get("latency", 5) * noise,
                        "error": min(1, pm.get("error", 0) * random.uniform(0.4, 2.2)),
                        "saturation": min(1, pm.get("saturation", 0) * random.uniform(0.6, 1.6)),
                    }
            nodes_list = list(ep_metrics.keys())
            edges = fine_edges
            metrics_to_use = ep_metrics
        elif gran in ("fine", "component"):
            # Fine-grained: use shared TOPOLOGY_SCHEMA sub-components + edges
            sub_services = TOPOLOGY_SCHEMA["components"]
            fine_edges = [tuple(e) for e in TOPOLOGY_SCHEMA["fine_edges"]]
            # Derive sub-service metrics from parent
            fine_metrics = {}
            for parent, subs in sub_services.items():
                pm = node_metrics.get(parent, {})
                for sub in subs:
                    noise = random.uniform(0.8, 1.2)
                    fine_metrics[sub] = {
                        "traffic": max(1, int(pm.get("traffic", 1) / len(subs))),
                        "latency": pm.get("latency", 5) * noise,
                        "error": min(1, pm.get("error", 0) * random.uniform(0.5, 2.0)),
                        "saturation": min(1, pm.get("saturation", 0) * random.uniform(0.7, 1.5)),
                    }
            nodes_list = list(fine_metrics.keys())
            edges = fine_edges
            metrics_to_use = fine_metrics
        else:
            nodes_list = list(node_metrics.keys())
            edges = [tuple(e) for e in TOPOLOGY_SCHEMA["inter_edges"]]
            metrics_to_use = node_metrics

        n = len(nodes_list)
        node_idx = {name: i for i, name in enumerate(nodes_list)}

        # -- Connection Strength Matrix (Laplacian) --
        K = np.zeros((n, n))
        edge_data = []
        for (a, b) in edges:
            if a in node_idx and b in node_idx:
                ia, ib = node_idx[a], node_idx[b]
                ma = metrics_to_use.get(a, {})
                Ta = ma.get("traffic", 0) + 1
                La = ma.get("latency", 0) + 1
                Ea = ma.get("error", 0)
                Sa = ma.get("saturation", 0)
                w = (Ta / La) * (1 - Sa) * (1 - Ea)
                w = max(w, 0.001)
                K[ia, ib] -= w
                K[ib, ia] -= w
                K[ia, ia] += w
                K[ib, ib] += w
                edge_data.append({"source": a, "target": b, "connection_strength": round(float(w), 4)})

        # -- Degradation Load Vector --
        f = np.zeros(n)
        for i, name in enumerate(nodes_list):
            m = metrics_to_use.get(name, {})
            f[i] = (min(m.get("latency", 0) / 200.0, 1.0) * 0.30 +
                     min(m.get("error", 0) / 0.15, 1.0) * 0.45 +
                     m.get("saturation", 0) * 0.25)

        # -- Solve for Service Drift --
        try:
            u = np.linalg.pinv(K) @ f
        except Exception:
            u = np.zeros(n)

        # -- Health Debt per service --
        health_debt = np.array([0.5 * abs(u[i]) * K[i, i] * abs(u[i]) for i in range(n)])

        # -- Service Pressure (combined load intensity) --
        service_pressure = np.zeros(n)
        for i in range(n):
            direct = abs(u[i]) * K[i, i]
            load = f[i]
            service_pressure[i] = np.sqrt(max(direct**2 + load**2 - direct * load, 0))

        # -- Failure Threshold (adaptive) --
        sp_mean = float(np.mean(service_pressure))
        sp_std = float(np.std(service_pressure))
        failure_threshold = max(sp_mean + 0.5 * sp_std, 0.10)

        # -- Identify critical services --
        node_action_map = {
            "Cache": "cache_flush", "API": "rate_limit",
            "Backend": "circuit_breaker", "DB": "connection_pool_reset",
            "Queue": "queue_drain",
        }
        # For fine-grained, map sub-services to parent actions
        if granularity == "fine":
            for parent, action in list(node_action_map.items()):
                for sub in sub_services.get(parent, []):
                    node_action_map[sub] = action

        services = []
        critical_services = []
        for i, name in enumerate(nodes_list):
            entry = {
                "service": name,
                "service_drift": round(float(u[i]), 6),
                "degradation_load": round(float(f[i]), 4),
                "health_debt": round(float(health_debt[i]), 6),
                "service_pressure": round(float(service_pressure[i]), 4),
                "is_critical": bool(service_pressure[i] > failure_threshold),
                "corrective_action": node_action_map.get(name),
                "metrics": {
                    "latency_ms": round(metrics_to_use.get(name, {}).get("latency", 0), 1),
                    "error_rate_pct": round(metrics_to_use.get(name, {}).get("error", 0) * 100, 2),
                    "saturation_pct": round(metrics_to_use.get(name, {}).get("saturation", 0) * 100, 1),
                    "traffic": metrics_to_use.get(name, {}).get("traffic", 0),
                },
            }
            services.append(entry)
            if entry["is_critical"]:
                critical_services.append(entry)

        critical_services.sort(key=lambda x: -x["health_debt"])
        services.sort(key=lambda x: -x["service_pressure"])

        # -- Path Fragility (edge analysis) --
        path_analysis = []
        max_path_fragility = 1e-9
        for ed in edge_data:
            ia, ib = node_idx[ed["source"]], node_idx[ed["target"]]
            drift_diff = abs(u[ia] - u[ib])
            fragility = drift_diff * ed["connection_strength"]
            max_path_fragility = max(max_path_fragility, fragility)
            path_analysis.append({
                "source": ed["source"], "target": ed["target"],
                "connection_strength": ed["connection_strength"],
                "drift_differential": round(float(drift_diff), 6),
                "path_fragility": round(float(fragility), 4),
            })

        # Cascade-risk score per edge (HaiQ-inspired):
        #   risk(i,j) = norm_pressure_avg(i,j) * connection_strength(i,j) / total_strength_at_target
        #   ranges in [0,1] — probability mass that a fault originating at i
        #   propagates to j given current upstream stress and coupling.
        max_pressure = float(max(service_pressure)) if n else 1.0
        target_in_strength: Dict[str, float] = {}
        for ed in edge_data:
            target_in_strength[ed["target"]] = target_in_strength.get(ed["target"], 0) + ed["connection_strength"]
            target_in_strength[ed["source"]] = target_in_strength.get(ed["source"], 0) + ed["connection_strength"]
        for entry in path_analysis:
            ia, ib = node_idx[entry["source"]], node_idx[entry["target"]]
            avg_pressure = (service_pressure[ia] + service_pressure[ib]) / 2.0
            norm_pressure = float(avg_pressure / max_pressure) if max_pressure > 0 else 0.0
            ts = target_in_strength.get(entry["target"], entry["connection_strength"]) or 1e-9
            cascade_risk = norm_pressure * (entry["connection_strength"] / ts)
            entry["cascade_risk"] = round(float(min(max(cascade_risk, 0.0), 1.0)), 4)

        path_analysis.sort(key=lambda x: -x["path_fragility"])

        trend = sri_interpolator.analyze()

        return {
            "granularity": granularity,
            "mesh_size": n,
            "services": services,
            "critical_services": critical_services,
            "failure_threshold": round(float(failure_threshold), 4),
            "path_analysis": path_analysis,
            "total_health_debt": round(float(np.sum(health_debt)), 6),
            "max_service_pressure": round(float(np.max(service_pressure)), 4),
            "degradation_load": {nodes_list[i]: round(float(f[i]), 4) for i in range(n)},
            "service_drift": {nodes_list[i]: round(float(u[i]), 6) for i in range(n)},
            "sri_trend": trend,
            "multi_ca_recommended": len(critical_services) > 1,
            "recommended_cas": [cs["corrective_action"] for cs in critical_services],
            "sri_at_analysis": round(float(sri_data.get("sri", 0)), 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # FEA strict-sense ↔ software-friendly term mapping. Every consumer
            # gets both vocabularies side-by-side so the same dashboard reads
            # well to both reliability engineers and structural-FEA folks.
            "terminology": {
                "stress (σ)": "Service Pressure — request·latency / capacity",
                "von_mises (σvm)": "Composite Pressure — combined latency+error+saturation load",
                "strain (ε)": "Service Drift — % deviation of node state from baseline",
                "stiffness (K)": "Connection Strength — 1 / (latency · error_rate)",
                "yield (σy)": "Failure Threshold — pressure at which a service breaks SLO",
                "displacement (u)": "State Deviation — solved drift vector u from K·u = F",
                "load (F)": "Degradation Load — weighted sum of latency + errors + saturation",
                "energy (E)": "Resilience Debt — ∫₀ᵗ Φ dt (cumulative system imbalance)",
                "potential (Φ)": "Stability Potential — xᵀLx, drives adaptive healing",
                "cascade_risk": "HaiQ-inspired propagation probability w_ij·norm_pressure / Σ_in",
            },
            "fea_equation": "K · u = F  →  σ = K · ε  →  σvm = √((σ₁−σ₂)² + (σ₂−σ₃)² + (σ₃−σ₁)²)/√2",
        }

    def simulate_fault_propagation(self, source: str, fault_strength: float = 1.0,
                                    steps: int = 30, dt: float = 0.5,
                                    granularity: str = "service") -> Dict:
        """Simulate how a fault at `source` propagates through the topology.

        Uses Laplacian diffusion `x(t+Δt) = x(t) − dt·α·L·x(t)` with the
        adjacency strength as edge weights. This implements the propagation
        kernel from the SRI/Unified-View papers: stability potential
        Φ = xᵀLx evolves over time as the fault diffuses across coupled
        services. Each component j sees rising x_j(t) when a fault at i
        propagates through edges (i→…→j).
        """
        # Build node list + Laplacian from TOPOLOGY_SCHEMA
        if granularity == "endpoint":
            nodes_list: List[str] = [
                ep for eps in TOPOLOGY_SCHEMA["endpoints"].values() for ep in eps
            ]
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]]
        elif granularity == "component":
            services_list = TOPOLOGY_SCHEMA["services"]
            nodes_list = []
            for svc in services_list:
                nodes_list.extend(TOPOLOGY_SCHEMA["components"].get(svc["name"], []))
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["fine_edges"]]
        else:
            nodes_list = [s["name"] for s in TOPOLOGY_SCHEMA["services"]]
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["inter_edges"]]

        if source not in nodes_list:
            raise ValueError(f"Unknown source '{source}' for granularity={granularity}")

        n = len(nodes_list)
        idx = {name: i for i, name in enumerate(nodes_list)}

        # Symmetric Laplacian: L = D - A
        A = np.zeros((n, n))
        for (a, b) in edges_list:
            if a in idx and b in idx:
                A[idx[a], idx[b]] = 1.0
                A[idx[b], idx[a]] = 1.0
        D = np.diag(A.sum(axis=1))
        L = D - A

        # Diffusion coefficient — chosen so the wave reaches the farthest
        # node before `steps` * dt. With dt=0.5 and steps=30 this gives a
        # visually pleasing animation regardless of mesh size.
        alpha = 0.25

        x = np.zeros(n)
        x[idx[source]] = float(max(0.0, min(1.0, fault_strength)))

        timeline = []
        node_max = {name: 0.0 for name in nodes_list}
        first_arrival_step = {name: None for name in nodes_list}
        arrival_threshold = 0.05  # mark a node "infected" once x crosses this

        for step in range(steps + 1):
            # Record snapshot
            snap_x = {nodes_list[i]: round(float(max(0.0, min(1.0, x[i]))), 4) for i in range(n)}
            phi = float(x.T @ L @ x)
            timeline.append({
                "step": step,
                "t": round(step * dt, 3),
                "x": snap_x,
                "phi": round(phi, 4),
                "infected_count": int(sum(1 for v in snap_x.values() if v >= arrival_threshold)),
            })
            for i, name in enumerate(nodes_list):
                if x[i] > node_max[name]:
                    node_max[name] = float(x[i])
                if first_arrival_step[name] is None and x[i] >= arrival_threshold:
                    first_arrival_step[name] = step

            # Evolve: dx/dt = -L x  (heat equation on the graph)
            x = x - dt * alpha * (L @ x)
            # Re-clamp source to keep the fault active for the whole window
            x[idx[source]] = max(x[idx[source]], 0.5 * timeline[0]["x"][source])
            x = np.clip(x, 0.0, 1.0)

        # Per-node summary: peak fault, time-to-arrival
        node_summary = []
        for name in nodes_list:
            arr = first_arrival_step[name]
            node_summary.append({
                "node": name,
                "peak_fault": round(node_max[name], 4),
                "first_arrival_step": arr,
                "first_arrival_t": round(arr * dt, 2) if arr is not None else None,
                "is_source": name == source,
            })
        node_summary.sort(key=lambda r: (-r["peak_fault"], r["first_arrival_step"] or 999))

        return {
            "source": source,
            "granularity": granularity,
            "fault_strength": fault_strength,
            "steps": steps,
            "dt": dt,
            "alpha": alpha,
            "mesh_size": n,
            "timeline": timeline,
            "node_summary": node_summary,
            "total_phi": round(sum(t["phi"] for t in timeline), 4),
            "max_phi": round(max(t["phi"] for t in timeline), 4),
            "max_infected": max(t["infected_count"] for t in timeline),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def auto_dampen_wave(self, source: str, fault_strength: float = 1.0,
                          steps: int = 30, dt: float = 0.5,
                          granularity: str = "service",
                          critical_arrival_threshold: float = 0.30,
                          auto_execute: bool = False) -> Dict:
        """Compute and (optionally) execute a dampening action that arrests
        a traveling fault wave before it reaches downstream critical nodes.

        Algorithm (wave-mechanics inspired):
          1. Simulate the un-dampened propagation.
          2. Find downstream nodes whose peak_fault > critical_arrival_threshold.
          3. BFS from source → identify the first cut-edge on each path.
          4. Pick the cut-edge with the highest cascade-risk score.
          5. Re-simulate with that edge removed (zero coupling) → "dampened".
          6. Map the cut to a software-side healing action:
             - circuit_breaker on the target service
             - rate_limit on the source service
             - cache_flush if either endpoint is Cache.*
          7. If auto_execute, apply the action.
        """
        # Step 1: baseline propagation
        baseline = self.simulate_fault_propagation(source, fault_strength, steps, dt, granularity)

        # Step 2: critical arrivals (excluding source)
        critical_arrivals = [
            n for n in baseline["node_summary"]
            if not n["is_source"] and n["peak_fault"] >= critical_arrival_threshold
        ]
        if not critical_arrivals:
            return {
                "wave_arrested": False,
                "reason": "no_critical_arrivals",
                "critical_arrival_threshold": critical_arrival_threshold,
                "baseline": baseline,
                "recommended_action": None,
                "auto_executed": False,
            }

        # Build adjacency for BFS
        if granularity == "endpoint":
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]]
        elif granularity == "component":
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["fine_edges"]]
        else:
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["inter_edges"]]
        adj: Dict[str, List[str]] = {}
        for a, b in edges_list:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)

        # Step 3: BFS path source → each critical arrival
        def bfs_path(src: str, dst: str) -> List[str]:
            if src == dst:
                return [src]
            seen = {src}
            queue = [(src, [src])]
            while queue:
                cur, path = queue.pop(0)
                for nxt in adj.get(cur, []):
                    if nxt in seen:
                        continue
                    if nxt == dst:
                        return path + [nxt]
                    seen.add(nxt)
                    queue.append((nxt, path + [nxt]))
            return []

        # Compute fea path_analysis for cascade_risk lookup
        node_metrics = metrics_aggregator.get_all_metrics()
        sri_data = compute_sri_from_metrics(node_metrics)
        topo = self.analyze_topology(node_metrics, sri_data, granularity=("fine" if granularity == "component" else "service"))
        risk_lookup: Dict[Tuple[str, str], float] = {}
        for e in topo.get("path_analysis", []):
            risk_lookup[(e["source"], e["target"])] = e.get("cascade_risk", 0.0)
            risk_lookup[(e["target"], e["source"])] = e.get("cascade_risk", 0.0)

        # Step 4: pick the cut-edge with max cascade_risk across all paths
        best_edge = None
        best_score = -1.0
        best_target = None
        for arrival in critical_arrivals:
            path = bfs_path(source, arrival["node"])
            if len(path) < 2:
                continue
            for i in range(len(path) - 1):
                a, b = path[i], path[i + 1]
                # Don't cut the source's own outbound — pick the edge furthest from source
                # but still upstream of the critical arrival
                score = risk_lookup.get((a, b), 0.0) * (i + 1)  # weight by depth
                if score > best_score:
                    best_score = score
                    best_edge = (a, b)
                    best_target = arrival["node"]

        if not best_edge:
            return {
                "wave_arrested": False,
                "reason": "no_cut_edge_found",
                "baseline": baseline,
                "recommended_action": None,
                "auto_executed": False,
            }

        # Step 5: re-simulate with that edge cut
        dampened = self._simulate_with_cut(source, fault_strength, steps, dt, granularity, cut_edge=best_edge)

        # Step 6: map to a healing action
        cut_a, cut_b = best_edge
        cut_a_parent = cut_a.split(".")[0] if "." in cut_a else cut_a
        cut_b_parent = cut_b.split(".")[0] if "." in cut_b else cut_b
        if cut_a_parent == "Cache" or cut_b_parent == "Cache":
            mapped_action = "cache_flush"
            mapped_target = "Cache"
        elif cut_b_parent == "DB" or cut_a_parent == "DB":
            mapped_action = "connection_pool_reset"
            mapped_target = "DB"
        elif cut_b_parent == "Backend" or cut_a_parent == "Backend":
            mapped_action = "circuit_breaker"
            mapped_target = "Backend"
        elif cut_b_parent == "Queue" or cut_a_parent == "Queue":
            mapped_action = "queue_drain"
            mapped_target = "Queue"
        else:
            mapped_action = "rate_limit"
            mapped_target = "API"

        # Wave arrest stats — measure dampening on nodes BEYOND the cut, not at
        # the cut endpoint itself (which is the direct path-target, where peak
        # rarely changes). This gives a meaningful "X% arrested" number.
        excluded = {source, cut_a, cut_b}
        beyond_cut_baseline = [s["peak_fault"] for s in baseline["node_summary"] if s["node"] not in excluded]
        beyond_cut_dampened = [s["peak_fault"] for s in dampened["node_summary"] if s["node"] not in excluded]
        baseline_max = max(beyond_cut_baseline) if beyond_cut_baseline else 0.0
        dampened_max = max(beyond_cut_dampened) if beyond_cut_dampened else 0.0
        # Avoid division by zero / overflow → clamp to 0..100
        if baseline_max < 1e-4:
            arrested_pct = 0.0
        else:
            arrested_pct = max(0.0, min(100.0, (1 - dampened_max / baseline_max) * 100))

        # Find "t_arrest" — first step where dampened ≤ 50% of baseline at the worst arrival
        t_arrest = None
        for ts in dampened["timeline"]:
            base_x = next((b for b in baseline["timeline"] if b["step"] == ts["step"]), None)
            if base_x is None:
                continue
            target_x_dampened = ts["x"].get(best_target, 0)
            target_x_baseline = base_x["x"].get(best_target, 0)
            if target_x_baseline > 0.05 and target_x_dampened <= 0.5 * target_x_baseline:
                t_arrest = ts["t"]
                break

        result = {
            "wave_arrested": True,
            "source": source,
            "granularity": granularity,
            "critical_arrivals": critical_arrivals,
            "cut_edge": {"source": best_edge[0], "target": best_edge[1], "cascade_risk": round(risk_lookup.get(best_edge, 0.0), 4)},
            "recommended_action": {
                "action_id": mapped_action,
                "target_node": mapped_target,
                "rationale": f"Cuts the highest-cascade-risk edge ({best_edge[0]}→{best_edge[1]}) on the path to {best_target}",
            },
            "wave_metrics": {
                "baseline_peak_downstream": round(baseline_max, 4),
                "dampened_peak_downstream": round(dampened_max, 4),
                "arrest_percentage": round(arrested_pct, 1),
                "t_arrest_seconds": t_arrest,
            },
            "baseline": baseline,
            "dampened": dampened,
            "auto_executed": False,
            "execution_result": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Step 7: auto-execute if requested
        if auto_execute:
            target_action = self.actions.get(mapped_action)
            cd_remaining = target_action.cooldown_remaining() if target_action else 0.0
            if target_action and not target_action.can_execute():
                # Cooldown blocks the action — surface it cleanly to the UI
                result["execution_result"] = {
                    "success": False,
                    "reason": "cooldown",
                    "cooldown_remaining_seconds": round(cd_remaining, 1),
                    "message": f"{mapped_action} is cooling down for {cd_remaining:.0f}s — recommendation queued.",
                }
            else:
                try:
                    exec_result = self.execute_action(
                        action_id=mapped_action,
                        triggered_by="auto_dampen_wave",
                        target_node_override=mapped_target,
                    )
                    result["auto_executed"] = bool(exec_result.get("success"))
                    result["execution_result"] = {
                        "success": exec_result.get("success"),
                        "sri_before": exec_result.get("record", {}).get("sri_before"),
                        "sri_after": exec_result.get("record", {}).get("sri_after"),
                        "sri_delta": exec_result.get("record", {}).get("sri_delta"),
                    }
                except Exception as e:
                    result["execution_result"] = {"error": str(e)}

        return result

    def _simulate_with_cut(self, source: str, fault_strength: float, steps: int,
                            dt: float, granularity: str, cut_edge: Tuple[str, str]) -> Dict:
        """Same as simulate_fault_propagation but with one edge zeroed out."""
        if granularity == "endpoint":
            nodes_list: List[str] = [
                ep for eps in TOPOLOGY_SCHEMA["endpoints"].values() for ep in eps
            ]
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]]
        elif granularity == "component":
            services_list = TOPOLOGY_SCHEMA["services"]
            nodes_list = []
            for svc in services_list:
                nodes_list.extend(TOPOLOGY_SCHEMA["components"].get(svc["name"], []))
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["fine_edges"]]
        else:
            nodes_list = [s["name"] for s in TOPOLOGY_SCHEMA["services"]]
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["inter_edges"]]

        cut_set = {(cut_edge[0], cut_edge[1]), (cut_edge[1], cut_edge[0])}
        n = len(nodes_list)
        idx = {name: i for i, name in enumerate(nodes_list)}
        A = np.zeros((n, n))
        for (a, b) in edges_list:
            if (a, b) in cut_set:
                continue
            if a in idx and b in idx:
                A[idx[a], idx[b]] = 1.0
                A[idx[b], idx[a]] = 1.0
        D = np.diag(A.sum(axis=1))
        L = D - A
        alpha = 0.25
        x = np.zeros(n)
        x[idx[source]] = float(max(0.0, min(1.0, fault_strength)))

        timeline = []
        node_max = {name: 0.0 for name in nodes_list}
        first_arrival = {name: None for name in nodes_list}
        for step in range(steps + 1):
            snap_x = {nodes_list[i]: round(float(max(0.0, min(1.0, x[i]))), 4) for i in range(n)}
            phi = float(x.T @ L @ x)
            timeline.append({"step": step, "t": round(step * dt, 3), "x": snap_x, "phi": round(phi, 4),
                             "infected_count": int(sum(1 for v in snap_x.values() if v >= 0.05))})
            for i, name in enumerate(nodes_list):
                if x[i] > node_max[name]:
                    node_max[name] = float(x[i])
                if first_arrival[name] is None and x[i] >= 0.05:
                    first_arrival[name] = step
            x = x - dt * alpha * (L @ x)
            x[idx[source]] = max(x[idx[source]], 0.5 * timeline[0]["x"][source])
            x = np.clip(x, 0.0, 1.0)

        node_summary = sorted([
            {"node": name, "peak_fault": round(node_max[name], 4),
             "first_arrival_step": first_arrival[name],
             "first_arrival_t": round(first_arrival[name] * dt, 2) if first_arrival[name] is not None else None,
             "is_source": name == source}
            for name in nodes_list
        ], key=lambda r: (-r["peak_fault"], r["first_arrival_step"] or 999))
        return {"timeline": timeline, "node_summary": node_summary}

    # Backward compatibility alias
    def perform_fea(self, node_metrics: Dict, sri_data: Dict) -> Dict:
        """Alias for analyze_topology with service-level granularity.
        Maps old FEA field names to new software-friendly names for backward compat."""
        result = self.analyze_topology(node_metrics, sri_data, granularity="service")
        # Map to legacy field names for existing consumers
        result["elements"] = result["services"]
        result["yield_nodes"] = result["critical_services"]
        result["yield_threshold"] = result["failure_threshold"]
        result["edge_analysis"] = result["path_analysis"]
        result["total_strain_energy"] = result["total_health_debt"]
        result["max_von_mises"] = result["max_service_pressure"]
        result["load_vector"] = result["degradation_load"]
        result["displacement_vector"] = result["service_drift"]
        # Map per-element fields
        for svc in result["elements"]:
            svc["node"] = svc["service"]
            svc["von_mises_stress"] = svc["service_pressure"]
            svc["strain_energy"] = svc["health_debt"]
            svc["yield_exceeded"] = svc["is_critical"]
            svc["displacement"] = svc["service_drift"]
            svc["load"] = svc["degradation_load"]
        for svc in result["yield_nodes"]:
            svc["node"] = svc["service"]
            svc["von_mises_stress"] = svc["service_pressure"]
            svc["strain_energy"] = svc["health_debt"]
            svc["yield_exceeded"] = svc["is_critical"]
        for edge in result["edge_analysis"]:
            edge["stiffness"] = edge["connection_strength"]
            edge["edge_strain"] = edge["path_fragility"]
            edge["elongation"] = edge["drift_differential"]
        return result

    def perform_rca(self, node_metrics: Dict, sri_data: Dict) -> Dict:
        """Root Cause Analysis: Spectral + Topology + Learned Intelligence.
        Identifies the service dragging SRI down and its dominant failing signal."""
        nodes = list(node_metrics.keys())
        fiedler = sri_data.get("fiedler", [0] * len(nodes))
        if len(fiedler) != len(nodes):
            fiedler = [0] * len(nodes)

        topo = self.analyze_topology(node_metrics, sri_data, granularity="service")
        topo_map = {s["service"]: s for s in topo.get("services", [])}

        node_scores = []
        for i, node_name in enumerate(nodes):
            metrics = node_metrics.get(node_name, {})
            spectral_isolation = abs(fiedler[i])
            degradation = (min(metrics.get("latency", 0) / 200.0, 1.0) * 0.35 +
                          min(metrics.get("error", 0) / 0.2, 1.0) * 0.4 +
                          metrics.get("saturation", 0) * 0.25)

            svc = topo_map.get(node_name, {})
            service_pressure = svc.get("service_pressure", 0)
            health_debt = svc.get("health_debt", 0)

            # RCA score: spectral 25% + degradation 35% + topology pressure 40%
            max_pressure = topo.get("max_service_pressure", 0.01)
            rca_score = (spectral_isolation * 0.25 + degradation * 0.35 +
                         min(service_pressure / max(max_pressure, 0.01), 1.0) * 0.40)

            # Identify dominant signal using learned node importance
            node_imp = self.node_signal_importance.get(node_name, {})
            signal_scores = {}
            for sig in ["latency", "errors", "saturation"]:
                raw = self._signal_severity(metrics, sig)
                importance = node_imp.get(sig, 0.33)
                signal_scores[sig] = raw * importance

            node_scores.append({
                "service": node_name,
                "rca_score": round(rca_score, 4),
                "spectral_isolation": round(spectral_isolation, 4),
                "degradation": round(degradation, 4),
                "health_debt": round(health_debt, 6),
                "service_pressure": round(service_pressure, 4),
                "is_critical": svc.get("is_critical", False),
                "dominant_signal": max(signal_scores, key=signal_scores.get),
                "signal_scores": {k: round(v, 4) for k, v in signal_scores.items()},
                "evidence": {
                    "latency_ms": round(metrics.get("latency", 0), 1),
                    "error_rate_pct": round(metrics.get("error", 0) * 100, 2),
                    "saturation_pct": round(metrics.get("saturation", 0) * 100, 1),
                    "traffic": metrics.get("traffic", 0),
                },
            })

        node_scores.sort(key=lambda x: -x["rca_score"])
        root_cause = node_scores[0] if node_scores else None
        confidence = ("high" if root_cause and root_cause["rca_score"] > 0.5 else
                      "medium" if root_cause and root_cause["rca_score"] > 0.25 else "low")

        node_action_map = {"Cache": "cache_flush", "API": "rate_limit",
                           "Backend": "circuit_breaker", "DB": "connection_pool_reset",
                           "Queue": "queue_drain"}
        recommended_action = node_action_map.get(root_cause["service"]) if root_cause else None

        multi_ca_targets = [
            {"service": ns["service"], "action": node_action_map.get(ns["service"]),
             "rca_score": ns["rca_score"], "service_pressure": ns["service_pressure"],
             "dominant_signal": ns["dominant_signal"]}
            for ns in node_scores if ns["is_critical"]
        ]

        return {
            "root_cause_service": root_cause["service"] if root_cause else None,
            "root_cause_node": root_cause["service"] if root_cause else None,  # backward compat
            "dominant_signal": root_cause["dominant_signal"] if root_cause else None,
            "confidence": confidence,
            "rca_score": root_cause["rca_score"] if root_cause else 0,
            "recommended_action": recommended_action,
            "multi_ca_targets": multi_ca_targets,
            "service_rankings": node_scores,
            "node_rankings": node_scores,  # backward compat
            "topology_summary": {
                "failure_threshold": topo.get("failure_threshold", 0),
                "total_health_debt": topo.get("total_health_debt", 0),
                "max_service_pressure": topo.get("max_service_pressure", 0),
                "critical_service_count": len(topo.get("critical_services", [])),
                "weakest_path": topo["path_analysis"][0] if topo.get("path_analysis") else None,
            },
            "sri_at_analysis": round(sri_data.get("sri", 0), 4),
            "weak_edges": sri_data.get("weak_edges", []),
            "sri_trend": topo.get("sri_trend", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def on_alert(self, alert: dict):
        """React to alerts with precision signal-aware healing.
        Identifies the dominant failing signal and picks the action with
        highest affinity for that signal — swift and precise."""
        if not self.alert_driven:
            return []

        category = alert.get("category", "")
        node = alert.get("node")
        executed = []

        node_metrics = metrics_aggregator.get_all_metrics()
        sri_data = compute_sri_from_metrics(node_metrics)
        rca = self.perform_rca(node_metrics, sri_data)
        dip = self._detect_sri_dip(sri_data["sri"])

        root_node = rca.get("root_cause_node")
        if not root_node:
            root_node = node or "API"

        root_metrics = node_metrics.get(root_node, {})
        dominant_signal = self._identify_dominant_signal(root_metrics)

        # Precision: select action by signal affinity
        action_id = self._select_signal_aware_action(root_node, dominant_signal, node_metrics)
        if action_id:
            result = self.execute_action(action_id, triggered_by="precision_alert", trigger_alert=alert, target_signal=dominant_signal, target_node_override=root_node)
            if result["success"]:
                result["record"]["rca_root_cause"] = root_node
                result["record"]["target_signal"] = dominant_signal
                result["record"]["dip"] = dip
                result["record"]["selection_method"] = "signal_affinity"
                executed.append(result["record"])
                await alert_manager.broadcast({"type": "healing", "record": result["record"]})
                return executed

        # Fallback: adaptive escalation
        action_id = self._select_adaptive_action(root_node, node_metrics)
        if action_id:
            result = self.execute_action(action_id, triggered_by="adaptive_alert", trigger_alert=alert, target_signal=dominant_signal, target_node_override=root_node)
            if result["success"]:
                result["record"]["rca_root_cause"] = root_node
                result["record"]["target_signal"] = dominant_signal
                result["record"]["selection_method"] = "adaptive_escalation"
                executed.append(result["record"])
                await alert_manager.broadcast({"type": "healing", "record": result["record"]})

        return executed

    def get_status(self) -> dict:
        now = datetime.now(timezone.utc)
        self.active_healers = {k: v for k, v in self.active_healers.items() if v > now}

        return {
            "enabled": self.enabled,
            "alert_driven": self.alert_driven,
            "mode": "emergent_intelligence",
            "sri_dip_detection": {
                "high_watermark": round(self.sri_high_watermark, 4),
                "last_sri": round(self.last_sri, 4),
                "dip_threshold": self.sri_dip_threshold,
            },
            "adaptation": self.get_adaptation_status(),
            "active_healers": [
                {"action_id": k, "expires": v.isoformat()}
                for k, v in self.active_healers.items()
            ],
            "total_actions_executed": sum(a.execution_count for a in self.actions.values()),
            "actions": {k: v.to_dict() for k, v in self.actions.items()},
            "recent_history": self.history[-10:] if self.history else [],
            "correction_history": metrics_aggregator.correction_history[-10:] if metrics_aggregator.correction_history else []
        }

class HealingSequenceOptimizer:
    """Compute the optimal ordering of healing actions across multiple
    stressed nodes / dampener cuts.

    Score per candidate:
      score = sri_gain · readiness − cascade_overlap_penalty
      where:
        sri_gain         = action.sri_impact × |effectiveness_history_mean|
        readiness        = 1 − cooldown_remaining / cooldown_total   (0 if cd, 1 if ready)
        cascade_overlap  = sum of cascade_risk for downstream edges of action.target_node
                           that are already covered earlier in the sequence

    Sequence assembly:
      1. Build a per-stressed-node candidate list (one action per node).
      2. Topologically order by propagation depth (root cause first).
      3. Within each depth, pick the highest-score action.
      4. Skip any action whose target_node is already healed in the sequence
         to avoid redundant work.
    """

    def __init__(self, healing_engine):
        self.he = healing_engine

    def _bfs_depth(self, source: str, granularity: str) -> Dict[str, int]:
        if granularity == "endpoint":
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]]
        elif granularity == "component":
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["fine_edges"]]
        else:
            edges_list = [tuple(e) for e in TOPOLOGY_SCHEMA["inter_edges"]]
        adj: Dict[str, List[str]] = {}
        for a, b in edges_list:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        depth = {source: 0}
        queue = [source]
        while queue:
            cur = queue.pop(0)
            for nxt in adj.get(cur, []):
                if nxt not in depth:
                    depth[nxt] = depth[cur] + 1
                    queue.append(nxt)
        return depth

    def optimize(self, stressed_nodes: List[Dict], source: Optional[str] = None,
                 granularity: str = "service") -> Dict:
        """stressed_nodes: list of {"node": str, "pressure": float, "yield_exceeded": bool}.
        source: optional root-cause node for depth ordering. If None, uses the
                most-pressured node as root.
        """
        if not stressed_nodes:
            return {"sequence": [], "skipped": [], "rationale": "no stressed nodes provided"}

        if source is None:
            source = max(stressed_nodes, key=lambda s: s.get("pressure", 0))["node"]
        depth_map = self._bfs_depth(source, granularity)

        candidates: List[Dict] = []
        for sn in stressed_nodes:
            node = sn["node"]
            parent = node.split(".")[0] if "." in node else node
            # Map parent → preferred action (mirrors auto-dampener mapping)
            if parent == "Cache":
                aid = "cache_flush"
            elif parent == "DB":
                aid = "connection_pool_reset"
            elif parent == "Backend":
                aid = "circuit_breaker"
            elif parent == "Queue":
                aid = "queue_drain"
            else:
                aid = "rate_limit"
            action = self.he.actions.get(aid)
            if action is None:
                continue
            # Compute readiness 0..1
            cd_remaining = action.cooldown_remaining()
            readiness = 1.0 if action.cooldown <= 0 else max(0.0, 1.0 - cd_remaining / action.cooldown)
            # Effectiveness history average (default 0.5 if no history)
            hist = self.he.action_effectiveness.get(aid, [])
            avg_eff = (sum(hist) / len(hist)) if hist else 0.0
            sri_gain = abs(action.sri_impact) * (1.0 + abs(avg_eff))
            score = sri_gain * readiness - 0.05 * abs(sn.get("pressure", 0))
            candidates.append({
                "node": node,
                "target_node": parent,
                "action_id": aid,
                "depth": depth_map.get(node, 99),
                "pressure": round(float(sn.get("pressure", 0)), 4),
                "yield_exceeded": bool(sn.get("yield_exceeded", False)),
                "cooldown_remaining": round(cd_remaining, 1),
                "readiness": round(readiness, 3),
                "sri_gain_estimate": round(sri_gain, 4),
                "effectiveness_history_avg": round(avg_eff, 4),
                "score": round(score, 4),
            })

        # Sort: depth asc (root cause first), then score desc
        candidates.sort(key=lambda c: (c["depth"], -c["score"]))

        # Dedup: don't run same action_id twice in a row (cooldown will block anyway)
        sequence: List[Dict] = []
        skipped: List[Dict] = []
        seen_actions: Set[str] = set()
        for c in candidates:
            if c["action_id"] in seen_actions:
                skipped.append({**c, "skip_reason": "duplicate_action_in_sequence"})
                continue
            sequence.append(c)
            seen_actions.add(c["action_id"])

        # Compute expected cumulative SRI gain
        expected_total = round(sum(s["sri_gain_estimate"] * s["readiness"] for s in sequence), 4)
        return {
            "source": source,
            "granularity": granularity,
            "sequence": sequence,
            "skipped": skipped,
            "expected_total_sri_gain": expected_total,
            "ordering_rule": "Root cause first (BFS depth from source) → highest readiness × sri_impact within each depth",
            "candidate_count": len(candidates),
        }

class AggressiveHealingMode:
    """Proactive, multi-objective auto-healing that fires *before* SRI dips.

    Triggers on any of:
      (a) debt rate dE/dt > debt_rate_threshold
      (b) SRI velocity AND acceleration both negative (predicted dip)
      (c) projected reliability lift from candidate action >= min_lift_threshold

    Action scoring (multi-objective):
      score = 0.30·ΔSRI + 0.30·ΔApdex + 0.20·ΔAvail + 0.15·ΔConv − 0.05·cost
    ΔApdex/Avail/Conv are derived from `golden_signals_before/after` in
    healing_engine.history (latency↘ → Apdex↗ / errors↘ → Avail↗ & Conv↗).
    """
    def __init__(self):
        self.enabled = True
        self.debt_rate_threshold = 0.0008  # phi/s units
        self.min_lift_threshold = 0.003    # reliability lift
        self.action_cost = {
            "cache_flush": 0.10, "rate_limit": 0.15, "circuit_breaker": 0.35,
            "connection_pool_reset": 0.30, "queue_drain": 0.20,
            "api_error_suppression": 0.05,
            # Scaling actions are the most expensive — real infra spin-up.
            "scale_out_frontend": 0.50,
            "scale_out_cache_node": 0.40,
            "scale_out_db_read_replica": 0.60,
            "scale_out_backend": 0.50,
            # scale_in actions are cheap — they release infra, no spin-up cost
            "scale_in_frontend":         0.05,
            "scale_in_cache_node":       0.05,
            "scale_in_db_read_replica":  0.05,
            "scale_in_backend":          0.05,
        }
        self.recent_actions: List[Dict] = []   # last 20 proactive fires
        self.reliability_baseline = None       # set on first cycle
        self.reliability_with_aggressive: List[float] = []
        # Per-action observed Φ reduction (debt-rate reduction): mean over recent fires
        self.action_phi_reduction: Dict[str, List[float]] = {}
        # Pending phi-before measurements awaiting next-tick comparison
        # { action_id: [(t_fired, phi_before, fire_index), ...] }
        self._pending_phi: Dict[str, List[Tuple[float, float, int]]] = {}
        # Cumulative SRI lift attributable to aggressive heals (for counterfactual)
        self.cumulative_proactive_sri_lift: float = 0.0
        # iter 40 — cheap-first escalation: bias toward low-cost actions
        # so the engine genuinely walks low-cost-high-improvement → higher-
        # cost rather than picking expensive actions on score parity.
        # The bonus is RELAXED for actions that have already been tried
        # ≥ AGGR_PLATEAU_FIRES times AND whose recent mean |ΔSRI| sits below
        # AGGR_PLATEAU_THRESHOLD (the cheap option proved insufficient,
        # so the engine progresses to costlier alternatives).
        self.AGGR_LOW_COST_BIAS      = float(os.environ.get("AGGR_LOW_COST_BIAS",      "0.08"))
        self.AGGR_PLATEAU_FIRES      = int(  os.environ.get("AGGR_PLATEAU_FIRES",       "3"))
        self.AGGR_PLATEAU_THRESHOLD  = float(os.environ.get("AGGR_PLATEAU_THRESHOLD",  "0.002"))
        self.AGGR_PLATEAU_RELAX      = float(os.environ.get("AGGR_PLATEAU_RELAX",      "0.30"))
        # iter 41 — unified eutectic-distance objective. The auto-heal's
        # PRIMARY goal is now `minimize d(x, Ψ_c)²` (the composite phase-
        # space distance to the eutectic point). SRI/Apdex/Avail/Conv are
        # all consequences of where (L̂, Q, M, E) sits relative to Ψ_c,
        # so this single objective subsumes them. A small `W_BIZ` residual
        # captures business-metric concerns the (L̂, Q, M, E) model
        # doesn't fully express (apdex floor, conversion ceiling).
        self.AGGR_W_EUT      = float(os.environ.get("AGGR_W_EUT",      "5.0"))
        self.AGGR_W_BIZ      = float(os.environ.get("AGGR_W_BIZ",      "0.20"))
        # Snapshot of last rank scoring for the /status payload — exposes
        # per-action (low_cost_bias, plateaued) so operators can see
        # which actions are still in the "cheap-first" budget.
        self._last_rank_breakdown: Dict[str, Dict] = {}

    def status(self) -> Dict:
        gain = 0.0
        if len(self.reliability_with_aggressive) >= 5:
            recent = self.reliability_with_aggressive[-20:]
            gain = float(np.mean(recent[-10:]) - np.mean(recent[:10])) if len(recent) >= 10 else 0.0
        # Counterfactual: what reliability would have been WITHOUT proactive heals.
        # We subtract the cumulative attributable SRI lift (weighted by SRI's
        # reliability weight 0.25) from current reliability.
        current_rel = self.reliability_with_aggressive[-1] if self.reliability_with_aggressive else 0.0
        counterfactual_rel = max(0.0, current_rel - 0.25 * self.cumulative_proactive_sri_lift)
        savings = current_rel - counterfactual_rel
        # Per-action mean Φ reduction (positive = action reduced debt rate)
        phi_red_summary = {
            aid: round(float(np.mean(v[-20:])), 6)
            for aid, v in self.action_phi_reduction.items() if v
        }
        return {
            "enabled": self.enabled,
            "debt_rate_threshold": self.debt_rate_threshold,
            "min_lift_threshold": self.min_lift_threshold,
            "recent_actions": self.recent_actions[-10:],
            "reliability_gain_60s": round(gain, 4),
            "proactive_fire_count": len(self.recent_actions),
            "cumulative_proactive_sri_lift": round(self.cumulative_proactive_sri_lift, 6),
            "counterfactual": {
                "current_reliability": round(current_rel, 4),
                "counterfactual_reliability": round(counterfactual_rel, 4),
                "reliability_saved": round(savings, 4),
                "interpretation": "counterfactual = current − 0.25 × Σ(proactive_sri_lift); 0.25 is SRI's weight in the composite reliability score",
            },
            "phi_reduction_per_action": phi_red_summary,
            # iter 40 — cheap-first escalation surface
            "cheap_first_escalation": {
                "low_cost_bias": self.AGGR_LOW_COST_BIAS,
                "plateau_fires": self.AGGR_PLATEAU_FIRES,
                "plateau_threshold": self.AGGR_PLATEAU_THRESHOLD,
                "plateau_relax": self.AGGR_PLATEAU_RELAX,
                # per-action {bias, plateaued} from the last rank scoring
                "per_action": {
                    aid: {
                        "low_cost_bias": v.get("low_cost_bias", 0.0),
                        "plateaued":     v.get("plateaued", False),
                        "recent_abs_delta": v.get("recent_abs_delta"),
                        "cost":          v.get("cost", 0.0),
                    }
                    for aid, v in self._last_rank_breakdown.items()
                },
            },
        }

    def _action_effectiveness(self) -> Dict[str, Dict[str, float]]:
        """Mine healing_engine.history for per-action mean Δsri/apdex/avail/conv."""
        scores: Dict[str, Dict[str, List[float]]] = {}
        for rec in healing_engine.history[-100:]:
            aid = rec.get("action_id") or rec.get("action")
            if not aid:
                continue
            gb = rec.get("golden_signals_before", {})
            ga = rec.get("golden_signals_after", {})
            d_sri = float(rec.get("sri_delta", 0))
            lat_b = float(gb.get("latency", 0) or 0); lat_a = float(ga.get("latency", 0) or 0)
            err_b = float(gb.get("errors", 0) or 0);  err_a = float(ga.get("errors", 0) or 0)
            # Proxies: lower latency → +Apdex; lower errors → +Avail & +Conv
            d_apdex = max(-1, min(1, (lat_b - lat_a) / max(lat_b, 0.05)))
            d_avail = max(-1, min(1, (err_b - err_a) / max(err_b, 0.005)))
            d_conv  = 0.7 * d_avail + 0.3 * d_apdex
            scores.setdefault(aid, {"sri": [], "apdex": [], "avail": [], "conv": []})
            scores[aid]["sri"].append(d_sri)
            scores[aid]["apdex"].append(d_apdex)
            scores[aid]["avail"].append(d_avail)
            scores[aid]["conv"].append(d_conv)
        out = {}
        for aid, m in scores.items():
            out[aid] = {k: float(np.mean(v)) if v else 0.0 for k, v in m.items()}
        return out

    def rank_actions(self, available_action_ids: List[str]) -> List[Tuple[str, float, Dict]]:
        # Phase-classifier brake (iter 31): if a service is in retry-amplification
        # phase, firing healing actions adds load to the positive-feedback loop.
        # Defer entirely — aggressive_healing_loop will retry on the next tick.
        if phase_classifier_instance is not None and getattr(phase_classifier_instance, "aggressive_braked", False):
            return []
        eff = self._action_effectiveness()
        ranked: List[Tuple[str, float, Dict]] = []
        breakdown: Dict[str, Dict] = {}
        for aid in available_action_ids:
            history_n = len(eff.get(aid, {}).get("sri", [])) if isinstance(eff.get(aid, {}).get("sri"), list) else 0
            e = eff.get(aid, {"sri": 0.0, "apdex": 0.0, "avail": 0.0, "conv": 0.0})
            # Prior: actions without history get a small positive prior so they
            # don't lose only on cost. After a few executions, real effectiveness dominates.
            prior = 0.01 if history_n == 0 else 0.0
            cost = self.action_cost.get(aid, 0.20)
            # 5th term: observed Φ reduction (debt-rate reduction). Bounded so
            # noisy big values don't dominate the score; ×0.10 weight.
            phi_red_history = self.action_phi_reduction.get(aid, [])
            phi_red_mean = float(np.mean(phi_red_history[-20:])) if phi_red_history else 0.0
            phi_term = 0.10 * max(-0.05, min(0.05, phi_red_mean))
            # iter 40 — Low-cost-first escalation bias. Adds up to
            # AGGR_LOW_COST_BIAS for the cheapest actions and ~0 for the
            # most expensive — same shape as the synthesizer's complexity
            # bias (iter 39) but acting on the AggressiveHealingMode's
            # independent scoring. Relaxed when the action has been tried
            # ≥ AGGR_PLATEAU_FIRES times and its recent |ΔSRI| sits below
            # AGGR_PLATEAU_THRESHOLD — i.e. the cheap option has proven
            # insufficient, so the engine progresses to costlier ones.
            # We use HealingEngine.action_effectiveness directly for the
            # plateau test. `healing_engine` is the module-level singleton
            # bound by obs_server._wire_extracted_modules at startup.
            sri_obs = healing_engine.action_effectiveness.get(aid, []) if healing_engine is not None else []
            recent_abs_delta = float(np.mean([abs(x) for x in sri_obs[-self.AGGR_PLATEAU_FIRES:]])) if len(sri_obs) >= self.AGGR_PLATEAU_FIRES else None
            plateaued = (
                recent_abs_delta is not None
                and recent_abs_delta < self.AGGR_PLATEAU_THRESHOLD
            )
            low_cost_bias_raw = self.AGGR_LOW_COST_BIAS * max(0.0, 1.0 - cost)
            low_cost_bias = low_cost_bias_raw * (self.AGGR_PLATEAU_RELAX if plateaued else 1.0)

            # iter 41 — UNIFIED EUTECTIC-DISTANCE OBJECTIVE
            # The primary scoring term: simulated reduction in d(x, Ψ_c)².
            # A negative delta_d2 = action pulls TOWARD Ψ_c = positive score.
            # Action's default target node is used (None ⇒ engine's
            # _ACTION_AXIS_EFFECTS map resolves the target).
            eut_info = healing_engine.simulate_eutectic_delta(None, aid) if healing_engine is not None else None
            delta_d2 = float(eut_info.get("delta_d2", 0.0)) if eut_info else 0.0
            eut_pull_score = -self.AGGR_W_EUT * delta_d2  # +score when delta_d2 < 0

            # Business residual: what (L̂, Q, M, E) doesn't directly model
            # (apdex floor + conversion ceiling). Kept small relative to
            # the eutectic term so it never dominates.
            biz_score = self.AGGR_W_BIZ * (0.6 * e["apdex"] + 0.4 * e["conv"])

            score = (eut_pull_score
                     + biz_score
                     - 0.05 * cost
                     + prior
                     + phi_term
                     + low_cost_bias)
            entry = {
                **e, "cost": cost, "history_n": history_n,
                "phi_reduction_mean": round(phi_red_mean, 6),
                "phi_term": round(phi_term, 6),
                "low_cost_bias": round(low_cost_bias, 6),
                "plateaued": plateaued,
                "recent_abs_delta": round(recent_abs_delta, 6) if recent_abs_delta is not None else None,
                # iter 41 — eutectic-objective surface
                "eut_target":   eut_info.get("target", "") if eut_info else "",
                "eut_cur_d2":   eut_info.get("cur_d2", 0.0) if eut_info else 0.0,
                "eut_new_d2":   eut_info.get("new_d2", 0.0) if eut_info else 0.0,
                "eut_delta_d2": round(delta_d2, 6),
                "eut_pull_score": round(eut_pull_score, 6),
                "biz_score":      round(biz_score, 6),
            }
            ranked.append((aid, round(score, 6), entry))
            breakdown[aid] = entry
        ranked.sort(key=lambda x: x[1], reverse=True)
        self._last_rank_breakdown = breakdown
        return ranked

    def should_fire(self, sri: float, debt_rate: float, sri_velocity: float, sri_accel: float, max_service_pressure: float = 0.0) -> Optional[str]:
        if not self.enabled:
            return None
        if debt_rate > self.debt_rate_threshold:
            return f"debt_rate={debt_rate:.5f} > {self.debt_rate_threshold}"
        if sri_velocity < -0.001 and sri_accel < 0:
            return f"predicted_dip (v={sri_velocity:.4f}, a={sri_accel:.4f})"
        if sri < 0.985 and debt_rate > 0:
            return f"baseline_drift sri={sri:.3f} dE/dt={debt_rate:.5f}"
        # Preemptive: if the most stressed service has appreciable pressure,
        # heal it even when SRI is still nominally healthy
        if max_service_pressure > 0.008:
            return f"preemptive_pressure={max_service_pressure:.3f}"
        return None

class PermanentFunnelHealer:
    """Detects stagnation in the e-commerce conversion funnel, traces the
    root-cause node via SRI attribution, and installs a *permanent* fix —
    a per-node stiffness multiplier persisted in MongoDB. The fix attenuates
    that node's latency / error / saturation contribution going forward,
    permanently reducing resilience-debt accumulation (E = ∫Φ dt) and the
    reliability-debt that follows from it.

    This is the architectural step beyond reactive healing (alerts → 5-s ad-hoc
    actions) and aggressive healing (5-s proactive bursts): it installs
    durable corrections that don't decay between cooldowns.
    """
    def __init__(self):
        self.enabled = True
        self.stagnation_window = 6   # consecutive samples to flag stagnation
        self.conversion_stagnation_threshold = 0.65  # health_adjusted_conversion below 0.65 of base
        self.recent_fixes: List[Dict] = []
        self._conv_history: List[float] = []  # health-adjusted conversion samples
        self._loaded = False
        # Auto-decay: when no stagnation is detected, all multipliers shrink
        # by `decay_factor` each loop tick. With default 0.995 and a 30 s loop,
        # half-life ≈ 57 min, so a node fully self-corrects within 2–3 hours.
        self.decay_factor = 0.995
        self.decay_floor = 0.01  # multipliers below this are dropped
        self._decay_ticks_since_persist = 0
        self.decay_event_count = 0

    async def load_persisted(self):
        """Reload PERMANENT_FIX_REGISTRY from MongoDB on startup."""
        try:
            cursor = db.permanent_fixes.find({}, {"_id": 0})
            count = 0
            async for doc in cursor:
                node = doc.get("node")
                signal = doc.get("signal")
                mult = float(doc.get("multiplier", 0.0))
                if node and signal:
                    PERMANENT_FIX_REGISTRY.setdefault(node, {})[signal] = mult
                    count += 1
            self._loaded = True
            logger.info(f"PermanentFunnelHealer: loaded {count} persisted fixes")
        except Exception as e:
            logger.warning(f"PermanentFunnelHealer.load_persisted: {e}")

    async def _persist(self, node: str, signal: str, multiplier: float, fix_record: Dict):
        try:
            await db.permanent_fixes.update_one(
                {"node": node, "signal": signal},
                {"$set": {
                    "node": node, "signal": signal,
                    "multiplier": float(multiplier),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_fix": fix_record,
                }},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"PermanentFunnelHealer._persist: {e}")

    async def decay_idle(self) -> Dict:
        """Multiplicatively shrink all permanent-fix multipliers when no
        stagnation is detected. Persists every ~10 ticks (~5 min) to keep
        Mongo writes bounded; in-memory state is authoritative between writes."""
        if not PERMANENT_FIX_REGISTRY:
            return {"decayed": 0, "removed": 0}
        decayed = 0
        removed = []
        for node in list(PERMANENT_FIX_REGISTRY.keys()):
            for sig in list(PERMANENT_FIX_REGISTRY[node].keys()):
                old = PERMANENT_FIX_REGISTRY[node][sig]
                new = old * self.decay_factor
                if new < self.decay_floor:
                    del PERMANENT_FIX_REGISTRY[node][sig]
                    removed.append((node, sig))
                else:
                    PERMANENT_FIX_REGISTRY[node][sig] = new
                    decayed += 1
            if not PERMANENT_FIX_REGISTRY[node]:
                del PERMANENT_FIX_REGISTRY[node]
        self.decay_event_count += decayed + len(removed)

        # Persistence policy: every 10 ticks or on removal
        self._decay_ticks_since_persist += 1
        if removed or self._decay_ticks_since_persist >= 10:
            try:
                for node, sig in removed:
                    await db.permanent_fixes.delete_one({"node": node, "signal": sig})
                for node, sigs in PERMANENT_FIX_REGISTRY.items():
                    for sig, mult in sigs.items():
                        await db.permanent_fixes.update_one(
                            {"node": node, "signal": sig},
                            {"$set": {"multiplier": float(mult), "updated_at": datetime.now(timezone.utc).isoformat()}},
                            upsert=False,
                        )
                self._decay_ticks_since_persist = 0
            except Exception as e:
                logger.debug(f"decay_idle persist: {e}")
        if removed:
            logger.info(f"PermanentFunnelHealer DECAY: removed {removed}, decayed {decayed} multipliers")
        return {"decayed": decayed, "removed": len(removed)}

    def status(self) -> Dict:
        # Total estimated debt-rate suppression: sum of all multipliers * baseline impact
        total_suppression = sum(
            mult for node_fixes in PERMANENT_FIX_REGISTRY.values()
            for mult in node_fixes.values()
        )
        return {
            "enabled": self.enabled,
            "stagnation_window": self.stagnation_window,
            "fix_count": sum(len(v) for v in PERMANENT_FIX_REGISTRY.values()),
            "registry": {k: dict(v) for k, v in PERMANENT_FIX_REGISTRY.items()},
            "recent_fixes": self.recent_fixes[-10:],
            "total_debt_suppression_estimate": round(total_suppression, 4),
            "decay": {
                "factor_per_tick": self.decay_factor,
                "floor": self.decay_floor,
                "tick_seconds": 30,
                "half_life_minutes": round(0.5 * 30 / 60 / (1 - self.decay_factor), 1),
                "decay_event_count": self.decay_event_count,
            },
            "interpretation": (
                "PERMANENT fixes attenuate per-node degradation contributions "
                "(latency × (1−0.6m), errors × (1−0.7m), saturation × (1−0.5m)). "
                "When no funnel stagnation is detected, every tick multipliers "
                "are auto-decayed by `factor_per_tick` (default 0.995); they "
                "self-correct as conditions improve and are dropped at the floor."
            ),
        }

    def detect_stagnation(self, funnel: Dict) -> Optional[Dict]:
        """Funnel stagnation = health-adjusted conversion well below base for
        N consecutive samples AND the latest sample is not improving."""
        modeled = funnel.get("modeled_conversion", {})
        base = float(modeled.get("base_conversion_rate", 0.025)) or 0.025
        eff = float(modeled.get("effective_conversion_rate", 0.0))
        ratio = eff / max(base, 1e-6)
        self._conv_history.append(ratio)
        if len(self._conv_history) > 30:
            self._conv_history = self._conv_history[-30:]
        if len(self._conv_history) < self.stagnation_window:
            return None
        recent = self._conv_history[-self.stagnation_window:]
        if all(r < self.conversion_stagnation_threshold for r in recent):
            # Also require non-improving trend (latest <= mean of older samples)
            older = recent[:-1]
            if recent[-1] <= float(np.mean(older)) + 1e-3:
                return {
                    "ratio": round(ratio, 4),
                    "base_conversion": round(base, 4),
                    "effective_conversion": round(eff, 4),
                    "window_samples": recent,
                }
        return None

    async def install_fix(self, attribution: Dict, funnel_stagnation: Dict) -> Optional[Dict]:
        """Find the largest-attribution node/signal pair and install a permanent
        multiplier on it. Returns the fix record (or None if no clear culprit)."""
        per_node = attribution.get("node_attributions", []) or []
        if not per_node:
            return None
        top = per_node[0]  # already sorted by total_attribution desc
        node = top.get("node")
        signals = top.get("signal_breakdown", {})  # { latency: x, errors: y, saturation: z }
        if not signals or not node:
            return None
        worst_signal = max(signals.items(), key=lambda s: float(s[1]))[0]
        prev = PERMANENT_FIX_REGISTRY.get(node, {}).get(worst_signal, 0.0)
        new_mult = min(0.85, prev + 0.15)
        PERMANENT_FIX_REGISTRY.setdefault(node, {})[worst_signal] = new_mult
        fix = {
            "t": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "signal": worst_signal,
            "multiplier_before": round(prev, 4),
            "multiplier_after": round(new_mult, 4),
            "trigger": "funnel_stagnation",
            "funnel_ratio": funnel_stagnation.get("ratio"),
            "attribution_contribution": round(float(top.get("total_attribution", 0)), 6),
            "rationale": f"Funnel ratio {funnel_stagnation.get('ratio')} below {self.conversion_stagnation_threshold} for {self.stagnation_window} samples; root cause = {node}.{worst_signal}",
        }
        self.recent_fixes.append(fix)
        if len(self.recent_fixes) > 50:
            self.recent_fixes = self.recent_fixes[-50:]
        await self._persist(node, worst_signal, new_mult, fix)
        logger.info(f"PermanentFunnelHealer INSTALLED: {worst_signal}@{node} → {new_mult:.2f} (was {prev:.2f}); funnel ratio {funnel_stagnation.get('ratio'):.3f}")
        return fix
