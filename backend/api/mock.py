import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Customer, Plan, Subscription, Network, Outage, AuditLog
from backend.schemas import (
    MockRechargeRequest,
    MockChangePlanRequest,
)

router = APIRouter(prefix="/api/mock", tags=["Mock Telecom APIs"])


@router.get("/network/{location}")
def mock_external_network_status(location: str, db: Session = Depends(get_db)):
    """
    Mock external carrier network telemetry feed for a city.
    """
    towers = db.query(Network).filter(Network.location.ilike(location.strip())).all()
    if not towers:
        return {
            "source": "MockCarrierNetworkGateway",
            "location": location,
            "status": "NO_CARRIER_DATA",
            "towers": [],
        }

    return {
        "source": "MockCarrierNetworkGateway",
        "location": location,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "towers_online": len(towers),
        "telemetry": [
            {
                "tower_id": t.tower_id,
                "technology": t.technology,
                "status": t.status,
                "download_mbps": t.download_mbps,
                "upload_mbps": t.upload_mbps,
                "latency_ms": t.latency_ms,
                "packet_loss_percent": t.packet_loss_percent,
                "signal_strength_dbm": t.signal_strength_dbm,
                "active_users": t.active_users,
            }
            for t in towers
        ],
    }


@router.get("/outages")
def mock_external_outages(db: Session = Depends(get_db)):
    """
    Mock external carrier national outage monitoring feed.
    """
    outages = db.query(Outage).all()
    return {
        "source": "MockCarrierNOC",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_active": len([o for o in outages if o.status.lower() == "active"]),
        "outages": [
            {
                "outage_id": o.outage_id,
                "tower_id": o.tower_id,
                "location": o.location,
                "start_time": o.start_time,
                "end_time": o.end_time,
                "reason": o.reason,
                "status": o.status,
            }
            for o in outages
        ],
    }


@router.get("/customer/{customer_id}")
def mock_external_customer_lookup(customer_id: str, db: Session = Depends(get_db)):
    """
    Mock external BSS/OSS carrier subscriber data lookup.
    """
    customer = db.query(Customer).filter(Customer.customer_id == customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Carrier BSS: subscriber {customer_id} not registered",
        )

    sub = (
        db.query(Subscription)
        .filter(Subscription.customer_id == customer.customer_id)
        .order_by(Subscription.start_date.desc())
        .first()
    )

    return {
        "source": "MockCarrierBSS",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "subscriber_id": customer.customer_id,
        "customer": {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "location": customer.location,
            "status": customer.account_status,
        },
        "msisdn": customer.phone,
        "imsi_status": "ACTIVE" if customer.account_status == "active" else "SUSPENDED",
        "active_subscription": sub.subscription_id if sub else None,
        "plan_id": sub.plan_id if sub else None,
    }


@router.post("/recharge")
def mock_recharge(recharge: MockRechargeRequest, db: Session = Depends(get_db)):
    """
    Mock telecom prepaid/postpaid recharge transaction.
    """
    customer = db.query(Customer).filter(Customer.customer_id == recharge.customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {recharge.customer_id} not found",
        )

    tx_id = f"TXN{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"

    # Log in audit table
    log = AuditLog(
        customer_id=customer.customer_id,
        action="RECHARGE",
        details=f"Amount: ₹{recharge.amount}, Payment Method: {recharge.payment_method}, TxID: {tx_id}",
        status="success",
    )
    db.add(log)
    db.commit()

    return {
        "status": "SUCCESS",
        "transaction_id": tx_id,
        "customer_id": customer.customer_id,
        "recharge_amount": recharge.amount,
        "payment_method": recharge.payment_method,
        "message": f"Successfully recharged ₹{recharge.amount} for {customer.customer_id}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.post("/change-plan")
def mock_change_plan(change: MockChangePlanRequest, db: Session = Depends(get_db)):
    """
    Mock telecom tariff migration.
    """
    customer = db.query(Customer).filter(Customer.customer_id == change.customer_id.upper()).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {change.customer_id} not found",
        )

    new_plan = db.query(Plan).filter(Plan.plan_id == change.new_plan_id.upper()).first()
    if not new_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {change.new_plan_id} not found",
        )

    # Update or add subscription
    sub = (
        db.query(Subscription)
        .filter(Subscription.customer_id == customer.customer_id)
        .order_by(Subscription.start_date.desc())
        .first()
    )

    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    expiry_date = (datetime.datetime.now() + datetime.timedelta(days=new_plan.validity_days)).strftime("%Y-%m-%d")

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

    # Log in audit table
    log = AuditLog(
        customer_id=customer.customer_id,
        action="CHANGE_PLAN",
        details=f"Migrated from {old_plan_id} to {new_plan.plan_id} ({new_plan.plan_name})",
        status="success",
    )
    db.add(log)
    db.commit()

    return {
        "status": "SUCCESS",
        "customer_id": customer.customer_id,
        "previous_plan": old_plan_id,
        "new_plan_id": new_plan.plan_id,
        "new_plan_name": new_plan.plan_name,
        "validity_days": new_plan.validity_days,
        "expiry_date": expiry_date,
        "message": f"Plan upgraded to {new_plan.plan_name}",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
