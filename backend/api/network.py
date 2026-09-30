from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Network, Outage
from backend.schemas import NetworkOut, OutageOut

router = APIRouter(prefix="/api", tags=["Network & Outages"])


@router.get("/network", response_model=List[NetworkOut])
def get_all_network_towers(
    location: Optional[str] = Query(None, description="Optional location filter"),
    db: Session = Depends(get_db),
):
    """
    Retrieve all network towers with optional location query filter.
    """
    query = db.query(Network)
    if location:
        query = query.filter(Network.location.ilike(location.strip()))
    return query.all()


@router.get("/network/live/opencellid")
def get_live_opencellid_towers(
    city: Optional[str] = Query(None, description="City name (e.g. Kolkata, Delhi, London)"),
    lat: Optional[float] = Query(None, description="Latitude coordinate"),
    lon: Optional[float] = Query(None, description="Longitude coordinate"),
):
    """
    Fetch real live cell towers directly from OpenCellID global database.
    Requires user permission or city selection.
    """
    from backend.opencellid_service import get_real_towers, get_city_towers

    if lat is not None and lon is not None:
        return get_real_towers(lat=lat, lon=lon)
    if city:
        return get_city_towers(city_name=city)
    return get_city_towers(city_name="Kolkata")


@router.get("/network/{location}", response_model=List[NetworkOut])
def get_network_by_location(location: str, db: Session = Depends(get_db)):
    """
    Retrieve all network towers for a specific geographic location (e.g. Kolkata).
    """
    towers = (
        db.query(Network)
        .filter(Network.location.ilike(location.strip()))
        .all()
    )
    if not towers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No network towers found for location {location}",
        )
    return towers


@router.get("/outages", response_model=List[OutageOut])
def get_outages(
    location: Optional[str] = Query(None, description="Optional location filter"),
    status_filter: Optional[str] = Query("active", alias="status", description="Outage status: active/resolved/all"),
    db: Session = Depends(get_db),
):
    """
    Retrieve network outages with optional location and status filtering.
    """
    query = db.query(Outage)

    if location:
        query = query.filter(Outage.location.ilike(location.strip()))

    if status_filter and status_filter.lower() != "all":
        query = query.filter(Outage.status.ilike(status_filter.strip()))

    outages = query.all()
    return outages
