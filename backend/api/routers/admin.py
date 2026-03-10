import os
import json
import shutil
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.session import get_db
from backend.core.security import require_admin
from backend.core.config import MODELS_DIR

router = APIRouter(prefix="/admin", tags=["admin"])

SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://simulator:9000")
BACKUPS_DIR   = MODELS_DIR / "backups"

PLANT_NAMES = {
    1: "Caribe",   2: "Andina",  3: "Paisa",  4: "Valle",
    5: "Llanos",   6: "Guajira", 7: "Sierra", 8: "Boyacá",
}

# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def get_admin_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    try:
        readings_count     = db.execute(text("SELECT COUNT(*) FROM solar_readings")).scalar()
        predictions_count  = db.execute(text("SELECT COUNT(*) FROM ai_predictions")).scalar()
        explanations_count = db.execute(text("SELECT COUNT(*) FROM ai_explanations")).scalar()
    except Exception:
        readings_count = predictions_count = explanations_count = -1

    sim_status = None
    try:
        resp = requests.get(f"{SIMULATOR_URL}/status", timeout=2)
        if resp.status_code == 200:
            sim_status = resp.json()
    except Exception:
        pass

    return {
        "db": {
            "solar_readings":   readings_count,
            "ai_predictions":   predictions_count,
            "ai_explanations":  explanations_count,
        },
        "simulator": sim_status,
    }

# ── DB ────────────────────────────────────────────────────────────────────────

@router.get("/db/readings")
def get_readings(
    page:           int   = Query(0,   ge=0),
    limit:          int   = Query(50,  ge=1, le=200),
    plant_id:       Optional[int]   = None,
    label_is_fault: Optional[int]   = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    filters = ["1=1"]
    params: dict = {"limit": limit, "offset": page * limit}

    if plant_id is not None:
        filters.append("plant_id = :plant_id")
        params["plant_id"] = plant_id
    if label_is_fault is not None:
        filters.append("label_is_fault = :label_is_fault")
        params["label_is_fault"] = label_is_fault

    where = " AND ".join(filters)
    rows = db.execute(text(f"""
        SELECT id, ts, plant_id, inverter_id,
               irradiance_wm2, temp_module_c,
               power_ac_kw, expected_power_ac_kw,
               label_is_fault, fault_type
        FROM solar_readings
        WHERE {where}
        ORDER BY id DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    return {"rows": [dict(r) for r in rows]}


@router.post("/db/truncate/{target}")
def truncate_db(
    target: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    allowed = {"readings", "predictions", "explanations", "all"}
    if target not in allowed:
        raise HTTPException(400, f"Target debe ser uno de: {allowed}")
    try:
        if target in ("explanations", "all"):
            db.execute(text("TRUNCATE TABLE ai_explanations"))
        if target in ("predictions", "all"):
            db.execute(text("TRUNCATE TABLE ai_predictions CASCADE"))
        if target in ("readings", "all"):
            db.execute(text("TRUNCATE TABLE solar_readings CASCADE"))
        db.commit()
        return {"status": "ok", "truncated": target}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))


@router.post("/db/export")
def export_db_csv(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """Exporta solar_readings a CSV en el volumen del simulador."""
    try:
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = f"/app/output/export_{ts}.csv"
        db.execute(text(f"COPY solar_readings TO '{path}' CSV HEADER"))
        db.commit()
        return {"status": "ok", "path": path}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

# ── Simulator ─────────────────────────────────────────────────────────────────

@router.post("/simulator/start")
def start_simulator(current_user: dict = Depends(require_admin)):
    try:
        return requests.post(f"{SIMULATOR_URL}/start", timeout=5).json()
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


@router.post("/simulator/stop")
def stop_simulator(current_user: dict = Depends(require_admin)):
    try:
        return requests.post(f"{SIMULATOR_URL}/stop", timeout=5).json()
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


class StepRequest(BaseModel):
    n_steps: int = 1

@router.post("/simulator/step")
def step_simulator(
    req: StepRequest,
    current_user: dict = Depends(require_admin),
):
    try:
        resp = requests.post(
            f"{SIMULATOR_URL}/step",
            json={"n_steps": req.n_steps},
            timeout=300,  # steps grandes pueden tardar
        )
        return resp.json()
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


@router.delete("/simulator/reset")
def reset_simulator(current_user: dict = Depends(require_admin)):
    try:
        return requests.delete(f"{SIMULATOR_URL}/reset", timeout=5).json()
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


@router.post("/simulator/reingest")
def reingest_csv(
    backup_id: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    """Dispara reingest_csv.py en el simulador. Si backup_id, reingesta ese snapshot."""
    try:
        params = f"?backup_id={backup_id}" if backup_id else ""
        resp = requests.post(f"{SIMULATOR_URL}/reingest{params}", timeout=360)
        if resp.status_code >= 400:
            raise HTTPException(resp.status_code, resp.json().get("detail", resp.text[:300]))
        return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


@router.get("/simulator/reingest-status")
def reingest_status(current_user: dict = Depends(require_admin)):
    """Estado del reingest en background en el simulador."""
    try:
        resp = requests.get(f"{SIMULATOR_URL}/reingest/status", timeout=5)
        return resp.json()
    except Exception:
        return {"running": False, "output": "", "error": "No se pudo contactar el simulador"}


@router.get("/simulator/csv-backups")
def list_csv_backups(current_user: dict = Depends(require_admin)):
    """Lista los snapshots CSV disponibles en el simulador."""
    try:
        resp = requests.get(f"{SIMULATOR_URL}/backups", timeout=5)
        return resp.json()
    except Exception:
        return {"backups": []}


@router.post("/simulator/csv-backups/{backup_id}/restore")
def restore_csv_backup(
    backup_id: str,
    current_user: dict = Depends(require_admin),
):
    """Restaura un snapshot CSV en el simulador."""
    try:
        resp = requests.post(f"{SIMULATOR_URL}/backups/{backup_id}/restore", timeout=10)
        return resp.json()
    except Exception as e:
        raise HTTPException(500, f"No se pudo contactar el simulador: {e}")


@router.post("/db/full-reset")
def full_reset(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """
    Reset completo del sistema:
    1. Para el simulador
    2. Resetea el simulador (hace snapshot CSV -> backups/ automáticamente)
    3. Trunca toda la DB (solar_readings CASCADE)
    """
    errors = []

    # 1. Stop simulator
    try:
        requests.post(f"{SIMULATOR_URL}/stop", timeout=5)
    except Exception:
        pass  # si ya estaba detenido, no importa

    # 2. Reset simulator (esto hace el snapshot del CSV)
    backup_id = None
    try:
        resp = requests.delete(f"{SIMULATOR_URL}/reset", timeout=10)
        if resp.status_code == 200:
            backup_id = resp.json().get("backup_id")
    except Exception as e:
        errors.append(f"simulator reset: {e}")

    # 3. Truncate DB
    try:
        db.execute(text("TRUNCATE TABLE ai_explanations"))
        db.execute(text("TRUNCATE TABLE ai_predictions CASCADE"))
        db.execute(text("TRUNCATE TABLE solar_readings CASCADE"))
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"db truncate: {e}")

    return {
        "status": "ok" if not errors else "partial",
        "backup_id": backup_id,
        "errors": errors,
    }


@router.get("/simulator/faults")
def get_active_faults(current_user: dict = Depends(require_admin)):
    """
    Retorna las fallas activas en el simulador en este momento.
    El simulador expone /faults con la lista de FaultEvent activos.
    """
    try:
        resp = requests.get(f"{SIMULATOR_URL}/faults", timeout=3)
        if resp.status_code == 200:
            return resp.json()
        return {"faults": []}
    except Exception:
        return {"faults": []}

# ── ML ────────────────────────────────────────────────────────────────────────

def _load_training_results() -> dict:
    """Lee metrics.json generado por train_from_db.py.
    Estructura real: {"per_plant": {"1": {...}, "2": {...}}}
    Cada planta tiene: f1, roc_auc, regression_mae, fault_type_classifier.f1, etc.
    """
    results_path = MODELS_DIR / "metrics.json"
    if results_path.exists():
        try:
            data = json.loads(results_path.read_text())
            return data.get("per_plant", {})
        except Exception:
            pass
    return {}


def _artifact_exists(plant_id: int) -> bool:
    return (MODELS_DIR / f"fault_clf_p{plant_id}.joblib").exists()


def _backup_exists(plant_id: int) -> bool:
    if not BACKUPS_DIR.exists():
        return False
    # Hay backup si existe al menos un snapshot con artifact de esta planta
    for snap in sorted(BACKUPS_DIR.iterdir()):
        if snap.is_dir() and (snap / f"fault_clf_p{plant_id}.joblib").exists():
            return True
    return False


@router.get("/ml/status")
def get_ml_status(current_user: dict = Depends(require_admin)):
    results = _load_training_results()
    models = []
    for pid in range(1, 9):
        # metrics.json puede tener keys int o str según el encoder usado
        res = results.get(pid) or results.get(str(pid)) or {}
        type_clf = res.get("fault_type_classifier") or {}
        models.append({
            "plant_id":    pid,
            "plant_name":  PLANT_NAMES.get(pid, f"Planta {pid}"),
            "f1_binary":   res.get("f1"),           # campo real en metrics.json
            "f1_type":     type_clf.get("f1"),       # dentro de fault_type_classifier
            "mae":         res.get("regression_mae"),
            "roc_auc":     res.get("roc_auc"),
            "n_samples":   res.get("n_samples"),
            "trained_at":  res.get("trained_at"),    # None si no se guarda — OK
            "artifact_ok": _artifact_exists(pid),
            "has_backup":  _backup_exists(pid),
        })
    return {"models": models}


@router.post("/ml/backup")
def backup_ml(current_user: dict = Depends(require_admin)):
    """Copia todos los artifacts actuales a backups/<timestamp>/"""
    if not MODELS_DIR.exists():
        raise HTTPException(404, "No hay artifacts para respaldar")

    ts         = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_dir = BACKUPS_DIR / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for f in MODELS_DIR.glob("*.joblib"):
        shutil.copy2(f, backup_dir / f.name)
        copied.append(f.name)

    # También copia metrics.json si existe
    results_src = MODELS_DIR / "metrics.json"
    if results_src.exists():
        shutil.copy2(results_src, backup_dir / "metrics.json")

    return {"status": "ok", "backup_id": ts, "files": copied}


@router.get("/ml/backups")
def list_backups(current_user: dict = Depends(require_admin)):
    if not BACKUPS_DIR.exists():
        return {"backups": []}

    backups = []
    for snap in sorted(BACKUPS_DIR.iterdir(), reverse=True):
        if not snap.is_dir():
            continue
        files  = list(snap.glob("*.joblib"))
        size_b = sum(f.stat().st_size for f in files)
        size_s = f"{size_b / 1_048_576:.1f} MB" if size_b > 0 else "—"

        # Leer métricas del snapshot si existen
        label = "Backup manual"
        res_path = snap / "metrics.json"
        if res_path.exists():
            label = "Auto-backup pre-retrain"

        backups.append({
            "id":    snap.name,
            "label": label,
            "size":  size_s,
            "files": len(files),
        })

    return {"backups": backups}


@router.post("/ml/restore/{backup_id}")
def restore_backup(
    backup_id: str,
    current_user: dict = Depends(require_admin),
):
    backup_dir = BACKUPS_DIR / backup_id
    if not backup_dir.exists():
        raise HTTPException(404, f"Backup '{backup_id}' no encontrado")

    # Auto-backup del estado actual antes de restaurar
    ts         = datetime.now().strftime("%Y-%m-%d_%H-%M")
    pre_dir    = BACKUPS_DIR / f"{ts}_pre-restore"
    pre_dir.mkdir(parents=True, exist_ok=True)
    for f in MODELS_DIR.glob("*.joblib"):
        shutil.copy2(f, pre_dir / f.name)

    # Restaurar
    restored = []
    for f in backup_dir.glob("*.joblib"):
        shutil.copy2(f, MODELS_DIR / f.name)
        restored.append(f.name)

    if (backup_dir / "metrics.json").exists():
        shutil.copy2(
            backup_dir / "metrics.json",
            MODELS_DIR / "metrics.json",
        )

    # Limpiar caché en memoria del registry
    try:
        from backend.ml.registry import _plant_cache
        _plant_cache.clear()
    except Exception:
        pass

    return {"status": "ok", "restored": restored, "pre_backup": f"{ts}_pre-restore"}


@router.post("/ml/restore/latest/{plant_id}")
def restore_latest_for_plant(
    plant_id: int,
    current_user: dict = Depends(require_admin),
):
    """Restaura solo los artifacts de una planta desde el backup más reciente."""
    if not BACKUPS_DIR.exists():
        raise HTTPException(404, "Sin backups disponibles")

    snapshots = sorted(
        [d for d in BACKUPS_DIR.iterdir() if d.is_dir() and not "pre-restore" in d.name],
        reverse=True
    )
    for snap in snapshots:
        artifacts = list(snap.glob(f"*_p{plant_id}.joblib"))
        if artifacts:
            for f in artifacts:
                shutil.copy2(f, MODELS_DIR / f.name)
            try:
                from backend.ml.registry import _plant_cache
                _plant_cache.pop(plant_id, None)
            except Exception:
                pass
            return {"status": "ok", "restored_from": snap.name, "plant_id": plant_id}

    raise HTTPException(404, f"No hay backup con artifacts para P{plant_id}")


@router.get("/ml/download/{plant_id}")
def download_artifact(
    plant_id: int,
    artifact: str = Query("fault_clf", description="phys_reg | fault_clf | fault_type_clf | shap_explainer"),
    current_user: dict = Depends(require_admin),
):
    path = MODELS_DIR / f"{artifact}_p{plant_id}.joblib"
    if not path.exists():
        raise HTTPException(404, "Artifact no encontrado")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )


@router.post("/ml/retrain", status_code=status.HTTP_202_ACCEPTED)
def retrain_ml(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
):
    """Lanza reentrenamiento en background. Hace backup automático antes."""
    def _retrain_with_backup():
        # 1. Auto-backup antes de reentrenar
        try:
            ts  = datetime.now().strftime("%Y-%m-%d_%H-%M")
            dst = BACKUPS_DIR / ts
            dst.mkdir(parents=True, exist_ok=True)
            for f in MODELS_DIR.glob("*.joblib"):
                shutil.copy2(f, dst / f.name)
        except Exception:
            pass  # backup falla silenciosamente — no bloquea el retrain

        # 2. Entrenar
        from backend.ml.train_from_db import train
        train()

        # 3. Limpiar cache del registry
        try:
            from backend.ml.registry import _plant_cache
            _plant_cache.clear()
        except Exception:
            pass

    background_tasks.add_task(_retrain_with_backup)
    return {"status": "accepted", "message": "Reentrenamiento iniciado en background con backup automático"}