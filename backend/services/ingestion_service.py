from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.ml.registry import predict_batch
from backend.repositories.readings_repository import insert_batch_readings, insert_batch_predictions
from backend.services.event_bus import publish

import pandas as pd


def _enrich_features(df: pd.DataFrame) -> pd.DataFrame:
    X = df.copy()
    X["temp_delta_c"]         = X["temp_module_c"] - X["temp_ambient_c"]
    X["irr_temp_interaction"] = X["irradiance_wm2"] * X["temp_module_c"]
    ts = pd.to_datetime(X["ts"])
    X["hour"]   = ts.dt.hour
    X["minute"] = ts.dt.minute
    X["delta_power_ac_kw"]   = X["power_ac_kw"].diff().fillna(0)
    X["delta_irr_wm2"]       = X["irradiance_wm2"].diff().fillna(0)
    X["delta_temp_module_c"] = X["temp_module_c"].diff().fillna(0)
    X["ac_dc_ratio"]         = X["power_ac_kw"] / X["power_dc_kw"].replace(0, float("nan"))
    X["ac_dc_ratio"]         = X["ac_dc_ratio"].fillna(0)
    X["eff_irr_kw_per_wm2"]  = X["power_ac_kw"] / X["irradiance_wm2"].replace(0, float("nan"))
    X["eff_irr_kw_per_wm2"]  = X["eff_irr_kw_per_wm2"].fillna(0)
    return X


def _build_live_event(readings: List[Dict[str, Any]], predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Construye el payload SSE que recibe el frontend.
    Incluye datos de clima (_meta) + predicciones ML por planta.
    """
    by_plant: Dict[int, Any] = {}

    for r, pred in zip(readings, predictions):
        pid = r.get("plant_id")
        meta = r.get("_meta", {}) or {}

        by_plant[pid] = {
            "plant_id":            pid,
            "ts":                  r.get("ts"),
            # Clima (del _meta del simulador)
            "cloud_cover":         meta.get("cloud_cover"),
            "wind_ms":             meta.get("wind_ms"),
            "rain_active":         meta.get("rain_active", False),
            "soiling":             meta.get("soiling"),
            "degradation_pct":     meta.get("degradation_pct"),
            "elevation_deg":       meta.get("elevation_deg"),
            # Lectura
            "irradiance_wm2":      r.get("irradiance_wm2"),
            "temp_ambient_c":      r.get("temp_ambient_c"),
            "temp_module_c":       r.get("temp_module_c"),
            "power_ac_kw":         r.get("power_ac_kw"),
            "energy_daily_kwh":    r.get("energy_daily_kwh"),
            "label_is_fault":      r.get("label_is_fault", 0),
            "fault_type":          r.get("fault_type", ""),
            "fault_severity":      r.get("fault_severity", 0),
            # ML
            "fault_proba":         pred.get("fault_proba"),
            "fault_pred":          pred.get("fault_pred"),
            "expected_power_ac_kw": pred.get("expected_power_ac_kw"),
            "power_residual_kw":   pred.get("power_residual_kw"),
        }

    return {"plants": list(by_plant.values())}


def ingest_batch_service(payload, db: Session) -> Dict[str, Any]:
    """
    1) Inserta solar_readings
    2) Ejecuta modelos ML
    3) Inserta ai_predictions
    4) Publica evento SSE con clima + predicciones (sin persistir _meta)
    """
    readings: List[Dict[str, Any]] = [dict(r) for r in payload.readings]

    if not readings:
        return {
            "status": "no_data",
            "inserted_readings": 0,
            "inserted_predictions": 0,
        }

    reading_ids = insert_batch_readings(db, readings)

    df = pd.DataFrame(readings)
    features_df = _enrich_features(df)
    predictions = predict_batch(features_df)

    insert_batch_predictions(db, reading_ids, predictions)
    db.commit()

    # Broadcast SSE — no bloquea, fire-and-forget
    try:
        publish(_build_live_event(readings, predictions))
    except Exception:
        pass  # SSE nunca debe romper la ingesta

    return {
        "status": "ok",
        "inserted_readings": len(reading_ids),
        "inserted_predictions": len(reading_ids),
    }