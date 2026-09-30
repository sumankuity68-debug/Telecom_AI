"""
Comprehensive test suite for TelecomAI Phase B:
- Step 6: FastAPI Endpoints
- Step 7: Database (PostgreSQL/SQLite dual-layer)
- Step 8: Authentication & JWT
- Step 9: API-based Tools
- Step 10: Mock Telecom APIs
"""
import sys
import os
import unittest
from fastapi.testclient import TestClient

# Ensure root directory is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import get_db, SessionLocal
from backend.models import AuditLog


class TestPhaseB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_root_and_health(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"].upper(), "ONLINE")

    def test_02_customer_profile(self):
        res = self.client.get("/api/customers/CUST001")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["customer_id"], "CUST001")
        self.assertEqual(data["name"], "Aarav Sharma")

    def test_03_customer_plan(self):
        res = self.client.get("/api/customers/CUST001/plan")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("plan_name", data)
        self.assertIn("price", data)

    def test_04_customer_usage(self):
        res = self.client.get("/api/customers/CUST001/usage")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

        # Test standalone usage endpoint
        res2 = self.client.get("/api/usage/CUST001")
        self.assertEqual(res2.status_code, 200)
        self.assertIsInstance(res2.json(), list)

    def test_05_customer_bill(self):
        res = self.client.get("/api/customers/CUST001/bill")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_amount", data)

        # Test standalone billing endpoint
        res2 = self.client.get("/api/billing/CUST001")
        self.assertEqual(res2.status_code, 200)
        self.assertIn("total_amount", res2.json())

    def test_06_customer_tickets(self):
        res = self.client.get("/api/customers/CUST001/tickets")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)

    def test_07_all_plans(self):
        res = self.client.get("/api/plans")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_08_network_and_outages(self):
        res = self.client.get("/api/network/Kolkata")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data, list)

        res_outages = self.client.get("/api/outages")
        self.assertEqual(res_outages.status_code, 200)
        outages = res_outages.json()
        self.assertIsInstance(outages, list)

    def test_09_create_ticket(self):
        payload = {
            "customer_id": "CUST001",
            "category": "Billing",
            "description": "Test billing inquiry ticket from Phase B test",
            "priority": "low"
        }
        res = self.client.post("/api/tickets", json=payload)
        self.assertEqual(res.status_code, 201)
        ticket = res.json()
        self.assertTrue(ticket["ticket_id"].startswith("TEL"))
        self.assertEqual(ticket["customer_id"], "CUST001")

    def test_10_auth_flow(self):
        import uuid
        username = f"user_{uuid.uuid4().hex[:6]}"
        email = f"{username}@example.com"
        password = "SecurePassword123!"

        # Register
        reg_res = self.client.post("/api/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
            "customer_id": "CUST001"
        })
        self.assertEqual(reg_res.status_code, 201)
        token = reg_res.json()["access_token"]
        self.assertIsNotNone(token)

        # Me with token
        headers = {"Authorization": f"Bearer {token}"}
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["username"], username)
        self.assertEqual(me_data["customer_id"], "CUST001")

        # Login
        login_res = self.client.post("/api/auth/login", json={
            "username": username,
            "password": password
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("access_token", login_res.json())

    def test_11_mock_carrier_endpoints(self):
        # Mock network
        res_net = self.client.get("/api/mock/network/Downtown")
        self.assertEqual(res_net.status_code, 200)
        self.assertIn("towers", res_net.json())

        # Mock customer
        res_cust = self.client.get("/api/mock/customer/CUST001")
        self.assertEqual(res_cust.status_code, 200)
        self.assertEqual(res_cust.json()["customer"]["customer_id"], "CUST001")

        # Mock recharge
        res_rech = self.client.post("/api/mock/recharge", json={
            "customer_id": "CUST001",
            "amount": 299.0,
            "payment_method": "UPI"
        })
        self.assertEqual(res_rech.status_code, 200)
        self.assertEqual(res_rech.json()["status"].lower(), "success")

        # Mock change plan
        res_change = self.client.post("/api/mock/change-plan", json={
            "customer_id": "CUST001",
            "new_plan_id": "P006"
        })
        self.assertEqual(res_change.status_code, 200)
        self.assertEqual(res_change.json()["status"].lower(), "success")

    def test_12_operator_lookup_and_airtel_override(self):
        from authy import lookup_phone_telecom_details
        airtel_info = lookup_phone_telecom_details("8609056545")
        self.assertTrue(airtel_info["valid"])
        self.assertEqual(airtel_info["operator"], "Bharti Airtel")
        self.assertEqual(airtel_info["technology"], "5G Plus")
        self.assertEqual(airtel_info["circle"], "West Bengal & Kolkata")

        jio_info = lookup_phone_telecom_details("9883633066")
        self.assertTrue(jio_info["valid"])
        self.assertEqual(jio_info["operator"], "Reliance Jio")


if __name__ == "__main__":
    unittest.main()

