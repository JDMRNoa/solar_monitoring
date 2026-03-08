import os
import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.session import get_db
from backend.core.security import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])

SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://simulator:9000")

@router.get("/status")
def get_admin_status(db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    """Devuelve el estado de la base de datos y del simulador."""
    try:
        readings_count = db.execute(text("SELECT COUNT(*) FROM solar_readings")).scalar()
        predictions_count = db.execute(text("SELECT COUNT(*) FROM ai_predictions")).scalar()
    except Exception as e:
        readings_count = -1
        predictions_count = -1

    sim_status = None
    try:
        resp = requests.get(f"{SIMULATOR_URL}/status", timeout=2)
        if resp.status_code == 200:
            sim_status = resp.json()
    except Exception:
        pass

    return {
        "db": {
            "solar_readings": readings_count,
            "ai_predictions": predictions_count,
        },
        "simulator": sim_status
    }

@router.post("/db/truncate/{target}")
def truncate_db(target: str, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    """Elimina los datos de las tablas. Target: 'readings', 'predictions', o 'all'"""
    try:
        if target == "predictions" or target == "all":
            db.execute(text("TRUNCATE TABLE ai_predictions CASCADE"))
        if target == "readings" or target == "all":
            db.execute(text("TRUNCATE TABLE solar_readings CASCADE"))
        db.commit()
        return {"status": "success", "message": f"Truncated {target}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/simulator/start")
def start_simulator(current_user: dict = Depends(require_admin)):
    try:
        resp = requests.post(f"{SIMULATOR_URL}/start", timeout=5)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact simulator: {e}")

@router.post("/simulator/stop")
def stop_simulator(current_user: dict = Depends(require_admin)):
    try:
        resp = requests.post(f"{SIMULATOR_URL}/stop", timeout=5)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact simulator: {e}")

@router.post("/simulator/step")
def step_simulator(n_steps: int = 1, current_user: dict = Depends(require_admin)):
    try:
        resp = requests.post(f"{SIMULATOR_URL}/step", json={"n_steps": n_steps}, timeout=5)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact simulator: {e}")

@router.delete("/simulator/reset")
def reset_simulator(current_user: dict = Depends(require_admin)):
    try:
        resp = requests.delete(f"{SIMULATOR_URL}/reset", timeout=5)
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact simulator: {e}")

@router.post("/ml/retrain")
def retrain_ml(current_user: dict = Depends(require_admin)):
    """Simula un trigger o lanza un script asíncrono real para reentrenamiento."""
    return {"status": "success", "message": "ML Retraining pipeline initiated (Simulated)"}
