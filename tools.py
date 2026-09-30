import os
from datetime import datetime
import requests

from database import query_database, execute_database

from diagnostics import (
    diagnose_tower,
    diagnose_location,
    network_summary,
)

from anomaly_detection import (
    predict_tower,
    predict_all_towers,
)

from rag import get_context

# FastAPI Base URL for API-based tools
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")
API_TIMEOUT = 0.5


# ============================================================
# CUSTOMER PROFILE
# ============================================================

def get_customer_profile(customer_id: str):
    """
    Retrieve customer details via FastAPI backend, with DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/customers/{customer_id}", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return f"No customer found with ID {customer_id}."
    except Exception:
        pass

    query = """
    SELECT *
    FROM customers
    WHERE customer_id = ?
    """
    df = query_database(query, (customer_id,))
    if df.empty:
        return f"No customer found with ID {customer_id}."
    return df.iloc[0].to_dict()


# ============================================================
# CURRENT PLAN
# ============================================================

def get_current_plan(customer_id: str):
    """
    Retrieve active plan details via FastAPI backend, with DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/customers/{customer_id}/plan", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return f"No active subscription found for {customer_id}."
    except Exception:
        pass

    query = """
    SELECT
        s.subscription_id,
        s.customer_id,
        s.start_date,
        s.expiry_date,
        s.status,
        p.plan_id,
        p.plan_name,
        p.price,
        p.validity_days,
        p.data_gb,
        p.calls,
        p.sms,
        p.technology
    FROM subscriptions s
    JOIN plans p
        ON s.plan_id = p.plan_id
    WHERE s.customer_id = ?
    """
    df = query_database(query, (customer_id,))
    if df.empty:
        return f"No active subscription found for {customer_id}."
    return df.iloc[0].to_dict()


# ============================================================
# USAGE
# ============================================================

def get_usage(customer_id: str):
    """
    Retrieve customer data/call usage records via FastAPI backend, with DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/customers/{customer_id}/usage", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return f"No usage data found for {customer_id}."
            return data
    except Exception:
        pass

    query = """
    SELECT *
    FROM usage
    WHERE customer_id = ?
    ORDER BY date DESC
    """
    df = query_database(query, (customer_id,))
    if df.empty:
        return f"No usage data found for {customer_id}."
    return df.to_dict(orient="records")


# ============================================================
# BILL
# ============================================================

def get_bill(customer_id: str):
    """
    Retrieve latest billing statement via FastAPI backend, with DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/customers/{customer_id}/bill", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return f"No bill found for {customer_id}."
    except Exception:
        pass

    query = """
    SELECT *
    FROM bills
    WHERE customer_id = ?
    ORDER BY billing_date DESC
    LIMIT 1
    """
    df = query_database(query, (customer_id,))
    if df.empty:
        return f"No bill found for {customer_id}."
    return df.iloc[0].to_dict()


# ============================================================
# BILL EXPLANATION
# ============================================================

def explain_bill(customer_id: str):
    bill = get_bill(customer_id)
    if isinstance(bill, str):
        return bill
    return {
        "base_plan": bill.get("base_plan", 0.0),
        "addon_charges": bill.get("addon_charges", 0.0),
        "roaming_charges": bill.get("roaming_charges", 0.0),
        "taxes": bill.get("taxes", 0.0),
        "total_amount": bill.get("total_amount", 0.0),
        "status": bill.get("status", "pending"),
    }


# ============================================================
# PLAN SEARCH
# ============================================================

def search_plans(
    technology=None,
    max_price=None,
    min_data=None
):
    """
    Search available telecom plans via FastAPI backend, with DB fallback.
    """
    try:
        params = {}
        if technology:
            params["technology"] = technology
        if max_price is not None:
            params["max_price"] = max_price
        if min_data is not None:
            params["min_data"] = min_data

        resp = requests.get(f"{FASTAPI_BASE_URL}/api/plans", params=params, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return "No matching plans found."
            return data
    except Exception:
        pass

    query = """
    SELECT *
    FROM plans
    WHERE 1 = 1
    """
    params = []
    if technology:
        query += " AND technology = ?"
        params.append(technology)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    if min_data is not None:
        query += " AND data_gb >= ?"
        params.append(min_data)

    query += " ORDER BY price ASC"
    df = query_database(query, tuple(params))
    if df.empty:
        return "No matching plans found."
    return df.to_dict(orient="records")


# ============================================================
# NETWORK STATUS
# ============================================================

def check_network_status(
    location=None
):
    """
    Check telecom tower metrics via FastAPI backend, with DB fallback.
    """
    try:
        url = f"{FASTAPI_BASE_URL}/api/network/{location}" if location else f"{FASTAPI_BASE_URL}/api/network"
        resp = requests.get(url, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return "No network information found."
            return data
    except Exception:
        pass

    if location:
        query = "SELECT * FROM network WHERE location = ?"
        df = query_database(query, (location,))
    else:
        query = "SELECT * FROM network"
        df = query_database(query)

    if df.empty:
        return "No network information found."
    return df.to_dict(orient="records")


# ============================================================
# NETWORK HEALTH
# ============================================================

def get_network_health(
    location=None,
    tower_id=None
):
    if tower_id:
        return diagnose_tower(tower_id)
    if location:
        return diagnose_location(location)
    return network_summary()


# ============================================================
# REAL LIVE OPENCELLID TOWERS
# ============================================================

def get_live_cell_towers(location=None, lat=None, lon=None):
    """
    Fetch real-world cellular towers from OpenCellID global database.
    """
    try:
        params = {}
        if location:
            params["city"] = location
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon

        resp = requests.get(f"{FASTAPI_BASE_URL}/api/network/live/opencellid", params=params, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    from backend.opencellid_service import get_city_towers, get_real_towers
    if lat is not None and lon is not None:
        return get_real_towers(lat=lat, lon=lon)
    return get_city_towers(city_name=location or "Kolkata")


# ============================================================
# NETWORK ANOMALY
# ============================================================

def get_network_anomalies(
    tower_id=None
):
    if tower_id:
        return predict_tower(tower_id)

    df = predict_all_towers()
    return df[
        [
            "tower_id",
            "location",
            "anomaly",
            "anomaly_score",
        ]
    ].to_dict(orient="records")


# ============================================================
# OUTAGE CHECK
# ============================================================

def check_outage(
    location=None
):
    """
    Check active outages via FastAPI backend, with DB fallback.
    """
    try:
        params = {"status": "active"}
        if location:
            params["location"] = location
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/outages", params=params, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return "No active outage found."
            return data
    except Exception:
        pass

    if location:
        query = """
        SELECT *
        FROM outages
        WHERE location = ?
        AND status = 'active'
        """
        df = query_database(query, (location,))
    else:
        query = """
        SELECT *
        FROM outages
        WHERE status = 'active'
        """
        df = query_database(query)

    if df.empty:
        return "No active outage found."
    return df.to_dict(orient="records")


# ============================================================
# COMPLETE NETWORK INTELLIGENCE
# ============================================================

def network_intelligence(
    location=None,
    tower_id=None
):
    health = get_network_health(
        location=location,
        tower_id=tower_id
    )
    anomalies = get_network_anomalies(
        tower_id=tower_id
    )
    outage = check_outage(
        location=location
    )
    live_towers = get_live_cell_towers(location=location) if location else {"total_towers": 0}
    return {
        "health_analysis": health,
        "ml_anomaly_analysis": anomalies,
        "active_outage": outage,
        "real_opencellid_towers_detected": live_towers.get("total_towers", 0),
    }


# ============================================================
# RAG SEARCH
# ============================================================

def search_telecom_knowledge(
    query
):
    return get_context(
        query,
        top_k=3
    )


# ============================================================
# SUPPORT TICKET
# ============================================================

def create_support_ticket(
    customer_id: str,
    category: str,
    description: str,
    priority: str = "medium"
):
    """
    Create a new support ticket via FastAPI backend, with DB fallback.
    """
    try:
        payload = {
            "customer_id": customer_id,
            "category": category,
            "description": description,
            "priority": priority,
        }
        resp = requests.post(f"{FASTAPI_BASE_URL}/api/tickets", json=payload, timeout=API_TIMEOUT)
        if resp.status_code in (200, 201):
            return resp.json()
    except Exception:
        pass

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query = """
    SELECT COUNT(*) AS count
    FROM tickets
    """
    df = query_database(query)
    count = int(df.iloc[0]["count"]) + 1
    ticket_id = f"TEL{count:03d}"

    insert_query = """
    INSERT INTO tickets
    (
        ticket_id,
        customer_id,
        category,
        description,
        priority,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    execute_database(
        insert_query,
        (
            ticket_id,
            customer_id,
            category,
            description,
            priority,
            "open",
            timestamp,
        )
    )

    return {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "category": category,
        "description": description,
        "priority": priority,
        "status": "open",
        "created_at": timestamp,
    }


# ============================================================
# TICKET STATUS
# ============================================================

def get_ticket_status(
    ticket_id: str
):
    query = """
    SELECT *
    FROM tickets
    WHERE ticket_id = ?
    """
    df = query_database(query, (ticket_id,))
    if df.empty:
        return f"No ticket found with ID {ticket_id}."
    return df.iloc[0].to_dict()


# ============================================================
# CUSTOMER TICKETS
# ============================================================

def get_customer_tickets(
    customer_id: str
):
    """
    Retrieve customer tickets via FastAPI backend, with DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/customers/{customer_id}/tickets", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return "No support tickets found."
            return data
    except Exception:
        pass

    query = """
    SELECT *
    FROM tickets
    WHERE customer_id = ?
    ORDER BY created_at DESC
    """
    df = query_database(query, (customer_id,))
    if df.empty:
        return "No support tickets found."
    return df.to_dict(orient="records")


# ============================================================
# PHASE C — AGENT INTELLIGENCE TOOLS
# ============================================================

def get_network_diagnostics(customer_id: str = None, location: str = None):
    """
    Step 11: End-to-end customer/location network diagnostic tool.
    Computes deterministic health score and quality classification.
    """
    from diagnostics import get_network_diagnostics as diag_func
    return diag_func(customer_id=customer_id, location=location)


def calculate_network_health(download_mbps, upload_mbps, latency_ms, packet_loss_percent, signal_strength_dbm):
    """
    Step 11: Deterministic network health scoring algorithm.
    """
    from diagnostics import calculate_network_health as calc_func
    return calc_func(download_mbps, upload_mbps, latency_ms, packet_loss_percent, signal_strength_dbm)


def classify_network_quality(health_score: int):
    """
    Step 11: Network quality tier classification.
    """
    from diagnostics import classify_network_quality as class_func
    return class_func(health_score)


def detect_network_anomaly(network_data):
    """
    Step 12: Machine-learning based anomaly detection for network telemetry.
    """
    from anomaly_detection import detect_network_anomaly as anom_func
    return anom_func(network_data)


def recommend_plans(customer_id: str, preferred_technology: str = None, max_budget: float = None):
    """
    Step 13: Usage-driven personalized telecom plan recommendation engine.
    """
    from recommendations import recommend_plans as rec_func
    return rec_func(customer_id=customer_id, preferred_technology=preferred_technology, max_budget=max_budget)


def analyze_bill(customer_id: str):
    """
    Step 14: Comprehensive bill analysis and itemized variance engine.
    """
    from billing_analysis import analyze_bill as bill_func
    return bill_func(customer_id=customer_id)


def correlate_outage(customer_id: str, location: str = None):
    """
    Step 15: Outage correlation linking subscriber issues with active carrier NOC alerts.
    """
    from outage_correlation import correlate_outage as out_func
    return out_func(customer_id=customer_id, location=location)


def complete_network_incident_analysis(customer_id: str = None, location: str = None):
    """
    Combines Network Diagnostics (11), Anomaly Detection (12), and Outage Correlation (15)
    into an integrated grounded intelligence report.
    """
    diag = get_network_diagnostics(customer_id=customer_id, location=location)
    anom = detect_network_anomaly(diag)
    outage_corr = correlate_outage(customer_id=customer_id, location=location)

    return {
        "diagnostics": diag,
        "anomaly_analysis": anom,
        "outage_correlation": outage_corr,
    }


# ============================================================
# PHASE D — STATE-CHANGING ACTION TOOLS
# ============================================================

def get_all_plans():
    """
    Retrieve all available telecom plans with FastAPI backend and DB fallback.
    """
    try:
        resp = requests.get(f"{FASTAPI_BASE_URL}/api/plans", timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    df = query_database("SELECT * FROM plans")
    if df.empty:
        return []
    return df.to_dict(orient="records")


def create_support_ticket(
    customer_id: str,
    description: str,
    category: str = "general",
    priority: str = "medium",
    auth_token: str = None,
):
    """
    Step 16: Creates a support ticket in FastAPI backend with DB fallback.
    Records creation in the action audit log.
    """
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    payload = {
        "customer_id": customer_id.upper(),
        "category": category.lower(),
        "description": description.strip(),
        "priority": priority.lower(),
    }

    try:
        resp = requests.post(f"{FASTAPI_BASE_URL}/api/tickets", json=payload, headers=headers, timeout=API_TIMEOUT)
        if resp.status_code == 201:
            return resp.json()
        elif resp.status_code in (401, 403, 404):
            return {
                "status": "FAILED",
                "error": resp.json().get("detail", "Request failed"),
                "status_code": resp.status_code,
            }
    except Exception:
        pass

    # Direct DB execution fallback
    from backend.audit import record_audit_log
    from config import DATA_DIR
    import pandas as pd

    cid = customer_id.upper()
    df_count = query_database("SELECT COUNT(*) as cnt FROM tickets")
    cnt = int(df_count.iloc[0]["cnt"]) if not df_count.empty else 0
    ticket_id = f"TEL{cnt + 1:03d}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    execute_database(
        "INSERT INTO tickets (ticket_id, customer_id, category, description, priority, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, cid, category.lower(), description.strip(), priority.lower(), "open", now_str),
    )

    # Sync tickets.csv
    tickets_csv = DATA_DIR / "tickets.csv"
    if tickets_csv.exists():
        try:
            df_t = pd.read_csv(tickets_csv, dtype=str)
            new_row = {
                "ticket_id": ticket_id,
                "customer_id": cid,
                "category": category.lower(),
                "description": description.strip(),
                "priority": priority.lower(),
                "status": "open",
                "created_at": now_str,
            }
            df_t = pd.concat([df_t, pd.DataFrame([new_row])], ignore_index=True)
            df_t.to_csv(tickets_csv, index=False)
        except Exception:
            pass

    record_audit_log(
        customer_id=cid,
        action="TICKET_CREATED",
        details=f"Ticket {ticket_id} created. Priority: {priority}, Category: {category}. Desc: {description}",
        status="success",
        username=cid,
    )

    return {
        "ticket_id": ticket_id,
        "customer_id": cid,
        "category": category.lower(),
        "description": description.strip(),
        "priority": priority.lower(),
        "status": "open",
        "created_at": now_str,
    }


def execute_plan_change(
    customer_id: str,
    new_plan_id: str,
    auth_token: str = None,
):
    """
    Step 17: Mutates customer subscription to a new plan via FastAPI with DB fallback.
    Requires user confirmation prior to execution.
    """
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    cid = customer_id.upper()
    pid = new_plan_id.upper()

    try:
        resp = requests.post(
            f"{FASTAPI_BASE_URL}/api/customers/{cid}/change-plan",
            json={"new_plan_id": pid},
            headers=headers,
            timeout=API_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (400, 401, 403, 404):
            return {
                "status": "FAILED",
                "error": resp.json().get("detail", "Plan change failed"),
                "status_code": resp.status_code,
            }
    except Exception:
        pass

    # Direct DB execution fallback
    from backend.audit import record_audit_log
    from config import DATA_DIR
    import pandas as pd
    import datetime as dt

    df_p = query_database("SELECT * FROM plans WHERE UPPER(plan_id) = ?", (pid,))
    if df_p.empty:
        return {"status": "FAILED", "error": f"Plan {pid} not found", "status_code": 404}
    plan = df_p.iloc[0].to_dict()

    now = dt.datetime.now()
    now_str = now.strftime("%Y-%m-%d")
    expiry_date = (now + dt.timedelta(days=int(plan.get("validity_days", 28)))).strftime("%Y-%m-%d")

    df_sub = query_database("SELECT * FROM subscriptions WHERE customer_id = ?", (cid,))
    old_plan = df_sub.iloc[0]["plan_id"] if not df_sub.empty else "NONE"

    if df_sub.empty:
        execute_database(
            "INSERT INTO subscriptions (subscription_id, customer_id, plan_id, start_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, ?)",
            (f"SUB{int(now.timestamp())%1000:03d}", cid, pid, now_str, expiry_date, "active"),
        )
    else:
        execute_database(
            "UPDATE subscriptions SET plan_id = ?, start_date = ?, expiry_date = ?, status = 'active' WHERE customer_id = ?",
            (pid, now_str, expiry_date, cid),
        )

    # Sync subscriptions.csv
    sub_csv = DATA_DIR / "subscriptions.csv"
    if sub_csv.exists():
        try:
            df_csv = pd.read_csv(sub_csv, dtype=str)
            mask = df_csv["customer_id"].str.upper() == cid
            if mask.any():
                df_csv.loc[mask, "plan_id"] = pid
                df_csv.loc[mask, "start_date"] = now_str
                df_csv.loc[mask, "expiry_date"] = expiry_date
                df_csv.loc[mask, "status"] = "active"
            else:
                new_row = {
                    "subscription_id": f"SUB{len(df_csv)+1:03d}",
                    "customer_id": cid,
                    "plan_id": pid,
                    "start_date": now_str,
                    "expiry_date": expiry_date,
                    "status": "active",
                }
                df_csv = pd.concat([df_csv, pd.DataFrame([new_row])], ignore_index=True)
            df_csv.to_csv(sub_csv, index=False)
        except Exception:
            pass

    record_audit_log(
        customer_id=cid,
        action="PLAN_CHANGE_COMPLETED",
        details=f"Migrated from {old_plan} to {pid} ({plan.get('plan_name')}). Price: ₹{plan.get('price')}",
        status="success",
        username=cid,
    )

    return {
        "status": "SUCCESS",
        "action": "CHANGE_PLAN",
        "customer_id": cid,
        "previous_plan": old_plan,
        "new_plan_id": pid,
        "new_plan_name": plan.get("plan_name"),
        "price": plan.get("price"),
        "validity_days": plan.get("validity_days"),
        "data_gb": plan.get("data_gb"),
        "expiry_date": expiry_date,
        "message": f"Plan successfully changed to {plan.get('plan_name')}",
    }


def execute_recharge(
    customer_id: str,
    amount: float,
    payment_method: str = "UPI",
    auth_token: str = None,
):
    """
    Step 18: Executes a mock/demo recharge via FastAPI with DB fallback.
    Explicitly marked as DEMO / MOCK transaction.
    """
    if amount <= 0:
        return {
            "status": "FAILED",
            "error": "Invalid recharge amount. Amount must be greater than zero.",
            "status_code": 400,
        }

    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    cid = customer_id.upper()
    payload = {
        "customer_id": cid,
        "amount": float(amount),
        "payment_method": payment_method,
    }

    try:
        resp = requests.post(f"{FASTAPI_BASE_URL}/api/recharge", json=payload, headers=headers, timeout=API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (400, 401, 403, 404):
            return {
                "status": "FAILED",
                "error": resp.json().get("detail", "Recharge failed"),
                "status_code": resp.status_code,
            }
    except Exception:
        pass

    # Direct DB execution fallback
    from backend.audit import record_audit_log
    import datetime as dt

    tx_id = f"TXN{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
    record_audit_log(
        customer_id=cid,
        action="RECHARGE_COMPLETED",
        details=f"Demo recharge of ₹{amount:.2f} processed via {payment_method}. TxID: {tx_id}",
        status="success",
        username=cid,
    )

    return {
        "status": "SUCCESS",
        "action": "RECHARGE",
        "demo_mode": True,
        "transaction_id": tx_id,
        "customer_id": cid,
        "amount": float(amount),
        "payment_method": payment_method,
        "status_code": "COMPLETED",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "message": f"MOCK/DEMO recharge of ₹{amount:.2f} successful. No real currency transferred.",
    }


# Convenience workflow wrappers requested by prompt
def request_plan_change(customer_id: str, plan_id: str):
    from confirmation import prepare_plan_change_preview, create_pending_action
    prev = prepare_plan_change_preview(customer_id, plan_id)
    if not prev.get("valid"):
        return prev
    action = create_pending_action(customer_id, "change_plan", {"plan_id": plan_id}, prev)
    return {"status": "PENDING_CONFIRMATION", "preview": prev, "pending_action": action}


def confirm_plan_change(customer_id: str, auth_token: str = None):
    from confirmation import confirm_and_execute_pending_action
    return confirm_and_execute_pending_action(customer_id, auth_token=auth_token)


def request_recharge(customer_id: str, amount: float, payment_method: str = "UPI"):
    from confirmation import prepare_recharge_preview, create_pending_action
    prev = prepare_recharge_preview(customer_id, amount, payment_method)
    if not prev.get("valid"):
        return prev
    action = create_pending_action(customer_id, "recharge", {"amount": amount, "payment_method": payment_method}, prev)
    return {"status": "PENDING_CONFIRMATION", "preview": prev, "pending_action": action}


def confirm_recharge(customer_id: str, auth_token: str = None):
    from confirmation import confirm_and_execute_pending_action
    return confirm_and_execute_pending_action(customer_id, auth_token=auth_token)


def request_support_ticket(customer_id: str, description: str, category: str = "network", priority: str = "high"):
    from confirmation import prepare_ticket_preview, create_pending_action
    prev = prepare_ticket_preview(customer_id, description, category, priority)
    action = create_pending_action(customer_id, "create_ticket", {"description": description, "category": category, "priority": priority}, prev)
    return {"status": "PENDING_CONFIRMATION", "preview": prev, "pending_action": action}


def confirm_support_ticket(customer_id: str, auth_token: str = None):
    from confirmation import confirm_and_execute_pending_action
    return confirm_and_execute_pending_action(customer_id, auth_token=auth_token)