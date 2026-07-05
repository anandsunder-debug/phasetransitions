"""Iteration 15 tests: fault propagation, non-recoverable detector,
resilience debt, cascade-risk on edges.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://delivery-metrics-hub-1.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_client(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@freshcart.com",
        "password": "admin123",
    })
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text}")
    token = r.json().get("access_token") or r.json().get("token")
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    # also keep cookies from login response
    for c in api.cookies:
        s.cookies.set(c.name, c.value)
    return s


# ---------------- Fault propagation ----------------
class TestFaultPropagation:
    def test_service_level_API_source(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "API", "fault_strength": 1.0, "steps": 15, "granularity": "service",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "API"
        assert d["granularity"] == "service"
        assert d["mesh_size"] == 5
        assert d["steps"] == 15
        assert len(d["timeline"]) == 16
        for entry in d["timeline"]:
            assert {"step", "t", "x", "phi", "infected_count"}.issubset(entry.keys())
            assert isinstance(entry["x"], dict)
        assert len(d["node_summary"]) == 5
        peaks = [n["peak_fault"] for n in d["node_summary"]]
        assert peaks == sorted(peaks, reverse=True)
        for n in d["node_summary"]:
            assert {"node", "peak_fault", "first_arrival_step", "first_arrival_t", "is_source"}.issubset(n.keys())
        source_row = [n for n in d["node_summary"] if n["is_source"]][0]
        assert source_row["node"] == "API"
        assert d["max_phi"] > 0
        assert d["total_phi"] > 0
        assert d["max_infected"] >= 1

    def test_component_level_DB_orders(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "DB.orders", "fault_strength": 1.0, "steps": 20, "granularity": "component",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mesh_size"] == 19
        arrivals = {n["node"]: n["first_arrival_step"] for n in d["node_summary"]}
        # source itself arrives at step 0
        assert arrivals["DB.orders"] == 0
        # direct neighbors (per fine_edges from DB.orders): DB.users, DB.metrics, DB.products, API.orders
        direct = ["DB.users", "DB.metrics", "DB.products", "API.orders"]
        for name in direct:
            assert arrivals.get(name) is not None, f"{name} never arrived"
            assert arrivals[name] <= 5, f"{name} should arrive quickly, got step={arrivals[name]}"
        # some distant component (Backend.analytics) should arrive later OR be larger step
        backend_analytics = arrivals.get("Backend.analytics")
        if backend_analytics is not None:
            assert backend_analytics > max(arrivals[n] for n in direct)

    def test_invalid_source(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "NotAService", "fault_strength": 1.0, "steps": 10, "granularity": "service",
        })
        assert r.status_code == 400
        assert "unknown source" in r.json().get("detail", "").lower()

    def test_invalid_granularity(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "API", "fault_strength": 1.0, "steps": 10, "granularity": "foo",
        })
        assert r.status_code == 400

    def test_invalid_steps(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "API", "fault_strength": 1.0, "steps": 500, "granularity": "service",
        })
        assert r.status_code == 400

    def test_invalid_fault_strength(self, api):
        r = api.post(f"{BASE_URL}/api/healing/fault-propagation", json={
            "source": "API", "fault_strength": 2.0, "steps": 10, "granularity": "service",
        })
        assert r.status_code == 400


# ---------------- Non-recoverable in /healing/trend ----------------
class TestNonRecoverableTrend:
    def test_trend_always_has_non_recoverable_keys(self, api):
        r = api.get(f"{BASE_URL}/api/healing/trend")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "non_recoverable" in d
        assert isinstance(d["non_recoverable"], bool)
        assert "non_recoverable_criterion" in d
        c = d["non_recoverable_criterion"]
        for k in ("plateau", "plateau_eps", "sustained_below_threshold", "sri_threshold"):
            assert k in c, f"missing {k} in non_recoverable_criterion"


# ---------------- Resilience debt ----------------
class TestResilienceDebt:
    def test_snapshot_shape(self, api):
        r = api.get(f"{BASE_URL}/api/healing/resilience-debt")
        assert r.status_code == 200, r.text
        d = r.json()
        required = {
            "energy_integral_phi", "cost_total_usd", "current_phi", "current_sri",
            "instantaneous_cost_per_sec", "samples", "cost_per_phi_sec", "interpretation",
        }
        assert required.issubset(d.keys()), f"missing: {required - d.keys()}"

    def test_cost_grows_with_traffic(self, api):
        snap1 = api.get(f"{BASE_URL}/api/healing/resilience-debt").json()
        # drive traffic
        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                api.get(f"{BASE_URL}/api/products", timeout=5)
            except Exception:
                pass
            time.sleep(0.3)
        snap2 = api.get(f"{BASE_URL}/api/healing/resilience-debt").json()
        assert snap2["samples"] >= snap1["samples"], (
            f"samples did not increase: {snap1['samples']} -> {snap2['samples']}"
        )
        assert snap2["cost_total_usd"] >= snap1["cost_total_usd"], (
            f"cost did not grow: {snap1['cost_total_usd']} -> {snap2['cost_total_usd']}"
        )


# ---------------- Cascade risk on edges ----------------
class TestCascadeRisk:
    def test_service_edge_analysis_has_cascade_risk(self, api):
        r = api.get(f"{BASE_URL}/api/healing/fea?granularity=service")
        assert r.status_code == 200, r.text
        d = r.json()
        ea = d.get("edge_analysis", [])
        assert len(ea) > 0, "no edges returned"
        for e in ea:
            assert "cascade_risk" in e, f"missing cascade_risk: {e}"
            cr = float(e["cascade_risk"])
            assert 0.0 <= cr <= 1.0, f"cascade_risk out of [0,1]: {cr}"

    def test_component_path_analysis_has_cascade_risk(self, api):
        r = api.get(f"{BASE_URL}/api/healing/fea?granularity=component")
        assert r.status_code == 200, r.text
        d = r.json()
        pa = d.get("path_analysis") or d.get("edge_analysis") or []
        assert len(pa) > 0, "no component edges/paths returned"
        for e in pa:
            assert "cascade_risk" in e, f"missing cascade_risk in: {e}"
            assert 0.0 <= float(e["cascade_risk"]) <= 1.0


# ---------------- Regressions ----------------
class TestRegressions:
    def test_topology_schema(self, api):
        r = api.get(f"{BASE_URL}/api/healing/topology/schema")
        assert r.status_code == 200
        assert r.json().get("version") == 1

    def test_fea_component_nested(self, api):
        r = api.get(f"{BASE_URL}/api/healing/fea?granularity=component")
        assert r.status_code == 200
        d = r.json()
        svcs = d.get("services") or d.get("elements") or []
        assert any("components" in s for s in svcs), "components not nested at granularity=component"

    def test_admin_webhooks_status(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/webhooks/status")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "configured" in d

    def test_auth_login(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@freshcart.com", "password": "admin123",
        })
        assert r.status_code == 200

    def test_products(self, api):
        r = api.get(f"{BASE_URL}/api/products")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
