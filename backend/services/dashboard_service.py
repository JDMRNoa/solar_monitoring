from sqlalchemy.orm import Session
from backend.repositories import dashboard_repo


def get_summary(db: Session, plant_id: int = None, hours: int = None):
    if plant_id:
        data = dashboard_repo.fetch_summary_by_plant(db, plant_id, hours=hours)
    else:
        data = dashboard_repo.fetch_summary(db, hours=hours)

    if not data:
        return {
            "total_readings":  0,
            "avg_power":       0,
            "max_power":       0,
            "total_faults":    0,
            "max_fault_proba": None,
            "last_ts":         None,
        }

    return data


def get_alerts(db: Session, plant_id: int = None, hours: int = None, min_proba: float = 0.3):
    if plant_id:
        return dashboard_repo.fetch_alerts_by_plant(db, plant_id, min_proba=min_proba, hours=hours)
    return dashboard_repo.fetch_alerts(db, hours=hours)


def get_timeseries(db: Session, plant_id: int = None, hours: int = None, limit: int = 2000):
    if plant_id:
        series = dashboard_repo.fetch_timeseries_by_plant(db, plant_id, hours=hours, limit=limit)
    else:
        series = dashboard_repo.fetch_timeseries(db, hours=hours, limit=limit)
    return {"data": series}