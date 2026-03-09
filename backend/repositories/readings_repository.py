from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import text


_INSERT_READING_SQL = text("""
    INSERT INTO solar_readings (
        ts, plant_id, irradiance_wm2, temp_ambient_c, temp_module_c,
        power_ac_kw, power_dc_kw, energy_daily_kwh, energy_total_kwh,
        expected_power_ac_kw,
        label_is_fault, fault_type, fault_severity
    )
    VALUES (
        :ts, :plant_id, :irradiance_wm2, :temp_ambient_c, :temp_module_c,
        :power_ac_kw, :power_dc_kw, :energy_daily_kwh, :energy_total_kwh,
        :expected_power_ac_kw,
        :label_is_fault, :fault_type, :fault_severity
    )
    RETURNING id
""")

# fault_type_pred / fault_type_proba se guardan en ai_predictions
_INSERT_PREDICTION_SQL = text("""
    INSERT INTO ai_predictions (
        reading_id, model_version, expected_power_ac_kw,
        power_residual_kw, fault_proba, fault_pred,
        fault_type_pred, fault_type_proba
    )
    VALUES (
        :reading_id, :model_version, :expected_power_ac_kw,
        :power_residual_kw, :fault_proba, :fault_pred,
        :fault_type_pred, :fault_type_proba
    )
""")


def insert_reading(db: Session, r: Dict[str, Any]) -> int:
    return db.execute(_INSERT_READING_SQL, {
        "ts":                   r["ts"],
        "plant_id":             r["plant_id"],
        "irradiance_wm2":       r.get("irradiance_wm2"),
        "temp_ambient_c":       r.get("temp_ambient_c"),
        "temp_module_c":        r.get("temp_module_c"),
        "power_ac_kw":          r.get("power_ac_kw"),
        "power_dc_kw":          r.get("power_dc_kw"),
        "energy_daily_kwh":     r.get("energy_daily_kwh"),
        "energy_total_kwh":     r.get("energy_total_kwh"),
        "expected_power_ac_kw": r.get("expected_power_ac_kw"),
        "label_is_fault":       r.get("label_is_fault", 0),
        "fault_type":           r.get("fault_type", ""),
        "fault_severity":       r.get("fault_severity", 0),
    }).scalar_one()


def insert_batch_readings(db: Session, rows: List[Dict[str, Any]]) -> List[int]:
    if not rows:
        return []
        
    records = []
    for r in rows:
        records.append({
            "ts":                   r["ts"],
            "plant_id":             r["plant_id"],
            "irradiance_wm2":       r.get("irradiance_wm2"),
            "temp_ambient_c":       r.get("temp_ambient_c"),
            "temp_module_c":        r.get("temp_module_c"),
            "power_ac_kw":          r.get("power_ac_kw"),
            "power_dc_kw":          r.get("power_dc_kw"),
            "energy_daily_kwh":     r.get("energy_daily_kwh"),
            "energy_total_kwh":     r.get("energy_total_kwh"),
            "expected_power_ac_kw": r.get("expected_power_ac_kw"),
            "label_is_fault":       r.get("label_is_fault", 0),
            "fault_type":           r.get("fault_type", ""),
            "fault_severity":       r.get("fault_severity", 0),
        })

    result = db.execute(_INSERT_READING_SQL, records)
    return [row[0] for row in result.fetchall()]


def insert_prediction(db: Session, reading_id: int, pred: Dict[str, Any]) -> None:
    db.execute(_INSERT_PREDICTION_SQL, {
        "reading_id":           reading_id,
        "model_version":        "phys_rf_v1",
        "expected_power_ac_kw": pred["expected_power_ac_kw"],
        "power_residual_kw":    pred["power_residual_kw"],
        "fault_proba":          pred["fault_proba"],
        "fault_pred":           pred["fault_pred"],
        "fault_type_pred":      pred.get("fault_type_pred"),    # None si no hay falla predicha
        "fault_type_proba":     pred.get("fault_type_proba"),   # None si no hay falla predicha
    })


def insert_batch_predictions(db: Session, reading_ids: List[int], predictions: List[Dict[str, Any]]) -> None:
    if not reading_ids or not predictions:
        return
        
    records = []
    for rid, pred in zip(reading_ids, predictions):
        records.append({
            "reading_id":           rid,
            "model_version":        "phys_rf_v1",
            "expected_power_ac_kw": pred["expected_power_ac_kw"],
            "power_residual_kw":    pred["power_residual_kw"],
            "fault_proba":          pred["fault_proba"],
            "fault_pred":           pred["fault_pred"],
            "fault_type_pred":      pred.get("fault_type_pred"),
            "fault_type_proba":     pred.get("fault_type_proba"),
        })
        
    db.execute(_INSERT_PREDICTION_SQL, records)