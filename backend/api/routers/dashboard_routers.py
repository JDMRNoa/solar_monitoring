from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.core.security import get_current_user
from backend.services.dashboard_service import get_summary, get_alerts, get_timeseries, get_fault_packages, get_fault_events

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_summary(db, plant_id=plant_id, hours=hours)


@router.get("/alerts")
def alerts_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    min_proba: float = Query(0.3),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_alerts(db, plant_id=plant_id, hours=hours, min_proba=min_proba)


@router.get("/timeseries")
def timeseries_endpoint(
    plant_id: int = Query(None),
    hours: int = Query(None),
    limit: int = Query(2000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_timeseries(db, plant_id=plant_id, hours=hours, limit=limit)


@router.get("/fault-packages")
def fault_packages_endpoint(
    plant_id: int = Query(...),
    hours: int = Query(None),
    min_proba: float = Query(0.3),
    gap_minutes: int = Query(30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Agrupa lecturas con falla detectada por ML en paquetes de evento.
    gap_minutes: máximo gap entre lecturas para considerarlas el mismo evento.
    """
    return get_fault_packages(
        db, plant_id=plant_id, hours=hours,
        min_proba=min_proba, gap_minutes=gap_minutes,
    )


@router.get("/events")
def events_endpoint(
    plant_id: int = Query(...),
    hours: int = Query(None),
    min_proba: float = Query(0.5),
    limit: int = Query(200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Log de eventos de falla detectados por el ML (transiciones 0→1 y 1→0).
    Fuente: ai_predictions — nunca ground truth del simulador.
    """
    return get_fault_events(db, plant_id=plant_id, hours=hours, min_proba=min_proba, limit=limit)