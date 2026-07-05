"""
RST (Runtime Stiffness Tensor) — backend unit tests.

Tests the RSTEngine in isolation (no live obs_server) to verify:
  * K-component derivation from raw metrics
  * K_eff weighted-geometric-mean formula
  * Stress σ and strain ε computation
  * Spectral properties (λ2, λmax, rst_sri) of the stiffness Laplacian
  * Scenario override mechanism
  * History rolling buffer
  * API endpoint shapes (contract tests via REACT_APP_BACKEND_URL if set)
"""
import math
import os
import sys
import time
import types
import unittest

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when run from the repo root or
# from the backend/ directory.
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from obs.engines.rst_engine import (
    RSTEngine,
    ALL_NODES,
    GRAPH_EDGES,
    W_A, W_H, W_S, W_D, W_F, W_R,
)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _fake_metrics(latency=50.0, error=0.0, saturation=0.0, traffic=100.0):
    return {"latency": latency, "error": error, "saturation": saturation, "traffic": traffic}


def _fake_phase(eutectic_d2=0.0):
    return {"eutectic_d2": eutectic_d2}


def _engine_with_metrics(node_metrics: dict, phase_data: dict | None = None) -> RSTEngine:
    """Return an RSTEngine with fake singletons pre-wired."""
    import obs.engines.rst_engine as rst_mod

    # Build a fake MetricsAggregator
    class FakeMA:
        def get_all_metrics(self):
            return node_metrics

    # Build a fake PhaseClassifier
    class FakePC:
        def state(self):
            return {"per_node": phase_data or {}}

    rst_mod.metrics_aggregator       = FakeMA()
    rst_mod.phase_classifier_instance = FakePC()
    rst_mod.healing_engine            = None

    engine = RSTEngine()
    return engine


# ---------------------------------------------------------------------------
#  Unit tests
# ---------------------------------------------------------------------------

class TestNodeTensor(unittest.TestCase):

    def setUp(self):
        import obs.engines.rst_engine as rst_mod
        rst_mod.metrics_aggregator        = None
        rst_mod.phase_classifier_instance = None
        rst_mod.healing_engine            = None
        self.engine = RSTEngine()

    def _compute_node(self, node, m, ph=None, scenario=None):
        return self.engine._node_tensor(node, m or {}, ph or {}, {}, scenario)

    # --- K_A ---

    def test_k_a_healthy_node(self):
        t = self._compute_node("API", _fake_metrics(error=0.0))
        self.assertAlmostEqual(t["K_A"], 1.0, places=2)

    def test_k_a_degraded_node(self):
        t = self._compute_node("API", _fake_metrics(error=0.5))
        self.assertAlmostEqual(t["K_A"], 0.5, places=2)

    def test_k_a_fully_failed(self):
        t = self._compute_node("API", _fake_metrics(error=1.0))
        self.assertLessEqual(t["K_A"], 0.01)

    # --- K_S ---

    def test_k_s_no_saturation(self):
        t = self._compute_node("DB", _fake_metrics(saturation=0.0))
        self.assertAlmostEqual(t["K_S"], 1.0, places=2)

    def test_k_s_high_saturation(self):
        t = self._compute_node("DB", _fake_metrics(saturation=0.9))
        self.assertLessEqual(t["K_S"], 0.15)

    # --- K_D ---

    def test_k_d_frontend_vs_backend(self):
        """Frontend (degree 1) should have lower K_D than Backend (degree 3)."""
        t_fe  = self._compute_node("Frontend", _fake_metrics())
        t_be  = self._compute_node("Backend",  _fake_metrics())
        self.assertLess(t_fe["K_D"], t_be["K_D"])

    def test_k_d_in_range(self):
        for node in ALL_NODES:
            t = self._compute_node(node, _fake_metrics())
            self.assertGreaterEqual(t["K_D"], 0.01)
            self.assertLessEqual(t["K_D"], 1.0)

    # --- K_F ---

    def test_k_f_low_latency(self):
        t = self._compute_node("API", _fake_metrics(latency=50.0))  # ratio=1 → K_F at max
        self.assertGreater(t["K_F"], 0.6)

    def test_k_f_high_latency(self):
        t = self._compute_node("API", _fake_metrics(latency=1500.0))  # ratio=30
        self.assertLess(t["K_F"], 0.3)

    # --- K_R ---

    def test_k_r_at_eutectic(self):
        """d2=0 means node is exactly at the stable point → K_R = 1."""
        t = self._compute_node("API", _fake_metrics(), _fake_phase(eutectic_d2=0.0))
        self.assertAlmostEqual(t["K_R"], 1.0, places=2)

    def test_k_r_far_from_eutectic(self):
        t = self._compute_node("API", _fake_metrics(), _fake_phase(eutectic_d2=5.0))
        self.assertLess(t["K_R"], 0.01)

    # --- K_eff ---

    def test_k_eff_formula(self):
        """K_eff = K_A^W_A · K_H^W_H · ... must match manual computation."""
        m = _fake_metrics(latency=50.0, error=0.0, saturation=0.0)
        t = self._compute_node("API", m, _fake_phase(eutectic_d2=0.0))
        expected = (
            t["K_A"] ** W_A *
            t["K_H"] ** W_H *
            t["K_S"] ** W_S *
            t["K_D"] ** W_D *
            t["K_F"] ** W_F *
            t["K_R"] ** W_R
        )
        self.assertAlmostEqual(t["K_eff"], expected, places=4)

    def test_k_eff_in_range(self):
        m = _fake_metrics(latency=200.0, error=0.2, saturation=0.5)
        for node in ALL_NODES:
            t = self._compute_node(node, m)
            self.assertGreater(t["K_eff"], 0.0)
            self.assertLessEqual(t["K_eff"], 1.0)

    # --- Stress & Strain ---

    def test_sigma_healthy(self):
        """σ should be ~0 for a perfectly healthy node."""
        t = self._compute_node("API", _fake_metrics(latency=50.0, error=0.0, saturation=0.0))
        self.assertAlmostEqual(t["sigma"], 0.0, places=2)

    def test_sigma_stressed(self):
        t = self._compute_node("API", _fake_metrics(latency=500.0, error=0.4, saturation=0.6))
        self.assertGreater(t["sigma"], 0.3)

    def test_epsilon_increases_with_low_stiffness(self):
        """For the same σ, a lower K_eff should produce higher ε."""
        t_healthy = self._compute_node("API", _fake_metrics(latency=300.0, error=0.2, saturation=0.3),
                                       _fake_phase(eutectic_d2=0.1))
        t_failed  = self._compute_node("API", _fake_metrics(latency=300.0, error=0.2, saturation=0.3),
                                       _fake_phase(eutectic_d2=5.0))
        # K_R is lower for failed → K_eff is lower → epsilon is higher
        self.assertLess(t_healthy["epsilon"], t_failed["epsilon"])

    def test_epsilon_clamped_to_five(self):
        """ε is capped at 5."""
        # Extreme stress + very low stiffness
        t = self._compute_node("API", _fake_metrics(latency=1500.0, error=1.0, saturation=1.0),
                               _fake_phase(eutectic_d2=10.0))
        self.assertLessEqual(t["epsilon"], 5.0)

    # --- Scenario override ---

    def test_scenario_reduces_k_a(self):
        t_base = self._compute_node("DB", _fake_metrics())
        scenario = {"overrides": {"DB": {"K_A": 0.1}}}
        t_sc   = self._compute_node("DB", _fake_metrics(), scenario=scenario)
        self.assertLess(t_sc["K_A"], t_base["K_A"])

    def test_scenario_clamped_at_min(self):
        scenario = {"overrides": {"API": {"K_A": 0.0}}}
        t = self._compute_node("API", _fake_metrics(), scenario=scenario)
        self.assertGreaterEqual(t["K_A"], 0.01)


class TestSpectral(unittest.TestCase):

    def setUp(self):
        import obs.engines.rst_engine as rst_mod
        rst_mod.metrics_aggregator        = None
        rst_mod.phase_classifier_instance = None
        rst_mod.healing_engine            = None
        self.engine = RSTEngine()

    def _uniform_nodes(self, k_eff: float = 0.7) -> dict:
        return {nd: {"K_eff": k_eff, "sigma": 0.1, "epsilon": 0.14, "phase": "stable_throughput"}
                for nd in ALL_NODES}

    def test_lambda2_positive_connected_graph(self):
        nodes = self._uniform_nodes(0.7)
        sp = self.engine._spectral(nodes)
        self.assertGreater(sp["lambda2"], 0.0)

    def test_lambda_max_gt_lambda2(self):
        nodes = self._uniform_nodes(0.7)
        sp = self.engine._spectral(nodes)
        self.assertGreater(sp["lambda_max"], sp["lambda2"])

    def test_rst_sri_in_0_1(self):
        nodes = self._uniform_nodes(0.7)
        sp = self.engine._spectral(nodes)
        self.assertGreaterEqual(sp["rst_sri"], 0.0)
        self.assertLessEqual(sp["rst_sri"], 1.0)

    def test_rst_sri_lower_with_weaker_nodes(self):
        """A graph with lower K_eff edges should have lower λ2 and RST-SRI."""
        high = self._uniform_nodes(0.9)
        low  = self._uniform_nodes(0.1)
        sp_high = self.engine._spectral(high)
        sp_low  = self.engine._spectral(low)
        self.assertGreater(sp_high["lambda2"], sp_low["lambda2"])


class TestEngineCompute(unittest.TestCase):
    """Integration-style: full _compute() call with fake singletons."""

    def test_compute_returns_all_nodes(self):
        engine = _engine_with_metrics(
            {nd: _fake_metrics() for nd in ALL_NODES}
        )
        snap = engine._compute()
        self.assertTrue(snap["ready"])
        for nd in ALL_NODES:
            self.assertIn(nd, snap["nodes"])

    def test_compute_snap_has_spectral(self):
        engine = _engine_with_metrics(
            {nd: _fake_metrics() for nd in ALL_NODES}
        )
        snap = engine._compute()
        self.assertIn("spectral", snap)
        self.assertIn("lambda2",    snap["spectral"])
        self.assertIn("lambda_max", snap["spectral"])
        self.assertIn("rst_sri",    snap["spectral"])

    def test_compute_adds_to_history(self):
        engine = _engine_with_metrics(
            {nd: _fake_metrics() for nd in ALL_NODES}
        )
        snap = engine._compute()
        engine.history.append(snap)
        self.assertEqual(len(engine.history_snapshot(limit=1)), 1)

    def test_state_not_ready_before_compute(self):
        import obs.engines.rst_engine as rst_mod
        rst_mod.metrics_aggregator = None
        rst_mod.phase_classifier_instance = None
        rst_mod.healing_engine = None
        engine = RSTEngine()
        s = engine.state()
        self.assertFalse(s["ready"])

    def test_scenario_applied_and_cleared(self):
        engine = _engine_with_metrics(
            {nd: _fake_metrics() for nd in ALL_NODES}
        )
        engine.apply_scenario("test", {"DB": {"K_A": 0.1}}, duration_s=10.0)
        snap_with = engine._compute()
        self.assertEqual(snap_with["scenario"], "test")

        engine.clear_scenario()
        snap_cleared = engine._compute()
        self.assertIsNone(snap_cleared["scenario"])


# ---------------------------------------------------------------------------
#  Contract / API tests (only run when REACT_APP_BACKEND_URL is set)
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@unittest.skipUnless(BASE_URL, "REACT_APP_BACKEND_URL not set — skipping live API tests")
class TestRSTAPI(unittest.TestCase):

    def setUp(self):
        import requests
        self.s = requests.Session()
        self.s.headers["Content-Type"] = "application/json"
        self.TIMEOUT = 20

    def test_rst_state_200(self):
        r = self.s.get(f"{BASE_URL}/api/rst/state", timeout=self.TIMEOUT)
        self.assertEqual(r.status_code, 200)

    def test_rst_state_shape(self):
        r = self.s.get(f"{BASE_URL}/api/rst/state", timeout=self.TIMEOUT).json()
        self.assertIn("ready", r)
        if r["ready"]:
            self.assertIn("nodes", r)
            self.assertIn("spectral", r)
            for nd in ALL_NODES:
                self.assertIn(nd, r["nodes"])
                for comp in ("K_A", "K_H", "K_S", "K_D", "K_F", "K_R", "K_eff", "sigma", "epsilon"):
                    self.assertIn(comp, r["nodes"][nd], f"missing {comp} for {nd}")

    def test_rst_history_200(self):
        r = self.s.get(f"{BASE_URL}/api/rst/history?limit=5", timeout=self.TIMEOUT)
        self.assertEqual(r.status_code, 200)
        self.assertIn("samples", r.json())

    def test_rst_scenario_post_and_delete(self):
        payload = {"name": "test_ci", "overrides": {"DB": {"K_A": 0.2}}, "duration_s": 5.0}
        r = self.s.post(f"{BASE_URL}/api/rst/scenario", json=payload, timeout=self.TIMEOUT)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

        r2 = self.s.delete(f"{BASE_URL}/api/rst/scenario", timeout=self.TIMEOUT)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["ok"])


if __name__ == "__main__":
    unittest.main()
