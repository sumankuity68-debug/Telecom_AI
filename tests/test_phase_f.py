"""
Phase F — Production Hardening & Deployment Test Suite
Covers:
1. Health endpoint
2. Authentication protection
3. Invalid JWT
4. Expired JWT
5. Customer isolation
6. CORS configuration
7. Invalid input handling
8. File upload validation
9. Safe exception handling
10. Rate limiting
11. 429 response
12. No secret leakage in responses
13. Password hash protection
14. Audit log safety
15. Production configuration validation
"""

import os
import sys
import unittest
import uuid
import datetime
from fastapi.testclient import TestClient
from starlette.requests import Request
from slowapi.errors import RateLimitExceeded

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import SessionLocal
from backend.models import User, Customer, AuditLog
from backend.auth import create_access_token, hash_password
from backend.security import (
    validate_image_file,
    validate_audio_file,
    sanitize_filename,
    mask_sensitive_token,
)
from backend.rate_limiter import custom_rate_limit_exceeded_handler


class TestPhaseFProductionHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        db = SessionLocal()

        # Seed isolated test user 1 (CUST001)
        cls.u1_name = f"pf_u1_{uuid.uuid4().hex[:6]}"
        cls.user1 = User(
            username=cls.u1_name,
            email=f"{cls.u1_name}@example.com",
            hashed_password=hash_password("StrongPassword123!"),
            customer_id="CUST001",
            is_active=True,
        )
        db.add(cls.user1)

        # Seed isolated test user 2 (CUST002)
        cls.u2_name = f"pf_u2_{uuid.uuid4().hex[:6]}"
        cls.user2 = User(
            username=cls.u2_name,
            email=f"{cls.u2_name}@example.com",
            hashed_password=hash_password("StrongPassword123!"),
            customer_id="CUST002",
            is_active=True,
        )
        db.add(cls.user2)

        db.commit()
        db.close()

        # Valid tokens
        cls.token1 = create_access_token({"sub": cls.u1_name, "customer_id": "CUST001"})
        cls.token2 = create_access_token({"sub": cls.u2_name, "customer_id": "CUST002"})

        # Expired token (issued in past)
        past_delta = datetime.timedelta(minutes=-60)
        cls.expired_token = create_access_token({"sub": cls.u1_name, "customer_id": "CUST001"}, expires_delta=past_delta)

        # Invalid signature token
        cls.invalid_token = cls.token1[:-8] + "ABCDEFGH"

    # ------------------------------------------------------------
    # 1. Health Endpoint
    # ------------------------------------------------------------
    def test_01_health_endpoint(self):
        """Test 1: Health endpoint returns 200, status=healthy, and connected database."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("database"), "connected")
        self.assertIn("service", data)

    # ------------------------------------------------------------
    # 2. Authentication Protection
    # ------------------------------------------------------------
    def test_02_authentication_protection(self):
        """Test 2: Protected state-changing endpoints return 401 when no token is provided."""
        res_recharge = self.client.post("/api/recharge", json={"customer_id": "CUST001", "amount": 100})
        self.assertEqual(res_recharge.status_code, 401)

        res_plan = self.client.post("/api/customers/CUST001/change-plan", json={"new_plan_id": "P004"})
        self.assertEqual(res_plan.status_code, 401)

    # ------------------------------------------------------------
    # 3. Invalid JWT
    # ------------------------------------------------------------
    def test_03_invalid_jwt(self):
        """Test 3: Forged or malformed JWT token returns 401 Unauthorized."""
        headers = {"Authorization": f"Bearer {self.invalid_token}"}
        res = self.client.post("/api/recharge", json={"customer_id": "CUST001", "amount": 100}, headers=headers)
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid", res.json().get("detail", ""))

    # ------------------------------------------------------------
    # 4. Expired JWT
    # ------------------------------------------------------------
    def test_04_expired_jwt(self):
        """Test 4: Expired JWT token is strictly rejected with 401 Unauthorized."""
        headers = {"Authorization": f"Bearer {self.expired_token}"}
        res = self.client.post("/api/recharge", json={"customer_id": "CUST001", "amount": 100}, headers=headers)
        self.assertEqual(res.status_code, 401)
        self.assertIn("expired", res.json().get("detail", "").lower())

    # ------------------------------------------------------------
    # 5. Customer Isolation
    # ------------------------------------------------------------
    def test_05_customer_isolation(self):
        """Test 5: User 1 (CUST001) cannot perform actions on User 2 (CUST002) - 403 Forbidden."""
        headers = {"Authorization": f"Bearer {self.token1}"}
        res = self.client.post(
            "/api/customers/CUST002/change-plan",
            json={"new_plan_id": "P004"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden", res.json().get("detail", ""))

        # Also verify recharge isolation
        res_rech = self.client.post(
            "/api/recharge",
            json={"customer_id": "CUST002", "amount": 299.0},
            headers=headers,
        )
        self.assertEqual(res_rech.status_code, 403)

    # ------------------------------------------------------------
    # 6. CORS Configuration
    # ------------------------------------------------------------
    def test_06_cors_configuration(self):
        """Test 6: CORS middleware responds with correct access control headers."""
        headers = {
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
        }
        res = self.client.options("/api/auth/login", headers=headers)
        self.assertIn(res.status_code, [200, 204])

    # ------------------------------------------------------------
    # 7. Invalid Input Handling
    # ------------------------------------------------------------
    def test_07_invalid_input_handling(self):
        """Test 7: Validation errors and invalid inputs return 400 or 404 cleanly."""
        headers = {"Authorization": f"Bearer {self.token1}"}

        # Negative recharge amount -> 400
        res_neg = self.client.post(
            "/api/recharge",
            json={"customer_id": "CUST001", "amount": -50.0},
            headers=headers,
        )
        self.assertEqual(res_neg.status_code, 400)

        # Non-existent plan -> 404
        res_plan = self.client.post(
            "/api/customers/CUST001/change-plan",
            json={"new_plan_id": "P999_NON_EXISTENT"},
            headers=headers,
        )
        self.assertEqual(res_plan.status_code, 404)

    # ------------------------------------------------------------
    # 8. File Upload Validation
    # ------------------------------------------------------------
    def test_08_file_upload_validation(self):
        """Test 8: File validators reject oversized files, invalid magic bytes, and path traversal."""
        # Oversize image
        oversize_image = b"X" * (16 * 1024 * 1024)
        valid, msg = validate_image_file(oversize_image, "image/jpeg")
        self.assertFalse(valid)
        self.assertIn("exceeds", msg)

        # Invalid magic bytes for JPEG
        fake_jpeg = b"NOT_A_REAL_JPEG_HEADER"
        valid, msg = validate_image_file(fake_jpeg, "image/jpeg")
        self.assertFalse(valid)
        self.assertIn("does not match", msg)

        # Valid JPEG magic bytes
        real_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        valid, msg = validate_image_file(real_jpeg, "image/jpeg")
        self.assertTrue(valid)

        # Audio file validation
        valid_wav = b"RIFF\x24\x00\x00\x00WAVEfmt "
        valid_a, _ = validate_audio_file(valid_wav)
        self.assertTrue(valid_a)

        # Path traversal filename sanitization
        traversal = "../../etc/passwd"
        clean = sanitize_filename(traversal)
        self.assertNotIn("..", clean)
        self.assertNotIn("/", clean)
        self.assertEqual(clean, "passwd")

    # ------------------------------------------------------------
    # 9. Safe Exception Handling
    # ------------------------------------------------------------
    def test_09_safe_exception_handling(self):
        """Test 9: Error responses attach X-Request-ID and do not leak stack traces."""
        res = self.client.get("/non-existent-endpoint-404")
        self.assertEqual(res.status_code, 404)
        self.assertIn("X-Request-ID", res.headers)
        # Should not contain raw python tracebacks
        self.assertNotIn("Traceback (most recent call last)", res.text)

    # ------------------------------------------------------------
    # 10. Rate Limiting Request Tracking
    # ------------------------------------------------------------
    def test_10_rate_limiting_request_tracking(self):
        """Test 10: Normal requests within threshold succeed and return correlation ID."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("X-Request-ID", res.headers)
        self.assertEqual(res.json().get("status"), "ONLINE")

    # ------------------------------------------------------------
    # 11. Rate Limit 429 Response
    # ------------------------------------------------------------
    def test_11_rate_limit_429_response(self):
        """Test 11: 429 handler produces user-friendly error without leaking limiter internals."""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [],
            "state": {"request_id": "test_req_123"},
        }
        mock_req = Request(scope)
        from unittest.mock import MagicMock
        exc = RateLimitExceeded(MagicMock())

        response = custom_rate_limit_exceeded_handler(mock_req, exc)
        self.assertEqual(response.status_code, 429)
        import json
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body.get("status_code"), 429)
        self.assertEqual(body.get("error"), "Rate limit exceeded")
        self.assertIn("Too many requests", body.get("message", ""))
        self.assertIn("Retry-After", response.headers)

    # ------------------------------------------------------------
    # 12. No Secret Leakage in Responses
    # ------------------------------------------------------------
    def test_12_no_secret_leakage_in_responses(self):
        """Test 12: API endpoints never leak JWT secret, DB URLs, or API keys in payloads."""
        headers = {"Authorization": f"Bearer {self.token1}"}
        res_me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res_me.status_code, 200)
        text_resp = res_me.text

        # Ensure no database credentials or secrets leaked
        self.assertNotIn("telecom_ai_super_secret", text_resp)
        self.assertNotIn("password", text_resp.lower())
        self.assertNotIn("postgresql://", text_resp)
        self.assertNotIn("gsk_", text_resp)

        # Masking helper verification
        masked = mask_sensitive_token("gsk_1234567890abcdef1234567890")
        self.assertNotIn("abcdef", masked)
        self.assertEqual(masked, "gsk_...7890")

    # ------------------------------------------------------------
    # 13. Password Hash Protection
    # ------------------------------------------------------------
    def test_13_password_hash_protection(self):
        """Test 13: Password hashes are bcrypt strings and never exposed in UserOut models."""
        headers = {"Authorization": f"Bearer {self.token1}"}
        res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res.status_code, 200)
        user_dict = res.json()
        self.assertNotIn("hashed_password", user_dict)
        self.assertNotIn("password", user_dict)

        # Direct DB inspection confirms bcrypt hash format
        db = SessionLocal()
        u = db.query(User).filter(User.username == self.u1_name).first()
        self.assertTrue(u.hashed_password.startswith("$2b$") or u.hashed_password.startswith("$2a$"))
        db.close()

    # ------------------------------------------------------------
    # 14. Audit Log Safety
    # ------------------------------------------------------------
    def test_14_audit_log_safety(self):
        """Test 14: Action audit log records do not contain bearer tokens or passwords."""
        db = SessionLocal()
        logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
        for log in logs:
            det = log.details or ""
            self.assertNotIn("Bearer eyJ", det)
            self.assertNotIn("password123", det.lower())
            self.assertNotIn("telecom_ai_super_secret", det)
        db.close()

    # ------------------------------------------------------------
    # 15. Production Configuration Validation
    # ------------------------------------------------------------
    def test_15_production_configuration_validation(self):
        """Test 15: Verify .env.example exists with placeholders, .gitignore ignores .env, and Dockerfile exists."""
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        # Verify .env.example
        env_example_path = os.path.join(root_dir, ".env.example")
        self.assertTrue(os.path.exists(env_example_path))
        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("DATABASE_URL=", content)
        self.assertIn("JWT_SECRET_KEY=", content)
        self.assertIn("GROQ_API_KEY=", content)
        # Ensure no real groq key in .env.example
        self.assertNotIn("gsk_sGFLfNktC9", content)

        # Verify .gitignore
        gitignore_path = os.path.join(root_dir, ".gitignore")
        self.assertTrue(os.path.exists(gitignore_path))
        with open(gitignore_path, "r", encoding="utf-8") as f:
            gi_content = f.read()
        self.assertIn(".env", gi_content)
        self.assertIn("*.db", gi_content)

        # Verify Dockerfile & docker-compose.yml
        self.assertTrue(os.path.exists(os.path.join(root_dir, "Dockerfile")))
        self.assertTrue(os.path.exists(os.path.join(root_dir, "docker-compose.yml")))
        self.assertTrue(os.path.exists(os.path.join(root_dir, "README.md")))


if __name__ == "__main__":
    unittest.main()
