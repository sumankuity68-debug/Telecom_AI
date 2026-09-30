import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Customer, Subscription, Plan, Usage, Bill, Ticket, User
from backend.dependencies import get_current_user, get_optional_current_user, verify_customer_access
from backend.audit import record_audit_log
from backend.rate_limiter import limiter, STATE_CHANGE_RATE_LIMIT
from backend.schemas import (
    CustomerOut,
    PlanOut,
    UsageOut,
    BillOut,
    TicketOut,
    PlanChangeRequest,
)

router = APIRouter(prefix="/api/customers", tags=["Customers"])


def check_customer_isolation(customer_id: str, current_user: Optional[User]):
    """
    Check customer isolation: if authenticated, prevent accessing another customer's private data.
    If ENFORCE_CUSTOMER_AUTH is set, require authentication.
    """
    enforce_auth = os.getenv("ENFORCE_CUSTOMER_AUTH", "false").lower() in ("true", "1")
    if enforce_auth and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access customer data",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if current_user:
        verify_customer_access(customer_id, current_user)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve customer profile by ID (e.g. CUST001).
    """
    check_customer_isolation(customer_id, current_user)
    customer = db.query(Customer).filter(Customer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} was not found",
        )
    return customer


@router.get("/{customer_id}/plan", response_model=PlanOut)
def get_customer_plan(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve active subscription and plan details for a customer.
    """
    check_customer_isolation(customer_id, current_user)
    sub = (
        db.query(Subscription)
        .filter(Subscription.customer_id == customer_id.upper())
        .order_by(Subscription.start_date.desc())
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No subscription found for customer {customer_id}",
        )

    plan = db.query(Plan).filter(Plan.plan_id == sub.plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {sub.plan_id} associated with subscription not found",
        )
    return plan


@router.get("/{customer_id}/usage", response_model=List[UsageOut])
def get_customer_usage(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve usage records for a customer.
    """
    check_customer_isolation(customer_id, current_user)
    usage_records = (
        db.query(Usage)
        .filter(Usage.customer_id == customer_id.upper())
        .order_by(Usage.date.desc())
        .all()
    )
    return usage_records


@router.get("/{customer_id}/bill", response_model=BillOut)
def get_customer_bill(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve latest billing record for a customer.
    """
    check_customer_isolation(customer_id, current_user)
    bill = (
        db.query(Bill)
        .filter(Bill.customer_id == customer_id.upper())
        .order_by(Bill.billing_date.desc())
        .first()
    )
    if not bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No billing record found for customer {customer_id}",
        )
    return bill


@router.get("/{customer_id}/tickets", response_model=List[TicketOut])
def get_customer_tickets(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all support tickets filed by a customer.
    """
    check_customer_isolation(customer_id, current_user)
    tickets = (
        db.query(Ticket)
        .filter(Ticket.customer_id == customer_id.upper())
        .order_by(Ticket.created_at.desc())
        .all()
    )
    return tickets


@router.post("/{customer_id}/change-plan")
@limiter.limit(STATE_CHANGE_RATE_LIMIT)
def change_customer_plan(
    request: Request,
    customer_id: str,
    payload: PlanChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    State-changing endpoint: Migrates customer's subscription to a new plan.
    Requires JWT authentication and customer ownership authorization.
    """
    import datetime
    from config import DATA_DIR
    import pandas as pd

    # 1. Authorization: Verify user owns this customer record
    verify_customer_access(customer_id, current_user)

    # 2. Verify Customer Exists
    customer = db.query(Customer).filter(Customer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} does not exist",
        )

    # 3. Verify Target Plan Exists
    new_plan = db.query(Plan).filter(Plan.plan_id == payload.new_plan_id.upper()).first()
    if not new_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan with ID {payload.new_plan_id} not found",
        )

    # 4. Update or Create Active Subscription
    sub = (
        db.query(Subscription)
        .filter(Subscription.customer_id == customer.customer_id)
        .order_by(Subscription.start_date.desc())
        .first()
    )

    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d")
    expiry_date = (now + datetime.timedelta(days=new_plan.validity_days)).strftime("%Y-%m-%d")

    if sub:
        old_plan_id = sub.plan_id
        sub.plan_id = new_plan.plan_id
        sub.start_date = now_str
        sub.expiry_date = expiry_date
        sub.status = "active"
    else:
        old_plan_id = "NONE"
        sub_id = f"SUB{int(datetime.datetime.now(datetime.timezone.utc).timestamp()) % 1000:03d}"
        sub = Subscription(
            subscription_id=sub_id,
            customer_id=customer.customer_id,
            plan_id=new_plan.plan_id,
            start_date=now_str,
            expiry_date=expiry_date,
            status="active",
        )
        db.add(sub)

    db.commit()

    # Sync to subscriptions.csv if present
    sub_csv = DATA_DIR / "subscriptions.csv"
    if sub_csv.exists():
        try:
            df_sub = pd.read_csv(sub_csv, dtype=str)
            mask = df_sub["customer_id"].str.upper() == customer.customer_id.upper()
            if mask.any():
                df_sub.loc[mask, "plan_id"] = new_plan.plan_id
                df_sub.loc[mask, "start_date"] = now_str
                df_sub.loc[mask, "expiry_date"] = expiry_date
                df_sub.loc[mask, "status"] = "active"
            else:
                new_sub_row = {
                    "subscription_id": f"SUB{len(df_sub)+1:03d}",
                    "customer_id": customer.customer_id,
                    "plan_id": new_plan.plan_id,
                    "start_date": now_str,
                    "expiry_date": expiry_date,
                    "status": "active",
                }
                df_sub = pd.concat([df_sub, pd.DataFrame([new_sub_row])], ignore_index=True)
            df_sub.to_csv(sub_csv, index=False)
        except Exception as e:
            print(f"[SYNC NOTE] subscriptions.csv sync warning: {e}")

    # 5. Persist Audit Log
    record_audit_log(
        customer_id=customer.customer_id,
        action="PLAN_CHANGE_COMPLETED",
        details=f"Migrated from {old_plan_id} to {new_plan.plan_id} ({new_plan.plan_name}). Price: ₹{new_plan.price}",
        status="success",
        username=current_user.username,
        db=db,
    )

    return {
        "status": "SUCCESS",
        "action": "CHANGE_PLAN",
        "customer_id": customer.customer_id,
        "previous_plan": old_plan_id,
        "new_plan_id": new_plan.plan_id,
        "new_plan_name": new_plan.plan_name,
        "price": new_plan.price,
        "validity_days": new_plan.validity_days,
        "data_gb": new_plan.data_gb,
        "expiry_date": expiry_date,
        "message": f"Plan successfully changed to {new_plan.plan_name}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

