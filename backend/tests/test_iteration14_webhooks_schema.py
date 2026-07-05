"""Iteration 14 tests:
1. GET /api/healing/topology/schema (single source of truth for service mesh)
2. GET /api/admin/webhooks/status (admin only)
3. POST /api/admin/webhooks/test (admin only)
4. WebhookNotifier unit-level dispatch test against a local HTTP server
5. Regression: /api/healing/fea (service vs component), /api/healing/topology?granularity=fine,
   /api/metrics/real, /api/auth/login, /api/products
"""
import os
import sys
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://delivery-metrics-hub-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_TEST_EMAIL", "admin@freshcart.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_TEST_PASSWORD", "admin123")
USER_EMAIL = os.environ.get("USER_TEST_EMAIL", "test@freshcart.com")
USER_PASSWORD = os.environ.get("USER_TEST_PASSWORD", "testpass123")


# ---------------------------- fixtures ----------------------------

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    # Try login; if 401, register.
    r = s.post(f"{API}/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD}, timeout=10)
    if r.status_code != 200:
        s.post(f"{API}/auth/register", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD,
            "name": "Test User",
        }, timeout=10)
        r = s.post(f"{API}/auth/login", json={"email": USER_EMAIL, "password": USER_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"user login failed: {r.status_code} {r.text}"
    return s


# ============================================================
# Topology schema endpoint
# ============================================================

class TestTopologySchema:
    def test_schema_endpoint_no_auth_200(self):
        r = requests.get(f"{API}/healing/topology/schema", timeout=10)
        assert r.status_code == 200
        data = r.json()
        for k in ("services", "inter_edges", "components", "fine_edges", "version"):
            assert k in data, f"missing key {k}"
        assert data["version"] == 1

    def test_schema_services_exact(self):
        data = requests.get(f"{API}/healing/topology/schema", timeout=10).json()
        names = [s["name"] for s in data["services"]]
        assert names == ["API", "Cache", "DB", "Queue", "Backend"]
        positions = {s["name"]: s["position"] for s in data["services"]}
        assert positions["API"]["x"] == 300
        assert positions["Backend"]["x"] == 500
        assert positions["Cache"]["x"] == 110
        assert positions["DB"]["x"] == 210
        assert positions["Queue"]["x"] == 410
        # Each position has x and y
        for s in data["services"]:
            assert "x" in s["position"] and "y" in s["position"]

    def test_schema_inter_edges(self):
        data = requests.get(f"{API}/healing/topology/schema", timeout=10).json()
        assert len(data["inter_edges"]) == 5
        edges = [tuple(e) for e in data["inter_edges"]]
        for e in [("API", "Cache"), ("API", "DB"), ("API", "Queue"),
                  ("Cache", "DB"), ("Queue", "Backend")]:
            assert e in edges

    def test_schema_components_mapping(self):
        data = requests.get(f"{API}/healing/topology/schema", timeout=10).json()
        comps = data["components"]
        assert set(comps.keys()) == {"API", "Cache", "DB", "Queue", "Backend"}
        assert comps["API"] == ["API.auth", "API.catalog", "API.cart", "API.checkout", "API.orders"]
        assert comps["Cache"] == ["Cache.session", "Cache.product", "Cache.price"]
        assert comps["DB"] == ["DB.users", "DB.products", "DB.orders", "DB.metrics"]
        assert comps["Queue"] == ["Queue.orders", "Queue.healing", "Queue.metrics"]
        assert comps["Backend"] == ["Backend.sri_engine", "Backend.healing_engine", "Backend.fea_engine", "Backend.analytics"]

    def test_schema_fine_edges_count(self):
        data = requests.get(f"{API}/healing/topology/schema", timeout=10).json()
        assert len(data["fine_edges"]) == 25
        # All endpoints should reference known sub-components
        valid = set()
        for arr in data["components"].values():
            valid.update(arr)
        for a, b in data["fine_edges"]:
            assert a in valid, f"unknown edge node {a}"
            assert b in valid, f"unknown edge node {b}"


# ============================================================
# Webhook admin endpoints
# ============================================================

class TestWebhookEndpoints:
    def test_status_admin_200(self, admin_session):
        r = admin_session.get(f"{API}/admin/webhooks/status", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "configured" in data
        assert set(data["configured"].keys()) == {"slack", "discord"}
        assert isinstance(data["configured"]["slack"], bool)
        assert isinstance(data["configured"]["discord"], bool)
        assert "any_configured" in data and isinstance(data["any_configured"], bool)
        assert data["any_configured"] == any(data["configured"].values())
        assert "cooldown_seconds" in data and isinstance(data["cooldown_seconds"], int)
        assert data["fires_on"] == "critical"

    def test_status_non_admin_403(self, user_session):
        r = user_session.get(f"{API}/admin/webhooks/status", timeout=10)
        assert r.status_code == 403

    def test_status_unauth_401(self):
        r = requests.get(f"{API}/admin/webhooks/status", timeout=10)
        assert r.status_code in (401, 403)

    def test_test_admin_200(self, admin_session):
        r = admin_session.post(f"{API}/admin/webhooks/test", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "configured" in data
        # Without webhooks configured the call must short-circuit
        if not any(data["configured"].values()):
            assert data["results"].get("skipped") is True
            assert data["results"].get("reason") == "no_webhook_configured"

    def test_test_non_admin_403(self, user_session):
        r = user_session.post(f"{API}/admin/webhooks/test", timeout=10)
        assert r.status_code == 403


# ============================================================
# WebhookNotifier direct unit test (loopback HTTP server)
# ============================================================

class _Recorder(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else None
        except Exception:
            payload = None
        _Recorder.received.append({"path": self.path, "payload": payload})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt, *args):
        return


@pytest.fixture(scope="module")
def loopback_server():
    _Recorder.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield port
    srv.shutdown()
    srv.server_close()


class TestWebhookNotifierUnit:
    def test_dispatch_critical_hits_both_endpoints_and_cooldown(self, loopback_server):
        port = loopback_server
        slack_url = f"http://127.0.0.1:{port}/slack"
        discord_url = f"http://127.0.0.1:{port}/discord"

        # Inject env then import server lazily so a fresh notifier reads them
        os.environ["SLACK_WEBHOOK_URL"] = slack_url
        os.environ["DISCORD_WEBHOOK_URL"] = discord_url
        os.environ["WEBHOOK_COOLDOWN_SEC"] = "120"

        sys.path.insert(0, "/app/backend")
        from server import WebhookNotifier  # noqa: WPS433

        notifier = WebhookNotifier()
        assert notifier.is_configured() == {"slack": True, "discord": True}

        critical_alert = {
            "id": "unit_test_critical_1",
            "type": "critical",
            "category": "latency",
            "title": "Test Critical",
            "message": "loopback delivery",
            "value": 1.23,
            "threshold": 0.5,
            "action": "scale_out",
            "node": "API",
        }

        async def _run():
            r1 = await notifier.dispatch(critical_alert)
            # Same id within cooldown -> skipped
            r2 = await notifier.dispatch(critical_alert)
            warn = dict(critical_alert, id="warn1", type="warning")
            r3 = await notifier.dispatch(warn)
            return r1, r2, r3

        r1, r2, r3 = asyncio.run(_run())

        # First dispatch should hit both endpoints
        assert "slack" in r1 and r1["slack"]["ok"] is True
        assert "discord" in r1 and r1["discord"]["ok"] is True

        # Cooldown skip
        assert r2.get("skipped") is True
        assert r2.get("reason") == "cooldown"

        # Warning skip
        assert r3.get("skipped") is True
        assert r3.get("reason") == "not_critical"

        # Validate captured payloads
        slack_hits = [r for r in _Recorder.received if r["path"] == "/slack"]
        discord_hits = [r for r in _Recorder.received if r["path"] == "/discord"]
        assert len(slack_hits) == 1, f"expected 1 slack hit, got {len(slack_hits)}"
        assert len(discord_hits) == 1, f"expected 1 discord hit, got {len(discord_hits)}"

        slack_payload = slack_hits[0]["payload"]
        assert "attachments" in slack_payload and isinstance(slack_payload["attachments"], list)
        assert slack_payload["attachments"][0]["color"] == "#FF3B30"
        # Field names present
        field_titles = {f["title"] for f in slack_payload["attachments"][0]["fields"]}
        assert {"Category", "Value", "Threshold", "Action"}.issubset(field_titles)

        discord_payload = discord_hits[0]["payload"]
        assert "embeds" in discord_payload and isinstance(discord_payload["embeds"], list)
        assert discord_payload["embeds"][0]["color"] == 0xFF3B30
        names = {f["name"] for f in discord_payload["embeds"][0]["fields"]}
        assert {"Category", "Value", "Threshold", "Action"}.issubset(names)

        # Cleanup env vars so the rest of the suite runs against the live notifier state
        os.environ.pop("SLACK_WEBHOOK_URL", None)
        os.environ.pop("DISCORD_WEBHOOK_URL", None)


# ============================================================
# Regression
# ============================================================

class TestRegression:
    def test_fea_service_no_components_key(self):
        r = requests.get(f"{API}/healing/fea?granularity=service", timeout=10)
        assert r.status_code == 200
        data = r.json()
        elements = data.get("elements") or data.get("services") or []
        assert isinstance(elements, list) and len(elements) >= 1
        for el in elements:
            assert "components" not in el, "service-granularity element must NOT contain 'components'"

    def test_fea_component_has_components(self):
        r = requests.get(f"{API}/healing/fea?granularity=component", timeout=10)
        assert r.status_code == 200
        data = r.json()
        elements = data.get("elements") or data.get("services") or []
        assert isinstance(elements, list) and len(elements) >= 1
        with_comp = [el for el in elements if "components" in el]
        assert len(with_comp) >= 1, "component-granularity must include 'components' on services"

    def test_topology_fine_19_nodes(self):
        r = requests.get(f"{API}/healing/topology?granularity=fine", timeout=10)
        assert r.status_code == 200
        data = r.json()
        services = data.get("services") or []
        # Fine mesh should have 19 sub-components (5+3+4+3+4)
        assert len(services) == 19, f"expected 19 fine nodes, got {len(services)}"

    def test_metrics_real_200(self):
        r = requests.get(f"{API}/metrics/real", timeout=10)
        assert r.status_code == 200

    def test_auth_login_200(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
        assert r.status_code == 200

    def test_products_200(self):
        r = requests.get(f"{API}/products", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
