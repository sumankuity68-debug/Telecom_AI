import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from config import DATA_DIR, DATABASE_PATH
from backend.models import (
    Base,
    Customer,
    Plan,
    Subscription,
    Usage,
    Bill,
    Network,
    Outage,
    Ticket,
    User,
)

# ------------------------------------------------------------
# DATABASE CONFIGURATION & ABSTRACTION
# ------------------------------------------------------------
# Check for DATABASE_URL (e.g. postgresql://user:pass@localhost:5432/telecom_ai)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Development / Fallback SQLite
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# Normalize postgresql prefix if needed (e.g. postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite requires check_same_thread=False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    """
    FastAPI dependency yielding a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database schema and seed data from CSVs if tables are empty.
    Supports both PostgreSQL and SQLite seamlessly.
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if customer records already exist
        customer_count = db.query(Customer).count()
        if customer_count == 0:
            print("[DB] Seeding database from CSV files...")

            # 1. Customers
            cust_csv = DATA_DIR / "customers.csv"
            if cust_csv.exists():
                df_cust = pd.read_csv(cust_csv).fillna("")
                for _, row in df_cust.iterrows():
                    db.add(Customer(
                        customer_id=str(row["customer_id"]).strip(),
                        name=str(row["name"]).strip(),
                        phone=str(row["phone"]).strip(),
                        email=str(row["email"]).strip(),
                        location=str(row["location"]).strip(),
                        customer_type=str(row.get("customer_type", "individual")).strip(),
                        account_status=str(row.get("account_status", "active")).strip(),
                    ))
                db.commit()

            # 2. Plans
            plans_csv = DATA_DIR / "plans.csv"
            if plans_csv.exists():
                df_plans = pd.read_csv(plans_csv).fillna("")
                for _, row in df_plans.iterrows():
                    db.add(Plan(
                        plan_id=str(row["plan_id"]).strip(),
                        plan_name=str(row["plan_name"]).strip(),
                        price=float(row["price"]),
                        validity_days=int(row["validity_days"]),
                        data_gb=float(row["data_gb"]),
                        calls=str(row.get("calls", "unlimited")).strip(),
                        sms=int(row.get("sms", 100)),
                        technology=str(row.get("technology", "5G")).strip(),
                    ))
                db.commit()

            # 3. Subscriptions
            sub_csv = DATA_DIR / "subscriptions.csv"
            if sub_csv.exists():
                df_sub = pd.read_csv(sub_csv).fillna("")
                for _, row in df_sub.iterrows():
                    db.add(Subscription(
                        subscription_id=str(row["subscription_id"]).strip(),
                        customer_id=str(row["customer_id"]).strip(),
                        plan_id=str(row["plan_id"]).strip(),
                        start_date=str(row["start_date"]).strip(),
                        expiry_date=str(row["expiry_date"]).strip(),
                        status=str(row.get("status", "active")).strip(),
                    ))
                db.commit()

            # 4. Usage
            usage_csv = DATA_DIR / "usage.csv"
            if usage_csv.exists():
                df_usage = pd.read_csv(usage_csv).fillna(0)
                for _, row in df_usage.iterrows():
                    db.add(Usage(
                        customer_id=str(row["customer_id"]).strip(),
                        date=str(row["date"]).strip(),
                        data_used_gb=float(row.get("data_used_gb", 0.0)),
                        call_minutes=int(row.get("call_minutes", 0)),
                        sms_count=int(row.get("sms_count", 0)),
                    ))
                db.commit()

            # 5. Bills
            bills_csv = DATA_DIR / "bills.csv"
            if bills_csv.exists():
                df_bills = pd.read_csv(bills_csv).fillna(0)
                for _, row in df_bills.iterrows():
                    db.add(Bill(
                        bill_id=str(row["bill_id"]).strip(),
                        customer_id=str(row["customer_id"]).strip(),
                        billing_date=str(row["billing_date"]).strip(),
                        base_plan=float(row.get("base_plan", 0.0)),
                        addon_charges=float(row.get("addon_charges", 0.0)),
                        roaming_charges=float(row.get("roaming_charges", 0.0)),
                        taxes=float(row.get("taxes", 0.0)),
                        total_amount=float(row.get("total_amount", 0.0)),
                        status=str(row.get("status", "paid")).strip(),
                    ))
                db.commit()

            # 6. Network
            net_csv = DATA_DIR / "network.csv"
            if net_csv.exists():
                df_net = pd.read_csv(net_csv).fillna("")
                for _, row in df_net.iterrows():
                    db.add(Network(
                        tower_id=str(row["tower_id"]).strip(),
                        location=str(row["location"]).strip(),
                        technology=str(row.get("technology", "5G")).strip(),
                        download_mbps=float(row.get("download_mbps", 0.0)),
                        upload_mbps=float(row.get("upload_mbps", 0.0)),
                        latency_ms=float(row.get("latency_ms", 0.0)),
                        packet_loss_percent=float(row.get("packet_loss_percent", 0.0)),
                        signal_strength_dbm=float(row.get("signal_strength_dbm", -100.0)),
                        active_users=int(row.get("active_users", 0)),
                        status=str(row.get("status", "healthy")).strip(),
                    ))
                db.commit()

            # 7. Outages
            outage_csv = DATA_DIR / "outages.csv"
            if outage_csv.exists():
                df_outage = pd.read_csv(outage_csv).fillna("")
                for _, row in df_outage.iterrows():
                    db.add(Outage(
                        outage_id=str(row["outage_id"]).strip(),
                        tower_id=str(row.get("tower_id", "")).strip(),
                        location=str(row["location"]).strip(),
                        start_time=str(row["start_time"]).strip(),
                        end_time=str(row.get("end_time", "")).strip(),
                        reason=str(row.get("reason", "")).strip(),
                        status=str(row.get("status", "active")).strip(),
                    ))
                db.commit()

            # 8. Tickets
            ticket_csv = DATA_DIR / "tickets.csv"
            if ticket_csv.exists():
                df_ticket = pd.read_csv(ticket_csv).fillna("")
                for _, row in df_ticket.iterrows():
                    db.add(Ticket(
                        ticket_id=str(row["ticket_id"]).strip(),
                        customer_id=str(row["customer_id"]).strip(),
                        category=str(row.get("category", "general")).strip(),
                        description=str(row["description"]).strip(),
                        priority=str(row.get("priority", "medium")).strip(),
                        status=str(row.get("status", "open")).strip(),
                        created_at=str(row.get("created_at", "")).strip(),
                    ))
                db.commit()

            print("[DB] Seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"[DB] Error seeding database: {e}")
    finally:
        db.close()
