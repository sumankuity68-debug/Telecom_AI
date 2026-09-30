import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Customer, User
from backend.schemas import RechargeActionRequest
from backend.dependencies import get_current_user, verify_customer_access
from backend.audit import record_audit_log
from backend.rate_limiter import limiter, STATE_CHANGE_RATE_LIMIT

router = APIRouter(prefix="/api/recharge", tags=["Recharge"])


@router.post("")
@limiter.limit(STATE_CHANGE_RATE_LIMIT)
def process_recharge(
    request: Request,
    payload: RechargeActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    State-changing endpoint: Processes a telecom account recharge.
    Explicitly marked as DEMO / MOCK transaction.
    Requires valid JWT and customer ownership verification.
    """
    # 1. Validate Amount
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recharge amount. Amount must be greater than zero.",
        )

    # 2. Authorization: Verify user owns this customer account
    verify_customer_access(payload.customer_id, current_user)

    # 3. Verify Customer Exists
    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == payload.customer_id.upper())
        .first()
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer with ID {payload.customer_id} does not exist",
        )

    # 4. Generate transaction record
    timestamp_now = datetime.datetime.now(datetime.timezone.utc)
    tx_id = f"TXN{int(timestamp_now.timestamp())}"

    # 5. Record in Audit Log
    record_audit_log(
        customer_id=customer.customer_id,
        action="RECHARGE_COMPLETED",
        details=f"Demo recharge of ₹{payload.amount:.2f} processed via {payload.payment_method}. TxID: {tx_id}",
        status="success",
        username=current_user.username,
        db=db,
    )

    return {
        "status": "SUCCESS",
        "action": "RECHARGE",
        "demo_mode": True,
        "transaction_id": tx_id,
        "customer_id": customer.customer_id,
        "amount": payload.amount,
        "payment_method": payload.payment_method,
        "status_code": "COMPLETED",
        "created_at": timestamp_now.isoformat(),
        "message": f"MOCK/DEMO recharge of ₹{payload.amount:.2f} successful. No real currency transferred.",
    }
