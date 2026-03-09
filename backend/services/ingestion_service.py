from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.orm import Session

from backend.ml.registry import predict_batch
from backend.repositories.readings_repository import insert_batch_readings, insert_batch_predictions
from backend.services.event_bus import publish

import pandas as pd



def _build_live_event(readings: List[Dict[str, Any]], predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Construye el payload SSE que recibe el frontend.
    Incluye datos de clima (_meta) + predicciones ML por planta.
    """
    by_inverter: Dict[str, Any] = {}

    for r, pred in zip(readings, predictions):
        pid = r.get("plant_id")
        inv_id = r.get("inverter_id")
        meta = r.get("_meta", {}) or {}

        by_inverter[inv_id] = {
            "plant_id":            pid,
            "inverter_id":         inv_id,
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

    return {"inverters": list(by_inverter.values())}


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

    # Solo predecir durante el día — igual que en entrenamiento (irradiance > 20)
    _ZERO_PRED = {"expected_power_ac_kw": 0.0, "power_residual_kw": 0.0,
                  "fault_proba": 0.0, "fault_pred": 0}

    day_mask = df["irradiance_wm2"].fillna(0) > 20
    predictions: list = [_ZERO_PRED.copy()] * len(readings)

    if day_mask.any():
        df_day = df[day_mask].copy()
        day_preds = predict_batch(df_day)
        day_indices = df.index[day_mask].tolist()
        for i, pred in zip(day_indices, day_preds):
            predictions[i] = pred

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