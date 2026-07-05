"""Runtime Stiffness Tensor (RST) Engine — models each service node as a
structural element with a 6-component stiffness tensor K.

Each component measures a distinct mechanical-analogous property:
  K_A  — Availability stiffness   (resistance to error-driven yielding)
  K_H  — Healing stiffness         (responsiveness to corrective actions)
  K_S  — Saturation stiffness      (resistance to resource exhaustion)
  K_D  — Dependency stiffness      (structural integrity under graph load)
  K_F  — Fault stiffness           (resistance to fault propagation)
  K_R  — Resilience stiffness      (SRI-derived global resilience coupling)

The tensor composition gives a per-node effective stiffness:
  K_eff(n) = K_A · K_H · K_S · K_D · K_F · K_R  (geometric / harmonic mean variant)

Physical analogy (Hooke's law):
  σ(n) = applied operational stress  (derived from golden signals)
  ε(n) = σ(n) / K_eff(n)           (strain — how much the node deforms under load)

High K_eff → stiff node (low strain, survives load well).
Low  K_eff → compliant node (high strain, deforms / fails under moderate stress).

The engine also computes:
  * λ2   — algebraic connectivity (second smallest Laplacian eigenvalue)
  * λmax — spectral radius of the stiffness-weighted graph Laplacian
  * SRI  — agrees with obs_server's SRI when stress is low; diverges upward
           under concentrated fault propagation

Background tick: 5 s (same cadence as PhaseClassifier and StabilityFunctional).
History window : 240 samples (~20 min).

All singletons are forward-declared and bound by obs_server._wire_extracted_modules.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import deque
from threading import Lock
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
#  Service graph topology (mirrors ladder_synthesizer.ALL_NODES)
# ============================================================

ALL_NODES: List[str] = ["Frontend", "API", "Cache", "Backend", "DB", "Queue"]

# Undirected service graph edges (n_i → n_j means they exchange load)
GRAPH_EDGES: List[Tuple[str, str]] = [
    ("Frontend", "API"),
    ("API",      "Cache"),
    ("API",      "Backend"),
    ("Backend",  "DB"),
    ("Backend",  "Queue"),
    ("Cache",    "DB"),
]

# Structural degree of each node (pre-computed for K_D baseline)
_NODE_DEGREE: Dict[str, int] = {n: 0 for n in ALL_NODES}
for _a, _b in GRAPH_EDGES:
    _NODE_DEGREE[_a] += 1
    _NODE_DEGREE[_b] += 1
_MAX_DEGREE = max(_NODE_DEGREE.values()) or 1

# ============================================================
#  Tunables
# ============================================================
RST_TICK_INTERVAL_S  = float(os.environ.get("RST_TICK_INTERVAL_S",  "5.0"))
RST_HISTORY_SIZE     = int(os.environ.get("RST_HISTORY_SIZE",        "240"))   # ~20 min

# Weights for geometric mean composition (must sum to 1 for normalised output)
W_A = float(os.environ.get("RST_W_A", "0.20"))   # availability
W_H = float(os.environ.get("RST_W_H", "0.15"))   # healing
W_S = float(os.environ.get("RST_W_S", "0.20"))   # saturation
W_D = float(os.environ.get("RST_W_D", "0.15"))   # dependency
W_F = float(os.environ.get("RST_W_F", "0.15"))   # fault
W_R = float(os.environ.get("RST_W_R", "0.15"))   # resilience

# Stress normalisation baselines (mirror phase_classifier.py)
LATENCY_BASELINE_MS  = float(os.environ.get("PHASE_L0",      "50.0"))
LATENCY_CEILING_MS   = float(os.environ.get("PHASE_L_CEIL",  "1500.0"))
MEM_CAP              = float(os.environ.get("PHASE_M_CAP",   "0.80"))


# ============================================================
#  Forward-declared singletons — bound by obs_server
# ============================================================
metrics_aggregator      = None
phase_classifier_instance = None
healing_engine          = None
resilience_debt         = None  # ResilienceDebtAccumulator (optional)


# ============================================================
#  RST Engine
# ============================================================

class RSTEngine:
    """Computes per-node Runtime Stiffness Tensor at every tick."""

    def __init__(self):
        self.lock = Lock()
        self.history: Deque[Dict[str, Any]] = deque(maxlen=RST_HISTORY_SIZE)
        self._latest: Optional[Dict[str, Any]] = None
        self._task: Optional[asyncio.Task] = None
        # Active scenario override: None or dict {node: {component: override_factor}}
        self._scenario: Optional[Dict[str, Any]] = None
        self._scenario_expires: float = 0.0

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def state(self) -> Dict[str, Any]:
        with self.lock:
            if self._latest is None:
                return {"ready": False, "nodes": {}}
            return dict(self._latest)

    def history_snapshot(self, limit: int = 60) -> List[Dict[str, Any]]:
        with self.lock:
            samples = list(self.history)
        return samples[-limit:]

    def apply_scenario(self, name: str, overrides: Dict[str, Any], duration_s: float = 30.0) -> None:
        """Temporarily inject fault/stress overrides for demo/testing."""
        with self.lock:
            self._scenario = {"name": name, "overrides": overrides}
            self._scenario_expires = time.time() + duration_s
        self._publish(self._compute())

    def clear_scenario(self) -> None:
        with self.lock:
            self._scenario = None
            self._scenario_expires = 0.0
        self._publish(self._compute())

    # ------------------------------------------------------------------ #
    #  Background loop                                                     #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        if self._task is None or self._task.done():
            try:
                self._publish(self._compute())
            except Exception as exc:
                logger.exception("RSTEngine initial sample error: %s", exc)
            self._task = asyncio.create_task(self._loop())
            logger.info("RSTEngine background loop started")

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(RST_TICK_INTERVAL_S)
                self._publish(self._compute())
            except Exception as exc:
                logger.exception("RSTEngine tick error: %s", exc)

    def _publish(self, snap: Dict[str, Any]) -> None:
        with self.lock:
            self._latest = snap
            self.history.append(snap)

    # ------------------------------------------------------------------ #
    #  Core computation                                                    #
    # ------------------------------------------------------------------ #

    def _compute(self) -> Dict[str, Any]:
        now = time.time()
        ts  = now

        # Pull live node metrics
        node_metrics: Dict[str, Dict] = {}
        if metrics_aggregator is not None:
            try:
                node_metrics = metrics_aggregator.get_all_metrics()
            except Exception:
                pass

        # Pull phase-classifier data (optional)
        phase_data: Dict[str, Any] = {}
        if phase_classifier_instance is not None:
            try:
                phase_data = phase_classifier_instance.state() or {}
            except Exception:
                pass

        # Pull healing gain matrix (optional)
        gain_matrix: Dict[str, Dict] = {}
        if healing_engine is not None:
            try:
                if hasattr(healing_engine, "last_gain_matrix"):
                    gain_matrix = healing_engine.last_gain_matrix or {}
            except Exception:
                pass

        # Active scenario?
        scenario: Optional[Dict] = None
        with self.lock:
            if self._scenario and now < self._scenario_expires:
                scenario = self._scenario
            elif self._scenario and now >= self._scenario_expires:
                self._scenario = None

        # Compute per-node tensor
        nodes_out: Dict[str, Any] = {}
        per_node_phase = phase_data.get("per_node", {})
        for node in ALL_NODES:
            m = node_metrics.get(node, {})
            ph = per_node_phase.get(node, {})
            nodes_out[node] = self._node_tensor(node, m, ph, gain_matrix, scenario)

        # Build stiffness-weighted graph and spectral properties
        spectral = self._spectral(nodes_out)

        snap = {
            "ready":    True,
            "ts":       ts,
            "nodes":    nodes_out,
            "spectral": spectral,
            "scenario": scenario["name"] if scenario else None,
        }
        return snap

    # ------------------------------------------------------------------ #
    #  Per-node tensor computation                                         #
    # ------------------------------------------------------------------ #

    def _node_tensor(
        self,
        node: str,
        m: Dict,
        ph: Dict,
        gain_matrix: Dict,
        scenario: Optional[Dict],
    ) -> Dict[str, Any]:

        latency    = float(m.get("latency",    50.0))
        error_rate = float(m.get("error",       0.0))
        saturation = float(m.get("saturation",  0.0))
        traffic    = float(m.get("traffic",      0.0))

        # ── K_A: Availability stiffness ──────────────────────────────
        # High error rate → low availability → low K_A
        # K_A ∈ (0, 1], approaches 0 as error_rate → 1
        k_a = max(0.01, 1.0 - error_rate)

        # ── K_S: Saturation stiffness ─────────────────────────────────
        # High saturation → low K_S (service at capacity, easily deflected)
        k_s = max(0.01, 1.0 - saturation)

        # ── K_D: Dependency / structural stiffness ────────────────────
        # Higher degree in graph → more load paths → higher K_D
        # Normalised by max degree; high connectivity = more stiff
        degree = _NODE_DEGREE.get(node, 1)
        k_d = 0.5 + 0.5 * (degree / _MAX_DEGREE)

        # ── K_H: Healing stiffness ────────────────────────────────────
        # Derived from the average gain-matrix score for this node's actions.
        # If no gain matrix, default to 0.5 (neutral).
        node_gains = gain_matrix.get(node, {})
        if node_gains:
            avg_gain = sum(node_gains.values()) / len(node_gains)
            # gain ∈ [-1, +1]; remap to (0, 1]
            k_h = max(0.01, 0.5 + 0.5 * avg_gain)
        else:
            k_h = 0.5

        # ── K_F: Fault stiffness ──────────────────────────────────────
        # Derived from latency ratio L/L_0.  High latency means the node is
        # already "deformed" by faults — it has low resistance to further stress.
        latency_ratio = latency / max(LATENCY_BASELINE_MS, 1.0)
        k_f = max(0.01, 1.0 / (1.0 + math.log(max(latency_ratio, 1.0))))

        # ── K_R: Resilience stiffness ─────────────────────────────────
        # Use per-node phase eutectic distance from the PhaseClassifier.
        # Nodes close to Ψ_s are more resilient (high K_R).
        # d2 ∈ [0, ∞); map to (0, 1] via exponential decay.
        d2 = ph.get("eutectic_d2", None)
        if d2 is not None:
            k_r = math.exp(-float(d2))
        else:
            # Fallback: derive from SRI proxy (error + latency + saturation)
            stress_proxy = 0.3 * (latency_ratio - 1.0) / max(LATENCY_CEILING_MS / LATENCY_BASELINE_MS - 1.0, 1.0) \
                         + 0.35 * error_rate \
                         + 0.35 * saturation
            k_r = max(0.01, math.exp(-3.0 * max(0.0, stress_proxy)))

        # ── Apply scenario overrides ──────────────────────────────────
        if scenario:
            node_ov = scenario.get("overrides", {}).get(node, {})
            k_a *= float(node_ov.get("K_A", 1.0))
            k_h *= float(node_ov.get("K_H", 1.0))
            k_s *= float(node_ov.get("K_S", 1.0))
            k_d *= float(node_ov.get("K_D", 1.0))
            k_f *= float(node_ov.get("K_F", 1.0))
            k_r *= float(node_ov.get("K_R", 1.0))
            # Clamp to valid range
            k_a = max(0.01, min(1.0, k_a))
            k_h = max(0.01, min(1.0, k_h))
            k_s = max(0.01, min(1.0, k_s))
            k_d = max(0.01, min(1.0, k_d))
            k_f = max(0.01, min(1.0, k_f))
            k_r = max(0.01, min(1.0, k_r))

        # ── Effective stiffness: weighted geometric mean ───────────────
        # K_eff = K_A^w_A · K_H^w_H · K_S^w_S · K_D^w_D · K_F^w_F · K_R^w_R
        k_eff = (
            k_a ** W_A *
            k_h ** W_H *
            k_s ** W_S *
            k_d ** W_D *
            k_f ** W_F *
            k_r ** W_R
        )
        k_eff = max(0.001, k_eff)

        # ── Stress σ: operational stress on this node ─────────────────
        # Combines latency pressure, error stress, saturation stress
        sigma = (
            0.30 * min(1.0, max(0.0, (latency_ratio - 1.0) / (LATENCY_CEILING_MS / LATENCY_BASELINE_MS - 1.0))) +
            0.35 * min(1.0, error_rate) +
            0.35 * min(1.0, saturation)
        )

        # ── Strain ε: node deformation under σ ────────────────────────
        # Hooke's law analogy: ε = σ / K_eff
        # High K_eff → low ε (stiff node absorbs stress without yielding)
        epsilon = sigma / k_eff

        # Clamp strain to a sensible display range [0, 5]
        epsilon = min(5.0, max(0.0, epsilon))

        return {
            "K_A":   round(k_a,   4),
            "K_H":   round(k_h,   4),
            "K_S":   round(k_s,   4),
            "K_D":   round(k_d,   4),
            "K_F":   round(k_f,   4),
            "K_R":   round(k_r,   4),
            "K_eff": round(k_eff, 4),
            "sigma": round(sigma,   4),
            "epsilon": round(epsilon, 4),
            "phase": ph.get("phase", "unknown"),
        }

    # ------------------------------------------------------------------ #
    #  Spectral analysis of stiffness-weighted Laplacian                  #
    # ------------------------------------------------------------------ #

    def _spectral(self, nodes_out: Dict[str, Any]) -> Dict[str, Any]:
        """Compute λ2 (algebraic connectivity) and λmax from the
        stiffness-weighted graph Laplacian L = D - W."""
        n = len(ALL_NODES)
        idx = {node: i for i, node in enumerate(ALL_NODES)}
        W = np.zeros((n, n), dtype=float)
        for a, b in GRAPH_EDGES:
            ia, ib = idx[a], idx[b]
            # Edge weight = harmonic mean of K_eff values (weakest link)
            ka = nodes_out[a]["K_eff"]
            kb = nodes_out[b]["K_eff"]
            w_ab = 2.0 * ka * kb / (ka + kb + 1e-9)
            W[ia, ib] = w_ab
            W[ib, ia] = w_ab

        D = np.diag(W.sum(axis=1))
        L = D - W

        try:
            eigvals = np.linalg.eigvalsh(L)
            eigvals_sorted = sorted(eigvals.tolist())
            lambda2  = float(eigvals_sorted[1])  if len(eigvals_sorted) > 1 else 0.0
            lambda_max = float(eigvals_sorted[-1]) if eigvals_sorted else 0.0
        except Exception:
            lambda2 = 0.0
            lambda_max = 0.0

        # RST-SRI: normalise λ2 by λmax to get a [0,1] connectivity index
        rst_sri = lambda2 / (lambda_max + 1e-9)

        return {
            "lambda2":    round(lambda2,    4),
            "lambda_max": round(lambda_max, 4),
            "rst_sri":    round(rst_sri,    4),
        }
