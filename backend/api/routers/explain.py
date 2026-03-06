# backend/api/routers/explain.py
from __future__ import annotations

import os
import json
from typing import Dict, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.session import get_db
from backend.ml.registry import get_shap_explainer, predict_fault_type
from backend.ml.features import build_clf_features

import pandas as pd
import numpy as np
import requests

router = APIRouter(prefix="/explain", tags=["xai"])

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3.5:mini")
CONTEXT_ROWS = 6

# ── Labels y playbook ─────────────────────────────────────────────────────────

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
    "panel_soiling":    "Suciedad en paneles",
    "string_fault":     "Falla en string de paneles",
    "pid_effect":       "Efecto PID (degradación por voltaje)",
    "grid_disconnect":  "Desconexión de red",
    "mppt_failure":     "Falla en seguidor MPPT",
    "partial_shading":  "Sombra parcial",
    "inverter_derate":  "Limitación del inversor",
    "sensor_flatline":  "Sensor sin señal",
    "unknown":          "Tipo indeterminado",
}

# Fuentes: IEA PVPS T13, SMA Fault Diagnosis Guide, NREL O&M Best Practices
_FAULT_PLAYBOOK = {
    "inverter_derate": {
        "causas": "Sobrecalentamiento del inversor, límite de potencia activo, ventilación obstruida o temperatura ambiente muy alta.",
        "acciones": [
            "Verificar temperatura interna del inversor (umbral típico: 70°C).",
            "Limpiar o revisar filtros de ventilación del inversor.",
            "Comprobar si hay alarmas activas en el display del inversor.",
            "Si la temperatura ambiente supera 40°C, considerar ventilación adicional.",
        ],
    },
    "string_fault": {
        "causas": "Diodo de bypass activado, módulo dañado, conexión suelta en caja de strings, o cable cortado.",
        "acciones": [
            "Medir la corriente de cada string con pinza amperimétrica.",
            "Revisar cajas de strings en busca de bornes sueltos o quemados.",
            "Hacer termografía infrarroja para localizar módulos con punto caliente.",
            "Verificar continuidad de cables DC entre string y caja de combinación.",
        ],
    },
    "grid_disconnect": {
        "causas": "Corte en el suministro de red, disparo del interruptor AC, falla en la protección de anti-isla, o sobretensión de red.",
        "acciones": [
            "Verificar si hay corte de suministro en la zona.",
            "Revisar el interruptor general AC en el tablero de conexión a red.",
            "Comprobar parámetros de tensión y frecuencia de red en el inversor.",
            "Revisar relé de protección de anti-isla y configuración de límites.",
        ],
    },
    "mppt_failure": {
        "causas": "Algoritmo MPPT desorientado por cambios bruscos de irradiancia, firmware desactualizado, o sensor de referencia descalibrado.",
        "acciones": [
            "Revisar historial de eventos del inversor en la última hora.",
            "Comparar curva I-V del string con curva de referencia.",
            "Actualizar firmware del inversor si hay versión disponible.",
            "Reiniciar el inversor fuera del horario pico (antes del amanecer).",
        ],
    },
    "partial_shading": {
        "causas": "Sombra de estructura cercana, vegetación, edificios, ensuciamiento puntual o ave posada sobre módulos.",
        "acciones": [
            "Inspección visual de la superficie de paneles (sombras, objetos).",
            "Revisar si hay crecimiento de vegetación cerca de la instalación.",
            "Verificar si la sombra es recurrente en el mismo horario (sombra estructural).",
            "Considerar optimizadores de potencia si la sombra es crónica.",
        ],
    },
    "panel_soiling": {
        "causas": "Acumulación progresiva de polvo, arena (en zonas áridas), excrementos de aves o lodo por lluvia.",
        "acciones": [
            "Inspeccionar visualmente la superficie de los módulos.",
            "Programar limpieza con agua desmineralizada y paño suave.",
            "En zonas con polvo Saháreo, aumentar frecuencia de limpieza a cada 2 semanas.",
            "Revisar sistema de limpieza automática si existe.",
        ],
    },
    "pid_effect": {
        "causas": "Degradación acumulativa por alto voltaje de polarización, humedad elevada, o deficiencia en el encapsulante del módulo.",
        "acciones": [
            "Medir resistencia de aislamiento de strings (valor normal > 40 MΩ).",
            "Verificar si el inversor tiene función anti-PID activa.",
            "Revisar humedad relativa en el sitio (PID se acelera con HR > 85%).",
            "Contactar fabricante si la degradación supera el 5% anual.",
        ],
    },
    "sensor_flatline": {
        "causas": "Sensor de irradiancia o temperatura desconectado, cable dañado, datalogger sin comunicación, o sensor saturado.",
        "acciones": [
            "Verificar conexión física del sensor de irradiancia (piranómetro).",
            "Comprobar si el datalogger/RTU registra datos en tiempo real.",
            "Limpiar la cúpula del piranómetro si está sucia.",
            "Comparar lectura local con datos meteorológicos de la zona.",
        ],
    },
    "unknown": {
        "causas": "Comportamiento anómalo no clasificado. Puede ser combinación de factores o condición no vista en entrenamiento.",
        "acciones": [
            "Revisar el registro de eventos del inversor de las últimas 24 horas.",
            "Comparar producción real con plantas similares en la misma zona.",
            "Verificar que todos los sensores reportan valores coherentes.",
            "Escalar a técnico especializado si la anomalía persiste más de 2 horas.",
        ],
    },
}

# ── Fallback por reglas (cuando el modelo no está entrenado aún) ──────────────

def _infer_fault_type_rules(top_reasons: Dict, reading: Dict) -> str:
    """Heurísticas físicas como fallback cuando fault_type_clf no existe."""
    top_features = set(list(top_reasons.keys())[:4])
    residual = reading.get("power_residual_kw") or 0.0
    power_ac = reading.get("power_ac_kw") or 0.0
    expected = reading.get("expected_power_ac_kw") or 1.0

    if expected > 5 and power_ac < 0.5:
        return "grid_disconnect"
    if "ac_dc_ratio" in top_features and top_reasons.get("ac_dc_ratio", 0) > 0:
        return "inverter_derate"
    if "delta_irr_wm2" in top_features and "eff_irr_kw_per_wm2" in top_features:
        return "mppt_failure"
    if "eff_irr_kw_per_wm2" in top_features and residual < -0.05 * expected:
        return "panel_soiling"
    if "power_residual_kw" in top_features or "abs_residual_kw" in top_features:
        loss_pct = abs(residual) / max(expected, 1)
        if loss_pct > 0.3:
            return "string_fault"
        if loss_pct > 0.05:
            return "partial_shading"
    if "delta_temp_module_c" in top_features and "temp_delta_c" in top_features:
        return "pid_effect"
    if "delta_power_ac_kw" in top_features and "delta_irr_wm2" not in top_features:
        return "sensor_flatline"
    return "unknown"


# ── Ollama ────────────────────────────────────────────────────────────────────

def _generate_explanation(
    reading: Dict,
    top_reasons: Dict,
    fault_proba: float,
    inferred_type: str,
    reading_count: int = 1,
    duration_minutes: int = 0,
) -> str:
    plant_id = reading.get("plant_id", "?")
    residual = reading.get("power_residual_kw") or 0.0
    power_ac = reading.get("power_ac_kw") or 0.0
    expected = reading.get("expected_power_ac_kw") or 0.0

    type_label = _FAULT_TYPE_LABELS.get(inferred_type, inferred_type)
    playbook   = _FAULT_PLAYBOOK.get(inferred_type, _FAULT_PLAYBOOK["unknown"])

    physical_reasons = {k: v for k, v in top_reasons.items() if k != "plant_id"}
    top3 = list(physical_reasons.items())[:3]

    features_text = "\n".join(
        f"  - {_FEATURE_LABELS.get(k, k)}: {'aumenta' if v > 0 else 'reduce'} el riesgo (impacto {abs(v):.3f})"
        for k, v in top3
    )

    if reading_count > 1 and duration_minutes > 0:
        duracion_str = f"{duration_minutes} minutos" if duration_minutes < 60 else f"{duration_minutes // 60}h {duration_minutes % 60}min"
        paquete_ctx  = f"- Duración del evento: {duracion_str} ({reading_count} lecturas consecutivas en falla)"
    elif reading_count > 1:
        paquete_ctx = f"- Lecturas consecutivas en falla: {reading_count}"
    else:
        paquete_ctx = "- Evento puntual (1 lectura)"

    acciones_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(playbook["acciones"]))

    prompt = f"""Eres un técnico experto en mantenimiento de plantas solares fotovoltaicas.
Tu tarea es explicar en español claro (para un operador de planta, no un programador) por qué el sistema detectó una posible falla, y qué debe hacer.

INSTRUCCIONES:
- Escribe exactamente DOS secciones separadas por la línea "---"
- Sección 1 (ANÁLISIS): máximo 3 oraciones describiendo qué está pasando físicamente. No menciones "SHAP", "features", ni "machine learning".
- Sección 2 (RECOMENDACIÓN): máximo 3 oraciones con acciones concretas y urgentes para el operador.

DATOS DEL EVENTO:
- Planta: {plant_id}
- Probabilidad de falla: {fault_proba*100:.1f}%
- Tipo de falla detectado: {type_label}
- Causas típicas: {playbook["causas"]}
- Potencia actual: {power_ac:.1f} kW (se esperaban {expected:.1f} kW, diferencia: {residual:+.1f} kW)
{paquete_ctx}
- Factores físicos que más contribuyeron:
{features_text}

ACCIONES DE REFERENCIA:
{acciones_text}

Responde SOLO con las dos secciones. Primera línea: el análisis. Luego exactamente "---". Luego la recomendación."""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        top_feat  = _FEATURE_LABELS.get(top3[0][0], top3[0][0]) if top3 else "desconocido"
        direction = "aumentó" if (top3[0][1] > 0 if top3 else False) else "redujo"
        pkg_info  = f" El evento duró {duration_minutes} min ({reading_count} lecturas)." if reading_count > 1 else ""
        analisis  = (
            f"La planta {plant_id} genera {power_ac:.1f} kW pero se esperaban {expected:.1f} kW "
            f"(diferencia: {residual:+.1f} kW).{pkg_info} "
            f"El factor principal fue '{top_feat}', que {direction} el riesgo de falla."
        )
        recomendacion = playbook["acciones"][0] + " " + playbook["acciones"][1]
        return f"{analisis}\n---\n{recomendacion}"


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
        SELECT
            e.top_reasons,
            e.explanation_text,
            p.fault_proba,
            s.expected_value
        FROM ai_explanations e
        JOIN ai_predictions p ON p.id = e.prediction_id
        LEFT JOIN (
            SELECT AVG(fault_proba) AS expected_value
            FROM ai_predictions WHERE fault_pred = 0
        ) s ON true
        WHERE e.prediction_id = :pid
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
    """), {"pid": prediction_id, "tr": json.dumps(top_reasons), "et": explanation_text})
    db.commit()


def _build_response(
    prediction_id: int,
    cached: bool,
    fault_proba: float | None,
    expected_value: float | None,
    top_reasons: dict,
    explanation_text: str,
    fault_type_result: dict | None,
    reading_count: int,
    duration_minutes: int,
) -> dict:
    """Construye el dict de respuesta unificado."""
    parts = explanation_text.split("\n---\n", 1) if explanation_text else ["", ""]

    # Determinar tipo: modelo > fallback ya aplicado
    inferred_type = (fault_type_result or {}).get("fault_type", "unknown")
    confidence    = (fault_type_result or {}).get("confidence")
    all_probas    = (fault_type_result or {}).get("all_probas")
    source        = "model" if fault_type_result else "rules"

    return {
        "prediction_id":       prediction_id,
        "cached":              cached,
        "fault_proba":         fault_proba,
        "expected_value":      expected_value,
        "top_reasons":         top_reasons,
        "inferred_fault_type": inferred_type,
        "fault_type_label":    _FAULT_TYPE_LABELS.get(inferred_type, inferred_type),
        "fault_type_source":   source,           # "model" | "rules"
        "fault_type_confidence": confidence,     # None si viene de reglas
        "fault_type_all_probas": all_probas,     # None si viene de reglas
        "analysis_text":       parts[0].strip() if parts[0] else "",
        "recommendation_text": parts[1].strip() if len(parts) > 1 else "",
        "explanation_text":    explanation_text,
        "reading_count":       reading_count,
        "duration_minutes":    duration_minutes,
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/{prediction_id}")
def explain_prediction(
    prediction_id:    int,
    reading_count:    int = Query(1, description="Lecturas consecutivas en falla del paquete"),
    duration_minutes: int = Query(0, description="Duración del evento en minutos"),
    db: Session = Depends(get_db),
):
    # ── Cache hit ──────────────────────────────────────────────────────────
    cached_data = _already_explained(db, prediction_id)
    if cached_data:
        top_reasons = cached_data.get("top_reasons") or {}

        # Re-computar tipo de falla desde el modelo (puede haber mejorado)
        context_rows = _get_context_window(db, prediction_id, n=CONTEXT_ROWS)
        reading      = context_rows[-1] if context_rows else {}

        fault_type_result = None
        if context_rows:
            df = pd.DataFrame(context_rows)
            df["expected_power_ac_kw"] = df["expected_power_ac_kw"].fillna(0.0)
            df["power_residual_kw"]    = df["power_residual_kw"].fillna(0.0)
            df["abs_residual_kw"]      = df["power_residual_kw"].abs()
            X = build_clf_features(df)
            X_target = X.iloc[[-1]]
            fault_type_result = predict_fault_type(X_target)

        if fault_type_result is None:
            inferred = _infer_fault_type_rules(top_reasons, reading)
            fault_type_result = {"fault_type": inferred}

        return _build_response(
            prediction_id   = prediction_id,
            cached          = True,
            fault_proba     = cached_data.get("fault_proba"),
            expected_value  = cached_data.get("expected_value"),
            top_reasons     = top_reasons,
            explanation_text= cached_data.get("explanation_text", ""),
            fault_type_result = fault_type_result,
            reading_count   = reading_count,
            duration_minutes= duration_minutes,
        )

    # ── Calcular SHAP ──────────────────────────────────────────────────────
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

    # ── Clasificar tipo de falla ──────────────────────────────────────────
    fault_type_result = predict_fault_type(X_target)
    if fault_type_result is None:
        # Fallback a reglas si el modelo aún no existe
        inferred = _infer_fault_type_rules(top_reasons, reading)
        fault_type_result = {"fault_type": inferred}

    inferred_type = fault_type_result["fault_type"]

    fault_proba      = reading.get("fault_proba") or 0.0
    explanation_text = _generate_explanation(
        reading, top_reasons, fault_proba,
        inferred_type, reading_count, duration_minutes,
    )

    _save_explanation(db, prediction_id, top_reasons, explanation_text)

    return _build_response(
        prediction_id    = prediction_id,
        cached           = False,
        fault_proba      = fault_proba,
        expected_value   = expected_value,
        top_reasons      = top_reasons,
        explanation_text = explanation_text,
        fault_type_result= fault_type_result,
        reading_count    = reading_count,
        duration_minutes = duration_minutes,
    )