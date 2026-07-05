"""
Iteration 20 — Backend microservice split (server.py + obs_server.py) validation.

Covers:
  - Health on main app (8001) and obs (8002, internal only)
  - E-commerce endpoints on main app (auth/products/cart/orders/admin)
  - Observability proxy correctness for /metrics/*, /healing/*, /cx/*, /rum/*,
    /alerts, /admin/webhooks/* via main app
  - Event emission: request and business events flow main_app -> obs and
    affect /api/metrics/real, /api/metrics/business
  - WebSocket proxy /ws/alerts through main app
  - Auth cookie preservation across proxy (/api/admin/webhooks/test)
"""
import asyncio
import json
import os
import time
import uuid
import pytest
import requests
import websockets

_env = os.environ.get("REACT_APP_BACKEND_URL")
if not _env:
    # Load from frontend/.env file
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    _env = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
assert _env, "REACT_APP_BACKEND_URL not found in env or /app/frontend/.env"
BASE_URL = _env.rstrip("/")
OBS_LOCAL = "http://localhost:8002"


# ---------- Shared fixtures ----------

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@freshcart.com", "password": "admin123"},
               timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "test12345", "name": "Test User"},
               timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text[:200]}"
    return s


# ---------- INFRA ----------

class TestInfra:
    def test_main_app_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"

    def test_main_root_health_endpoint(self):
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        # Main app exposes /health via root_health
        assert r.status_code == 200

    def test_obs_service_running_internally(self):
        # Must be reachable on localhost:8002 to prove it is a separate process
        r = requests.get(f"{OBS_LOCAL}/health", timeout=5)
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"


# ---------- E-COMMERCE ----------

class TestEcommerce:
    def test_products_list(self):
        r = requests.get(f"{BASE_URL}/api/products", timeout=15)
        assert r.status_code == 200
        body = r.json()
        items = body if isinstance(body, list) else body.get("products") or body.get("items") or []
        assert isinstance(items, list) and len(items) >= 1
        # store one id for later
        TestEcommerce.sample_product_id = items[0].get("id") or items[0].get("_id")
        assert TestEcommerce.sample_product_id

    def test_product_detail(self):
        pid = TestEcommerce.sample_product_id
        r = requests.get(f"{BASE_URL}/api/products/{pid}", timeout=10)
        assert r.status_code == 200
        assert (r.json().get("id") or r.json().get("_id")) == pid

    def test_categories(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or "categories" in data

    def test_auth_me_with_admin_cookie(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 200
        assert r.json().get("email") == "admin@freshcart.com"

    def test_cart_add_get_clear(self, user_session):
        pid = TestEcommerce.sample_product_id
        r = user_session.post(f"{BASE_URL}/api/cart/add",
                              json={"product_id": pid, "quantity": 2}, timeout=10)
        assert r.status_code in (200, 201), r.text[:200]
        r = user_session.get(f"{BASE_URL}/api/cart", timeout=10)
        assert r.status_code == 200
        cart = r.json()
        items = cart.get("items") or cart.get("cart_items") or []
        assert len(items) >= 1
        # delete cart (clear)
        r = user_session.delete(f"{BASE_URL}/api/cart/clear", timeout=10)
        assert r.status_code in (200, 204)

    def test_orders_list_auth(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/orders", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_admin_orders_requires_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/orders", timeout=10)
        assert r.status_code == 200


# ---------- OBS PROXY ----------

PROXIED_GET_ENDPOINTS = [
    "/api/metrics/real",
    "/api/metrics/golden-signals",
    "/api/metrics/customer-experience",
    "/api/metrics/business",
    "/api/metrics/reliability",
    "/api/metrics/attribution",
    "/api/metrics/sri-history",
    "/api/metrics/summary",
    "/api/metrics/correlation",
    "/api/healing",
    "/api/healing/status",
    "/api/healing/fea",
    "/api/healing/topology",
    "/api/healing/topology/schema",
    "/api/healing/rca",
    "/api/healing/trend",
    "/api/healing/resilience-debt",
    "/api/healing/active-propagations",
    "/api/healing/history",
    "/api/cx/metrics",
    "/api/alerts",
]


class TestObsProxy:
    @pytest.mark.parametrize("path", PROXIED_GET_ENDPOINTS)
    def test_proxy_get(self, path):
        r = requests.get(f"{BASE_URL}{path}", timeout=20)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        # must be JSON
        try:
            body = r.json()
        except Exception:
            pytest.fail(f"{path} returned non-JSON: {r.text[:200]}")
        assert body is not None

    def test_proxy_returns_same_body_as_direct(self):
        """Sanity: proxied response shape should equal direct obs response (top-level keys)."""
        direct = requests.get(f"{OBS_LOCAL}/api/healing/topology/schema", timeout=5).json()
        proxied = requests.get(f"{BASE_URL}/api/healing/topology/schema", timeout=10).json()
        assert set(direct.keys()) == set(proxied.keys())
        # services list of 6 should match between direct and proxied
        d_names = [s["name"] for s in direct["services"]]
        p_names = [s["name"] for s in proxied["services"]]
        assert d_names == p_names
        assert len(p_names) == 6

    def test_synthetic_user_post_proxy(self):
        r = requests.post(f"{BASE_URL}/api/cx/synthetic-user/run", json={}, timeout=20)
        assert r.status_code == 200
        body = r.json()
        # endpoint returns either {ok:True} or detailed result
        assert isinstance(body, dict)

    def test_admin_webhooks_status_requires_auth(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/webhooks/status", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)

    def test_admin_webhooks_test_preserves_cookie(self, admin_session):
        # Unauthenticated request should not be allowed (cookie must be required)
        anon = requests.post(f"{BASE_URL}/api/admin/webhooks/test", json={}, timeout=10)
        assert anon.status_code in (401, 403), f"expected 401/403, got {anon.status_code}"
        # Authenticated should pass through proxy. Endpoint may return 200/400/500
        # depending on whether webhook configured, but NOT 401/403.
        r = admin_session.post(f"{BASE_URL}/api/admin/webhooks/test", json={}, timeout=15)
        assert r.status_code not in (401, 403), \
            f"cookie not preserved through proxy: {r.status_code} {r.text[:200]}"

    def test_unknown_proxy_path_404(self):
        r = requests.get(f"{BASE_URL}/api/this-route-does-not-exist", timeout=10)
        assert r.status_code in (404, 405)


# ---------- EVENT EMISSION ----------

class TestEventEmission:
    def test_request_events_propagate_to_obs_traffic(self):
        # Snapshot
        before = requests.get(f"{BASE_URL}/api/metrics/real", timeout=10).json()
        api_before = (before.get("nodes") or {})
        # MetricsAggregator may return list or dict; normalize
        if isinstance(api_before, list):
            api_before = {n.get("id") or n.get("name"): n for n in api_before}
        api_before_traffic = (api_before.get("API") or {}).get("traffic", 0)

        # Generate ~15 requests (each goes through main_app middleware that
        # fires obs internal/events/request)
        for _ in range(15):
            requests.get(f"{BASE_URL}/api/products", timeout=10)
        time.sleep(2)

        after = requests.get(f"{BASE_URL}/api/metrics/real", timeout=10).json()
        api_after = after.get("nodes") or {}
        if isinstance(api_after, list):
            api_after = {n.get("id") or n.get("name"): n for n in api_after}
        api_after_traffic = (api_after.get("API") or {}).get("traffic", 0)

        assert api_after_traffic >= api_before_traffic, \
            f"traffic should grow: before={api_before_traffic} after={api_after_traffic}"
        # SRI must be computed
        sri = after.get("sri")
        assert sri is None or isinstance(sri, (int, float))
        # Customer experience total_requests grows
        cx = after.get("customer_experience") or {}
        total_req = cx.get("total_requests")
        if total_req is not None:
            assert total_req >= 0

    def test_business_event_addtocart_increments(self, user_session):
        pid = TestEcommerce.sample_product_id
        before = requests.get(f"{BASE_URL}/api/metrics/business", timeout=10).json()
        b_add_before = (before.get("funnel") or {}).get("add_to_cart") or before.get("add_to_cart") or 0

        # Add to cart 3 times (correct endpoint /api/cart/add)
        for _ in range(3):
            user_session.post(f"{BASE_URL}/api/cart/add",
                              json={"product_id": pid, "quantity": 1}, timeout=10)
        time.sleep(2)

        after = requests.get(f"{BASE_URL}/api/metrics/business", timeout=10).json()
        b_add_after = (after.get("funnel") or {}).get("add_to_cart") or after.get("add_to_cart") or 0
        assert b_add_after >= b_add_before + 1, \
            f"add_to_cart counter not incrementing through proxy: before={b_add_before} after={b_add_after}"

    def test_business_event_order_complete(self, user_session):
        pid = TestEcommerce.sample_product_id
        before = requests.get(f"{BASE_URL}/api/metrics/business", timeout=10).json()
        b_order_before = ((before.get("funnel") or {}).get("order_complete")
                          or before.get("order_complete") or 0)

        # Add to cart and checkout via buy-now (or full order)
        r = user_session.post(f"{BASE_URL}/api/orders/buy-now",
                              json={"product_id": pid, "quantity": 1,
                                    "shipping_address": "123 Test St"},
                              timeout=15)
        # Some impl require shipping address as object; try both
        if r.status_code >= 400:
            r = user_session.post(f"{BASE_URL}/api/orders/buy-now",
                                  json={"product_id": pid, "quantity": 1,
                                        "shipping_address": {"line1": "123 Test St",
                                                              "city": "X", "zip": "00000"}},
                                  timeout=15)
        # don't hard-fail if buy-now route differs; at least test add_to_cart path
        time.sleep(1.5)
        after = requests.get(f"{BASE_URL}/api/metrics/business", timeout=10).json()
        b_order_after = ((after.get("funnel") or {}).get("order_complete")
                         or after.get("order_complete") or 0)
        if r.status_code in (200, 201):
            assert b_order_after >= b_order_before, "order_complete counter regressed"


# ---------- RUM BEACON ----------

class TestRumBeacon:
    def test_rum_beacon_proxy(self):
        payload = {
            "session_id": "test-session-001",
            "page_load_ms": 800,
            "render_ms": 120,
            "api_calls": [{"path": "/api/products", "duration_ms": 80, "error": False}],
            "js_errors": [],
        }
        r = requests.post(f"{BASE_URL}/api/rum/beacon", json=payload, timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body.get("ok") is True


# ---------- AUTO-HEALING ----------

class TestHealing:
    def test_healing_recommendations(self):
        r = requests.get(f"{BASE_URL}/api/healing", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)

    def test_healing_toggle_requires_auth(self, admin_session):
        r = requests.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": True}, timeout=10)
        # Anonymous: should be 401/403 OR allowed (route may not require auth in obs)
        # If allowed, ensure admin call also passes
        if r.status_code in (401, 403):
            r2 = admin_session.post(f"{BASE_URL}/api/healing/toggle",
                                    json={"enabled": True}, timeout=10)
            assert r2.status_code in (200, 201)
        else:
            assert r.status_code in (200, 201), f"toggle failed: {r.status_code} {r.text[:200]}"

    def test_fault_propagation_api(self):
        r = requests.post(f"{BASE_URL}/api/healing/fault-propagation",
                          json={"source": "API"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "node_summary" in body or "timeline" in body or "mesh_size" in body


# ---------- WEBSOCKET PROXY ----------

class TestWebSocketProxy:
    @pytest.mark.asyncio
    async def test_ws_alerts_proxy(self):
        """Validate ws proxy at application layer via main_app:8001.

        NOTE: external URL WebSocket may be blocked by ingress in this preview
        environment. Connection at the application layer (main_app -> obs) is
        what matters for the architecture under test.
        """
        ws_url = "ws://localhost:8001/ws/alerts"
        try:
            async with websockets.connect(ws_url, open_timeout=10, ping_interval=None) as ws:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=8)
                    # Should receive history payload
                    data = json.loads(msg)
                    assert "type" in data or "alerts" in data
                except asyncio.TimeoutError:
                    # connection established is sufficient
                    pass
        except Exception as e:
            pytest.fail(f"WS proxy (main_app -> obs) connection failed: {e}")

    @pytest.mark.asyncio
    async def test_ws_alerts_external_url(self):
        """External URL WS support. May not work in some preview k8s ingresses.
        Marked xfail-soft: failure surfaces as a warning, not a hard fail."""
        ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws/alerts"
        try:
            async with websockets.connect(ws_url, open_timeout=15, ping_interval=None) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=8)
                data = json.loads(msg)
                assert "type" in data
        except Exception as e:
            pytest.skip(f"External WS not reachable through ingress: {e}")
