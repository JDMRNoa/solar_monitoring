import threading
import time
import os
from fastapi import FastAPI
from simulator_core import MultiPlantSimulator
import requests
import pandas as pd

app = FastAPI()

# ─────────────────────────────────────────
# Estado global
# ─────────────────────────────────────────

SIM_RUNNING = False
SIM_THREAD = None

API_URL = os.getenv("SOLAR_API_URL", "http://backend:8000")
INGEST_ENDPOINT = os.getenv("SOLAR_INGEST_ENDPOINT", "/ingest_batch")
STEP_DELAY = float(os.getenv("SOLAR_STEP_DELAY", "2.0"))
PLANTS = int(os.getenv("SOLAR_PLANTS", "4"))

simulator = MultiPlantSimulator()
lock = threading.Lock()

# ─────────────────────────────────────────
# Loop de simulación
# ─────────────────────────────────────────

def simulation_loop():
    global SIM_RUNNING
    while True:
        if SIM_RUNNING:
            with lock:
                df = simulator.run_batch(1)

            try:
                requests.post(
                    f"{API_URL}{INGEST_ENDPOINT}",
                    json={"readings": df.to_dict(orient="records")},
                    timeout=5
                )
            except Exception as e:
                print("Error enviando datos:", e)

        time.sleep(STEP_DELAY)


# ─────────────────────────────────────────
# Endpoints de control
# ─────────────────────────────────────────

@app.post("/start")
def start():
    global SIM_RUNNING
    SIM_RUNNING = True
    return {"status": "running"}

@app.post("/pause")
def pause():
    global SIM_RUNNING
    SIM_RUNNING = False
    return {"status": "paused"}

@app.post("/reset")
def reset():
    global simulator
    with lock:
        simulator = MultiPlantSimulator()
    return {"status": "reset"}

@app.get("/status")
def status():
    return {
        "running": SIM_RUNNING,
        "step_delay": STEP_DELAY
    }


# ─────────────────────────────────────────
# Arranque del thread al iniciar servicio
# ─────────────────────────────────────────

@app.on_event("startup")
def startup_event():
    global SIM_THREAD
    SIM_THREAD = threading.Thread(target=simulation_loop, daemon=True)
    SIM_THREAD.start()