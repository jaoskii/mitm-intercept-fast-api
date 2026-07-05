import os
import shutil
import unittest
import json

# Force test database directory
TEST_DB_DIR = "test_data"
os.environ["DB_DIR"] = TEST_DB_DIR

# Import application components
from app import db
from app.main import app
from fastapi.testclient import TestClient

class TestMitmProxyInterceptor(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Ensure database is initialized in test dir
        db.init_db()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        # Cleanup test database folder
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)

    def setUp(self):
        # Clear database records between tests
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rules")
        cursor.execute("DELETE FROM logs")
        conn.commit()
        conn.close()

    def test_database_crud(self):
        # 1. Create a rule
        rule_id = db.create_rule(
            name="Mock API User response",
            method="GET",
            url_pattern="api/users",
            action="mock_response",
            is_active=1,
            status_code=200,
            response_body='{"users": []}'
        )
        self.assertIsNotNone(rule_id)
        
        # 2. Get rule
        rule = db.get_rule(rule_id)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["name"], "Mock API User response")
        self.assertEqual(rule["method"], "GET")
        self.assertEqual(rule["action"], "mock_response")
        self.assertEqual(rule["is_active"], 1)

        # 3. Get active rules
        active_rules = db.get_active_rules()
        self.assertEqual(len(active_rules), 1)

        # 4. Toggle rule
        db.toggle_rule(rule_id, 0)
        rule = db.get_rule(rule_id)
        self.assertEqual(rule["is_active"], 0)
        self.assertEqual(len(db.get_active_rules()), 0)

        # 5. Delete rule
        deleted = db.delete_rule(rule_id)
        self.assertTrue(deleted)
        self.assertIsNone(db.get_rule(rule_id))

    def test_fastapi_endpoints(self):
        # 1. Create rule via REST API
        rule_payload = {
            "name": "Test Header Rewrite",
            "method": "POST",
            "url_pattern": "submit-data",
            "action": "modify_request_headers",
            "is_active": 1,
            "headers_json": '{"X-Test-Inject": "True"}'
        }
        res = self.client.post("/api/rules", json=rule_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["status"], "success")
        rule_id = data["rule_id"]

        # 2. Fetch rules list
        res = self.client.get("/api/rules")
        self.assertEqual(res.status_code, 200)
        rules = res.json()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], rule_id)
        self.assertEqual(rules[0]["method"], "POST")

        # 3. Toggle rule via REST API
        res = self.client.patch(f"/api/rules/{rule_id}/toggle", json={"is_active": 0})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["is_active"], 0)

        # 4. Delete rule via REST API
        res = self.client.delete(f"/api/rules/{rule_id}")
        self.assertEqual(res.status_code, 200)

        # Confirm deleted
        res = self.client.get("/api/rules")
        self.assertEqual(len(res.json()), 0)

    def test_fastapi_logging_and_stream(self):
        # Mock internal reporting payload from proxy addon
        log_payload = {
            "method": "GET",
            "url": "https://httpbin.org/get",
            "request_headers": '{"User-Agent": "curl/7.79.1"}',
            "request_body": "",
            "response_status": 200,
            "response_headers": '{"Content-Type": "application/json"}',
            "response_body": '{"args": {}}',
            "intercepted": 0
        }
        
        # Report log to API
        res = self.client.post("/api/internal/log", json=log_payload)
        self.assertEqual(res.status_code, 200)
        log_id = res.json()["log_id"]

        # Check logs history list
        res = self.client.get("/api/logs")
        self.assertEqual(res.status_code, 200)
        logs = res.json()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["id"], log_id)
        self.assertEqual(logs[0]["url"], "https://httpbin.org/get")
        self.assertEqual(logs[0]["intercepted"], 0)

        # Clear logs
        res = self.client.delete("/api/logs")
        self.assertEqual(res.status_code, 200)
        res = self.client.get("/api/logs")
        self.assertEqual(len(res.json()), 0)

if __name__ == "__main__":
    unittest.main()
