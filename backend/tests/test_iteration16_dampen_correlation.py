"""Iteration 16 backend tests:
- Auto-Dampen Wave: POST /api/healing/auto-dampen-wave
- SRI x Conversion correlation: GET /api/metrics/correlation
- FEA terminology + fea_equation in /api/healing/fea
- Regression on iteration 13/14/15 endpoints.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://delivery-metrics-hub-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ------------------------ FEA terminology + equation ------------------------
class TestFEATerminology:
    def test_fea_service_includes_terminology(self):
        r = requests.get(f"{API}/healing/fea", params={"granularity": "service"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "terminology" in data, "terminology dict missing"
        term = data["terminology"]
        assert isinstance(term, dict)
        assert len(term) >= 10, f"expected >=10 term pairs, got {len(term)}"
        keys = " ".join(term.keys()).lower()
        for needed in ("stress", "strain", "stiffness", "yield", "displacement", "load"):
            assert needed in keys, f"missing FEA term: {needed}"
        assert "fea_equation" in data
        eq = data["fea_equation"]
        assert "K" in eq and "u" in eq and "F" in eq and "σ" in eq

    def test_fea_component_still_works(self):
        r = requests.get(f"{API}/healing/fea", params={"granularity": "component"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "path_analysis" in data
        for p in data["path_analysis"]:
            assert "cascade_risk" in p
            assert 0.0 <= p["cascade_risk"] <= 1.0


# ------------------------ Auto-Dampen Wave ------------------------
class TestAutoDampenWave:
    def _payload(self, **over):
        base = {
            "source": "DB",
            "fault_strength": 1.0,
            "steps": 15,
            "granularity": "service",
            "critical_arrival_threshold": 0.05,
            "auto_execute": False,
        }
        base.update(over)
        return base

    def test_auto_dampen_no_execute(self):
        r = requests.post(f"{API}/healing/auto-dampen-wave", json=self._payload(), timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["wave_arrested"] is True
        ce = d["cut_edge"]
        assert {"source", "target", "cascade_risk"}.issubset(ce.keys())
        ra = d["recommended_action"]
        assert ra["action_id"] in {"cache_flush", "connection_pool_reset", "circuit_breaker", "queue_drain", "rate_limit"}
        assert ra["target_node"]
        assert ra["rationale"]
        wm = d["wave_metrics"]
        for k in ("baseline_peak_downstream", "dampened_peak_downstream", "arrest_percentage"):
            assert k in wm
        assert "t_arrest_seconds" in wm
        assert "timeline" in d["baseline"] and "timeline" in d["dampened"]
        assert d["auto_executed"] is False
        assert d["execution_result"] is None

    def test_auto_dampen_with_auto_execute_true(self):
        # Different sources map to different healing actions (DB→connection_pool_reset/circuit_breaker,
        # API→rate_limit, Cache→cache_flush, Queue→queue_drain). Try several to dodge per-action cooldowns.
        sources = ["DB", "API", "Cache", "Queue", "Backend"]
        d = None
        for source in sources:
            for attempt in range(3):
                r = requests.post(
                    f"{API}/healing/auto-dampen-wave",
                    json=self._payload(source=source, auto_execute=True),
                    timeout=60,
                )
                assert r.status_code == 200, r.text
                d = r.json()
                if not d.get("wave_arrested"):
                    break  # try next source
                er = d["execution_result"]
                assert er is not None
                if d["auto_executed"] is True:
                    for k in ("success", "sri_before", "sri_after", "sri_delta"):
                        assert k in er, f"execution_result missing {k}"
                    return
                time.sleep(8)
        pytest.fail(
            f"auto_executed never True across sources={sources} — last result={d}"
        )

    def test_auto_dampen_no_critical_arrivals(self):
        # tiny fault + huge threshold => no critical arrivals
        r = requests.post(
            f"{API}/healing/auto-dampen-wave",
            json=self._payload(fault_strength=0.01, critical_arrival_threshold=0.95),
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["wave_arrested"] is False
        assert d["reason"] == "no_critical_arrivals"
        assert d["recommended_action"] is None

    @pytest.mark.parametrize(
        "override",
        [
            {"granularity": "bogus"},
            {"steps": 0},
            {"steps": 500},
            {"fault_strength": 0},
            {"fault_strength": 1.5},
            {"critical_arrival_threshold": 0.0},
            {"critical_arrival_threshold": 1.0},
        ],
    )
    def test_auto_dampen_validation_errors(self, override):
        r = requests.post(f"{API}/healing/auto-dampen-wave", json=self._payload(**override), timeout=15)
        assert r.status_code == 400, f"expected 400 for {override}, got {r.status_code}: {r.text[:200]}"


# ------------------------ Correlation endpoint ------------------------
class TestCorrelationEndpoint:
    def test_correlation_basic_shape(self):
        r = requests.get(f"{API}/metrics/correlation", params={"window_seconds": 300}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("window_seconds", "samples", "series", "pearson_r", "annotations", "interpretation"):
            assert k in d, f"missing top-level {k}"
        assert d["window_seconds"] == 300
        assert isinstance(d["series"], list)
        assert isinstance(d["annotations"], list)
        # pearson_r is float OR null when n<3
        if d["samples"] < 3:
            assert d["pearson_r"] is None
        else:
            assert isinstance(d["pearson_r"], (int, float))
            cur = d["current"]
            for k in ("sri", "conversion", "sri_min", "sri_max", "conversion_min", "conversion_max"):
                assert k in cur

    def test_correlation_window_validation(self):
        r1 = requests.get(f"{API}/metrics/correlation", params={"window_seconds": 29}, timeout=10)
        assert r1.status_code == 400
        r2 = requests.get(f"{API}/metrics/correlation", params={"window_seconds": 3601}, timeout=10)
        assert r2.status_code == 400

    def test_correlation_populated_after_traffic_and_action(self):
        # 1) Drive traffic to populate samples (every 10 requests records a sample)
        deadline = time.time() + 35
        n_req = 0
        while time.time() < deadline and n_req < 200:
            try:
                requests.get(f"{API}/products", timeout=5)
            except requests.RequestException:
                pass
            n_req += 1
        # 2) Trigger a healing action that will be annotated. Retry until
        # we get a real auto_execute (cooldowns may block specific actions).
        executed_action = None
        for _ in range(4):
            ar = requests.post(
                f"{API}/healing/auto-dampen-wave",
                json={
                    "source": "DB",
                    "fault_strength": 1.0,
                    "steps": 15,
                    "granularity": "service",
                    "critical_arrival_threshold": 0.05,
                    "auto_execute": True,
                },
                timeout=60,
            )
            assert ar.status_code == 200
            ar_data = ar.json()
            if ar_data.get("auto_executed") is True:
                executed_action = ar_data["recommended_action"]["action_id"]
                break
            time.sleep(5)
        assert executed_action is not None, "Could not auto-execute any healing action"

        # Drive a bit more traffic to ensure post-annotation samples
        for _ in range(20):
            try:
                requests.get(f"{API}/products", timeout=5)
            except requests.RequestException:
                pass

        # 3) Verify correlation shows samples + annotations
        time.sleep(1)
        r = requests.get(f"{API}/metrics/correlation", params={"window_seconds": 600}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["samples"] > 3, f"expected samples > 3 after traffic, got {d['samples']}"
        ann_ids = [a.get("action_id") for a in d["annotations"]]
        assert executed_action in ann_ids, f"executed action {executed_action} not in annotations: {ann_ids}"
        # spot-check annotation shape
        first = d["annotations"][0]
        for k in ("action_id", "sri_before", "sri_after", "sri_delta", "t_relative", "target_node"):
            assert k in first


# ------------------------ Regression on prior iterations ------------------------
class TestRegression:
    def test_topology_schema(self):
        r = requests.get(f"{API}/healing/topology/schema", timeout=15)
        assert r.status_code == 200

    def test_fault_propagation(self):
        r = requests.post(
            f"{API}/healing/fault-propagation",
            json={"source": "API", "fault_strength": 1.0, "steps": 10, "granularity": "service"},
            timeout=30,
        )
        assert r.status_code == 200

    def test_resilience_debt(self):
        r = requests.get(f"{API}/healing/resilience-debt", timeout=15)
        assert r.status_code == 200

    def test_trend_has_non_recoverable(self):
        r = requests.get(f"{API}/healing/trend", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "non_recoverable" in d
        assert "non_recoverable_criterion" in d

    def test_admin_webhooks_status(self):
        # webhooks/status is admin-only; login first
        s = requests.Session()
        login = s.post(
            f"{API}/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"},
            timeout=15,
        )
        assert login.status_code == 200
        r = s.get(f"{API}/admin/webhooks/status", timeout=15)
        assert r.status_code == 200, r.text

    def test_auth_login(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"},
            timeout=15,
        )
        assert r.status_code == 200
        assert "token" in r.json() or "access_token" in r.json() or r.cookies

    def test_products(self):
        r = requests.get(f"{API}/products", timeout=15)
        assert r.status_code == 200
