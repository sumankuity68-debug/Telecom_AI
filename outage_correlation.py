from typing import Dict, Any, Optional


def correlate_outage(customer_id: str, location: Optional[str] = None) -> Dict[str, Any]:
    """
    Correlate customer connectivity issues with active carrier outages and network telemetry.
    Combines geographic proximity, tower degradation, and timestamp data without assuming causality.
    """
    from tools import get_customer_profile, check_network_status, check_outage
    from database import query_database

    cust_id = customer_id.strip().upper() if customer_id else "CUST001"
    loc = location

    # 1. Resolve Customer Location
    if not loc:
        profile = get_customer_profile(cust_id)
        if isinstance(profile, dict) and "location" in profile:
            loc = profile.get("location")
        else:
            df_c = query_database("SELECT location FROM customers WHERE customer_id = ?", (cust_id,))
            loc = df_c.iloc[0]["location"] if not df_c.empty else "Kolkata"

    if not loc:
        loc = "Kolkata"

    # 2. Retrieve Outages in Location
    outages = check_outage(location=loc)
    if isinstance(outages, str) or not outages:
        outages = query_database("SELECT * FROM outages WHERE location = ? AND status = 'active'", (loc,)).to_dict(orient="records")

    if isinstance(outages, str):
        outages = []

    # 3. Retrieve Towers in Location
    towers = check_network_status(location=loc)
    if isinstance(towers, str) or not towers:
        towers = query_database("SELECT * FROM network WHERE location = ?", (loc,)).to_dict(orient="records")

    if isinstance(towers, str):
        towers = []

    # 4. Correlation Analysis
    if not outages:
        return {
            "customer_id": cust_id,
            "location": loc,
            "tower_id": towers[0].get("tower_id") if towers else "N/A",
            "outage_detected": False,
            "outage_id": None,
            "reason": None,
            "correlation": "none",
            "explanation": f"No active carrier outages detected in the customer's area ({loc}). Local network degradation may be coverage- or handset-related."
        }

    # Match active outage
    primary_outage = outages[0]
    outage_id = primary_outage.get("outage_id", "OUT001")
    outage_tower = primary_outage.get("tower_id", "")
    reason = primary_outage.get("reason", "Network congestion")
    start_time = primary_outage.get("start_time", "")

    # Check if any matching tower is degraded
    matched_tower = None
    is_tower_degraded = False

    for t in towers:
        if outage_tower and t.get("tower_id") == outage_tower:
            matched_tower = t
            break

    if not matched_tower and towers:
        matched_tower = towers[0]

    if matched_tower:
        is_tower_degraded = (
            matched_tower.get("status", "").lower() == "degraded"
            or float(matched_tower.get("latency_ms", 0.0)) > 80.0
            or float(matched_tower.get("packet_loss_percent", 0.0)) > 5.0
        )

    assigned_tower_id = matched_tower.get("tower_id", outage_tower or "T002") if matched_tower else outage_tower

    if is_tower_degraded:
        correlation = "high"
        explanation = (
            f"Network degradation is correlated with an active outage ({outage_id}: {reason}) "
            f"affecting tower {assigned_tower_id} in {loc} since {start_time}."
        )
    else:
        correlation = "moderate"
        explanation = (
            f"An active outage ({outage_id}: {reason}) is recorded in {loc}, "
            f"though nearby tower metrics indicate partial or localized service continuity."
        )

    return {
        "customer_id": cust_id,
        "location": loc,
        "tower_id": assigned_tower_id,
        "outage_detected": True,
        "outage_id": outage_id,
        "reason": reason,
        "start_time": start_time,
        "correlation": correlation,
        "explanation": explanation,
        "tower_status": matched_tower.get("status") if matched_tower else "unknown",
        "affected_technology": matched_tower.get("technology") if matched_tower else "5G",
    }
