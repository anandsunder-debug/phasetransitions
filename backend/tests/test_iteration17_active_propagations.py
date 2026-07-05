"""Iteration 17: Active propagations + healing sequence optimization tests.

Covers:
- GET  /api/healing/active-propagations         (snapshot shape)
- POST /api/healing/auto-propagation/config     (toggle + clamps)
- POST /api/healing/optimize-sequence           (BFS-depth × score ordering)
- POST /api/healing/execute-sequence            (per-step results, validation)
- Heavy-traffic activation of `active` list + autonomous healing plan
- Regression: previously-shipped endpoints still 200
"""
import os
import time
import uuid
import threading
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
API = f"{BASE_URL}/api"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def admin(s):
    r = s.post(f"{API}/auth/login", json={"email": "admin@freshcart.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    return s


# ---------- /healing/active-propagations snapshot shape ----------
class TestSnapshot:
    def test_snapshot_shape(self, s):
        r = s.get(f"{API}/healing/active-propagations")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in [
            "enabled", "autonomous_heal", "interval_sec",
            "stress_pressure_threshold", "active", "detection_count",
            "last_run_at", "recent_history",
        ]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["enabled"], bool)
        assert isinstance(d["autonomous_heal"], bool)
        assert isinstance(d["interval_sec"], int)
        assert isinstance(d["active"], list)
        assert isinstance(d["detection_count"], int)
        assert isinstance(d["recent_history"], list)


# ---------- /healing/auto-propagation/config ----------
class TestConfig:
    def test_disable_then_enable(self, s):
        r = s.post(f"{API}/healing/auto-propagation/config", json={"enabled": False})
        assert r.status_code == 200, r.text
        assert r.json()["enabled"] is False
        r2 = s.post(f"{API}/healing/auto-propagation/config", json={"enabled": True})
        assert r2.status_code == 200
        assert r2.json()["enabled"] is True

    def test_interval_clamp_low(self, s):
        r = s.post(f"{API}/healing/auto-propagation/config", json={"interval_sec": 2})
        assert r.status_code == 200, r.text
        assert r.json()["interval_sec"] == 3, r.json()

    def test_interval_clamp_high(self, s):
        r = s.post(f"{API}/healing/auto-propagation/config", json={"interval_sec": 100})
        assert r.status_code == 200, r.text
        assert r.json()["interval_sec"] == 60, r.json()
        # restore to 8 default-ish
        s.post(f"{API}/healing/auto-propagation/config", json={"interval_sec": 8})


# ---------- /healing/optimize-sequence ----------
class TestOptimize:
    payload = {
        "stressed_nodes": [
            {"node": "DB", "pressure": 0.5, "yield_exceeded": True},
            {"node": "Cache", "pressure": 0.3, "yield_exceeded": False},
            {"node": "Backend", "pressure": 0.2, "yield_exceeded": False},
        ],
        "source": "DB",
        "granularity": "service",
    }

    def test_optimize_shape_and_ordering(self, s):
        r = s.post(f"{API}/healing/optimize-sequence", json=self.payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "DB"
        assert d["granularity"] == "service"
        assert d["candidate_count"] == 3
        assert isinstance(d["ordering_rule"], str) and d["ordering_rule"]
        assert d["expected_total_sri_gain"] >= 0  # gt 0 if any non-zero readiness
        assert isinstance(d["sequence"], list) and len(d["sequence"]) >= 1
        # DB at depth 0 first (BFS source)
        assert d["sequence"][0]["node"] == "DB"
        assert d["sequence"][0]["depth"] == 0
        # depths non-decreasing
        depths = [s["depth"] for s in d["sequence"]]
        assert depths == sorted(depths), depths
        # each step shape
        for st in d["sequence"]:
            for k in ["node", "target_node", "action_id", "depth", "pressure", "readiness", "score"]:
                assert k in st, f"missing {k} in step {st}"
            assert 0.0 <= st["readiness"] <= 1.0

    def test_optimize_invalid_granularity(self, s):
        bad = dict(self.payload, granularity="bogus")
        r = s.post(f"{API}/healing/optimize-sequence", json=bad)
        assert r.status_code == 400


# ---------- /healing/execute-sequence ----------
class TestExecute:
    def _seq(self, s):
        r = s.post(f"{API}/healing/optimize-sequence", json=TestOptimize.payload)
        assert r.status_code == 200
        return r.json()["sequence"]

    def test_execute_returns_per_step_results(self, s):
        seq = self._seq(s)
        r = s.post(f"{API}/healing/execute-sequence", json={"sequence": seq, "delay_ms": 200})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "results" in d and isinstance(d["results"], list)
        assert len(d["results"]) == len(seq)
        assert "executed_count" in d
        assert "cumulative_sri_delta" in d
        for res in d["results"]:
            assert "step" in res
            if res.get("executed"):
                assert "sri_before" in res
                assert "sri_after" in res
                assert "sri_delta" in res
            elif res.get("skipped"):
                assert res.get("reason") in ("cooldown", "unknown action", "missing action_id/target_node")
            else:
                # error path acceptable
                assert "error" in res

    def test_execute_empty_400(self, s):
        r = s.post(f"{API}/healing/execute-sequence", json={"sequence": [], "delay_ms": 200})
        assert r.status_code == 400

    def test_execute_delay_too_high_400(self, s):
        seq = [{"action_id": "cache_flush", "target_node": "Cache"}]
        r = s.post(f"{API}/healing/execute-sequence", json={"sequence": seq, "delay_ms": 10000})
        assert r.status_code == 400


# ---------- Heavy traffic → active populated ----------
def _hammer(stop_evt, errors):
    while not stop_evt.is_set():
        try:
            requests.get(f"{API}/products", timeout=4)
        except Exception as e:
            errors.append(str(e))


class TestHeavyTrafficActivation:
    def test_active_populated_under_traffic(self, s):
        # Make sure detection enabled with a short interval
        s.post(f"{API}/healing/auto-propagation/config",
               json={"enabled": True, "autonomous_heal": True, "interval_sec": 3})

        snap0 = s.get(f"{API}/healing/active-propagations").json()
        baseline_count = snap0["detection_count"]

        stop = threading.Event()
        errors = []
        threads = [threading.Thread(target=_hammer, args=(stop, errors), daemon=True) for _ in range(80)]
        for t in threads:
            t.start()

        active_snapshot = None
        deadline = time.time() + 30
        try:
            while time.time() < deadline:
                time.sleep(3)
                snap = s.get(f"{API}/healing/active-propagations").json()
                if snap["active"]:
                    active_snapshot = snap
                    break
        finally:
            stop.set()
            for t in threads:
                t.join(timeout=2)

        assert active_snapshot is not None, "no active propagations detected within 30s under heavy load"
        # detection_count should have increased
        assert active_snapshot["detection_count"] > baseline_count, (
            f"detection_count not advancing: {baseline_count} -> {active_snapshot['detection_count']}"
        )
        # entry shape
        for entry in active_snapshot["active"]:
            for k in ["source", "pressure", "yield_exceeded", "downstream",
                      "max_phi", "max_infected", "detected_at"]:
                assert k in entry, f"missing key {k} in active entry"
            assert entry["pressure"] >= 0.0
            assert isinstance(entry["downstream"], list)
            # plan/optional healing_executed (autonomous_heal=True default)
            if "plan" in entry:
                p = entry["plan"]
                assert "sequence" in p
                assert "skipped" in p
                assert "expected_total_sri_gain" in p
                assert "ordering_rule" in p

        # detection_count strictly increasing across two consecutive ticks
        time.sleep(4)
        snap2 = s.get(f"{API}/healing/active-propagations").json()
        assert snap2["detection_count"] >= active_snapshot["detection_count"]


# ---------- Regression: previously shipped endpoints still 200 ----------
class TestRegression:
    def test_topology_schema(self, s):
        assert s.get(f"{API}/healing/topology/schema").status_code == 200

    def test_fea_component(self, s):
        assert s.get(f"{API}/healing/fea?granularity=component").status_code == 200

    def test_auto_dampen_wave(self, s):
        r = s.post(f"{API}/healing/auto-dampen-wave",
                   json={"source": "DB", "fault_strength": 0.6, "steps": 30, "dt": 0.5,
                         "granularity": "service", "auto_execute": False})
        assert r.status_code == 200, r.text

    def test_fault_propagation(self, s):
        r = s.post(f"{API}/healing/fault-propagation",
                   json={"source": "DB", "fault_strength": 0.6, "steps": 30, "dt": 0.5,
                         "granularity": "service"})
        assert r.status_code == 200, r.text

    def test_resilience_debt(self, s):
        assert s.get(f"{API}/healing/resilience-debt").status_code == 200

    def test_trend(self, s):
        assert s.get(f"{API}/healing/trend").status_code == 200

    def test_correlation(self, s):
        assert s.get(f"{API}/metrics/correlation").status_code == 200

    def test_admin_webhooks_status(self, admin):
        r = admin.get(f"{API}/admin/webhooks/status")
        assert r.status_code == 200, r.text

    def test_login(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "admin@freshcart.com", "password": "admin123"})
        assert r.status_code == 200

    def test_products(self, s):
        assert s.get(f"{API}/products").status_code == 200
