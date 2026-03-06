from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.services.dashboard_service import get_summary, get_alerts, get_timeseries, get_fault_packages

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

@router.get("/fault-packages")
def fault_packages_endpoint(
    plant_id: int = Query(...),
    hours: int = Query(None),
    min_proba: float = Query(0.3),
    gap_minutes: int = Query(30),
    db: Session = Depends(get_db),
):
    """
    Agrupa fallas consecutivas en paquetes de evento.
    gap_minutes: máximo intervalo entre lecturas para considerarlas la misma falla.
    """
    return {"data": get_fault_packages(db, plant_id=plant_id, hours=hours, min_proba=min_proba, gap_minutes=gap_minutes)}