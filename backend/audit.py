import datetime
from typing import Optional
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import AuditLog


def record_audit_log(
    customer_id: Optional[str],
    action: str,
    details: str,
    status: str = "success",
    username: Optional[str] = None,
    db: Optional[Session] = None,
) -> AuditLog:
    """
    Persist state-changing action audit log.
    Captures: Who (username), What action, Which customer, Details, When, and Status.
    """
    user_str = f" [User: {username}]" if username else ""
    full_details = f"{details}{user_str}"

    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        log_entry = AuditLog(
            customer_id=customer_id.upper() if customer_id else None,
            action=action.upper(),
            details=full_details,
            status=status.lower(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        db.rollback()
        print(f"[AUDIT LOG ERROR] Failed to record audit log: {e}")
        return None
    finally:
        if close_session:
            db.close()
