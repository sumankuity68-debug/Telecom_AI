import joblib

from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from database import query_database
from config import ANOMALY_MODEL_PATH


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [
    "download_mbps",
    "upload_mbps",
    "latency_ms",
    "packet_loss_percent",
    "signal_strength_dbm",
    "active_users",
]


# ============================================================
# LOAD NETWORK DATA
# ============================================================

def load_network_data():

    query = """
    SELECT
        tower_id,
        location,
        technology,
        download_mbps,
        upload_mbps,
        latency_ms,
        packet_loss_percent,
        signal_strength_dbm,
        active_users
    FROM network
    """

    return query_database(query)


# ============================================================
# TRAIN MODEL
# ============================================================

def train_anomaly_model():

    df = load_network_data()

    if len(df) < 5:

        raise ValueError(
            "At least 5 network records are required."
        )

    X = df[FEATURE_COLUMNS].astype(float)

    model = Pipeline(
        steps=[
            (
                "scaler",
                StandardScaler()
            ),

            (
                "isolation_forest",
                IsolationForest(
                    n_estimators=200,
                    contamination=0.25,
                    random_state=42
                )
            ),
        ]
    )

    model.fit(X)

    joblib.dump(
        {
            "model": model,
            "features": FEATURE_COLUMNS,
        },
        ANOMALY_MODEL_PATH
    )

    return model


# ============================================================
# LOAD MODEL
# ============================================================

def load_anomaly_model():

    if not ANOMALY_MODEL_PATH.exists():

        train_anomaly_model()

    saved = joblib.load(
        ANOMALY_MODEL_PATH
    )

    return saved["model"]


# ============================================================
# PREDICT ALL TOWERS
# ============================================================

def predict_all_towers():

    df = load_network_data()

    model = load_anomaly_model()

    X = df[FEATURE_COLUMNS].astype(float)

    predictions = model.predict(X)

    scores = model.decision_function(X)

    df["anomaly_prediction"] = predictions

    df["anomaly_score"] = scores

    df["anomaly"] = df[
        "anomaly_prediction"
    ].apply(
        lambda x: (
            "ANOMALY"
            if x == -1
            else "NORMAL"
        )
    )

    return df


# ============================================================
# PREDICT ONE TOWER
# ============================================================

def predict_tower(tower_id):

    df = load_network_data()

    tower = df[
        df["tower_id"] == tower_id
    ]

    if tower.empty:

        return {
            "error": f"Tower {tower_id} not found."
        }

    model = load_anomaly_model()

    X = tower[
        FEATURE_COLUMNS
    ].astype(float)

    prediction = model.predict(X)[0]

    score = model.decision_function(X)[0]

    return {

        "tower_id": tower_id,

        "location": tower.iloc[0]["location"],

        "prediction": (
            "ANOMALY"
            if prediction == -1
            else "NORMAL"
        ),

        "anomaly_score": round(
            float(score),
            4
        ),
    }


# ============================================================
# COMPREHENSIVE ANOMALY DETECTION FOR TELECOM INTELLIGENCE
# ============================================================

def detect_network_anomaly(network_data) -> dict:
    """
    Detect statistical anomalies in network telemetry using the trained Isolation Forest model.
    Accepts a dictionary of metrics, a DataFrame row, a tower_id ('T001'), or a customer_id ('CUST001').
    Returns structured output with raw ML model score, calibrated severity, and human-readable reasons.
    """
    import pandas as pd

    raw_metrics = {}

    # Handle string identifiers (tower_id or customer_id)
    if isinstance(network_data, str):
        cleaned = network_data.strip().upper()
        if cleaned.startswith("CUST"):
            from diagnostics import get_network_diagnostics
            diag = get_network_diagnostics(customer_id=cleaned)
            raw_metrics = {
                "download_mbps": diag.get("download_mbps", 50.0),
                "upload_mbps": diag.get("upload_mbps", 15.0),
                "latency_ms": diag.get("latency_ms", 30.0),
                "packet_loss_percent": diag.get("packet_loss_percent", 0.5),
                "signal_strength_dbm": diag.get("signal_strength_dbm", -75.0),
                "active_users": diag.get("active_users", 400),
            }
        elif cleaned.startswith("T"):
            df_net = load_network_data()
            match = df_net[df_net["tower_id"].str.upper() == cleaned]
            if not match.empty:
                raw_metrics = match.iloc[0].to_dict()
    elif isinstance(network_data, dict):
        raw_metrics = network_data
    elif hasattr(network_data, "to_dict"):
        raw_metrics = network_data.to_dict()

    # Fill defaults for any missing features
    down = float(raw_metrics.get("download_mbps", 50.0))
    up = float(raw_metrics.get("upload_mbps", 15.0))
    lat = float(raw_metrics.get("latency_ms", 35.0))
    loss = float(raw_metrics.get("packet_loss_percent", 0.5))
    sig = float(raw_metrics.get("signal_strength_dbm", -75.0))
    users = int(raw_metrics.get("active_users", 400))

    feature_dict = {
        "download_mbps": [down],
        "upload_mbps": [up],
        "latency_ms": [lat],
        "packet_loss_percent": [loss],
        "signal_strength_dbm": [sig],
        "active_users": [users],
    }
    df_features = pd.DataFrame(feature_dict)[FEATURE_COLUMNS].astype(float)

    model = load_anomaly_model()
    prediction = int(model.predict(df_features)[0])
    raw_score = float(model.decision_function(df_features)[0])
    is_anomaly = bool(prediction == -1)

    # Deterministic reasons based on operational thresholds
    reasons = []
    if lat > 120:
        reasons.append("Very high latency")
    elif lat > 80:
        reasons.append("High latency")

    if loss > 10:
        reasons.append("Severe packet loss")
    elif loss > 4.0:
        reasons.append("High packet loss")

    if down < 10:
        reasons.append("Critically low download speed")
    elif down < 25:
        reasons.append("Low download speed")

    if sig < -90:
        reasons.append("Weak signal strength")
    elif sig < -85:
        reasons.append("Marginal signal strength")

    if users >= 800:
        reasons.append("High tower congestion / user load")

    if is_anomaly and not reasons:
        reasons.append("Multivariate outlier detected across combined network telemetry")
    elif not is_anomaly and not reasons:
        reasons.append("All network metrics operate within normal historical parameters")

    # Calibrated severity based on score and critical metrics
    if not is_anomaly:
        severity = "normal"
    elif raw_score < -0.10 or lat > 150 or loss > 10.0:
        severity = "high"
    elif raw_score < -0.04 or lat > 80 or loss > 5.0:
        severity = "medium"
    else:
        severity = "low"

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": round(raw_score, 4),
        "score_interpretation": "IsolationForest decision score: negative indicates anomaly, positive indicates normal",
        "severity": severity,
        "reasons": reasons,
        "metrics": {
            "download_mbps": down,
            "upload_mbps": up,
            "latency_ms": lat,
            "packet_loss_percent": loss,
            "signal_strength_dbm": sig,
            "active_users": users,
        },
    }