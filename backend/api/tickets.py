import os
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import pandas as pd

from backend.database import get_db
from backend.models import Ticket, Customer, User
from backend.schemas import TicketCreate, TicketOut
from backend.dependencies import get_optional_current_user, verify_customer_access
from backend.audit import record_audit_log
from backend.rate_limiter import limiter, STATE_CHANGE_RATE_LIMIT
from config import DATA_DIR

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(STATE_CHANGE_RATE_LIMIT)
def create_ticket(
    request: Request,
    ticket_data: TicketCreate,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new support ticket for a customer.
    Supports JWT authorization when token is provided, protecting customer ownership.
    Records creation in the action audit log.
    """
    enforce_auth = os.getenv("ENFORCE_TICKET_AUTH", "false").lower() in ("true", "1")
    if enforce_auth and not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to create support ticket",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Verify customer exists
    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == ticket_data.customer_id.upper())
        .first()
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {ticket_data.customer_id} does not exist",
        )

    # 2. Authorization check if authenticated
    if current_user:
        verify_customer_access(customer.customer_id, current_user)

    # 3. Generate new ticket ID: TELxxx
    count = db.query(Ticket).count() + 1
    ticket_id = f"TEL{count:03d}"

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_ticket = Ticket(
        ticket_id=ticket_id,
        customer_id=customer.customer_id,
        category=ticket_data.category.lower(),
        description=ticket_data.description.strip(),
        priority=ticket_data.priority.lower(),
        status="open",
        created_at=timestamp,
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    # 4. Sync with tickets.csv if it exists
    tickets_csv = DATA_DIR / "tickets.csv"
    if tickets_csv.exists():
        try:
            df_t = pd.read_csv(tickets_csv, dtype=str)
            new_row = {
                "ticket_id": ticket_id,
                "customer_id": customer.customer_id,
                "category": new_ticket.category,
                "description": new_ticket.description,
                "priority": new_ticket.priority,
                "status": "open",
                "created_at": timestamp,
            }
            df_t = pd.concat([df_t, pd.DataFrame([new_row])], ignore_index=True)
            df_t.to_csv(tickets_csv, index=False)
        except Exception as e:
            print(f"[SYNC NOTE] tickets.csv sync warning: {e}")

    # 5. Record in Audit Log
    username = current_user.username if current_user else "system"
    record_audit_log(
        customer_id=customer.customer_id,
        action="TICKET_CREATED",
        details=f"Ticket {ticket_id} created. Priority: {new_ticket.priority}, Category: {new_ticket.category}. Desc: {new_ticket.description}",
        status="success",
        username=username,
        db=db,
    )

    return new_ticket

