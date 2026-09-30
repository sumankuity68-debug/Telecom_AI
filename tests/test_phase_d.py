"""
Phase D — Comprehensive State-Changing Actions & Confirmation Test Suite:
- TEST 1: Ticket preview (no DB mutation)
- TEST 2: Ticket confirmation (DB state changes, ticket created)
- TEST 3: Ticket cancellation (DB state remains unchanged)
- TEST 4: Plan change preview (no DB mutation)
- TEST 5: Plan change confirmation (DB state changes, subscription updated)
- TEST 6: Plan change cancellation (DB state remains unchanged)
- TEST 7: Recharge preview (no DB mutation)
- TEST 8: Recharge confirmation (MOCK/DEMO transaction processed)
- TEST 9: Recharge cancellation (cancellation logged, no transaction)
- TEST 10: Audit log creation (actions tracked with timestamps and user)
- TEST 11: JWT authorization (unauthenticated requests rejected with 401)
- TEST 12: Customer ownership protection (User A cannot mutate User B, returns 403)
- TEST 13: Invalid plan handling (returns 404 / error)
- TEST 14: Invalid recharge amount handling (<= 0 rejected with 400)
- TEST 15: Pending action expiration / stale action handling
- TEST 16: Agent action routing (previews, neutral phrase handling, confirm, cancel)
"""

import os
import sys
import unittest
import datetime
import uuid
from fastapi.testclient import TestClient

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import SessionLocal
from backend.models import User, Customer, Subscription, Ticket, AuditLog
from backend.auth import create_access_token, hash_password
from database import query_database
from confirmation import (
    create_pending_action,
    get_pending_action,
    cancel_pending_action,
    confirm_and_execute_pending_action,
    prepare_plan_change_preview,
    prepare_recharge_preview,
    prepare_ticket_preview,
    is_confirmation_phrase,
    is_cancellation_phrase,
    _PENDING_ACTIONS,
)
from agent import ask_telecom_agent, detect_intent


class TestPhaseDActions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()

        # Seed test user 1 (CUST001)
        cls.u1_name = f"user1_{uuid.uuid4().hex[:6]}"
        cls.user1 = User(
            username=cls.u1_name,
            email=f"{cls.u1_name}@example.com",
            hashed_password=hash_password("Password123!"),
            customer_id="CUST001",
            is_active=True,
        )
        db.add(cls.user1)

        # Seed test user 2 (CUST002) for ownership violation tests
        cls.u2_name = f"user2_{uuid.uuid4().hex[:6]}"
        cls.user2 = User(
            username=cls.u2_name,
            email=f"{cls.u2_name}@example.com",
            hashed_password=hash_password("Password123!"),
            customer_id="CUST002",
            is_active=True,
        )
        db.add(cls.user2)

        # Ensure CUST001 subscription exists and is reset to P003 (5G Basic)
        sub1 = db.query(Subscription).filter(Subscription.customer_id == "CUST001").first()
        if sub1:
            sub1.plan_id = "P003"
        else:
            sub1 = Subscription(
                subscription_id="SUB001",
                customer_id="CUST001",
                plan_id="P003",
                start_date="2026-09-01",
                expiry_date="2026-09-29",
                status="active",
            )
            db.add(sub1)

        db.commit()
        db.close()

        # Generate JWT tokens
        cls.token_user1 = create_access_token({"sub": cls.u1_name, "customer_id": "CUST001"})
        cls.token_user2 = create_access_token({"sub": cls.u2_name, "customer_id": "CUST002"})

    def setUp(self):
        # Clear in-memory pending actions before each test
        _PENDING_ACTIONS.clear()

    # ------------------------------------------------------------
    # 1. TICKET PREVIEW
    # ------------------------------------------------------------
    def test_01_ticket_preview(self):
        """Test 1: Ticket preview shows details and does NOT mutate DB tickets table."""
        count_before = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))

        preview = prepare_ticket_preview(
            customer_id="CUST001",
            description="Internet drops every 10 minutes",
            category="network",
            priority="high",
        )

        self.assertTrue(preview.get("valid"))
        self.assertEqual(preview.get("action_type"), "create_ticket")
        self.assertEqual(preview.get("customer_id"), "CUST001")
        self.assertIn("Internet drops every 10 minutes", preview.get("preview_text"))

        # Verify DB tickets count remains identical
        count_after = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))
        self.assertEqual(count_before, count_after, "Database tickets must not change during preview")

    # ------------------------------------------------------------
    # 2. TICKET CONFIRMATION
    # ------------------------------------------------------------
    def test_02_ticket_confirmation(self):
        """Test 2: Ticket confirmation executes creation in DB and returns real ticket ID."""
        count_before = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))

        prev = prepare_ticket_preview("CUST001", "Slow network issue", "network", "high")
        create_pending_action("CUST001", "create_ticket", prev["parameters"], prev)

        result = confirm_and_execute_pending_action("CUST001", auth_token=self.token_user1)

        self.assertIn("ticket_id", result)
        self.assertTrue(result["ticket_id"].startswith("TEL"))

        # Verify database state after confirmation
        count_after = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))
        self.assertEqual(count_after, count_before + 1, "Database tickets count must increase by 1 after confirmation")

    # ------------------------------------------------------------
    # 3. TICKET CANCELLATION
    # ------------------------------------------------------------
    def test_03_ticket_cancellation(self):
        """Test 3: Ticket cancellation discards pending action and leaves DB unchanged."""
        count_before = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))

        prev = prepare_ticket_preview("CUST001", "Cancelled inquiry", "general", "low")
        create_pending_action("CUST001", "create_ticket", prev["parameters"], prev)

        cancelled = cancel_pending_action("CUST001", reason="User decided not to raise ticket")
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled["status"], "cancelled")

        # Verify DB state remained untouched
        count_after = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))
        self.assertEqual(count_before, count_after, "Database tickets must not change after cancellation")

    # ------------------------------------------------------------
    # 4. PLAN CHANGE PREVIEW
    # ------------------------------------------------------------
    def test_04_plan_change_preview(self):
        """Test 4: Plan change preview displays current vs target plan and does NOT modify subscription."""
        df_sub_before = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        initial_plan = df_sub_before.iloc[0]["plan_id"]

        preview = prepare_plan_change_preview("CUST001", "P004")

        self.assertTrue(preview.get("valid"))
        self.assertEqual(preview.get("action_type"), "change_plan")
        self.assertIn("5G Plus", preview.get("preview_text"))
        self.assertIn("599", preview.get("preview_text"))

        # Verify database state before confirmation
        df_sub_after = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        current_plan = df_sub_after.iloc[0]["plan_id"]
        self.assertEqual(initial_plan, current_plan, "Subscription in DB must not change during plan preview")

    # ------------------------------------------------------------
    # 5. PLAN CHANGE CONFIRMATION
    # ------------------------------------------------------------
    def test_05_plan_change_confirmation(self):
        """Test 5: Explicit confirmation executes plan migration and updates DB subscription."""
        # Set subscription to P003 first
        db = SessionLocal()
        sub = db.query(Subscription).filter(Subscription.customer_id == "CUST001").first()
        sub.plan_id = "P003"
        db.commit()
        db.close()

        prev = prepare_plan_change_preview("CUST001", "P004")
        create_pending_action("CUST001", "change_plan", {"plan_id": "P004"}, prev)

        # Before confirmation: DB plan must still be P003
        df_before = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        self.assertEqual(df_before.iloc[0]["plan_id"], "P003")

        # Execute confirmation with auth token
        result = confirm_and_execute_pending_action("CUST001", auth_token=self.token_user1)

        self.assertEqual(result.get("status"), "SUCCESS")
        self.assertEqual(result.get("new_plan_id"), "P004")

        # After confirmation: DB plan MUST be P004
        df_after = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        self.assertEqual(df_after.iloc[0]["plan_id"], "P004", "DB subscription must be updated to P004")

    # ------------------------------------------------------------
    # 6. PLAN CHANGE CANCELLATION
    # ------------------------------------------------------------
    def test_06_plan_change_cancellation(self):
        """Test 6: User cancellation leaves customer subscription unchanged in database."""
        # Current plan is P004 from test 5
        df_before = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        plan_before = df_before.iloc[0]["plan_id"]

        prev = prepare_plan_change_preview("CUST001", "P005")
        create_pending_action("CUST001", "change_plan", {"plan_id": "P005"}, prev)

        cancel_pending_action("CUST001", reason="User cancelled plan upgrade")

        # After cancellation: DB plan must remain unchanged
        df_after = query_database("SELECT plan_id FROM subscriptions WHERE customer_id = 'CUST001'")
        plan_after = df_after.iloc[0]["plan_id"]
        self.assertEqual(plan_before, plan_after, "Subscription plan must not change after cancellation")

    # ------------------------------------------------------------
    # 7. RECHARGE PREVIEW
    # ------------------------------------------------------------
    def test_07_recharge_preview(self):
        """Test 7: Recharge preview generates clear mock/demo summary without executing recharge."""
        preview = prepare_recharge_preview("CUST001", 599.0)

        self.assertTrue(preview.get("valid"))
        self.assertEqual(preview.get("action_type"), "recharge")
        self.assertEqual(preview.get("parameters")["amount"], 599.0)
        self.assertIn("MOCK/DEMO", preview.get("preview_text"))
        self.assertIn("599.00", preview.get("preview_text"))

    # ------------------------------------------------------------
    # 8. RECHARGE CONFIRMATION
    # ------------------------------------------------------------
    def test_08_recharge_confirmation(self):
        """Test 8: Explicit recharge confirmation generates valid TXN transaction and logs audit."""
        prev = prepare_recharge_preview("CUST001", 599.0)
        create_pending_action("CUST001", "recharge", prev["parameters"], prev)

        result = confirm_and_execute_pending_action("CUST001", auth_token=self.token_user1)

        self.assertEqual(result.get("status"), "SUCCESS")
        self.assertTrue(result.get("demo_mode"))
        self.assertTrue(result.get("transaction_id", "").startswith("TXN"))
        self.assertEqual(result.get("amount"), 599.0)

        # Verify audit log recorded
        df_audit = query_database(
            "SELECT * FROM audit_logs WHERE customer_id = 'CUST001' AND action = 'RECHARGE_COMPLETED' ORDER BY id DESC LIMIT 1"
        )
        self.assertFalse(df_audit.empty)
        self.assertIn("599", df_audit.iloc[0]["details"])

    # ------------------------------------------------------------
    # 9. RECHARGE CANCELLATION
    # ------------------------------------------------------------
    def test_09_recharge_cancellation(self):
        """Test 9: Recharge cancellation records RECHARGE_CANCELLED in audit log without charging."""
        prev = prepare_recharge_preview("CUST001", 299.0)
        create_pending_action("CUST001", "recharge", prev["parameters"], prev)

        cancelled = cancel_pending_action("CUST001", reason="User decided not to proceed")
        self.assertIsNotNone(cancelled)

        df_audit = query_database(
            "SELECT * FROM audit_logs WHERE customer_id = 'CUST001' AND action = 'RECHARGE_CANCELLED' ORDER BY id DESC LIMIT 1"
        )
        self.assertFalse(df_audit.empty)

    # ------------------------------------------------------------
    # 10. AUDIT LOG CREATION
    # ------------------------------------------------------------
    def test_10_audit_log_creation(self):
        """Test 10: State-changing operations write rich audit records to audit_logs table."""
        df_logs = query_database("SELECT * FROM audit_logs WHERE customer_id = 'CUST001'")
        self.assertFalse(df_logs.empty)

        actions = df_logs["action"].tolist()
        # Verify requested, confirmed, completed, and cancelled audit markers exist
        self.assertTrue(any("REQUESTED" in act for act in actions))
        self.assertTrue(any("CONFIRMED" in act for act in actions))
        self.assertTrue(any("COMPLETED" in act for act in actions))

        # Check required columns
        for col in ["id", "timestamp", "customer_id", "action", "details", "status"]:
            self.assertIn(col, df_logs.columns)

    # ------------------------------------------------------------
    # 11. JWT AUTHORIZATION
    # ------------------------------------------------------------
    def test_11_jwt_authorization(self):
        """Test 11: Unauthenticated callers receive 401 Unauthorized on state-changing endpoints."""
        # Unauthenticated change plan
        res_plan = self.client.post("/api/customers/CUST001/change-plan", json={"new_plan_id": "P004"})
        self.assertEqual(res_plan.status_code, 401)

        # Unauthenticated recharge
        res_recharge = self.client.post("/api/recharge", json={"customer_id": "CUST001", "amount": 599.0})
        self.assertEqual(res_recharge.status_code, 401)

    # ------------------------------------------------------------
    # 12. CUSTOMER OWNERSHIP PROTECTION
    # ------------------------------------------------------------
    def test_12_customer_ownership_protection(self):
        """Test 12: User A cannot change User B's plan or recharge User B's account (403 Forbidden)."""
        headers_user2 = {"Authorization": f"Bearer {self.token_user2}"}

        # User 2 (CUST002) attempts to change plan for CUST001
        res_plan = self.client.post(
            "/api/customers/CUST001/change-plan",
            json={"new_plan_id": "P004"},
            headers=headers_user2,
        )
        self.assertEqual(res_plan.status_code, 403, "User cannot mutate another customer's plan")

        # User 2 (CUST002) attempts to recharge CUST001's account
        res_recharge = self.client.post(
            "/api/recharge",
            json={"customer_id": "CUST001", "amount": 599.0},
            headers=headers_user2,
        )
        self.assertEqual(res_recharge.status_code, 403, "User cannot recharge another customer's account")

    # ------------------------------------------------------------
    # 13. INVALID PLAN HANDLING
    # ------------------------------------------------------------
    def test_13_invalid_plan_handling(self):
        """Test 13: Attempting to change to a non-existent plan ID returns 404 / validation error."""
        # Preview validation
        preview = prepare_plan_change_preview("CUST001", "P999")
        self.assertFalse(preview.get("valid"))
        self.assertIn("error", preview)

        # Backend endpoint with valid token
        headers_user1 = {"Authorization": f"Bearer {self.token_user1}"}
        res = self.client.post(
            "/api/customers/CUST001/change-plan",
            json={"new_plan_id": "P999"},
            headers=headers_user1,
        )
        self.assertEqual(res.status_code, 404)

    # ------------------------------------------------------------
    # 14. INVALID RECHARGE AMOUNT HANDLING
    # ------------------------------------------------------------
    def test_14_invalid_recharge_amount_handling(self):
        """Test 14: Recharge amount <= 0 is rejected with 400 Bad Request."""
        # Negative amount
        prev_neg = prepare_recharge_preview("CUST001", -50.0)
        self.assertFalse(prev_neg.get("valid"))

        # Zero amount via API endpoint
        headers_user1 = {"Authorization": f"Bearer {self.token_user1}"}
        res_zero = self.client.post(
            "/api/recharge",
            json={"customer_id": "CUST001", "amount": 0.0},
            headers=headers_user1,
        )
        self.assertEqual(res_zero.status_code, 400)

        # Negative amount via API endpoint
        res_neg = self.client.post(
            "/api/recharge",
            json={"customer_id": "CUST001", "amount": -100.0},
            headers=headers_user1,
        )
        self.assertEqual(res_neg.status_code, 400)

    # ------------------------------------------------------------
    # 15. PENDING ACTION EXPIRATION / STALE ACTION
    # ------------------------------------------------------------
    def test_15_pending_action_expiration(self):
        """Test 15: Expired pending action cannot be executed and returns EXPIRED_OR_NOT_FOUND."""
        prev = prepare_plan_change_preview("CUST001", "P004")
        action = create_pending_action("CUST001", "change_plan", {"plan_id": "P004"}, prev, ttl_seconds=1)

        # Artificially age the pending action past expiration
        action["expires_at"] = datetime.datetime.now() - datetime.timedelta(seconds=10)

        # Attempt to fetch: get_pending_action should purge expired action
        fetched = get_pending_action("CUST001")
        self.assertIsNone(fetched, "Expired action must return None")

        # Attempt to confirm expired action
        exec_res = confirm_and_execute_pending_action("CUST001", auth_token=self.token_user1)
        self.assertEqual(exec_res.get("status"), "FAILED")
        self.assertEqual(exec_res.get("code"), "EXPIRED_OR_NOT_FOUND")

    # ------------------------------------------------------------
    # 16. AGENT ACTION ROUTING
    # ------------------------------------------------------------
    def test_16_agent_action_routing(self):
        """Test 16: End-to-end agent workflow for action previews, neutral phrases, confirmations, and cancellations."""
        ctx = {"customer_id": "CUST001", "name": "Aarav Sharma"}

        # Step A: Request creating a ticket
        res1 = ask_telecom_agent(
            "My internet has been slow for three days. Create a support ticket.",
            customer_context=ctx,
            return_metadata=True,
            auth_token=self.token_user1,
        )
        self.assertEqual(res1.get("intent"), "create_ticket_preview")
        self.assertIn("Would you like me to create this support ticket?", res1.get("answer"))

        # Step B: Ordinary conversation ("okay" / "thanks") must NOT execute confirmation
        res_neutral = ask_telecom_agent(
            "okay",
            customer_context=ctx,
            return_metadata=True,
            auth_token=self.token_user1,
        )
        self.assertEqual(res_neutral.get("intent"), "pending_action_reminder")
        self.assertIn("create ticket", res_neutral.get("answer").lower())
        self.assertIn("awaiting confirmation", res_neutral.get("answer").lower())

        # Step C: Explicit confirmation ("yes, create it") executes creation
        count_before = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))
        res_confirm = ask_telecom_agent(
            "yes, create it",
            customer_context=ctx,
            return_metadata=True,
            auth_token=self.token_user1,
        )
        self.assertEqual(res_confirm.get("intent"), "action_confirmed")
        self.assertIn("SUPPORT TICKET CREATED", res_confirm.get("answer"))

        count_after = len(query_database("SELECT * FROM tickets WHERE customer_id = 'CUST001'"))
        self.assertEqual(count_after, count_before + 1)

        # Step D: Plan change request and cancellation
        res_plan_req = ask_telecom_agent(
            "Change my plan to 5G Plus",
            customer_context=ctx,
            return_metadata=True,
            auth_token=self.token_user1,
        )
        self.assertEqual(res_plan_req.get("intent"), "change_plan_preview")
        self.assertIn("PLAN CHANGE REQUEST", res_plan_req.get("answer"))

        res_cancel = ask_telecom_agent(
            "cancel",
            customer_context=ctx,
            return_metadata=True,
            auth_token=self.token_user1,
        )
        self.assertEqual(res_cancel.get("intent"), "action_cancelled")
        self.assertIn("cancelled", res_cancel.get("answer").lower())


if __name__ == "__main__":
    unittest.main()
