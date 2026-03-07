from __future__ import annotations

import json
import joblib
import pandas as pd
import numpy as np
from pathlib import Path

from .features import (
    build_phys_features,
    build_clf_features,
    PHYS_FEATURES,
    CLF_FEATURES,
)

# ── Rutas ─────────────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

FEATURE_LIST_PATH = ARTIFACTS_DIR / "feature_list.json"


def _p(name: str, plant_id: int) -> Path:
    return ARTIFACTS_DIR / f"{name}_p{plant_id}.joblib"


def _type_classes_path(plant_id: int) -> Path:
    return ARTIFACTS_DIR / f"fault_type_classes_p{plant_id}.json"


# ── Cache por planta ──────────────────────────────────────────────────────────
# Cada entrada: {"reg": model, "clf": model, "type_clf": artifact|None,
#                "shap": artifact|None, "feature_config": dict}

_plant_cache: dict[int, dict] = {}
_feature_config: dict | None = None

# Plantas con modelos disponibles (se detecta en runtime)
_available_plants: set[int] | None = None


def _get_available_plants() -> set[int]:
    global _available_plants
    if _available_plants is None:
        found = set()
        for p in range(1, 9):
            if _p("phys_reg", p).exists() and _p("fault_clf", p).exists():
                found.add(p)
        _available_plants = found
    return _available_plants


def _load_feature_config() -> dict:
    global _feature_config
    if _feature_config is None and FEATURE_LIST_PATH.exists():
        with open(FEATURE_LIST_PATH) as f:
            _feature_config = json.load(f)
    return _feature_config or {"phys_features": PHYS_FEATURES, "clf_features": CLF_FEATURES}


def _load_plant(plant_id: int) -> dict | None:
    """Carga todos los artefactos de una planta. Retorna None si no existen."""
    reg_path = _p("phys_reg", plant_id)
    clf_path = _p("fault_clf", plant_id)

    if not reg_path.exists() or not clf_path.exists():
        return None

    reg = joblib.load(reg_path)
    clf = joblib.load(clf_path)

    # Tipo (opcional)
    type_artifact = None
    type_path = _p("fault_type_clf", plant_id)
    if type_path.exists():
        type_artifact = joblib.load(type_path)

    # SHAP (opcional)
    shap_artifact = None
    shap_path = _p("shap_explainer", plant_id)
    if shap_path.exists():
        shap_artifact = joblib.load(shap_path)

    return {
        "reg":            reg,
        "clf":            clf,
        "type_artifact":  type_artifact,
        "shap_artifact":  shap_artifact,
    }


def _get_plant(plant_id: int) -> dict | None:
    if plant_id not in _plant_cache:
        loaded = _load_plant(plant_id)
        if loaded is None:
            return None
        _plant_cache[plant_id] = loaded
    return _plant_cache[plant_id]


# ── API pública ───────────────────────────────────────────────────────────────

def get_shap_explainer(plant_id: int) -> dict | None:
    """Retorna el artefacto SHAP de la planta, o None."""
    plant = _get_plant(plant_id)
    return plant["shap_artifact"] if plant else None


def get_fault_type_clf(plant_id: int) -> dict | None:
    """Retorna {model, classes} del clasificador de tipo, o None."""
    plant = _get_plant(plant_id)
    return plant["type_artifact"] if plant else None


def predict_fault_type(X_clf: pd.DataFrame, plant_id: int) -> dict | None:
    """
    Predice tipo de falla para una planta.
    Retorna {fault_type, confidence, all_probas} o None.
    """
    artifact = get_fault_type_clf(plant_id)
    if artifact is None:
        return None

    model   = artifact["model"]
    classes = artifact["classes"]

    try:
        probas     = model.predict_proba(X_clf)[0]
        best_idx   = int(np.argmax(probas))
        return {
            "fault_type": classes[best_idx],
            "confidence": round(float(probas[best_idx]), 4),
            "all_probas": {cls: round(float(p), 4) for cls, p in zip(classes, probas)},
        }
    except Exception:
        return None


def predict_batch(df: pd.DataFrame) -> list[dict]:
    """
    Pipeline completo para un DataFrame de lecturas diurnas.
    Agrupa por plant_id y usa el modelo correspondiente a cada planta.
    Si una planta no tiene modelo, retorna predicción nula para esas filas.

    Retorna lista de dicts en el mismo orden que df.
    """
    feature_config = _load_feature_config()
    phys_features  = feature_config["phys_features"]
    clf_features   = feature_config["clf_features"]

    results = [None] * len(df)
    df = df.copy().reset_index(drop=True)

    # Agrupar por planta
    if "plant_id" not in df.columns:
        raise RuntimeError("predict_batch requiere columna plant_id")

    for plant_id, idx_group in df.groupby("plant_id").groups.items():
        plant_id = int(plant_id)
        plant = _get_plant(plant_id)

        if plant is None:
            # Sin modelo para esta planta — predicción nula
            zero = {
                "expected_power_ac_kw": 0.0,
                "power_residual_kw":    0.0,
                "fault_proba":          0.0,
                "fault_pred":           0,
                "fault_type_pred":      None,
                "fault_type_proba":     None,
            }
            for i in idx_group:
                results[i] = zero.copy()
            continue

        reg = plant["reg"]
        clf = plant["clf"]
        df_p = df.loc[idx_group].copy()

        # 1. Regresor
        X_reg = build_phys_features(df_p)[phys_features]
        expected        = reg.predict(X_reg)
        df_p["expected_power_ac_kw"] = expected
        df_p["power_residual_kw"]    = df_p["power_ac_kw"] - df_p["expected_power_ac_kw"]
        df_p["abs_residual_kw"]      = df_p["power_residual_kw"].abs()

        # 2. Clasificador binario
        X_clf      = build_clf_features(df_p)[clf_features]
        fault_proba = clf.predict_proba(X_clf)[:, 1]
        fault_pred  = (fault_proba >= 0.65).astype(int)

        # 3. Clasificador de tipo (solo fallas predichas)
        fault_type_preds  = [None] * len(df_p)
        fault_type_probas = [None] * len(df_p)
        type_artifact = plant["type_artifact"]

        fault_local_idx = [i for i, p in enumerate(fault_pred) if p == 1]
        if fault_local_idx and type_artifact is not None:
            X_type  = X_clf.iloc[fault_local_idx]
            model   = type_artifact["model"]
            classes = type_artifact["classes"]
            try:
                type_probas_mat = model.predict_proba(X_type)
                for li, probas in zip(fault_local_idx, type_probas_mat):
                    best = int(np.argmax(probas))
                    fault_type_preds[li]  = classes[best]
                    fault_type_probas[li] = round(float(probas[best]), 4)
            except Exception:
                pass

        # Mapear resultados de vuelta a posiciones originales
        for local_i, global_i in enumerate(idx_group):
            results[global_i] = {
                "expected_power_ac_kw": float(df_p.iloc[local_i]["expected_power_ac_kw"]),
                "power_residual_kw":    float(df_p.iloc[local_i]["power_residual_kw"]),
                "fault_proba":          float(fault_proba[local_i]),
                "fault_pred":           int(fault_pred[local_i]),
                "fault_type_pred":      fault_type_preds[local_i],
                "fault_type_proba":     fault_type_probas[local_i],
            }

    # Rellenar cualquier None que haya quedado (no debería ocurrir)
    zero = {"expected_power_ac_kw": 0.0, "power_residual_kw": 0.0,
            "fault_proba": 0.0, "fault_pred": 0,
            "fault_type_pred": None, "fault_type_proba": None}
    results = [r if r is not None else zero.copy() for r in results]

    return results


def reload_models():
    """Fuerza recarga completa de todos los modelos."""
    global _plant_cache, _feature_config, _available_plants
    _plant_cache      = {}
    _feature_config   = None
    _available_plants = None


def ml_status() -> dict:
    available = _get_available_plants()
    status = {"available_plants": sorted(available)}
    for p in range(1, 9):
        has_reg      = _p("phys_reg",        p).exists()
        has_clf      = _p("fault_clf",       p).exists()
        has_type     = _p("fault_type_clf",  p).exists()
        has_shap     = _p("shap_explainer",  p).exists()
        status[f"plant_{p}"] = {
            "reg":      has_reg,
            "clf":      has_clf,
            "type_clf": has_type,
            "shap":     has_shap,
            "ready":    has_reg and has_clf,
        }
    return status