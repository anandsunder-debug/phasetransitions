"""
Iteration 18 — Customer Experience metrics + Synthetic User journey.
Covers: GET /api/cx/metrics shape & boundaries, POST /api/cx/synthetic-user/run
shape & verdict, recent_journeys cap, perceived_speed scoring, and regression
on previous endpoints.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN_EMAIL = os.environ.get("ADMIN_TEST_EMAIL", "admin@freshcart.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_TEST_PASSWORD", "admin123")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                     timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    return session


# ==================== /api/cx/metrics shape ====================

class TestCxMetricsShape:
    def test_metrics_default_window(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ["window_seconds", "samples", "series", "current",
                    "rolling_30s", "annotations", "recent_journeys"]:
            assert key in data, f"missing key: {key}"
        assert data["window_seconds"] == 300
        assert isinstance(data["series"], list)
        assert isinstance(data["annotations"], list)
        assert isinstance(data["recent_journeys"], list)

    def test_metrics_custom_window(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics",
                        params={"window_seconds": 60}, timeout=15)
        assert r.status_code == 200
        assert r.json()["window_seconds"] == 60

    def test_metrics_window_too_small(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics",
                        params={"window_seconds": 10}, timeout=15)
        assert r.status_code == 400

    def test_metrics_window_too_large(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics",
                        params={"window_seconds": 5000}, timeout=15)
        assert r.status_code == 400

    def test_rolling30s_keys_present(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics", timeout=15)
        r30 = r.json()["rolling_30s"]
        for k in ["page_load_ms", "add_to_cart_ms", "checkout_ms",
                  "error_shown_rate", "perceived_speed", "conversion"]:
            assert k in r30, f"rolling_30s missing key: {k}"

    def test_series_entry_keys(self, session):
        # Wait briefly for at least 1 sample to populate via background loop
        for _ in range(8):
            r = session.get(f"{BASE_URL}/api/cx/metrics", timeout=15)
            series = r.json()["series"]
            if series:
                entry = series[-1]
                for k in ["t", "page_load_ms", "add_to_cart_ms",
                          "checkout_ms", "error_shown_rate", "conversion",
                          "perceived_speed"]:
                    assert k in entry, f"series entry missing key: {k}"
                return
            time.sleep(2)
        pytest.skip("No CX series samples produced within wait window")

    def test_annotations_have_t_relative_and_cx_delta(self, session):
        r = session.get(f"{BASE_URL}/api/cx/metrics", timeout=15)
        anns = r.json()["annotations"]
        # If annotations exist, every entry MUST have t_relative and cx_delta dict
        for a in anns:
            assert "t_relative" in a, "annotation missing t_relative"
            assert isinstance(a["t_relative"], (int, float))
            assert "cx_delta" in a, "annotation missing cx_delta"
            d = a["cx_delta"]
            for k in ["page_load_ms_delta", "perceived_speed_delta",
                      "error_rate_delta", "samples_before", "samples_after"]:
                assert k in d, f"cx_delta missing key: {k}"


# ==================== /api/cx/synthetic-user/run ====================

class TestSyntheticUserRun:
    def test_run_synthetic_user_shape(self, session):
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run",
                         timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ["started_at", "total_ms", "total_steps", "successful_steps",
                  "errors_seen", "avg_latency_ms", "avg_perceived_speed",
                  "verdict", "verdict_color", "sri_at_run", "steps"]:
            assert k in j, f"journey missing key: {k}"
        assert j["total_steps"] >= 3
        assert 0 <= j["avg_perceived_speed"] <= 100
        assert j["verdict"] in ["delightful", "acceptable", "frustrating", "broken"]
        assert isinstance(j["verdict_color"], str) and j["verdict_color"].startswith("#")
        assert isinstance(j["steps"], list) and len(j["steps"]) == j["total_steps"]

    def test_run_synthetic_step_keys(self, session):
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=30)
        assert r.status_code == 200
        steps = r.json()["steps"]
        for s in steps:
            for k in ["name", "method", "path", "status_code", "latency_ms",
                      "perceived_speed", "success", "error", "body_preview"]:
                assert k in s, f"step missing key: {k}"

    def test_run_synthetic_completes_under_3s(self, session):
        # Budget per the agent_to_agent_context_note (≤3s)
        # Allow some network overhead since this hits public preview URL
        t0 = time.perf_counter()
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=10)
        elapsed = time.perf_counter() - t0
        assert r.status_code == 200
        j = r.json()
        # Server-internal total_ms (in-process httpx ASGITransport) should be <3s
        assert j["total_ms"] < 3000, f"in-process total_ms too high: {j['total_ms']}"
        # Wall-clock includes net hop; just ensure it's reasonable (<10s)
        assert elapsed < 10, f"wall clock too slow: {elapsed}s"

    def test_recent_journeys_capped_at_5(self, session):
        # Run twice and check len(recent_journeys) >=2 and <=5
        r1 = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        r2 = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200
        snap = session.get(f"{BASE_URL}/api/cx/metrics", timeout=10).json()
        rj = snap["recent_journeys"]
        assert len(rj) >= 2, f"expected at least 2 journeys, got {len(rj)}"
        assert len(rj) <= 5, f"recent_journeys must cap at 5, got {len(rj)}"

    def test_checkout_preview_returns_401_counted_as_error(self, session):
        # Anonymous /api/orders is expected to 401 → counted as error
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        j = r.json()
        checkout_step = next((s for s in j["steps"] if "Checkout" in s["name"]), None)
        assert checkout_step is not None, "Checkout preview step missing"
        assert checkout_step["status_code"] == 401
        assert checkout_step["success"] is False
        assert j["errors_seen"] >= 1


# ==================== perceived_speed scoring ====================

class TestPerceivedSpeedScoring:
    def test_fast_step_scores_100(self, session):
        # /api/health or /api/products is typically <200ms in-process
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        steps = r.json()["steps"]
        # find any successful step <200ms
        fast = [s for s in steps if s.get("success") and s["latency_ms"] < 200]
        for s in fast:
            assert s["perceived_speed"] == 100, \
                f"expected 100 for {s['latency_ms']}ms, got {s['perceived_speed']}"

    def test_perceived_speed_bounded(self, session):
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        for s in r.json()["steps"]:
            assert 0 <= s["perceived_speed"] <= 100

    def test_perceived_speed_linear_interp(self, session):
        # Call once and check formula on every step:
        r = session.post(f"{BASE_URL}/api/cx/synthetic-user/run", timeout=15)
        for s in r.json()["steps"]:
            lat = s["latency_ms"]
            ps = s["perceived_speed"]
            if lat <= 200:
                assert ps == 100
            elif lat >= 2000:
                assert ps == 0
            else:
                expected = round(100 * (1 - (lat - 200) / 1800), 1)
                # tolerate 1.0 due to rounding in chain
                assert abs(ps - expected) <= 1.0, \
                    f"latency={lat} ps={ps} expected≈{expected}"


# ==================== Regression: prior endpoints still 200 ====================

REGRESSION_GETS = [
    "/api/healing/topology/schema",
    "/api/healing/fea?granularity=service",
    "/api/healing/fea?granularity=component",
    "/api/healing/active-propagations",
    "/api/metrics/correlation",
    "/api/healing/resilience-debt",
    "/api/healing/trend",
    "/api/products",
]


@pytest.mark.parametrize("path", REGRESSION_GETS)
def test_regression_get_endpoints(session, path):
    r = session.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 200, f"{path} returned {r.status_code}: {r.text[:200]}"


def test_regression_auto_dampen_wave(session):
    payload = {
        "source": "API",
        "granularity": "service",
        "fault_strength": 0.5,
        "steps": 30,
        "critical_arrival_threshold": 0.4,
    }
    r = session.post(f"{BASE_URL}/api/healing/auto-dampen-wave",
                     json=payload, timeout=15)
    assert r.status_code == 200, r.text


def test_regression_optimize_sequence(session):
    payload = {
        "stressed_nodes": [
            {"node": "DB", "target_node": "DB", "action_id": "connection_pool_reset"},
            {"node": "Cache", "target_node": "Cache", "action_id": "cache_flush"},
            {"node": "Backend", "target_node": "Backend", "action_id": "circuit_breaker"},
        ]
    }
    r = session.post(f"{BASE_URL}/api/healing/optimize-sequence",
                     json=payload, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sequence" in body and "candidate_count" in body


def test_regression_execute_sequence(session):
    payload = {"sequence": [
        {"target_node": "Cache", "action_id": "cache_flush"}
    ]}
    r = session.post(f"{BASE_URL}/api/healing/execute-sequence",
                     json=payload, timeout=15)
    assert r.status_code == 200, r.text


def test_regression_admin_webhooks_status(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/webhooks/status", timeout=15)
    assert r.status_code == 200, r.text


def test_regression_auth_login(session):
    # Already validated by admin_session fixture; explicit roundtrip:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                     timeout=15)
    assert r.status_code == 200
