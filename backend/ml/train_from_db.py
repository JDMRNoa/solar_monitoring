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

REG_PATH            = ARTIFACT_DIR / "phys_reg.joblib"
CLF_PATH            = ARTIFACT_DIR / "fault_clf.joblib"
TYPE_CLF_PATH       = ARTIFACT_DIR / "fault_type_clf.joblib"
TYPE_CLASSES_PATH   = ARTIFACT_DIR / "fault_type_classes.json"
FEATURE_JSON_PATH   = ARTIFACT_DIR / "feature_list.json"
METRICS_PATH        = ARTIFACT_DIR / "metrics.json"


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

    # Distribución de tipos de falla
    fault_rows = df[df["label_is_fault"] == 1]
    type_counts = fault_rows["fault_type"].value_counts()
    print(f"  Tipos de falla             :")
    for ft, cnt in type_counts.items():
        print(f"    {ft:25s}: {cnt:,}")

    return df


# ── Training ──────────────────────────────────────────────────────────────────

def train():

    print("🔄 Cargando datos...")
    df = load_training_data()

    # Split temporal 80/20 por planta
    train_parts, test_parts = [], []
    for pid, g in df.groupby("plant_id"):
        g = g.sort_values("ts")
        cut = int(len(g) * 0.8)
        train_parts.append(g.iloc[:cut])
        test_parts.append(g.iloc[cut:])

    train_df = pd.concat(train_parts).reset_index(drop=True)
    test_df  = pd.concat(test_parts).reset_index(drop=True)

    print(f"\n📊 Train: {len(train_df):,} | Test: {len(test_df):,}")

    # ── 1. Regresor físico ────────────────────────────────────────────────────
    print("\n🌲 Entrenando regresor físico...")

    reg = RandomForestRegressor(
        n_estimators=300, max_depth=None, random_state=42, n_jobs=-1,
    )

    X_reg_train = build_phys_features(train_df)
    y_reg_train = train_df["power_ac_kw"]
    reg.fit(X_reg_train, y_reg_train)

    X_reg_test = build_phys_features(test_df)
    y_reg_test = test_df["power_ac_kw"]
    reg_mae = mean_absolute_error(y_reg_test, reg.predict(X_reg_test))
    print(f"  Regresor MAE: {reg_mae:.4f} kW")

    # Enriquecer con residuales
    def enrich(df_part, X_reg):
        out = df_part.copy()
        out["expected_power_ac_kw"] = reg.predict(X_reg)
        out["power_residual_kw"]    = out["power_ac_kw"] - out["expected_power_ac_kw"]
        out["abs_residual_kw"]      = out["power_residual_kw"].abs()
        return out

    train_df = enrich(train_df, X_reg_train)
    test_df  = enrich(test_df,  X_reg_test)

    # ── 2. Clasificador binario (detección de fallas) ─────────────────────────
    print("\n🌲 Entrenando clasificador binario de fallas...")

    clf = RandomForestClassifier(
        n_estimators=300, random_state=42, n_jobs=-1, class_weight="balanced",
    )

    X_clf_train = build_clf_features(train_df)
    y_clf_train = train_df["label_is_fault"]
    clf.fit(X_clf_train, y_clf_train)

    X_clf_test = build_clf_features(test_df)
    y_clf_test  = test_df["label_is_fault"]
    clf_pred    = clf.predict(X_clf_test)
    clf_proba   = clf.predict_proba(X_clf_test)[:, 1]
    cm          = confusion_matrix(y_clf_test, clf_pred)

    print(f"  Accuracy : {accuracy_score(y_clf_test, clf_pred):.4f}")
    print(f"  F1       : {f1_score(y_clf_test, clf_pred, zero_division=0):.4f}")
    print(f"  ROC-AUC  : {roc_auc_score(y_clf_test, clf_proba):.4f}")

    # ── 3. Clasificador multiclass de tipo de falla ───────────────────────────
    print("\n🌲 Entrenando clasificador de tipo de falla (multiclass)...")

    # Solo filas con falla activa y tipo conocido
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

    print(f"  Filas de falla para entrenar tipo: {len(fault_train):,}")
    print(f"  Filas de falla para testear tipo : {len(fault_test):,}")
    print(f"  Clases: {sorted(fault_train['fault_type'].unique())}")

    type_metrics = {}

    if len(fault_train) < 50 or fault_train["fault_type"].nunique() < 2:
        print("  ⚠ Datos insuficientes para clasificador de tipo — se omite")
        fault_type_clf = None
        fault_type_classes = []
    else:
        # class_weight="balanced" porque algunos tipos son más raros
        fault_type_clf = RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced",
        )

        X_type_train = build_clf_features(fault_train)
        y_type_train = fault_train["fault_type"]

        fault_type_clf.fit(X_type_train, y_type_train)
        fault_type_classes = fault_type_clf.classes_.tolist()

        if len(fault_test) > 0:
            X_type_test  = build_clf_features(fault_test)
            y_type_test  = fault_test["fault_type"]
            type_pred    = fault_type_clf.predict(X_type_test)
            type_acc     = accuracy_score(y_type_test, type_pred)
            type_f1      = f1_score(y_type_test, type_pred, average="weighted", zero_division=0)
            type_report  = classification_report(y_type_test, type_pred, output_dict=True, zero_division=0)

            print(f"  Accuracy (tipo): {type_acc:.4f}")
            print(f"  F1 weighted    : {type_f1:.4f}")

            type_metrics = {
                "accuracy":                type_acc,
                "f1_weighted":             type_f1,
                "classification_report":   type_report,
                "classes":                 fault_type_classes,
                "n_train":                 len(fault_train),
                "n_test":                  len(fault_test),
            }

        joblib.dump(
            {"model": fault_type_clf, "classes": fault_type_classes},
            TYPE_CLF_PATH,
        )
        with open(TYPE_CLASSES_PATH, "w") as f:
            json.dump(fault_type_classes, f, indent=2)

        print(f"  Clases aprendidas: {fault_type_classes}")

    # ── 4. SHAP TreeExplainer (para el clf binario) ───────────────────────────
    print("\n🔍 Construyendo SHAP explainer...")
    try:
        import shap
        explainer = shap.TreeExplainer(clf)
        expected_value = (
            float(explainer.expected_value[1])
            if hasattr(explainer.expected_value, "__len__")
            else float(explainer.expected_value)
        )
        joblib.dump(
            {"explainer": explainer, "expected_value": expected_value, "feature_names": CLF_FEATURES},
            ARTIFACT_DIR / "shap_explainer.joblib",
        )
        print("  SHAP explainer guardado")
    except Exception as e:
        print(f"  ⚠ SHAP no disponible: {e}")

    # ── 5. Guardar artefactos y métricas ─────────────────────────────────────
    print("\n💾 Guardando artefactos...")

    joblib.dump(reg, REG_PATH)
    joblib.dump(clf, CLF_PATH)

    with open(FEATURE_JSON_PATH, "w") as f:
        json.dump({"phys_features": PHYS_FEATURES, "clf_features": CLF_FEATURES}, f, indent=2)

    feat_imp = dict(zip(CLF_FEATURES, clf.feature_importances_.tolist()))
    metrics = {
        "n_samples":              len(df),
        "n_train":                len(train_df),
        "n_test":                 len(test_df),
        "class_distribution": {
            "count": {
                "0": int((df["label_is_fault"] == 0).sum()),
                "1": int((df["label_is_fault"] == 1).sum()),
            },
            "ratio": {
                "0": round(float((df["label_is_fault"] == 0).mean()), 4),
                "1": round(float((df["label_is_fault"] == 1).mean()), 4),
            },
        },
        "regression_mae": round(float(reg_mae), 6),
        "accuracy":       round(float(accuracy_score(y_clf_test, clf_pred)), 4),
        "precision":      round(float(precision_score(y_clf_test, clf_pred, zero_division=0)), 4),
        "recall":         round(float(recall_score(y_clf_test, clf_pred, zero_division=0)), 4),
        "f1":             round(float(f1_score(y_clf_test, clf_pred, zero_division=0)), 4),
        "roc_auc":        round(float(roc_auc_score(y_clf_test, clf_proba)), 4),
        "confusion_matrix": cm.tolist(),
        "classification_report": classification_report(
            y_clf_test, clf_pred, output_dict=True, zero_division=0
        ),
        "feature_importances": {
            k: round(v, 5)
            for k, v in sorted(feat_imp.items(), key=lambda x: -x[1])
        },
        "fault_type_classifier": type_metrics if type_metrics else {"status": "not_trained"},
    }

    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print("✅ Entrenamiento completo\n")
    print(f"📊 Clasificador binario:")
    print(f"   MAE regresor : {metrics['regression_mae']} kW")
    print(f"   Accuracy     : {metrics['accuracy']}")
    print(f"   F1           : {metrics['f1']}")
    print(f"   ROC-AUC      : {metrics['roc_auc']}")
    if type_metrics:
        print(f"\n📊 Clasificador de tipo de falla:")
        print(f"   Accuracy     : {round(type_metrics['accuracy'], 4)}")
        print(f"   F1 weighted  : {round(type_metrics['f1_weighted'], 4)}")
        print(f"   Clases       : {type_metrics['classes']}")


if __name__ == "__main__":
    train()