import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

DATABASE_DIR = BASE_DIR / "database"

DATABASE_PATH = DATABASE_DIR / "telecom.db"

MODELS_DIR = BASE_DIR / "models"

KNOWLEDGE_DIR = BASE_DIR / "knowledge"


# Create directories if missing
DATABASE_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR.mkdir(exist_ok=True)


# ============================================================
# GROQ
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# Main text/reasoning model
LLM_MODEL = "openai/gpt-oss-120b"


# Current Groq multimodal model
VISION_MODEL = "qwen/qwen3.8-27b"


# Speech-to-text
WHISPER_MODEL = "whisper-large-v3"


# ============================================================
# MODEL FILES
# ============================================================

ANOMALY_MODEL_PATH = MODELS_DIR / "network_anomaly_model.pkl"

RAG_INDEX_PATH = MODELS_DIR / "rag_index.pkl"


# ============================================================
# APPLICATION
# ============================================================

APP_NAME = "TelecomAI"

APP_VERSION = "2.0.0"


# ============================================================
# VALIDATION
# ============================================================

if not GROQ_API_KEY:

    print(
        "WARNING: GROQ_API_KEY is not configured."
    )

    print(
        "Add your API key to E:\\telecom_ai\\.env"
    )