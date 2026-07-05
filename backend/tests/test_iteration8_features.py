"""
Test iteration 8 features:
- SPA navigation (Footer uses React Router Links)
- Optimistic cart updates
- ProductCard add-to-cart with instant feedback
- Metrics middleware distributes across all 5 nodes
- Golden signals and CX metrics from real API traffic
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGoldenSignalsAPI:
    """Test Golden Signals endpoint"""
    
    def test_golden_signals_returns_4_signals(self):
        """GET /api/metrics/golden-signals returns 4 golden signals"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        data = response.json()
        
        assert "signals" in data
        signals = data["signals"]
        assert "latency" in signals
        assert "traffic" in signals
        assert "errors" in signals
        assert "saturation" in signals
        print("Golden signals endpoint returns all 4 signals")
    
    def test_golden_signals_have_health_scores(self):
        """Each golden signal has health score"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        data = response.json()
        
        for signal_name in ["latency", "traffic", "errors", "saturation"]:
            signal = data["signals"][signal_name]
            assert "value" in signal
            assert "health" in signal
            assert "unit" in signal
            assert "threshold" in signal
            assert 0 <= signal["health"] <= 1
        print("All golden signals have health scores")
    
    def test_golden_signals_includes_sri(self):
        """Golden signals endpoint includes SRI"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        data = response.json()
        
        assert "sri" in data
        assert isinstance(data["sri"], (int, float))
        print(f"SRI value: {data['sri']}")
    
    def test_golden_signals_includes_signal_contributions(self):
        """Golden signals endpoint includes signal contributions"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        data = response.json()
        
        assert "signal_contributions" in data
        contributions = data["signal_contributions"]
        assert "latency" in contributions
        assert "traffic" in contributions
        assert "errors" in contributions
        assert "saturation" in contributions
        print("Signal contributions included")


class TestCustomerExperienceAPI:
    """Test Customer Experience endpoint"""
    
    def test_customer_experience_returns_apdex(self):
        """GET /api/metrics/customer-experience returns Apdex"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        data = response.json()
        
        assert "apdex" in data
        assert "apdex_label" in data
        assert 0 <= data["apdex"] <= 1
        print(f"Apdex: {data['apdex']} ({data['apdex_label']})")
    
    def test_customer_experience_returns_percentiles(self):
        """GET /api/metrics/customer-experience returns P50/P95/P99"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        data = response.json()
        
        assert "p50" in data
        assert "p95" in data
        assert "p99" in data
        print(f"Percentiles - P50: {data['p50']}ms, P95: {data['p95']}ms, P99: {data['p99']}ms")
    
    def test_customer_experience_returns_availability(self):
        """GET /api/metrics/customer-experience returns availability"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        data = response.json()
        
        assert "availability" in data
        assert 0 <= data["availability"] <= 100
        print(f"Availability: {data['availability']}%")
    
    def test_customer_experience_returns_error_budget(self):
        """GET /api/metrics/customer-experience returns error budget"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        data = response.json()
        
        assert "error_budget" in data
        eb = data["error_budget"]
        assert "slo" in eb
        assert "total" in eb
        assert "consumed" in eb
        assert "remaining" in eb
        assert "remaining_pct" in eb
        print(f"Error Budget - SLO: {eb['slo']}%, Remaining: {eb['remaining_pct']}%")


class TestMetricsRealAPI:
    """Test /api/metrics/real endpoint"""
    
    def test_metrics_real_includes_golden_signals(self):
        """GET /api/metrics/real includes golden_signals field"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        data = response.json()
        
        assert "golden_signals" in data
        gs = data["golden_signals"]
        assert "latency" in gs
        assert "traffic" in gs
        assert "errors" in gs
        assert "saturation" in gs
        print("Metrics real includes golden_signals")
    
    def test_metrics_real_includes_customer_experience(self):
        """GET /api/metrics/real includes customer_experience field"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        data = response.json()
        
        assert "customer_experience" in data
        cx = data["customer_experience"]
        assert "apdex" in cx
        assert "p50" in cx
        assert "availability" in cx
        print("Metrics real includes customer_experience")
    
    def test_metrics_real_includes_signal_contributions(self):
        """GET /api/metrics/real includes signal_contributions"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        data = response.json()
        
        assert "signal_contributions" in data
        print("Metrics real includes signal_contributions")
    
    def test_metrics_real_includes_all_5_nodes(self):
        """GET /api/metrics/real includes all 5 nodes"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        data = response.json()
        
        assert "nodes" in data
        node_ids = [n["id"] for n in data["nodes"]]
        expected_nodes = ["API", "Cache", "DB", "Queue", "Backend"]
        for node in expected_nodes:
            assert node in node_ids, f"Node {node} not found"
        print(f"All 5 nodes present: {node_ids}")


class TestCartAPI:
    """Test Cart API for optimistic updates"""
    
    @pytest.fixture
    def auth_session(self):
        """Login and return authenticated session"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@freshcart.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        return session
    
    def test_add_to_cart(self, auth_session):
        """POST /api/cart/add works"""
        # Get a product first
        products_response = auth_session.get(f"{BASE_URL}/api/products")
        assert products_response.status_code == 200
        products = products_response.json()
        assert len(products) > 0
        
        product_id = products[0]["id"]
        
        # Add to cart
        add_response = auth_session.post(f"{BASE_URL}/api/cart/add", json={
            "product_id": product_id,
            "quantity": 1
        })
        assert add_response.status_code == 200
        print(f"Added product {product_id} to cart")
    
    def test_get_cart(self, auth_session):
        """GET /api/cart returns cart with items"""
        response = auth_session.get(f"{BASE_URL}/api/cart")
        assert response.status_code == 200
        data = response.json()
        
        assert "items" in data
        print(f"Cart has {len(data['items'])} items")
    
    def test_update_cart_item(self, auth_session):
        """PUT /api/cart/update works"""
        # Get cart first
        cart_response = auth_session.get(f"{BASE_URL}/api/cart")
        cart = cart_response.json()
        
        if cart["items"]:
            product_id = cart["items"][0]["product_id"]
            update_response = auth_session.put(f"{BASE_URL}/api/cart/update", json={
                "product_id": product_id,
                "quantity": 2
            })
            assert update_response.status_code == 200
            print("Updated cart item quantity")
    
    def test_remove_from_cart(self, auth_session):
        """DELETE /api/cart/remove/{product_id} works"""
        # Get cart first
        cart_response = auth_session.get(f"{BASE_URL}/api/cart")
        cart = cart_response.json()
        
        if cart["items"]:
            product_id = cart["items"][0]["product_id"]
            remove_response = auth_session.delete(f"{BASE_URL}/api/cart/remove/{product_id}")
            assert remove_response.status_code == 200
            print("Removed product from cart")


class TestProductsAPI:
    """Test Products API"""
    
    def test_get_products(self):
        """GET /api/products returns products"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        products = response.json()
        
        assert isinstance(products, list)
        assert len(products) > 0
        
        # Check product structure
        product = products[0]
        assert "id" in product
        assert "name" in product
        assert "price" in product
        assert "category" in product
        assert "image_url" in product
        print(f"Found {len(products)} products")
    
    def test_get_product_by_id(self):
        """GET /api/products/{id} returns single product"""
        # Get products first
        products_response = requests.get(f"{BASE_URL}/api/products")
        products = products_response.json()
        product_id = products[0]["id"]
        
        # Get single product
        response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert response.status_code == 200
        product = response.json()
        
        assert product["id"] == product_id
        print(f"Got product: {product['name']}")
    
    def test_get_categories(self):
        """GET /api/categories returns categories"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        categories = response.json()
        
        assert isinstance(categories, list)
        assert len(categories) > 0
        print(f"Categories: {categories}")


class TestCheckoutFlow:
    """Test checkout flow"""
    
    @pytest.fixture
    def auth_session(self):
        """Login and return authenticated session"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@freshcart.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        return session
    
    def test_create_order(self, auth_session):
        """POST /api/orders creates order from cart"""
        # First add item to cart
        products_response = auth_session.get(f"{BASE_URL}/api/products")
        products = products_response.json()
        product_id = products[0]["id"]
        
        auth_session.post(f"{BASE_URL}/api/cart/add", json={
            "product_id": product_id,
            "quantity": 1
        })
        
        # Create order
        order_response = auth_session.post(f"{BASE_URL}/api/orders", json={
            "delivery_address": "123 Test Street, Test City",
            "phone": "+1234567890"
        })
        assert order_response.status_code == 200
        order = order_response.json()
        
        assert "id" in order
        assert "total" in order
        assert "status" in order
        print(f"Created order {order['id']} with total ${order['total']}")
    
    def test_get_orders(self, auth_session):
        """GET /api/orders returns user orders"""
        response = auth_session.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        orders = response.json()
        
        assert isinstance(orders, list)
        print(f"User has {len(orders)} orders")


class TestHealingAPI:
    """Test Auto-Healing API"""
    
    @pytest.fixture
    def auth_session(self):
        """Login and return authenticated session"""
        session = requests.Session()
        login_response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@freshcart.com",
            "password": "admin123"
        })
        assert login_response.status_code == 200
        return session
    
    def test_healing_status(self, auth_session):
        """GET /api/healing/status returns status"""
        response = auth_session.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "enabled" in data
        assert "alert_driven" in data
        assert "golden_signals" in data
        print(f"Healing enabled: {data['enabled']}, Alert-driven: {data['alert_driven']}")
    
    def test_healing_toggle(self, auth_session):
        """POST /api/healing/toggle works"""
        response = auth_session.post(f"{BASE_URL}/api/healing/toggle", json={
            "enabled": True,
            "alert_driven": True
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "enabled" in data
        print(f"Toggled healing: {data}")
    
    def test_healing_recommendations(self, auth_session):
        """GET /api/healing/recommendations returns recommendations"""
        response = auth_session.get(f"{BASE_URL}/api/healing/recommendations")
        assert response.status_code == 200
        data = response.json()
        
        assert "recommendations" in data
        assert "golden_signals" in data
        print(f"Got {len(data['recommendations'])} recommendations")


class TestAlertsAPI:
    """Test Alerts API"""
    
    def test_get_alerts(self):
        """GET /api/alerts returns alerts"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        alerts = response.json()
        
        assert isinstance(alerts, list)
        print(f"Found {len(alerts)} alerts")
    
    def test_get_alert_config(self):
        """GET /api/alerts/config returns config"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        assert response.status_code == 200
        config = response.json()
        
        assert "sri_critical" in config
        assert "sri_warning" in config
        assert "latency_critical" in config
        assert "error_rate_critical" in config
        print(f"Alert config: {config}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
