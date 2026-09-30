from database import query_database


# ============================================================
# SCORE DOWNLOAD SPEED
# ============================================================

def score_download_speed(value):

    value = float(value)

    if value >= 80:
        return 30

    if value >= 50:
        return 24

    if value >= 25:
        return 18

    if value >= 10:
        return 10

    return 3


# ============================================================
# SCORE UPLOAD SPEED
# ============================================================

def score_upload_speed(value):

    value = float(value)

    if value >= 20:
        return 15

    if value >= 15:
        return 12

    if value >= 8:
        return 9

    if value >= 4:
        return 6

    return 2


# ============================================================
# SCORE LATENCY
# ============================================================

def score_latency(value):

    value = float(value)

    if value <= 30:
        return 20

    if value <= 50:
        return 16

    if value <= 80:
        return 12

    if value <= 120:
        return 7

    return 2


# ============================================================
# SCORE PACKET LOSS
# ============================================================

def score_packet_loss(value):

    value = float(value)

    if value <= 1:
        return 20

    if value <= 2:
        return 16

    if value <= 5:
        return 11

    if value <= 10:
        return 6

    return 1


# ============================================================
# SCORE SIGNAL
# ============================================================

def score_signal(value):

    value = float(value)

    # dBm is negative.
    # Closer to zero means stronger signal.

    if value >= -70:
        return 15

    if value >= -80:
        return 12

    if value >= -90:
        return 7

    return 2


# ============================================================
# HEALTH STATUS
# ============================================================

def health_status(score):

    if score >= 75:
        return "HEALTHY"

    if score >= 50:
        return "DEGRADED"

    return "CRITICAL"


# ============================================================
# LIKELY PROBLEMS
# ============================================================

def identify_problems(row):

    problems = []

    latency = float(row["latency_ms"])
    packet_loss = float(row["packet_loss_percent"])
    signal = float(row["signal_strength_dbm"])
    download = float(row["download_mbps"])
    active_users = int(row["active_users"])

    if latency > 120:
        problems.append(
            "Very high latency"
        )

    elif latency > 80:
        problems.append(
            "High latency"
        )

    if packet_loss > 10:
        problems.append(
            "Severe packet loss"
        )

    elif packet_loss > 5:
        problems.append(
            "High packet loss"
        )

    if signal < -90:
        problems.append(
            "Weak signal strength"
        )

    elif signal < -80:
        problems.append(
            "Moderately weak signal"
        )

    if download < 10:
        problems.append(
            "Very low download speed"
        )

    elif download < 25:
        problems.append(
            "Low download speed"
        )

    if active_users >= 800:
        problems.append(
            "High tower utilization"
        )

    if not problems:
        problems.append(
            "No major network problem detected"
        )

    return problems


# ============================================================
# DIAGNOSE ONE TOWER
# ============================================================

def diagnose_tower(tower_id):

    query = """
    SELECT *
    FROM network
    WHERE tower_id = ?
    """

    df = query_database(
        query,
        (tower_id,)
    )

    if df.empty:

        return {
            "error": f"Tower {tower_id} not found."
        }

    row = df.iloc[0]

    download_score = score_download_speed(
        row["download_mbps"]
    )

    upload_score = score_upload_speed(
        row["upload_mbps"]
    )

    latency_score = score_latency(
        row["latency_ms"]
    )

    packet_loss_score = score_packet_loss(
        row["packet_loss_percent"]
    )

    signal_score = score_signal(
        row["signal_strength_dbm"]
    )

    total_score = (
        download_score
        + upload_score
        + latency_score
        + packet_loss_score
        + signal_score
    )

    problems = identify_problems(row)

    status = health_status(
        total_score
    )

    return {

        "tower_id": row["tower_id"],

        "location": row["location"],

        "technology": row["technology"],

        "download_mbps": float(
            row["download_mbps"]
        ),

        "upload_mbps": float(
            row["upload_mbps"]
        ),

        "latency_ms": float(
            row["latency_ms"]
        ),

        "packet_loss_percent": float(
            row["packet_loss_percent"]
        ),

        "signal_strength_dbm": float(
            row["signal_strength_dbm"]
        ),

        "active_users": int(
            row["active_users"]
        ),

        "database_status": row["status"],

        "health_score": total_score,

        "health_status": status,

        "problems": problems,

    }


# ============================================================
# DIAGNOSE LOCATION
# ============================================================

def diagnose_location(location):

    query = """
    SELECT tower_id
    FROM network
    WHERE location = ?
    """

    df = query_database(
        query,
        (location,)
    )

    if df.empty:

        return {
            "error": f"No network towers found in {location}."
        }

    results = []

    for tower_id in df["tower_id"]:

        results.append(
            diagnose_tower(tower_id)
        )

    return results


# ============================================================
# NETWORK SUMMARY
# ============================================================

def network_summary():

    query = """
    SELECT *
    FROM network
    """

    df = query_database(query)

    if df.empty:

        return {
            "error": "No network data available."
        }

    results = []

    for tower_id in df["tower_id"]:
        results.append(
            diagnose_tower(tower_id)
        )

    return results


# ============================================================
# DETERMINISTIC NETWORK HEALTH SCORE & CLASSIFICATION
# ============================================================

def calculate_network_health(
    download_mbps: float,
    upload_mbps: float,
    latency_ms: float,
    packet_loss_percent: float,
    signal_strength_dbm: float,
) -> int:
    """
    Calculate deterministic, transparent network health score (0-100).
    Metric weights:
    - Download speed: up to 30 points (>=80 Mbps: 30, >=50: 24, >=25: 18, >=10: 10, <10: 3)
    - Upload speed: up to 15 points (>=20 Mbps: 15, >=15: 12, >=8: 9, >=4: 6, <4: 2)
    - Latency: up to 20 points (<=30 ms: 20, <=50: 16, <=80: 12, <=120: 7, >120: 2)
    - Packet loss: up to 20 points (<=1%: 20, <=2%: 16, <=5%: 11, <=10%: 6, >10%: 1)
    - Signal strength: up to 15 points (>=-70 dBm: 15, >=-80: 12, >=-90: 7, <-90: 2)
    Total score = sum of metric points (range: 10 to 100).
    """
    return int(
        score_download_speed(download_mbps)
        + score_upload_speed(upload_mbps)
        + score_latency(latency_ms)
        + score_packet_loss(packet_loss_percent)
        + score_signal(signal_strength_dbm)
    )


def classify_network_quality(health_score: int) -> str:
    """
    Classify numerical health score into standard telecom quality category.
    >= 80: Excellent
    >= 60: Good
    >= 40: Fair
    < 40: Poor
    """
    if health_score >= 80:
        return "Excellent"
    if health_score >= 60:
        return "Good"
    if health_score >= 40:
        return "Fair"
    return "Poor"


# ============================================================
# COMPREHENSIVE CUSTOMER NETWORK DIAGNOSTICS
# ============================================================

def get_network_diagnostics(customer_id: str = None, location: str = None):
    """
    Retrieve deterministic end-to-end network diagnostics for a customer or location.
    Integrates customer profile, active technology, local towers, and active outages.
    """
    loc = location
    tech = "5G"
    cust_id = customer_id

    # 1. Customer Context Resolution
    if cust_id:
        try:
            from tools import get_customer_profile, get_current_plan
            profile = get_customer_profile(cust_id)
            if isinstance(profile, dict) and "location" in profile:
                if not loc:
                    loc = profile.get("location")
            plan_info = get_current_plan(cust_id)
            if isinstance(plan_info, dict) and "technology" in plan_info:
                tech = plan_info.get("technology", "5G")
        except Exception:
            # Fallback to direct DB query if needed
            q = "SELECT location FROM customers WHERE customer_id = ?"
            df_c = query_database(q, (cust_id,))
            if not df_c.empty and not loc:
                loc = df_c.iloc[0]["location"]

    if not loc:
        loc = "Kolkata"

    # 2. Towers in Customer Location
    try:
        from tools import check_network_status, check_outage
        towers = check_network_status(location=loc)
        outages = check_outage(location=loc)
    except Exception:
        towers = query_database("SELECT * FROM network WHERE location = ?", (loc,)).to_dict(orient="records")
        outages = query_database("SELECT * FROM outages WHERE location = ? AND status = 'active'", (loc,)).to_dict(orient="records")

    if isinstance(towers, str) or not towers:
        towers = query_database("SELECT * FROM network WHERE location = ?", (loc,)).to_dict(orient="records")
    if isinstance(outages, str):
        outages = []

    if not towers:
        return {
            "customer_id": cust_id or "UNKNOWN",
            "location": loc,
            "technology": tech,
            "error": f"No network towers found for location {loc}."
        }

    # 3. Select Representative Tower
    # Prioritize degraded tower or tower with active outage if present to diagnose user problem
    selected_tower = None
    outage_tower_ids = [o.get("tower_id") for o in outages if isinstance(o, dict) and o.get("tower_id")]

    for t in towers:
        if t.get("tower_id") in outage_tower_ids:
            selected_tower = t
            break

    if not selected_tower:
        for t in towers:
            if t.get("status", "").lower() == "degraded" and (t.get("technology", "").upper() == tech.upper() or not tech):
                selected_tower = t
                break

    if not selected_tower:
        for t in towers:
            if t.get("technology", "").upper() == tech.upper():
                selected_tower = t
                break

    if not selected_tower:
        selected_tower = towers[0]

    # 4. Deterministic Calculation
    down = float(selected_tower.get("download_mbps", 0.0))
    up = float(selected_tower.get("upload_mbps", 0.0))
    lat = float(selected_tower.get("latency_ms", 0.0))
    loss = float(selected_tower.get("packet_loss_percent", 0.0))
    sig = float(selected_tower.get("signal_strength_dbm", -100.0))
    tower_status = selected_tower.get("status", "unknown")

    score = calculate_network_health(down, up, lat, loss, sig)
    quality = classify_network_quality(score)
    problems = identify_problems(selected_tower)

    return {
        "customer_id": cust_id or "CUST001",
        "location": loc,
        "technology": selected_tower.get("technology", tech),
        "tower_id": selected_tower.get("tower_id", "T001"),
        "health_score": score,
        "quality": quality,
        "download_mbps": down,
        "upload_mbps": up,
        "latency_ms": lat,
        "packet_loss_percent": loss,
        "signal_strength_dbm": sig,
        "tower_status": tower_status,
        "active_users": int(selected_tower.get("active_users", 0)),
        "problems": problems,
        "active_outages": outages,
    }