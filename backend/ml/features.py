import numpy as np
import pandas as pd

# Capacidad por planta (kW) — igual que en PlantGrid y simulator
PLANT_CAPACITY_KW: dict[int, float] = {
    1: 200.0, 2: 80.0, 3: 150.0, 4: 120.0,
    5: 90.0, 6: 300.0, 7: 60.0, 8: 45.0,
}
PLANT_INVERTER_COUNT: dict[int, int] = {
    1: 6, 2: 3, 3: 5, 4: 4,
    5: 3, 6: 8, 7: 2, 8: 2,
}
DEFAULT_CAPACITY_KW = 100.0
DEFAULT_INVERTER_COUNT = 4

def get_capacity(plant_id) -> float:
    try:
        pid = int(plant_id)
        cap = PLANT_CAPACITY_KW.get(pid, DEFAULT_CAPACITY_KW)
        inv = PLANT_INVERTER_COUNT.get(pid, DEFAULT_INVERTER_COUNT)
        return cap / inv  # Capacidad por inversor (para ML de registros individuales)
    except Exception:
        return DEFAULT_CAPACITY_KW / DEFAULT_INVERTER_COUNT


# ── Utilidades internas ───────────────────────────────────────────────────────

def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    # Asegurar que ts sea datetime y manejar tanto formatos naive como UTC
    ts = pd.to_datetime(df["ts"], utc=True)
    # Convertir a hora de Colombia (el contexto en el que se entrenaron los modelos)
    ts_local = ts.dt.tz_convert("America/Bogota")
    df["hour"]   = ts_local.dt.hour
    df["minute"] = ts_local.dt.minute
    return df


def _safe_div(a, b, eps=1e-9):
    if isinstance(b, pd.Series):
        b = b.replace(0, np.nan)
    return a / (b + eps)


# ── Features físicas (regresor) ───────────────────────────────────────────────
# Sin plant_id — el regresor aprende física pura.
# Se añade capacity_kw para que el regresor escale bien entre plantas.

PHYS_FEATURES = [
    "irradiance_wm2",
    "temp_module_c",
    "temp_ambient_c",
    "temp_delta_c",
    "hour",
    "minute",
    "capacity_kw",   # capacidad nominal de la planta — escala la salida
]


def build_phys_features(df: pd.DataFrame) -> pd.DataFrame:
    X = df.copy()
    X = _add_time_parts(X)
    X["temp_delta_c"] = X["temp_module_c"] - X["temp_ambient_c"]
    if "capacity_kw" not in X.columns:
        if "plant_id" in X.columns:
            X["capacity_kw"] = X["plant_id"].apply(get_capacity)
        else:
            X["capacity_kw"] = DEFAULT_CAPACITY_KW
    return X[PHYS_FEATURES]


# ── Features clasificador ─────────────────────────────────────────────────────
# Sin plant_id — reemplazado por power_ratio y residual_ratio (normalizados
# por capacidad instalada). Así el modelo aprende física relativa y generaliza
# a plantas nuevas sin haberlas visto en entrenamiento.

CLF_FEATURES = [
    "irradiance_wm2",
    "temp_module_c",
    "temp_ambient_c",
    "temp_delta_c",
    "expected_power_ac_kw",
    "power_residual_kw",
    "abs_residual_kw",
    "power_ratio",          # power_ac_kw / capacity_kw  (0–1)
    "residual_ratio",       # power_residual_kw / capacity_kw
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
      - expected_power_ac_kw  (del regresor)
      - power_residual_kw
      - abs_residual_kw
    Acepta opcionalmente plant_id (para calcular capacity_kw).
    """
    X = df.copy()
    X = _add_time_parts(X)

    X["temp_delta_c"] = X["temp_module_c"] - X["temp_ambient_c"]

    # Capacidad para normalizar
    if "capacity_kw" not in X.columns:
        if "plant_id" in X.columns:
            X["capacity_kw"] = X["plant_id"].apply(get_capacity)
        else:
            X["capacity_kw"] = DEFAULT_CAPACITY_KW

    # Features normalizadas — comparables entre plantas
    X["power_ratio"]    = _safe_div(X["power_ac_kw"],         X["capacity_kw"])
    X["residual_ratio"] = _safe_div(X["power_residual_kw"],   X["capacity_kw"])

    # Orden temporal por inversor para deltas
    sort_cols = ["inverter_id", "ts"] if "inverter_id" in X.columns else ["ts"]
    X = X.sort_values(sort_cols)

    if "inverter_id" in X.columns:
        X["delta_power_ac_kw"]   = X.groupby("inverter_id")["power_ac_kw"].diff()
        X["delta_irr_wm2"]       = X.groupby("inverter_id")["irradiance_wm2"].diff()
        X["delta_temp_module_c"] = X.groupby("inverter_id")["temp_module_c"].diff()
    else:
        X["delta_power_ac_kw"]   = X["power_ac_kw"].diff()
        X["delta_irr_wm2"]       = X["irradiance_wm2"].diff()
        X["delta_temp_module_c"] = X["temp_module_c"].diff()

    if "power_dc_kw" in X.columns:
        X["ac_dc_ratio"] = _safe_div(X["power_ac_kw"], X["power_dc_kw"])
    else:
        X["ac_dc_ratio"] = np.nan

    X["eff_irr_kw_per_wm2"] = _safe_div(X["power_ac_kw"], X["irradiance_wm2"])

    for c in ["delta_power_ac_kw", "delta_irr_wm2", "delta_temp_module_c"]:
        X[c] = X[c].fillna(0.0)

    return X[CLF_FEATURES]