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

REG_MODEL_PATH      = ARTIFACTS_DIR / "phys_reg.joblib"
CLF_MODEL_PATH      = ARTIFACTS_DIR / "fault_clf.joblib"
TYPE_CLF_PATH       = ARTIFACTS_DIR / "fault_type_clf.joblib"
TYPE_CLASSES_PATH   = ARTIFACTS_DIR / "fault_type_classes.json"
FEATURE_LIST_PATH   = ARTIFACTS_DIR / "feature_list.json"
SHAP_PATH           = ARTIFACTS_DIR / "shap_explainer.joblib"

# ── Cache de modelos (lazy load) ──────────────────────────────────────────────

_reg_model       = None
_clf_model       = None
_feature_config  = None
_shap_artifact   = None
_fault_type_artifact = None   # {"model": clf, "classes": [...]}


# ── Loaders ───────────────────────────────────────────────────────────────────

def get_shap_explainer() -> dict | None:
    global _shap_artifact
    if _shap_artifact is None and SHAP_PATH.exists():
        _shap_artifact = joblib.load(SHAP_PATH)
    return _shap_artifact


def get_fault_type_clf() -> dict | None:
    """Devuelve {"model": clf, "classes": [...]} o None si no está entrenado."""
    global _fault_type_artifact
    if _fault_type_artifact is None and TYPE_CLF_PATH.exists():
        _fault_type_artifact = joblib.load(TYPE_CLF_PATH)
    return _fault_type_artifact


def _models_ready() -> bool:
    return REG_MODEL_PATH.exists() and CLF_MODEL_PATH.exists()


def _load_models():
    global _reg_model, _clf_model, _feature_config

    if not _models_ready():
        raise RuntimeError(
            "Modelos no encontrados en artifacts/. "
            "Corre el trainer primero: "
            "docker compose --profile train run --rm ml-trainer"
        )

    if _reg_model is None:
        _reg_model = joblib.load(REG_MODEL_PATH)

    if _clf_model is None:
        _clf_model = joblib.load(CLF_MODEL_PATH)

    if _feature_config is None:
        with open(FEATURE_LIST_PATH, "r") as f:
            _feature_config = json.load(f)


def reload_models():
    """Fuerza recarga completa de todos los modelos."""
    global _reg_model, _clf_model, _feature_config, _shap_artifact, _fault_type_artifact
    _reg_model            = None
    _clf_model            = None
    _feature_config       = None
    _shap_artifact        = None
    _fault_type_artifact  = None
    _load_models()


# ── Predicción de tipo de falla ───────────────────────────────────────────────

def predict_fault_type(X_clf: pd.DataFrame) -> dict | None:
    """
    Predice el tipo de falla usando el clasificador multiclass.
    Devuelve {"fault_type": str, "confidence": float, "all_probas": dict}
    o None si el modelo no está disponible.

    X_clf debe tener exactamente las CLF_FEATURES (mismo orden que en training).
    """
    artifact = get_fault_type_clf()
    if artifact is None:
        return None

    model   = artifact["model"]
    classes = artifact["classes"]

    try:
        probas = model.predict_proba(X_clf)[0]          # shape (n_classes,)
        best_idx    = int(np.argmax(probas))
        fault_type  = classes[best_idx]
        confidence  = float(probas[best_idx])
        all_probas  = {cls: round(float(p), 4) for cls, p in zip(classes, probas)}

        return {
            "fault_type":  fault_type,
            "confidence":  round(confidence, 4),
            "all_probas":  all_probas,
        }
    except Exception:
        return None


# ── Predicción batch (ingesta) ────────────────────────────────────────────────

def predict_batch(df: pd.DataFrame):

    _load_models()

    phys_features_json = _feature_config["phys_features"]
    clf_features_json  = _feature_config["clf_features"]

    df = df.copy()

    # 1. Features físicas
    X_reg_full = build_phys_features(df)
    missing_phys = [c for c in phys_features_json if c not in X_reg_full.columns]
    if missing_phys:
        raise RuntimeError(f"Faltan phys_features: {missing_phys}")

    X_reg = X_reg_full[phys_features_json]

    # 2. Potencia esperada
    expected_power = _reg_model.predict(X_reg)
    df["expected_power_ac_kw"] = expected_power
    df["power_residual_kw"]    = df["power_ac_kw"] - df["expected_power_ac_kw"]
    df["abs_residual_kw"]      = df["power_residual_kw"].abs()

    # 3. Features clasificador
    X_clf_full = build_clf_features(df)
    missing_clf = [c for c in clf_features_json if c not in X_clf_full.columns]
    if missing_clf:
        raise RuntimeError(f"Faltan clf_features: {missing_clf}")

    X_clf = X_clf_full[clf_features_json]

    # 4. Clasificación binaria
    fault_proba = _clf_model.predict_proba(X_clf)[:, 1]
    THRESHOLD   = 0.65
    fault_pred  = (fault_proba >= THRESHOLD).astype(int)

    # 5. Salida
    results = []
    for i in range(len(df)):
        results.append({
            "expected_power_ac_kw": float(df.iloc[i]["expected_power_ac_kw"]),
            "power_residual_kw":    float(df.iloc[i]["power_residual_kw"]),
            "fault_proba":          float(fault_proba[i]),
            "fault_pred":           int(fault_pred[i]),
        })

    return results


def ml_status() -> dict:
    """Estado del ML — útil para /ml/status."""
    return {
        "models_ready":          _models_ready(),
        "reg_model_exists":      REG_MODEL_PATH.exists(),
        "clf_model_exists":      CLF_MODEL_PATH.exists(),
        "fault_type_clf_exists": TYPE_CLF_PATH.exists(),
        "shap_exists":           SHAP_PATH.exists(),
    }