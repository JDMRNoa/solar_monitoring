from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


def _hours_clause(hours: Optional[int], alias: str = "r") -> str:
    """Filtra por las últimas N horas relativas al dato más reciente en la DB.
    Usa MAX(ts) en lugar de NOW() para que funcione con datos históricos/simulados.
    """
    if hours:
        return (
            f"AND {alias}.ts >= "
            f"(SELECT MAX(ts) FROM solar_readings) - INTERVAL '{hours} hours'"
        )
    return ""


def fetch_summary(db: Session, hours: int = None):
    query = text(f"""
        SELECT
            COUNT(r.id)                                          AS total_readings,
            AVG(r.power_ac_kw)                                   AS avg_power,
            MAX(r.power_ac_kw)                                   AS max_power,
            COUNT(p.id) FILTER (WHERE p.fault_pred = 1)          AS total_faults,
            MAX(p.fault_proba)                                   AS max_fault_proba,
            MAX(r.ts)                                            AS last_ts
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE 1=1 {_hours_clause(hours)}
    """)
    result = db.execute(query).mappings().first()
    return dict(result) if result else {}


def fetch_summary_by_plant(db: Session, plant_id: int, hours: int = None):
    query = text(f"""
        SELECT
            COUNT(r.id)                                          AS total_readings,
            AVG(r.power_ac_kw)                                   AS avg_power,
            MAX(r.power_ac_kw)                                   AS max_power,
            COUNT(p.id) FILTER (WHERE p.fault_pred = 1)          AS total_faults,
            MAX(p.fault_proba)                                   AS max_fault_proba,
            MAX(r.ts)                                            AS last_ts
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE r.plant_id = :plant_id {_hours_clause(hours)}
    """)
    result = db.execute(query, {"plant_id": plant_id}).mappings().first()
    return dict(result) if result else {}


def fetch_alerts(db: Session, min_proba: float = 0.3, hours: int = None):
    query = text(f"""
        SELECT
            p.id,
            r.ts,
            r.plant_id,
            p.fault_proba,
            p.fault_pred,
            p.expected_power_ac_kw,
            p.power_residual_kw,
            p.model_version,
            p.created_at
        FROM ai_predictions p
        JOIN solar_readings r ON r.id = p.reading_id
        WHERE p.fault_pred = 1
          AND p.fault_proba >= :min_proba
          {_hours_clause(hours)}
        ORDER BY p.created_at DESC
        LIMIT 20
    """)
    result = db.execute(query, {"min_proba": min_proba}).mappings().all()
    return [dict(row) for row in result]


def fetch_alerts_by_plant(db: Session, plant_id: int, min_proba: float = 0.3, hours: int = None):
    query = text(f"""
        SELECT
            p.id,
            r.ts,
            r.plant_id,
            p.fault_proba,
            p.fault_pred,
            p.expected_power_ac_kw,
            p.power_residual_kw,
            p.model_version,
            p.created_at
        FROM ai_predictions p
        JOIN solar_readings r ON r.id = p.reading_id
        WHERE p.fault_pred = 1
          AND r.plant_id = :plant_id
          AND p.fault_proba >= :min_proba
          {_hours_clause(hours)}
        ORDER BY p.created_at DESC
        LIMIT 20
    """)
    result = db.execute(query, {"plant_id": plant_id, "min_proba": min_proba}).mappings().all()
    return [dict(row) for row in result]


def fetch_timeseries(db: Session, hours: int = None, limit: int = 2000):
    query = text(f"""
        SELECT
            r.ts,
            r.plant_id,
            r.power_ac_kw,
            p.expected_power_ac_kw,
            p.power_residual_kw,
            p.fault_proba
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE 1=1 {_hours_clause(hours)}
        ORDER BY r.ts
        LIMIT :limit
    """)
    result = db.execute(query, {"limit": limit}).mappings().all()
    return [dict(row) for row in result]


def fetch_timeseries_by_plant(db: Session, plant_id: int, hours: int = None, limit: int = 2000):
    query = text(f"""
        SELECT
            r.ts,
            r.plant_id,
            r.power_ac_kw,
            p.expected_power_ac_kw,
            p.power_residual_kw,
            p.fault_proba
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE r.plant_id = :plant_id {_hours_clause(hours)}
        ORDER BY r.ts DESC
        LIMIT :limit
    """)
    result = db.execute(query, {"plant_id": plant_id, "limit": limit}).mappings().all()
    rows = [dict(row) for row in result]
    return list(reversed(rows))