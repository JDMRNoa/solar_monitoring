# from __future__ import annotations

# import json
# import joblib
# import pandas as pd
# from pathlib import Path

# from .features import (
#     build_phys_features,
#     build_clf_features,
#     PHYS_FEATURES,
#     CLF_FEATURES,
# )

# # ==========================
# # Rutas artefactos
# # ==========================

# BASE_DIR = Path(__file__).resolve().parent
# ARTIFACTS_DIR = BASE_DIR / "artifacts"

# REG_MODEL_PATH = ARTIFACTS_DIR / "phys_reg.joblib"
# CLF_MODEL_PATH = ARTIFACTS_DIR / "fault_clf.joblib"
# FEATURE_LIST_PATH = ARTIFACTS_DIR / "feature_list.json"

# # ==========================
# # Cargar modelos
# # ==========================

# reg_model = joblib.load(REG_MODEL_PATH)
# clf_model = joblib.load(CLF_MODEL_PATH)

# with open(FEATURE_LIST_PATH, "r") as f:
#     feature_config = json.load(f)

# PHYS_FEATURES_JSON = feature_config["phys_features"]
# CLF_FEATURES_JSON = feature_config["clf_features"]


# # ==========================
# # Predicción batch
# # ==========================

# def predict_batch(df: pd.DataFrame):

#     df = df.copy()

#     # 1️⃣ Features físicas
#     X_reg_full = build_phys_features(df)

#     missing_phys = [
#         c for c in PHYS_FEATURES_JSON if c not in X_reg_full.columns
#     ]
#     if missing_phys:
#         raise RuntimeError(f"Faltan phys_features: {missing_phys}")

#     X_reg = X_reg_full[PHYS_FEATURES_JSON]

#     # 2️⃣ Predicción física
#     expected_power = reg_model.predict(X_reg)

#     df["expected_power_ac_kw"] = expected_power
#     df["power_residual_kw"] = df["power_ac_kw"] - df["expected_power_ac_kw"]
#     df["abs_residual_kw"] = df["power_residual_kw"].abs()

#     # 3️⃣ Features clasificador
#     X_clf_full = build_clf_features(df)

#     missing_clf = [
#         c for c in CLF_FEATURES_JSON if c not in X_clf_full.columns
#     ]
#     if missing_clf:
#         raise RuntimeError(f"Faltan clf_features: {missing_clf}")

#     X_clf = X_clf_full[CLF_FEATURES_JSON]

#     # 4️⃣ Clasificación
#     fault_proba = clf_model.predict_proba(X_clf)[:, 1]
#     fault_pred = clf_model.predict(X_clf)

#     # 5️⃣ Salida (igual que antes)
#     results = []

#     for i in range(len(df)):
#         results.append({
#             "expected_power_ac_kw": float(df.iloc[i]["expected_power_ac_kw"]),
#             "power_residual_kw": float(df.iloc[i]["power_residual_kw"]),
#             "fault_proba": float(fault_proba[i]),
#             "fault_pred": int(fault_pred[i]),
#         })

#     return results


from __future__ import annotations

import json
import joblib
import pandas as pd
from pathlib import Path

from .features import (
    build_phys_features,
    build_clf_features,
    PHYS_FEATURES,
    CLF_FEATURES,
)

# ==========================
# Rutas artefactos
# ==========================

BASE_DIR      = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

REG_MODEL_PATH    = ARTIFACTS_DIR / "phys_reg.joblib"
CLF_MODEL_PATH    = ARTIFACTS_DIR / "fault_clf.joblib"
FEATURE_LIST_PATH = ARTIFACTS_DIR / "feature_list.json"

# ==========================
# Carga lazy de modelos
# Los modelos se cargan solo cuando se necesitan,
# no al importar el módulo. Así el backend arranca
# aunque los .joblib no existan todavía.
# ==========================

_reg_model = None
_clf_model = None
_feature_config = None


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
    """Fuerza recarga de modelos (útil después de reentrenar)."""
    global _reg_model, _clf_model, _feature_config
    _reg_model = None
    _clf_model = None
    _feature_config = None
    _load_models()


# ==========================
# Predicción batch
# ==========================

def predict_batch(df: pd.DataFrame):

    _load_models()

    phys_features_json = _feature_config["phys_features"]
    clf_features_json  = _feature_config["clf_features"]

    df = df.copy()

    # 1️⃣ Features físicas
    X_reg_full = build_phys_features(df)

    missing_phys = [c for c in phys_features_json if c not in X_reg_full.columns]
    if missing_phys:
        raise RuntimeError(f"Faltan phys_features: {missing_phys}")

    X_reg = X_reg_full[phys_features_json]

    # 2️⃣ Predicción física → expected power
    expected_power = _reg_model.predict(X_reg)

    df["expected_power_ac_kw"] = expected_power
    df["power_residual_kw"]    = df["power_ac_kw"] - df["expected_power_ac_kw"]
    df["abs_residual_kw"]      = df["power_residual_kw"].abs()

    # 3️⃣ Features clasificador
    X_clf_full = build_clf_features(df)

    missing_clf = [c for c in clf_features_json if c not in X_clf_full.columns]
    if missing_clf:
        raise RuntimeError(f"Faltan clf_features: {missing_clf}")

    X_clf = X_clf_full[clf_features_json]

    # 4️⃣ Clasificación
    fault_proba = _clf_model.predict_proba(X_clf)[:, 1]
    fault_pred  = _clf_model.predict(X_clf)

    # 5️⃣ Salida
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
    """Devuelve el estado del ML — útil para un endpoint /ml/status."""
    ready = _models_ready()
    return {
        "models_ready":    ready,
        "reg_model_path":  str(REG_MODEL_PATH),
        "clf_model_path":  str(CLF_MODEL_PATH),
        "reg_model_exists": REG_MODEL_PATH.exists(),
        "clf_model_exists": CLF_MODEL_PATH.exists(),
    }