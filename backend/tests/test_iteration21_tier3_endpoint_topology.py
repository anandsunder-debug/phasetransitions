"""
Iteration 21 — Tier-3 endpoint granularity for FEA topology.

Verifies:
  * /api/healing/topology/schema exposes version=2 + tier_counts + endpoints + endpoint_edges
  * /api/healing/fea supports granularity in {service, component, endpoint}
  * /api/healing/fault-propagation supports granularity='endpoint' (mesh_size=101)
  * /api/healing/auto-dampen-wave granularity='endpoint' — explicit rejection acceptable
  * Existing service-tier endpoints still return 200
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TIMEOUT = 30


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- topology/schema (tier-3 surface) ----------
class TestTopologySchema:
    def test_schema_version_and_counts(self, client):
        r = client.get(f"{BASE_URL}/api/healing/topology/schema", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d.get("version") == 2, f"expected version=2, got {d.get('version')}"
        tc = d.get("tier_counts") or {}
        assert tc.get("services") == 6
        assert tc.get("components") == 46
        assert tc.get("endpoints") == 101

    def test_schema_keys_present(self, client):
        d = client.get(f"{BASE_URL}/api/healing/topology/schema", timeout=TIMEOUT).json()
        for k in ["services", "inter_edges", "components", "fine_edges",
                  "endpoints", "endpoint_edges", "tier_counts", "version"]:
            assert k in d, f"missing schema key: {k}"

    def test_schema_edge_counts(self, client):
        d = client.get(f"{BASE_URL}/api/healing/topology/schema", timeout=TIMEOUT).json()
        # spec: fine_edges ~84 (up from 26), endpoint_edges ~139
        fe = len(d["fine_edges"])
        ee = len(d["endpoint_edges"])
        ie = len(d["inter_edges"])
        assert fe >= 60, f"fine_edges too small: {fe}"
        assert ee >= 100, f"endpoint_edges too small: {ee}"
        assert ie == 8, f"inter_edges expected 8, got {ie}"

    def test_schema_components_and_endpoints_shape(self, client):
        d = client.get(f"{BASE_URL}/api/healing/topology/schema", timeout=TIMEOUT).json()
        # components is dict service -> [components]
        comps = d["components"]
        assert isinstance(comps, dict)
        total_comp = sum(len(v) for v in comps.values())
        assert total_comp == 46, f"flattened components != 46: {total_comp}"
        for svc, lst in comps.items():
            assert 6 <= len(lst) <= 9, f"service {svc} has {len(lst)} components (expected 6-9)"
        # endpoints is dict component -> [endpoints]
        eps = d["endpoints"]
        assert isinstance(eps, dict)
        total_ep = sum(len(v) for v in eps.values())
        assert total_ep == 101, f"flattened endpoints != 101: {total_ep}"
        for comp, lst in eps.items():
            assert 1 <= len(lst) <= 4, f"component {comp} has {len(lst)} endpoints (expected 1-4)"


# ---------- /api/healing/fea ----------
class TestFEAGranularity:
    def test_service_no_regression(self, client):
        r = client.get(f"{BASE_URL}/api/healing/fea?granularity=service", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["granularity"] == "service"
        assert len(d["services"]) == 6

    def test_component_granularity(self, client):
        d = client.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=TIMEOUT).json()
        assert d["granularity"] == "component"
        assert d.get("mesh_size_fine") == 46
        total = sum(len(s.get("components", [])) for s in d["services"])
        assert total == 46, f"sum(comps) != 46: {total}"
        for s in d["services"]:
            assert 6 <= len(s["components"]) <= 9
            assert "intra_edges" in s
            assert isinstance(s["intra_edges"], list)
            for c in s["components"]:
                for f in ["component", "short_name", "von_mises_stress",
                          "service_pressure", "strain_energy", "yield_exceeded",
                          "load", "displacement", "metrics"]:
                    assert f in c, f"component missing field {f}"

    def test_endpoint_granularity(self, client):
        d = client.get(f"{BASE_URL}/api/healing/fea?granularity=endpoint", timeout=TIMEOUT).json()
        assert d["granularity"] == "endpoint"
        assert d.get("mesh_size_fine") == 46
        assert d.get("mesh_size_endpoint") == 101
        assert len(d["services"]) == 6
        total_ep = 0
        for s in d["services"]:
            for c in s["components"]:
                assert "endpoints" in c, f"component {c.get('component')} missing endpoints"
                assert "endpoint_edges" in c
                eps = c["endpoints"]
                assert 1 <= len(eps) <= 4, f"{c['component']} has {len(eps)} eps"
                total_ep += len(eps)
                for ep in eps:
                    for f in ["endpoint", "short_name", "von_mises_stress",
                              "service_pressure", "strain_energy", "yield_exceeded",
                              "load", "displacement", "metrics"]:
                        assert f in ep, f"endpoint missing field {f}"
                    # loose value tolerances (probabilistic)
                    assert ep["von_mises_stress"] >= 0
                    assert ep["strain_energy"] >= 0
                    m = ep["metrics"]
                    for mk in ["latency_ms", "error_rate_pct", "saturation_pct", "traffic"]:
                        assert mk in m
        assert total_ep == 101, f"sum(endpoints) != 101: {total_ep}"


# ---------- /api/healing/fault-propagation ----------
class TestFaultPropagation:
    def test_endpoint_fault_prop(self, client):
        body = {"source": "API.auth.login", "granularity": "endpoint", "steps": 10}
        r = client.post(f"{BASE_URL}/api/healing/fault-propagation", json=body, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["granularity"] == "endpoint"
        assert d["mesh_size"] == 101
        tl = d["timeline"]
        assert len(tl) == 11  # steps 0..10
        # diffusion: by step 10 should infect >= 20
        last = tl[-1]
        assert last.get("infected_count", 0) >= 20, \
            f"infected at step 10 = {last.get('infected_count')}, expected >=20"

    def test_component_fault_prop_regression(self, client):
        body = {"source": "Frontend.page_load", "granularity": "component", "steps": 30}
        r = client.post(f"{BASE_URL}/api/healing/fault-propagation", json=body, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["granularity"] == "component"
        assert d["mesh_size"] == 46
        assert len(d["timeline"]) == 31


# ---------- /api/healing/auto-dampen-wave (tier-3 acceptance) ----------
class TestDampenWaveTier3:
    def test_dampen_endpoint_response(self, client):
        # spec accepts EITHER a computed dampening response OR explicit error.
        body = {"source": "API.auth.login", "granularity": "endpoint"}
        r = client.post(f"{BASE_URL}/api/healing/auto-dampen-wave", json=body, timeout=TIMEOUT)
        # accept 200 (supported) or 400 (explicit reject)
        assert r.status_code in (200, 400), f"unexpected status {r.status_code}"
        body_j = r.json()
        if r.status_code == 400:
            assert "detail" in body_j
            # documented response
            assert "service" in body_j["detail"] or "component" in body_j["detail"]


# ---------- Existing service-tier endpoints still healthy ----------
@pytest.mark.parametrize("path", [
    "/api/metrics/real",
    "/api/healing",
    "/api/healing/topology",
    "/api/cx/metrics",
])
def test_existing_endpoints_no_regression(client, path):
    r = client.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    # body parses as JSON
    _ = r.json()
