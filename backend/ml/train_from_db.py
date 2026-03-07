from __future__ import annotations

import os
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import (
    mean_absolute_error,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)

from backend.ml.features import (
    build_phys_features,
    build_clf_features,
    PHYS_FEATURES,
    CLF_FEATURES,
)

# ── Config ────────────────────────────────────────────────────────────────────

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(exist_ok=True)

# Artefactos globales (fallback y SHAP global)
FEATURE_JSON_PATH = ARTIFACT_DIR / "feature_list.json"
METRICS_PATH      = ARTIFACT_DIR / "metrics.json"

# Mínimo de registros diurnos por planta para entrenar
MIN_ROWS_PER_PLANT    = 500
MIN_FAULT_ROWS_TYPE   = 30   # mínimo para clasificador de tipo


class _NpEncoder(json.JSONEncoder):
    """Serializa tipos numpy a tipos Python nativos."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def artifact_path(name: str, plant_id: int) -> Path:
    """Ruta de artefacto para una planta específica."""
    return ARTIFACT_DIR / f"{name}_p{plant_id}.joblib"


def type_classes_path(plant_id: int) -> Path:
    return ARTIFACT_DIR / f"fault_type_classes_p{plant_id}.json"


# ── DB ────────────────────────────────────────────────────────────────────────

def get_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://solar_user:solar_pass@localhost:5432/solar_db"
    )
    return create_engine(db_url)


def load_training_data() -> pd.DataFrame:
    engine = get_engine()
    query = text("""
        SELECT *
        FROM solar_readings
        WHERE power_ac_kw IS NOT NULL
          AND irradiance_wm2 > 20
        ORDER BY plant_id, ts
    """)
    df = pd.read_sql(query, engine)
    if df.empty:
        raise RuntimeError("No hay datos para entrenar.")

    print(f"  Registros diurnos cargados : {len(df):,}")
    print(f"  Plantas                    : {sorted(df['plant_id'].unique())}")
    print(f"  Fallas (label=1)           : {df['label_is_fault'].sum():,} "
          f"({df['label_is_fault'].mean()*100:.1f}%)")

    fault_rows = df[df["label_is_fault"] == 1]
    type_counts = fault_rows["fault_type"].value_counts()
    print("  Tipos de falla             :")
    for ft, cnt in type_counts.items():
        print(f"    {ft:25s}: {cnt:,}")

    return df


# ── Entrenamiento de una planta ───────────────────────────────────────────────

def train_plant(plant_id: int, df_plant: pd.DataFrame) -> dict:
    """
    Entrena regresor + clf binario + clf tipo para una planta.
    Retorna dict con métricas.
    """
    print(f"\n{'─'*60}")
    print(f"  Planta {plant_id}  ({len(df_plant):,} registros diurnos)")
    print(f"{'─'*60}")

    df_plant = df_plant.sort_values("ts").reset_index(drop=True)

    # Split temporal 80/20
    cut = int(len(df_plant) * 0.8)
    train_df = df_plant.iloc[:cut].copy()
    test_df  = df_plant.iloc[cut:].copy()

    # ── Regresor ──────────────────────────────────────────────────────────────
    print(f"  🌲 Regresor...")
    reg = RandomForestRegressor(
        n_estimators=200, max_depth=None, random_state=42, n_jobs=-1,
    )
    X_reg_train = build_phys_features(train_df)
    X_reg_test  = build_phys_features(test_df)
    reg.fit(X_reg_train, train_df["power_ac_kw"])
    reg_mae = mean_absolute_error(test_df["power_ac_kw"], reg.predict(X_reg_test))
    print(f"     MAE: {reg_mae:.3f} kW")

    # Enriquecer con residuales
    def enrich(df_part, X_reg):
        out = df_part.copy()
        out["expected_power_ac_kw"] = reg.predict(X_reg)
        out["power_residual_kw"]    = out["power_ac_kw"] - out["expected_power_ac_kw"]
        out["abs_residual_kw"]      = out["power_residual_kw"].abs()
        return out

    train_df = enrich(train_df, X_reg_train)
    test_df  = enrich(test_df,  X_reg_test)

    # ── Clasificador binario ──────────────────────────────────────────────────
    print(f"  🌲 Clasificador binario...")
    clf = RandomForestClassifier(
        n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced",
    )
    X_clf_train = build_clf_features(train_df)
    X_clf_test  = build_clf_features(test_df)
    clf.fit(X_clf_train, train_df["label_is_fault"])

    clf_pred  = clf.predict(X_clf_test)
    clf_proba = clf.predict_proba(X_clf_test)[:, 1]
    acc  = accuracy_score(test_df["label_is_fault"], clf_pred)
    f1   = f1_score(test_df["label_is_fault"], clf_pred, zero_division=0)
    auc  = roc_auc_score(test_df["label_is_fault"], clf_proba)
    cm   = confusion_matrix(test_df["label_is_fault"], clf_pred)
    print(f"     Acc: {acc:.4f}  F1: {f1:.4f}  AUC: {auc:.4f}")

    # ── Clasificador de tipo ──────────────────────────────────────────────────
    fault_train = train_df[
        (train_df["label_is_fault"] == 1) &
        (train_df["fault_type"].notna()) &
        (train_df["fault_type"] != "")
    ].copy()
    fault_test = test_df[
        (test_df["label_is_fault"] == 1) &
        (test_df["fault_type"].notna()) &
        (test_df["fault_type"] != "")
    ].copy()

    type_metrics = {}
    fault_type_clf    = None
    fault_type_classes = []

    if len(fault_train) >= MIN_FAULT_ROWS_TYPE and fault_train["fault_type"].nunique() >= 2:
        print(f"  🌲 Clasificador de tipo ({len(fault_train):,} fallas, "
              f"{fault_train['fault_type'].nunique()} clases)...")
        fault_type_clf = RandomForestClassifier(
            n_estimators=200, random_state=42, n_jobs=-1, class_weight="balanced",
        )
        X_type_train = build_clf_features(fault_train)
        fault_type_clf.fit(X_type_train, fault_train["fault_type"])
        fault_type_classes = fault_type_clf.classes_.tolist()

        if len(fault_test) > 0:
            X_type_test = build_clf_features(fault_test)
            type_pred   = fault_type_clf.predict(X_type_test)
            type_acc    = accuracy_score(fault_test["fault_type"], type_pred)
            type_f1     = f1_score(fault_test["fault_type"], type_pred,
                                   average="weighted", zero_division=0)
            type_report = classification_report(
                fault_test["fault_type"], type_pred,
                output_dict=True, zero_division=0
            )
            type_metrics = {
                "accuracy":              type_acc,
                "f1_weighted":           type_f1,
                "classification_report": type_report,
                "classes":               fault_type_classes,
                "n_train":               len(fault_train),
                "n_test":                len(fault_test),
            }
            print(f"     Acc: {type_acc:.4f}  F1: {type_f1:.4f}  "
                  f"Clases: {fault_type_classes}")
    else:
        print(f"  ⚠  Clasificador de tipo omitido "
              f"({len(fault_train)} fallas, "
              f"{fault_train['fault_type'].nunique() if len(fault_train) else 0} clases)")

    # ── SHAP ──────────────────────────────────────────────────────────────────
    try:
        import shap
        explainer = shap.TreeExplainer(clf)
        expected_value = (
            float(explainer.expected_value[1])
            if hasattr(explainer.expected_value, "__len__")
            else float(explainer.expected_value)
        )
        joblib.dump(
            {"explainer": explainer, "expected_value": expected_value,
             "feature_names": CLF_FEATURES},
            artifact_path("shap_explainer", plant_id),
        )
    except Exception as e:
        print(f"  ⚠  SHAP: {e}")

    # ── Guardar artefactos ────────────────────────────────────────────────────
    joblib.dump(reg, artifact_path("phys_reg", plant_id))
    joblib.dump(clf, artifact_path("fault_clf", plant_id))

    if fault_type_clf is not None:
        joblib.dump(
            {"model": fault_type_clf, "classes": fault_type_classes},
            artifact_path("fault_type_clf", plant_id),
        )
        with open(type_classes_path(plant_id), "w") as fh:
            json.dump(fault_type_classes, fh, indent=2)

    # Feature importances
    feat_imp = dict(zip(CLF_FEATURES, clf.feature_importances_.tolist()))

    return {
        "plant_id":            plant_id,
        "n_samples":           len(df_plant),
        "n_train":             len(train_df),
        "n_test":              len(test_df),
        "regression_mae":      round(float(reg_mae), 4),
        "accuracy":            round(float(acc), 4),
        "f1":                  round(float(f1), 4),
        "roc_auc":             round(float(auc), 4),
        "confusion_matrix":    cm.tolist(),
        "classification_report": classification_report(
            test_df["label_is_fault"], clf_pred,
            output_dict=True, zero_division=0,
        ),
        "feature_importances": {
            k: round(v, 5)
            for k, v in sorted(feat_imp.items(), key=lambda x: -x[1])
        },
        "fault_type_classifier": type_metrics if type_metrics else {"status": "not_trained"},
        "class_distribution": {
            "count": {
                "0": int((df_plant["label_is_fault"] == 0).sum()),
                "1": int((df_plant["label_is_fault"] == 1).sum()),
            },
            "ratio": {
                "0": round(float((df_plant["label_is_fault"] == 0).mean()), 4),
                "1": round(float((df_plant["label_is_fault"] == 1).mean()), 4),
            },
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def train():
    print("🔄 Cargando datos...")
    df = load_training_data()

    plant_ids = sorted(df["plant_id"].unique())
    print(f"\n🏭 Plantas a entrenar: {plant_ids}")

    all_metrics: dict[int, dict] = {}
    skipped: list[int] = []

    for pid in plant_ids:
        df_plant = df[df["plant_id"] == pid].copy()

        if len(df_plant) < MIN_ROWS_PER_PLANT:
            print(f"\n⚠  Planta {pid}: solo {len(df_plant)} registros "
                  f"(mínimo {MIN_ROWS_PER_PLANT}) — omitida")
            skipped.append(pid)
            continue

        metrics = train_plant(pid, df_plant)
        all_metrics[pid] = metrics

    # ── Feature list (compartida) ─────────────────────────────────────────────
    with open(FEATURE_JSON_PATH, "w") as fh:
        json.dump({"phys_features": PHYS_FEATURES, "clf_features": CLF_FEATURES}, fh, indent=2)

    # ── Métricas globales ─────────────────────────────────────────────────────
    metrics_output = {
        "trained_plants":  [int(p) for p in all_metrics.keys()],
        "skipped_plants":  [int(p) for p in skipped],
        "per_plant":       {int(k): v for k, v in all_metrics.items()},
        "summary": _weighted_summary(all_metrics),
    }

    class _NpEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (np.integer,)):  return int(o)
            if isinstance(o, (np.floating,)): return float(o)
            if isinstance(o, np.ndarray):     return o.tolist()
            return super().default(o)

    with open(METRICS_PATH, "w") as fh:
        json.dump(metrics_output, fh, indent=2, cls=_NpEncoder)

    # ── Reporte final ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✅ Entrenamiento completo")
    print(f"   Plantas entrenadas : {list(all_metrics.keys())}")
    if skipped:
        print(f"   Plantas omitidas   : {skipped} (datos insuficientes)")
    print(f"\n{'─'*60}")
    print(f"  {'Planta':<10} {'Registros':>10} {'MAE kW':>8} {'Acc':>7} {'F1':>7} {'AUC':>7}")
    print(f"{'─'*60}")
    for pid, m in all_metrics.items():
        print(f"  P{pid:<9} {m['n_samples']:>10,} {m['regression_mae']:>8.3f} "
              f"{m['accuracy']:>7.4f} {m['f1']:>7.4f} {m['roc_auc']:>7.4f}")
    print(f"{'='*60}\n")


def _weighted_summary(metrics: dict[int, dict]) -> dict:
    """Métricas ponderadas por número de muestras."""
    if not metrics:
        return {}
    total = sum(m["n_samples"] for m in metrics.values())
    if total == 0:
        return {}

    def wavg(key):
        return sum(m[key] * m["n_samples"] for m in metrics.values()) / total

    return {
        "total_samples":  total,
        "weighted_mae":   round(wavg("regression_mae"), 4),
        "weighted_acc":   round(wavg("accuracy"), 4),
        "weighted_f1":    round(wavg("f1"), 4),
        "weighted_auc":   round(wavg("roc_auc"), 4),
    }


if __name__ == "__main__":
    train()