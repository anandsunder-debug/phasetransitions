#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime

class FreshCartAPITester:
    def __init__(self, base_url="https://delivery-metrics-hub-1.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_token = None
        self.user_token = None
        self.test_product_id = None
        self.test_order_id = None

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        return success

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, cookies=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if headers:
            test_headers.update(headers)

        try:
            if method == 'GET':
                response = self.session.get(url, headers=test_headers, cookies=cookies)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=test_headers, cookies=cookies)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=test_headers, cookies=cookies)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=test_headers, cookies=cookies)

            success = response.status_code == expected_status
            details = f"Expected {expected_status}, got {response.status_code}"
            if not success and response.text:
                try:
                    error_data = response.json()
                    details += f" - {error_data.get('detail', response.text[:100])}"
                except:
                    details += f" - {response.text[:100]}"

            return self.log_test(name, success, details), response

        except Exception as e:
            return self.log_test(name, False, f"Exception: {str(e)}"), None

    def test_health_check(self):
        """Test basic health endpoint"""
        success, response = self.run_test("Health Check", "GET", "health", 200)
        return success

    def test_admin_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST", 
            "auth/login",
            200,
            data={"email": "admin@freshcart.com", "password": "admin123"}
        )
        if success and response:
            try:
                data = response.json()
                if data.get('role') == 'admin':
                    # Store cookies for future requests
                    self.session.cookies.update(response.cookies)
                    print(f"   Admin logged in: {data.get('email')}")
                    return True
                else:
                    print(f"   Expected admin role, got: {data.get('role')}")
            except:
                print("   Failed to parse login response")
        return False

    def test_user_registration(self):
        """Test user registration"""
        timestamp = datetime.now().strftime("%H%M%S")
        test_email = f"test{timestamp}@example.com"
        
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register", 
            200,
            data={
                "email": test_email,
                "password": "test123",
                "name": "Test User"
            }
        )
        if success and response:
            try:
                data = response.json()
                print(f"   User registered: {data.get('email')}")
                return True
            except:
                print("   Failed to parse registration response")
        return False

    def test_user_login(self):
        """Test user login with test credentials"""
        # First register the test user
        timestamp = datetime.now().strftime("%H%M%S")
        test_email = f"testuser{timestamp}@example.com"
        
        # Register
        reg_success, reg_response = self.run_test(
            "Test User Registration",
            "POST",
            "auth/register",
            200,
            data={
                "email": test_email,
                "password": "test123", 
                "name": "Test User"
            }
        )
        
        if not reg_success:
            return False
            
        # Login
        success, response = self.run_test(
            "Test User Login",
            "POST",
            "auth/login",
            200,
            data={"email": test_email, "password": "test123"}
        )
        
        if success and response:
            try:
                data = response.json()
                print(f"   User logged in: {data.get('email')}")
                return True
            except:
                print("   Failed to parse login response")
        return False

    def test_products_api(self):
        """Test products endpoints"""
        # Get all products
        success, response = self.run_test("Get All Products", "GET", "products", 200)
        if not success:
            return False
            
        try:
            products = response.json()
            if len(products) > 0:
                self.test_product_id = products[0]['id']
                print(f"   Found {len(products)} products")
                
                # Test get single product
                success, _ = self.run_test(
                    "Get Single Product", 
                    "GET", 
                    f"products/{self.test_product_id}", 
                    200
                )
                if not success:
                    return False
                    
                # Test categories
                success, cat_response = self.run_test("Get Categories", "GET", "categories", 200)
                if success and cat_response:
                    categories = cat_response.json()
                    print(f"   Found categories: {categories}")
                    
                    # Test filter by category
                    if categories:
                        success, _ = self.run_test(
                            "Filter Products by Category",
                            "GET",
                            f"products?category={categories[0]}",
                            200
                        )
                        return success
                return True
            else:
                print("   No products found")
                return False
        except Exception as e:
            print(f"   Failed to parse products: {e}")
            return False

    def test_cart_operations(self):
        """Test cart operations (requires login)"""
        if not self.test_product_id:
            print("   Skipping cart tests - no product ID available")
            return False
            
        # Get empty cart
        success, response = self.run_test("Get Cart", "GET", "cart", 200)
        if not success:
            return False
            
        # Add item to cart
        success, _ = self.run_test(
            "Add to Cart",
            "POST",
            "cart/add",
            200,
            data={"product_id": self.test_product_id, "quantity": 2}
        )
        if not success:
            return False
            
        # Get cart with items
        success, response = self.run_test("Get Cart with Items", "GET", "cart", 200)
        if success and response:
            try:
                cart = response.json()
                items = cart.get('items', [])
                if len(items) > 0:
                    print(f"   Cart has {len(items)} items")
                    
                    # Update cart item
                    success, _ = self.run_test(
                        "Update Cart Item",
                        "PUT",
                        "cart/update",
                        200,
                        data={"product_id": self.test_product_id, "quantity": 3}
                    )
                    if not success:
                        return False
                        
                    return True
                else:
                    print("   Cart is empty after adding item")
                    return False
            except Exception as e:
                print(f"   Failed to parse cart: {e}")
                return False
        return False

    def test_checkout_and_orders(self):
        """Test checkout and order creation"""
        # Create order
        success, response = self.run_test(
            "Create Order",
            "POST",
            "orders",
            200,
            data={
                "delivery_address": "123 Test Street, Test City",
                "phone": "+1234567890"
            }
        )
        
        if success and response:
            try:
                order = response.json()
                self.test_order_id = order.get('id')
                print(f"   Order created: {self.test_order_id}")
                
                # Get orders list
                success, response = self.run_test("Get Orders", "GET", "orders", 200)
                if success and response:
                    orders = response.json()
                    print(f"   Found {len(orders)} orders")
                    
                    # Get specific order
                    if self.test_order_id:
                        success, _ = self.run_test(
                            "Get Order Details",
                            "GET",
                            f"orders/{self.test_order_id}",
                            200
                        )
                        return success
                return True
            except Exception as e:
                print(f"   Failed to parse order: {e}")
                return False
        return False

    def test_admin_endpoints(self):
        """Test admin-only endpoints"""
        if not self.test_order_id:
            print("   Skipping admin tests - no order ID available")
            return True
            
        # Re-login as admin to ensure proper session
        admin_success, admin_response = self.run_test(
            "Re-login as Admin",
            "POST", 
            "auth/login",
            200,
            data={"email": "admin@freshcart.com", "password": "admin123"}
        )
        
        if not admin_success:
            return False
            
        # Update session cookies
        if admin_response:
            self.session.cookies.update(admin_response.cookies)
            
        # Get all orders (admin)
        success, response = self.run_test("Admin Get All Orders", "GET", "admin/orders", 200)
        if success and response:
            try:
                orders = response.json()
                print(f"   Admin found {len(orders)} orders")
                
                # Update order status
                success, _ = self.run_test(
                    "Admin Update Order Status",
                    "PUT",
                    f"admin/orders/{self.test_order_id}/status?status=confirmed",
                    200
                )
                return success
            except Exception as e:
                print(f"   Failed to parse admin orders: {e}")
                return False
        return False

    def test_metrics_endpoints(self):
        """Test metrics and dashboard endpoints"""
        # Get metrics summary
        success, response = self.run_test("Get Metrics Summary", "GET", "metrics/summary", 200)
        if not success:
            return False
            
        # Test real metrics endpoint
        success, response = self.run_test("Get Real Metrics", "GET", "metrics/real", 200)
        if success and response:
            try:
                real_metrics = response.json()
                print(f"   Real SRI: {real_metrics.get('sri', 'N/A'):.4f}")
                print(f"   Real Nodes: {len(real_metrics.get('nodes', []))}")
                print(f"   Real Edges: {len(real_metrics.get('edges', []))}")
                print(f"   Source: {real_metrics.get('source', 'unknown')}")
            except Exception as e:
                print(f"   Failed to parse real metrics: {e}")
                return False
        else:
            return False
            
        # Test SRI history endpoint
        success, response = self.run_test("Get SRI History", "GET", "metrics/sri-history", 200)
        if success and response:
            try:
                sri_history = response.json()
                print(f"   SRI History entries: {len(sri_history)}")
            except Exception as e:
                print(f"   Failed to parse SRI history: {e}")
                return False
        else:
            return False
            
        # Generate traffic to update real metrics
        print("   Generating traffic to update real metrics...")
        traffic_success = True
        for i in range(5):
            # Make multiple API calls to generate traffic
            success1, _ = self.run_test(f"Traffic Gen Products {i+1}", "GET", "products", 200)
            success2, _ = self.run_test(f"Traffic Gen Categories {i+1}", "GET", "categories", 200)
            if not (success1 and success2):
                traffic_success = False
                break
                
        if not traffic_success:
            print("   Failed to generate traffic")
            return False
            
        # Check if real metrics updated after traffic generation
        success, response = self.run_test("Get Real Metrics After Traffic", "GET", "metrics/real", 200)
        if success and response:
            try:
                updated_metrics = response.json()
                print(f"   Updated Real SRI: {updated_metrics.get('sri', 'N/A'):.4f}")
                print(f"   Avg Latency: {updated_metrics.get('avg_latency', 'N/A'):.2f}ms")
                print(f"   Avg Error Rate: {updated_metrics.get('avg_error', 'N/A'):.4f}")
            except Exception as e:
                print(f"   Failed to parse updated metrics: {e}")
                return False
        else:
            return False
            
        # Simulate metrics (existing test)
        success, response = self.run_test(
            "Simulate Metrics",
            "POST",
            "metrics/simulate",
            200,
            data={
                "traffic_scale": 1000,
                "latency_scale": 50,
                "error_rate": 0.05,
                "saturation": 0.3,
                "failure_mode": "None"
            }
        )
        
        if success and response:
            try:
                metrics = response.json()
                print(f"   Simulated SRI: {metrics.get('sri', 'N/A'):.4f}")
                print(f"   Simulated Nodes: {len(metrics.get('nodes', []))}")
                print(f"   Simulated Edges: {len(metrics.get('edges', []))}")
                
                # Get metrics history
                success, _ = self.run_test("Get Metrics History", "GET", "metrics/history", 200)
                return success
            except Exception as e:
                print(f"   Failed to parse simulated metrics: {e}")
                return False
        return False

    def test_alerts_endpoints(self):
        """Test alert system endpoints"""
        # Get alerts list
        success, response = self.run_test("Get Alerts", "GET", "alerts", 200)
        if not success:
            return False
            
        try:
            alerts = response.json()
            print(f"   Found {len(alerts)} alerts")
        except Exception as e:
            print(f"   Failed to parse alerts: {e}")
            return False
            
        # Get alert configuration
        success, response = self.run_test("Get Alert Config", "GET", "alerts/config", 200)
        if success and response:
            try:
                config = response.json()
                print(f"   SRI Critical Threshold: {config.get('sri_critical')}")
                print(f"   SRI Warning Threshold: {config.get('sri_warning')}")
                print(f"   Latency Critical Threshold: {config.get('latency_critical')}ms")
                print(f"   Error Rate Critical Threshold: {config.get('error_rate_critical')}")
                print(f"   Alert Cooldown: {config.get('cooldown_seconds')}s")
            except Exception as e:
                print(f"   Failed to parse alert config: {e}")
                return False
        else:
            return False
            
        # Test generate traffic endpoint (should trigger alert checks)
        success, response = self.run_test("Generate Traffic for Alerts", "POST", "metrics/generate-traffic", 200)
        if not success:
            print("   Generate traffic endpoint failed")
            return False
            
        return True

    def test_websocket_endpoint(self):
        """Test WebSocket endpoint availability (connection test only)"""
        import socket
        import ssl
        from urllib.parse import urlparse
        
        try:
            # Parse the WebSocket URL
            ws_url = self.base_url.replace('/api', '').replace('https://', '').replace('http://', '')
            host = ws_url.split('/')[0]
            
            # Test if we can connect to the host on port 443 (HTTPS)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            
            # Wrap with SSL for HTTPS
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                result = ssock.connect_ex((host, 443))
                if result == 0:
                    print("✅ WebSocket endpoint host is reachable")
                    return True
                else:
                    print(f"❌ WebSocket endpoint host unreachable: {result}")
                    return False
                    
        except Exception as e:
            print(f"❌ WebSocket endpoint test failed: {e}")
            return False

    def run_all_tests(self):
        """Run comprehensive API test suite"""
        print("🚀 Starting FreshCart API Tests")
        print("=" * 50)
        
        # Basic connectivity
        if not self.test_health_check():
            print("❌ Health check failed - stopping tests")
            return False
            
        # Authentication tests
        print("\n📝 Testing Authentication...")
        admin_login_success = self.test_admin_login()
        user_reg_success = self.test_user_registration()
        user_login_success = self.test_user_login()
        
        if not (admin_login_success and user_reg_success and user_login_success):
            print("❌ Authentication tests failed - stopping")
            return False
            
        # Products tests
        print("\n🛍️ Testing Products...")
        if not self.test_products_api():
            print("❌ Products tests failed")
            return False
            
        # Cart tests (requires user login)
        print("\n🛒 Testing Cart...")
        if not self.test_cart_operations():
            print("❌ Cart tests failed")
            return False
            
        # Orders tests
        print("\n📦 Testing Orders...")
        if not self.test_checkout_and_orders():
            print("❌ Orders tests failed")
            return False
            
        # Admin tests
        print("\n👑 Testing Admin...")
        if not self.test_admin_endpoints():
            print("❌ Admin tests failed")
            return False
            
        # Metrics tests
        print("\n📊 Testing Metrics...")
        if not self.test_metrics_endpoints():
            print("❌ Metrics tests failed")
            return False
            
        # Alert tests
        print("\n🚨 Testing Alerts...")
        if not self.test_alerts_endpoints():
            print("❌ Alert tests failed")
            return False
            
        # WebSocket tests
        print("\n🔌 Testing WebSocket...")
        if not self.test_websocket_endpoint():
            print("❌ WebSocket tests failed")
            return False
            
        return True

def main():
    tester = FreshCartAPITester()
    
    try:
        success = tester.run_all_tests()
        
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} passed")
        
        if success and tester.tests_passed == tester.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("❌ Some tests failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted")
        return 1
    except Exception as e:
        print(f"\n💥 Test suite crashed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())