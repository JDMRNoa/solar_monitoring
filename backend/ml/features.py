import numpy as np
import pandas as pd


# ==========================
# Utilidades internas
# ==========================

def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["ts"])
    df["hour"] = ts.dt.hour
    df["minute"] = ts.dt.minute
    return df


def _safe_div(a, b, eps=1e-9):
    if isinstance(b, pd.Series):
        b = b.replace(0, np.nan)
    return a / (b + eps)


# ==========================
# Features físicas (regresión)
# ==========================

PHYS_FEATURES = [
    "irradiance_wm2",
    "temp_module_c",
    "temp_ambient_c",
    "temp_delta_c",
    "hour",
    "minute",
]


def build_phys_features(df: pd.DataFrame) -> pd.DataFrame:
    X = df.copy()
    X = _add_time_parts(X)
    X["temp_delta_c"] = X["temp_module_c"] - X["temp_ambient_c"]
    return X[PHYS_FEATURES]


# ==========================
# Features clasificador
# FIX: se agrega plant_id para que el modelo distinga perfiles
#      climáticos entre plantas (Bogotá nublada ≠ Guajira nublada)
# ==========================

CLF_FEATURES = [
    "plant_id",           # ← NUEVO: perfil de planta
    "irradiance_wm2",
    "temp_module_c",
    "temp_ambient_c",
    "temp_delta_c",
    "expected_power_ac_kw",
    "power_residual_kw",
    "abs_residual_kw",
    "delta_power_ac_kw",
    "delta_irr_wm2",
    "delta_temp_module_c",
    "ac_dc_ratio",
    "eff_irr_kw_per_wm2",
    "hour",
    "minute",
]


def build_clf_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Requiere que df tenga:
    - expected_power_ac_kw  (calculado por el regresor, no copiado del simulador)
    - power_residual_kw
    - abs_residual_kw
    - plant_id              (int — ya viene de solar_readings)
    """
    X = df.copy()
    X = _add_time_parts(X)

    X["temp_delta_c"] = X["temp_module_c"] - X["temp_ambient_c"]

    # Orden temporal por planta
    sort_cols = ["plant_id", "ts"] if "plant_id" in X.columns else ["ts"]
    X = X.sort_values(sort_cols)

    # Deltas por planta
    if "plant_id" in X.columns:
        X["delta_power_ac_kw"]   = X.groupby("plant_id")["power_ac_kw"].diff()
        X["delta_irr_wm2"]       = X.groupby("plant_id")["irradiance_wm2"].diff()
        X["delta_temp_module_c"] = X.groupby("plant_id")["temp_module_c"].diff()
    else:
        X["delta_power_ac_kw"]   = X["power_ac_kw"].diff()
        X["delta_irr_wm2"]       = X["irradiance_wm2"].diff()
        X["delta_temp_module_c"] = X["temp_module_c"].diff()

    # Ratios
    if "power_dc_kw" in X.columns:
        X["ac_dc_ratio"] = _safe_div(X["power_ac_kw"], X["power_dc_kw"])
    else:
        X["ac_dc_ratio"] = np.nan

    X["eff_irr_kw_per_wm2"] = _safe_div(X["power_ac_kw"], X["irradiance_wm2"])

    # Rellenar NaNs de diffs (primer registro de cada planta)
    for c in ["delta_power_ac_kw", "delta_irr_wm2", "delta_temp_module_c"]:
        X[c] = X[c].fillna(0.0)

    return X[CLF_FEATURES]