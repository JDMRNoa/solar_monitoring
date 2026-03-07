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


def get_fault_packages(
    db: Session,
    plant_id: int,
    hours: int = None,
    min_proba: float = 0.3,
    gap_minutes: int = 30,
):
    """
    Agrupa fallas consecutivas en paquetes de evento.
    Dos lecturas pertenecen al mismo paquete si el gap entre timestamps <= gap_minutes.

    El paquete incluye fault_type_pred y fault_type_proba del representative_id
    (la lectura con mayor fault_proba del grupo), sin necesitar llamar a /explain.
    """
    rows = dashboard_repo.fetch_raw_faults_by_plant(
        db, plant_id, hours=hours, min_proba=min_proba
    )
    if not rows:
        return []

    packages = []
    current  = None

    for row in rows:
        ts = row["ts"]
        if isinstance(ts, str):
            from datetime import datetime
            ts = datetime.fromisoformat(ts)

        if current is None:
            current = _new_package(row, ts)
        else:
            gap = (ts - current["_last_ts"]).total_seconds() / 60
            if gap <= gap_minutes:
                # Mismo paquete — actualizar si esta lectura tiene mayor proba
                current["end_ts"]   = ts.isoformat()
                current["_last_ts"] = ts
                current["reading_count"] += 1
                if row["fault_proba"] > current["max_fault_proba"]:
                    current["max_fault_proba"]            = row["fault_proba"]
                    current["representative_id"]          = row["id"]
                    current["representative_expected_kw"] = row["expected_power_ac_kw"]
                    current["representative_residual_kw"] = row["power_residual_kw"]
                    current["fault_type_pred"]            = row.get("fault_type_pred")
                    current["fault_type_proba"]           = row.get("fault_type_proba")
            else:
                packages.append(_close_package(current))
                current = _new_package(row, ts)

    if current:
        packages.append(_close_package(current))

    packages.sort(key=lambda p: p["max_fault_proba"], reverse=True)
    return packages


def _new_package(row: dict, ts) -> dict:
    return {
        "start_ts":                   ts.isoformat(),
        "end_ts":                     ts.isoformat(),
        "_last_ts":                   ts,
        "plant_id":                   row["plant_id"],
        "reading_count":              1,
        "max_fault_proba":            row["fault_proba"],
        "representative_id":          row["id"],
        "representative_expected_kw": row["expected_power_ac_kw"],
        "representative_residual_kw": row["power_residual_kw"],
        "model_version":              row["model_version"],
        # Tipo de falla ya disponible sin llamar a /explain
        "fault_type_pred":            row.get("fault_type_pred"),
        "fault_type_proba":           row.get("fault_type_proba"),
    }


def _close_package(pkg: dict) -> dict:
    from datetime import datetime
    start    = datetime.fromisoformat(pkg["start_ts"])
    end      = datetime.fromisoformat(pkg["end_ts"])
    duration = round((end - start).total_seconds() / 60)
    result   = {k: v for k, v in pkg.items() if not k.startswith("_")}
    result["duration_minutes"] = duration
    return result