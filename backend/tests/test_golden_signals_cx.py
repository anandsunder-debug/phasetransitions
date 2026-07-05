"""
Test suite for Golden Signals, Customer Experience, and Enhanced Healing features
Tests the new observability enhancements including:
- Golden Signals API (Latency, Traffic, Errors, Saturation)
- Customer Experience metrics (Apdex, P50/P95/P99, Availability, Error Budget)
- Enhanced /api/metrics/real with golden_signals, customer_experience, signal_contributions
- Enhanced /api/healing/status with golden_signals, signal_contributions, alert_driven
- POST /api/healing/toggle with both enabled and alert_driven fields
- POST /api/healing/trigger with correction_factors and golden_signals_before/after
- GET /api/healing/recommendations with golden_signals and correction_history
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestGoldenSignalsAPI:
    """Test GET /api/metrics/golden-signals endpoint"""
    
    def test_golden_signals_returns_4_signals(self):
        """Verify golden signals endpoint returns all 4 signals"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        
        data = response.json()
        assert "signals" in data
        signals = data["signals"]
        
        # Verify all 4 golden signals present
        assert "latency" in signals
        assert "traffic" in signals
        assert "errors" in signals
        assert "saturation" in signals
    
    def test_golden_signals_have_health_scores(self):
        """Verify each signal has health score and value"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        
        data = response.json()
        signals = data["signals"]
        
        for signal_key in ["latency", "traffic", "errors", "saturation"]:
            signal = signals[signal_key]
            assert "value" in signal
            assert "health" in signal
            assert "unit" in signal
            assert "threshold" in signal
            assert 0 <= signal["health"] <= 1
    
    def test_golden_signals_have_sri_contributions(self):
        """Verify signal_contributions field is present"""
        response = requests.get(f"{BASE_URL}/api/metrics/golden-signals")
        assert response.status_code == 200
        
        data = response.json()
        assert "signal_contributions" in data
        assert "sri" in data
        
        contributions = data["signal_contributions"]
        for key in ["latency", "traffic", "errors", "saturation"]:
            assert key in contributions


class TestCustomerExperienceAPI:
    """Test GET /api/metrics/customer-experience endpoint"""
    
    def test_customer_experience_returns_apdex(self):
        """Verify Apdex score is returned"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        
        data = response.json()
        assert "apdex" in data
        assert "apdex_label" in data
        assert 0 <= data["apdex"] <= 1
    
    def test_customer_experience_returns_percentiles(self):
        """Verify P50/P95/P99 latency percentiles"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        
        data = response.json()
        assert "p50" in data
        assert "p95" in data
        assert "p99" in data
        assert data["p50"] <= data["p95"] <= data["p99"]
    
    def test_customer_experience_returns_availability(self):
        """Verify availability metric"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        
        data = response.json()
        assert "availability" in data
        assert 0 <= data["availability"] <= 100
    
    def test_customer_experience_returns_error_budget(self):
        """Verify error budget structure"""
        response = requests.get(f"{BASE_URL}/api/metrics/customer-experience")
        assert response.status_code == 200
        
        data = response.json()
        assert "error_budget" in data
        
        budget = data["error_budget"]
        assert "slo" in budget
        assert "total" in budget
        assert "consumed" in budget
        assert "remaining" in budget
        assert "remaining_pct" in budget


class TestEnhancedMetricsReal:
    """Test GET /api/metrics/real includes new fields"""
    
    def test_metrics_real_includes_golden_signals(self):
        """Verify /api/metrics/real includes golden_signals"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        
        data = response.json()
        assert "golden_signals" in data
        
        gs = data["golden_signals"]
        for key in ["latency", "traffic", "errors", "saturation"]:
            assert key in gs
    
    def test_metrics_real_includes_customer_experience(self):
        """Verify /api/metrics/real includes customer_experience"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        
        data = response.json()
        assert "customer_experience" in data
        
        cx = data["customer_experience"]
        assert "apdex" in cx
        assert "p50" in cx
        assert "availability" in cx
    
    def test_metrics_real_includes_signal_contributions(self):
        """Verify /api/metrics/real includes signal_contributions"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        
        data = response.json()
        assert "signal_contributions" in data
        
        contrib = data["signal_contributions"]
        for key in ["latency", "traffic", "errors", "saturation"]:
            assert key in contrib


class TestEnhancedHealingStatus:
    """Test GET /api/healing/status includes new fields"""
    
    def test_healing_status_includes_golden_signals(self):
        """Verify /api/healing/status includes golden_signals"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "golden_signals" in data
        
        gs = data["golden_signals"]
        for key in ["latency", "traffic", "errors", "saturation"]:
            assert key in gs
    
    def test_healing_status_includes_signal_contributions(self):
        """Verify /api/healing/status includes signal_contributions"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "signal_contributions" in data
    
    def test_healing_status_includes_alert_driven(self):
        """Verify /api/healing/status includes alert_driven field"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "alert_driven" in data
        assert isinstance(data["alert_driven"], bool)


class TestHealingToggle:
    """Test POST /api/healing/toggle with enabled and alert_driven"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before tests"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"}
        )
        if login_response.status_code != 200:
            pytest.skip("Admin login failed")
        yield
        # Reset to default state
        self.session.post(
            f"{BASE_URL}/api/healing/toggle",
            json={"enabled": False, "alert_driven": True}
        )
    
    def test_toggle_enabled_field(self):
        """Test toggling enabled field"""
        response = self.session.post(
            f"{BASE_URL}/api/healing/toggle",
            json={"enabled": True}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] == True
        assert "message" in data
    
    def test_toggle_alert_driven_field(self):
        """Test toggling alert_driven field"""
        response = self.session.post(
            f"{BASE_URL}/api/healing/toggle",
            json={"alert_driven": False}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["alert_driven"] == False
    
    def test_toggle_both_fields(self):
        """Test toggling both enabled and alert_driven"""
        response = self.session.post(
            f"{BASE_URL}/api/healing/toggle",
            json={"enabled": True, "alert_driven": True}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] == True
        assert data["alert_driven"] == True


class TestHealingTrigger:
    """Test POST /api/healing/trigger returns correction_factors and golden signals"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as admin before tests"""
        self.session = requests.Session()
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"}
        )
        if login_response.status_code != 200:
            pytest.skip("Admin login failed")
    
    def test_trigger_returns_correction_factors(self):
        """Test healing trigger returns correction_factors"""
        # Use rate_limit as it has shorter cooldown
        response = self.session.post(
            f"{BASE_URL}/api/healing/trigger",
            json={"action_id": "rate_limit"}
        )
        
        # May fail due to cooldown, check both cases
        if response.status_code == 200:
            data = response.json()
            assert "correction_factors" in data
            
            cf = data["correction_factors"]
            for key in ["latency", "traffic", "errors", "saturation"]:
                assert key in cf
                assert "before" in cf[key]
                assert "after" in cf[key]
                assert "delta" in cf[key]
                assert "correction_factor" in cf[key]
        elif response.status_code == 400:
            # Cooldown active - this is expected behavior
            data = response.json()
            assert "detail" in data
            assert "Cooldown" in data["detail"]
    
    def test_trigger_returns_golden_signals_before_after(self):
        """Test healing trigger returns golden_signals_before and golden_signals_after"""
        response = self.session.post(
            f"{BASE_URL}/api/healing/trigger",
            json={"action_id": "queue_drain"}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "golden_signals_before" in data
            assert "golden_signals_after" in data
            
            for key in ["latency", "traffic", "errors", "saturation"]:
                assert key in data["golden_signals_before"]
                assert key in data["golden_signals_after"]
        elif response.status_code == 400:
            # Cooldown active
            pass


class TestHealingRecommendations:
    """Test GET /api/healing/recommendations includes golden_signals and correction_history"""
    
    def test_recommendations_includes_golden_signals(self):
        """Verify recommendations endpoint includes golden_signals"""
        response = requests.get(f"{BASE_URL}/api/healing/recommendations")
        assert response.status_code == 200
        
        data = response.json()
        assert "golden_signals" in data
        
        gs = data["golden_signals"]
        for key in ["latency", "traffic", "errors", "saturation"]:
            assert key in gs
    
    def test_recommendations_includes_correction_history(self):
        """Verify recommendations endpoint includes correction_history"""
        response = requests.get(f"{BASE_URL}/api/healing/recommendations")
        assert response.status_code == 200
        
        data = response.json()
        assert "correction_history" in data
        assert isinstance(data["correction_history"], list)


class TestSRIBaselineCalibration:
    """Test SRI baseline calibration behavior"""
    
    def test_sri_baseline_value(self):
        """Verify SRI baseline is around 0.85"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        
        data = response.json()
        assert "baseline_sri" in data
        assert data["baseline_sri"] == 0.85
    
    def test_warmup_complete_field(self):
        """Verify warmup_complete field exists"""
        response = requests.get(f"{BASE_URL}/api/metrics/real")
        assert response.status_code == 200
        
        data = response.json()
        assert "warmup_complete" in data
        assert isinstance(data["warmup_complete"], bool)


class TestExistingFeatures:
    """Test existing features still work"""
    
    def test_products_endpoint(self):
        """Verify products endpoint works"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_categories_endpoint(self):
        """Verify categories endpoint works"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_admin_login(self):
        """Verify admin login works"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@freshcart.com", "password": "admin123"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Login returns user data directly or wrapped in 'user' key
        user_data = data.get("user", data)
        assert user_data["role"] == "admin"
    
    def test_health_endpoint(self):
        """Verify health endpoint works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
