"""Action Stagnation Guard (iter 34) — inner-loop reliability complement
to the LadderSynthesizer's outer-loop adaptation.

The synthesizer rewrites the *ladder* every 120 s (§12.7). Between
synthesis passes, the engine can still spend cycles firing an action
that, on a particular node, has just produced N consecutive zero or
negative ΔSRI outcomes. This module watches every execution in real
time, and as soon as a `(node, action)` pair shows a stagnation
signature, it **dynamically removes the pair from the available action
set** so subsequent `_should_trigger` calls skip it.

Stagnation signature (default thresholds):
  • last 4 attempts on the (node, action) pair all have |ΔSRI| < 0.003
  • AND there has been at least one attempt in the last 90 s
  → mark the pair stagnant.

Removal is reversible:
  • cooldown — pairs are auto-restored 180 s after the last attempt
    (the conditions that caused stagnation may have changed)
  • admin endpoint — POST /api/healing/stagnation/restore can clear
    any pair manually
  • full reset — POST /api/healing/stagnation/reset wipes all state

The guard is consulted by `HealingEngine._should_trigger` (so the
classical escalation walk skips stagnant pairs) and by
`LadderSynthesizer._build_new_ladder` (so newly-synthesized ladders
exclude stagnant pairs entirely until the cooldown expires).

This closes a gap that no other engine covers: §12.7 acts on aggregate
gain, §12.8 acts on regime, §12.9 acts on user-felt outcomes — none of
them stop a single, currently-misfiring action from being re-tried on
its very next cycle.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Forward-declared singleton — bound by wire_runtime
healing_engine = None


# Tunables
STAGNATION_WINDOW            = 4       # last N attempts considered
STAGNATION_EPSILON           = 0.003   # |ΔSRI| below this counts as "no effect"
STAGNATION_MIN_AGE_S         = 90.0    # must have at least one recent attempt
STAGNATION_COOLDOWN_S        = 180.0   # how long the pair stays removed
LOOP_INTERVAL_S              = 30      # background tick — expires cooldowns


class ActionStagnationGuard:
    """Per-(node, action) stagnation detector + dynamic-removal registry."""

    def __init__(self):
        self.lock = Lock()
        # ring buffers: (node, action) → deque of (timestamp, sri_delta)
        self._attempts: Dict[Tuple[str, str], Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=STAGNATION_WINDOW)
        )
        # pairs currently marked stagnant: { (node, action): {removed_at, reason, stats} }
        self._removed: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # full event log (recent removals + restores) for the dashboard
        self._events: Deque[Dict[str, Any]] = deque(maxlen=120)
        self.enabled = True

    # ----------------- consume -----------------

    def record(self, node: str, action: str, sri_delta: float) -> Optional[str]:
        """Called by HealingEngine.execute_action after each execution.
        Returns 'newly_stagnant' if this record tripped removal, else None."""
        if not self.enabled or not node or not action:
            return None
        now = time.time()
        key = (node, action)
        with self.lock:
            self._attempts[key].append((now, float(sri_delta)))
            # if already removed, nothing to do — cooldown will restore later
            if key in self._removed:
                return None
            if len(self._attempts[key]) < STAGNATION_WINDOW:
                return None
            # all of the last N attempts must be (a) close to zero AND (b)
            # within the staleness horizon — old stagnation should *not*
            # disqualify an action that hasn't been tried in 5 minutes.
            attempts = list(self._attempts[key])
            recent_oldest = attempts[0][0]
            if now - recent_oldest > STAGNATION_MIN_AGE_S * 3:
                return None
            if not all(abs(d) < STAGNATION_EPSILON for _, d in attempts):
                return None
            mean_abs = sum(abs(d) for _, d in attempts) / len(attempts)
            self._removed[key] = {
                "removed_at": now,
                "reason": f"last {STAGNATION_WINDOW} attempts all |ΔSRI| < {STAGNATION_EPSILON} (mean |ΔSRI|={mean_abs:.5f})",
                "mean_abs_delta": round(mean_abs, 5),
                "cooldown_until": now + STAGNATION_COOLDOWN_S,
            }
            self._events.appendleft({
                "kind": "stagnated",
                "node": node,
                "action": action,
                "timestamp": now,
                "mean_abs_delta": round(mean_abs, 5),
                "samples": STAGNATION_WINDOW,
            })
        logger.info(
            "ActionStagnationGuard: %s @ %s removed — mean |ΔSRI|=%.5f over last %d attempts",
            action, node, mean_abs, STAGNATION_WINDOW,
        )
        return "newly_stagnant"

    # ----------------- query (called from hot paths) -----------------

    def is_blocked(self, node: str, action: str) -> bool:
        """Hot-path predicate used by HealingEngine._should_trigger and
        the LadderSynthesizer. Lock-free read of `self._removed` is safe
        for membership checks under CPython's GIL."""
        if not self.enabled:
            return False
        return (node, action) in self._removed

    def blocked_pairs_for_node(self, node: str) -> Set[str]:
        """Used by LadderSynthesizer._build_new_ladder to filter the
        synth output."""
        if not self.enabled:
            return set()
        with self.lock:
            return {a for (n, a) in self._removed if n == node}

    # ----------------- cooldown / housekeeping -----------------

    def tick(self) -> int:
        """Expire cooldowns and clear old attempt history. Returns number
        of restores performed."""
        if not self.enabled:
            return 0
        now = time.time()
        restored = 0
        with self.lock:
            expired = [k for k, v in self._removed.items()
                       if now >= v.get("cooldown_until", 0.0)]
            for key in expired:
                meta = self._removed.pop(key)
                # also wipe the attempt history so the next attempt gets a fresh
                # window — otherwise the same old zero-delta samples would
                # re-trip stagnation immediately.
                self._attempts.pop(key, None)
                self._events.appendleft({
                    "kind": "restored",
                    "node": key[0],
                    "action": key[1],
                    "timestamp": now,
                    "reason": "cooldown_expired",
                    "was_stagnant_for_s": round(now - meta.get("removed_at", now), 1),
                })
                restored += 1
            # also reap *attempt* history for pairs that haven't fired in 5 min
            stale_keys = [
                k for k, dq in self._attempts.items()
                if dq and (now - dq[-1][0]) > 300.0
            ]
            for k in stale_keys:
                if k not in self._removed:
                    self._attempts.pop(k, None)
        if restored:
            logger.info("ActionStagnationGuard: restored %d pair(s) from cooldown", restored)
        return restored

    # ----------------- admin / read API -----------------

    def force_restore(self, node: str, action: str) -> bool:
        with self.lock:
            key = (node, action)
            if key not in self._removed:
                return False
            meta = self._removed.pop(key)
            self._attempts.pop(key, None)
            self._events.appendleft({
                "kind": "restored",
                "node": node,
                "action": action,
                "timestamp": time.time(),
                "reason": "manual",
                "was_stagnant_for_s": round(time.time() - meta.get("removed_at", time.time()), 1),
            })
        return True

    def reset(self) -> int:
        with self.lock:
            n = len(self._removed)
            self._removed.clear()
            self._attempts.clear()
            self._events.appendleft({
                "kind": "reset", "timestamp": time.time(), "count": n,
            })
        return n

    def status(self) -> Dict[str, Any]:
        with self.lock:
            now = time.time()
            removed = [
                {
                    "node": n,
                    "action": a,
                    "removed_at": meta["removed_at"],
                    "cooldown_until": meta["cooldown_until"],
                    "cooldown_remaining_s": max(0.0, round(meta["cooldown_until"] - now, 1)),
                    "mean_abs_delta": meta["mean_abs_delta"],
                    "reason": meta["reason"],
                }
                for (n, a), meta in self._removed.items()
            ]
            attempts_summary = {
                f"{n}@{a}": [round(d, 5) for _, d in dq]
                for (n, a), dq in list(self._attempts.items())[:30]
            }
            return {
                "enabled": self.enabled,
                "window": STAGNATION_WINDOW,
                "epsilon": STAGNATION_EPSILON,
                "cooldown_s": STAGNATION_COOLDOWN_S,
                "min_age_s": STAGNATION_MIN_AGE_S,
                "removed": removed,
                "removed_count": len(removed),
                "attempts_tracked": len(self._attempts),
                "recent_attempts_sample": attempts_summary,
                "events": list(self._events)[:30],
            }

    def events(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._events)[:limit]


# Module-level singleton — bound by obs_server._wire_extracted_modules
guard: Optional[ActionStagnationGuard] = None


async def stagnation_guard_loop():
    logger.info("stagnation_guard_loop started")
    await asyncio.sleep(20)
    while True:
        try:
            if guard is not None:
                guard.tick()
        except Exception as e:
            logger.debug(f"stagnation_guard_loop tick: {e}")
        await asyncio.sleep(LOOP_INTERVAL_S)
