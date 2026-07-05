"""RUM Ladder Learner (iter 32) — builds reliability from real-user telemetry.

§12.7's `LadderSynthesizer` learns per-(node, action) gains from internal
SRI deltas. This module closes the loop with the **actual user-perceived
outcome** captured by the `rum/beacon` ingestion path:

  • page_load_ms         (navigation timing — what the user waits for)
  • perceived_speed      (0..100 score derived from latency)
  • error_shown_rate     (user-visible HTTP/exception rate)

These three are the only metrics the user can *feel*. A healing decision
that improves internal SRI but does not move these is, from the user's
perspective, a no-op. Conversely, certain **sequences** of cheap actions
(e.g. `rate_limit → cache_flush → connection_pool_reset`) produce
emergent RUM improvements that no individual action's `cx_delta` can
explain. This module mines those sequences and feeds the result back
into the ladder synthesiser as a sequence-bonus term.

Architecture:
  1. Group `correlation_tracker._annotations` into **sequences** —
     contiguous runs of healing actions whose timestamps lie within
     `SEQ_WINDOW_S = 15 s` of each other.
  2. For each sequence, compute the aggregated RUM gain by sampling
     `cx_tracker._samples` for the 30 s preceding the first action and
     the 30 s following the last action. The composite gain is
        gain = 0.4 · Δperceived_speed
             − 0.4 · clamp(Δpage_load_ms / 500, −1, 1)   # normalised
             − 0.2 · 100 · Δerror_shown_rate
  3. Persist the top-K sequences (default 30) to MongoDB
     `rum_validated_sequences` keyed by sequence signature
     `signature = node@action₁→…→action_n`. On boot the latest top-K
     are restored.
  4. Expose a small read API `best_action_bonuses(node)` that the
     `LadderSynthesizer` calls per node when computing its gain matrix.
     Actions that appear in at least one validated sequence for that
     node receive a `RUM_BONUS_COEFF · normalised_gain` additive term.

The result is an end-to-end closed loop: engine → action sequence →
real-user RUM beacon → sequence aggregation → next ladder synthesis.
Reliability is now graded by what users actually feel.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Forward-declared singletons — bound by obs_server.wire_runtime
cx_tracker = None
correlation_tracker = None
db = None


# Tunables
SEQ_WINDOW_S          = 15.0   # max gap between two annotations in a sequence
RUM_BEFORE_AFTER_S    = 30.0   # window for before/after RUM aggregation
MIN_SAMPLES_PER_SIDE  = 0      # tolerate empty before/after (missing
                               # deltas contribute 0 to composite gain).
                               # With real-world traffic this becomes
                               # naturally non-zero almost immediately.
TOP_K_SEQUENCES       = 30     # global cap of "best" sequences
PER_NODE_TOP_K        = 6      # bonus budget per node
RUM_BONUS_COEFF       = 0.15   # max additive term injected into gain matrix
LEARNER_INTERVAL_S    = 15     # loop tick


def _normalise_page_load(delta_ms: float) -> float:
    """Map ms change into [-1, 1] (-1 = 500 ms slower, +1 = 500 ms faster)."""
    if delta_ms is None:
        return 0.0
    return max(-1.0, min(1.0, -float(delta_ms) / 500.0))


def _composite_rum_gain(ps_d: Optional[float], pl_d: Optional[float], er_d: Optional[float]) -> float:
    """Composite gain in roughly [-1.0, +1.5] — positive = users felt better."""
    g_ps = (float(ps_d) / 100.0) if ps_d is not None else 0.0    # 0..1 (1% over 100-pt scale)
    g_pl = _normalise_page_load(pl_d)
    g_er = (-100.0 * float(er_d)) if er_d is not None else 0.0   # 1% error rate cut = +1
    return round(0.4 * g_ps * 100 + 0.4 * g_pl + 0.2 * g_er, 4)


class RumLadderLearner:
    """Mines RUM-validated healing sequences."""

    def __init__(self):
        self.lock = Lock()
        self.top_sequences: List[Dict[str, Any]] = []      # global top-K
        self.per_node_index: Dict[str, List[Dict[str, Any]]] = {}  # for synth lookup
        self.last_pass_ts: Optional[float] = None
        self.last_seq_count: int = 0
        self.last_validated_count: int = 0
        self.enabled: bool = True

    # ----- sequence extraction -----

    def _extract_sequences(self) -> List[List[Dict[str, Any]]]:
        """Group annotations into temporally contiguous runs."""
        if correlation_tracker is None:
            return []
        with correlation_tracker._lock:
            anns = list(correlation_tracker._annotations)
        anns.sort(key=lambda a: a.get("t", 0.0))

        seqs: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for a in anns:
            if not current:
                current = [a]
                continue
            if a["t"] - current[-1]["t"] <= SEQ_WINDOW_S:
                current.append(a)
            else:
                seqs.append(current)
                current = [a]
        if current:
            seqs.append(current)
        # only keep sequences that have at least 2 actions (single-action
        # gain is already covered by §12.7's per-action mean ΔSRI)
        return [s for s in seqs if len(s) >= 2]

    # ----- RUM aggregation -----

    def _aggregate_rum_delta(self, seq: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if cx_tracker is None:
            return None
        first_t = seq[0]["t"]
        last_t = seq[-1]["t"]
        with cx_tracker._lock:
            samples = list(cx_tracker._samples)
        before = [s for s in samples if first_t - RUM_BEFORE_AFTER_S <= s["t"] < first_t]
        after  = [s for s in samples if last_t  <  s["t"] <= last_t + RUM_BEFORE_AFTER_S]
        if len(before) < MIN_SAMPLES_PER_SIDE or len(after) < MIN_SAMPLES_PER_SIDE:
            return None

        def avg(rows, key):
            vals = [r[key] for r in rows if key in r and r[key] is not None]
            return statistics.fmean(vals) if vals else None

        pl_b, pl_a = avg(before, "page_load_ms"), avg(after, "page_load_ms")
        ps_b, ps_a = avg(before, "perceived_speed"), avg(after, "perceived_speed")
        er_b, er_a = avg(before, "error_shown_rate"), avg(after, "error_shown_rate")

        pl_d = (pl_a - pl_b) if (pl_a is not None and pl_b is not None) else None
        ps_d = (ps_a - ps_b) if (ps_a is not None and ps_b is not None) else None
        er_d = (er_a - er_b) if (er_a is not None and er_b is not None) else None

        gain = _composite_rum_gain(ps_d, pl_d, er_d)
        return {
            "page_load_ms_delta": round(pl_d, 1) if pl_d is not None else None,
            "perceived_speed_delta": round(ps_d, 1) if ps_d is not None else None,
            "error_shown_rate_delta": round(er_d, 4) if er_d is not None else None,
            "samples_before": len(before),
            "samples_after": len(after),
            "rum_gain": gain,
        }

    # ----- main pass -----

    def _build_signature(self, seq: List[Dict[str, Any]]) -> Tuple[str, str]:
        """Return (node, chain_signature)."""
        # Use modal node so sequences across different nodes don't collide
        nodes = [a.get("target_node", "?") for a in seq]
        modal_node = max(set(nodes), key=nodes.count) if nodes else "?"
        chain = "->".join(a.get("action_id", "?") for a in seq)
        return modal_node, chain

    async def pass_once(self) -> Dict[str, Any]:
        """One full mining pass: extract → aggregate → merge."""
        seqs = self._extract_sequences()
        self.last_seq_count = len(seqs)
        validated: List[Dict[str, Any]] = []
        for seq in seqs:
            cx_delta = self._aggregate_rum_delta(seq)
            if cx_delta is None:
                continue
            # accept neutral & positive gains (negative ones rejected so we
            # never recommend a sequence the user felt worse from)
            if cx_delta["rum_gain"] < 0:
                continue
            node, chain = self._build_signature(seq)
            validated.append({
                "node": node,
                "chain": chain,
                "actions": [a.get("action_id", "?") for a in seq],
                "nodes": [a.get("target_node", "?") for a in seq],
                "length": len(seq),
                "first_t": seq[0]["t"],
                "last_t": seq[-1]["t"],
                "cx_delta": cx_delta,
                "rum_gain": cx_delta["rum_gain"],
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })

        self.last_validated_count = len(validated)
        if not validated:
            self.last_pass_ts = time.time()
            return {"validated": 0}

        # Merge with existing top — dedupe by (node, chain), prefer higher gain
        with self.lock:
            by_sig: Dict[Tuple[str, str], Dict[str, Any]] = {
                (s["node"], s["chain"]): s for s in self.top_sequences
            }
            for s in validated:
                key = (s["node"], s["chain"])
                cur = by_sig.get(key)
                if cur is None or s["rum_gain"] > cur["rum_gain"]:
                    by_sig[key] = s
            merged = sorted(by_sig.values(), key=lambda s: s["rum_gain"], reverse=True)
            self.top_sequences = merged[:TOP_K_SEQUENCES]

            # Build per-node index for fast synth lookup
            per_node: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for s in self.top_sequences:
                per_node[s["node"]].append(s)
            self.per_node_index = {
                n: sorted(items, key=lambda x: x["rum_gain"], reverse=True)[:PER_NODE_TOP_K]
                for n, items in per_node.items()
            }
            self.last_pass_ts = time.time()

        # persist outside the lock
        await self._persist(validated)
        return {
            "validated": len(validated),
            "top_total": len(self.top_sequences),
            "nodes_with_validated_sequences": len(self.per_node_index),
        }

    async def _persist(self, new_seqs: List[Dict[str, Any]]) -> None:
        if db is None or not new_seqs:
            return
        try:
            for s in new_seqs:
                await db["rum_validated_sequences"].update_one(
                    {"node": s["node"], "chain": s["chain"]},
                    {"$max": {"rum_gain": s["rum_gain"]},
                     "$set": {
                         "node": s["node"],
                         "chain": s["chain"],
                         "actions": s["actions"],
                         "nodes": s["nodes"],
                         "length": s["length"],
                         "cx_delta": s["cx_delta"],
                         "last_seen_at": s["discovered_at"],
                     },
                     "$setOnInsert": {"first_seen_at": s["discovered_at"]}},
                    upsert=True,
                )
        except Exception as e:
            logger.debug(f"RumLadderLearner persist: {e}")

    async def load_persisted(self) -> None:
        if db is None:
            return
        try:
            cursor = db["rum_validated_sequences"].find(
                {}, projection={"_id": 0}
            ).sort("rum_gain", -1).limit(TOP_K_SEQUENCES)
            docs = await cursor.to_list(length=TOP_K_SEQUENCES)
            if not docs:
                return
            with self.lock:
                self.top_sequences = docs
                per_node: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for s in docs:
                    per_node[s["node"]].append(s)
                self.per_node_index = {
                    n: sorted(items, key=lambda x: x["rum_gain"], reverse=True)[:PER_NODE_TOP_K]
                    for n, items in per_node.items()
                }
            logger.info(f"RumLadderLearner restored {len(docs)} validated sequences")
        except Exception as e:
            logger.debug(f"RumLadderLearner load_persisted: {e}")

    # ----- public API (read) -----

    def best_action_bonuses(self, node: str) -> Dict[str, float]:
        """Map of action_id → additive bonus, derived from this node's
        top-K validated sequences. Called by `LadderSynthesizer.compute_gain_matrix`."""
        with self.lock:
            seqs = list(self.per_node_index.get(node, []))
        if not seqs:
            return {}
        # Normalise gains over the per-node top-K so the bonus is bounded
        # by RUM_BONUS_COEFF regardless of absolute gain magnitude.
        max_gain = max((s["rum_gain"] for s in seqs), default=0.0)
        if max_gain <= 0:
            return {}
        out: Dict[str, float] = defaultdict(float)
        for s in seqs:
            w = s["rum_gain"] / max_gain  # [0, 1]
            for action in set(s["actions"]):
                out[action] = max(out[action], RUM_BONUS_COEFF * w)
        return dict(out)

    def top(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.top_sequences)[:limit]

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "enabled": self.enabled,
                "top_total": len(self.top_sequences),
                "nodes_with_validated_sequences": len(self.per_node_index),
                "last_pass_ts": self.last_pass_ts,
                "last_seq_count": self.last_seq_count,
                "last_validated_count": self.last_validated_count,
                "window_seconds": SEQ_WINDOW_S,
                "rum_before_after_s": RUM_BEFORE_AFTER_S,
                "top_k": TOP_K_SEQUENCES,
                "per_node_top_k": PER_NODE_TOP_K,
                "rum_bonus_coeff": RUM_BONUS_COEFF,
            }


# Module-level singleton, bound by wire_runtime
learner: Optional[RumLadderLearner] = None


async def rum_ladder_learner_loop():
    """Background loop — runs `learner.pass_once()` every LEARNER_INTERVAL_S."""
    logger.info("rum_ladder_learner_loop started")
    await asyncio.sleep(30)  # let RUM beacons accumulate
    if learner is None:
        logger.warning("rum_ladder_learner_loop: not wired")
        return
    await learner.load_persisted()
    while True:
        try:
            if learner.enabled:
                await learner.pass_once()
        except Exception as e:
            logger.debug(f"rum_ladder_learner_loop tick: {e}")
        await asyncio.sleep(LEARNER_INTERVAL_S)
