"""Ladder Synthesizer — "Programs Writing Programs" (iter 30).

Auto-generates new `escalation_ladder` configurations for the HealingEngine
by analysing observed reliability gains of past healing actions per node.

The synthesizer runs on a periodic schedule (or on stagnation triggers),
computes a per-(node, action) gain matrix from `healing_engine.history`,
emits a new escalation ladder ranked by gain, persists the new ladder to
MongoDB (`synthesized_ladders` collection) and atomically swaps it into
the live engine. A rollback guard reverts to the previous version if the
post-swap reliability trend regresses.

The ladder *is* the program. The engine, by observing its own outcomes,
literally rewrites the config that drives its next decisions — meta-
programming for reliability convergence.
"""
from __future__ import annotations

import asyncio
import logging
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Default ladder used as cold-start fallback (mirrors HealingEngine default)
DEFAULT_LADDER: Dict[str, List[str]] = {
    "Frontend": ["scale_out_frontend"],
    "API":      ["rate_limit", "api_error_suppression", "circuit_breaker", "cache_flush"],
    "Cache":    ["cache_flush", "scale_out_cache_node", "connection_pool_reset", "rate_limit"],
    "Backend":  ["circuit_breaker", "scale_out_backend", "rate_limit", "queue_drain", "connection_pool_reset"],
    "DB":       ["connection_pool_reset", "scale_out_db_read_replica", "cache_flush", "circuit_breaker"],
    "Queue":    ["queue_drain", "rate_limit", "connection_pool_reset"],
}

# Action-signal effect profile (mirrors engine's affinity intuition;
# used to break ties when a node has zero observation for an action).
_ACTION_SIGNAL_EFFECTS: Dict[str, Dict[str, float]] = {
    "cache_flush":           {"latency": 0.6, "errors": 0.7, "saturation": 0.1},
    "rate_limit":            {"latency": 0.2, "errors": 0.5, "saturation": 0.5},
    "circuit_breaker":       {"latency": 0.5, "errors": 0.8, "saturation": 0.2},
    "connection_pool_reset": {"latency": 0.5, "errors": 0.3, "saturation": 0.4},
    "queue_drain":           {"latency": 0.5, "errors": 0.1, "saturation": 0.6},
    "api_error_suppression": {"latency": 0.3, "errors": 0.85, "saturation": 0.1},
    # Scaling actions: high latency + saturation impact, no direct error
    # signal (added capacity makes existing errors statistically rarer
    # only as a side effect of lower contention).
    "scale_out_frontend":         {"latency": 0.55, "errors": 0.1, "saturation": 0.70},
    "scale_out_cache_node":       {"latency": 0.50, "errors": 0.1, "saturation": 0.75},
    "scale_out_db_read_replica":  {"latency": 0.55, "errors": 0.1, "saturation": 0.65},
    "scale_out_backend":          {"latency": 0.55, "errors": 0.1, "saturation": 0.70},
    # scale_in_* (iter 37) — eutectic-pulling cost-saving actions. They
    # don't reduce stress signals; the synthesizer's affinity model
    # therefore gives them low gains and they're picked through the
    # eutectic-distance filter in HealingEngine._scale_pulls_to_eutectic,
    # NOT through ranking. Listed here so the synthesizer's gain matrix
    # still contains an entry (avoids KeyError on RUM updates).
    "scale_in_frontend":          {"latency": 0.05, "errors": 0.0, "saturation": 0.02},
    "scale_in_cache_node":        {"latency": 0.05, "errors": 0.0, "saturation": 0.02},
    "scale_in_db_read_replica":   {"latency": 0.05, "errors": 0.0, "saturation": 0.02},
    "scale_in_backend":           {"latency": 0.05, "errors": 0.0, "saturation": 0.02},
}

# iter 39 — Per-action complexity score in [0, 1]. Lower = simpler/safer/
# cheaper/faster to apply (idempotent dampeners). Higher = real infra
# spin-up, long persistence, broader blast radius. Used by the
# synthesizer to break gain-ties in favor of the simpler action so the
# escalation ladder reads as "try the easy thing first, then escalate."
#
# Inputs to the score (normalised + averaged):
#   • action_cost (0-1)
#   • cooldown_norm = cooldown_s / 300       (5-min ceiling)
#   • persistence_norm = dampener_duration / 120
#   • blast_radius (1.0 for scale-out, 0.4 for dampener, 0.2 for cache flush)
_ACTION_COMPLEXITY: Dict[str, float] = {
    # === Tier 1 — simplest / idempotent dampeners ===
    "cache_flush":               0.10,
    "api_error_suppression":     0.12,
    "rate_limit":                0.15,
    "queue_drain":               0.20,
    # === Tier 2 — stateful dampeners ===
    "connection_pool_reset":     0.30,
    "circuit_breaker":           0.45,
    # === Tier 3 — scale_in (releases infra, fast) ===
    "scale_in_frontend":         0.25,
    "scale_in_cache_node":       0.25,
    "scale_in_db_read_replica":  0.30,
    "scale_in_backend":          0.25,
    # === Tier 4 — scale_out (real infra spin-up, long persistence) ===
    "scale_out_cache_node":          0.70,
    "scale_out_frontend":            0.75,
    "scale_out_backend":             0.75,
    "scale_out_db_read_replica":     0.85,
}

ALL_NODES = ["Frontend", "API", "Cache", "Backend", "DB", "Queue"]
ALL_ACTIONS = list(_ACTION_SIGNAL_EFFECTS.keys())

# iter 39 — Complexity-bias coefficient. Added to each action's gain score
# as `+ BIAS × (1 − complexity)` so the ladder reads "low-complexity high-
# improvement actions first → escalate to higher-complexity actions later".
# 0.0 disables the bias (revert to pre-iter-39 behaviour). 0.12 default
# = up to +0.108 lift for the simplest actions, +0.018 for the most
# complex — enough to break ties between comparable observed gains
# without overriding actions that have strong measured ΔSRI.
LADDER_COMPLEXITY_BIAS = float(os.environ.get("LADDER_COMPLEXITY_BIAS", "0.12"))

# Synthesis cadence + guard rails
SYNTHESIS_INTERVAL_S = 120         # re-synthesize every 2 min
STAGNATION_TRIGGER_S = 60          # also fire if SRI flat-lined > 60s
ROLLBACK_WINDOW_S = 60             # evaluate post-swap reliability for 60s
ROLLBACK_REGRESSION_DELTA = 0.02   # if mean SRI drops > 2 pp, revert
MIN_OBS_FOR_GAIN = 1               # at least one observation to weight


class LadderSynthesizer:
    """Programs-writing-programs synthesizer for the action ladder."""

    def __init__(self, engine: Any, business_metrics: Any, db: Any = None):
        self.engine = engine
        self.business_metrics = business_metrics
        self.db = db
        self.lock = Lock()

        # Live state
        self.version: int = 0
        self.last_synth_ts: Optional[str] = None
        self.last_swap_ts: Optional[str] = None
        self.last_swap_sri_baseline: Optional[float] = None
        self.last_reason: str = "init"
        self.history: List[Dict[str, Any]] = []   # version timeline
        self.enabled: bool = True
        self.last_gain_matrix: Dict[str, Dict[str, float]] = {}
        self.last_diff: Dict[str, Dict[str, List[str]]] = {}
        self.rollback_armed: bool = False
        self.previous_ladder: Optional[Dict[str, List[str]]] = None

    # -------------------- analysis --------------------

    def _signal_priority(self) -> Dict[str, float]:
        """Use current golden-signal health to weight signals; degraded ones
        get higher priority (urgency-normalised)."""
        # Avoid hard module dep on metrics_aggregator; ask the engine instead
        try:
            mod = __import__("obs.engines.core", fromlist=["metrics_aggregator"])
            ma = getattr(mod, "metrics_aggregator", None)
            golden = ma.get_golden_signals() if ma else {}
        except Exception:
            golden = {}
        lat = max(1 - golden.get("latency", {}).get("health", 0.5), 0.05)
        err = max(1 - golden.get("errors", {}).get("health", 0.5), 0.05)
        sat = max(1 - golden.get("saturation", {}).get("health", 0.5), 0.05)
        tot = lat + err + sat
        return {"latency": lat / tot, "errors": err / tot, "saturation": sat / tot}

    def compute_gain_matrix(self) -> Dict[str, Dict[str, float]]:
        """Build per-(node, action) gain score from healing_engine.history.

        Score = α * mean_observed_sri_delta + β * affinity_score
            + γ * recency_bias
        Cold-start: affinity-only (engine still useful before any history).
        """
        history = list(getattr(self.engine, "history", []) or [])
        sig_priority = self._signal_priority()

        # group sri_deltas by (node, action), preserving order for recency
        per_pair_deltas: Dict[Tuple[str, str], List[float]] = defaultdict(list)
        for rec in history:
            node = rec.get("target_node")
            aid = rec.get("action_id")
            d = rec.get("sri_delta")
            if not node or not aid or d is None:
                continue
            try:
                per_pair_deltas[(node, aid)].append(float(d))
            except (TypeError, ValueError):
                continue

        matrix: Dict[str, Dict[str, float]] = {n: {} for n in ALL_NODES}
        # Phase-classifier hook (iter 31): under healing-saturation, boost the
        # cost-penalty so the synthesizer favours cheaper actions for the next
        # synthesis pass — breaks the heal-rate / ΔSRI positive feedback.
        cost_boost = 1.0
        try:
            mod = __import__("obs.engines.core", fromlist=["phase_classifier_instance"])
            pc = getattr(mod, "phase_classifier_instance", None)
            if pc is not None:
                cost_boost = float(getattr(pc, "synth_cost_penalty_boost", 1.0))
        except Exception:
            pass

        # Per-action cost (mirrors HealingEngine.action_cost — cheap fallback)
        action_cost = {
            "cache_flush":           0.10, "rate_limit":            0.15,
            "circuit_breaker":       0.35, "connection_pool_reset": 0.25,
            "queue_drain":           0.20, "api_error_suppression": 0.15,
            "scale_out_frontend":         0.50,
            "scale_out_cache_node":       0.40,
            "scale_out_db_read_replica":  0.60,
            "scale_out_backend":          0.50,
            "scale_in_frontend":          0.05,
            "scale_in_cache_node":        0.05,
            "scale_in_db_read_replica":   0.05,
            "scale_in_backend":           0.05,
        }

        # RUM ladder learner (iter 32): per-node action bonuses from
        # user-validated healing sequences. Actions that appear in a
        # sequence whose post-heal page_load / perceived_speed /
        # error_shown_rate moved in the user's favor get a positive
        # additive term, bounded by RUM_BONUS_COEFF.
        rum_bonus_lookup: Dict[str, Dict[str, float]] = {}
        try:
            rl_mod = __import__("obs.engines.rum_ladder_learner", fromlist=["learner"])
            _l = getattr(rl_mod, "learner", None)
            if _l is not None:
                for _node in ALL_NODES:
                    rum_bonus_lookup[_node] = _l.best_action_bonuses(_node)
        except Exception:
            pass

        for node in ALL_NODES:
            rum_bonuses = rum_bonus_lookup.get(node, {})
            for action in ALL_ACTIONS:
                deltas = per_pair_deltas.get((node, action), [])
                # Affinity baseline (effect-vs-current-signal-urgency)
                effects = _ACTION_SIGNAL_EFFECTS.get(action, {})
                affinity = sum(
                    effects.get(s, 0.0) * sig_priority.get(s, 0.0)
                    for s in ("latency", "errors", "saturation")
                )  # ~[0..1]

                if not deltas:
                    # cold start — affinity only, slight negative bias to push
                    # unseen actions down vs observed ones with equal affinity
                    score = 0.5 * affinity
                else:
                    mean = statistics.fmean(deltas)
                    # recency bias: weight last 3 observations 2x
                    recent = deltas[-3:]
                    recency = statistics.fmean(recent) if recent else mean
                    obs_score = 0.6 * mean + 0.4 * recency  # ~[-0.2..+0.2]
                    score = 0.7 * obs_score + 0.3 * affinity

                # Apply phase-driven cost penalty: under healing_saturation
                # (cost_boost == 2.0), heavyweight actions lose ground to
                # cheap ones, breaking the heal-rate positive feedback.
                score -= 0.05 * cost_boost * action_cost.get(action, 0.20)

                # iter 39 — Complexity bias: prefer simpler, lower-blast-
                # radius actions for early ladder positions. Adds up to
                # `LADDER_COMPLEXITY_BIAS` for the simplest actions
                # (complexity ≈ 0) and ~0 for the most complex
                # (complexity ≈ 1). Combined with the cost penalty above,
                # ladders naturally read low-complexity-high-improvement
                # → escalating-complexity from position 1 → position N.
                complexity = _ACTION_COMPLEXITY.get(action, 0.30)
                score += LADDER_COMPLEXITY_BIAS * (1.0 - complexity)

                # RUM-validated sequence bonus (iter 32).
                score += rum_bonuses.get(action, 0.0)

                matrix[node][action] = round(score, 6)
        self.last_gain_matrix = matrix
        return matrix

    def _build_new_ladder(self, matrix: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
        """Rank actions per node by gain score; trim trailing strictly-negative
        non-affinity-justified actions (those whose only score component is
        negative observed delta). Stagnation guard (iter 34): exclude any
        (node, action) pair currently marked stagnant — the synthesizer's
        outer-loop view must respect the inner-loop's removals so the
        next ladder swap doesn't immediately reintroduce a misfiring pair."""
        blocked_per_node: Dict[str, set] = {}
        try:
            stagn_mod = __import__("obs.engines.action_stagnation", fromlist=["guard"])
            _g = getattr(stagn_mod, "guard", None)
            if _g is not None:
                for node in ALL_NODES:
                    blocked_per_node[node] = _g.blocked_pairs_for_node(node)
        except Exception:
            pass

        new_ladder: Dict[str, List[str]] = {}
        for node in ALL_NODES:
            blocked = blocked_per_node.get(node, set())
            scored = sorted(
                ((a, s) for a, s in matrix.get(node, {}).items() if a not in blocked),
                key=lambda kv: kv[1],
                reverse=True,
            )
            # Keep top-K (max 4) and require score > -0.05 (avoid known harmful)
            ranked = [a for a, s in scored if s > -0.05][:4]
            if not ranked:
                # Ladder must be non-empty — fall back to default for this node
                # (still filtering stagnant pairs from the fallback).
                ranked = [a for a in DEFAULT_LADDER.get(node, []) if a not in blocked]
                if not ranked:
                    ranked = list(DEFAULT_LADDER.get(node, []))
            new_ladder[node] = ranked
        return new_ladder

    def _diff_ladder(self, old: Dict[str, List[str]], new: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
        d: Dict[str, Dict[str, List[str]]] = {}
        for node in ALL_NODES:
            o = old.get(node, [])
            n = new.get(node, [])
            if o != n:
                d[node] = {"before": list(o), "after": list(n)}
        return d

    # -------------------- swap + persist --------------------

    async def synthesize(self, reason: str = "scheduled", force: bool = False) -> Dict[str, Any]:
        """Compute → diff → swap → persist a new ladder version."""
        with self.lock:
            if not self.enabled and not force:
                return {"swapped": False, "reason": "disabled"}

            matrix = self.compute_gain_matrix()
            old_ladder = dict(self.engine.escalation_ladder)
            new_ladder = self._build_new_ladder(matrix)
            diff = self._diff_ladder(old_ladder, new_ladder)
            now = datetime.now(timezone.utc).isoformat()
            self.last_synth_ts = now
            self.last_reason = reason

            if not diff and not force:
                return {
                    "swapped": False,
                    "reason": reason,
                    "version": self.version,
                    "ladder": new_ladder,
                    "gain_matrix": matrix,
                    "timestamp": now,
                }

            # ---- atomic swap ----
            self.previous_ladder = old_ladder
            self.engine.escalation_ladder = new_ladder
            self.version += 1
            self.last_swap_ts = now
            try:
                mod = __import__("obs.engines.core", fromlist=["metrics_aggregator"])
                ma = getattr(mod, "metrics_aggregator", None)
                # use current SRI as the post-swap baseline for rollback check
                if ma is not None:
                    node_metrics = ma.get_all_metrics()
                    compute_fn = getattr(mod, "compute_sri_from_metrics", None)
                    if compute_fn is not None:
                        self.last_swap_sri_baseline = float(compute_fn(node_metrics).get("sri", 0))
            except Exception:
                self.last_swap_sri_baseline = None
            self.rollback_armed = True
            self.last_diff = diff

            # Phase tag (iter 31): record the operational phase at swap time
            # so we can learn which ladders perform best in which phases.
            phase_tag = "unknown"
            try:
                mod = __import__("obs.engines.core", fromlist=["phase_classifier_instance"])
                pc = getattr(mod, "phase_classifier_instance", None)
                if pc is not None and getattr(pc, "latest", None) is not None:
                    phase_tag = pc.latest.worst_phase
            except Exception:
                pass

            entry = {
                "version": self.version,
                "timestamp": now,
                "reason": reason,
                "ladder": new_ladder,
                "previous_ladder": old_ladder,
                "diff": diff,
                "gain_matrix": matrix,
                "sri_baseline": self.last_swap_sri_baseline,
                "phase_at_swap": phase_tag,
            }
            self.history.append(entry)
            if len(self.history) > 50:
                self.history = self.history[-50:]

        # persist outside the lock
        await self._persist(entry)
        logger.info(
            "LadderSynthesizer v%s swapped (%s nodes changed) — reason=%s",
            self.version, len(diff), reason,
        )
        return {"swapped": True, **entry}

    async def _persist(self, entry: Dict[str, Any]) -> None:
        if self.db is None:
            return
        try:
            # store a shallow copy excluding any non-serialisable refs
            doc = {
                "version": entry["version"],
                "timestamp": entry["timestamp"],
                "reason": entry["reason"],
                "ladder": entry["ladder"],
                "previous_ladder": entry["previous_ladder"],
                "diff": entry["diff"],
                "gain_matrix": entry["gain_matrix"],
                "sri_baseline": entry.get("sri_baseline"),
            }
            await self.db["synthesized_ladders"].insert_one(doc)
        except Exception as e:
            logger.debug(f"LadderSynthesizer persist failed: {e}")

    async def load_persisted(self) -> None:
        """Load the most recent persisted ladder on boot, swap it in."""
        if self.db is None:
            return
        try:
            doc = await self.db["synthesized_ladders"].find_one(
                sort=[("version", -1)],
                projection={"_id": 0},
            )
            if not doc:
                return
            with self.lock:
                self.version = int(doc.get("version", 0))
                ladder = doc.get("ladder") or {}
                if ladder:
                    self.engine.escalation_ladder = ladder
                self.last_swap_ts = doc.get("timestamp")
                self.last_synth_ts = doc.get("timestamp")
                self.last_diff = doc.get("diff", {})
                self.last_gain_matrix = doc.get("gain_matrix", {})
                self.last_reason = "boot_restore"
                self.history.append({
                    "version": self.version,
                    "timestamp": doc.get("timestamp"),
                    "reason": "boot_restore",
                    "ladder": ladder,
                    "previous_ladder": doc.get("previous_ladder", {}),
                    "diff": doc.get("diff", {}),
                    "gain_matrix": doc.get("gain_matrix", {}),
                })
            logger.info(f"LadderSynthesizer restored v{self.version} from MongoDB")
        except Exception as e:
            logger.debug(f"LadderSynthesizer load_persisted: {e}")

    # -------------------- rollback guard --------------------

    async def evaluate_post_swap(self) -> Dict[str, Any]:
        """Check if the latest swap regressed reliability; auto-rollback if so."""
        if not self.rollback_armed or self.last_swap_sri_baseline is None:
            return {"checked": False}
        if not self.last_swap_ts:
            return {"checked": False}
        # only evaluate after ROLLBACK_WINDOW_S has elapsed
        try:
            t = datetime.fromisoformat(self.last_swap_ts.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - t).total_seconds()
        except Exception:
            elapsed = ROLLBACK_WINDOW_S + 1
        if elapsed < ROLLBACK_WINDOW_S:
            return {"checked": False, "elapsed": elapsed}

        # Pull current SRI; if regressed beyond threshold, rollback
        try:
            mod = __import__("obs.engines.core", fromlist=["metrics_aggregator"])
            ma = getattr(mod, "metrics_aggregator", None)
            compute_fn = getattr(mod, "compute_sri_from_metrics", None)
            if ma is None or compute_fn is None:
                return {"checked": False}
            current_sri = float(compute_fn(ma.get_all_metrics()).get("sri", 0))
        except Exception:
            return {"checked": False}

        delta = current_sri - self.last_swap_sri_baseline
        with self.lock:
            self.rollback_armed = False  # one-shot guard per swap

        if delta < -ROLLBACK_REGRESSION_DELTA and self.previous_ladder:
            logger.warning(
                "LadderSynthesizer rollback triggered: ΔSRI=%.4f, reverting v%s→v%s",
                delta, self.version, self.version - 1,
            )
            await self.rollback_to_previous(reason=f"auto_rollback (ΔSRI={delta:.4f})")
            return {"checked": True, "rolled_back": True, "sri_delta": round(delta, 4)}

        return {"checked": True, "rolled_back": False, "sri_delta": round(delta, 4)}

    async def rollback_to_previous(self, reason: str = "manual") -> Dict[str, Any]:
        with self.lock:
            if not self.previous_ladder:
                return {"rolled_back": False, "reason": "no_previous_ladder"}
            old = dict(self.engine.escalation_ladder)
            self.engine.escalation_ladder = dict(self.previous_ladder)
            self.version += 1
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "version": self.version,
                "timestamp": now,
                "reason": f"rollback:{reason}",
                "ladder": dict(self.previous_ladder),
                "previous_ladder": old,
                "diff": self._diff_ladder(old, self.previous_ladder),
                "gain_matrix": self.last_gain_matrix,
            }
            self.history.append(entry)
            self.last_swap_ts = now
            self.last_synth_ts = now
            self.last_reason = entry["reason"]
            self.previous_ladder = old  # so user can flip back
            self.rollback_armed = False
        await self._persist(entry)
        return {"rolled_back": True, **entry}

    # -------------------- API surface --------------------

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "version": self.version,
            "current_ladder": dict(self.engine.escalation_ladder),
            "previous_ladder": self.previous_ladder,
            "last_synth_ts": self.last_synth_ts,
            "last_swap_ts": self.last_swap_ts,
            "last_reason": self.last_reason,
            "rollback_armed": self.rollback_armed,
            "history_size": len(self.history),
            "synthesis_interval_s": SYNTHESIS_INTERVAL_S,
            "stagnation_trigger_s": STAGNATION_TRIGGER_S,
            "rollback_window_s": ROLLBACK_WINDOW_S,
            "rollback_regression_delta": ROLLBACK_REGRESSION_DELTA,
            "last_gain_matrix": self.last_gain_matrix,
            "last_diff": self.last_diff,
        }

    def list_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(self.history)[-limit:]


# Bound by obs_server.wire_runtime / startup
synthesizer: Optional[LadderSynthesizer] = None


async def synthesis_loop():
    """Background loop: synth every SYNTHESIS_INTERVAL_S; also detect SRI
    stagnation and trigger an early synthesis."""
    logger.info("ladder_synthesis_loop started")
    await asyncio.sleep(25)  # let other singletons settle
    if synthesizer is None:
        logger.warning("ladder_synthesis_loop: synthesizer not wired, exiting")
        return
    await synthesizer.load_persisted()

    last_sri_samples: List[Tuple[float, float]] = []  # (ts, sri)
    last_periodic = asyncio.get_event_loop().time()
    while True:
        try:
            if not synthesizer.enabled:
                await asyncio.sleep(SYNTHESIS_INTERVAL_S)
                continue
            # post-swap rollback check
            await synthesizer.evaluate_post_swap()

            # sample SRI for stagnation detection
            try:
                mod = __import__("obs.engines.core", fromlist=["metrics_aggregator"])
                ma = getattr(mod, "metrics_aggregator", None)
                compute_fn = getattr(mod, "compute_sri_from_metrics", None)
                if ma and compute_fn:
                    sri = float(compute_fn(ma.get_all_metrics()).get("sri", 0))
                    now_t = asyncio.get_event_loop().time()
                    last_sri_samples.append((now_t, sri))
                    # keep last 30s of samples
                    last_sri_samples = [(t, s) for (t, s) in last_sri_samples if now_t - t <= STAGNATION_TRIGGER_S]
                    stagnant = False
                    if len(last_sri_samples) >= 4:
                        sris = [s for _, s in last_sri_samples]
                        if max(sris) - min(sris) < 0.005 and statistics.fmean(sris) < 0.85:
                            stagnant = True
                    now_loop = asyncio.get_event_loop().time()
                    if stagnant:
                        await synthesizer.synthesize(reason="sri_stagnation")
                        last_sri_samples.clear()
                        last_periodic = now_loop
                    elif now_loop - last_periodic >= SYNTHESIS_INTERVAL_S:
                        await synthesizer.synthesize(reason="scheduled")
                        last_periodic = now_loop
            except Exception as e:
                logger.debug(f"synthesis_loop sampler: {e}")
        except Exception as e:
            logger.debug(f"synthesis_loop: {e}")
        await asyncio.sleep(10)
