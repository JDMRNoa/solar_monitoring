from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional


def _hours_clause(hours: Optional[int], alias: str = "r") -> str:
    """Filtra por las últimas N horas relativas al dato más reciente en la DB."""
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
            p.id, r.ts, r.plant_id,
            p.fault_proba, p.fault_pred,
            p.expected_power_ac_kw, p.power_residual_kw,
            p.model_version, p.created_at
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
            p.id, r.ts, r.plant_id,
            p.fault_proba, p.fault_pred,
            p.expected_power_ac_kw, p.power_residual_kw,
            p.model_version, p.created_at
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
            r.ts, r.plant_id, r.power_ac_kw,
            r.irradiance_wm2, r.temp_module_c,
            p.expected_power_ac_kw, p.power_residual_kw, p.fault_proba
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
            r.ts, r.plant_id, r.power_ac_kw,
            r.irradiance_wm2, r.temp_module_c,
            p.expected_power_ac_kw, p.power_residual_kw, p.fault_proba
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE r.plant_id = :plant_id {_hours_clause(hours)}
        ORDER BY r.ts DESC
        LIMIT :limit
    """)
    result = db.execute(query, {"plant_id": plant_id, "limit": limit}).mappings().all()
    return list(reversed([dict(row) for row in result]))


def fetch_raw_faults_by_plant(
    db: Session,
    plant_id: int,
    hours: int = None,
    min_proba: float = 0.0,
    limit: int = 5000,
):
    """
    Trae todas las predicciones de falla para agruparlas en paquetes.
    Incluye fault_type_pred y fault_type_proba para mostrar el tipo
    en la tabla sin necesitar llamar a /explain.
    """
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
            p.fault_type_pred,
            p.fault_type_proba,
            p.created_at
        FROM ai_predictions p
        JOIN solar_readings r ON r.id = p.reading_id
        WHERE p.fault_pred = 1
          AND r.plant_id = :plant_id
          AND p.fault_proba >= :min_proba
          {_hours_clause(hours)}
        ORDER BY r.ts ASC
        LIMIT :limit
    """)
    result = db.execute(
        query, {"plant_id": plant_id, "min_proba": min_proba, "limit": limit}
    ).mappings().all()
    return [dict(row) for row in result]


def fetch_fault_events_by_plant(
    db: Session,
    plant_id: int,
    hours: int = None,
    min_proba: float = 0.5,
    limit: int = 200,
) -> list[dict]:
    """
    Retorna eventos de transición detectados por el ML:
    - fault_start: fault_pred pasó de 0 → 1
    - fault_end:   fault_pred pasó de 1 → 0

    Usa LAG() para detectar el cambio de estado sin depender del simulador.
    """
    hours_clause = (
        f"AND r.ts >= (SELECT MAX(ts) FROM solar_readings) - INTERVAL '{hours} hours'"
        if hours else ""
    )
    query = text(f"""
        WITH ranked AS (
            SELECT
                p.id,
                r.ts,
                r.plant_id,
                p.fault_pred,
                p.fault_proba,
                p.fault_type_pred,
                p.fault_type_proba,
                p.power_residual_kw,
                LAG(p.fault_pred) OVER (PARTITION BY r.plant_id ORDER BY r.ts) AS prev_fault_pred
            FROM ai_predictions p
            JOIN solar_readings r ON r.id = p.reading_id
            WHERE r.plant_id = :plant_id
              AND p.fault_proba >= :min_proba
              {hours_clause}
        )
        SELECT *
        FROM ranked
        WHERE (fault_pred = 1 AND (prev_fault_pred = 0 OR prev_fault_pred IS NULL))
           OR (fault_pred = 0 AND prev_fault_pred = 1)
        ORDER BY ts DESC
        LIMIT :limit
    """)
    result = db.execute(query, {
        "plant_id": plant_id,
        "min_proba": min_proba,
        "limit": limit,
    }).mappings().all()
    return [dict(row) for row in result]