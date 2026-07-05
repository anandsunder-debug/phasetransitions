"""Tracker classes — Phase 2 physical extraction (iter 28).

Originally lived in `obs_server.py`. These classes have no dependencies on
any module-level singleton (metrics_aggregator, healing_engine, etc.)
defined *after* their own class definition in obs_server.py — except for
MetricsAggregator's reference to PERMANENT_FIX_REGISTRY, which is
late-imported inside the relevant method.

The classes are pure in-memory state holders / math computations.

Re-exported via obs.trackers.__init__:

    from obs.trackers import MetricsAggregator, SRIInterpolator, ...
"""
from __future__ import annotations

import os
import time
import logging
import random
import asyncio
import math
import secrets
import statistics
import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import httpx

logger = logging.getLogger(__name__)


class MetricsAggregator:
    def __init__(self):
        self.lock = Lock()
        self.window_size = 30  # 30 second rolling window (faster SRI response)
        self.metrics = defaultdict(lambda: {
            "requests": [],
            "latencies": [],
            "errors": [],
            "timestamps": []
        })
        # SRI Baseline calibration
        self.baseline_sri = 0.85  # Target healthy SRI
        self.warmup_complete = False
        self.warmup_requests = 0
        self.warmup_target = 10  # Requests needed before real SRI kicks in
        # Golden Signals tracking (system-wide)
        self.golden_signals_history = []  # [{timestamp, latency, traffic, errors, saturation}]
        # Customer Experience tracking
        self.all_latencies = []  # All raw latencies for percentile calc
        self.total_requests = 0
        self.total_errors = 0
        self.apdex_satisfied = 0  # < 200ms
        self.apdex_tolerating = 0  # 200ms - 800ms
        self.apdex_frustrated = 0  # > 800ms
        self.availability_checks = 0
        self.availability_ok = 0
        self.cx_start_time = time.time()
        # Correction factor tracking
        self.correction_history = []
        # HEALING DAMPENER: per-node dampening from corrective actions
        self.healing_dampeners = {}
        # CAPACITY BOOSTS: per-node multiplier on the effective capacity
        # denominator. Driven by scale_out_* actions — fixes the
        # "yielding state" where scaling actions fired but saturation
        # stayed pinned at 1.0 because the capacity denominator was
        # hard-coded. {node: {"multiplier": float, "expires": ts}}.
        self.capacity_boosts = {}
        self.CAPACITY_BOOST_CEILING = 8.0  # don't let scale-out compound past 8×

    def apply_dampener(self, node: str, latency_factor: float, error_suppression: float, duration: float = 20.0):
        """Apply a healing dampener to a node. Future requests get latency
        multiplied by factor and errors suppressed for `duration` seconds.
        This models the infrastructure actually being healthier post-CA."""
        self.healing_dampeners[node] = {
            "latency_factor": latency_factor,
            "error_suppression": error_suppression,
            "expires": time.time() + duration,
        }

    def apply_capacity_boost(self, node: str, multiplier: float, duration: float = 120.0):
        """Increase a node's effective request-capacity denominator for
        `duration` seconds — models scale-out actions actually adding
        replicas. Compounds multiplicatively within the persistence
        window, capped at `CAPACITY_BOOST_CEILING` to prevent runaway
        scaling thrash. multiplier must be ≥ 1.0."""
        if multiplier < 1.0:
            return
        now = time.time()
        existing = self.capacity_boosts.get(node)
        if existing and existing["expires"] > now:
            new_mult = min(existing["multiplier"] * multiplier, self.CAPACITY_BOOST_CEILING)
        else:
            new_mult = min(multiplier, self.CAPACITY_BOOST_CEILING)
        self.capacity_boosts[node] = {
            "multiplier": new_mult,
            "expires": now + duration,
        }

    def apply_capacity_drain(self, node: str, drain_factor: float, duration: float = 120.0):
        """Reduce a node's active capacity boost — models scale-in actions
        removing replicas. drain_factor in (0.0, 1.0): the active
        multiplier is scaled by drain_factor. If the resulting multiplier
        drops below 1.05 the boost entry is cleared entirely (a single
        replica is the baseline, no boost needed). Refreshes TTL so the
        scaled-in state persists for `duration` seconds. No-op when no
        boost is currently active (you can't scale in below baseline)."""
        if not (0.0 < drain_factor < 1.0):
            return
        now = time.time()
        existing = self.capacity_boosts.get(node)
        if not existing or existing["expires"] <= now:
            # nothing to drain — node is already at baseline capacity
            return
        new_mult = existing["multiplier"] * drain_factor
        if new_mult < 1.05:
            del self.capacity_boosts[node]
        else:
            self.capacity_boosts[node] = {
                "multiplier": new_mult,
                "expires": now + duration,
            }

    def get_capacity_boost(self, node: str) -> float:
        """Return the active capacity multiplier for `node` (≥ 1.0).
        Expired boosts are returned as 1.0 and cleaned lazily."""
        boost = self.capacity_boosts.get(node)
        if not boost:
            return 1.0
        if boost["expires"] <= time.time():
            del self.capacity_boosts[node]
            return 1.0
        return float(boost["multiplier"])
        
    def record(self, node: str, latency: float, is_error: bool):
        with self.lock:
            now = time.time()
            
            # Apply healing dampener if active (simulates improved infra)
            dampener = self.healing_dampeners.get(node)
            if dampener and dampener["expires"] > now:
                latency = latency * dampener["latency_factor"]
                if is_error and random.random() < dampener["error_suppression"]:
                    is_error = False
            elif dampener:
                del self.healing_dampeners[node]
            self.metrics[node]["requests"].append(1)
            self.metrics[node]["latencies"].append(latency)
            self.metrics[node]["errors"].append(1 if is_error else 0)
            self.metrics[node]["timestamps"].append(now)
            
            # Track CX metrics
            self.total_requests += 1
            self.total_errors += int(is_error)
            latency_ms = latency * 1000
            self.all_latencies.append(latency_ms)
            if len(self.all_latencies) > 5000:
                self.all_latencies = self.all_latencies[-5000:]
            
            # Apdex scoring (T=200ms)
            if latency_ms < 200:
                self.apdex_satisfied += 1
            elif latency_ms < 800:
                self.apdex_tolerating += 1
            else:
                self.apdex_frustrated += 1
            
            # Availability
            self.availability_checks += 1
            if not is_error:
                self.availability_ok += 1
            
            # Warmup tracking
            self.warmup_requests += 1
            if self.warmup_requests >= self.warmup_target:
                self.warmup_complete = True
            
            # Clean old data
            cutoff = now - self.window_size
            for key in ["requests", "latencies", "errors", "timestamps"]:
                data = self.metrics[node][key]
                timestamps = self.metrics[node]["timestamps"]
                while timestamps and timestamps[0] < cutoff:
                    for k in ["requests", "latencies", "errors", "timestamps"]:
                        if self.metrics[node][k]:
                            self.metrics[node][k].pop(0)
                    if not timestamps:
                        break
    
    def get_node_metrics(self, node: str) -> Dict:
        with self.lock:
            data = self.metrics[node]
            if not data["requests"]:
                return {"traffic": 0, "latency": 0, "error": 0, "saturation": 0}
            
            traffic = len(data["requests"])
            avg_latency = sum(data["latencies"]) / len(data["latencies"]) if data["latencies"] else 0
            error_rate = sum(data["errors"]) / len(data["errors"]) if data["errors"] else 0
            # Capacity boost from scale-out actions (≥ 1.0). Treats added
            # replicas as a multiplier on the effective request-capacity
            # denominator and applies a queueing-theoretic latency divisor
            # (M/M/c ≈ 1/c steady-state delay for the congested term).
            boost = self.get_capacity_boost(node)
            effective_cap = 100.0 * boost
            saturation = min(traffic / effective_cap, 1.0)
            if boost > 1.0:
                avg_latency = avg_latency / boost

            # Apply persistent fixes ("stiffness boost") from PermanentFunnelHealer.
            # Each fix attenuates latency / error / saturation by a multiplier that
            # decays over time (since the underlying root-cause was already removed,
            # the boost is just bookkeeping to reflect ongoing benefit).
            try:
                from obs_server import PERMANENT_FIX_REGISTRY  # late-import: defined after this module loads
                node_fixes = PERMANENT_FIX_REGISTRY.get(node, {})
                for sig, mult in node_fixes.items():
                    m = max(0.0, min(1.0, float(mult)))
                    if sig == "latency":
                        avg_latency *= (1 - 0.6 * m)
                    elif sig == "errors":
                        error_rate *= (1 - 0.7 * m)
                    elif sig == "saturation":
                        saturation *= (1 - 0.5 * m)
            except Exception:
                pass

            return {
                "traffic": traffic,
                "latency": avg_latency * 1000,  # Convert to ms
                "error": error_rate,
                "saturation": saturation
            }
    
    def get_all_metrics(self) -> Dict[str, Dict]:
        nodes = ["API", "Cache", "DB", "Queue", "Backend", "Frontend"]
        result = {}
        for node in nodes:
            result[node] = self.get_node_metrics(node)
        return result

    def get_golden_signals(self) -> Dict:
        """Compute the 4 Golden Signals (Google SRE) from current metrics"""
        node_metrics = self.get_all_metrics()
        all_traffic = sum(m["traffic"] for m in node_metrics.values())
        all_latencies = [m["latency"] for m in node_metrics.values() if m["traffic"] > 0]
        all_errors = [m["error"] for m in node_metrics.values() if m["traffic"] > 0]
        all_saturation = [m["saturation"] for m in node_metrics.values()]
        
        avg_latency = np.mean(all_latencies) if all_latencies else 0
        avg_error = np.mean(all_errors) if all_errors else 0
        avg_saturation = np.mean(all_saturation) if all_saturation else 0
        
        # Per-signal health score (0-1, higher is better)
        latency_health = max(0, 1 - (avg_latency / 500))  # 500ms = 0 health
        traffic_health = min(all_traffic / 20, 1.0) if all_traffic > 0 else 0  # Need at least 20 req
        error_health = max(0, 1 - (avg_error / 0.2))  # 20% errors = 0 health
        saturation_health = max(0, 1 - (avg_saturation / 1.0))
        
        return {
            "latency": {"value": round(avg_latency, 2), "health": round(latency_health, 4), "unit": "ms", "threshold": 200},
            "traffic": {"value": all_traffic, "health": round(traffic_health, 4), "unit": "req/min", "threshold": 20},
            "errors": {"value": round(avg_error * 100, 2), "health": round(error_health, 4), "unit": "%", "threshold": 10},
            "saturation": {"value": round(avg_saturation * 100, 2), "health": round(saturation_health, 4), "unit": "%", "threshold": 80}
        }

    def get_customer_experience(self) -> Dict:
        """Compute customer experience metrics"""
        with self.lock:
            total_apdex = self.apdex_satisfied + self.apdex_tolerating + self.apdex_frustrated
            apdex = ((self.apdex_satisfied + (self.apdex_tolerating * 0.5)) / max(total_apdex, 1))
            
            sorted_lat = sorted(self.all_latencies) if self.all_latencies else [0]
            p50 = sorted_lat[int(len(sorted_lat) * 0.5)] if sorted_lat else 0
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
            p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0
            
            availability = (self.availability_ok / max(self.availability_checks, 1)) * 100
            
            # Error budget: SLO of 99.5% availability
            slo_target = 99.5
            error_budget_total = 100 - slo_target  # 0.5%
            error_budget_consumed = max(0, 100 - availability)
            error_budget_remaining = max(0, error_budget_total - error_budget_consumed)
            error_budget_pct = (error_budget_remaining / error_budget_total) * 100 if error_budget_total > 0 else 100
            
            uptime_seconds = time.time() - self.cx_start_time
            
            return {
                "apdex": round(apdex, 4),
                "apdex_label": "Excellent" if apdex >= 0.94 else "Good" if apdex >= 0.85 else "Fair" if apdex >= 0.7 else "Poor" if apdex >= 0.5 else "Unacceptable",
                "p50": round(p50, 1),
                "p95": round(p95, 1),
                "p99": round(p99, 1),
                "availability": round(availability, 3),
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "error_budget": {
                    "slo": slo_target,
                    "total": round(error_budget_total, 2),
                    "consumed": round(error_budget_consumed, 3),
                    "remaining": round(error_budget_remaining, 3),
                    "remaining_pct": round(error_budget_pct, 1)
                },
                "uptime_seconds": int(uptime_seconds),
                "satisfied": self.apdex_satisfied,
                "tolerating": self.apdex_tolerating,
                "frustrated": self.apdex_frustrated
            }

class SRIInterpolator:
    """Tracks SRI over time and uses polynomial interpolation to compute
    velocity (dSRI/dt), acceleration (d²SRI/dt²), and predicted future SRI.
    Drives urgency classification for the FEA-based healing engine."""

    def __init__(self, max_samples=200):
        self.lock = Lock()
        self.timestamps = []   # epoch seconds
        self.values = []       # SRI values
        self.max_samples = max_samples

    def record(self, sri: float, ts: float = None):
        with self.lock:
            t = ts or time.time()
            self.timestamps.append(t)
            self.values.append(sri)
            if len(self.timestamps) > self.max_samples:
                self.timestamps = self.timestamps[-self.max_samples:]
                self.values = self.values[-self.max_samples:]

    def analyze(self) -> Dict:
        """Interpolate SRI trend using quadratic polynomial fit.
        Returns velocity, acceleration, predicted SRI, and trend label."""
        with self.lock:
            n = len(self.values)
            if n < 3:
                return {
                    "velocity": 0, "acceleration": 0,
                    "predicted_30s": self.values[-1] if self.values else 0.85,
                    "predicted_60s": self.values[-1] if self.values else 0.85,
                    "trend": "insufficient_data", "samples": n,
                    "current_sri": self.values[-1] if self.values else 0.85,
                    "non_recoverable": False,
                    "non_recoverable_criterion": {
                        "plateau": False, "plateau_eps": 0.0008,
                        "sustained_below_threshold": False, "sri_threshold": 0.3,
                    },
                }

            # Normalise timestamps relative to most recent sample
            t0 = self.timestamps[-1]
            t_rel = np.array([t - t0 for t in self.timestamps])
            v = np.array(self.values)

            # Quadratic fit: SRI(t) = a*t² + b*t + c
            try:
                coeffs = np.polyfit(t_rel, v, deg=min(2, n - 1))
                poly = np.poly1d(coeffs)
                dpoly = poly.deriv(1)   # velocity polynomial
                ddpoly = poly.deriv(2)  # acceleration polynomial

                velocity = float(dpoly(0))        # dSRI/dt at t=0 (now)
                acceleration = float(ddpoly(0))    # d²SRI/dt² at t=0
                pred_30 = float(np.clip(poly(30), 0, 1))
                pred_60 = float(np.clip(poly(60), 0, 1))
            except Exception:
                velocity, acceleration = 0, 0
                pred_30 = pred_60 = self.values[-1]

            # Trend classification
            if velocity < -0.005 and acceleration < -0.0001:
                trend = "critical_degrading"
            elif velocity < -0.002:
                trend = "degrading"
            elif velocity > 0.002:
                trend = "recovering"
            else:
                trend = "stable"

            # Non-recoverable state detector (Eq. 7 from SRI/SAI paper):
            #   d(SRI)/dt ≈ 0  ∧  SRI < SRI_threshold
            # We also require the condition to have held for ≥3 of the most
            # recent samples to avoid transient false positives.
            current_sri = self.values[-1]
            plateau_eps = 0.0008
            sri_floor = 0.3
            recent = self.values[-min(5, n):]
            plateau = abs(velocity) < plateau_eps
            sustained_low = all(v < sri_floor for v in recent[-3:]) if len(recent) >= 3 else False
            non_recoverable = bool(plateau and sustained_low and current_sri < sri_floor)

            return {
                "velocity": round(velocity, 6),
                "acceleration": round(acceleration, 8),
                "predicted_30s": round(pred_30, 4),
                "predicted_60s": round(pred_60, 4),
                "trend": trend,
                "samples": n,
                "current_sri": round(current_sri, 4),
                "non_recoverable": non_recoverable,
                "non_recoverable_criterion": {
                    "plateau": plateau,
                    "plateau_eps": plateau_eps,
                    "sustained_below_threshold": sustained_low,
                    "sri_threshold": sri_floor,
                },
            }

class ResilienceDebtAccumulator:
    """Cumulative resilience debt: E(t) = ∫₀ᵗ Φ(t) dt.

    Implements the Unified-View paper's energy/cost model:
      • Φ = xᵀLx  (stability potential — already produced by the topology engine)
      • E       = time-integrated Φ  (total "energy" / "operational cost")
      • Cost    ∝ 1/SRI  (inverse-resilience cost proxy)

    We expose this so the dashboard can show a $-saved value after each
    healing action (the area under the Φ curve that didn't accumulate).
    """

    def __init__(self, cost_per_phi_sec: float = 0.05):
        self._lock = Lock()
        self._E = 0.0          # cumulative ∫Φ dt
        self._cost_total = 0.0 # cumulative 1/SRI integrated → cost units
        self._last_t: Optional[float] = None
        self._last_phi = 0.0
        self._last_sri = 1.0
        self._samples = 0
        self.cost_per_phi_sec = cost_per_phi_sec  # tuning constant
        # iter 43 — history for D(t) integral-curve plotting on the
        # ResilienceDebtCard. Each entry is (t, Φ, E, cost). 720 samples
        # ≈ 1 hour at the 5-s tick cadence used by upstream pollers.
        from collections import deque
        self._history: "deque[Dict]" = deque(maxlen=720)

    def record(self, phi: float, sri: float, ts: Optional[float] = None) -> None:
        now = ts or time.time()
        with self._lock:
            if self._last_t is not None:
                dt = max(0.0, now - self._last_t)
                # Trapezoidal rule for both integrals
                self._E += 0.5 * (self._last_phi + max(0.0, phi)) * dt
                inv_sri_now = 1.0 / max(sri, 1e-3)
                inv_sri_prev = 1.0 / max(self._last_sri, 1e-3)
                self._cost_total += 0.5 * (inv_sri_prev + inv_sri_now) * dt * self.cost_per_phi_sec
            self._last_t = now
            self._last_phi = max(0.0, phi)
            self._last_sri = max(sri, 1e-3)
            self._samples += 1
            # iter 43 — append history sample for the D(t) integral curve
            self._history.append({
                "t": round(now, 3),
                "phi": round(self._last_phi, 6),
                "E":   round(self._E, 6),
                "cost":round(self._cost_total, 4),
                "sri": round(self._last_sri, 4),
            })

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "energy_integral_phi": round(self._E, 6),
                "cost_total_usd": round(self._cost_total, 4),
                "current_phi": round(self._last_phi, 6),
                "current_sri": round(self._last_sri, 4),
                "instantaneous_cost_per_sec": round(self.cost_per_phi_sec / max(self._last_sri, 1e-3), 4),
                "samples": self._samples,
                "cost_per_phi_sec": self.cost_per_phi_sec,
                "interpretation": (
                    "E = ∫₀ᵗ Φ(t) dt is the cumulative system imbalance ('resilience debt'). "
                    "Cost ∝ 1/SRI per Unified-View paper — every drop in SRI raises operational cost."
                ),
            }

    def history(self, limit: int = 240) -> Dict:
        """iter 43 — return the last `limit` samples for plotting the
        D(t) integral curve + Φ(t) instantaneous-debt-rate curve."""
        with self._lock:
            samples = list(self._history)[-limit:]
        return {"samples": samples}

class CorrelationTracker:
    """Time-aligned sampler of (SRI, conversion_rate, latency, error) for the
    Reliability ↔ Business correlation chart. Demonstrates the central thesis
    of the SRI papers: as infrastructure resilience improves, business
    conversion follows.
    """

    def __init__(self, max_samples: int = 600):
        self._lock = Lock()
        self._samples: List[Dict] = []  # [{t, sri, conversion, latency_ms, error_pct}]
        self.max_samples = max_samples
        # Healing-action annotations: [{t, action_id, sri_before, sri_after, target_node}]
        self._annotations: List[Dict] = []

    def record(self, sri: float, conversion: float, latency_ms: float, error_pct: float, ts: Optional[float] = None) -> None:
        now = ts or time.time()
        with self._lock:
            self._samples.append({
                "t": now,
                "sri": float(sri),
                "conversion": float(conversion),
                "latency_ms": float(latency_ms),
                "error_pct": float(error_pct),
            })
            if len(self._samples) > self.max_samples:
                self._samples = self._samples[-self.max_samples:]

    def annotate_healing(self, action_id: str, sri_before: float, sri_after: float, target_node: str = "") -> None:
        with self._lock:
            self._annotations.append({
                "t": time.time(),
                "action_id": action_id,
                "sri_before": float(sri_before),
                "sri_after": float(sri_after),
                "sri_delta": round(float(sri_after - sri_before), 4),
                "target_node": target_node,
            })
            if len(self._annotations) > 200:
                self._annotations = self._annotations[-200:]

    def snapshot(self, window_seconds: int = 300) -> Dict:
        with self._lock:
            now = time.time()
            cutoff = now - window_seconds
            recent = [s for s in self._samples if s["t"] >= cutoff]
            recent_anns = [a for a in self._annotations if a["t"] >= cutoff]
            n = len(recent)
            if n < 3:
                return {
                    "window_seconds": window_seconds,
                    "samples": n,
                    "series": recent,
                    "pearson_r": None,
                    "interpretation": "Insufficient samples — generate traffic to populate the correlation.",
                    "annotations": [
                        {**a, "t_relative": round(a["t"] - now, 2)} for a in recent_anns
                    ],
                }
            sri_arr = np.array([s["sri"] for s in recent])
            conv_arr = np.array([s["conversion"] for s in recent])
            # Pearson correlation
            try:
                if sri_arr.std() > 1e-9 and conv_arr.std() > 1e-9:
                    r = float(np.corrcoef(sri_arr, conv_arr)[0, 1])
                else:
                    r = 0.0
            except Exception:
                r = 0.0

            interp = "SRI and conversion track tightly — infra health drives revenue." if r > 0.5 else (
                "Weak coupling — bottleneck may be elsewhere (UX, pricing, traffic mix)." if r < 0.2 else
                "Moderate coupling — partial business impact from infra resilience."
            )
            return {
                "window_seconds": window_seconds,
                "samples": n,
                "series": [
                    {
                        "t": round(s["t"] - now, 2),  # relative seconds, negative
                        "absolute_t": s["t"],
                        "sri": round(s["sri"], 4),
                        "conversion": round(s["conversion"], 6),
                        "latency_ms": round(s["latency_ms"], 1),
                        "error_pct": round(s["error_pct"], 3),
                    } for s in recent
                ],
                "pearson_r": round(r, 4),
                "annotations": [
                    {**a, "t_relative": round(a["t"] - now, 2)} for a in recent_anns
                ],
                "interpretation": interp,
                "current": {
                    "sri": round(sri_arr[-1], 4),
                    "conversion": round(conv_arr[-1], 6),
                    "sri_min": round(float(sri_arr.min()), 4),
                    "sri_max": round(float(sri_arr.max()), 4),
                    "conversion_min": round(float(conv_arr.min()), 6),
                    "conversion_max": round(float(conv_arr.max()), 6),
                },
            }

class AutoPropagationDetector:
    """Background watcher that detects natural failure propagations.

    Every `interval_sec` it scans node metrics for *stressed* services
    (composite pressure > yield threshold OR rising trend), runs the
    Laplacian propagation simulator, and stores the active propagations.
    Optionally fires autonomous healing along the predicted path.
    """

    def __init__(self):
        self._lock = Lock()
        self._active: Dict[str, Dict] = {}      # source -> propagation snapshot
        self._history: List[Dict] = []           # last 30 detections
        self.enabled: bool = True
        self.autonomous_heal: bool = True        # auto-execute path-based healing
        self.interval_sec: int = 8
        self.stress_pressure_threshold: float = 0.005   # composite stress trigger
        self.detection_count: int = 0
        self.last_run_at: Optional[float] = None

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "enabled": self.enabled,
                "autonomous_heal": self.autonomous_heal,
                "interval_sec": self.interval_sec,
                "stress_pressure_threshold": self.stress_pressure_threshold,
                "active": list(self._active.values()),
                "detection_count": self.detection_count,
                "last_run_at": self.last_run_at,
                "recent_history": self._history[-10:],
            }

    def set_config(self, enabled: Optional[bool] = None, autonomous_heal: Optional[bool] = None,
                   interval_sec: Optional[int] = None, threshold: Optional[float] = None) -> Dict:
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)
            if autonomous_heal is not None:
                self.autonomous_heal = bool(autonomous_heal)
            if interval_sec is not None:
                self.interval_sec = max(3, min(60, int(interval_sec)))
            if threshold is not None:
                self.stress_pressure_threshold = max(0.001, min(1.0, float(threshold)))
        return self.snapshot()

class SRIAttributionEngine:
    """Decomposes SRI dips into per-signal, per-node attributions.
    Maps infrastructure degradation to business impact.
    This is the 'emergent intelligence' — connecting resilience to reliability."""

    # How each signal impacts business metrics (empirical weights)
    SIGNAL_BUSINESS_IMPACT = {
        "latency": {"conversion": 0.4, "apdex": 0.6, "revenue": 0.3},
        "errors": {"conversion": 0.7, "apdex": 0.5, "revenue": 0.6},
        "saturation": {"conversion": 0.2, "apdex": 0.3, "revenue": 0.1},
    }

    def attribute_dip(self, node_metrics: Dict, sri_data: Dict, golden: Dict) -> Dict:
        """Decompose current SRI state into per-node, per-signal attributions.
        Returns which signal on which node is most responsible for the dip
        AND what business metric it's most likely hurting."""

        nodes = list(node_metrics.keys())
        signal_contributions = sri_data.get("signal_contributions", {})

        # Per-node signal breakdown
        node_attributions = []
        for node_name in nodes:
            m = node_metrics.get(node_name, {})
            traffic_share = m.get("traffic", 0) / max(sum(nm.get("traffic", 0) for nm in node_metrics.values()), 1)

            lat_impact = min(m.get("latency", 0) / 200.0, 1.0) * traffic_share
            err_impact = min(m.get("error", 0) / 0.15, 1.0) * traffic_share
            sat_impact = m.get("saturation", 0) * traffic_share

            total_impact = lat_impact * 0.3 + err_impact * 0.45 + sat_impact * 0.25

            # Which business metric is this node most hurting?
            biz_impact = {}
            for biz_metric in ["conversion", "apdex", "revenue"]:
                impact = (lat_impact * self.SIGNAL_BUSINESS_IMPACT["latency"][biz_metric] +
                          err_impact * self.SIGNAL_BUSINESS_IMPACT["errors"][biz_metric] +
                          sat_impact * self.SIGNAL_BUSINESS_IMPACT["saturation"][biz_metric])
                biz_impact[biz_metric] = round(impact, 4)

            node_attributions.append({
                "node": node_name,
                "total_attribution": round(total_impact, 4),
                "signal_breakdown": {
                    "latency": round(lat_impact, 4),
                    "errors": round(err_impact, 4),
                    "saturation": round(sat_impact, 4),
                },
                "business_impact": biz_impact,
                "dominant_signal": max({"latency": lat_impact, "errors": err_impact, "saturation": sat_impact}, key=lambda k: {"latency": lat_impact, "errors": err_impact, "saturation": sat_impact}[k]),
                "dominant_business_metric": max(biz_impact, key=biz_impact.get),
            })

        node_attributions.sort(key=lambda x: -x["total_attribution"])

        # Global signal attribution
        total_lat = sum(a["signal_breakdown"]["latency"] for a in node_attributions)
        total_err = sum(a["signal_breakdown"]["errors"] for a in node_attributions)
        total_sat = sum(a["signal_breakdown"]["saturation"] for a in node_attributions)
        total_all = total_lat + total_err + total_sat or 1

        return {
            "node_attributions": node_attributions,
            "global_signal_share": {
                "latency": round(total_lat / total_all, 4),
                "errors": round(total_err / total_all, 4),
                "saturation": round(total_sat / total_all, 4),
            },
            "primary_root_cause": node_attributions[0] if node_attributions else None,
            "sri_signal_contributions": signal_contributions,
            "healing_priority": {
                "target_node": node_attributions[0]["node"] if node_attributions else None,
                "target_signal": node_attributions[0]["dominant_signal"] if node_attributions else None,
                "business_justification": node_attributions[0]["dominant_business_metric"] if node_attributions else None,
            },
        }

class WebhookNotifier:
    """Fire-and-forget webhook notifier for critical SRI alerts.

    Reads SLACK_WEBHOOK_URL and DISCORD_WEBHOOK_URL from env. If neither is set,
    silently no-ops. Deduplicates per-alert-key with a cooldown so a sustained
    critical condition doesn't spam channels.
    """

    def __init__(self):
        self.slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        self.discord_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        self.cooldown_sec = int(os.environ.get("WEBHOOK_COOLDOWN_SEC", "120"))
        self._last_sent: Dict[str, datetime] = {}
        self._lock = Lock()

    def is_configured(self) -> Dict[str, bool]:
        return {"slack": bool(self.slack_url), "discord": bool(self.discord_url)}

    def _can_send(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            last = self._last_sent.get(key)
            if last and (now - last).total_seconds() < self.cooldown_sec:
                return False
            self._last_sent[key] = now
            return True

    @staticmethod
    def _slack_payload(alert: dict) -> dict:
        severity = alert.get("type", "info").upper()
        emoji = {"CRITICAL": ":rotating_light:", "WARNING": ":warning:"}.get(severity, ":information_source:")
        fields = [
            {"title": "Category", "value": alert.get("category", "-"), "short": True},
            {"title": "Value", "value": f'{alert.get("value", 0):.4f}', "short": True},
            {"title": "Threshold", "value": f'{alert.get("threshold", 0):.4f}', "short": True},
            {"title": "Action", "value": alert.get("action", "-"), "short": False},
        ]
        if alert.get("node"):
            fields.insert(0, {"title": "Node", "value": alert["node"], "short": True})
        return {
            "text": f'{emoji} *{severity}* — {alert.get("title", "SRI Alert")}',
            "attachments": [{
                "color": "#FF3B30" if severity == "CRITICAL" else "#FFCC00",
                "text": alert.get("message", ""),
                "fields": fields,
                "footer": "FreshCart SRI Engine",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }],
        }

    @staticmethod
    def _discord_payload(alert: dict) -> dict:
        severity = alert.get("type", "info").upper()
        color = 0xFF3B30 if severity == "CRITICAL" else 0xFFCC00
        fields = [
            {"name": "Category", "value": str(alert.get("category", "-")), "inline": True},
            {"name": "Value", "value": f'{alert.get("value", 0):.4f}', "inline": True},
            {"name": "Threshold", "value": f'{alert.get("threshold", 0):.4f}', "inline": True},
            {"name": "Action", "value": alert.get("action", "-"), "inline": False},
        ]
        if alert.get("node"):
            fields.insert(0, {"name": "Node", "value": str(alert["node"]), "inline": True})
        return {
            "username": "FreshCart SRI Engine",
            "embeds": [{
                "title": f'[{severity}] {alert.get("title", "SRI Alert")}',
                "description": alert.get("message", ""),
                "color": color,
                "fields": fields,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }],
        }

    async def _post(self, url: str, payload: dict, label: str) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(url, json=payload)
                ok = 200 <= r.status_code < 300
                if not ok:
                    logger.warning(f"{label} webhook failed status={r.status_code} body={r.text[:200]}")
                return {"ok": ok, "status": r.status_code}
        except Exception as e:
            logger.warning(f"{label} webhook error: {e}")
            return {"ok": False, "error": str(e)}

    async def dispatch(self, alert: dict, force: bool = False) -> Dict[str, Dict]:
        """Send alert to configured webhooks. Only CRITICAL by default.

        `force=True` bypasses both the severity filter and the cooldown (used by
        the admin "test webhook" button).
        """
        severity = alert.get("type", "").lower()
        if not force and severity != "critical":
            return {"skipped": True, "reason": "not_critical"}

        key = alert.get("id") or alert.get("category") or "generic"
        if not force and not self._can_send(key):
            return {"skipped": True, "reason": "cooldown"}

        results: Dict[str, Dict] = {}
        if self.slack_url:
            results["slack"] = await self._post(self.slack_url, self._slack_payload(alert), "Slack")
        if self.discord_url:
            results["discord"] = await self._post(self.discord_url, self._discord_payload(alert), "Discord")
        if not results:
            return {"skipped": True, "reason": "no_webhook_configured"}
        return results

class HealingAction:
    def __init__(self, action_id: str, name: str, target_node: str, description: str,
                 trigger_condition: str, effect_description: str, sri_impact: float,
                 cooldown: int = 120):
        self.action_id = action_id
        self.name = name
        self.target_node = target_node
        self.description = description
        self.trigger_condition = trigger_condition
        self.effect_description = effect_description
        self.sri_impact = sri_impact  # estimated SRI improvement (0.0 to 0.5)
        self.cooldown = cooldown
        self.last_executed = None
        self.execution_count = 0

    def can_execute(self) -> bool:
        if self.last_executed is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_executed).total_seconds()
        return elapsed > self.cooldown

    def cooldown_remaining(self) -> float:
        """Seconds remaining on cooldown; 0 if ready to execute."""
        if self.last_executed is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - self.last_executed).total_seconds()
        return max(0.0, self.cooldown - elapsed)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "target_node": self.target_node,
            "description": self.description,
            "trigger_condition": self.trigger_condition,
            "effect_description": self.effect_description,
            "sri_impact": self.sri_impact,
            "cooldown": self.cooldown,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
            "execution_count": self.execution_count,
            "can_execute": self.can_execute()
        }


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
# Numeric thresholds shared from obs_server.py
SRI_CRITICAL_THRESHOLD = 0.1
SRI_WARNING_THRESHOLD = 0.3
LATENCY_CRITICAL_THRESHOLD = 200
ERROR_RATE_CRITICAL_THRESHOLD = 0.1

class CustomerExperienceTracker:
    """Tracks USER-FACING metrics (not infra terms) to show the effect of
    auto-healing on customer experience. Sampled alongside the correlation
    tracker so each entry carries infra + CX state.

    Perceived speed score:
      • < 200ms  → 100
      • > 2000ms → 0
      • linear in between
    """

    PERCEIVED_FAST_MS = 200.0
    PERCEIVED_SLOW_MS = 2000.0

    def __init__(self, max_samples: int = 600):
        self._lock = Lock()
        self._samples: List[Dict] = []
        self.max_samples = max_samples
        self._journeys: List[Dict] = []   # recent synthetic-user runs

    @classmethod
    def perceived_speed(cls, latency_ms: float) -> float:
        if latency_ms <= cls.PERCEIVED_FAST_MS:
            return 100.0
        if latency_ms >= cls.PERCEIVED_SLOW_MS:
            return 0.0
        span = cls.PERCEIVED_SLOW_MS - cls.PERCEIVED_FAST_MS
        return round(100.0 * (1 - (latency_ms - cls.PERCEIVED_FAST_MS) / span), 1)

    def record(self, latency_ms: float, error_rate_pct: float, conversion: float,
               add_to_cart_ms: Optional[float] = None,
               checkout_ms: Optional[float] = None,
               ts: Optional[float] = None) -> None:
        now = ts or time.time()
        # Heuristic: API-node latency approximates page-load; Cache-node ≈ add-to-cart
        # which is typically faster. We accept either explicit or derived values.
        page_load_ms = float(latency_ms)
        add_to_cart = float(add_to_cart_ms) if add_to_cart_ms is not None else max(50.0, page_load_ms * 0.4)
        checkout_t = float(checkout_ms) if checkout_ms is not None else max(100.0, page_load_ms * 1.5)
        with self._lock:
            self._samples.append({
                "t": now,
                "page_load_ms": round(page_load_ms, 1),
                "add_to_cart_ms": round(add_to_cart, 1),
                "checkout_ms": round(checkout_t, 1),
                "error_shown_rate": round(float(error_rate_pct), 3),
                "conversion": float(conversion),
                "perceived_speed": self.perceived_speed(page_load_ms),
            })
            if len(self._samples) > self.max_samples:
                self._samples = self._samples[-self.max_samples:]

    def add_journey(self, journey: Dict) -> None:
        with self._lock:
            self._journeys.append(journey)
            if len(self._journeys) > 20:
                self._journeys = self._journeys[-20:]

    def snapshot(self, window_seconds: int = 300) -> Dict:
        with self._lock:
            now = time.time()
            cutoff = now - window_seconds
            recent = [s for s in self._samples if s["t"] >= cutoff]
            # Pull healing annotations from correlation_tracker (shared)
            with correlation_tracker._lock:
                anns = [a for a in correlation_tracker._annotations if a["t"] >= cutoff]
            # Compute before/after delta for each annotation
            delta_window = 30.0
            for a in anns:
                before = [s for s in self._samples if a["t"] - delta_window <= s["t"] < a["t"]]
                after = [s for s in self._samples if a["t"] < s["t"] <= a["t"] + delta_window]

                def avg(rows, key):
                    vals = [r[key] for r in rows if key in r]
                    return sum(vals) / len(vals) if vals else None
                pl_b, pl_a = avg(before, "page_load_ms"), avg(after, "page_load_ms")
                ps_b, ps_a = avg(before, "perceived_speed"), avg(after, "perceived_speed")
                er_b, er_a = avg(before, "error_shown_rate"), avg(after, "error_shown_rate")
                a["cx_delta"] = {
                    "page_load_ms_delta": round(pl_a - pl_b, 1) if pl_a is not None and pl_b is not None else None,
                    "perceived_speed_delta": round(ps_a - ps_b, 1) if ps_a is not None and ps_b is not None else None,
                    "error_rate_delta": round(er_a - er_b, 3) if er_a is not None and er_b is not None else None,
                    "samples_before": len(before),
                    "samples_after": len(after),
                }
                a["t_relative"] = round(a["t"] - now, 2)

            # Current scorecard (latest sample) + 30s average
            latest = recent[-1] if recent else None
            recent_30 = [s for s in self._samples if s["t"] >= now - 30]

            def avg30(key):
                vals = [r[key] for r in recent_30]
                return round(sum(vals) / len(vals), 2) if vals else None

            return {
                "window_seconds": window_seconds,
                "samples": len(recent),
                "series": [
                    {**s, "t": round(s["t"] - now, 2), "absolute_t": s["t"]}
                    for s in recent
                ],
                "current": latest,
                "rolling_30s": {
                    "page_load_ms": avg30("page_load_ms"),
                    "add_to_cart_ms": avg30("add_to_cart_ms"),
                    "checkout_ms": avg30("checkout_ms"),
                    "error_shown_rate": avg30("error_shown_rate"),
                    "perceived_speed": avg30("perceived_speed"),
                    "conversion": avg30("conversion"),
                },
                "annotations": anns,
                "recent_journeys": self._journeys[-5:],
            }

class BusinessMetrics:
    """Tracks the e-commerce conversion funnel and business KPIs.
    Models how system health (latency, errors) affects conversion rates.
    The healing engine uses these to ensure resilience improvements
    translate into actual business reliability."""

    def __init__(self):
        self.lock = Lock()
        self.window = 300
        self.events = {"page_view": [], "add_to_cart": [], "checkout_start": [], "order_complete": []}
        self.totals = {"page_view": 0, "add_to_cart": 0, "checkout_start": 0, "order_complete": 0}
        self.revenue_window = []
        self.total_revenue = 0.0
        self.reliability_history = []
        # Conversion model: tracks how health affects conversion
        self.conversion_samples = []  # [{timestamp, health_score, converted}]

    def record_event(self, event_type: str, amount: float = 0):
        with self.lock:
            now = time.time()
            if event_type in self.events:
                self.events[event_type].append(now)
                self.totals[event_type] += 1
            if event_type == "order_complete" and amount > 0:
                self.revenue_window.append((now, amount))
                self.total_revenue += amount
            self._clean(now)

    def _clean(self, now: float):
        cutoff = now - self.window
        for key in self.events:
            self.events[key] = [t for t in self.events[key] if t > cutoff]
        self.revenue_window = [(t, a) for t, a in self.revenue_window if t > cutoff]

    def get_funnel(self) -> Dict:
        with self.lock:
            now = time.time()
            self._clean(now)
            views = len(self.events["page_view"])
            carts = len(self.events["add_to_cart"])
            checkouts = len(self.events["checkout_start"])
            orders = len(self.events["order_complete"])

            # Modeled conversion based on current system health
            modeled = self._model_conversion_impact()

            return {
                "window_seconds": self.window,
                "page_views": views,
                "add_to_cart": carts,
                "checkout_starts": checkouts,
                "orders_completed": orders,
                "conversion_rates": {
                    "view_to_cart": round(carts / max(views, 1), 4),
                    "cart_to_checkout": round(checkouts / max(carts, 1), 4),
                    "checkout_to_order": round(orders / max(checkouts, 1), 4),
                    "overall": round(orders / max(views, 1), 4),
                },
                "modeled_conversion": modeled,
                "revenue_5min": round(sum(a for _, a in self.revenue_window), 2),
                "total_revenue": round(self.total_revenue, 2),
                "totals": dict(self.totals),
            }

    def _model_conversion_impact(self) -> Dict:
        """Model how current system health affects conversion probability.
        Uses empirical relationships: latency kills conversion, errors kill trust."""
        golden = metrics_aggregator.get_golden_signals()
        latency_ms = golden["latency"]["value"]
        error_pct = golden["errors"]["value"]
        
        # Conversion probability model (industry benchmarks):
        # - Every 100ms latency = ~7% conversion loss (Amazon/Google research)
        # - Every 1% error rate = ~10% conversion loss
        base_conversion = 0.035  # 3.5% baseline e-commerce conversion
        latency_factor = max(0, 1 - (latency_ms / 1500))  # 0 at 1500ms
        error_factor = max(0, 1 - (error_pct / 10))  # 0 at 10% errors
        
        effective_conversion = base_conversion * latency_factor * error_factor
        
        # Revenue impact: conversion * avg order value * traffic
        traffic = golden["traffic"]["value"]
        avg_order = 25.0  # estimated average order value
        projected_revenue_per_min = effective_conversion * traffic * avg_order

        # Health-adjusted funnel probabilities
        view_to_cart_prob = 0.15 * latency_factor  # 15% baseline
        cart_to_checkout_prob = 0.60 * error_factor  # 60% baseline
        checkout_to_order_prob = 0.85 * latency_factor * error_factor  # 85% baseline

        return {
            "effective_conversion_rate": round(effective_conversion, 4),
            "base_conversion_rate": base_conversion,
            "latency_impact_factor": round(latency_factor, 4),
            "error_impact_factor": round(error_factor, 4),
            "projected_revenue_per_min": round(projected_revenue_per_min, 2),
            "health_adjusted_funnel": {
                "view_to_cart": round(view_to_cart_prob, 4),
                "cart_to_checkout": round(cart_to_checkout_prob, 4),
                "checkout_to_order": round(checkout_to_order_prob, 4),
            },
            "improvement_opportunity": {
                "if_latency_halved": round(base_conversion * min(latency_factor * 1.5, 1) * error_factor, 4),
                "if_errors_zero": round(base_conversion * latency_factor * 1.0, 4),
                "current": round(effective_conversion, 4),
            },
        }

    def compute_reliability_score(self, sri: float, apdex: float, availability: float) -> Dict:
        """Reliability = weighted composite of resilience + business outcomes."""
        w_sri = 0.20
        w_apdex = 0.30
        w_avail = 0.25
        w_conversion = 0.25

        modeled = self._model_conversion_impact()
        conv_health = modeled["effective_conversion_rate"] / max(modeled["base_conversion_rate"], 0.001)
        conv_health = min(conv_health, 1.0)

        reliability = (w_sri * sri + w_apdex * apdex +
                       w_avail * (availability / 100.0) + w_conversion * conv_health)
        reliability = round(min(max(reliability, 0), 1), 4)

        with self.lock:
            self.reliability_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reliability": reliability,
                "sri": round(sri, 4),
                "apdex": round(apdex, 4),
                "availability": round(availability, 3),
                "conversion_health": round(conv_health, 4),
            })
            if len(self.reliability_history) > 200:
                self.reliability_history = self.reliability_history[-200:]

        return {
            "score": reliability,
            "label": ("excellent" if reliability >= 0.9 else "good" if reliability >= 0.75
                      else "fair" if reliability >= 0.5 else "poor" if reliability >= 0.3 else "critical"),
            "components": {
                "resilience_sri": {"value": round(sri, 4), "weight": w_sri, "contribution": round(w_sri * sri, 4)},
                "customer_apdex": {"value": round(apdex, 4), "weight": w_apdex, "contribution": round(w_apdex * apdex, 4)},
                "availability": {"value": round(availability / 100.0, 4), "weight": w_avail, "contribution": round(w_avail * availability / 100.0, 4)},
                "conversion_health": {"value": round(conv_health, 4), "weight": w_conversion, "contribution": round(w_conversion * conv_health, 4)},
            },
            "modeled_conversion": modeled,
        }

class AlertManager:
    def __init__(self):
        self.lock = Lock()
        self.alerts = []
        self.websocket_clients: Set[WebSocket] = set()
        self.last_alert_time = {}
        self.alert_cooldown = 60  # seconds between same alert type
        
    async def add_client(self, websocket: WebSocket):
        await websocket.accept()
        self.websocket_clients.add(websocket)
        # Send recent alerts
        with self.lock:
            if self.alerts:
                await websocket.send_json({"type": "history", "alerts": self.alerts[-20:]})
    
    def remove_client(self, websocket: WebSocket):
        self.websocket_clients.discard(websocket)
    
    async def broadcast(self, alert: dict):
        dead_clients = set()
        for ws in self.websocket_clients:
            try:
                await ws.send_json(alert)
            except:
                dead_clients.add(ws)
        self.websocket_clients -= dead_clients
    
    async def check_and_alert(self, sri: float, avg_latency: float, avg_error: float, node_metrics: dict):
        now = datetime.now(timezone.utc)
        alerts_to_send = []
        
        # SRI Critical Alert
        if sri < SRI_CRITICAL_THRESHOLD:
            alert_key = "sri_critical"
            if self._can_alert(alert_key, now):
                alert = {
                    "id": f"{alert_key}_{now.timestamp()}",
                    "type": "critical",
                    "category": "sri",
                    "title": "CRITICAL: System Resilience Index Below Threshold",
                    "message": f"SRI dropped to {sri:.4f} (threshold: {SRI_CRITICAL_THRESHOLD})",
                    "value": sri,
                    "threshold": SRI_CRITICAL_THRESHOLD,
                    "timestamp": now.isoformat(),
                    "action": "Investigate system health immediately"
                }
                alerts_to_send.append(alert)
                self.last_alert_time[alert_key] = now
        elif sri < SRI_WARNING_THRESHOLD:
            alert_key = "sri_warning"
            if self._can_alert(alert_key, now):
                alert = {
                    "id": f"{alert_key}_{now.timestamp()}",
                    "type": "warning",
                    "category": "sri",
                    "title": "WARNING: System Resilience Index Degraded",
                    "message": f"SRI at {sri:.4f} (warning threshold: {SRI_WARNING_THRESHOLD})",
                    "value": sri,
                    "threshold": SRI_WARNING_THRESHOLD,
                    "timestamp": now.isoformat(),
                    "action": "Monitor system closely"
                }
                alerts_to_send.append(alert)
                self.last_alert_time[alert_key] = now
        
        # Latency Alert
        if avg_latency > LATENCY_CRITICAL_THRESHOLD:
            alert_key = "latency_critical"
            if self._can_alert(alert_key, now):
                alert = {
                    "id": f"{alert_key}_{now.timestamp()}",
                    "type": "critical",
                    "category": "latency",
                    "title": "CRITICAL: High System Latency",
                    "message": f"Average latency at {avg_latency:.1f}ms (threshold: {LATENCY_CRITICAL_THRESHOLD}ms)",
                    "value": avg_latency,
                    "threshold": LATENCY_CRITICAL_THRESHOLD,
                    "timestamp": now.isoformat(),
                    "action": "Check for bottlenecks in API, DB, or Cache"
                }
                alerts_to_send.append(alert)
                self.last_alert_time[alert_key] = now
        
        # Error Rate Alert
        if avg_error > ERROR_RATE_CRITICAL_THRESHOLD:
            alert_key = "error_critical"
            if self._can_alert(alert_key, now):
                alert = {
                    "id": f"{alert_key}_{now.timestamp()}",
                    "type": "critical",
                    "category": "error",
                    "title": "CRITICAL: High Error Rate",
                    "message": f"Error rate at {avg_error*100:.1f}% (threshold: {ERROR_RATE_CRITICAL_THRESHOLD*100}%)",
                    "value": avg_error,
                    "threshold": ERROR_RATE_CRITICAL_THRESHOLD,
                    "timestamp": now.isoformat(),
                    "action": "Check application logs for errors"
                }
                alerts_to_send.append(alert)
                self.last_alert_time[alert_key] = now
        
        # Node-specific alerts
        for node_name, metrics in node_metrics.items():
            if metrics["saturation"] > 0.9:
                alert_key = f"saturation_{node_name}"
                if self._can_alert(alert_key, now):
                    alert = {
                        "id": f"{alert_key}_{now.timestamp()}",
                        "type": "warning",
                        "category": "saturation",
                        "title": f"WARNING: {node_name} Node Saturated",
                        "message": f"{node_name} saturation at {metrics['saturation']*100:.0f}%",
                        "value": metrics["saturation"],
                        "threshold": 0.9,
                        "timestamp": now.isoformat(),
                        "node": node_name,
                        "action": f"Consider scaling {node_name} resources"
                    }
                    alerts_to_send.append(alert)
                    self.last_alert_time[alert_key] = now
        
        # Store and broadcast alerts
        for alert in alerts_to_send:
            with self.lock:
                self.alerts.append(alert)
                if len(self.alerts) > 100:
                    self.alerts = self.alerts[-100:]
            
            # Store in MongoDB (remove _id to let MongoDB auto-generate)
            alert_doc = {k: v for k, v in alert.items() if k != "_id"}
            await db.alerts.insert_one(alert_doc)
            
            # Store in InfluxDB
            if write_api:
                try:
                    point = Point("alert") \
                        .tag("type", alert["type"]) \
                        .tag("category", alert["category"]) \
                        .field("value", alert["value"]) \
                        .field("threshold", alert["threshold"]) \
                        .time(now, WritePrecision.MS)
                    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                except:
                    pass
            
            # Broadcast via WebSocket
            await self.broadcast({"type": "alert", "alert": alert})

            # Fire external webhooks (Slack / Discord) — critical only, non-blocking
            if alert.get("type") == "critical":
                asyncio.create_task(webhook_notifier.dispatch(alert))

            logger.warning(f"ALERT: {alert['title']} - {alert['message']}")
            
            # Trigger alert-driven healing
            try:
                await healing_engine.on_alert(alert)
            except Exception as e:
                logger.debug(f"Alert-driven healing error: {e}")
        
        return alerts_to_send
    
    def _can_alert(self, alert_key: str, now: datetime) -> bool:
        if alert_key not in self.last_alert_time:
            return True
        elapsed = (now - self.last_alert_time[alert_key]).total_seconds()
        return elapsed > self.alert_cooldown
    
    def get_recent_alerts(self, limit: int = 50) -> list:
        with self.lock:
            return self.alerts[-limit:]
