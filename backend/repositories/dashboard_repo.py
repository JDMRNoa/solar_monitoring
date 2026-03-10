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


def _bucket_minutes(hours: Optional[int]) -> int:
    """
    Devuelve el tamaño del bucket de agregación en minutos según el rango.
    Apunta a ~300 puntos por gráfica para que se vea limpio.
      ≤ 6h   →  1 min  (datos detallados, pocos puntos)
      ≤ 12h  →  3 min
      ≤ 24h  →  5 min
      ≤ 48h  → 10 min
      ≤ 168h →  30 min  (7 días)
      ≤ 720h →  2h      (30 días)
      >  720h →  6h      (todo)
    """
    if not hours:
        return 360  # "Todo" → buckets de 6h
    if hours <= 6:    return 1
    if hours <= 12:   return 3
    if hours <= 24:   return 5
    if hours <= 48:   return 10
    if hours <= 168:  return 30
    if hours <= 720:  return 120
    return 360


def fetch_summary(db: Session, hours: int = None):
    query = text(f"""
        WITH plant_ts AS (
            SELECT
                r.plant_id, r.ts,
                SUM(r.power_ac_kw) AS total_power,
                MAX(p.fault_pred) AS has_fault,
                MAX(p.fault_proba) AS max_proba
            FROM solar_readings r
            LEFT JOIN ai_predictions p ON p.reading_id = r.id
            WHERE 1=1 {_hours_clause(hours)}
            GROUP BY r.plant_id, r.ts
        )
        SELECT
            COUNT(*)                                             AS total_readings,
            AVG(total_power)                                     AS avg_power,
            MAX(total_power)                                     AS max_power,
            COUNT(*) FILTER (WHERE has_fault = 1)                AS total_faults,
            MAX(max_proba)                                       AS max_fault_proba,
            MAX(ts)                                              AS last_ts
        FROM plant_ts
    """)
    result = db.execute(query).mappings().first()
    return dict(result) if result else {}


def fetch_summary_by_plant(db: Session, plant_id: int, hours: int = None):
    query = text(f"""
        WITH plant_ts AS (
            SELECT
                r.ts,
                SUM(r.power_ac_kw) AS total_power,
                MAX(p.fault_pred) AS has_fault,
                MAX(p.fault_proba) AS max_proba
            FROM solar_readings r
            LEFT JOIN ai_predictions p ON p.reading_id = r.id
            WHERE r.plant_id = :plant_id {_hours_clause(hours)}
            GROUP BY r.ts
        )
        SELECT
            COUNT(*)                                             AS total_readings,
            AVG(total_power)                                     AS avg_power,
            MAX(total_power)                                     AS max_power,
            COUNT(*) FILTER (WHERE has_fault = 1)                AS total_faults,
            MAX(max_proba)                                       AS max_fault_proba,
            MAX(ts)                                              AS last_ts
        FROM plant_ts
    """)
    result = db.execute(query, {"plant_id": plant_id}).mappings().first()
    return dict(result) if result else {}


def fetch_alerts(db: Session, min_proba: float = 0.3, hours: int = None):
    query = text(f"""
        SELECT
            p.id, r.ts, r.plant_id, r.inverter_id,
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
            p.id, r.ts, r.plant_id, r.inverter_id,
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
    bucket = _bucket_minutes(hours)
    query = text(f"""
        WITH bucketed AS (
            SELECT
                to_timestamp(
                    floor(extract(epoch from r.ts) / ({bucket} * 60)) * ({bucket} * 60)
                ) AS bucket_ts,
                r.plant_id,
                r.ts,
                SUM(r.power_ac_kw) AS ts_power_ac,
                AVG(r.irradiance_wm2) AS ts_irradiance,
                AVG(r.temp_module_c) AS ts_temp,
                SUM(COALESCE(p.expected_power_ac_kw, r.expected_power_ac_kw)) AS ts_expected,
                SUM(COALESCE(p.power_residual_kw, r.power_ac_kw - r.expected_power_ac_kw)) AS ts_residual,
                MAX(p.fault_proba) AS ts_fault_proba
            FROM solar_readings r
            LEFT JOIN ai_predictions p ON p.reading_id = r.id
            WHERE 1=1 {_hours_clause(hours)}
            GROUP BY bucket_ts, r.plant_id, r.ts
        )
        SELECT
            bucket_ts AS ts,
            plant_id,
            AVG(ts_power_ac)    AS power_ac_kw,
            AVG(ts_irradiance)  AS irradiance_wm2,
            AVG(ts_temp)        AS temp_module_c,
            AVG(ts_expected)    AS expected_power_ac_kw,
            AVG(ts_residual)    AS power_residual_kw,
            MAX(ts_fault_proba) AS fault_proba
        FROM bucketed
        GROUP BY bucket_ts, plant_id
        ORDER BY bucket_ts
        LIMIT :limit
    """)
    result = db.execute(query, {"limit": limit}).mappings().all()
    return [dict(row) for row in result]


def fetch_timeseries_by_plant(db: Session, plant_id: int, hours: int = None, limit: int = 2000):
    bucket = _bucket_minutes(hours)
    query = text(f"""
        WITH bucketed AS (
            SELECT
                to_timestamp(
                    floor(extract(epoch from r.ts) / ({bucket} * 60)) * ({bucket} * 60)
                ) AS bucket_ts,
                r.plant_id,
                r.ts,
                SUM(r.power_ac_kw) AS ts_power_ac,
                AVG(r.irradiance_wm2) AS ts_irradiance,
                AVG(r.temp_module_c) AS ts_temp,
                SUM(COALESCE(p.expected_power_ac_kw, r.expected_power_ac_kw)) AS ts_expected,
                SUM(COALESCE(p.power_residual_kw, r.power_ac_kw - r.expected_power_ac_kw)) AS ts_residual,
                MAX(p.fault_proba) AS ts_fault_proba
            FROM solar_readings r
            LEFT JOIN ai_predictions p ON p.reading_id = r.id
            WHERE r.plant_id = :plant_id {_hours_clause(hours)}
            GROUP BY bucket_ts, r.plant_id, r.ts
        )
        SELECT
            bucket_ts AS ts,
            plant_id,
            AVG(ts_power_ac)    AS power_ac_kw,
            AVG(ts_irradiance)  AS irradiance_wm2,
            AVG(ts_temp)        AS temp_module_c,
            AVG(ts_expected)    AS expected_power_ac_kw,
            AVG(ts_residual)    AS power_residual_kw,
            MAX(ts_fault_proba) AS fault_proba
        FROM bucketed
        GROUP BY bucket_ts, plant_id
        ORDER BY bucket_ts DESC
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
            r.inverter_id,
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
                r.inverter_id,
                p.fault_pred,
                p.fault_proba,
                p.fault_type_pred,
                p.fault_type_proba,
                p.power_residual_kw,
                LAG(p.fault_pred) OVER (PARTITION BY r.inverter_id ORDER BY r.ts) AS prev_fault_pred
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