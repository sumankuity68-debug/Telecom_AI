from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Plan
from backend.schemas import PlanOut

router = APIRouter(prefix="/api/plans", tags=["Plans"])


@router.get("", response_model=List[PlanOut])
def get_plans(
    technology: Optional[str] = Query(None, description="Filter by technology, e.g. 5G or 4G"),
    max_price: Optional[float] = Query(None, description="Filter by maximum price"),
    min_data: Optional[float] = Query(None, description="Filter by minimum data in GB"),
    db: Session = Depends(get_db),
):
    """
    Retrieve all available telecom plans with optional filters.
    """
    query = db.query(Plan)

    if technology:
        query = query.filter(Plan.technology.ilike(f"%{technology}%"))

    if max_price is not None:
        query = query.filter(Plan.price <= max_price)

    if min_data is not None:
        query = query.filter(Plan.data_gb >= min_data)

    plans = query.order_by(Plan.price.asc()).all()
    return plans
