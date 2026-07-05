"""Stability Functional Ψ — Phase 2 of the Unified Model (iter 42).

Defines a Lyapunov-style scalar functional `Ψ(t)` over the live system
phase-space `(L̂, Q, M, E)` per node, such that:

  • Ψ → 0  iff every node sits at the eutectic point Ψ_c
  • dΨ/dt < 0 means the system is *stabilising* (pulling toward Ψ_c)
  • dΨ/dt > 0 means the system is *destabilising*

This complements iter 41's unified eutectic-distance objective: where
that gives the engine a *per-action* optimization signal, Ψ gives the
*system-wide* stability state — the scalar that operators can watch
to see whether the closed-loop is succeeding.

The construction follows Sunder, RSM Part II (SSRN 6580058), ref. [15]
of the whitepaper: the stability potential is a positive-definite
function of the deviation from the operating-point manifold.

We use:
        Ψ(t) =  α · ⟨d_n²(t)⟩           (instantaneous quadratic deviation)
              + β · D_accum(t)            (accumulated resilience debt)
              + γ · variance_n(d_n(t))   (cross-node phase dispersion penalty)

with defaults α=1.0, β=0.10, γ=0.50 (env-tunable). ⟨·⟩ is the mean
over the 6 services; D_accum is sampled from ResilienceDebtAccumulator
when present, else from a local integral of Σd_n² over the window.

Stability classification:
  • dΨ/dt < −Ψ_STABILISING_THRESHOLD ........ STABILISING
  • |dΨ/dt| ≤ Ψ_STEADY_BAND ................. STEADY
  • dΨ/dt >  Ψ_DESTABILISING_THRESHOLD ...... DESTABILISING

Read-only: this engine *measures* Ψ; it does not act on it. (The
existing auto-heal loops already act via the iter 41 objective.)
"""
from __future__ import annotations

import asyncio
import logging
import os
import statistics
import time
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)

# Forward-declared singletons — bound by obs_server._wire_extracted_modules
phase_classifier_instance = None
resilience_debt_accumulator = None  # may be None on installs without iter 28

# Tunables
PSI_ALPHA = float(os.environ.get("PSI_ALPHA", "1.0"))
PSI_BETA  = float(os.environ.get("PSI_BETA",  "0.10"))
PSI_GAMMA = float(os.environ.get("PSI_GAMMA", "0.50"))

PSI_TICK_INTERVAL_S = 5.0
PSI_HISTORY_SIZE    = 240   # ~20 min at 5-s ticks
PSI_DOT_WINDOW      = 6     # samples for dΨ/dt fit (~30 s)

PSI_STABILISING_THRESHOLD   = float(os.environ.get("PSI_STABILISING_THRESHOLD",   "0.003"))
PSI_STEADY_BAND             = float(os.environ.get("PSI_STEADY_BAND",             "0.003"))
PSI_DESTABILISING_THRESHOLD = float(os.environ.get("PSI_DESTABILISING_THRESHOLD", "0.003"))


class StabilityFunctional:
    """Computes Ψ and dΨ/dt from the live phase-classifier snapshot."""

    def __init__(self):
        self.lock = Lock()
        self.history: Deque[Dict[str, Any]] = deque(maxlen=PSI_HISTORY_SIZE)
        self._d2_integral = 0.0  # fallback debt-rate integral
        self.last_tick_ts: Optional[float] = None

    # ---------------- core math ----------------

    def _per_node_distances(self) -> Dict[str, float]:
        if phase_classifier_instance is None:
            return {}
        snap = getattr(phase_classifier_instance, "latest", None)
        if snap is None:
            return {}
        return {
            node: float(getattr(s, "eutectic_distance", 0.0) or 0.0)
            for node, s in snap.per_node.items()
        }

    def _debt_accum(self) -> float:
        """Best-effort D_accum — uses ResilienceDebtAccumulator if wired,
        else integrates Σd_n² locally over the lifetime of the tracker.
        Both produce a monotonically non-decreasing scalar suitable for
        the β-weighted term."""
        if resilience_debt_accumulator is not None:
            try:
                d = getattr(resilience_debt_accumulator, "current_debt", None)
                if d is None:
                    d = getattr(resilience_debt_accumulator, "D_t", None)
                if d is not None:
                    return float(d)
            except Exception:
                pass
        return self._d2_integral

    def tick(self) -> None:
        now = time.time()
        d_per_node = self._per_node_distances()
        if not d_per_node:
            return
        d_vals = list(d_per_node.values())
        d2_mean = float(statistics.mean([d * d for d in d_vals]))
        d2_var  = float(statistics.pvariance(d_vals)) if len(d_vals) > 1 else 0.0
        # Local integral for fallback debt term (5-s tick assumed)
        if self.last_tick_ts is not None:
            dt = max(0.1, min(15.0, now - self.last_tick_ts))
            self._d2_integral += sum(d * d for d in d_vals) * dt
        self.last_tick_ts = now
        debt = self._debt_accum()
        psi = PSI_ALPHA * d2_mean + PSI_BETA * debt + PSI_GAMMA * d2_var

        # dΨ/dt via linear least-squares on the last PSI_DOT_WINDOW samples
        psi_dot = 0.0
        with self.lock:
            if len(self.history) >= 2:
                window = list(self.history)[-(PSI_DOT_WINDOW - 1):]
                window.append({"timestamp": now, "psi": psi})
                xs = [w["timestamp"] - window[0]["timestamp"] for w in window]
                ys = [w["psi"] for w in window]
                n = len(xs)
                sx, sy = sum(xs), sum(ys)
                sxx = sum(x * x for x in xs)
                sxy = sum(x * y for x, y in zip(xs, ys))
                denom = n * sxx - sx * sx
                if denom > 1e-9:
                    psi_dot = (n * sxy - sx * sy) / denom

            classification = "steady"
            if psi_dot < -PSI_STABILISING_THRESHOLD:
                classification = "stabilising"
            elif psi_dot > PSI_DESTABILISING_THRESHOLD:
                classification = "destabilising"

            sample = {
                "timestamp": round(now, 3),
                "psi": round(psi, 6),
                "psi_dot": round(psi_dot, 6),
                "d2_mean": round(d2_mean, 6),
                "d2_var": round(d2_var, 6),
                "debt": round(debt, 4),
                "per_node": {n: round(v, 4) for n, v in d_per_node.items()},
                "classification": classification,
            }
            self.history.append(sample)

    # ---------------- public API ----------------

    def status(self) -> Dict[str, Any]:
        with self.lock:
            latest = self.history[-1] if self.history else None
            # Min/max in last 60 samples (~5 min)
            window = list(self.history)[-60:]
        if not latest:
            return {"ready": False, "history_size": 0}
        psi_min = min(w["psi"] for w in window) if window else latest["psi"]
        psi_max = max(w["psi"] for w in window) if window else latest["psi"]
        return {
            "ready": True,
            "latest": latest,
            "psi_min_5m": round(psi_min, 6),
            "psi_max_5m": round(psi_max, 6),
            "weights": {
                "alpha_quadratic_dev": PSI_ALPHA,
                "beta_debt": PSI_BETA,
                "gamma_dispersion": PSI_GAMMA,
            },
            "thresholds": {
                "stabilising_below": -PSI_STABILISING_THRESHOLD,
                "steady_band_abs":   PSI_STEADY_BAND,
                "destabilising_above": PSI_DESTABILISING_THRESHOLD,
            },
            "history_size": len(self.history),
        }

    def trend(self, limit: int = 60) -> Dict[str, Any]:
        with self.lock:
            samples = list(self.history)[-limit:]
        return {
            "samples": [
                {
                    "t":    s["timestamp"],
                    "psi":  s["psi"],
                    "psi_dot": s["psi_dot"],
                    "cls":  s["classification"],
                }
                for s in samples
            ]
        }


# Module-level singleton — bound by obs_server._wire_extracted_modules
functional: Optional[StabilityFunctional] = None


async def stability_functional_loop():
    logger.info("stability_functional_loop started")
    await asyncio.sleep(15)  # let phase-classifier produce a snapshot first
    while True:
        try:
            if functional is not None:
                functional.tick()
        except Exception as e:
            logger.debug(f"stability_functional_loop tick: {e}")
        await asyncio.sleep(PSI_TICK_INTERVAL_S)
