from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.services.dashboard_service import get_summary, get_alerts, get_timeseries

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    db: Session = Depends(get_db),
):
    return get_summary(db, plant_id=plant_id, hours=hours)


@router.get("/alerts")
def alerts_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    min_proba: float = Query(0.3),
    db: Session = Depends(get_db),
):
    return get_alerts(db, plant_id=plant_id, hours=hours, min_proba=min_proba)


@router.get("/timeseries")
def timeseries_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    limit: int = Query(2000),
    db: Session = Depends(get_db),
):
    return get_timeseries(db, plant_id=plant_id, hours=hours, limit=limit)