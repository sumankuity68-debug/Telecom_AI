# TelecomAI • Production-Hardened Telecom Operations Platform

TelecomAI is an enterprise-grade AI co-pilot and automated telecom customer service operations platform. It combines autonomous agentic intelligence, real-time deterministic network telemetry diagnostics, machine learning anomaly detection, natural language multi-turn multilingual voice conversations, and state-changing telecom workflows protected by explicit user confirmation and JWT authorization.

---

## 1. Project Overview

TelecomAI bridges customer inquiries with live telecommunications backend systems. Subscribers can diagnose high packet loss and slow download speeds, analyze itemized bills, receive personalized tariff recommendations, file support tickets, change subscription plans, and recharge their accounts using text or natural voice in English, Hindi, and Bengali.

---

## 2. Architecture

```
                                  SUBSCRIBER
                                      │
                   ┌──────────────────┴──────────────────┐
                   ▼                                     ▼
        STREAMLIT WEB INTERFACE              VOICE / WEBRTC READY
        • Text Chat Mode                      • Groq Whisper v3 STT
        • Continuous Voice Mode               • Edge-TTS Neural Speech
        • Real-time Visual Telemetry          • Hindi / Bengali / English
        • Confirmation Dialogs                • Barge-in Interruption
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      ▼
                           TELECOM AGENT CO-PILOT
                                (agent.py)
                                      │
        ┌───────────────┬─────────────┼───────────────┬───────────────┐
        ▼               ▼             ▼               ▼               ▼
   DIAGNOSTICS     ANOMALY ML     OUTAGE NOC    RECOMMENDER     BILLING
  Deterministic    Isolation     Correlation    Plan heuristic   Itemized
  Health Scoring     Forest       Incidents       Analytics      Breakdown
        └───────────────┴─────────────┼───────────────┴───────────────┘
                                      ▼
                           CONFIRMATION WORKFLOW
                        (Two-phase safety & Audit)
                                      │
                                      ▼
                        FASTAPI REST MICROSERVICES
                        • JWT Auth & Bearer Tokens
                        • SlowAPI Rate Limiting
                        • Request ID Correlation
                        • Sensitive Data Scrubbing
                                      │
                                      ▼
                         ENTERPRISE DATABASE LAYER
                         • PostgreSQL (Production)
                         • SQLite (Local Development)
```

---

## 3. Features & Roadmap Milestones

* **Phase A — Domain Guardrails & Voice Baseline:** Strict telecom domain guardrails, SQLite memory, Groq LLM integration, Groq Whisper transcription.
* **Phase B — Real Telecom Backend:** FastAPI REST microservices, PostgreSQL schema abstraction, bcrypt password hashing, JWT bearer tokens, OpenCelliD live telemetry.
* **Phase C — Agent Intelligence:** Deterministic 0-100 network health scoring, Isolation Forest ML anomaly detection, active NOC outage correlation, usage-grounded plan recommendation, and bill analysis.
* **Phase D — Safe State-Changing Actions:** Action previews, two-phase confirmation gating, ticket creation, plan migration, demo recharges, and immutable action audit logging.
* **Phase E — Multilingual Voice Suite:** Continuous voice conversations, Microsoft Edge neural text-to-speech for Indian English, Hindi, and Bengali, barge-in priority handling, and persistent memory across voice/text.
* **Phase F — Production Hardening & Deployment:** Structured request monitoring, secret scrubbing filters, rate limiting via SlowAPI, configurable CORS, safe global exception handling, customer account isolation, and Docker deployment.

---

## 4. Folder Structure

```
telecom_ai/
├── app.py                      # Streamlit rich visual copilot frontend
├── agent.py                    # TelecomAI core reasoning & intent router
├── config.py                   # Central environment & model configuration
├── authy.py                    # Twilio SMS OTP & client authentication
├── confirmation.py             # Action preview, TTL staging & confirmation
├── database.py                 # Core database abstraction & CSV sync
├── diagnostics.py              # Deterministic network health scoring engine
├── anomaly_detection.py        # ML anomaly detection (Isolation Forest)
├── recommendations.py          # Tariff recommendation engine
├── billing_analysis.py         # Financial invoice breakdown & tax verification
├── outage_correlation.py       # NOC incident & tower outage correlation
├── memory.py                   # Persistent multi-turn conversation memory
├── voice.py                    # Speech-to-text, neural TTS & voice controller
├── vision_tools.py             # Multimodal speed-test & bill image analyzer
├── requirements.txt            # Python production dependencies
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # Container orchestration (DB, API, Frontend)
├── .env.example                # Configuration template (no credentials)
│
├── backend/                    # FastAPI REST API Backend
│   ├── main.py                 # Application factory, CORS, monitoring, routes
│   ├── auth.py                 # JWT generation, validation & bcrypt utilities
│   ├── dependencies.py         # Bearer auth & customer isolation dependencies
│   ├── database.py             # SQLAlchemy engine & session management
│   ├── models.py               # ORM entities (Users, Customers, Plans, Bills...)
│   ├── schemas.py              # Pydantic validation models
│   ├── monitoring.py           # Request ID middleware & structured logger
│   ├── security.py             # File, MIME, audio & magic-byte validators
│   ├── rate_limiter.py         # SlowAPI rate limiting & 429 handlers
│   ├── audit.py                # Audit logging helper
│   └── api/                    # Route endpoints
│       ├── auth.py             # User registration, login & SMS OTP
│       ├── customers.py        # Customer profile, plans, usage & migration
│       ├── recharge.py         # Account recharge (demo mode)
│       ├── tickets.py          # Support ticket creation & tracking
│       ├── plans.py            # Tariff catalog & plan search
│       ├── billing.py          # Itemized customer billing records
│       ├── usage.py            # Data, call & SMS usage history
│       └── network.py          # Tower telemetry & regional outages
│
└── tests/                      # Automated Regression & Verification Suites
    ├── test_phase_b.py         # Phase B backend tests
    ├── test_phase_c.py         # Phase C intelligence tests
    ├── test_phase_d.py         # Phase D confirmation & audit tests
    ├── test_phase_e.py         # Phase E voice, STT, TTS & multilingual tests
    ├── test_phase_f.py         # Phase F security, isolation, rate limit tests
    └── test_live_api.py        # Live HTTP integration tests
```

---

## 5. Environment Variables

Create `.env` in the project root based on `.env.example`:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `APP_ENV` | Environment mode (`production` / `development`) | `production` |
| `DATABASE_URL` | Database URI | `postgresql://user:pass@localhost:5432/telecom_ai` |
| `JWT_SECRET_KEY` | Secret key for signing JWT tokens | Cryptographic random string |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token validity in minutes | `1440` (24 hours) |
| `FASTAPI_BASE_URL` | Backend URL for Streamlit communication | `http://127.0.0.1:8000` |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins | `http://localhost:8501,http://127.0.0.1:8501` |
| `RATE_LIMIT_ENABLED` | Enable SlowAPI request rate limiting | `true` |
| `LOGIN_RATE_LIMIT` | Login attempts allowed per IP | `10/minute` |
| `OTP_RATE_LIMIT` | SMS OTP requests allowed per IP | `5/minute` |
| `STATE_CHANGE_RATE_LIMIT` | Recharges / Plan changes / Tickets | `10/minute` |
| `GROQ_API_KEY` | Groq Cloud API Key for Llama-3 & Whisper | `gsk_...` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID for real SMS OTP | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | Auth token |
| `TWILIO_PHONE_NUMBER` | Twilio sender phone number | `+1...` |
| `TWILIO_VERIFY_SERVICE_SID` | Twilio Verify Service SID | `VA...` |
| `OPENCELLID_API_KEY` | OpenCelliD API key for live cell towers | `pk....` |

---

## 6. Local Installation

### Prerequisites
* Python 3.11 or Python 3.12 (Windows / Linux / macOS)
* PostgreSQL 15+ (optional for local dev; SQLite fallback is supported)

### Step 1: Clone and Create Virtual Environment
```powershell
cd E:\telecom_ai
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 7. Database Setup

### Option A: PostgreSQL (Production Recommended)
1. Ensure PostgreSQL is running on `localhost:5432`.
2. Create database and user:
```sql
CREATE DATABASE telecom_ai;
CREATE USER telecom_user WITH ENCRYPTED PASSWORD 'telecom_secure_pass_2026';
GRANT ALL PRIVILEGES ON DATABASE telecom_ai TO telecom_user;
```
3. Set in `.env`:
```env
DATABASE_URL=postgresql://telecom_user:telecom_secure_pass_2026@localhost:5432/telecom_ai
```

### Option B: SQLite (Development Fallback)
If `DATABASE_URL` is omitted, TelecomAI automatically initializes an embedded SQLite database at `database/telecom.db` and seeds all mock subscribers, plans, usage records, bills, and towers.

---

## 8. FastAPI Startup

To start the FastAPI backend service in development mode with live reloading:
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

For **production deployment** (without `--reload`):
```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

API documentation is immediately available at `http://127.0.0.1:8000/docs`.

---

## 9. Streamlit Startup

In a separate terminal, launch the Streamlit frontend copilot:
```powershell
.\venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1
```

Access the web interface at `http://127.0.0.1:8501`.

---

## 10. Testing

### Run Phase F Production Hardening Tests
```powershell
.\venv\Scripts\python.exe -m unittest tests/test_phase_f.py
```

### Run Full Regression Test Suite (60+ Automated Tests)
```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

### Verify Python Compilation
```powershell
.\venv\Scripts\python.exe -m py_compile backend/main.py app.py agent.py voice.py confirmation.py
```

---

## 11. Docker Deployment

Deploy the entire stack (PostgreSQL + FastAPI + Streamlit) with a single command:

```bash
docker-compose up --build -d
```

Check service status and health:
```bash
docker-compose ps
docker-compose logs -f backend
```

To stop containers:
```bash
docker-compose down
```

---

## 12. Security Notes

* **JWT Secrets:** Never use default keys in production. Generate a high-entropy secret using `openssl rand -hex 32`.
* **Customer Isolation:** Authenticated users can only read or mutate their own customer account records. Cross-account access attempts return `403 Forbidden`.
* **Password Hashing:** Passwords are encrypted with bcrypt (cost factor 12). Plaintext passwords and hashes are never exposed in API responses or logs.
* **Safe Error Handling:** Internal stack traces and database schemas are scrubbed from all client-facing responses. A unique `X-Request-ID` is attached to every response for correlation in server logs.
* **Secret Scrubbing Filter:** The structured logging pipeline automatically detects and redacts Bearer tokens, passwords, database URIs, and Groq API keys before writing to log streams.
* **Rate Limiting:** Protects `/login`, `/otp`, `/recharge`, `/change-plan`, and `/tickets` against brute-force attacks and abuse.

---

## 13. Known Limitations

* **Audio Barge-in:** In Streamlit, real-time voice barge-in is implemented via UI interrupt controls and state cancellation rather than full-duplex client-side WebRTC acoustic echo cancellation.
* **Offline Neural TTS:** Edge-TTS utilizes Microsoft cloud neural endpoints. When network access is unavailable, the voice engine falls back to local system synthesizers (`pyttsx3`).
