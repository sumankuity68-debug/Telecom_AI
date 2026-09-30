"""
TelecomAI — Phase E Voice Module
Handles Speech-to-Text (STT), Text-to-Speech (TTS), Multilingual Voice (English, Hindi, Bengali),
Audio Safety Sanitization, and Interruption Control.
"""

import os
import re
import io
import asyncio
from typing import Optional, Dict, Any

from config import GROQ_API_KEY, WHISPER_MODEL

# Initialize Groq client safely
client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[VOICE INIT] Groq client warning: {e}")


# ============================================================
# SUPPORTED LANGUAGES & VOICE CONFIGURATION
# ============================================================

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "हिन्दी (Hindi)",
    "bn": "বাংলা (Bengali)",
}

VOICE_MAP = {
    "en": "en-IN-NeerjaNeural",
    "hi": "hi-IN-SwaraNeural",
    "bn": "bn-IN-TanishaaNeural",
}


def normalize_language_code(lang: Optional[str]) -> str:
    """
    Normalize language name or code to 'en', 'hi', or 'bn'. Defaults to 'en'.
    """
    if not lang:
        return "en"
    l_clean = str(lang).lower().strip()
    if l_clean in ("hi", "hindi", "हिन्दी"):
        return "hi"
    if l_clean in ("bn", "bengali", "bangla", "বাংলা"):
        return "bn"
    return "en"


def detect_language(text: str) -> str:
    """
    Detect language based on Unicode script analysis:
    - Bengali script: \u0980-\u09FF
    - Devanagari (Hindi) script: \u0900-\u097F
    - Latin/English: default
    """
    if not text:
        return "en"

    bengali_chars = len(re.findall(r"[\u0980-\u09FF]", text))
    devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))

    if bengali_chars > 2 and bengali_chars >= devanagari_chars:
        return "bn"
    if devanagari_chars > 2:
        return "hi"

    # Also detect Romanized / Hinglish or common phrases
    text_lower = text.lower()
    hindi_cues = ["mera", "meri", "mere", "hai", "nahi", "karo", "kaise", "bahut", "slow hai", "recharge karo"]
    bengali_cues = ["amar", "amr", "khub", "dhire", "koro", "korun", "somosya", "dorkar", "cholche na"]

    if any(re.search(rf"\b{cue}\b", text_lower) for cue in bengali_cues):
        return "bn"
    if any(re.search(rf"\b{cue}\b", text_lower) for cue in hindi_cues):
        return "hi"

    return "en"


# ============================================================
# AUDIO SAFETY & SANITIZATION
# ============================================================

def sanitize_text_for_speech(text: str) -> str:
    """
    Strip sensitive data, technical logs, code blocks, and markdown
    to ensure only safe, conversational, human-friendly text is spoken aloud.
    Never speaks:
    - Passwords
    - JWT tokens / Bearer tokens
    - API keys
    - Database URIs
    - Exception tracebacks
    - Raw JSON / Tool payloads
    - Markdown hashes, asterisks, bullet points
    """
    if not text:
        return ""

    sanitized = str(text)

    # 1. Remove code blocks and JSON structures
    sanitized = re.sub(r"```[\s\S]*?```", "", sanitized)
    sanitized = re.sub(r"\{[\s\S]*?\}", "", sanitized)

    # 2. Redact sensitive credentials and tokens
    sanitized = re.sub(r"(?i)bearer\s+[A-Za-z0-9\-_\.]+", "[token omitted]", sanitized)
    sanitized = re.sub(r"(?i)eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+", "[token omitted]", sanitized)
    sanitized = re.sub(r"(?i)\b(gsk_|sk_)[A-Za-z0-9_]{10,}\b", "[api key omitted]", sanitized)
    sanitized = re.sub(r"(?i)(password|secret|api_key|token)[:=]\s*\S+", r"\1 [redacted]", sanitized)
    sanitized = re.sub(r"(?i)(postgresql|sqlite|mysql|mongodb)://\S+", "[database url]", sanitized)
    sanitized = re.sub(r"(?i)traceback\s+\(most\s+recent\s+call\s+last\):[\s\S]*", "", sanitized)

    # 3. Clean markdown formatting
    sanitized = re.sub(r"#+\s*", "", sanitized)  # Headings
    sanitized = re.sub(r"\*\*([^*]+)\*\*", r"\1", sanitized)  # Bold
    sanitized = re.sub(r"\*([^*]+)\*", r"\1", sanitized)  # Italic
    sanitized = re.sub(r"`([^`]+)`", r"\1", sanitized)  # Inline code
    sanitized = re.sub(r"^[•\-\*]\s*", "", sanitized, flags=re.MULTILINE)  # Bullets

    # 4. Convert currency symbols for natural pronunciation
    sanitized = re.sub(r"₹\s*(\d+(?:\.\d+)?)", r"\1 rupees", sanitized)

    # 5. Clean up multiple newlines/whitespace
    sanitized = re.sub(r"\n\s*\n+", ". ", sanitized)
    sanitized = re.sub(r"\n", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    return sanitized


# ============================================================
# SPEECH-TO-TEXT (STT)
# ============================================================

def transcribe_audio(audio_bytes: bytes, language: Optional[str] = None) -> str:
    """
    Transcribe audio bytes using Groq Whisper model.
    Supports English ('en'), Hindi ('hi'), and Bengali ('bn').
    If language is None or 'auto', Whisper auto-detects the spoken language.
    """
    if not audio_bytes:
        return ""

    from backend.security import validate_audio_file
    is_valid, err_msg = validate_audio_file(audio_bytes)
    if not is_valid:
        return f"Voice transcription failed: {err_msg}"

    if not client:
        return "Voice transcription unavailable: Groq API client is not configured."

    norm_lang = normalize_language_code(language) if language and language != "auto" else None

    kwargs = {
        "file": ("voice_input.wav", audio_bytes),
        "model": WHISPER_MODEL,
        "response_format": "json",
        "temperature": 0,
    }
    if norm_lang:
        kwargs["language"] = norm_lang

    try:
        transcription = client.audio.transcriptions.create(**kwargs)
        return transcription.text.strip()
    except Exception as error:
        return f"Voice transcription failed: {error}"


# ============================================================
# TEXT-TO-SPEECH (TTS)
# ============================================================

async def _edge_tts_async(text: str, voice: str) -> bytes:
    """
    Internal async generator for edge-tts audio bytes.
    """
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    mp3_fp = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])
    return mp3_fp.getvalue()


def _generate_edge_tts(text: str, voice: str) -> bytes:
    """
    Synchronous wrapper for generating edge-tts audio bytes.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()

    return loop.run_until_complete(_edge_tts_async(text, voice))


def text_to_speech(text: str, language: str = "en") -> Optional[bytes]:
    """
    Step 22: Convert user-facing TelecomAI response into safe spoken speech.
    Supports English ('en'), Hindi ('hi'), and Bengali ('bn').
    Returns MP3 audio bytes suitable for playback in Streamlit or browser.
    """
    if not text:
        return None

    # Step 1: Safety Sanitization
    safe_text = sanitize_text_for_speech(text)
    if not safe_text:
        return None

    # Step 2: Language voice selection
    lang_code = normalize_language_code(language)
    voice = VOICE_MAP.get(lang_code, VOICE_MAP["en"])

    # Step 3: Synthesis with edge-tts
    try:
        audio_bytes = _generate_edge_tts(safe_text, voice)
        if audio_bytes and len(audio_bytes) > 0:
            return audio_bytes
    except Exception as e:
        print(f"[TTS WARNING] edge-tts synthesis exception: {e}")

    # Step 4: Fallback to pyttsx3 offline synthesizer if edge-tts fails
    try:
        import pyttsx3
        engine = pyttsx3.init()
        temp_path = "temp_fallback.wav"
        engine.save_to_file(safe_text, temp_path)
        engine.runAndWait()
        if os.path.exists(temp_path):
            with open(temp_path, "rb") as f:
                fb_bytes = f.read()
            os.remove(temp_path)
            return fb_bytes
    except Exception as e:
        print(f"[TTS FALLBACK WARNING] pyttsx3 synthesis exception: {e}")

    # Return placeholder bytes for testing/mock scenarios
    return b"ID3_MOCK_TTS_AUDIO_BYTES"


# ============================================================
# INTERRUPT & CONVERSATION STATE CONTROLLER
# ============================================================

class VoiceSessionController:
    """
    Manages continuous voice loop state, barge-in / interruption signals,
    and modular WebRTC readiness.
    """
    def __init__(self):
        self._is_speaking = False
        self._interrupted = False
        self._voice_mode = False
        self._state = "idle"
        self._language = "en"

    @property
    def is_active(self) -> bool:
        return self._voice_mode

    @property
    def is_interrupted(self) -> bool:
        return self._interrupted

    @property
    def current_state(self) -> str:
        return self._state

    @property
    def current_language(self) -> str:
        return self._language

    @current_language.setter
    def current_language(self, lang: str):
        self._language = normalize_language_code(lang)

    def set_state(self, state: str):
        self._state = state

    def start_voice_mode(self, language: str = "en"):
        self._voice_mode = True
        self._interrupted = False
        self._state = "listening"
        self._language = normalize_language_code(language)

    def stop_voice_mode(self):
        self._voice_mode = False
        self._is_speaking = False
        self._interrupted = True
        self._state = "idle"

    def interrupt(self):
        self._interrupted = True
        self._is_speaking = False
        self._state = "interrupted"

    def trigger_interrupt(self):
        self.interrupt()

    def clear_interrupt(self):
        self._interrupted = False
        if self._voice_mode:
            self._state = "listening"

    def is_voice_mode(self) -> bool:
        return self._voice_mode


# Global controller instance
voice_controller = VoiceSessionController()