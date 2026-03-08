# simulator_service.py
"""
Servicio FastAPI para el simulador solar.

El contenedor arranca DETENIDO. Solo genera cuando tú lo ordenas.

Endpoints:
  GET  /health        Healthcheck para Docker/K8s
  GET  /status        Estado completo del generador
  POST /start         Arranca la generación en background
  POST /stop          Pausa la generación (contenedor sigue vivo)
  POST /step          Ejecuta exactamente N pasos (sin arrancar el loop)
  DELETE /reset       Borra CSV + checkpoint, reinicia estado

Variables de entorno:
  SOLAR_API_URL           URL destino para publicar (vacío = solo CSV)
  SOLAR_INGEST_ENDPOINT   /ingest_batch
  SOLAR_BATCH_SIZE        250
  SOLAR_STEP_DELAY_S      Segundos entre pasos en modo continuo (default 2.0)
  SOLAR_FAULT_LEVEL       1-5 (default 2)
  SOLAR_N_PLANTS          1-8 (default 4)
  SOLAR_START_TS          ISO timestamp inicio (default 2025-01-01T00:00:00)
  SOLAR_OUTPUT_DIR        ./output
  AUTOSTART               true|false — si true arranca solo al iniciar
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from simulator_core import MultiPlantSimulator, build_plant_profiles

# ─────────────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger("simulator_service")


# ─────────────────────────────────────────────────────────────────
#  Config desde env
# ─────────────────────────────────────────────────────────────────

OUTPUT_DIR      = Path(os.getenv("SOLAR_OUTPUT_DIR", "./output"))
API_URL         = os.getenv("SOLAR_API_URL", "")
INGEST_ENDPOINT = os.getenv("SOLAR_INGEST_ENDPOINT", "/ingest_batch")
BATCH_SIZE      = int(os.getenv("SOLAR_BATCH_SIZE", "250"))
STEP_DELAY_S    = float(os.getenv("SOLAR_STEP_DELAY_S", "2.0"))
FAULT_LEVEL     = int(os.getenv("SOLAR_FAULT_LEVEL", "2"))
N_PLANTS        = int(os.getenv("SOLAR_N_PLANTS", "4"))
START_TS_STR    = os.getenv("SOLAR_START_TS", "2025-01-01T00:00:00")
AUTOSTART       = os.getenv("AUTOSTART", "false").lower() == "true"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH        = OUTPUT_DIR / "solar_stream.csv"
STATE_PATH      = OUTPUT_DIR / "simulator_state.json"


# ─────────────────────────────────────────────────────────────────
#  Estado global
# ─────────────────────────────────────────────────────────────────

class GeneratorState:
    def __init__(self):
        self.running: bool = False
        self.step_count: int = 0
        self.total_records: int = 0
        self.total_faults: int = 0
        self.last_ts: Optional[str] = None
        self.last_step_at: Optional[str] = None
        self.started_at: Optional[str] = None
        self.stopped_at: Optional[str] = None
        self.errors: int = 0
        self.simulator: Optional[MultiPlantSimulator] = None
        self._task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        fault_rate = round(self.total_faults / max(1, self.total_records) * 100, 2)
        return {
            "running":        self.running,
            "step_count":     self.step_count,
            "total_records":  self.total_records,
            "total_faults":   self.total_faults,
            "fault_rate_pct": fault_rate,
            "last_ts":        self.last_ts,
            "last_step_at":   self.last_step_at,
            "started_at":     self.started_at,
            "stopped_at":     self.stopped_at,
            "errors":         self.errors,
            "csv_path":       str(CSV_PATH),
            "config": {
                "step_delay_s":    STEP_DELAY_S,
                "n_plants":        N_PLANTS,
                "fault_level":     FAULT_LEVEL,
                "api_target":      API_URL or "(none — solo CSV)",
                "autostart":       AUTOSTART,
            },
        }


GEN = GeneratorState()


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _sanitize(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Quita _meta, limpia NaN/Inf, garantiza tipos API-safe."""
    clean = {k: v for k, v in rec.items() if k != "_meta"}
    for k, v in clean.items():
        if isinstance(v, float) and not np.isfinite(v):
            clean[k] = None
    if clean.get("fault_type") is None:
        clean["fault_type"] = ""
    return clean


def _append_csv(records: List[Dict[str, Any]]):
    df = pd.DataFrame(records)
    header = not CSV_PATH.exists()
    df.to_csv(CSV_PATH, mode="a", header=header, index=False)


def _save_state():
    STATE_PATH.write_text(json.dumps(GEN.to_dict(), indent=2), encoding="utf-8")


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _to_utc_iso(ts_str: str) -> str:
    dt = pd.to_datetime(ts_str, errors="coerce")
    if pd.isna(dt):
        return ts_str
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_to_api(records: List[Dict[str, Any]]) -> bool:
    if not API_URL:
        return False
    url = API_URL.rstrip("/") + INGEST_ENDPOINT
    payload = {"readings": [{**r, "ts": _to_utc_iso(r["ts"])} for r in records]}
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code < 400:
                return True
            log.warning("API HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        except Exception as e:
            wait = 1.5 * (attempt + 1)
            log.warning("API error intento %d: %s — reintentando en %.1fs", attempt + 1, e, wait)
            time.sleep(wait)
    return False


# ─────────────────────────────────────────────────────────────────
#  Un paso de generación
# ─────────────────────────────────────────────────────────────────

async def _execute_step() -> List[Dict[str, Any]]:
    raw = GEN.simulator.step_all()
    clean = [_sanitize(r) for r in raw]

    _append_csv(clean)

    if API_URL:
        loop = asyncio.get_event_loop()
        for i in range(0, len(clean), BATCH_SIZE):
            # run_in_executor para no bloquear el event loop durante reintentos
            await loop.run_in_executor(None, _post_to_api, clean[i:i + BATCH_SIZE])

    n_faults = sum(1 for r in clean if r.get("label_is_fault"))
    GEN.step_count    += 1
    GEN.total_records += len(clean)
    GEN.total_faults  += n_faults
    GEN.last_ts        = clean[-1]["ts"] if clean else GEN.last_ts
    GEN.last_step_at   = datetime.now(timezone.utc).isoformat()

    return clean


# ─────────────────────────────────────────────────────────────────
#  Background loop (asyncio)
# ─────────────────────────────────────────────────────────────────

async def _generation_loop():
    log.info("▶ Generación arrancada — delay=%.1fs plantas=%d fault_level=%d",
             STEP_DELAY_S, N_PLANTS, FAULT_LEVEL)
    while GEN.running:
        try:
            await _execute_step()
            if GEN.step_count % 50 == 0:
                _save_state()
                log.info("step=%d records=%d faults=%d (%.1f%%) last_ts=%s",
                         GEN.step_count, GEN.total_records, GEN.total_faults,
                         GEN.total_faults / max(1, GEN.total_records) * 100,
                         GEN.last_ts)
        except Exception as e:
            GEN.errors += 1
            log.error("Error en step %d: %s", GEN.step_count, e, exc_info=True)

        await asyncio.sleep(STEP_DELAY_S)

    log.info("⏹ Generación detenida. steps=%d records=%d", GEN.step_count, GEN.total_records)
    _save_state()


def _build_simulator(start_ts: Optional[str] = None) -> MultiPlantSimulator:
    ts_str = start_ts or GEN.last_ts or START_TS_STR
    ts = pd.Timestamp(ts_str)
    profiles = build_plant_profiles(N_PLANTS, FAULT_LEVEL)
    return MultiPlantSimulator(profiles, start_ts=ts)


# ─────────────────────────────────────────────────────────────────
#  Lifespan
# ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ─────────────────────────────────────────────────
    prev = _load_state()
    GEN.step_count    = int(prev.get("step_count", 0))
    GEN.total_records = int(prev.get("total_records", 0))
    GEN.total_faults  = int(prev.get("total_faults", 0))
    GEN.last_ts       = prev.get("last_ts")

    GEN.simulator = _build_simulator()
    log.info("Simulador inicializado. plantas=%d autostart=%s", N_PLANTS, AUTOSTART)

    if AUTOSTART:
        GEN.running    = True
        GEN.started_at = datetime.now(timezone.utc).isoformat()
        GEN._task      = asyncio.create_task(_generation_loop())

    yield  # ── App corriendo ─────────────────────────────────────

    # ── Shutdown limpio ─────────────────────────────────────────
    if GEN.running:
        GEN.running = False
        if GEN._task:
            GEN._task.cancel()
            try:
                await asyncio.wait_for(GEN._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
    _save_state()
    log.info("Servicio detenido limpiamente.")


# ─────────────────────────────────────────────────────────────────
#  FastAPI app
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Solar Simulator Service",
    description=(
        "Genera datos sintéticos de plantas fotovoltaicas hacia CSV y/o API.\n\n"
        "El contenedor arranca **detenido**. Usa `/start` para comenzar y `/stop` para pausar."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


# ── Schemas ─────────────────────────────────────────────────────

class StartRequest(BaseModel):
    start_ts: Optional[str] = None   # Sobreescribe checkpoint
    reset_csv: bool = False           # Borra el CSV antes de arrancar

class StepRequest(BaseModel):
    n_steps: int = 1                  # 1 – 10 000


# ── Endpoints ────────────────────────────────────────────────────

@app.get("/health", tags=["control"])
def health():
    """Healthcheck mínimo para Docker/K8s."""
    return {"status": "ok", "running": GEN.running}


@app.get("/status", tags=["control"])
def status():
    """Estado completo del servicio."""
    return JSONResponse(GEN.to_dict())


@app.post("/start", tags=["control"])
async def start(req: StartRequest = StartRequest()):
    """
    Arranca la generación continua en background.
    Si ya está corriendo devuelve 409.
    """
    if GEN.running:
        raise HTTPException(409, "El generador ya está corriendo. Usa /stop primero.")

    if req.reset_csv and CSV_PATH.exists():
        CSV_PATH.unlink()
        log.info("CSV eliminado (reset_csv=true)")

    if req.start_ts:
        GEN.simulator = _build_simulator(req.start_ts)

    GEN.running    = True
    GEN.started_at = datetime.now(timezone.utc).isoformat()
    GEN.stopped_at = None
    GEN._task      = asyncio.create_task(_generation_loop())

    log.info("Generación iniciada vía POST /start")
    return {"status": "started", "started_at": GEN.started_at, **GEN.to_dict()}


@app.post("/stop", tags=["control"])
async def stop():
    """
    Pausa la generación. El contenedor sigue vivo y el estado se conserva.
    Puedes reanudar con /start.
    """
    if not GEN.running:
        raise HTTPException(409, "El generador ya está detenido.")

    GEN.running    = False
    GEN.stopped_at = datetime.now(timezone.utc).isoformat()

    if GEN._task:
        try:
            await asyncio.wait_for(GEN._task, timeout=10.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            GEN._task.cancel()

    _save_state()
    log.info("Generación detenida vía POST /stop")
    return {"status": "stopped", "stopped_at": GEN.stopped_at, **GEN.to_dict()}


@app.post("/step", tags=["control"])
async def manual_step(req: StepRequest = StepRequest()):
    """
    Ejecuta N pasos manualmente sin activar el loop continuo.
    Ideal para rellenar datos iniciales o pruebas.
    """
    if req.n_steps < 1 or req.n_steps > 10_000:
        raise HTTPException(422, "n_steps debe estar entre 1 y 10 000.")

    all_records: List[Dict[str, Any]] = []
    for _ in range(req.n_steps):
        all_records.extend(_execute_step())

    _save_state()
    return {
        "status":            "ok",
        "steps_executed":    req.n_steps,
        "records_generated": len(all_records),
        "faults_in_batch":   sum(1 for r in all_records if r.get("label_is_fault")),
        "last_ts":           GEN.last_ts,
    }


@app.delete("/reset", tags=["control"])
async def reset():
    """
    Borra CSV y checkpoint, reinicia contadores.
    Requiere que el generador esté detenido.
    """
    if GEN.running:
        raise HTTPException(409, "Detén el generador con /stop antes de hacer reset.")

    if CSV_PATH.exists():
        CSV_PATH.unlink()
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    GEN.step_count    = 0
    GEN.total_records = 0
    GEN.total_faults  = 0
    GEN.errors        = 0
    GEN.last_ts       = None
    GEN.started_at    = None
    GEN.stopped_at    = None
    GEN.simulator     = _build_simulator(START_TS_STR)

    log.info("Reset completo ejecutado")
    return {"status": "reset", "next_start_ts": START_TS_STR}