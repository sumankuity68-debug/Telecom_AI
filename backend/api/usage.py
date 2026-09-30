import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Usage, Customer, User
from backend.schemas import UsageOut
from backend.dependencies import get_optional_current_user, verify_customer_access

router = APIRouter(tags=["Usage"])


def check_usage_isolation(customer_id: str, current_user: Optional[User]):
    enforce_auth = os.getenv("ENFORCE_CUSTOMER_AUTH", "false").lower() in ("true", "1")
    if enforce_auth and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access usage data",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if current_user:
        verify_customer_access(customer_id, current_user)


@router.get("/api/usage/{customer_id}", response_model=List[UsageOut])
def get_usage_by_customer_id(
    customer_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve network and call usage history for a customer.
    """
    check_usage_isolation(customer_id, current_user)
    customer = db.query(Customer).filter(Customer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {customer_id} was not found",
        )

    usage_records = (
        db.query(Usage)
        .filter(Usage.customer_id == customer_id.upper())
        .order_by(Usage.date.desc())
        .all()
    )
    return usage_records
