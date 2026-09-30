from typing import Optional, List
from pydantic import BaseModel, field_validator


# ============================================================
# AUTHENTICATION SCHEMAS
# ============================================================
class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    location: Optional[str] = None
    customer_type: Optional[str] = "individual"
    customer_id: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class OtpSendRequest(BaseModel):
    phone: str


class OtpVerifyRequest(BaseModel):
    phone: str
    otp: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: Optional[str] = None
    username: str


class TokenData(BaseModel):
    username: Optional[str] = None
    customer_id: Optional[str] = None


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    customer_id: Optional[str] = None
    is_active: bool

    @field_validator("phone", mode="before")
    @classmethod
    def coerce_phone(cls, v):
        return str(v) if v is not None else None

    class Config:
        from_attributes = True


# ============================================================
# CUSTOMER SCHEMAS
# ============================================================
class CustomerOut(BaseModel):
    customer_id: str
    name: str
    phone: str
    email: str
    location: str
    customer_type: str
    account_status: str

    @field_validator("phone", mode="before")
    @classmethod
    def coerce_phone(cls, v):
        return str(v) if v is not None else ""

    class Config:
        from_attributes = True


# ============================================================
# PLAN SCHEMAS
# ============================================================
class PlanOut(BaseModel):
    plan_id: str
    plan_name: str
    price: float
    validity_days: int
    data_gb: float
    calls: str
    sms: int
    technology: str

    class Config:
        from_attributes = True


# ============================================================
# SUBSCRIPTION SCHEMAS
# ============================================================
class SubscriptionOut(BaseModel):
    subscription_id: str
    customer_id: str
    plan_id: str
    start_date: str
    expiry_date: str
    status: str
    plan: Optional[PlanOut] = None

    class Config:
        from_attributes = True


# ============================================================
# USAGE SCHEMAS
# ============================================================
class UsageOut(BaseModel):
    customer_id: str
    date: str
    data_used_gb: float
    call_minutes: int
    sms_count: int

    class Config:
        from_attributes = True


# ============================================================
# BILL SCHEMAS
# ============================================================
class BillOut(BaseModel):
    bill_id: str
    customer_id: str
    billing_date: str
    base_plan: float
    addon_charges: float
    roaming_charges: float
    taxes: float
    total_amount: float
    status: str

    class Config:
        from_attributes = True


# ============================================================
# NETWORK & OUTAGE SCHEMAS
# ============================================================
class NetworkOut(BaseModel):
    tower_id: str
    location: str
    technology: str
    download_mbps: float
    upload_mbps: float
    latency_ms: float
    packet_loss_percent: float
    signal_strength_dbm: float
    active_users: int
    status: str

    class Config:
        from_attributes = True


class OutageOut(BaseModel):
    outage_id: str
    tower_id: Optional[str] = None
    location: str
    start_time: str
    end_time: Optional[str] = None
    reason: str
    status: str

    class Config:
        from_attributes = True


# ============================================================
# TICKET SCHEMAS
# ============================================================
class TicketCreate(BaseModel):
    customer_id: str
    category: str = "general"
    description: str
    priority: str = "medium"


class TicketOut(BaseModel):
    ticket_id: str
    customer_id: str
    category: str
    description: str
    priority: str
    status: str
    created_at: str

    class Config:
        from_attributes = True


# ============================================================
# PHASE D ACTION SCHEMAS
# ============================================================
class PlanChangeRequest(BaseModel):
    new_plan_id: str


class RechargeActionRequest(BaseModel):
    customer_id: str
    amount: float
    payment_method: str = "UPI"


# ============================================================
# MOCK API SCHEMAS
# ============================================================
class MockRechargeRequest(BaseModel):
    customer_id: str
    amount: float
    payment_method: str = "card"


class MockChangePlanRequest(BaseModel):
    customer_id: str
    new_plan_id: str

