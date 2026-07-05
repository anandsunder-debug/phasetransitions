"""
FreshCart E-commerce Platform API Tests
Tests for: Auth, Products, Cart, Orders, Metrics, Grafana Proxy, Alerts
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://delivery-metrics-hub-1.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@freshcart.com")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "admin123")
TEST_USER_EMAIL = f"test_user_{int(time.time())}@example.com"
TEST_USER_PASSWORD = os.environ.get("TEST_USER_PASSWORD", "testpass123")


class TestHealthAndBasics:
    """Basic health check and API availability tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        print(f"Health check passed: {data}")
    
    def test_root_endpoint(self):
        """Test /api/ returns API info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Root endpoint: {data}")


class TestAuthentication:
    """Authentication flow tests"""
    
    def test_admin_login_success(self):
        """Test admin login with correct credentials"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "id" in data
        print(f"Admin login successful: {data['email']}, role: {data['role']}")
        
        # Verify cookies are set
        assert "access_token" in session.cookies
        print("Access token cookie set correctly")
    
    def test_login_invalid_credentials(self):
        """Test login with wrong password"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        print(f"Invalid login rejected: {data['detail']}")
    
    def test_register_new_user(self):
        """Test user registration"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "name": "Test User"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == TEST_USER_EMAIL.lower()
        assert data["role"] == "user"
        print(f"User registered: {data['email']}")
    
    def test_register_duplicate_email(self):
        """Test registration with existing email fails"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": ADMIN_EMAIL,
            "password": "anypassword",
            "name": "Duplicate User"
        })
        assert response.status_code == 400
        print("Duplicate email registration rejected correctly")
    
    def test_get_current_user(self):
        """Test /api/auth/me returns current user"""
        session = requests.Session()
        # Login first
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == ADMIN_EMAIL
        print(f"Current user: {data}")
    
    def test_logout(self):
        """Test logout clears session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        
        response = session.post(f"{BASE_URL}/api/auth/logout")
        assert response.status_code == 200
        print("Logout successful")


class TestProducts:
    """Product listing and retrieval tests"""
    
    def test_get_all_products(self):
        """Test /api/products returns product list"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify product structure
        product = data[0]
        assert "id" in product
        assert "name" in product
        assert "price" in product
        assert "category" in product
        print(f"Found {len(data)} products")
    
    def test_get_products_by_category(self):
        """Test filtering products by category"""
        response = requests.get(f"{BASE_URL}/api/products?category=Vegetables")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for product in data:
            assert product["category"] == "Vegetables"
        print(f"Found {len(data)} vegetables")
    
    def test_get_single_product(self):
        """Test getting a single product by ID"""
        # First get all products
        products_response = requests.get(f"{BASE_URL}/api/products")
        products = products_response.json()
        product_id = products[0]["id"]
        
        # Get single product
        response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        print(f"Got product: {data['name']}")
    
    def test_get_categories(self):
        """Test /api/categories returns category list"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"Categories: {data}")


class TestCart:
    """Shopping cart operations tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return session
    
    def test_get_cart(self, auth_session):
        """Test getting user's cart"""
        response = auth_session.get(f"{BASE_URL}/api/cart")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        print(f"Cart has {len(data['items'])} items")
    
    def test_add_to_cart(self, auth_session):
        """Test adding item to cart"""
        # Get a product first
        products = requests.get(f"{BASE_URL}/api/products").json()
        product_id = products[0]["id"]
        
        response = auth_session.post(f"{BASE_URL}/api/cart/add", json={
            "product_id": product_id,
            "quantity": 2
        })
        assert response.status_code == 200
        
        # Verify item was added
        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        assert any(item["product_id"] == product_id for item in cart["items"])
        print(f"Added product {product_id} to cart")
    
    def test_update_cart_item(self, auth_session):
        """Test updating cart item quantity"""
        # Get cart
        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        if cart["items"]:
            product_id = cart["items"][0]["product_id"]
            
            response = auth_session.put(f"{BASE_URL}/api/cart/update", json={
                "product_id": product_id,
                "quantity": 5
            })
            assert response.status_code == 200
            print("Updated cart item quantity")
    
    def test_remove_from_cart(self, auth_session):
        """Test removing item from cart"""
        # Get cart
        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        if cart["items"]:
            product_id = cart["items"][0]["product_id"]
            
            response = auth_session.delete(f"{BASE_URL}/api/cart/remove/{product_id}")
            assert response.status_code == 200
            print(f"Removed product {product_id} from cart")
    
    def test_clear_cart(self, auth_session):
        """Test clearing entire cart"""
        response = auth_session.delete(f"{BASE_URL}/api/cart/clear")
        assert response.status_code == 200
        
        # Verify cart is empty
        cart = auth_session.get(f"{BASE_URL}/api/cart").json()
        assert len(cart["items"]) == 0
        print("Cart cleared successfully")


class TestMetrics:
    """Observability and metrics tests"""
    
    def test_real_metrics_endpoint(self):
        """Test /api/metrics/real returns SRI data"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        data = response.json()
        
        # Verify SRI structure
        assert "sri" in data
        assert "nodes" in data
        assert "edges" in data
        assert "eigenvalues" in data
        assert "source" in data
        assert data["source"] == "real"
        
        print(f"SRI: {data['sri']:.4f}, Nodes: {len(data['nodes'])}")
    
    def test_metrics_summary(self):
        """Test /api/metrics/summary returns business stats"""
        response = requests.get(f"{BASE_URL}/api/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_orders" in data
        assert "total_users" in data
        assert "total_products" in data
        assert "total_revenue" in data
        print(f"Summary: {data}")
    
    def test_transaction_metrics(self):
        """Test /api/metrics/transactions returns transaction data"""
        response = requests.get(f"{BASE_URL}/api/metrics/transactions")
        assert response.status_code == 200
        data = response.json()
        
        assert "by_category" in data
        assert "by_status" in data
        assert "hourly" in data
        assert "recent_orders" in data
        print(f"Transaction metrics: {len(data['recent_orders'])} recent orders")
    
    def test_sri_history(self):
        """Test /api/metrics/sri-history returns historical data"""
        response = requests.get(f"{BASE_URL}/api/metrics/sri-history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"SRI history: {len(data)} entries")
    
    def test_grafana_url_endpoint(self):
        """Test /api/metrics/grafana-url returns Grafana info"""
        response = requests.get(f"{BASE_URL}/api/metrics/grafana-url")
        assert response.status_code == 200
        data = response.json()
        
        assert "grafana_url" in data
        assert data["grafana_url"] == "/api/grafana/"
        print(f"Grafana URL: {data}")


class TestGrafanaProxy:
    """Grafana proxy endpoint tests"""
    
    def test_grafana_redirect_page(self):
        """Test /api/grafana returns HTML page"""
        response = requests.get(f"{BASE_URL}/api/grafana")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Grafana" in response.text
        print("Grafana redirect page loads correctly")
    
    def test_grafana_health(self):
        """Test /api/grafana/api/health returns Grafana health"""
        response = requests.get(f"{BASE_URL}/api/grafana/api/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "database" in data
        assert data["database"] == "ok"
        assert "version" in data
        print(f"Grafana health: {data}")
    
    def test_grafana_dashboard_page(self):
        """Test Grafana dashboard page loads via proxy"""
        response = requests.get(f"{BASE_URL}/api/grafana/d/spectral-resilience?orgId=1&kiosk")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "grafanaBootData" in response.text or "Grafana" in response.text
        print("Grafana dashboard page loads via proxy")
    
    def test_grafana_css_assets(self):
        """Test Grafana CSS assets load via proxy"""
        # First get the main page to find CSS filename
        main_page = requests.get(f"{BASE_URL}/api/grafana/")
        
        # Extract CSS filename from HTML
        import re
        css_match = re.search(r'href="(public/build/grafana\.dark\.[^"]+\.css)"', main_page.text)
        if css_match:
            css_path = css_match.group(1)
            response = requests.get(f"{BASE_URL}/api/grafana/{css_path}")
            assert response.status_code == 200
            print(f"Grafana CSS loads: {css_path}")
        else:
            print("CSS path not found in HTML, skipping asset test")


class TestAlerts:
    """Alert system tests"""
    
    def test_get_alerts(self):
        """Test /api/alerts returns alert list"""
        response = requests.get(f"{BASE_URL}/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} alerts")
    
    def test_get_alert_config(self):
        """Test /api/alerts/config returns thresholds"""
        response = requests.get(f"{BASE_URL}/api/alerts/config")
        assert response.status_code == 200
        data = response.json()
        
        assert "sri_critical" in data
        assert "sri_warning" in data
        assert "latency_critical" in data
        assert "error_rate_critical" in data
        print(f"Alert config: {data}")


class TestAdminEndpoints:
    """Admin-only endpoint tests"""
    
    @pytest.fixture
    def admin_session(self):
        """Create admin authenticated session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return session
    
    def test_admin_get_all_orders(self, admin_session):
        """Test admin can get all orders"""
        response = admin_session.get(f"{BASE_URL}/api/admin/orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Admin sees {len(data)} orders")
    
    def test_non_admin_cannot_access_admin_orders(self):
        """Test non-admin cannot access admin endpoints"""
        # Create a regular user session
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"regular_{int(time.time())}@example.com",
            "password": "testpass",
            "name": "Regular User"
        })
        
        response = session.get(f"{BASE_URL}/api/admin/orders")
        assert response.status_code == 403
        print("Non-admin correctly denied access to admin endpoints")


class TestEcommerceFlow:
    """End-to-end e-commerce flow test"""
    
    def test_complete_purchase_flow(self):
        """Test complete flow: browse -> add to cart -> checkout"""
        session = requests.Session()
        
        # 1. Register/Login
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        print("Step 1: Logged in")
        
        # 2. Browse products
        products = session.get(f"{BASE_URL}/api/products").json()
        assert len(products) > 0
        product = products[0]
        print(f"Step 2: Found product - {product['name']} @ ${product['price']}")
        
        # 3. Clear cart first
        session.delete(f"{BASE_URL}/api/cart/clear")
        
        # 4. Add to cart
        session.post(f"{BASE_URL}/api/cart/add", json={
            "product_id": product["id"],
            "quantity": 3
        })
        print("Step 3: Added to cart")
        
        # 5. Verify cart
        cart = session.get(f"{BASE_URL}/api/cart").json()
        assert len(cart["items"]) > 0
        print(f"Step 4: Cart verified - {len(cart['items'])} items")
        
        # 6. Create order
        order_response = session.post(f"{BASE_URL}/api/orders", json={
            "delivery_address": "123 Test Street, Test City",
            "phone": "555-1234"
        })
        assert order_response.status_code == 200
        order = order_response.json()
        print(f"Step 5: Order created - ID: {order['id']}, Total: ${order['total']}")
        
        # 7. Verify order
        order_detail = session.get(f"{BASE_URL}/api/orders/{order['id']}").json()
        assert order_detail["status"] == "pending"
        print(f"Step 6: Order verified - Status: {order_detail['status']}")
        
        # 8. Cart should be empty after order
        cart_after = session.get(f"{BASE_URL}/api/cart").json()
        assert len(cart_after["items"]) == 0
        print("Step 7: Cart cleared after order")
        
        print("E-commerce flow completed successfully!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
