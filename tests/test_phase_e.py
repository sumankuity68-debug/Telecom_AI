"""
Phase E Voice & Speech Unit Tests
Covers Steps 21-25:
1. Voice module imports
2. Speech-to-text interface
3. TTS interface
4. Language configuration
5. English language flow
6. Hindi language flow
7. Bengali language flow
8. Voice -> agent integration
9. Voice -> Phase C intelligence
10. Voice -> Phase D confirmation
11. Cancel voice action
12. Confirm voice action
13. Conversation memory preservation
14. Voice mode stop behavior
15. TTS safety filtering
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import io

from voice import (
    transcribe_audio,
    text_to_speech,
    detect_language,
    normalize_language_code,
    sanitize_text_for_speech,
    SUPPORTED_LANGUAGES,
    VoiceSessionController,
    voice_controller,
)
from agent import ask_telecom_agent
from confirmation import (
    create_pending_action,
    get_pending_action,
    cancel_pending_action,
    confirm_and_execute_pending_action,
    is_confirmation_phrase,
    is_cancellation_phrase,
)
from memory import save_message, get_recent_memory
from backend.database import SessionLocal
from backend.models import User
from backend.auth import create_access_token, hash_password


class TestPhaseEVoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        cls.test_user = db.query(User).filter(User.customer_id == "CUST001").first()
        if not cls.test_user:
            cls.test_user = User(
                username="voice_test_user",
                email="voice_test@example.com",
                hashed_password=hash_password("Password123!"),
                customer_id="CUST001",
                is_active=True,
            )
            db.add(cls.test_user)
            db.commit()
            db.refresh(cls.test_user)
        cls.test_username = cls.test_user.username
        db.close()

        cls.customer_context = {
            "customer_id": "CUST001",
            "name": "Aarav Sharma",
            "phone": "+91 98765 43210",
            "email": "aarav.sharma@example.com",
            "customer_type": "postpaid",
            "account_status": "active",
            "tenure_months": 24,
            "location": "Mumbai",
            "current_plan": {
                "plan_name": "5G Premium Unlimited",
                "price": 999.0,
                "data_gb": 100,
                "validity_days": 30,
                "technology": "5G",
            },
            "recent_bill": {
                "total_amount": 1178.82,
                "base_amount": 999.0,
                "tax_amount": 179.82,
                "status": "paid",
            },
            "open_tickets": 0,
            "recent_tickets": [],
        }

    # ----------------------------------------------------
    # 1. Voice module imports
    # ----------------------------------------------------
    def test_01_voice_module_imports(self):
        """Verify all Phase E voice exports exist and are callable."""
        self.assertTrue(callable(transcribe_audio))
        self.assertTrue(callable(text_to_speech))
        self.assertTrue(callable(detect_language))
        self.assertTrue(callable(normalize_language_code))
        self.assertTrue(callable(sanitize_text_for_speech))
        self.assertIsInstance(SUPPORTED_LANGUAGES, dict)
        self.assertIn("en", SUPPORTED_LANGUAGES)
        self.assertIn("hi", SUPPORTED_LANGUAGES)
        self.assertIn("bn", SUPPORTED_LANGUAGES)
        self.assertIsInstance(voice_controller, VoiceSessionController)

    # ----------------------------------------------------
    # 2. Speech-to-text interface
    # ----------------------------------------------------
    def test_02_speech_to_text_interface(self):
        """Verify STT interface handles empty input and mocks transcribe cleanly."""
        # Empty audio input handling
        res_empty = transcribe_audio(b"")
        self.assertEqual(res_empty, "")

        # Mocked Groq STT client
        fake_audio = b"RIFF....WAVEfmt ...."
        with patch("voice.client") as mock_client:
            mock_transcription = MagicMock()
            mock_transcription.text = "My 5G internet is very slow."
            mock_client.audio.transcriptions.create.return_value = mock_transcription

            transcript = transcribe_audio(fake_audio, language="en")
            self.assertEqual(transcript, "My 5G internet is very slow.")
            mock_client.audio.transcriptions.create.assert_called_once()

    # ----------------------------------------------------
    # 3. TTS interface
    # ----------------------------------------------------
    def test_03_tts_interface(self):
        """Verify text_to_speech generates audio safely for valid text."""
        # Empty text
        self.assertIsNone(text_to_speech(""))
        self.assertIsNone(text_to_speech(None))

        # Safe response generation
        with patch("voice._generate_edge_tts", return_value=b"ID3_MOCK_MP3_AUDIO_STREAM"):
            audio = text_to_speech("Your network health score is 95 out of 100.", language="en")
            self.assertIsNotNone(audio)
            self.assertIsInstance(audio, bytes)
            self.assertEqual(audio, b"ID3_MOCK_MP3_AUDIO_STREAM")

    # ----------------------------------------------------
    # 4. Language configuration
    # ----------------------------------------------------
    def test_04_language_configuration(self):
        """Verify language normalization, dictionary, and detection."""
        self.assertEqual(normalize_language_code("hindi"), "hi")
        self.assertEqual(normalize_language_code("HINDI"), "hi")
        self.assertEqual(normalize_language_code("HI"), "hi")
        self.assertEqual(normalize_language_code("bengali"), "bn")
        self.assertEqual(normalize_language_code("bangla"), "bn")
        self.assertEqual(normalize_language_code("english"), "en")
        self.assertEqual(normalize_language_code("unknown_lang"), "en")

        # Devanagari detection
        self.assertEqual(detect_language("मेरा इंटरनेट काम नहीं कर रहा है"), "hi")
        # Bengali script detection
        self.assertEqual(detect_language("আমার ইন্টারনেট খুব ধীর গতিতে চলছে"), "bn")
        # Romanized Hindi keyword detection
        self.assertEqual(detect_language("Mera internet bahut slow chal raha hai"), "hi")
        # Bengali Romanized keyword detection
        self.assertEqual(detect_language("amar net bondho hoye geche"), "bn")
        # English detection
        self.assertEqual(detect_language("What is my current monthly bill?"), "en")

    # ----------------------------------------------------
    # 5. English language flow
    # ----------------------------------------------------
    def test_05_english_language_flow(self):
        """Verify English language query returns English response and metadata."""
        res = ask_telecom_agent(
            "What is my current telecom plan?",
            self.customer_context,
            language="en",
            return_metadata=True,
        )
        self.assertIsInstance(res, dict)
        meta = res.get("language_metadata", {})
        self.assertEqual(meta.get("input_language"), "en")
        self.assertEqual(meta.get("output_language"), "en")
        self.assertIn("5G Premium Unlimited", res.get("answer", ""))

    # ----------------------------------------------------
    # 6. Hindi language flow
    # ----------------------------------------------------
    def test_06_hindi_language_flow(self):
        """Verify Hindi query detects Hindi and returns Hindi language metadata."""
        hindi_query = "Mera internet bahut slow hai"
        res = ask_telecom_agent(
            hindi_query,
            self.customer_context,
            language="hi",
            return_metadata=True,
        )
        self.assertIsInstance(res, dict)
        meta = res.get("language_metadata", {})
        self.assertEqual(meta.get("input_language"), "hi")
        self.assertEqual(meta.get("output_language"), "hi")
        # Answer must not be empty
        self.assertTrue(len(res.get("answer", "")) > 10)

    # ----------------------------------------------------
    # 7. Bengali language flow
    # ----------------------------------------------------
    def test_07_bengali_language_flow(self):
        """Verify Bengali query returns Bengali language metadata."""
        bengali_query = "আমার ইন্টারনেট খুব ধীর"
        res = ask_telecom_agent(
            bengali_query,
            self.customer_context,
            language="bn",
            return_metadata=True,
        )
        self.assertIsInstance(res, dict)
        meta = res.get("language_metadata", {})
        self.assertEqual(meta.get("input_language"), "bn")
        self.assertEqual(meta.get("output_language"), "bn")
        self.assertTrue(len(res.get("answer", "")) > 10)

    # ----------------------------------------------------
    # 8. Voice -> agent integration
    # ----------------------------------------------------
    def test_08_voice_to_agent_integration(self):
        """Verify voice transcription -> agent response -> TTS audio pipeline."""
        mock_speech_transcript = "What is my current balance and plan?"
        # Agent response
        agent_res = ask_telecom_agent(
            mock_speech_transcript,
            self.customer_context,
            return_metadata=True,
            language="en",
        )
        answer = agent_res.get("answer", "")
        self.assertTrue(len(answer) > 0)

        # TTS generation
        with patch("voice._generate_edge_tts", return_value=b"MOCK_SPEECH_AUDIO"):
            audio = text_to_speech(answer, language="en")
            self.assertIsNotNone(audio)
            self.assertEqual(audio, b"MOCK_SPEECH_AUDIO")

    # ----------------------------------------------------
    # 9. Voice -> Phase C intelligence
    # ----------------------------------------------------
    def test_09_voice_to_phase_c_intelligence(self):
        """Verify voice query triggers network diagnostics intelligence."""
        voice_query = "My 5G internet is very slow and lagging."
        res = ask_telecom_agent(
            voice_query,
            self.customer_context,
            return_metadata=True,
            language="en",
        )
        # Verify Phase C intelligence was engaged
        intel = res.get("tool_result")
        self.assertIsNotNone(intel)
        self.assertIn("diagnostics", intel)
        diag = intel["diagnostics"]
        self.assertIn("health_score", diag)
        self.assertIn("download_mbps", diag)

    # ----------------------------------------------------
    # 10. Voice -> Phase D confirmation
    # ----------------------------------------------------
    def test_10_voice_to_phase_d_confirmation(self):
        """Verify voice action request cannot bypass confirmation."""
        cust_id = self.customer_context["customer_id"]
        cancel_pending_action(cust_id)

        voice_action = "Change my plan to 5G Plus"
        res = ask_telecom_agent(
            voice_action,
            self.customer_context,
            return_metadata=True,
            language="en",
        )
        # Agent must prepare confirmation, NOT execute directly
        pending = get_pending_action(cust_id)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.get("action_type"), "change_plan")
        self.assertIn("confirm", res.get("answer", "").lower())

    # ----------------------------------------------------
    # 11. Cancel voice action
    # ----------------------------------------------------
    def test_11_cancel_voice_action(self):
        """Verify multilingual voice cancellation phrases."""
        self.assertTrue(is_cancellation_phrase("cancel"))
        self.assertTrue(is_cancellation_phrase("no, cancel it"))
        self.assertTrue(is_cancellation_phrase("नहीं, रद्द करें"))
        self.assertTrue(is_cancellation_phrase("না, বাতিল করুন"))

        # Agent cancellation flow
        cust_id = self.customer_context["customer_id"]
        create_pending_action(cust_id, "recharge", {"amount": 500}, {"details": "Recharge ₹500"})
        self.assertIsNotNone(get_pending_action(cust_id))

        res = ask_telecom_agent("नहीं, रद्द करो", self.customer_context, return_metadata=True, language="hi")
        self.assertIsNone(get_pending_action(cust_id))
        self.assertIn("cancelled", res.get("answer", "").lower())

    # ----------------------------------------------------
    # 12. Confirm voice action
    # ----------------------------------------------------
    def test_12_confirm_voice_action(self):
        """Verify multilingual voice confirmation phrases execute the action."""
        self.assertTrue(is_confirmation_phrase("yes, please confirm"))
        self.assertTrue(is_confirmation_phrase("हाँ, पुष्टि करें"))
        self.assertTrue(is_confirmation_phrase("হ্যাঁ, নিশ্চিত করুন"))

        # Agent confirmation execution with authenticated token
        cust_id = self.customer_context["customer_id"]
        token = create_access_token(data={"sub": self.test_username, "role": "customer", "customer_id": cust_id})
        create_pending_action(
            cust_id,
            "recharge",
            {"customer_id": cust_id, "amount": 299.0},
            {"details": "Recharge ₹299"},
            username=self.test_username,
        )
        self.assertIsNotNone(get_pending_action(cust_id))

        res = ask_telecom_agent(
            "Yes, confirm recharge",
            self.customer_context,
            return_metadata=True,
            language="en",
            auth_token=token,
            username=self.test_username,
        )
        self.assertIsNone(get_pending_action(cust_id))
        self.assertIn("success", res.get("answer", "").lower())

    # ----------------------------------------------------
    # 13. Conversation memory preservation
    # ----------------------------------------------------
    def test_13_conversation_memory_preservation(self):
        """Verify voice queries and responses are recorded in persistent memory."""
        cust_id = self.customer_context["customer_id"]
        save_message(cust_id, "user", "Voice query: check data balance", source="voice")
        save_message(cust_id, "assistant", "You have 82 GB remaining.", source="voice")

        recent = get_recent_memory(cust_id, limit=5)
        self.assertTrue(len(recent) >= 2)
        recent_texts = [m.get("content", "") for m in recent]
        self.assertTrue(any("Voice query: check data balance" in t for t in recent_texts))

    # ----------------------------------------------------
    # 14. Voice mode stop behavior
    # ----------------------------------------------------
    def test_14_voice_mode_stop_behavior(self):
        """Verify VoiceSessionController transitions and stop behavior."""
        ctrl = VoiceSessionController()
        self.assertFalse(ctrl.is_active)
        self.assertEqual(ctrl.current_state, "idle")

        ctrl.start_voice_mode(language="hi")
        self.assertTrue(ctrl.is_active)
        self.assertEqual(ctrl.current_state, "listening")
        self.assertEqual(ctrl.current_language, "hi")

        ctrl.set_state("speaking")
        self.assertEqual(ctrl.current_state, "speaking")

        # Barge-in interruption
        ctrl.interrupt()
        self.assertTrue(ctrl.is_interrupted)
        self.assertEqual(ctrl.current_state, "interrupted")

        # Stop voice mode
        ctrl.stop_voice_mode()
        self.assertFalse(ctrl.is_active)
        self.assertEqual(ctrl.current_state, "idle")

    # ----------------------------------------------------
    # 15. TTS safety filtering
    # ----------------------------------------------------
    def test_15_tts_safety_filtering(self):
        """Verify sanitize_text_for_speech strips sensitive tokens and internals."""
        unsafe_raw_text = (
            "Here is your result.\n"
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c\n"
            "password: supersecret123\n"
            "gsk_0123456789abcdefghijklmnopqrstuvwxyz1234\n"
            "postgresql://telecom_user:dbpassword123@localhost:5432/telecom_ai\n"
            "```json\n{\"internal_status\": \"error\", \"code\": 500}\n```\n"
            "Traceback (most recent call last):\n"
            "  File 'agent.py', line 42, in <module>\n"
            "ZeroDivisionError: division by zero"
        )
        cleaned = sanitize_text_for_speech(unsafe_raw_text)

        # Tokens, passwords, DB credentials, code blocks, and stack traces must be stripped
        self.assertNotIn("eyJhbGciOiJIUzI1Ni", cleaned)
        self.assertNotIn("supersecret123", cleaned)
        self.assertNotIn("gsk_0123456789", cleaned)
        self.assertNotIn("dbpassword123", cleaned)
        self.assertNotIn("internal_status", cleaned)
        self.assertNotIn("Traceback (most recent call last)", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("Here is your result", cleaned)


if __name__ == "__main__":
    unittest.main()
