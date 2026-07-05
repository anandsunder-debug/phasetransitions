"""Economic Reliability Tracker (iter 35) — Phase 3 of the Unified-Model
visualization plan: ties resilience metrics to actual conversion-funnel
outcomes.

Implements the economic equations from Sunder's RSM paper (§14.3 of
SRI_Whitepaper):

  R_econ = W / C_T                         (Eq. 57 — value-per-cost)
  R      = W · (ΣHᵢ / Σσᵢ) / C_T           (Eq. 58 — economic resilience)
  C_T    = C_I + C_O + C_H + C_F           (Eq. 51 — total cost)

The tracker is read-only: it composes data already produced by
`BusinessMetrics`, `MetricsAggregator`, `HealingEngine.history`, and
`PhaseClassifier`. No new persistence, no new instrumentation.

W (work / business value generated per minute) — derived from
BusinessMetrics revenue_5min, normalised to /minute.

Cost decomposition (per minute, USD):
  C_I  — flat infrastructure rate from env (PHASE3_INFRA_COST_USD_PER_MIN)
  C_O  — observability cost: proxied from event rate
  C_H  — healing cost: count of healing actions in last 60s × per-action $
  C_F  — failure cost: (1 - completed_orders / projected_orders) × revenue_5min
"""
from __future__ import annotations

import logging
import os
import statistics
import time
from collections import deque
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Forward-declared singletons — bound by wire_runtime
business_metrics = None
metrics_aggregator = None
healing_engine = None
phase_classifier_instance = None


# Tunable economic constants — sane defaults so /api/economic-reliability/state
# returns meaningful values out of the box. Override via env at deploy time.
INFRA_USD_PER_MIN = float(os.environ.get("PHASE3_INFRA_COST_USD_PER_MIN", "0.30"))
HEAL_USD_PER_ACTION = float(os.environ.get("PHASE3_HEAL_COST_PER_ACTION", "0.05"))
OBS_USD_PER_KEVT = float(os.environ.get("PHASE3_OBS_USD_PER_KEVT", "0.02"))
# Scaling actions have a separate per-action cost (real infra spin-up).
SCALE_USD_PER_ACTION = float(os.environ.get("PHASE3_SCALE_COST_PER_ACTION", "0.40"))

HISTORY_SIZE = 240   # ~20 minutes at 5-s ticks
RECENT_WINDOW_S = 60


class EconomicReliabilityTracker:
    """Composes existing observables into the unified-model economic metrics."""

    def __init__(self):
        self.lock = Lock()
        self.history: deque = deque(maxlen=HISTORY_SIZE)
        # heal-saved counterfactual accumulator (rolling)
        self._counterfactual_revenue_saved = 0.0
        self.last_tick_ts: Optional[float] = None

    # ---------------- cost decomposition ----------------

    def _infra_cost(self) -> float:
        """C_I — flat / per-minute infrastructure cost."""
        return INFRA_USD_PER_MIN

    def _observability_cost(self) -> float:
        """C_O — proxied from request volume. Real systems would integrate
        log volume + trace volume + metric retention, but at our scale
        proxy = event rate × constant."""
        if metrics_aggregator is None:
            return 0.0
        try:
            golden = metrics_aggregator.get_golden_signals()
            traffic_per_s = float(golden.get("traffic", {}).get("value", 0.0))
            events_per_min = traffic_per_s * 60.0
            return (events_per_min / 1000.0) * OBS_USD_PER_KEVT
        except Exception:
            return 0.0

    def _healing_cost(self) -> float:
        """C_H — count actions in last 60 s × per-action $.
        Scaling actions cost differently from dampener actions."""
        if healing_engine is None:
            return 0.0
        try:
            hist = list(getattr(healing_engine, "history", []) or [])[-50:]
        except Exception:
            return 0.0
        now = time.time()
        cost = 0.0
        for rec in hist:
            ts_str = rec.get("timestamp")
            if not ts_str:
                continue
            try:
                from datetime import datetime
                t = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if now - t > RECENT_WINDOW_S:
                continue
            aid = rec.get("action_id", "")
            cost += SCALE_USD_PER_ACTION if aid.startswith("scale_") else HEAL_USD_PER_ACTION
        return cost

    def _failure_cost(self, w_per_min: float, funnel: Dict[str, Any]) -> float:
        """C_F — revenue lost to dropped conversion. modeled vs actual gap."""
        try:
            modeled_conv = funnel.get("modeled_conversion", {}).get("effective_conversion", 0.0)
            actual_conv = funnel.get("conversion_rates", {}).get("overall", 0.0)
        except Exception:
            return 0.0
        # If we converted at the modeled rate (= what system health *should*
        # produce), the projected revenue rate would be projected_rpm. The
        # actual is what we shipped. The gap is failure cost.
        try:
            modeled_rpm = funnel.get("modeled_conversion", {}).get("projected_revenue_per_min", 0.0)
        except Exception:
            modeled_rpm = 0.0
        gap = max(0.0, modeled_rpm - w_per_min)
        # Also account for any healing-saved revenue (counterfactual): if
        # actual conversion currently > modeled, the gap is negative — we
        # show 0 for C_F (i.e. no failure cost, we're outperforming).
        return round(gap, 3) if modeled_conv > actual_conv * 0.5 else 0.0

    # ---------------- resilience composite ----------------

    def _resilience_ratio(self) -> float:
        """R_S = ΣH / Σσ. We approximate Hᵢ = (1 + dampener_credit) since
        per-node capacity-augmenting dampeners are a measurable instance of
        healing potential. σᵢ comes directly from the phase classifier."""
        try:
            snap = getattr(phase_classifier_instance, "latest", None)
            if snap is None:
                return 1.0
            sigmas = [p.sigma for p in snap.per_node.values()]
        except Exception:
            return 1.0
        if not sigmas:
            return 1.0
        # Noise floor on σ so an idle system doesn't produce R_S → ∞.
        # 0.01 corresponds to ~1% of full saturation, well below any
        # meaningful operational stress.
        SIGMA_FLOOR = 0.01
        sigmas = [max(SIGMA_FLOOR, float(s)) for s in sigmas]
        sum_sigma = sum(sigmas) or 1e-6
        # Healing potential proxy: 1.0 / (1 + σᵢ) per node — same shape as
        # H = C/σ but with C normalised to 1 (we have no absolute capacity
        # estimate). This makes R_S a bounded, sensible quantity.
        sum_h = sum(1.0 / (1.0 + s) for s in sigmas)
        # Saturate at 100 — a perfectly idle system is "very resilient"
        # but quoting six-figure ratios is meaningless.
        return round(min(100.0, sum_h / sum_sigma), 4)

    # ---------------- tick / read api ----------------

    def tick(self) -> Optional[Dict[str, Any]]:
        if business_metrics is None:
            return None
        try:
            funnel = business_metrics.get_funnel()
        except Exception as e:
            logger.debug(f"economic_reliability tick: {e}")
            return None

        # W — business value rate (revenue per minute)
        revenue_5min = float(funnel.get("revenue_5min", 0.0))
        w_per_min = revenue_5min / 5.0 if revenue_5min else 0.0

        # Cost decomposition
        c_i = self._infra_cost()
        c_o = self._observability_cost()
        c_h = self._healing_cost()
        c_f = self._failure_cost(w_per_min, funnel)
        c_t = c_i + c_o + c_h + c_f or 1e-6

        # Resilience ratio composite
        r_s = self._resilience_ratio()

        # Headline economic metrics
        r_econ = round(w_per_min / c_t, 4) if c_t > 0 else 0.0
        r_econ_resilience = round(w_per_min * r_s / c_t, 4) if c_t > 0 else 0.0

        # Counterfactual revenue saved by healing in the last 60s. We use
        # the modeled vs actual delta inverted: when actual > modeled
        # (i.e. healing pulled us up), we credit that delta × actual rpm.
        try:
            modeled_conv = funnel.get("modeled_conversion", {}).get("effective_conversion", 0.0)
            actual_conv = funnel.get("conversion_rates", {}).get("overall", 0.0)
            avg_order = 25.0
            traffic = float(metrics_aggregator.get_golden_signals().get("traffic", {}).get("value", 0.0))
            uplift = max(0.0, actual_conv - modeled_conv)
            heal_saved_per_min = uplift * traffic * 60.0 * avg_order
        except Exception:
            heal_saved_per_min = 0.0

        sample = {
            "timestamp": time.time(),
            "w_per_min": round(w_per_min, 3),
            "revenue_5min": revenue_5min,
            "total_revenue": float(funnel.get("total_revenue", 0.0)),
            "cost_decomposition": {
                "C_I": round(c_i, 3),
                "C_O": round(c_o, 3),
                "C_H": round(c_h, 3),
                "C_F": round(c_f, 3),
                "C_T": round(c_t, 3),
            },
            "resilience_ratio_R_S": r_s,
            "R_econ": r_econ,
            "R_econ_resilience": r_econ_resilience,
            "heal_saved_per_min_usd": round(heal_saved_per_min, 3),
            "funnel_conversion_overall": funnel.get("conversion_rates", {}).get("overall", 0.0),
            "funnel_orders": funnel.get("orders_completed", 0),
        }
        with self.lock:
            self.history.append(sample)
            self.last_tick_ts = sample["timestamp"]
            # rolling counterfactual: integrate per-tick over 12 ticks (1 min)
            self._counterfactual_revenue_saved = round(
                statistics.fmean(
                    s["heal_saved_per_min_usd"] for s in list(self.history)[-12:]
                ) if self.history else 0.0,
                3,
            )
        return sample

    def status(self) -> Dict[str, Any]:
        with self.lock:
            latest = self.history[-1] if self.history else None
            return {
                "ready": latest is not None,
                "latest": latest,
                "counterfactual_revenue_saved_per_min": self._counterfactual_revenue_saved,
                "constants": {
                    "infra_usd_per_min": INFRA_USD_PER_MIN,
                    "heal_usd_per_action": HEAL_USD_PER_ACTION,
                    "scale_usd_per_action": SCALE_USD_PER_ACTION,
                    "obs_usd_per_kevt": OBS_USD_PER_KEVT,
                },
                "history_size": len(self.history),
            }

    def trend(self, limit: int = 60) -> Dict[str, Any]:
        with self.lock:
            samples = list(self.history)[-limit:]
        return {
            "samples": [
                {
                    "t": s["timestamp"],
                    "W": s["w_per_min"],
                    "C_T": s["cost_decomposition"]["C_T"],
                    "R_econ": s["R_econ"],
                    "R_econ_resilience": s["R_econ_resilience"],
                    "R_S": s["resilience_ratio_R_S"],
                    "conv": s["funnel_conversion_overall"],
                }
                for s in samples
            ],
        }


# Module-level singleton — bound by obs_server._wire_extracted_modules
tracker: Optional[EconomicReliabilityTracker] = None


import asyncio  # noqa: E402

async def economic_reliability_loop():
    logger.info("economic_reliability_loop started")
    await asyncio.sleep(20)
    while True:
        try:
            if tracker is not None:
                tracker.tick()
        except Exception as e:
            logger.debug(f"economic_reliability_loop tick: {e}")
        await asyncio.sleep(5)
