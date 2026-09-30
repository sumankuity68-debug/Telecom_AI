import streamlit as st
import pandas as pd
import uuid
import datetime
import hashlib
from pathlib import Path

# ============================================================
# TELECOM AI IMPORTS
# ============================================================
from agent import ask_telecom_agent
from authy import (
    authenticate,
    find_customer_by_phone,
    normalize_phone,
    send_verification_otp,
    lookup_phone_telecom_details,
    set_carrier_override,
)
from user_context import build_user_context
from memory import (
    initialize_memory,
    save_message,
    get_recent_memory,
)

# ============================================================
# OPTIONAL VOICE IMPORT (PHASE E)
# ============================================================
try:
    from voice import (
        transcribe_audio,
        text_to_speech,
        detect_language,
        SUPPORTED_LANGUAGES,
        voice_controller,
        sanitize_text_for_speech,
    )
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False


# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
CUSTOMERS_FILE = BASE_DIR / "data" / "customers.csv"


# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="TelecomAI • Intelligent Telecom Platform",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# INITIALIZE MEMORY DATABASE
# ============================================================
try:
    initialize_memory()
except Exception as e:
    st.warning(f"Memory system initialization warning: {e}")


# ============================================================
# SESSION STATE
# ============================================================
DEFAULT_STATE = {
    "authenticated": False,
    "customer": None,
    "customer_context": {},
    "auth_page": "login",
    "otp_sent": False,
    "login_phone": "",
    "messages": [],
    "sessions": {},
    "active_session": None,
    "sidebar_rail": False,
    "voice_text": "",
    "processing": False,
    "processed_audio_hash": None,
    "flash_message": None,
    "voice_mode": False,
    "voice_language": "en",
    "voice_status": "idle",
    "last_tts_audio": None,
    "last_tts_text": "",
    "interrupted": False,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SAFE CUSTOMER CONTEXT
# ============================================================
def get_safe_customer_context(customer_id):
    """
    Build customer context safely. Always returns a valid dictionary.
    """
    default_context = {
        "customer": {},
        "current_plan": {},
        "recent_usage": {
            "data_used_gb": 0,
            "call_minutes": 0,
            "sms_count": 0,
        },
        "latest_bill": {},
        "open_tickets": 0,
        "tickets": [],
        "network": {},
        "outages": [],
    }

    try:
        context = build_user_context(customer_id)
        if not context or not isinstance(context, dict):
            return default_context

        for key, value in default_context.items():
            if key not in context or context[key] is None:
                context[key] = value

        return context
    except Exception as e:
        st.warning(f"Could not load customer context: {e}")
        return default_context


# ============================================================
# SESSION / CHAT MANAGEMENT
# ============================================================
def create_chat_session():
    session_id = str(uuid.uuid4())[:8]
    time_str = datetime.datetime.now().strftime("%I:%M %p")
    st.session_state.sessions[session_id] = {
        "title": "New Chat",
        "messages": [],
        "created_at": time_str,
    }
    st.session_state.active_session = session_id
    st.session_state.messages = st.session_state.sessions[session_id]["messages"]
    return session_id


def ensure_chat_session():
    if not st.session_state.sessions:
        create_chat_session()
        return
    if st.session_state.active_session not in st.session_state.sessions:
        create_chat_session()
        return
    st.session_state.messages = st.session_state.sessions[
        st.session_state.active_session
    ]["messages"]


def new_chat():
    create_chat_session()


def load_customer_memory():
    customer = st.session_state.customer
    if not customer:
        return

    customer_id = customer.get("customer_id")
    if not customer_id:
        return

    try:
        previous = get_recent_memory(customer_id, limit=50)
    except Exception as e:
        st.warning(f"Could not load previous conversations: {e}")
        previous = []

    create_chat_session()
    messages = st.session_state.messages

    if not previous:
        return

    for item in previous:
        messages.append({
            "role": item.get("role", "assistant"),
            "content": item.get("content", ""),
            "source": item.get("source", "text"),
            "time": item.get("created_at", ""),
        })


def logout():
    st.session_state.authenticated = False
    st.session_state.customer = None
    st.session_state.customer_context = {}
    st.session_state.otp_sent = False
    st.session_state.login_phone = ""
    st.session_state.messages = []
    st.session_state.sessions = {}
    st.session_state.active_session = None
    st.session_state.voice_text = ""
    st.session_state.processed_audio_hash = None
    st.session_state.flash_message = None
    st.rerun()


# ============================================================
# MESSAGE PROCESSING PIPELINE (TEXT, VOICE & QUICK PROMPTS)
# ============================================================
def process_user_message(user_text, source="text"):
    """
    Unified handler for processing text, voice, and quick questions.
    """
    user_text = user_text.strip()
    if not user_text:
        return

    customer = st.session_state.customer or {}
    customer_id = customer.get("customer_id", "DEMO_USER")
    customer_context = st.session_state.customer_context or {}

    ensure_chat_session()
    messages = st.session_state.messages

    # Update session title if first message
    active_id = st.session_state.active_session
    if active_id in st.session_state.sessions:
        if st.session_state.sessions[active_id]["title"] == "New Chat":
            clean_title = user_text[:28] + ("..." if len(user_text) > 28 else "")
            st.session_state.sessions[active_id]["title"] = clean_title

    # 1. Append user message
    messages.append({
        "role": "user",
        "content": user_text,
        "source": source,
        "time": datetime.datetime.now().strftime("%I:%M %p"),
    })

    # Save to persistent memory
    try:
        save_message(customer_id, "user", user_text, source)
    except Exception:
        pass

    # 2. Get Agent Response with Phase C Intelligence and Phase E Multilingual Voice
    selected_lang = st.session_state.get("voice_language", "en")
    with st.spinner("TelecomAI is analyzing..."):
        try:
            agent_res = ask_telecom_agent(
                user_text,
                customer_context,
                return_metadata=True,
                language=selected_lang,
            )
            if isinstance(agent_res, dict):
                answer = agent_res.get("answer", "")
                intel = agent_res.get("tool_result")
                intent = agent_res.get("intent", "general")
                pending_action = agent_res.get("pending_action")
                lang_meta = agent_res.get("language_metadata", {})
            else:
                answer = str(agent_res)
                intel = None
                intent = "general"
                pending_action = None
                lang_meta = {}
        except Exception as e:
            err_str = str(e).lower()
            if "expired" in err_str or "unauthorized" in err_str or "401" in err_str:
                answer = "Your session has expired. Please log in again."
            elif "connection" in err_str or "unavailable" in err_str or "503" in err_str:
                answer = "The telecom service is temporarily unavailable. Please try again shortly."
            else:
                answer = "Sorry, TelecomAI could not complete that request. Please try again."
            intel = None
            intent = "error"
            pending_action = None
            lang_meta = {}

    # 3. Speech Synthesis (TTS) for Voice Mode or Voice queries
    tts_audio = None
    out_lang = lang_meta.get("output_language", selected_lang) if isinstance(lang_meta, dict) else selected_lang
    if VOICE_AVAILABLE and (source == "voice" or st.session_state.get("voice_mode")):
        try:
            tts_audio = text_to_speech(answer, language=out_lang)
            st.session_state.last_tts_audio = tts_audio
            st.session_state.last_tts_text = answer
            st.session_state.voice_status = "speaking"
        except Exception as e:
            print(f"[TTS AUDIO ERROR] {e}")

    # 4. Append assistant message
    messages.append({
        "role": "assistant",
        "content": answer,
        "source": source,
        "time": datetime.datetime.now().strftime("%I:%M %p"),
        "intel": intel,
        "intent": intent,
        "pending_action": pending_action,
        "audio": tts_audio,
        "language": out_lang,
    })

    # Save to persistent memory
    try:
        save_message(customer_id, "assistant", answer, source)
    except Exception:
        pass

    st.rerun()


# ============================================================
# REGISTER NEW CUSTOMER
# ============================================================
def register_customer(name, phone, email, location, customer_type, operator=None):
    phone = normalize_phone(phone)

    if not name.strip():
        return False, "Please enter your full name."
    if len(phone) != 10:
        return False, "Please enter a valid 10-digit mobile number."
    if not email.strip() or "@" not in email:
        return False, "Please enter a valid email address."
    if not location.strip():
        return False, "Please enter your city/location."

    existing = find_customer_by_phone(phone)
    if existing:
        return False, "An account already exists with this mobile number."

    # Persist operator override if provided (e.g. MNP)
    if operator:
        set_carrier_override(phone, operator, location.strip())

    try:
        customers = pd.read_csv(CUSTOMERS_FILE, dtype=str)
    except FileNotFoundError:
        return False, "Customer database file was not found."

    existing_ids = customers["customer_id"].astype(str).tolist()
    numbers = []
    for cid in existing_ids:
        if cid.startswith("CUST"):
            try:
                numbers.append(int(cid[4:]))
            except ValueError:
                pass

    next_num = max(numbers) + 1 if numbers else 1
    new_customer_id = f"CUST{next_num:03d}"

    # Detect real telecom details
    tel_info = lookup_phone_telecom_details(phone)
    assigned_circle = tel_info.get("circle", location.strip())

    new_customer = {
        "customer_id": new_customer_id,
        "name": name.strip(),
        "phone": phone,
        "email": email.strip(),
        "location": location.strip() or assigned_circle,
        "customer_type": customer_type,
        "account_status": "active",
    }

    customers = pd.concat([customers, pd.DataFrame([new_customer])], ignore_index=True)
    customers.to_csv(CUSTOMERS_FILE, index=False)

    # Automatically provision active plan & exact expiry date
    try:
        from datetime import datetime, timedelta
        sub_file = BASE_DIR / "data" / "subscriptions.csv"
        bills_file = BASE_DIR / "data" / "bills.csv"

        is_5g = "5g" in tel_info.get("technology", "").lower()
        if "airtel" in tel_info.get("operator", "").lower():
            plan_id = "P004"  # 5G Plus (56 days, 168 GB)
            validity = 56
            price = 599.0
        elif is_5g:
            plan_id = "P006"  # Unlimited 5G (90 days, 999 GB)
            validity = 90
            price = 999.0
        else:
            plan_id = "P002"  # Smart 299 (28 days, 56 GB)
            validity = 28
            price = 299.0

        now = datetime.now()
        start_date = now.strftime("%Y-%m-%d")
        expiry_date = (now + timedelta(days=validity)).strftime("%Y-%m-%d")

        # Save subscription
        if sub_file.exists():
            sub_df = pd.read_csv(sub_file, dtype=str)
            sub_id = f"SUB{len(sub_df) + 1:03d}"
            new_sub = {
                "subscription_id": sub_id,
                "customer_id": new_customer_id,
                "plan_id": plan_id,
                "start_date": start_date,
                "expiry_date": expiry_date,
                "status": "active",
            }
            pd.concat([sub_df, pd.DataFrame([new_sub])], ignore_index=True).to_csv(sub_file, index=False)

        # Save initial bill
        if bills_file.exists():
            bill_df = pd.read_csv(bills_file, dtype=str)
            bill_id = f"B{len(bill_df) + 1:03d}"
            taxes = round(price * 0.18, 2)
            total = round(price + taxes, 2)
            new_bill = {
                "bill_id": bill_id,
                "customer_id": new_customer_id,
                "billing_date": start_date,
                "base_plan": str(price),
                "addon_charges": "0",
                "roaming_charges": "0",
                "taxes": str(taxes),
                "total_amount": str(total),
                "status": "paid",
            }
            pd.concat([bill_df, pd.DataFrame([new_bill])], ignore_index=True).to_csv(bills_file, index=False)

        # Sync to SQLite database
        from database import execute_database
        execute_database(
            "INSERT INTO customers (customer_id, name, phone, email, location, customer_type, account_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_customer_id, name.strip(), phone, email.strip(), location.strip() or assigned_circle, customer_type, "active"),
        )
        execute_database(
            "INSERT INTO subscriptions (subscription_id, customer_id, plan_id, start_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, ?)",
            (sub_id, new_customer_id, plan_id, start_date, expiry_date, "active"),
        )
        execute_database(
            "INSERT INTO bills (bill_id, customer_id, billing_date, base_plan, addon_charges, roaming_charges, taxes, total_amount, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (bill_id, new_customer_id, start_date, price, 0.0, 0.0, taxes, total, "paid"),
        )
    except Exception as exc:
        print(f"Provisioning note: {exc}")

    return True, new_customer


# ============================================================
# ULTRA-PREMIUM MODERN CSS
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    /* Global reset & typography */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: #f1f5f9;
        -webkit-font-smoothing: antialiased;
    }

    #MainMenu, footer {
        visibility: hidden !important;
        display: none !important;
    }

    header {
        background: transparent !important;
    }

    /* Main App Background - Elegant Deep Obsidian Gradient with ambient cyan & indigo glow */
    .stApp {
        background-color: #070c18 !important;
        background-image: 
            radial-gradient(at 10% 15%, rgba(6, 182, 212, 0.08) 0px, transparent 50%),
            radial-gradient(at 90% 10%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
            radial-gradient(at 50% 90%, rgba(14, 165, 233, 0.05) 0px, transparent 60%) !important;
        background-attachment: fixed !important;
        color: #f8fafc !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background: rgba(10, 16, 30, 0.95) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        backdrop-filter: blur(24px) !important;
    }

    section[data-testid="stSidebar"] hr {
        border-color: rgba(255, 255, 255, 0.08) !important;
        margin: 14px 0 !important;
    }

    /* Auth Container */
    .auth-card {
        max-width: 520px;
        margin: 4vh auto;
        padding: 40px 36px;
        border-radius: 28px;
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid rgba(56, 189, 248, 0.2);
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.6), 0 0 40px rgba(6, 182, 212, 0.1);
        backdrop-filter: blur(20px);
    }

    .auth-hero-icon {
        width: 72px;
        height: 72px;
        margin: 0 auto 16px auto;
        border-radius: 20px;
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(99, 102, 241, 0.2));
        border: 1px solid rgba(56, 189, 248, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        box-shadow: 0 0 30px rgba(6, 182, 212, 0.3);
    }

    .auth-title {
        text-align: center;
        font-size: 32px;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(135deg, #ffffff 30%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
    }

    .auth-subtitle {
        text-align: center;
        color: #94a3b8;
        font-size: 14px;
        margin-bottom: 24px;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 14px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 10px 18px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        background: rgba(22, 33, 56, 0.8) !important;
        color: #f1f5f9 !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }

    .stButton > button:hover {
        border-color: #38bdf8 !important;
        background: rgba(30, 45, 77, 0.95) !important;
        color: #ffffff !important;
        transform: translateY(-1.5px) !important;
        box-shadow: 0 6px 20px rgba(6, 182, 212, 0.2) !important;
    }

    /* Primary Button */
    .stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #0284c7 0%, #06b6d4 100%) !important;
        border: 1px solid rgba(56, 189, 248, 0.5) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 18px rgba(6, 182, 212, 0.35) !important;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0369a1 0%, #0891b2 100%) !important;
        box-shadow: 0 8px 25px rgba(6, 182, 212, 0.5) !important;
    }

    /* Inputs */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        background-color: rgba(15, 23, 42, 0.9) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 12px !important;
        color: #f8fafc !important;
        font-size: 14px !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25) !important;
    }

    /* Top Stats / Metrics Bar (Fixing the ugly white box completely) */
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 18px !important;
        overflow: hidden !important;
        backdrop-filter: blur(12px) !important;
        margin-bottom: 20px !important;
    }

    div[data-testid="stExpander"] summary {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(19, 29, 51, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 14px !important;
        padding: 14px 18px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2) !important;
    }

    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }

    div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-size: 22px !important;
        font-weight: 700 !important;
    }

    /* Welcome Hero Card */
    .hero-box {
        text-align: center;
        padding: 40px 24px 20px 24px;
        max-width: 820px;
        margin: 0 auto;
    }

    .hero-orb {
        width: 88px;
        height: 88px;
        margin: 0 auto 20px auto;
        border-radius: 28px;
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.25), rgba(99, 102, 241, 0.25));
        border: 1px solid rgba(56, 189, 248, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 46px;
        box-shadow: 0 0 50px rgba(6, 182, 212, 0.35);
        animation: pulseOrb 4s ease-in-out infinite;
    }

    @keyframes pulseOrb {
        0%, 100% { transform: scale(1); box-shadow: 0 0 40px rgba(6, 182, 212, 0.3); }
        50% { transform: scale(1.05); box-shadow: 0 0 60px rgba(99, 102, 241, 0.45); }
    }

    .hero-title {
        font-size: 38px;
        font-weight: 800;
        letter-spacing: -0.8px;
        background: linear-gradient(135deg, #ffffff 20%, #38bdf8 65%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 12px;
    }

    .hero-subtitle {
        color: #94a3b8;
        font-size: 15px;
        line-height: 1.6;
        max-width: 580px;
        margin: 0 auto 32px auto;
    }

    .prompt-grid-title {
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        margin-bottom: 14px;
        text-align: center;
    }

    /* Fixed Bottom Dock (Voice & Text Combined like ChatGPT) */
    div[data-testid="stBottom"] {
        background: rgba(7, 12, 24, 0.88) !important;
        backdrop-filter: blur(20px) !important;
        border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
        padding: 12px 0 18px 0 !important;
    }

    div[data-testid="stBottom"] > div {
        max-width: 860px !important;
        margin: 0 auto !important;
    }

    /* Chat input styling */
    div[data-testid="stChatInput"] {
        background-color: rgba(17, 26, 46, 0.95) !important;
        border: 1px solid rgba(56, 189, 248, 0.25) !important;
        border-radius: 20px !important;
        box-shadow: 0 6px 30px rgba(0, 0, 0, 0.4) !important;
        transition: all 0.2s ease !important;
    }

    div[data-testid="stChatInput"]:focus-within {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.3), 0 8px 32px rgba(0, 0, 0, 0.5) !important;
    }

    div[data-testid="stChatInput"] textarea {
        color: #f8fafc !important;
        font-size: 14px !important;
    }

    /* Popover Voice button inside bottom dock */
    div[data-testid="stPopover"] > button {
        height: 48px !important;
        border-radius: 18px !important;
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(99, 102, 241, 0.15)) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        color: #38bdf8 !important;
        font-weight: 700 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
    }

    div[data-testid="stPopover"] > button:hover {
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.3), rgba(99, 102, 241, 0.3)) !important;
        border-color: #38bdf8 !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.35) !important;
    }

    div[data-testid="stPopoverBody"] {
        background-color: #0d1527 !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        border-radius: 20px !important;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7) !important;
        padding: 16px !important;
    }

    div[data-testid="stAudioInput"] {
        background-color: rgba(19, 29, 51, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 16px !important;
    }

    /* Chat Messages styling */
    div[data-testid="stChatMessage"] {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 18px !important;
        padding: 16px 20px !important;
        margin-bottom: 14px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25) !important;
    }

    /* Badges & Status */
    .badge-online {
        display: inline-flex !important;
        align-items: center !important;
        gap: 5px !important;
        padding: 2px 8px !important;
        border-radius: 12px !important;
        background: rgba(16, 185, 129, 0.16) !important;
        border: 1px solid rgba(16, 185, 129, 0.4) !important;
        color: #34d399 !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
        width: fit-content !important;
        box-sizing: border-box !important;
    }

    .badge-dot {
        width: 7px !important;
        height: 7px !important;
        border-radius: 50% !important;
        background-color: #10b981 !important;
        box-shadow: 0 0 8px #10b981 !important;
        flex-shrink: 0 !important;
        display: inline-block !important;
    }

    /* Sidebar Conversation Row - Pixel Perfect Alignment */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        display: flex !important;
        align-items: center !important;
        margin-bottom: 6px !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"] {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-width: 0 !important;
        padding: 0 !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"] .stButton {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
    }

    /* Common button rules for the row */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] button {
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        margin: 0 !important;
        border-radius: 10px !important;
        box-sizing: border-box !important;
        display: flex !important;
        align-items: center !important;
        line-height: 1 !important;
    }

    /* Left button: Conversation title */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child button {
        padding: 0 10px !important;
        justify-content: flex-start !important;
        text-align: left !important;
        font-size: 13px !important;
        width: 100% !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child button p {
        margin: 0 !important;
        padding: 0 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 38px !important;
    }

    /* Right button: Delete action */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child button {
        padding: 0 !important;
        width: 100% !important;
        justify-content: center !important;
        background: rgba(239, 68, 68, 0.14) !important;
        border: 1px solid rgba(239, 68, 68, 0.35) !important;
        color: #f87171 !important;
        box-shadow: none !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child button:hover {
        background: rgba(239, 68, 68, 0.3) !important;
        border-color: #ef4444 !important;
        color: #ffffff !important;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.4) !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child button span {
        font-size: 18px !important;
        line-height: 1 !important;
        color: #f87171 !important;
        margin: 0 !important;
        padding: 0 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="column"]:last-child button:hover span {
        color: #ffffff !important;
    }

    .source-pill {
        display: inline-block;
        font-size: 10px;
        padding: 2px 7px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.08);
        color: #94a3b8;
        margin-left: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTHENTICATION PAGE (LOGIN & REGISTER WITH INSTANT OTP FLOW)
# ============================================================
if not st.session_state.authenticated:

    # Outer container
    st.markdown(
        """
        <div class="auth-card">
            <div class="auth-hero-icon">📡</div>
            <div class="auth-title">TelecomAI</div>
            <div class="auth-subtitle">Next-Generation Multimodal Telecom Intelligence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    auth_col1, auth_col2, auth_col3 = st.columns([1, 2.5, 1])

    with auth_col2:
        # Flash message banner if available
        if st.session_state.get("flash_message"):
            st.info(f"💡 {st.session_state.flash_message}")

        login_tab, register_tab = st.tabs(["🔐 Sign In", "✨ Create Account"])

        # ====================================================
        # LOGIN TAB
        # ====================================================
        with login_tab:
            st.markdown("#### Access Telecom Co-pilot")
            st.caption("Enter your registered mobile number for instant verification.")

            # STEP 1: MOBILE NUMBER INPUT
            if not st.session_state.otp_sent:
                login_phone = st.text_input(
                    "Mobile Number",
                    value=st.session_state.get("login_phone", ""),
                    placeholder="e.g. 9883633066",
                    key="input_login_phone",
                )
                if login_phone and len(normalize_phone(login_phone)) == 10:
                    tel_prev = lookup_phone_telecom_details(login_phone)
                    st.caption(f"📶 Detected: **{tel_prev['operator']}** • Circle: **{tel_prev['circle']}** ({tel_prev['technology']})")

                send_otp_btn = st.button(
                    "Send Verification OTP 🚀",
                    type="primary",
                    use_container_width=True,
                )

                if send_otp_btn:
                    cleaned_phone = normalize_phone(login_phone)
                    if len(cleaned_phone) != 10:
                        st.error("Please enter a valid 10-digit mobile number.")
                    else:
                        customer = find_customer_by_phone(cleaned_phone)
                        if customer is None:
                            st.error("No account found for this mobile number. Please register first.")
                        elif customer.get("account_status", "").lower() != "active":
                            st.error("This telecom account is currently suspended or inactive.")
                        else:
                            st.session_state.login_phone = cleaned_phone
                            success, otp_msg, is_real = send_verification_otp(cleaned_phone, name=customer.get("name"))
                            st.session_state.is_real_otp = is_real
                            st.session_state.otp_sent = True
                            st.session_state.flash_message = otp_msg
                            # INSTANT TRANSITION TO OTP INPUT
                            st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)
                st.caption("ℹ️ Demo numbers available: `9000000001` (Aarav), `9000000002` (Ananya), `9883633066` (Suman)")

            # STEP 2: OTP VERIFICATION INPUT (RENDERED IMMEDIATELY AFTER SEND OTP)
            else:
                phone_num = st.session_state.login_phone
                masked_phone = f"+91 {phone_num[:2]}••• ••{phone_num[-3:]}"
                is_real = st.session_state.get("is_real_otp", False)

                if is_real:
                    st.markdown(
                        f"""
                        <div style="background: linear-gradient(135deg, rgba(14, 165, 233, 0.15), rgba(99, 102, 241, 0.15)); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 16px; padding: 18px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(14, 165, 233, 0.12);">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 24px;">🚀</span>
                                    <div>
                                        <div style="font-weight: 800; font-size: 15px; color: #f8fafc; letter-spacing: -0.2px;">One-Time Passkey Dispatched</div>
                                        <div style="font-size: 11px; color: #38bdf8; font-weight: 600;">SMS Delivered to Handset</div>
                                    </div>
                                </div>
                                <span style="font-size: 11px; font-weight: 700; color: #34d399; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.35); padding: 3px 10px; border-radius: 20px;">
                                    ● Official SMS
                                </span>
                            </div>
                            <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5; margin-bottom: 10px;">
                                We've sent a 6-digit access code to <b style="color: #38bdf8;">{masked_phone}</b>. Enter it below to unlock your personalized 5G dashboard and intelligent co-pilot.
                            </div>
                            <div style="display: flex; gap: 10px; font-size: 11px; color: #94a3b8; font-weight: 500;">
                                <span>⏱️ 5-Min Expiry</span>
                                <span>•</span>
                                <span>🔒 256-Bit Encrypted</span>
                                <span>•</span>
                                <span>⚡ 5G Telemetry Ready</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"""
                        <div style="background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(234, 88, 12, 0.08)); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 16px; padding: 16px; margin-bottom: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span style="font-size: 20px;">⚡</span>
                                    <span style="font-weight: 800; font-size: 14px; color: #fef3c7;">Developer Sandbox Passkey</span>
                                </div>
                                <span style="font-size: 10px; font-weight: 700; color: #f59e0b; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.3); padding: 2px 8px; border-radius: 12px;">
                                    Preview Mode
                                </span>
                            </div>
                            <div style="font-size: 12px; color: #cbd5e1; line-height: 1.4; margin-bottom: 8px;">
                                Phone <b style="color: #fcd34d;">{masked_phone}</b> is unverified in your Twilio Trial. Use developer passkey <code style="background: rgba(0,0,0,0.4); color: #38bdf8; font-size: 13px; padding: 2px 6px; border-radius: 6px; font-weight: 700;">123456</code> to unlock the app.
                            </div>
                            <div style="font-size: 11px; color: #94a3b8;">
                                💡 To receive real SMS on this number, add it to Twilio Console ➔ Verified Caller IDs.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                login_otp = st.text_input(
                    "Enter 6-Digit Passcode",
                    placeholder="• • • • • •",
                    max_chars=6,
                    type="password",
                    key="input_login_otp",
                )

                c_verify, c_back = st.columns([1.2, 0.8])

                with c_verify:
                    if st.button("Verify & Sign In 🔓", type="primary", use_container_width=True):
                        auth_res = authenticate(st.session_state.login_phone, login_otp)
                        if auth_res["success"]:
                            cust = auth_res["customer"]
                            st.session_state.customer = cust
                            st.session_state.customer_context = get_safe_customer_context(cust["customer_id"])
                            st.session_state.authenticated = True
                            st.session_state.otp_sent = False
                            st.session_state.login_phone = ""
                            st.session_state.flash_message = None
                            st.session_state.sessions = {}
                            st.session_state.active_session = None
                            st.session_state.messages = []
                            load_customer_memory()
                            st.rerun()
                        else:
                            st.error(auth_res["message"])

                with c_back:
                    if st.button("Change Number ↺", use_container_width=True):
                        st.session_state.otp_sent = False
                        st.session_state.login_phone = ""
                        st.session_state.flash_message = None
                        st.rerun()

        # ====================================================
        # REGISTER TAB
        # ====================================================
        with register_tab:
            st.markdown("#### New Customer Registration")
            st.caption("Experience personalized telecom assistance with your own account.")

            reg_name = st.text_input("Full Name", placeholder="e.g. Suman Kuity", key="reg_name")
            reg_phone = st.text_input("Mobile Number (10 digits)", placeholder="e.g. 9883633066", key="reg_phone")
            detected_circle = "West Bengal & Kolkata"
            detected_op = "Bharti Airtel"
            if reg_phone and len(normalize_phone(reg_phone)) == 10:
                tel_reg_prev = lookup_phone_telecom_details(reg_phone)
                detected_circle = tel_reg_prev.get("circle", "West Bengal & Kolkata")
                detected_op = tel_reg_prev.get("operator", "Bharti Airtel")
                st.caption(f"📶 Auto-Detected: **{tel_reg_prev['operator']}** • Circle: **{detected_circle}** ({tel_reg_prev['technology']})")

            col_op1, col_op2 = st.columns(2)
            with col_op1:
                op_list = ["Bharti Airtel", "Reliance Jio", "Vodafone Idea (Vi)", "BSNL Mobile"]
                chosen_idx = 0
                for i, op_item in enumerate(op_list):
                    if op_item.lower() in detected_op.lower() or detected_op.lower() in op_item.lower():
                        chosen_idx = i
                        break
                reg_operator = st.selectbox("Operator / Carrier (MNP Supported)", op_list, index=chosen_idx, key="reg_operator")
            with col_op2:
                reg_location = st.text_input("City / Circle", value=detected_circle, placeholder="e.g. Kolkata", key="reg_location")

            reg_email = st.text_input("Email Address", placeholder="name@example.com", key="reg_email")
            reg_type = st.selectbox("Account Tier", ["individual", "business"], key="reg_type")

            if st.button("Create Account & Send OTP 🚀", type="primary", use_container_width=True):
                success, result = register_customer(reg_name, reg_phone, reg_email, reg_location, reg_type, operator=reg_operator)
                if success:
                    cleaned_reg_phone = normalize_phone(reg_phone)
                    otp_success, otp_msg, is_real = send_verification_otp(cleaned_reg_phone, name=reg_name)
                    st.session_state.login_phone = cleaned_reg_phone
                    st.session_state.is_real_otp = is_real
                    st.session_state.otp_sent = True
                    st.session_state.flash_message = f"Account {result['customer_id']} registered! {otp_msg}"
                    st.rerun()
                else:
                    st.error(result)

    # Stop execution when unauthenticated
    st.stop()


# ============================================================
# AUTHENTICATED WORKSPACE
# ============================================================
customer = st.session_state.customer or {}
customer_context = st.session_state.customer_context or {}

if not customer_context:
    customer_context = get_safe_customer_context(customer.get("customer_id"))
    st.session_state.customer_context = customer_context

ensure_chat_session()

plan = customer_context.get("current_plan", {}) or {}
usage = customer_context.get("recent_usage", {}) or {}
bill = customer_context.get("latest_bill", {}) or {}
cust_tel = lookup_phone_telecom_details(customer.get("phone", ""))


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    # Brand & Status Header
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:14px; padding:2px 0;">
            <div style="font-size:28px;">📡</div>
            <div style="line-height:1.2;">
                <div style="font-size:19px; font-weight:800; color:#f8fafc; letter-spacing:-0.4px;">
                    TelecomAI
                </div>
                <div style="display:flex; align-items:center; gap:6px; margin-top:4px;">
                    <span class="badge-online">
                        <span class="badge-dot"></span> Online
                    </span>
                    <span style="font-size:11px; color:#94a3b8;">• Co-pilot</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Customer Profile Card
    st.markdown(
        f"""
        <div style="padding:14px; border-radius:16px; background:rgba(19, 29, 51, 0.7); border:1px solid rgba(255, 255, 255, 0.08); margin-bottom:14px;">
            <div style="font-size:14px; font-weight:700; color:#f8fafc; margin-bottom:2px;">
                👤 {customer.get("name", "Customer")}
            </div>
            <div style="font-size:12px; color:#38bdf8; font-weight:500;">
                +91 {customer.get("phone", "")}
            </div>
            <div style="font-size:11px; color:#94a3b8; margin-top:4px;">
                📍 {customer.get("location", "India")} • <span style="text-transform:capitalize;">{customer.get("customer_type", "Individual")}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # New Chat Button
    if st.button("➕ New Conversation", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Chat Sessions List
    st.markdown("###### 💬 Conversation History")
    if st.session_state.sessions:
        for sid, sess in reversed(list(st.session_state.sessions.items())):
            stitle = sess.get("title", "New Chat")
            is_active = (sid == st.session_state.active_session)
            btn_label = f"{'🟢 ' if is_active else '💬 '}{stitle[:18]}"

            col_s1, col_s2 = st.columns([0.76, 0.24], gap="small", vertical_alignment="center")
            with col_s1:
                if st.button(btn_label, key=f"session_{sid}", use_container_width=True):
                    st.session_state.active_session = sid
                    st.session_state.messages = sess["messages"]
                    st.rerun()
            with col_s2:
                if st.button("", key=f"del_{sid}", icon=":material/delete:", help="Delete this conversation", use_container_width=True):
                    del st.session_state.sessions[sid]
                    if st.session_state.active_session == sid:
                        create_chat_session()
                    st.rerun()

    st.divider()

    # ========================================================
    # REAL CELL TOWER RADAR (OPENCELLID) WITH PERMISSION
    # ========================================================
    with st.expander("📡 Live Cell Tower Radar (OpenCellID)", expanded=False):
        st.caption("Scan real physical cell towers in your area using the OpenCellID global database.")

        user_loc = customer.get("location", "Kolkata").title()
        cities = ["Kolkata", "Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai", "Pune", "London", "New York"]
        idx = cities.index(user_loc) if user_loc in cities else 0
        selected_city = st.selectbox("Area / City", cities, index=idx, key="radar_city_select")

        allow_scan = st.checkbox("Grant permission to scan area towers", value=False, key="consent_opencellid")

        if allow_scan:
            if st.button("Scan Real Towers 🛰️", use_container_width=True):
                with st.spinner(f"Connecting to OpenCellID for {selected_city}..."):
                    from backend.opencellid_service import get_city_towers
                    t_res = get_city_towers(selected_city)
                    if t_res.get("success"):
                        towers = t_res.get("towers", [])
                        st.success(f"Detected **{len(towers)}** live cell towers near {selected_city}!")

                        jio_cnt = sum(1 for t in towers if "Jio" in t["carrier"])
                        airtel_cnt = sum(1 for t in towers if "Airtel" in t["carrier"])
                        vi_cnt = sum(1 for t in towers if "Vi" in t["carrier"] or "Vodafone" in t["carrier"])

                        m1, m2 = st.columns(2)
                        with m1:
                            st.metric("Jio Towers", jio_cnt)
                        with m2:
                            st.metric("Airtel / Others", airtel_cnt + vi_cnt)

                        st.caption("Live Towers Sample:")
                        for t in towers[:3]:
                            st.markdown(f"""
                            <div style="padding:6px 10px; margin-bottom:6px; border-radius:8px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); font-size:11px;">
                                <b>{t['carrier']}</b> • <span style="color:#38bdf8;">{t['technology']}</span><br>
                                <span style="color:#94a3b8;">Tower ID: {t['cell_id']} | Range: {t['range_meters']}m | Signal: {t['estimated_signal_dbm']} dBm</span>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.error(t_res.get("error", "Failed to retrieve towers."))
        else:
            st.info("Check the permission box above to scan live cell towers.")

    st.divider()

    # My Account Details Glance
    st.markdown("###### 📱 Account Snapshot")
    cust_tel = lookup_phone_telecom_details(customer.get("phone", ""))
    st.markdown(
        f"""
        <div style="font-size:12px; color:#94a3b8; display:flex; flex-direction:column; gap:6px;">
            <div><b style="color:#f1f5f9;">Carrier:</b> {cust_tel.get("operator", "Reliance Jio")}</div>
            <div><b style="color:#f1f5f9;">Circle:</b> {cust_tel.get("circle", customer.get("location", "India"))}</div>
            <div><b style="color:#f1f5f9;">Active Plan:</b> {plan.get("plan_name", "Unlimited 5G")}</div>
            <div><b style="color:#f1f5f9;">Network:</b> {plan.get("technology", cust_tel.get("technology", "5G"))}</div>
            <div><b style="color:#f1f5f9;">Data Allowance:</b> {plan.get("data_gb", 0)} GB</div>
            <div><b style="color:#f1f5f9;">Expires On:</b> <span style="color:#38bdf8; font-weight:600;">{plan.get("expiry_date", "Active")}</span></div>
            <div><b style="color:#f1f5f9;">Recent Usage:</b> {usage.get("data_used_gb", 0)} GB</div>
            <div><b style="color:#f1f5f9;">Latest Bill:</b> ₹{bill.get("total_amount", "0")}</div>
            <div><b style="color:#f1f5f9;">Open Tickets:</b> {customer_context.get("open_tickets", 0)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # Logout Button
    if st.button("🚪 Sign Out", use_container_width=True):
        logout()


# ============================================================
# MAIN TOP HEADER WITH "MY ACCOUNT" IN TOP RIGHT CORNER
# ============================================================
user_name = customer.get("name", "Customer")
first_name = user_name.split()[0] if user_name else "Customer"

top_c1, top_c2 = st.columns([0.62, 0.38], vertical_alignment="center")

with top_c1:
    st.markdown(
        f"""
        <div style="display:flex; flex-direction:column; justify-content:center; padding:4px 0;">
            <div style="font-size:24px; font-weight:800; letter-spacing:-0.5px; background:linear-gradient(135deg, #ffffff 30%, #38bdf8 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                Welcome, {user_name}! 👋
            </div>
            <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
                TelecomAI Hub • Connected to +91 {customer.get("phone", "")} <span style="color:#38bdf8; font-weight:600;">({customer.get("customer_id", "")})</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with top_c2:
    with st.popover(f"👤 My Account • {first_name}", use_container_width=True, help="Click to view your telecom account details"):
        st.markdown(
            f"""
            <div style="padding:4px 0 8px 0;">
                <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                    <div style="font-size:17px; font-weight:800; color:#f8fafc;">
                        👤 {customer.get("name", "Customer")}
                    </div>
                    <span class="badge-online">
                        <span class="badge-dot"></span> Active
                    </span>
                </div>
                <div style="font-size:12px; color:#38bdf8; font-weight:600; margin-bottom:4px;">
                    Customer ID: {customer.get("customer_id", "N/A")} • +91 {customer.get("phone", "")}
                </div>
                <div style="font-size:12px; color:#94a3b8; margin-bottom:2px;">
                    ✉️ {customer.get("email", "N/A")}
                </div>
                <div style="font-size:12px; color:#94a3b8; margin-bottom:10px;">
                    📍 {customer.get("location", "India")} • <span style="text-transform:capitalize;">{customer.get("customer_type", "Individual")}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        st.markdown("###### 📱 Plan & Subscription")
        plan_name = plan.get("plan_name", "No active plan")
        tech = plan.get("technology", cust_tel.get("technology", "5G Plus"))
        allowance = plan.get("data_gb", 0)
        data_used = usage.get("data_used_gb", 0)
        st.write(f"**Carrier:** {cust_tel.get('operator', 'Bharti Airtel')} • {tech}")
        st.write(f"**Circle:** {cust_tel.get('circle', customer.get('location', 'India'))}")
        st.write(f"**Current Plan:** {plan_name}")
        st.write(f"**Expires On:** {plan.get('expiry_date', 'Active')}")
        st.write(f"**Data Allowance:** {allowance} GB")
        st.write(f"**Recent Usage:** {data_used} GB")
        try:
            allow_float = float(allowance)
            used_float = float(data_used)
            if allow_float > 0:
                pct = min(1.0, max(0.0, used_float / allow_float))
                st.progress(pct, text=f"Data Used: {used_float:.1f} GB of {allow_float:.1f} GB ({int(pct*100)}%)")
        except Exception:
            pass
        st.divider()
        st.markdown("###### 💳 Invoicing & Support")
        st.write(f"**Latest Bill:** ₹{bill.get('total_amount', '0')}")
        st.write(f"**Open Support Tickets:** {customer_context.get('open_tickets', 0)}")
        if st.button("🚪 Sign Out", key="popover_account_logout", use_container_width=True):
            logout()

# 4 Key Metrics Bar (Replaces the expander with sleek dark-themed cards)
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Current Plan", plan.get("plan_name", "No active plan"))
with m2:
    st.metric("Technology", plan.get("technology", "Unknown"))
with m3:
    st.metric("Data Allowance", f"{plan.get('data_gb', 0)} GB")
with m4:
    st.metric("Open Tickets", customer_context.get("open_tickets", 0))

st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

# ============================================================
# PHASE E: INTERACTION MODE SELECTOR & VOICE CONVERSATION SUITE
# ============================================================
mode_col1, mode_col2, mode_col3 = st.columns([0.45, 0.35, 0.20])

with mode_col1:
    current_mode_index = 1 if st.session_state.get("voice_mode", False) else 0
    selected_mode = st.radio(
        "Conversation Mode",
        options=["💬 Text Mode", "🎙️ Voice Mode"],
        index=current_mode_index,
        horizontal=True,
        label_visibility="collapsed",
        key="mode_radio_selector",
    )
    is_voice_active = (selected_mode == "🎙️ Voice Mode")
    if is_voice_active != st.session_state.get("voice_mode", False):
        st.session_state.voice_mode = is_voice_active
        if is_voice_active:
            voice_controller.start_voice_mode(language=st.session_state.get("voice_language", "en"))
            st.session_state.voice_status = "listening"
        else:
            voice_controller.stop_voice_mode()
            st.session_state.voice_status = "idle"
        st.rerun()

with mode_col2:
    lang_options = ["en", "hi", "bn"]
    lang_labels = {"en": "🇬🇧 English", "hi": "🇮🇳 हिन्दी (Hindi)", "bn": "🇮🇳 বাংলা (Bengali)"}
    curr_lang = st.session_state.get("voice_language", "en")
    curr_idx = lang_options.index(curr_lang) if curr_lang in lang_options else 0
    chosen_lang = st.selectbox(
        "Voice Language",
        options=lang_options,
        index=curr_idx,
        format_func=lambda x: lang_labels.get(x, x),
        label_visibility="collapsed",
        key="voice_lang_picker",
    )
    if chosen_lang != st.session_state.get("voice_language"):
        st.session_state.voice_language = chosen_lang
        voice_controller.current_language = chosen_lang

with mode_col3:
    if st.session_state.get("voice_mode"):
        if st.button("🛑 Stop Voice", key="stop_voice_top_btn", use_container_width=True, type="secondary"):
            st.session_state.voice_mode = False
            voice_controller.stop_voice_mode()
            st.session_state.voice_status = "idle"
            st.rerun()
    else:
        if st.button("🎤 Start Voice", key="start_voice_top_btn", use_container_width=True, type="primary"):
            st.session_state.voice_mode = True
            voice_controller.start_voice_mode(language=st.session_state.get("voice_language", "en"))
            st.session_state.voice_status = "listening"
            st.rerun()

# DEDICATED CONTINUOUS VOICE MODE CARD
if st.session_state.get("voice_mode"):
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.95));
                    border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 14px; padding: 18px 22px;
                    margin: 12px 0 20px 0; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 24px;">🎙️</span>
                    <div>
                        <span style="font-size: 15px; font-weight: 700; color: #f8fafc; letter-spacing: 0.5px;">CONTINUOUS TELECOM VOICE MODE</span>
                        <div style="font-size: 12px; color: #94a3b8;">Natural speech interface in English, Hindi & Bengali</div>
                    </div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    # Status Pill indicator
    status = st.session_state.get("voice_status", "listening")
    if status == "listening":
        pill_html = '<span style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 12px;">🟢 Listening for speech...</span>'
    elif status == "processing":
        pill_html = '<span style="background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.4); padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 12px;">🟡 Processing speech with TelecomAI...</span>'
    elif status == "speaking":
        pill_html = '<span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 12px;">🔵 🔊 Speaking response...</span>'
    elif status == "interrupted":
        pill_html = '<span style="background: rgba(249, 115, 22, 0.2); color: #fb923c; border: 1px solid rgba(249, 115, 22, 0.4); padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 12px;">🟠 Audio Interrupted (Barge-in Active)</span>'
    else:
        pill_html = '<span style="background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.4); padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 12px;">⚪ Voice Ready</span>'

    st.markdown(f"<div style='margin-bottom: 14px;'>Current Status: {pill_html}</div>", unsafe_allow_html=True)

    # Audio input for voice mode
    vc_in, vc_ctrl = st.columns([0.7, 0.3])
    with vc_in:
        v_audio = st.audio_input("Speak to TelecomAI", key="continuous_voice_input")
        if v_audio is not None:
            v_bytes = v_audio.getvalue()
            v_hash = hashlib.md5(v_bytes).hexdigest()
            if v_hash != st.session_state.get("processed_voice_mode_hash"):
                st.session_state.processed_voice_mode_hash = v_hash
                st.session_state.voice_status = "processing"
                voice_controller.set_state("processing")
                if VOICE_AVAILABLE:
                    transcript = transcribe_audio(v_bytes, language=st.session_state.get("voice_language", "en"))
                    if transcript and not transcript.startswith("Voice transcription failed"):
                        process_user_message(transcript, source="voice")
                    else:
                        st.error(f"Voice transcription error: {transcript}")
                        st.session_state.voice_status = "listening"
                else:
                    st.warning("Voice transcription module is unavailable.")
                    st.session_state.voice_status = "listening"

    with vc_ctrl:
        if st.button("⏹️ Interrupt Audio", key="interrupt_voice_btn", use_container_width=True, help="Stop currently playing audio"):
            voice_controller.interrupt()
            st.session_state.voice_interrupted = True
            st.session_state.last_tts_audio = None
            st.session_state.voice_status = "interrupted"
            st.rerun()

        if st.button("🛑 Exit Voice", key="stop_continuous_voice_btn", use_container_width=True, help="Exit voice mode and return to text mode"):
            st.session_state.voice_mode = False
            voice_controller.stop_voice_mode()
            st.session_state.voice_status = "idle"
            st.rerun()

    if st.session_state.get("last_tts_audio") and not st.session_state.get("voice_interrupted"):
        st.markdown("<div style='margin-top: 10px; font-size: 13px; color: #38bdf8; font-weight: 600;'>🔊 TelecomAI Response Audio:</div>", unsafe_allow_html=True)
        st.audio(st.session_state.last_tts_audio, format="audio/mp3", autoplay=True)

    with st.expander("ℹ️ Technical Architecture & Interruption Notice", expanded=False):
        st.markdown(
            """
            - **Turn-based vs Acoustic Barge-in:** In Streamlit's client-server architecture over WebSockets, true simultaneous zero-latency acoustic barge-in while audio is playing requires client-side WebRTC or AudioWorklets in the browser.
            - **Implemented Interruption:** TelecomAI implements barge-in priority handling via the **Interrupt** control and state cancellation (`voice_controller.interrupt()`), which terminates current playback state and gives immediate priority to new user microphone input.
            """
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# CHAT AREA / WELCOME HERO
# ============================================================
messages = st.session_state.messages

if not messages:
    # Clean hero section with personalized greeting
    st.markdown(
        f"""
        <div class="hero-box">
            <div class="hero-orb">📡</div>
            <div class="hero-title">Welcome, {user_name}! 👋</div>
            <div class="hero-subtitle">
                I'm your personal TelecomAI co-pilot. Ask me about your <b>{plan.get('plan_name', 'telecom')}</b> plan,
                live data balance, latest bill breakdown, network health in {customer.get('location', 'your area')}, or diagnose connectivity issues.
                Type your question or speak via voice below!
            </div>
            <div class="prompt-grid-title">Suggested Inquiries</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 4 Quick Suggestion Cards
    pq1, pq2 = st.columns(2)
    with pq1:
        if st.button("📱 What is my current plan?", use_container_width=True):
            process_user_message("What is my current plan?", source="text")
    with pq2:
        if st.button("📊 How much data have I used?", use_container_width=True):
            process_user_message("How much data have I used recently?", source="text")

    pq3, pq4 = st.columns(2)
    with pq3:
        if st.button("💳 Explain my latest bill", use_container_width=True):
            process_user_message("Explain my latest bill in detail.", source="text")
    with pq4:
        if st.button("📶 Check my network status", use_container_width=True):
            process_user_message("Check my network status and tower health.", source="text")

else:
    # Render chat conversation stream
    for i, msg in enumerate(messages):
        role = msg.get("role", "assistant")
        avatar = "👤" if role == "user" else "📡"
        source = msg.get("source", "text")
        source_label = "🎙️ voice" if source == "voice" else "⌨️ text"
        time_stamp = msg.get("time", "")

        with st.chat_message(role, avatar=avatar):
            # Render Phase C Agent Intelligence Visual Cards if present
            intel = msg.get("intel")
            intent = msg.get("intent", "")

            if role == "assistant" and isinstance(intel, dict):
                # 1. NETWORK INTELLIGENCE VISUAL CARD
                diag = intel.get("diagnostics") or (intel if "health_score" in intel else None)
                if diag:
                    score = diag.get("health_score", 0)
                    down = diag.get("download_mbps", 0.0)
                    lat = diag.get("latency_ms", 0.0)
                    loss = diag.get("packet_loss_percent", 0.0)
                    sig = diag.get("signal_strength_dbm", -100.0)
                    tower = f"{diag.get('tower_id', 'T001')} — {diag.get('tower_status', 'healthy').capitalize()}"

                    anom_data = intel.get("anomaly_analysis", {})
                    is_anom = anom_data.get("is_anomaly", False) if isinstance(anom_data, dict) else False
                    anom_label = "Detected" if is_anom else "Normal"

                    outage_data = intel.get("outage_correlation", {})
                    out_active = outage_data.get("outage_detected", False) if isinstance(outage_data, dict) else (len(diag.get("active_outages", [])) > 0)
                    outage_label = "Active" if out_active else "None"

                    st.markdown(
                        f"""
                        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 14px; padding: 14px 18px; margin-bottom: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.3);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 6px;">
                                <span style="font-size: 13px; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.8px;">📡 Network Health Intelligence</span>
                                <span style="font-size: 16px; font-weight: 800; color: {'#34d399' if score >= 70 else ('#fbbf24' if score >= 40 else '#f87171')};">
                                    NETWORK HEALTH: {score} / 100
                                </span>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 12px;">
                                <div><span style="color:#94a3b8;">Download:</span><br><b style="color:#f8fafc; font-size:14px;">{down} Mbps</b></div>
                                <div><span style="color:#94a3b8;">Latency:</span><br><b style="color:#f8fafc; font-size:14px;">{lat} ms</b></div>
                                <div><span style="color:#94a3b8;">Packet Loss:</span><br><b style="color:#f8fafc; font-size:14px;">{loss}%</b></div>
                                <div><span style="color:#94a3b8;">Signal:</span><br><b style="color:#f8fafc; font-size:14px;">{sig} dBm</b></div>
                                <div><span style="color:#94a3b8;">Tower:</span><br><b style="color:#38bdf8; font-size:13px;">{tower}</b></div>
                                <div><span style="color:#94a3b8;">Outage:</span><br><b style="color:{'#f87171' if out_active else '#34d399'}; font-size:13px;">{outage_label}</b></div>
                                <div><span style="color:#94a3b8;">Anomaly:</span><br><b style="color:{'#fbbf24' if is_anom else '#34d399'}; font-size:13px;">{anom_label}</b></div>
                                <div><span style="color:#94a3b8;">Quality Tier:</span><br><b style="color:#a78bfa; font-size:13px;">{diag.get('quality', 'Good')}</b></div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # 2. PLAN RECOMMENDATION VISUAL CARD
                elif "recommendations" in intel:
                    curr = intel.get("current_plan", {})
                    recs = intel.get("recommendations", [])
                    st.markdown(
                        f"""
                        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(167, 139, 250, 0.35); border-radius: 14px; padding: 14px 18px; margin-bottom: 12px;">
                            <div style="font-size: 13px; font-weight: 800; color: #a78bfa; text-transform: uppercase; margin-bottom: 8px;">
                                📱 Plan Recommendation Engine
                            </div>
                            <div style="font-size: 12px; margin-bottom: 8px;">
                                <span style="color: #94a3b8;">CURRENT PLAN:</span> <b style="color: #f8fafc;">{curr.get('plan_name')} (₹{curr.get('price')}/mo • {curr.get('data_gb')} GB)</b>
                            </div>
                            <div style="font-size: 12px; color: #38bdf8; font-weight: 700; margin-bottom: 6px;">RECOMMENDED PLANS:</div>
                        """,
                        unsafe_allow_html=True,
                    )
                    for r in recs[:2]:
                        st.markdown(
                            f"""
                            <div style="background: rgba(30, 41, 59, 0.6); border-radius: 8px; padding: 8px 12px; margin-bottom: 6px; font-size: 12px;">
                                <div style="display:flex; justify-content:space-between; font-weight:700; color:#38bdf8;">
                                    <span>🌟 {r.get('plan_name')} — ₹{r.get('price')} ({r.get('validity_days')} days)</span>
                                    <span>Quota: {r.get('data_gb')} GB</span>
                                </div>
                                <div style="color: #cbd5e1; font-size: 11px; margin-top: 3px;"><b style="color:#94a3b8;">WHY RECOMMENDED:</b> {r.get('reason')}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    st.markdown("</div>", unsafe_allow_html=True)

                # 3. BILL ANALYSIS VISUAL CARD
                elif "breakdown_percentages" in intel or "base_plan" in intel:
                    b_tot = intel.get("total_amount", 0.0)
                    b_base = intel.get("base_plan", 0.0)
                    b_add = intel.get("addon_charges", 0.0)
                    b_roam = intel.get("roaming_charges", 0.0)
                    b_tax = intel.get("taxes", 0.0)
                    b_analysis = intel.get("analysis", [])

                    st.markdown(
                        f"""
                        <div style="background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 14px; padding: 14px 18px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">
                                <span style="font-size: 13px; font-weight: 800; color: #34d399; text-transform: uppercase;">💳 Deterministic Bill Analysis</span>
                                <span style="font-size: 15px; font-weight: 800; color: #f8fafc;">CURRENT BILL: ₹{b_tot:.2f}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 11px; margin-bottom: 8px;">
                                <div><span style="color:#94a3b8;">BASE PLAN:</span><br><b style="color:#f8fafc;">₹{b_base:.2f}</b></div>
                                <div><span style="color:#94a3b8;">ADD-ONS:</span><br><b style="color:#f8fafc;">₹{b_add:.2f}</b></div>
                                <div><span style="color:#94a3b8;">ROAMING:</span><br><b style="color:#f8fafc;">₹{b_roam:.2f}</b></div>
                                <div><span style="color:#94a3b8;">TAXES:</span><br><b style="color:#f8fafc;">₹{b_tax:.2f}</b></div>
                            </div>
                            <div style="font-size: 11px; color: #cbd5e1;">
                                <b style="color: #38bdf8;">ANALYSIS:</b>
                                <ul style="margin: 4px 0 0 16px; padding: 0;">
                                    {''.join([f'<li>{pt}</li>' for pt in b_analysis[:3]])}
                                </ul>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            # Natural language response body
            st.markdown(msg.get("content", ""))

            # Phase D: Action Confirmation Card
            pending_act = msg.get("pending_action")
            from confirmation import get_pending_action
            active_pending = get_pending_action(customer.get("customer_id", "CUST001"))
            if role == "assistant" and pending_act and active_pending and active_pending.get("status") == "pending":
                act_type = pending_act.get("action_type")
                prev_details = pending_act.get("preview", {}).get("details", {})
                params = pending_act.get("parameters", {})

                st.markdown(
                    """
                    <div style="background: rgba(15, 23, 42, 0.95); border: 2px solid #38bdf8; border-radius: 12px; padding: 14px 18px; margin: 12px 0 8px 0; box-shadow: 0 4px 20px rgba(56, 189, 248, 0.2);">
                        <div style="font-size: 13px; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px;">
                            ⚡ ACTION CONFIRMATION REQUIRED
                        </div>
                    """,
                    unsafe_allow_html=True,
                )
                if act_type == "change_plan":
                    st.markdown(
                        f"""
                        <div style="font-size: 12px; color: #f8fafc; line-height: 1.6; margin-bottom: 10px;">
                            <b>Action:</b> Change Plan<br>
                            <b>Current:</b> {prev_details.get('current_plan', 'Current')}<br>
                            <b>New:</b> <span style="color:#38bdf8; font-weight:700;">{prev_details.get('new_plan', 'New')}</span><br>
                            <b>Price:</b> ₹{prev_details.get('price', 0)}<br>
                            <b>Data:</b> {prev_details.get('data_gb', 0)} GB<br>
                            <b>Estimated Difference:</b> {prev_details.get('price_difference', '')}
                        </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                elif act_type == "recharge":
                    st.markdown(
                        f"""
                        <div style="font-size: 12px; color: #f8fafc; line-height: 1.6; margin-bottom: 10px;">
                            <b>Action:</b> Recharge Account (MOCK/DEMO)<br>
                            <b>Customer:</b> {customer.get('customer_id', 'CUST001')}<br>
                            <b>Amount:</b> <span style="color:#34d399; font-weight:700;">₹{params.get('amount', 0):.2f}</span><br>
                            <b>Notice:</b> Mock transaction only. No real money will be charged.
                        </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                elif act_type == "create_ticket":
                    st.markdown(
                        f"""
                        <div style="font-size: 12px; color: #f8fafc; line-height: 1.6; margin-bottom: 10px;">
                            <b>Action:</b> Create Support Ticket<br>
                            <b>Category:</b> {prev_details.get('category', 'Network').capitalize()}<br>
                            <b>Priority:</b> <span style="color:#f87171; font-weight:700;">{prev_details.get('priority', 'High').capitalize()}</span><br>
                            <b>Description:</b> {prev_details.get('description', '')}
                        </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                btn_c1, btn_c2, _ = st.columns([0.25, 0.25, 0.5])
                with btn_c1:
                    if st.button("✅ Confirm", key=f"confirm_btn_{i}", use_container_width=True):
                        process_user_message("Confirm", source="text")
                with btn_c2:
                    if st.button("❌ Cancel", key=f"cancel_btn_{i}", use_container_width=True):
                        process_user_message("Cancel", source="text")

            if role == "assistant" and msg.get("audio"):
                st.audio(msg["audio"], format="audio/mp3")

            st.markdown(
                f"<div style='font-size:11px; color:#64748b; margin-top:4px;'>{time_stamp} <span class='source-pill'>{source_label}</span></div>",
                unsafe_allow_html=True,
            )


# ============================================================
# CHATGPT-STYLE UNIFIED PROMPT DOCK (VOICE + TEXT IN SAME PLACE)
# ============================================================
with st.bottom:
    dock_c1, dock_c2 = st.columns([0.16, 0.84], gap="small", vertical_alignment="bottom")

    # VOICE ASSISTANT INLINE TRIGGER (LIKE CHATGPT'S MIC BUTTON)
    with dock_c1:
        with st.popover("🎙️ Voice", use_container_width=True, help="Click to record question via Voice"):
            st.markdown("##### 🎙️ Voice Assistant")
            st.caption("Click the microphone below to speak:")

            dock_audio = st.audio_input("Record audio", key="chatgpt_dock_audio")
            if dock_audio is not None:
                audio_bytes = dock_audio.getvalue()
                audio_hash = hashlib.md5(audio_bytes).hexdigest()

                if audio_hash != st.session_state.get("processed_audio_hash"):
                    st.session_state.processed_audio_hash = audio_hash

                    if VOICE_AVAILABLE:
                        with st.spinner("🎙️ Transcribing voice..."):
                            transcript = transcribe_audio(audio_bytes)

                        if transcript and not transcript.startswith("Voice transcription failed"):
                            st.success(f"Transcribed: {transcript}")
                            process_user_message(transcript, source="voice")
                        else:
                            st.error(f"Voice error: {transcript}")
                    else:
                        st.warning("Voice transcription module is unavailable.")

    # TEXT CHAT INPUT (LIKE CHATGPT'S PROMPT BOX)
    with dock_c2:
        chat_query = st.chat_input("Ask TelecomAI about your plan, bill, network or service...")
        if chat_query and chat_query.strip():
            process_user_message(chat_query.strip(), source="text")