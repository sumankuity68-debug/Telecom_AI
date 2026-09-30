"""
TelecomAI Domain Guardrails

Purpose:
    Prevent the LLM from answering questions outside the telecom domain.

Examples:

    "What is my current plan?"
        -> ALLOWED

    "Why is my 5G slow?"
        -> ALLOWED

    "What is packet loss?"
        -> ALLOWED

    "2 + 2"
        -> BLOCKED

    "Write me a Python program"
        -> BLOCKED

    "Who is the president?"
        -> BLOCKED
"""

import re


# ============================================================
# TELECOM DOMAIN KEYWORDS
# ============================================================

TELECOM_KEYWORDS = {

    # General telecom
    "telecom",
    "telecommunication",
    "mobile network",
    "mobile service",
    "network",
    "operator",
    "carrier",
    "subscriber",

    # Plans
    "plan",
    "plans",
    "subscription",
    "recharge",
    "prepaid",
    "postpaid",
    "validity",
    "data allowance",
    "addon",
    "add-on",

    # Mobile data
    "data",
    "internet",
    "mobile data",
    "data usage",
    "data balance",
    "hotspot",

    # Network technologies
    "2g",
    "3g",
    "4g",
    "5g",
    "lte",
    "nr",
    "volte",
    "wi-fi calling",
    "wifi calling",
    "wifi",
    "wi-fi",

    # SIM
    "sim",
    "esim",
    "sim card",
    "no sim",
    "sim not working",

    # Network performance
    "speed",
    "download speed",
    "upload speed",
    "latency",
    "ping",
    "packet loss",
    "jitter",
    "bandwidth",
    "throughput",
    "signal",
    "signal strength",
    "dbm",
    "coverage",
    "congestion",
    "backhaul",
    "tower",
    "cell tower",
    "network outage",
    "outage",
    "network health",
    "network health score",
    "network anomaly",
    "anomaly",

    # Calls / messaging
    "call",
    "calls",
    "calling",
    "call drop",
    "call drops",
    "dropped call",
    "voice call",
    "sms",
    "text message",
    "text messages",
    "message",

    # Roaming
    "roaming",
    "international roaming",

    # Billing
    "bill",
    "billing",
    "billing date",
    "bill amount",
    "bill charge",
    "charges",
    "tax",
    "taxes",
    "roaming charge",
    "addon charge",
    "payment",
    "pending bill",
    "overdue bill",

    # Customer account
    "account",
    "customer",
    "customer id",
    "account status",
    "suspended",
    "suspension",

    # Support
    "support",
    "support ticket",
    "ticket",
    "complaint",
    "issue",
    "problem",
    "troubleshooting",

    # Telecom configuration
    "apn",
    "network settings",
    "mobile settings",
    "airplane mode",

    # Portability
    "number portability",
    "port number",
    "mobile number",

    # Telecom hardware
    "router",
    "modem",
    "fiber",
    "broadband",

    # Telecom diagnostics
    "speedtest",
    "speed test",
    "network diagnostic",
    "network diagnostics",

    # Telecom image/voice use
    "screenshot",
    "network screenshot",
    "bill screenshot",
}


# ============================================================
# COMMON TELECOM QUESTION PATTERNS
# ============================================================

TELECOM_PATTERNS = [

    r"\bmy\s+(plan|bill|account|data|internet|network|sim|phone)\b",

    r"\bwhat\s+is\s+my\s+(plan|bill|account|data|usage)\b",

    r"\bhow\s+much\s+(data|internet)\b",

    r"\bhow\s+can\s+i\s+(check|change|upgrade|downgrade|recharge)\b",

    r"\bwhy\s+is\s+my\s+(internet|network|5g|4g|data|signal|connection)\b",

    r"\bwhy\s+(are|is)\s+my\s+(calls?|messages?|sms|internet)\b",

    r"\bcan\s+i\s+(upgrade|downgrade|recharge|change)\b",

    r"\bis\s+there\s+(an\s+)?outage\b",

    r"\bnetwork\s+(status|problem|issue|health)\b",

    r"\bcheck\s+(my\s+)?(plan|usage|bill|account|network|ticket)\b",

    r"\bcurrent\s+(plan|subscription|usage|bill)\b",

    r"\b5g\s+(speed|problem|issue|coverage|signal)\b",

    r"\b4g\s+(speed|problem|issue|coverage|signal)\b",

    r"\bsim\s+(card|problem|issue|not\s+working)\b",

    r"\bdata\s+(usage|balance|allowance)\b",

    r"\bnetwork\s+(outage|congestion|latency|speed|signal)\b",
]


# ============================================================
# SAFE TELECOM GREETINGS
# ============================================================

GREETING_PATTERNS = [
    r"^\s*hi\s*$",
    r"^\s*hello\s*$",
    r"^\s*hey\s*$",
    r"^\s*hi telecomai\s*$",
    r"^\s*hello telecomai\s*$",
    r"^\s*hey telecomai\s*$",
    r"^\s*good morning\s*$",
    r"^\s*good afternoon\s*$",
    r"^\s*good evening\s*$",
]


# ============================================================
# BLOCKED NON-TELECOM PATTERNS
# ============================================================

OBVIOUS_NON_TELECOM_PATTERNS = [

    # Mathematics
    r"^\s*\d+\s*[\+\-\*/]\s*\d+\s*$",
    r"^\s*what\s+is\s+\d+\s*[\+\-\*/]\s*\d+",
    r"\bsolve\s+(this\s+)?equation\b",
    r"\bcalculate\s+the\s+integral\b",
    r"\bderivative\s+of\b",

    # Programming
    r"\bwrite\s+(a\s+)?python\s+program\b",
    r"\bwrite\s+(a\s+)?c\+\+\s+program\b",
    r"\bwrite\s+(a\s+)?java\s+program\b",
    r"\bdebug\s+(my\s+)?code\b",
    r"\bwrite\s+code\b",
    r"\bprogramming\s+question\b",

    # General knowledge
    r"\bwho\s+is\s+the\s+president\b",
    r"\bwho\s+is\s+the\s+prime\s+minister\b",
    r"\bcapital\s+of\b",
    r"\bhistory\s+of\b",

    # Entertainment
    r"\bmovie\s+recommendation\b",
    r"\bbest\s+movie\b",
    r"\bbest\s+song\b",
    r"\bfootball\s+score\b",
    r"\bcricket\s+score\b",

    # Education
    r"\bsolve\s+my\s+homework\b",
    r"\bexam\s+question\b",
    r"\bsolve\s+this\s+math\b",

    # Creative writing
    r"\bwrite\s+a\s+poem\b",
    r"\bwrite\s+a\s+story\b",
    r"\bwrite\s+a\s+song\b",

    # Cooking
    r"\brecipe\s+for\b",
    r"\bhow\s+to\s+cook\b",
]


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize user input before guardrail analysis.
    """

    if not text:
        return ""

    text = text.lower().strip()

    # Replace multiple spaces
    text = re.sub(r"\s+", " ", text)

    return text


# ============================================================
# TELECOM KEYWORD CHECK
# ============================================================

def contains_telecom_keyword(text: str) -> bool:
    """
    Returns True when a known telecom term appears.
    """

    text = normalize_text(text)

    for keyword in TELECOM_KEYWORDS:

        # Exact phrase matching
        if keyword in text:
            return True

    return False


# ============================================================
# TELECOM PATTERN CHECK
# ============================================================

def matches_telecom_pattern(text: str) -> bool:
    """
    Detect common telecom question structures.
    """

    text = normalize_text(text)

    for pattern in TELECOM_PATTERNS:

        if re.search(pattern, text, flags=re.IGNORECASE):
            return True

    return False


# ============================================================
# GREETING CHECK
# ============================================================

def is_greeting(text: str) -> bool:
    """
    Allow simple greetings.
    """

    text = normalize_text(text)

    for pattern in GREETING_PATTERNS:

        if re.match(pattern, text, flags=re.IGNORECASE):
            return True

    return False


# ============================================================
# OBVIOUS NON-TELECOM CHECK
# ============================================================

def is_obviously_non_telecom(text: str) -> bool:
    """
    Detect obvious questions that should never reach the LLM.
    """

    text = normalize_text(text)

    for pattern in OBVIOUS_NON_TELECOM_PATTERNS:

        if re.search(pattern, text, flags=re.IGNORECASE):
            return True

    return False


# ============================================================
# MAIN GUARDRAIL
# ============================================================

def telecom_guardrail(user_input: str) -> dict:
    """
    Main domain guardrail.

    Returns:

    {
        "allowed": True/False,
        "reason": "...",
        "message": "..."
    }
    """

    text = normalize_text(user_input)

    # Empty input
    if not text:

        return {
            "allowed": False,
            "reason": "empty_input",
            "message": "Please enter a telecom-related question."
        }

    # Explicitly block obvious non-telecom questions
    if is_obviously_non_telecom(text):

        return {
            "allowed": False,
            "reason": "non_telecom",
            "message": (
                "Sorry, I can only help with telecom-related topics "
                "such as mobile plans, billing, data usage, calls, "
                "SIM/eSIM, 4G/5G, network problems, outages, "
                "roaming and telecom support."
            )
        }

    # Allow greetings
    if is_greeting(text):

        return {
            "allowed": True,
            "reason": "greeting",
            "message": ""
        }

    # Telecom keyword
    if contains_telecom_keyword(text):

        return {
            "allowed": True,
            "reason": "telecom_keyword",
            "message": ""
        }

    # Telecom question pattern
    if matches_telecom_pattern(text):

        return {
            "allowed": True,
            "reason": "telecom_pattern",
            "message": ""
        }

    # Everything else is blocked
    return {
        "allowed": False,
        "reason": "outside_telecom_domain",
        "message": (
            "Sorry, I can only help with telecom-related questions. "
            "Please ask me about mobile plans, billing, data usage, "
            "calls, SIM/eSIM, 4G/5G, network problems, outages, "
            "roaming or telecom support."
        )
    }


# ============================================================
# SIMPLE BOOLEAN HELPER
# ============================================================

def is_telecom_question(user_input: str) -> bool:
    """
    Simple helper for use inside agent.py.
    """

    result = telecom_guardrail(user_input)

    return result["allowed"]


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_questions = [

        "What is my current plan?",
        "Why is my 5G slow?",
        "What is packet loss?",
        "How much data did I use?",
        "Why is my bill high?",
        "Is there an outage in Kolkata?",
        "What is VoLTE?",
        "What does -90 dBm mean?",
        "2+2",
        "Write a Python program",
        "Who is the president?",
        "Tell me a joke",
        "What is the capital of India?",
        "Hello",
    ]

    print("\n" + "=" * 70)
    print("TELECOMAI GUARDRAIL TEST")
    print("=" * 70)

    for question in test_questions:

        result = telecom_guardrail(question)

        status = "ALLOWED" if result["allowed"] else "BLOCKED"

        print(f"\nQuestion : {question}")
        print(f"Status   : {status}")
        print(f"Reason   : {result['reason']}")

        if result["message"]:
            print(f"Message  : {result['message']}")

    print("\n" + "=" * 70)