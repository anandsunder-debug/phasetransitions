"""
Auto-Healing Engine API Tests
Tests for: Healing Status, Toggle, Trigger, History, Recommendations
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://delivery-metrics-hub-1.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@freshcart.com")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "admin123")

# All 5 healing actions
HEALING_ACTIONS = ["cache_flush", "rate_limit", "circuit_breaker", "connection_pool_reset", "queue_drain"]


class TestHealingStatusEndpoint:
    """Tests for GET /api/healing/status"""
    
    def test_healing_status_returns_200(self):
        """Test /api/healing/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        print("Healing status endpoint returns 200")
    
    def test_healing_status_structure(self):
        """Test /api/healing/status returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "enabled" in data
        assert "actions" in data
        assert "current_sri" in data
        assert "recommendations" in data
        assert "active_healers" in data
        assert "total_actions_executed" in data
        assert "recent_history" in data
        
        print(f"Healing status: enabled={data['enabled']}, SRI={data['current_sri']:.4f}")
    
    def test_healing_status_has_all_5_actions(self):
        """Test /api/healing/status contains all 5 healing actions"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        assert response.status_code == 200
        data = response.json()
        
        actions = data["actions"]
        for action_id in HEALING_ACTIONS:
            assert action_id in actions, f"Missing action: {action_id}"
            action = actions[action_id]
            assert "action_id" in action
            assert "name" in action
            assert "target_node" in action
            assert "description" in action
            assert "sri_impact" in action
            assert "cooldown" in action
            assert "can_execute" in action
        
        print(f"All 5 healing actions present: {list(actions.keys())}")
    
    def test_healing_status_action_details(self):
        """Test each action has correct target node"""
        response = requests.get(f"{BASE_URL}/api/healing/status")
        data = response.json()
        actions = data["actions"]
        
        expected_targets = {
            "cache_flush": "Cache",
            "rate_limit": "API",
            "circuit_breaker": "Backend",
            "connection_pool_reset": "DB",
            "queue_drain": "Queue"
        }
        
        for action_id, expected_node in expected_targets.items():
            assert actions[action_id]["target_node"] == expected_node
            print(f"{action_id} targets {expected_node} - OK")


class TestHealingRecommendationsEndpoint:
    """Tests for GET /api/healing/recommendations"""
    
    def test_recommendations_returns_200(self):
        """Test /api/healing/recommendations returns 200"""
        response = requests.get(f"{BASE_URL}/api/healing/recommendations")
        assert response.status_code == 200
        print("Recommendations endpoint returns 200")
    
    def test_recommendations_structure(self):
        """Test /api/healing/recommendations returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/healing/recommendations")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_sri" in data
        assert "recommendations" in data
        assert "recovery_path" in data
        
        assert isinstance(data["recommendations"], list)
        assert isinstance(data["recovery_path"], list)
        
        print(f"Current SRI: {data['current_sri']:.4f}, Recommendations: {len(data['recommendations'])}, Recovery path steps: {len(data['recovery_path'])}")
    
    def test_recommendations_have_correct_fields(self):
        """Test recommendation items have required fields"""
        response = requests.get(f"{BASE_URL}/api/healing/recommendations")
        data = response.json()
        
        if data["recommendations"]:
            rec = data["recommendations"][0]
            required_fields = ["action_id", "action_name", "target_node", "description", 
                            "effect", "urgency", "priority", "current_sri", "projected_sri",
                            "sri_improvement", "can_execute", "node_metrics"]
            for field in required_fields:
                assert field in rec, f"Missing field in recommendation: {field}"
            print(f"Recommendation structure verified: {rec['action_name']}")
        else:
            print("No recommendations (system healthy)")


class TestHealingHistoryEndpoint:
    """Tests for GET /api/healing/history"""
    
    def test_history_returns_200(self):
        """Test /api/healing/history returns 200"""
        response = requests.get(f"{BASE_URL}/api/healing/history")
        assert response.status_code == 200
        print("History endpoint returns 200")
    
    def test_history_returns_array(self):
        """Test /api/healing/history returns array"""
        response = requests.get(f"{BASE_URL}/api/healing/history")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        print(f"History contains {len(data)} entries")
    
    def test_history_with_limit(self):
        """Test /api/healing/history respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/healing/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) <= 5
        print(f"History with limit=5 returned {len(data)} entries")


class TestHealingToggleEndpoint:
    """Tests for POST /api/healing/toggle"""
    
    @pytest.fixture
    def admin_session(self):
        """Create admin authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return session
    
    def test_toggle_requires_auth(self):
        """Test /api/healing/toggle requires authentication"""
        response = requests.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": True})
        assert response.status_code == 401
        print("Toggle correctly requires authentication")
    
    def test_toggle_requires_admin(self):
        """Test /api/healing/toggle requires admin role"""
        # Create regular user session
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"regular_heal_{int(time.time())}@example.com",
            "password": "testpass",
            "name": "Regular User"
        })
        
        response = session.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": True})
        assert response.status_code == 403
        print("Toggle correctly requires admin role")
    
    def test_toggle_enable_autoheal(self, admin_session):
        """Test enabling auto-healing"""
        response = admin_session.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": True})
        assert response.status_code == 200
        data = response.json()
        
        assert data["enabled"] == True
        assert "message" in data
        print(f"Auto-healing enabled: {data['message']}")
    
    def test_toggle_disable_autoheal(self, admin_session):
        """Test disabling auto-healing"""
        response = admin_session.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": False})
        assert response.status_code == 200
        data = response.json()
        
        assert data["enabled"] == False
        assert "message" in data
        print(f"Auto-healing disabled: {data['message']}")
    
    def test_toggle_verify_state_persists(self, admin_session):
        """Test toggle state persists"""
        # Enable
        admin_session.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": True})
        
        # Verify via status
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        assert status["enabled"] == True
        
        # Disable
        admin_session.post(f"{BASE_URL}/api/healing/toggle", json={"enabled": False})
        
        # Verify via status
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        assert status["enabled"] == False
        
        print("Toggle state persists correctly")


class TestHealingTriggerEndpoint:
    """Tests for POST /api/healing/trigger"""
    
    @pytest.fixture
    def admin_session(self):
        """Create admin authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return session
    
    def test_trigger_requires_auth(self):
        """Test /api/healing/trigger requires authentication"""
        response = requests.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "cache_flush"})
        assert response.status_code == 401
        print("Trigger correctly requires authentication")
    
    def test_trigger_requires_admin(self):
        """Test /api/healing/trigger requires admin role"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"regular_trig_{int(time.time())}@example.com",
            "password": "testpass",
            "name": "Regular User"
        })
        
        response = session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "cache_flush"})
        assert response.status_code == 403
        print("Trigger correctly requires admin role")
    
    def test_trigger_invalid_action_id(self, admin_session):
        """Test trigger rejects invalid action_id"""
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "invalid_action"})
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"Invalid action rejected: {data['detail']}")
    
    def test_trigger_cache_flush(self, admin_session):
        """Test triggering cache_flush action"""
        # First check if action can execute
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        if not status["actions"]["cache_flush"]["can_execute"]:
            pytest.skip("cache_flush on cooldown")
        
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "cache_flush"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_id"] == "cache_flush"
        assert data["action_name"] == "Cache Flush"
        assert data["target_node"] == "Cache"
        assert "sri_before" in data
        assert "sri_after" in data
        assert "sri_delta" in data
        assert data["status"] == "success"
        
        print(f"Cache flush executed: SRI {data['sri_before']} -> {data['sri_after']} (delta: {data['sri_delta']})")
    
    def test_trigger_rate_limit(self, admin_session):
        """Test triggering rate_limit action"""
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        if not status["actions"]["rate_limit"]["can_execute"]:
            pytest.skip("rate_limit on cooldown")
        
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "rate_limit"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_id"] == "rate_limit"
        assert data["target_node"] == "API"
        print(f"Rate limiter executed: SRI {data['sri_before']} -> {data['sri_after']}")
    
    def test_trigger_circuit_breaker(self, admin_session):
        """Test triggering circuit_breaker action"""
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        if not status["actions"]["circuit_breaker"]["can_execute"]:
            pytest.skip("circuit_breaker on cooldown")
        
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "circuit_breaker"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_id"] == "circuit_breaker"
        assert data["target_node"] == "Backend"
        print(f"Circuit breaker executed: SRI {data['sri_before']} -> {data['sri_after']}")
    
    def test_trigger_connection_pool_reset(self, admin_session):
        """Test triggering connection_pool_reset action"""
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        if not status["actions"]["connection_pool_reset"]["can_execute"]:
            pytest.skip("connection_pool_reset on cooldown")
        
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "connection_pool_reset"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_id"] == "connection_pool_reset"
        assert data["target_node"] == "DB"
        print(f"Connection pool reset executed: SRI {data['sri_before']} -> {data['sri_after']}")
    
    def test_trigger_queue_drain(self, admin_session):
        """Test triggering queue_drain action"""
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        if not status["actions"]["queue_drain"]["can_execute"]:
            pytest.skip("queue_drain on cooldown")
        
        response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": "queue_drain"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["action_id"] == "queue_drain"
        assert data["target_node"] == "Queue"
        print(f"Queue drain executed: SRI {data['sri_before']} -> {data['sri_after']}")
    
    def test_trigger_cooldown_respected(self, admin_session):
        """Test that cooldown is respected on second trigger"""
        # First, find an action that was just executed (on cooldown)
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        
        # Find an action on cooldown
        action_on_cooldown = None
        for action_id, action in status["actions"].items():
            if not action["can_execute"] and action["last_executed"]:
                action_on_cooldown = action_id
                break
        
        if not action_on_cooldown:
            # Execute one to put it on cooldown
            for action_id in HEALING_ACTIONS:
                if status["actions"][action_id]["can_execute"]:
                    admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": action_id})
                    action_on_cooldown = action_id
                    break
        
        if action_on_cooldown:
            # Try to execute again - should fail with cooldown error
            response = admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": action_on_cooldown})
            assert response.status_code == 400
            data = response.json()
            assert "cooldown" in data["detail"].lower() or "remaining" in data["detail"].lower()
            print(f"Cooldown respected for {action_on_cooldown}: {data['detail']}")
        else:
            pytest.skip("No action available to test cooldown")


class TestHealingHistoryAfterTrigger:
    """Test that history is updated after trigger"""
    
    @pytest.fixture
    def admin_session(self):
        """Create admin authenticated session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        return session
    
    def test_history_updated_after_trigger(self, admin_session):
        """Test that history contains the triggered action"""
        # Get initial history count
        initial_history = requests.get(f"{BASE_URL}/api/healing/history").json()
        initial_count = len(initial_history)
        
        # Find an action that can execute
        status = requests.get(f"{BASE_URL}/api/healing/status").json()
        executable_action = None
        for action_id, action in status["actions"].items():
            if action["can_execute"]:
                executable_action = action_id
                break
        
        if not executable_action:
            pytest.skip("No action available to execute")
        
        # Execute the action
        admin_session.post(f"{BASE_URL}/api/healing/trigger", json={"action_id": executable_action})
        
        # Check history increased
        new_history = requests.get(f"{BASE_URL}/api/healing/history").json()
        assert len(new_history) > initial_count
        
        # Verify the latest entry
        latest = new_history[-1]
        assert latest["action_id"] == executable_action
        assert latest["triggered_by"] == "manual"
        assert "sri_before" in latest
        assert "sri_after" in latest
        
        print(f"History updated: {executable_action} added, total entries: {len(new_history)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
