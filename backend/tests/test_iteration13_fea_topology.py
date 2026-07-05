"""Iteration 13 — FEA topology granularity (service vs component) tests.

Validates:
 1. Backward-compat: ?granularity=service returns flat 5-service list (no `components`).
 2. New: ?granularity=component returns hierarchical response with sub-components,
    component_yield_threshold, mesh_size_fine~19, intra_edges per service.
 3. Component fields shape (von_mises_stress, strain_energy, yield_exceeded, load,
    displacement, corrective_action, metrics{latency_ms,error_rate_pct,saturation_pct}).
 4. Domain-specific component mapping (FreshCart e-commerce).
 5. Invalid granularity defaults to 'service' (no 500).
 6. Under load, stresses are non-trivial and yield flags can fire.
 7. Regression: /api/healing/topology?granularity=fine still works.
 8. Regression for unrelated endpoints: /api/metrics/real, /metrics/reliability,
    /metrics/business, /healing/status, /auth/login, /products.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                    break
    except Exception:
        pass

assert BASE_URL, "REACT_APP_BACKEND_URL not set"

EXPECTED_MAPPING = {
    "API": {"auth", "catalog", "cart", "checkout", "orders"},
    "Cache": {"session", "product", "price"},
    "DB": {"users", "products", "orders", "metrics"},
    "Queue": {"orders", "healing", "metrics"},
    "Backend": {"sri_engine", "healing_engine", "fea_engine", "analytics"},
}


@pytest.fixture(scope="module")
def warmed_load():
    """Generate a bit of traffic so SRI/FEA isn't all-zeros."""
    for _ in range(30):
        try:
            requests.get(f"{BASE_URL}/api/products", timeout=5)
        except Exception:
            pass
    time.sleep(2)
    return True


# ------------------------------- service granularity -----------------------------
class TestFEAServiceGranularity:
    def test_default_is_service_flat(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("granularity") == "service"
        elements = data.get("elements", [])
        assert len(elements) == 5
        nodes = {e["node"] for e in elements}
        assert nodes == {"API", "Cache", "DB", "Queue", "Backend"}
        # Backward compat: service-level must NOT carry `components`
        for e in elements:
            assert "components" not in e, f"{e['node']} unexpectedly has components in service mode"

    def test_explicit_service_granularity(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=service", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["granularity"] == "service"
        for e in data["elements"]:
            assert "components" not in e

    def test_invalid_granularity_defaults_to_service(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=foo", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["granularity"] == "service"
        for e in data["elements"]:
            assert "components" not in e


# ------------------------------- component granularity ---------------------------
class TestFEAComponentGranularity:
    def test_component_response_shape(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["granularity"] == "component"
        assert "component_yield_threshold" in data
        assert "mesh_size_fine" in data
        # ~19 components total
        assert data["mesh_size_fine"] >= 18
        assert data["mesh_size_fine"] <= 22
        assert data["component_yield_threshold"] > 0

    def test_each_service_has_components_and_intra_edges(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        for e in data["elements"]:
            assert "components" in e, f"{e['node']} missing components"
            assert isinstance(e["components"], list)
            assert len(e["components"]) > 0, f"{e['node']} has empty components"
            assert "intra_edges" in e
            assert isinstance(e["intra_edges"], list)

    def test_component_field_contract(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        required = {
            "component", "short_name", "von_mises_stress", "strain_energy",
            "yield_exceeded", "load", "displacement", "corrective_action", "metrics",
        }
        metric_required = {"latency_ms", "error_rate_pct", "saturation_pct"}
        for e in data["elements"]:
            for c in e["components"]:
                missing = required - set(c.keys())
                assert not missing, f"{c.get('component')} missing keys: {missing}"
                assert isinstance(c["yield_exceeded"], bool)
                m_missing = metric_required - set(c["metrics"].keys())
                assert not m_missing, f"{c['component']} metrics missing: {m_missing}"

    def test_domain_specific_component_mapping(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        for e in data["elements"]:
            parent = e["node"]
            short_names = {c["short_name"] for c in e["components"]}
            expected = EXPECTED_MAPPING[parent]
            assert short_names == expected, (
                f"{parent} mapping mismatch: got={short_names} want={expected}"
            )

    def test_component_names_are_dotted(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        for e in data["elements"]:
            parent = e["node"]
            for c in e["components"]:
                assert c["component"].startswith(parent + "."), c["component"]
                assert c["component"].split(".")[-1] == c["short_name"]

    def test_intra_edges_stay_within_parent(self):
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        for e in data["elements"]:
            parent = e["node"]
            for ed in e["intra_edges"]:
                assert ed["source"].startswith(parent + ".")
                assert ed["target"].startswith(parent + ".")

    def test_under_load_nontrivial_stress(self, warmed_load):
        # Hit endpoints to push some saturation
        r = requests.get(f"{BASE_URL}/api/healing/fea?granularity=component", timeout=10)
        data = r.json()
        any_stress = False
        for e in data["elements"]:
            for c in e["components"]:
                if c["von_mises_stress"] > 0:
                    any_stress = True
                    break
        assert any_stress, "No component reported von_mises_stress > 0"


# ------------------------------- regression --------------------------------------
class TestRegression:
    def test_topology_fine_still_works(self):
        r = requests.get(f"{BASE_URL}/api/healing/topology?granularity=fine", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "services" in data
        assert len(data["services"]) >= 18

    def test_topology_default_service(self):
        r = requests.get(f"{BASE_URL}/api/healing/topology", timeout=10)
        assert r.status_code == 200
        assert len(r.json().get("services", [])) == 5

    def test_metrics_real(self):
        r = requests.get(f"{BASE_URL}/api/metrics/real", timeout=10)
        assert r.status_code == 200

    def test_metrics_reliability(self):
        r = requests.get(f"{BASE_URL}/api/metrics/reliability", timeout=10)
        assert r.status_code == 200

    def test_metrics_business(self):
        r = requests.get(f"{BASE_URL}/api/metrics/business", timeout=10)
        assert r.status_code == 200

    def test_healing_status(self):
        r = requests.get(f"{BASE_URL}/api/healing/status", timeout=10)
        assert r.status_code == 200

    def test_products(self):
        r = requests.get(f"{BASE_URL}/api/products", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_login(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # httpOnly-cookie auth: user payload returned in body, token in Set-Cookie
        assert data.get("email") == "admin@freshcart.com"
        assert data.get("role") == "admin"
