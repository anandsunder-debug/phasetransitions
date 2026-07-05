"""Iteration 19 — Frontend as full participant in SRI, RUM beacon endpoint,
topology schema with 6 services, FEA reflecting Frontend stress, fault
propagation from Frontend, etc.

Run:
  pytest /app/backend/tests/test_iteration19_frontend_sri.py -v
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://delivery-metrics-hub-1.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_TEST_EMAIL", "admin@freshcart.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_TEST_PASSWORD", "admin123")


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_session(api):
    """Authenticated admin session via httpOnly cookie."""
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return api


# ---------- Topology schema (6 services + Frontend↔API + fine edges) ----------
class TestTopologySchema:
    def test_schema_includes_frontend(self, api):
        r = api.get(f"{BASE_URL}/api/healing/topology/schema")
        assert r.status_code == 200, r.text
        data = r.json()
        names = [s["name"] for s in data["services"]]
        assert names == ["Frontend", "API", "Cache", "DB", "Queue", "Backend"], names
        assert len(data["services"]) == 6

    def test_frontend_api_inter_edge(self, api):
        r = api.get(f"{BASE_URL}/api/healing/topology/schema")
        edges = [tuple(e) for e in r.json()["inter_edges"]]
        assert ("Frontend", "API") in edges, edges

    def test_frontend_components(self, api):
        r = api.get(f"{BASE_URL}/api/healing/topology/schema")
        comps = r.json()["components"]
        assert "Frontend" in comps
        assert set(comps["Frontend"]) == {
            "Frontend.page_load", "Frontend.render",
            "Frontend.api_calls", "Frontend.js_errors",
        }

    def test_fine_edges_frontend_to_api(self, api):
        r = api.get(f"{BASE_URL}/api/healing/topology/schema")
        edges = [tuple(e) for e in r.json()["fine_edges"]]
        # at least one Frontend.api_calls -> API.* mapping
        f2api = [e for e in edges if e[0] == "Frontend.api_calls" and e[1].startswith("API.")]
        assert len(f2api) >= 1, f"Expected Frontend.api_calls -> API.* edges, got {f2api}"


# ---------- /api/rum/beacon ----------
class TestRumBeacon:
    def test_beacon_basic(self, api):
        body = {
            "page": "/dashboard",
            "page_load_ms": 850,
            "first_contentful_paint_ms": 300,
            "largest_contentful_paint_ms": 780,
            "long_tasks_count": 1,
            "api_calls": [{"path": "/api/products", "duration_ms": 120, "status": 200}],
            "js_errors": [],
        }
        r = api.post(f"{BASE_URL}/api/rum/beacon", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "frontend_metrics_now" in data
        fm = data["frontend_metrics_now"]
        for k in ("traffic", "latency", "error", "saturation"):
            assert k in fm, f"Missing {k} in frontend_metrics_now"
        assert "received" in data
        assert data["received"]["page_load_ms"] == 850
        assert data["received"]["api_calls"] == 1

    def test_empty_beacon_does_not_crash(self, api):
        r = api.post(f"{BASE_URL}/api/rum/beacon", json={})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

    def test_beacon_clamps_huge_page_load(self, api):
        # 100s page_load_ms — record latency capped at 8s
        r = api.post(f"{BASE_URL}/api/rum/beacon", json={"page_load_ms": 100000})
        assert r.status_code == 200
        data = r.json()
        # latency in ms (latency_s capped at 8.0 → 8000ms)
        assert data["frontend_metrics_now"]["latency"] <= 8001, data["frontend_metrics_now"]


# ---------- FEA reflects Frontend stress after bad beacons ----------
class TestFEAFromRum:
    def test_bad_beacons_drive_frontend_stress(self, api):
        for _ in range(5):  # extra beacons help saturation
            api.post(f"{BASE_URL}/api/rum/beacon", json={
                "page": "/x",
                "page_load_ms": 2500,
                "api_calls": [
                    {"path": "/api/products", "duration_ms": 2200, "status": 500, "error": True},
                    {"path": "/api/cart", "duration_ms": 2100, "status": 500, "error": True},
                ],
                "js_errors": [{"message": "TypeError"}],
            })
        time.sleep(0.5)
        r = api.get(f"{BASE_URL}/api/healing/fea?granularity=service")
        assert r.status_code == 200, r.text
        data = r.json()
        services = data.get("services") or []
        front = None
        for n in services:
            if isinstance(n, dict) and (n.get("service") == "Frontend" or n.get("node") == "Frontend"):
                front = n
                break
        assert front is not None, f"Frontend service not in FEA. services: {[s.get('service') for s in services]}"
        vm = front.get("von_mises_stress", 0)
        assert vm > 0.05, f"Frontend stress too low: {vm}"


# ---------- /api/metrics/real includes Frontend ----------
class TestMetricsRealIncludesFrontend:
    def test_metrics_real_has_frontend(self, api):
        r = api.get(f"{BASE_URL}/api/metrics/real")
        assert r.status_code == 200, r.text
        data = r.json()
        nodes = data.get("nodes") or []
        assert isinstance(nodes, list) and len(nodes) >= 1
        ids = [n.get("id") if isinstance(n, dict) else n for n in nodes]
        assert "Frontend" in ids, f"Frontend missing from /api/metrics/real nodes ids={ids}"


# ---------- Fault propagation from Frontend ----------
class TestFaultPropagationFrontend:
    def test_propagation_frontend_source(self, api):
        body = {
            "source": "Frontend",
            "granularity": "service",
            "fault_strength": 1.0,
            "steps": 8,
            "critical_arrival_threshold": 0.3,
        }
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mesh_size") == 6, data.get("mesh_size")
        node_summary = data.get("node_summary") or []
        assert len(node_summary) >= 1
        first = node_summary[0]
        assert first.get("is_source") is True, first
        assert first.get("node") == "Frontend", first
        # timeline must show propagation
        assert "timeline" in data
        assert len(data["timeline"]) > 0


# ---------- Auto-dampen wave from Frontend ----------
class TestAutoDampenFrontend:
    def test_autodampen_arrests_wave(self, api):
        body = {
            "source": "Frontend",
            "granularity": "service",
            "fault_strength": 1.0,
            "steps": 12,
            "critical_arrival_threshold": 0.05,
            "auto_execute": False,
        }
        r = api.post(f"{BASE_URL}/api/healing/auto-dampen-wave", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("wave_arrested") is True, data
        cut = data.get("cut_edge")
        # cut_edge can be a dict {source, target, ...} or a list
        if isinstance(cut, dict):
            cut_nodes = [cut.get("source"), cut.get("target")]
        else:
            cut_nodes = list(cut or [])
        # cut_edge involves Frontend or API (the upstream of the wave)
        assert any(n in ("Frontend", "API") for n in cut_nodes), f"cut_edge unexpected: {cut}"
        action = data.get("recommended_action", {})
        valid_actions = {"rate_limit", "circuit_breaker", "cache_flush",
                         "connection_pool_reset", "queue_drain", "scale_out"}
        assert action.get("action_id") in valid_actions, action


# ---------- Regression checks on previous endpoints ----------
class TestRegression:
    def test_active_propagations(self, api):
        r = api.get(f"{BASE_URL}/api/healing/active-propagations")
        assert r.status_code == 200

    def test_optimize_sequence(self, api):
        body = {
            "stressed_nodes": [
                {"node": "API", "stress": 0.7},
                {"node": "DB", "stress": 0.6},
            ],
            "granularity": "service",
        }
        r = api.post(f"{BASE_URL}/api/healing/optimize-sequence", json=body)
        assert r.status_code == 200, r.text

    def test_cx_metrics(self, api):
        r = api.get(f"{BASE_URL}/api/cx/metrics")
        assert r.status_code == 200

    def test_synthetic_user(self, api):
        r = api.post(f"{BASE_URL}/api/cx/synthetic-user/run")
        assert r.status_code == 200

    def test_correlation(self, api):
        r = api.get(f"{BASE_URL}/api/metrics/correlation")
        assert r.status_code == 200

    def test_login(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200

    def test_products(self, api):
        r = api.get(f"{BASE_URL}/api/products")
        assert r.status_code == 200
