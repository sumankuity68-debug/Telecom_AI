import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Bill, Customer, User
from backend.schemas import BillOut
from backend.dependencies import get_optional_current_user, verify_customer_access

router = APIRouter(tags=["Billing"])


def check_billing_isolation(customer_id: str, current_user: Optional[User]):
    enforce_auth = os.getenv("ENFORCE_CUSTOMER_AUTH", "false").lower() in ("true", "1")
    if enforce_auth and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access billing data",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if current_user:
        verify_customer_access(customer_id, current_user)


@router.get("/api/billing/{customer_id}", response_model=BillOut)
def get_billing_by_customer_id(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve latest billing record for a customer by ID.
    """
    check_billing_isolation(customer_id, current_user)
    customer = db.query(Customer).filter(Customer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} was not found",
        )

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


@router.get("/api/billing/{customer_id}/all", response_model=List[BillOut])
def get_all_bills_for_customer(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all historical bills for a customer.
    """
    check_billing_isolation(customer_id, current_user)
    bills = (
        db.query(Bill)
        .filter(Bill.customer_id == customer_id.upper())
        .order_by(Bill.billing_date.desc())
        .all()
    )
    return bills
