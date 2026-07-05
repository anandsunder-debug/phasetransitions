"""
Test iteration 9 features:
- GET /api/healing/rca endpoint - root cause via Fiedler vector
- /api/healing/status includes rca field
- /api/healing/recommendations includes rca field
- Full purchasing flow: register/login -> products -> cart -> checkout -> order
- Cart clears after order is placed
- Empty cart still allows GET (no redirect happens at API layer)
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ========== HEALING/RCA TESTS ==========
class TestHealingRCA:
    """RCA endpoint and rca field inclusion in status/recommendations"""

    def test_healing_rca_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/healing/rca")
        assert r.status_code == 200, r.text
        data = r.json()

        # Required fields per problem statement
        for field in ["root_cause_node", "confidence", "rca_score",
                      "recommended_action", "node_rankings"]:
            assert field in data, f"Missing field: {field}"

        # Validate types
        assert isinstance(data["root_cause_node"], str)
        assert data["confidence"] in ["high", "medium", "low", "none"]
        assert isinstance(data["rca_score"], (int, float))
        assert isinstance(data["node_rankings"], list)
        assert len(data["node_rankings"]) >= 1

        # Each ranking has node, rca_score
        for r_ in data["node_rankings"]:
            assert "node" in r_
            assert "rca_score" in r_

        # Should also include extra useful fields
        assert "fiedler_vector" in data
        assert "golden_signals" in data
        print(f"RCA root cause: {data['root_cause_node']} ({data['confidence']}) -> {data['recommended_action']}")

    def test_healing_status_includes_rca(self):
        r = requests.get(f"{BASE_URL}/api/healing/status")
        assert r.status_code == 200
        data = r.json()
        assert "rca" in data, "healing/status missing rca field"
        rca = data["rca"]
        assert "root_cause_node" in rca
        assert "node_rankings" in rca
        print(f"healing/status.rca.root_cause_node = {rca['root_cause_node']}")

    def test_healing_recommendations_includes_rca(self):
        r = requests.get(f"{BASE_URL}/api/healing/recommendations")
        assert r.status_code == 200
        data = r.json()
        assert "rca" in data, "healing/recommendations missing rca field"
        rca = data["rca"]
        assert "root_cause_node" in rca
        print(f"healing/recommendations.rca.root_cause_node = {rca['root_cause_node']}")

    def test_rca_node_rankings_sorted_desc(self):
        r = requests.get(f"{BASE_URL}/api/healing/rca")
        data = r.json()
        scores = [n["rca_score"] for n in data["node_rankings"]]
        assert scores == sorted(scores, reverse=True), "node_rankings should be sorted by rca_score desc"


# ========== AUTH TESTS ==========
class TestAuth:
    """Auth: register + login"""

    @pytest.fixture(scope="class")
    def test_user(self):
        return {
            "email": f"TEST_user_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPass123!",
            "name": "Test User"
        }

    def test_register_user(self, test_user):
        r = requests.post(f"{BASE_URL}/api/auth/register", json=test_user)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        # Either returns user or a token
        assert "user" in data or "email" in data or "id" in data
        print(f"Registered: {test_user['email']}")

    def test_login_admin(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": "admin@freshcart.com", "password": "admin123"})
        assert r.status_code == 200, r.text
        # /api/auth/me check
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        me_data = me.json()
        assert me_data.get("role") == "admin", f"Admin role missing: {me_data}"
        print("Admin login + /me OK, role=admin")

    def test_login_regular_user(self, test_user):
        # Ensure registered
        requests.post(f"{BASE_URL}/api/auth/register", json=test_user)
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": test_user["email"], "password": test_user["password"]})
        assert r.status_code == 200, r.text
        me = s.get(f"{BASE_URL}/api/auth/me")
        assert me.status_code == 200
        me_data = me.json()
        # Should be regular user, not admin
        assert me_data.get("role") != "admin", "Regular user should not have admin role"
        print(f"Regular user login OK, role={me_data.get('role')}")


# ========== FULL PURCHASE FLOW ==========
class TestPurchaseFlow:
    """End-to-end purchasing flow including cart clear after order"""

    @pytest.fixture(scope="class")
    def auth_session(self):
        # Use a fresh user to keep cart isolated
        user = {
            "email": f"TEST_flow_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPass123!",
            "name": "Flow Test User"
        }
        s = requests.Session()
        reg = s.post(f"{BASE_URL}/api/auth/register", json=user)
        assert reg.status_code in (200, 201), reg.text
        # Some apps auto-login on register; ensure session is logged in
        me = s.get(f"{BASE_URL}/api/auth/me")
        if me.status_code != 200:
            login = s.post(f"{BASE_URL}/api/auth/login",
                           json={"email": user["email"], "password": user["password"]})
            assert login.status_code == 200, login.text
        return s

    def test_products_listing(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/products")
        assert r.status_code == 200
        products = r.json()
        assert isinstance(products, list) and len(products) > 0
        assert "id" in products[0]
        print(f"Products available: {len(products)}")

    def test_empty_cart_returns_empty_state(self, auth_session):
        # Clear cart first by getting and removing all
        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        for item in cart.get("items", []):
            auth_session.delete(f"{BASE_URL}/api/cart/remove/{item['product_id']}")
        r = auth_session.get(f"{BASE_URL}/api/cart")
        assert r.status_code == 200
        data = r.json()
        assert data.get("items") == []
        print("Empty cart returns 200 with empty items list")

    def test_full_purchase_and_cart_cleared(self, auth_session):
        # Add 2 items to cart
        products = auth_session.get(f"{BASE_URL}/api/products").json()
        p1, p2 = products[0]["id"], products[1]["id"]

        for pid, qty in [(p1, 2), (p2, 1)]:
            r = auth_session.post(f"{BASE_URL}/api/cart/add",
                                  json={"product_id": pid, "quantity": qty})
            assert r.status_code == 200, r.text

        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        assert len(cart["items"]) == 2
        print(f"Cart has {len(cart['items'])} items before checkout")

        # Place order
        order_resp = auth_session.post(f"{BASE_URL}/api/orders", json={
            "delivery_address": "123 Test Street, Test City",
            "phone": "+1234567890"
        })
        assert order_resp.status_code == 200, order_resp.text
        order = order_resp.json()
        assert "id" in order
        assert order.get("total", 0) > 0
        order_id = order["id"]
        print(f"Order created: {order_id}, total=${order['total']}")

        # Cart should be cleared in DB
        cart_after = auth_session.get(f"{BASE_URL}/api/cart").json()
        assert cart_after.get("items") == [], \
            f"Cart should be empty after order, got: {cart_after}"
        print("Cart cleared in backend after order placement")

        # Order shows up in user's orders
        orders = auth_session.get(f"{BASE_URL}/api/orders").json()
        assert any(o["id"] == order_id for o in orders), "Order not in user's orders list"
        print(f"Order {order_id} found in user's orders")

    def test_checkout_with_empty_cart_returns_error(self, auth_session):
        # Cart is already empty after previous test
        r = auth_session.post(f"{BASE_URL}/api/orders", json={
            "delivery_address": "123 Test Street",
            "phone": "+1234567890"
        })
        # Should fail (400/422) since cart is empty
        assert r.status_code >= 400, f"Empty cart order should fail, got {r.status_code}"
        print(f"Empty cart checkout properly rejected with {r.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
