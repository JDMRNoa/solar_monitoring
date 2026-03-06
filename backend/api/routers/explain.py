# backend/api/routers/explain.py
from __future__ import annotations

import os
import json
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.session import get_db
from backend.ml.registry import get_shap_explainer
from backend.ml.features import build_clf_features

import pandas as pd
import numpy as np
import requests

router = APIRouter(prefix="/explain", tags=["xai"])

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3.5:mini")
CONTEXT_ROWS = 6

# ── Traducciones para el operador ─────────────────────────────────────────────

_FEATURE_LABELS = {
    "irradiance_wm2":       "irradiancia solar",
    "temp_module_c":        "temperatura del módulo",
    "temp_ambient_c":       "temperatura ambiente",
    "temp_delta_c":         "diferencia térmica módulo-ambiente",
    "expected_power_ac_kw": "potencia esperada",
    "power_residual_kw":    "desviación de potencia (real vs esperada)",
    "abs_residual_kw":      "magnitud de la desviación de potencia",
    "delta_power_ac_kw":    "cambio brusco de potencia",
    "delta_irr_wm2":        "cambio brusco de irradiancia",
    "delta_temp_module_c":  "cambio brusco de temperatura del módulo",
    "ac_dc_ratio":          "eficiencia del inversor (ratio AC/DC)",
    "eff_irr_kw_per_wm2":   "eficiencia de conversión irradiancia-potencia",
    "hour":                 "hora del día",
    "minute":               "minuto",
}

_FAULT_TYPE_LABELS = {
    "panel_soiling":     "suciedad en paneles",
    "string_fault":      "falla en string de paneles",
    "pid_effect":        "efecto PID (degradación por voltaje)",
    "grid_disconnect":   "desconexión de red",
    "mppt_failure":      "falla en el seguidor MPPT",
    "partial_shading":   "sombra parcial",
    "inverter_derate":   "limitación del inversor",
    "sensor_flatline":   "sensor sin señal (posible falla de sensor)",
}


# ── Ollama ────────────────────────────────────────────────────────────────────

def _generate_explanation(reading: Dict, top_reasons: Dict, fault_proba: float) -> str:
    fault_type_raw = reading.get("fault_type") or "desconocida"
    fault_type     = _FAULT_TYPE_LABELS.get(fault_type_raw, fault_type_raw)
    plant_id       = reading.get("plant_id", "?")
    residual       = reading.get("power_residual_kw") or 0.0
    power_ac       = reading.get("power_ac_kw") or 0.0
    expected       = reading.get("expected_power_ac_kw") or 0.0

    physical_reasons = {k: v for k, v in top_reasons.items() if k != "plant_id"}
    top3 = list(physical_reasons.items())[:3]

    features_text = "\n".join(
        f"  - {_FEATURE_LABELS.get(k, k)}: {'aumenta' if v > 0 else 'reduce'} el riesgo de falla (impacto {abs(v):.3f})"
        for k, v in top3
    )

    prompt = f"""Eres un técnico experto en mantenimiento de plantas solares fotovoltaicas.
Escribe una explicación clara en español para un operador de planta (no programador) sobre por qué el sistema detectó una posible falla.
Usa máximo 3 oraciones. No menciones "SHAP", "features", ni términos de machine learning.
Sé concreto: menciona qué está pasando físicamente en la planta.

Situación:
- Planta: {plant_id}
- Probabilidad de falla: {fault_proba*100:.1f}%
- Tipo de falla detectada: {fault_type}
- Potencia actual: {power_ac:.1f} kW (se esperaban {expected:.1f} kW, diferencia: {residual:+.1f} kW)
- Factores que más contribuyeron a la alerta:
{features_text}

Responde SOLO con la explicación en lenguaje natural, sin listas ni puntos."""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        top_feat  = _FEATURE_LABELS.get(top3[0][0], top3[0][0]) if top3 else "desconocido"
        direction = "aumentó" if (top3[0][1] > 0 if top3 else False) else "redujo"
        return (
            f"La planta {plant_id} genera {power_ac:.1f} kW pero se esperaban {expected:.1f} kW "
            f"(diferencia: {residual:+.1f} kW). "
            f"El factor principal fue '{top_feat}', que {direction} el riesgo de falla."
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_context_window(db: Session, prediction_id: int, n: int = CONTEXT_ROWS) -> list[Dict]:
    rows = db.execute(text("""
        WITH target AS (
            SELECT r.plant_id, r.ts
            FROM ai_predictions p
            JOIN solar_readings r ON r.id = p.reading_id
            WHERE p.id = :pid
        )
        SELECT
            r.irradiance_wm2, r.temp_ambient_c, r.temp_module_c,
            r.power_ac_kw, r.power_dc_kw, r.energy_daily_kwh,
            r.energy_total_kwh, r.plant_id, r.ts,
            r.label_is_fault, r.fault_type, r.fault_severity,
            p.id                AS prediction_id,
            p.fault_proba,
            p.fault_pred,
            p.expected_power_ac_kw,
            p.power_residual_kw
        FROM solar_readings r
        LEFT JOIN ai_predictions p ON p.reading_id = r.id
        WHERE r.plant_id = (SELECT plant_id FROM target)
          AND r.ts <= (SELECT ts FROM target)
        ORDER BY r.ts DESC
        LIMIT :n
    """), {"pid": prediction_id, "n": n}).mappings().all()
    return [dict(row) for row in reversed(rows)]


def _already_explained(db: Session, prediction_id: int) -> Dict | None:
    row = db.execute(text("""
        SELECT top_reasons, explanation_text
        FROM ai_explanations
        WHERE prediction_id = :pid
        LIMIT 1
    """), {"pid": prediction_id}).mappings().first()
    return dict(row) if row else None


def _save_explanation(db: Session, prediction_id: int, top_reasons: dict, explanation_text: str) -> None:
    db.execute(text("""
        INSERT INTO ai_explanations (prediction_id, top_reasons, explanation_text)
        VALUES (:pid, cast(:tr AS jsonb), :et)
        ON CONFLICT (prediction_id) DO UPDATE
            SET top_reasons      = EXCLUDED.top_reasons,
                explanation_text = EXCLUDED.explanation_text
    """), {
        "pid": prediction_id,
        "tr":  json.dumps(top_reasons),
        "et":  explanation_text,
    })
    db.commit()


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/{prediction_id}")
def explain_prediction(prediction_id: int, db: Session = Depends(get_db)):
    cached = _already_explained(db, prediction_id)
    if cached:
        return {"prediction_id": prediction_id, "cached": True, **cached}

    context = _get_context_window(db, prediction_id, n=CONTEXT_ROWS)
    if not context:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")

    reading = context[-1]

    shap_artifact = get_shap_explainer()
    if shap_artifact is None:
        raise HTTPException(status_code=503, detail="SHAP explainer no disponible — reentrenar modelo")

    explainer      = shap_artifact["explainer"]
    feature_names  = shap_artifact["feature_names"]
    expected_value = shap_artifact["expected_value"]

    df = pd.DataFrame(context)
    df["expected_power_ac_kw"] = df["expected_power_ac_kw"].fillna(0.0)
    df["power_residual_kw"]    = df["power_residual_kw"].fillna(0.0)
    df["abs_residual_kw"]      = df["power_residual_kw"].abs()

    X        = build_clf_features(df)
    X_target = X.iloc[[-1]]

    shap_values = explainer.shap_values(X_target)

    if isinstance(shap_values, list):
        arr = np.array(shap_values[1])
    else:
        arr = np.array(shap_values)
    values = arr.flatten()[-len(feature_names):]

    contributions = {f: round(float(v), 5) for f, v in zip(feature_names, values)}
    physical      = {k: v for k, v in contributions.items() if k != "plant_id"}
    top_reasons   = dict(sorted(physical.items(), key=lambda x: -abs(x[1]))[:8])

    fault_proba      = reading.get("fault_proba") or 0.0
    explanation_text = _generate_explanation(reading, top_reasons, fault_proba)

    _save_explanation(db, prediction_id, top_reasons, explanation_text)

    return {
        "prediction_id":    prediction_id,
        "cached":           False,
        "fault_proba":      fault_proba,
        "expected_value":   expected_value,
        "top_reasons":      top_reasons,
        "explanation_text": explanation_text,
    }