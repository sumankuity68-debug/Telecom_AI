"""
Live HTTP end-to-end test against the running FastAPI server:
- Tests all customer endpoints
- Tests plans endpoint
- Tests network and outage endpoints
- Tests ticket creation endpoint
- Tests JWT registration, login, and auth me endpoints
- Tests mock carrier endpoints
- Tests tools.py integration over HTTP
"""
import unittest
import requests
import uuid
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

BASE_URL = "http://127.0.0.1:8000"


class TestLiveFastAPI(unittest.TestCase):
    def test_01_root_health(self):
        r = requests.get(f"{BASE_URL}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ONLINE")

    def test_02_customer_endpoints(self):
        # Profile
        r = requests.get(f"{BASE_URL}/api/customers/CUST001")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Aarav Sharma")

        # Plan
        r = requests.get(f"{BASE_URL}/api/customers/CUST001/plan")
        self.assertEqual(r.status_code, 200)
        self.assertIn("plan_name", r.json())
        self.assertIn("price", r.json())

        # Usage
        r = requests.get(f"{BASE_URL}/api/customers/CUST001/usage")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()), 0)

        # Bill
        r = requests.get(f"{BASE_URL}/api/customers/CUST001/bill")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_amount"], 942.82)

        # Tickets
        r = requests.get(f"{BASE_URL}/api/customers/CUST001/tickets")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_03_plans(self):
        r = requests.get(f"{BASE_URL}/api/plans")
        self.assertEqual(r.status_code, 200)
        plans = r.json()
        self.assertGreater(len(plans), 0)

        # Filter plans
        r_filtered = requests.get(f"{BASE_URL}/api/plans?technology=5G&max_price=500")
        self.assertEqual(r_filtered.status_code, 200)

    def test_04_network_and_outages(self):
        r_all = requests.get(f"{BASE_URL}/api/network")
        self.assertEqual(r_all.status_code, 200)
        self.assertGreater(len(r_all.json()), 0)

        r_loc = requests.get(f"{BASE_URL}/api/network/Kolkata")
        self.assertEqual(r_loc.status_code, 200)
        self.assertGreater(len(r_loc.json()), 0)

        r_out = requests.get(f"{BASE_URL}/api/outages")
        self.assertEqual(r_out.status_code, 200)
        self.assertIsInstance(r_out.json(), list)

    def test_05_ticket_creation(self):
        payload = {
            "customer_id": "CUST001",
            "category": "Technical",
            "description": "Live API ticket submission test",
            "priority": "high",
        }
        r = requests.post(f"{BASE_URL}/api/tickets", json=payload)
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertTrue(data["ticket_id"].startswith("TEL"))
        self.assertEqual(data["customer_id"], "CUST001")

    def test_06_jwt_auth(self):
        uname = f"liveuser_{uuid.uuid4().hex[:6]}"
        pw = "CarrierGrade123!"
        r_reg = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "username": uname,
                "password": pw,
                "email": f"{uname}@example.com",
                "customer_id": "CUST001",
            },
        )
        self.assertEqual(r_reg.status_code, 201)
        token = r_reg.json()["access_token"]

        # Check me
        r_me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r_me.status_code, 200)
        self.assertEqual(r_me.json()["username"], uname)
        self.assertEqual(r_me.json()["customer_id"], "CUST001")

        # Login
        r_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": uname, "password": pw})
        self.assertEqual(r_login.status_code, 200)
        self.assertIn("access_token", r_login.json())

    def test_07_mock_telecom_apis(self):
        # Mock network
        r_net = requests.get(f"{BASE_URL}/api/mock/network/Kolkata")
        self.assertEqual(r_net.status_code, 200)
        self.assertIn("telemetry", r_net.json())

        # Mock customer
        r_cust = requests.get(f"{BASE_URL}/api/mock/customer/CUST001")
        self.assertEqual(r_cust.status_code, 200)
        self.assertEqual(r_cust.json()["customer"]["customer_id"], "CUST001")

        # Mock recharge
        r_rech = requests.post(
            f"{BASE_URL}/api/mock/recharge",
            json={"customer_id": "CUST001", "amount": 199.0, "payment_method": "NetBanking"},
        )
        self.assertEqual(r_rech.status_code, 200)
        self.assertEqual(r_rech.json()["status"], "SUCCESS")

        # Mock change plan
        r_cp = requests.post(
            f"{BASE_URL}/api/mock/change-plan",
            json={"customer_id": "CUST001", "new_plan_id": "P003"},
        )
        self.assertEqual(r_cp.status_code, 200)
        self.assertEqual(r_cp.json()["status"], "SUCCESS")

    def test_08_tools_via_fastapi(self):
        import tools
        # Profile
        p = tools.get_customer_profile("CUST001")
        self.assertEqual(p["customer_id"], "CUST001")

        # Current plan
        plan = tools.get_current_plan("CUST001")
        self.assertIn("plan_name", plan)

        # Usage
        u = tools.get_usage("CUST001")
        self.assertIsInstance(u, list)

        # Bill
        b = tools.get_bill("CUST001")
        self.assertIn("total_amount", b)

        # Network status
        net = tools.check_network_status("Kolkata")
        self.assertIsInstance(net, list)

        # Create ticket
        t = tools.create_support_ticket("CUST001", "network", "High latency observed", "medium")
        self.assertTrue(t["ticket_id"].startswith("TEL"))

    def test_09_otp_api(self):
        # Test OTP Send endpoint
        r_send = requests.post(f"{BASE_URL}/api/auth/otp/send", json={"phone": "9000000001"})
        self.assertEqual(r_send.status_code, 200)
        self.assertTrue(r_send.json()["success"])

        # Test OTP Verify with demo fallback code
        r_ver = requests.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": "9000000001", "otp": "123456"})
        self.assertEqual(r_ver.status_code, 200)
        self.assertIn("access_token", r_ver.json())

    def test_10_opencellid_api(self):
        # Test OpenCellID live tower endpoint
        r = requests.get(f"{BASE_URL}/api/network/live/opencellid?city=Kolkata")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("success"))
        self.assertGreater(data.get("total_towers", 0), 0)


if __name__ == "__main__":
    unittest.main()
