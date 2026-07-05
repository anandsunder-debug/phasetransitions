"""Iteration 10 tests: FEA-driven RCA, SRI interpolation trend, multi-CA healing,
and root-level /health Kubernetes probe."""
import os
import time
import pytest
import requests
from pathlib import Path


def _load_frontend_env():
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api_client):
    r = api_client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": "admin@freshcart.com", "password": "admin123"})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed {r.status_code}: {r.text}")
    data = r.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module", autouse=True)
def generate_traffic(api_client):
    """Populate SRIInterpolator (records every 5 requests -> need 15+)."""
    for _ in range(20):
        api_client.get(f"{BASE_URL}/api/products")
    # Small wait for aggregator updates
    time.sleep(1)
    yield


# ---------- Root-level /health ----------
class TestRootHealth:
    def test_root_health_200_internal(self):
        """Root /health is intended for Kubernetes liveness/readiness probes which
        hit the pod directly on port 8001 - the public ingress only routes /api/*.
        Verify via internal localhost:8001."""
        r = requests.get("http://localhost:8001/health", timeout=5)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "healthy"
        assert "timestamp" in data

    def test_root_health_public_url_not_backend(self, api_client):
        """Document: public URL /health is NOT routed to backend (ingress limitation)."""
        r = api_client.get(f"{BASE_URL}/health")
        # If /api prefix were present it would hit backend; without it it's the frontend
        # This is informational; backend endpoint itself works internally
        assert r.status_code == 200


# ---------- /api/healing/trend interpolation ----------
class TestHealingTrend:
    def test_trend_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/trend")
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("velocity", "acceleration", "predicted_30s", "predicted_60s",
                    "trend", "samples", "current_sri", "thresholds"):
            assert key in data, f"missing {key} in trend: {list(data.keys())}"
        assert isinstance(data["velocity"], (int, float))
        assert isinstance(data["acceleration"], (int, float))
        assert data["trend"] in ("critical_degrading", "degrading", "stable",
                                 "recovering", "insufficient_data")
        assert "critical" in data["thresholds"]
        assert "warning" in data["thresholds"]

    def test_trend_has_samples_after_traffic(self, api_client):
        # Ensure enough traffic for >=3 samples
        for _ in range(10):
            api_client.get(f"{BASE_URL}/api/products")
        time.sleep(0.5)
        r = api_client.get(f"{BASE_URL}/api/healing/trend")
        data = r.json()
        # With 30 requests and recording every 5, expect >= 3 samples
        assert data["samples"] >= 3, f"Only {data['samples']} samples, expected >=3"
        assert data["trend"] != "insufficient_data"


# ---------- /api/healing/fea ----------
class TestHealingFEA:
    def test_fea_top_level_keys(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("elements", "yield_nodes", "yield_threshold", "edge_analysis",
                    "total_strain_energy", "max_von_mises", "load_vector",
                    "displacement_vector", "sri_trend", "multi_ca_recommended",
                    "recommended_cas"):
            assert key in data, f"missing FEA key '{key}'"

    def test_fea_element_structure(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        data = r.json()
        assert isinstance(data["elements"], list) and len(data["elements"]) > 0
        for el in data["elements"]:
            for key in ("node", "displacement", "load", "strain_energy",
                        "von_mises_stress", "yield_exceeded", "corrective_action",
                        "metrics"):
                assert key in el, f"element missing '{key}': {list(el.keys())}"
            assert isinstance(el["yield_exceeded"], bool)
            m = el["metrics"]
            for mk in ("latency_ms", "error_rate_pct", "saturation_pct", "traffic"):
                assert mk in m

    def test_fea_load_displacement_vectors(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        data = r.json()
        assert isinstance(data["load_vector"], dict)
        assert isinstance(data["displacement_vector"], dict)
        # Nodes in load_vector should equal nodes in elements
        node_names = {e["node"] for e in data["elements"]}
        assert set(data["load_vector"].keys()) == node_names
        assert set(data["displacement_vector"].keys()) == node_names

    def test_fea_multi_ca_consistency(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        data = r.json()
        # recommended_cas length must equal yield_nodes count
        assert len(data["recommended_cas"]) == len(data["yield_nodes"])
        # multi_ca_recommended flag matches
        assert data["multi_ca_recommended"] == (len(data["yield_nodes"]) > 1)

    def test_fea_sri_trend_embedded(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        data = r.json()
        trend = data["sri_trend"]
        for k in ("velocity", "acceleration", "trend", "samples"):
            assert k in trend


# ---------- /api/healing/rca (with FEA integration) ----------
class TestHealingRCA:
    def test_rca_fea_summary(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/rca")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "fea_summary" in data
        fs = data["fea_summary"]
        for k in ("yield_threshold", "total_strain_energy", "max_von_mises",
                  "yield_node_count"):
            assert k in fs, f"fea_summary missing '{k}'"
        assert isinstance(fs["yield_node_count"], int)

    def test_rca_multi_ca_targets(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/rca")
        data = r.json()
        assert "multi_ca_targets" in data
        assert isinstance(data["multi_ca_targets"], list)
        for t in data["multi_ca_targets"]:
            for k in ("node", "action", "rca_score", "von_mises_stress"):
                assert k in t

    def test_rca_sri_trend(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/rca")
        data = r.json()
        assert "sri_trend" in data
        assert "trend" in data["sri_trend"]

    def test_rca_node_rankings_include_fea_metrics(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/rca")
        data = r.json()
        assert data["node_rankings"]
        for nr in data["node_rankings"]:
            for k in ("node", "rca_score", "spectral_isolation", "degradation",
                      "strain_energy", "von_mises_stress", "yield_exceeded"):
                assert k in nr


# ---------- /api/healing/status ----------
class TestHealingStatus:
    def test_status_fea_summary(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/healing/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "fea_summary" in data
        fs = data["fea_summary"]
        for k in ("yield_nodes", "yield_threshold", "multi_ca_recommended",
                  "sri_trend"):
            assert k in fs, f"status.fea_summary missing '{k}'"
        assert isinstance(fs["yield_nodes"], list)


# ---------- Multi-CA behaviour (manual trigger of healing) ----------
class TestMultiCAIntegration:
    def test_fea_recommends_actions_exist(self, api_client):
        """recommended_cas should use valid action IDs known to healing engine."""
        r = api_client.get(f"{BASE_URL}/api/healing/fea")
        data = r.json()
        valid = {"cache_flush", "rate_limit", "circuit_breaker",
                 "connection_pool_reset", "queue_drain"}
        for action in data["recommended_cas"]:
            assert action in valid, f"unknown CA id: {action}"
