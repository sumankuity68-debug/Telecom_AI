import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    location = Column(String, nullable=False)
    customer_type = Column(String, default="individual")
    account_status = Column(String, default="active")

    subscriptions = relationship("Subscription", back_populates="customer")
    bills = relationship("Bill", back_populates="customer")
    usage_records = relationship("Usage", back_populates="customer")


class Plan(Base):
    __tablename__ = "plans"

    plan_id = Column(String, primary_key=True, index=True)
    plan_name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    validity_days = Column(Integer, nullable=False)
    data_gb = Column(Float, nullable=False)
    calls = Column(String, default="unlimited")
    sms = Column(Integer, default=100)
    technology = Column(String, default="5G")

    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)
    plan_id = Column(String, ForeignKey("plans.plan_id"), nullable=False)
    start_date = Column(String, nullable=False)
    expiry_date = Column(String, nullable=False)
    status = Column(String, default="active")

    customer = relationship("Customer", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")


class Usage(Base):
    __tablename__ = "usage"

    customer_id = Column(String, ForeignKey("customers.customer_id"), primary_key=True, index=True)
    date = Column(String, primary_key=True, index=True)
    data_used_gb = Column(Float, default=0.0)
    call_minutes = Column(Integer, default=0)
    sms_count = Column(Integer, default=0)

    customer = relationship("Customer", back_populates="usage_records")


class Bill(Base):
    __tablename__ = "bills"

    bill_id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False, index=True)
    billing_date = Column(String, nullable=False)
    base_plan = Column(Float, default=0.0)
    addon_charges = Column(Float, default=0.0)
    roaming_charges = Column(Float, default=0.0)
    taxes = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    status = Column(String, default="pending")

    customer = relationship("Customer", back_populates="bills")


class Network(Base):
    __tablename__ = "network"

    tower_id = Column(String, primary_key=True, index=True)
    location = Column(String, nullable=False, index=True)
    technology = Column(String, default="5G")
    download_mbps = Column(Float, default=0.0)
    upload_mbps = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    packet_loss_percent = Column(Float, default=0.0)
    signal_strength_dbm = Column(Float, default=-100.0)
    active_users = Column(Integer, default=0)
    status = Column(String, default="healthy")


class Outage(Base):
    __tablename__ = "outages"

    outage_id = Column(String, primary_key=True, index=True)
    tower_id = Column(String, index=True)
    location = Column(String, nullable=False, index=True)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=True)
    reason = Column(String, nullable=False)
    status = Column(String, default="active", index=True)


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id = Column(String, primary_key=True, index=True)
    customer_id = Column(String, nullable=False, index=True)
    category = Column(String, default="general")
    description = Column(Text, nullable=False)
    priority = Column(String, default="medium")
    status = Column(String, default="open", index=True)
    created_at = Column(String, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    customer_id = Column(String, nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String, default="success")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
