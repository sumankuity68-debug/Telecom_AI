"""
TelecomAI — Phase D Confirmation System
Handles state-changing action previews, pending action lifecycle, explicit confirmation/cancellation,
and security enforcement ensuring customers can only confirm their own pending actions.
"""

import re
import datetime
from typing import Optional, Dict, Any

from backend.audit import record_audit_log


# In-memory store for pending confirmations: {customer_id: PendingActionDict}
_PENDING_ACTIONS: Dict[str, Dict[str, Any]] = {}

DEFAULT_TTL_SECONDS = 300  # 5 minutes


# ============================================================
# INTENT DETECTION (CONFIRM / CANCEL)
# ============================================================

VALID_CONFIRM_PHRASES = [
    "yes",
    "confirm",
    "confirm it",
    "proceed",
    "do it",
    "yes please",
    "yes, create it",
    "yes, change it",
    "yes, proceed",
    "yes do it",
    "confirm action",
    "confirm recharge",
    "confirm plan change",
    "confirm ticket",
    "sure, proceed",
    "go ahead",
    # Hindi phrases
    "हाँ",
    "हाँ पुष्टि करें",
    "पुष्टि करें",
    "आगे बढ़ें",
    "हाँ, करो",
    "हाँ, कर दीजिए",
    "haan",
    "ha",
    # Bengali phrases
    "হ্যাঁ",
    "নিশ্চিত করুন",
    "নিশ্চিত",
    "এগিয়ে যান",
    "হ্যাঁ, করুন",
    "হ্যাঁ, তৈরি করুন",
    "hyan",
]

VALID_CANCEL_PHRASES = [
    "no",
    "cancel",
    "don't do it",
    "dont do it",
    "stop",
    "abort",
    "no, cancel",
    "do not do it",
    "cancel it",
    "nevermind",
    "never mind",
    "dismiss",
    # Hindi phrases
    "नहीं",
    "ना",
    "रद्द करें",
    "रद्द",
    "मत करो",
    "nahi",
    "band karo",
    # Bengali phrases
    "না",
    "বাতিল করুন",
    "বাতিল",
    "করবেন না",
    "থামুন",
    "batil",
]

# Ordinary words that must NEVER trigger confirmation
EXCLUDED_CONFIRM_PHRASES = [
    "okay",
    "ok",
    "fine",
    "thanks",
    "thank you",
    "cool",
    "got it",
    "understood",
    "alright",
]


def _clean_phrase(text: str) -> str:
    """
    Remove punctuation without corrupting Indic combining marks, matras, or script characters.
    """
    if not text:
        return ""
    cleaned = re.sub(r"[\.,!?;:\'\"()\[\]\-_/\\]", " ", text)
    return " ".join(cleaned.strip().lower().split())


CLEAN_CONFIRM_PHRASES = [_clean_phrase(p) for p in VALID_CONFIRM_PHRASES]
CLEAN_CANCEL_PHRASES = [_clean_phrase(p) for p in VALID_CANCEL_PHRASES]


def is_confirmation_phrase(text: str) -> bool:
    """
    Check if user input represents explicit confirmation.
    Strictly excludes neutral/pleasantry phrases ("okay", "fine", "thanks").
    """
    if not text:
        return False
    cleaned = _clean_phrase(text)
    if not cleaned:
        return False

    # Direct match on excluded phrases
    if cleaned in EXCLUDED_CONFIRM_PHRASES:
        return False

    # Check for exact or leading confirmation words
    words = cleaned.split()
    if not words:
        return False

    if cleaned in CLEAN_CONFIRM_PHRASES:
        return True

    # Check start or token match
    for phrase in CLEAN_CONFIRM_PHRASES:
        if cleaned == phrase or cleaned.startswith(phrase + " "):
            return True

    # Standalone keyword matches in English, Hindi, and Bengali
    standalone_confirm = ["yes", "confirm", "proceed", "haan", "ha", "hyan", "हाँ", "হ্যাঁ"]
    if any(w in words for w in standalone_confirm):
        return True

    return False


def is_cancellation_phrase(text: str) -> bool:
    """
    Check if user input represents explicit cancellation.
    """
    if not text:
        return False
    cleaned = _clean_phrase(text)
    if not cleaned:
        return False

    words = cleaned.split()
    if not words:
        return False

    if cleaned in CLEAN_CANCEL_PHRASES:
        return True

    for phrase in CLEAN_CANCEL_PHRASES:
        if cleaned == phrase or cleaned.startswith(phrase + " "):
            return True

    standalone_cancel = ["cancel", "stop", "abort", "batil", "नहीं", "না"]
    if any(w in words for w in standalone_cancel):
        return True

    if "no" in words and "problem" not in words:
        return True

    return False


# ============================================================
# PENDING ACTION MANAGEMENT
# ============================================================

def create_pending_action(
    customer_id: str,
    action_type: str,
    parameters: Dict[str, Any],
    preview: Dict[str, Any],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register a state-changing operation awaiting explicit user confirmation.
    Also logs a *_REQUESTED audit log.
    """
    cid = customer_id.upper()
    now = datetime.datetime.now()
    expires_at = now + datetime.timedelta(seconds=ttl_seconds)

    action_record = {
        "action_type": action_type.lower(),
        "customer_id": cid,
        "parameters": parameters,
        "preview": preview,
        "status": "pending",
        "created_at": now,
        "expires_at": expires_at,
        "username": username or cid,
    }

    _PENDING_ACTIONS[cid] = action_record

    # Audit Log: REQUESTED
    action_tag = f"{action_type.upper()}_REQUESTED"
    record_audit_log(
        customer_id=cid,
        action=action_tag,
        details=f"Pending {action_type} action registered. Parameters: {parameters}",
        status="pending",
        username=username or cid,
    )

    return action_record


def get_pending_action(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve currently pending action for a customer, checking TTL expiry.
    """
    cid = customer_id.upper()
    action = _PENDING_ACTIONS.get(cid)
    if not action:
        return None

    # Check if expired
    if datetime.datetime.now() > action["expires_at"]:
        # Mark expired and clean up
        action["status"] = "expired"
        _PENDING_ACTIONS.pop(cid, None)
        return None

    return action


def cancel_pending_action(
    customer_id: str,
    reason: str = "User cancelled action",
    username: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Cancel an active pending action without modifying database state.
    Logs a *_CANCELLED audit log.
    """
    cid = customer_id.upper()
    action = _PENDING_ACTIONS.pop(cid, None)
    if not action:
        return None

    action_type = action.get("action_type", "action")
    action["status"] = "cancelled"

    # Audit Log: CANCELLED
    record_audit_log(
        customer_id=cid,
        action=f"{action_type.upper()}_CANCELLED",
        details=f"Pending {action_type} cancelled: {reason}",
        status="cancelled",
        username=username or action.get("username") or cid,
    )

    return action


def confirm_and_execute_pending_action(
    customer_id: str,
    auth_token: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes a previously staged action upon explicit confirmation.
    Validates expiration, customer ownership, records audit logs,
    and calls backend action endpoints.
    """
    cid = customer_id.upper()
    action = get_pending_action(cid)

    if not action:
        # Check if it was expired
        return {
            "status": "FAILED",
            "error": "No pending action found or the action has expired. Please initiate the request again.",
            "code": "EXPIRED_OR_NOT_FOUND",
        }

    # Verify action belongs to this customer
    if action["customer_id"] != cid:
        return {
            "status": "FAILED",
            "error": "Unauthorized: Customer cannot confirm actions belonging to another customer.",
            "code": "UNAUTHORIZED_CUSTOMER",
        }

    action_type = action["action_type"]
    parameters = action["parameters"]
    user_name = username or action.get("username") or cid

    # Audit Log: CONFIRMED
    record_audit_log(
        customer_id=cid,
        action=f"{action_type.upper()}_CONFIRMED",
        details=f"User confirmed {action_type} with parameters {parameters}",
        status="confirmed",
        username=user_name,
    )

    # Dispatch Execution
    result = {}
    from tools import create_support_ticket, execute_plan_change, execute_recharge

    try:
        if action_type == "change_plan":
            result = execute_plan_change(
                customer_id=cid,
                new_plan_id=parameters["plan_id"],
                auth_token=auth_token,
            )
        elif action_type == "recharge":
            result = execute_recharge(
                customer_id=cid,
                amount=parameters["amount"],
                payment_method=parameters.get("payment_method", "UPI"),
                auth_token=auth_token,
            )
        elif action_type == "create_ticket":
            result = create_support_ticket(
                customer_id=cid,
                description=parameters["description"],
                category=parameters.get("category", "general"),
                priority=parameters.get("priority", "medium"),
                auth_token=auth_token,
            )
        else:
            result = {
                "status": "FAILED",
                "error": f"Unknown action type: {action_type}",
            }
    except Exception as e:
        result = {
            "status": "FAILED",
            "error": str(e),
        }
    finally:
        # Clear from pending store
        _PENDING_ACTIONS.pop(cid, None)

    return result


# ============================================================
# PREVIEW GENERATORS
# ============================================================

def prepare_plan_change_preview(customer_id: str, new_plan_id: str) -> Dict[str, Any]:
    """
    Retrieve current plan and target plan to compute differences and preview text.
    """
    from tools import get_current_plan, get_all_plans

    current_sub = get_current_plan(customer_id)
    plans = get_all_plans()

    curr_plan_name = current_sub.get("plan_name", "Unknown Plan") if isinstance(current_sub, dict) else "Current Plan"
    curr_price = float(current_sub.get("price", 0.0)) if isinstance(current_sub, dict) else 0.0

    target_plan = None
    if isinstance(plans, list):
        for p in plans:
            if str(p.get("plan_id", "")).upper() == new_plan_id.upper():
                target_plan = p
                break

    if not target_plan:
        # Fallback query DB
        from database import query_database
        df = query_database("SELECT * FROM plans WHERE UPPER(plan_id) = ?", (new_plan_id.upper(),))
        if not df.empty:
            target_plan = df.iloc[0].to_dict()

    if not target_plan:
        return {
            "error": f"Plan {new_plan_id} does not exist in available catalogue.",
            "valid": False,
        }

    target_price = float(target_plan.get("price", 0.0))
    price_diff = target_price - curr_price
    diff_text = f"+₹{price_diff:.2f}" if price_diff >= 0 else f"-₹{abs(price_diff):.2f}"

    preview_text = (
        f"**PLAN CHANGE REQUEST**\n\n"
        f"• **Current plan:** {curr_plan_name}\n"
        f"• **New plan:** {target_plan.get('plan_name')}\n"
        f"• **Price:** ₹{target_price:.0f}\n"
        f"• **Data:** {target_plan.get('data_gb')} GB\n"
        f"• **Validity:** {target_plan.get('validity_days')} days\n"
        f"• **Estimated monthly difference:** {diff_text}\n\n"
        f"Do you want me to confirm this plan change?"
    )

    return {
        "valid": True,
        "action_type": "change_plan",
        "customer_id": customer_id.upper(),
        "parameters": {"plan_id": target_plan.get("plan_id")},
        "details": {
            "current_plan": curr_plan_name,
            "new_plan": target_plan.get("plan_name"),
            "price": target_price,
            "data_gb": target_plan.get("data_gb"),
            "validity_days": target_plan.get("validity_days"),
            "price_difference": diff_text,
        },
        "preview_text": preview_text,
    }


def prepare_recharge_preview(
    customer_id: str,
    amount: float,
    payment_method: str = "UPI",
) -> Dict[str, Any]:
    """
    Generates preview for mock/demo recharge request.
    """
    if amount <= 0:
        return {
            "error": "Invalid recharge amount. Amount must be greater than zero.",
            "valid": False,
        }

    preview_text = (
        f"**RECHARGE REQUEST (DEMO)**\n\n"
        f"• **Customer:** {customer_id.upper()}\n"
        f"• **Amount:** ₹{amount:.2f}\n"
        f"• **Payment Method:** {payment_method}\n"
        f"• **Notice:** *This is a MOCK/DEMO transaction. No real money will be charged.*\n\n"
        f"Please confirm this recharge."
    )

    return {
        "valid": True,
        "action_type": "recharge",
        "customer_id": customer_id.upper(),
        "parameters": {
            "amount": float(amount),
            "payment_method": payment_method,
        },
        "details": {
            "amount": float(amount),
            "payment_method": payment_method,
        },
        "preview_text": preview_text,
    }


def prepare_ticket_preview(
    customer_id: str,
    description: str,
    category: str = "network",
    priority: str = "high",
) -> Dict[str, Any]:
    """
    Generates preview for support ticket creation.
    """
    preview_text = (
        f"**ACTION REQUIRED — Create Support Ticket**\n\n"
        f"• **Customer:** {customer_id.upper()}\n"
        f"• **Category:** {category.capitalize()}\n"
        f"• **Priority:** {priority.capitalize()}\n"
        f"• **Description:** {description}\n\n"
        f"Would you like me to create this support ticket?"
    )

    return {
        "valid": True,
        "action_type": "create_ticket",
        "customer_id": customer_id.upper(),
        "parameters": {
            "description": description,
            "category": category,
            "priority": priority,
        },
        "details": {
            "category": category,
            "priority": priority,
            "description": description,
        },
        "preview_text": preview_text,
    }
