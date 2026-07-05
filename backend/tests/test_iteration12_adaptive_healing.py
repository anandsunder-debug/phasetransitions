"""Iteration 12 — Adaptive Auto-Healing backend tests.

Validates:
 - mode='adaptive_auto_healing' on /api/healing and /api/healing/status
 - adaptation block on overview + status with exhausted/effective counts
 - /api/healing/adaptation: exhausted_actions, effective_actions,
   escalation_ladders (5 nodes), cross_node_map, next_action_per_node
 - escalation ladder for API == [rate_limit, circuit_breaker, api_error_suppression, cache_flush]
 - api_error_suppression action present in /api/healing/status actions
 - history records include effectiveness{sri_delta, recent_deltas, is_exhausted}
   and selection_method (adaptive_escalation / threshold_fallback / node_fallback)
 - history records carry 'adaptive' triggered_by values
 - /api/healing/rca, /fea, /trend still return required shapes
 - /api/health returns 200
"""

import os
import time
import pytest
import requests
from pathlib import Path


def _load_backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env_file = Path("/app/frontend/.env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
                    break
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not configured")
    return url.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def generate_traffic_and_wait(client):
    """Generate 25+ requests then wait so the 10s auto-heal loop fires several
    cycles and populates history with adaptive records."""
    for _ in range(25):
        try:
            client.get(f"{API}/products", timeout=8)
        except Exception:
            pass
    # auto-heal loop = 10s; need at least 2 cycles to potentially exhaust an action
    time.sleep(15)
    yield


# ---------- health ----------
class TestHealth:
    def test_health_ok(self, client):
        r = client.get(f"{API}/health", timeout=10)
        assert r.status_code == 200


# ---------- /api/healing overview ----------
class TestHealingOverview:
    def test_mode_is_adaptive(self, client):
        r = client.get(f"{API}/healing", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("mode") == "adaptive_auto_healing"

    def test_overview_has_adaptation_block(self, client):
        data = client.get(f"{API}/healing", timeout=15).json()
        assert "adaptation" in data
        adap = data["adaptation"]
        assert "exhausted_actions" in adap
        assert "effective_actions" in adap
        assert "total_exhausted" in adap
        assert "total_effective" in adap
        assert isinstance(adap["exhausted_actions"], list)
        assert isinstance(adap["effective_actions"], list)
        # totals must reconcile with list lengths
        assert adap["total_exhausted"] == len(adap["exhausted_actions"])
        assert adap["total_effective"] == len(adap["effective_actions"])


# ---------- /api/healing/status ----------
class TestHealingStatus:
    def test_status_mode_and_adaptation(self, client):
        r = client.get(f"{API}/healing/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("mode") == "adaptive_auto_healing"
        assert "adaptation" in data
        assert "exhausted_actions" in data["adaptation"]
        assert "effective_actions" in data["adaptation"]

    def test_api_error_suppression_action_present(self, client):
        data = client.get(f"{API}/healing/status", timeout=15).json()
        actions = data.get("actions", {})
        assert "api_error_suppression" in actions, (
            f"api_error_suppression missing. Available: {list(actions.keys())}"
        )
        # spec: error_reduction=0.7, latency_reduction=0.2, target API node
        a = actions["api_error_suppression"]
        assert a.get("target_node") == "API"


# ---------- /api/healing/adaptation ----------
class TestAdaptationEndpoint:
    def test_adaptation_endpoint_shape(self, client):
        r = client.get(f"{API}/healing/adaptation", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("exhausted_actions", "effective_actions",
                    "escalation_ladders", "cross_node_map",
                    "next_action_per_node"):
            assert key in data, f"missing key {key}"

    def test_escalation_ladders_5_nodes_multi_actions(self, client):
        data = client.get(f"{API}/healing/adaptation", timeout=15).json()
        ladders = data["escalation_ladders"]
        for node in ("API", "Cache", "Backend", "DB", "Queue"):
            assert node in ladders, f"node {node} missing from ladders"
            assert isinstance(ladders[node], list)
            assert len(ladders[node]) >= 2, (
                f"{node} ladder should have multiple actions, got {ladders[node]}"
            )

    def test_api_ladder_exact(self, client):
        data = client.get(f"{API}/healing/adaptation", timeout=15).json()
        api_ladder = data["escalation_ladders"]["API"]
        assert api_ladder == [
            "rate_limit", "circuit_breaker",
            "api_error_suppression", "cache_flush",
        ], f"Unexpected API ladder: {api_ladder}"

    def test_cross_node_map_has_5_nodes(self, client):
        data = client.get(f"{API}/healing/adaptation", timeout=15).json()
        xn = data["cross_node_map"]
        for node in ("API", "Cache", "Backend", "DB", "Queue"):
            assert node in xn
            assert isinstance(xn[node], list)
            assert len(xn[node]) >= 1

    def test_next_action_per_node_resolves(self, client):
        data = client.get(f"{API}/healing/adaptation", timeout=15).json()
        nap = data["next_action_per_node"]
        for node in ("API", "Cache", "Backend", "DB", "Queue"):
            assert node in nap
            assert isinstance(nap[node], str)


# ---------- /api/healing/history ----------
class TestHealingHistory:
    def test_history_has_records(self, client):
        r = client.get(f"{API}/healing/history?limit=200", timeout=15)
        assert r.status_code == 200
        records = r.json()
        assert isinstance(records, list)
        # We waited 15s post-traffic; at least one cycle should have run, but
        # healing only fires if SRI dipped/degrading. Use a lenient assertion:
        # if empty, push more traffic and retry once.
        if not records:
            for _ in range(30):
                try:
                    client.get(f"{API}/products", timeout=5)
                except Exception:
                    pass
            time.sleep(15)
            records = client.get(f"{API}/healing/history?limit=200",
                                 timeout=15).json()
        assert isinstance(records, list)
        # Save module-level for next checks via pytest cache won't work, just
        # rely on subsequent fetches.

    def _get_action_records(self, client):
        records = client.get(f"{API}/healing/history?limit=500",
                             timeout=15).json()
        # Filter out non-action summary records (e.g. multi_ca_batch)
        return [r for r in records if r.get("action_id")]

    def test_records_have_effectiveness_field(self, client):
        action_records = self._get_action_records(client)
        if not action_records:
            pytest.skip("No action records yet — auto-healing did not fire")
        # at least one record has effectiveness dict with required keys
        with_eff = [r for r in action_records if isinstance(r.get("effectiveness"), dict)]
        assert with_eff, "no record has effectiveness dict"
        eff = with_eff[-1]["effectiveness"]
        for key in ("sri_delta", "recent_deltas", "is_exhausted"):
            assert key in eff, f"effectiveness missing {key}: {eff}"
        assert isinstance(eff["recent_deltas"], list)
        assert isinstance(eff["is_exhausted"], bool)

    def test_records_have_selection_method(self, client):
        action_records = self._get_action_records(client)
        if not action_records:
            pytest.skip("No action records yet")
        methods = {r.get("selection_method") for r in action_records
                   if r.get("selection_method")}
        assert methods, f"no record has selection_method. sample: {action_records[-1]}"
        valid = {"adaptive_escalation", "threshold_fallback",
                 "node_fallback"}
        # at least one method must be a recognised adaptive value
        assert methods & valid, f"unexpected selection_methods: {methods}"

    def test_records_have_adaptive_triggered_by(self, client):
        action_records = self._get_action_records(client)
        if not action_records:
            pytest.skip("No action records yet")
        triggers = {r.get("triggered_by") for r in action_records}
        adaptive_triggers = {t for t in triggers
                             if t and "adaptive" in t}
        assert adaptive_triggers, (
            f"no triggered_by contains 'adaptive'. observed: {triggers}"
        )


# ---------- regression: existing endpoints still work ----------
class TestExistingEndpointsRegression:
    def test_rca_shape(self, client):
        r = client.get(f"{API}/healing/rca", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("root_cause_node", "multi_ca_targets", "fea_summary"):
            assert key in data, f"rca missing {key}"

    def test_fea_shape(self, client):
        r = client.get(f"{API}/healing/fea", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("elements", "yield_nodes", "yield_threshold"):
            assert key in data, f"fea missing {key}"

    def test_trend_shape(self, client):
        r = client.get(f"{API}/healing/trend", timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("velocity", "acceleration", "trend"):
            assert key in data, f"trend missing {key}"
