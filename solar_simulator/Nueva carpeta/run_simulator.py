# solar_simulator/run_simulator.py
"""
Orquestador del simulador solar.
- Genera datos en tiempo real o en batch
- Guarda CSV local
- Envía a API via HTTP POST (compatible con stream_publisher.py existente)

Uso:
  python run_simulator.py                          # Modo continuo (tiempo real)
  python run_simulator.py --batch 96              # Batch de 96 pasos (1 día)
  python run_simulator.py --api http://localhost:8000  # Con envío a API
  python run_simulator.py --plants 4 --batch 288  # 4 plantas, 3 días
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

# Agrega el directorio al path para importar simulator_core
sys.path.insert(0, str(Path(__file__).parent))
from simulator_core import MultiPlantSimulator, PlantConfig, FaultType


# ─────────────────────────────────────────────
#  Config por defecto
# ─────────────────────────────────────────────

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_CSV_NAME   = "solar_stream.csv"
DEFAULT_STATE_FILE = "simulator_state.json"
DEFAULT_STEP_DELAY = 2.0  # segundos entre pasos en modo real-time
DEFAULT_BATCH_SIZE = 50   # registros por POST a API


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _sanitize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Limpia NaN/Inf y remueve metadata antes de enviar/guardar."""
    clean = {k: v for k, v in rec.items() if k != "_meta"}
    for k, v in clean.items():
        if isinstance(v, float):
            if not np.isfinite(v):
                clean[k] = None
    if clean.get("fault_type") is None:
        clean["fault_type"] = ""
    return clean


def _to_utc_iso(ts_str: str) -> str:
    dt = pd.to_datetime(ts_str, errors="coerce")
    if dt is pd.NaT:
        return ts_str
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(state_path: Path) -> Dict[str, Any]:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state_path: Path, state: Dict[str, Any]):
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
#  Publisher HTTP
# ─────────────────────────────────────────────

class APIPublisher:
    def __init__(self, base_url: str, endpoint: str = "/ingest_batch",
                 batch_size: int = DEFAULT_BATCH_SIZE, timeout: int = 30, retries: int = 3):
        self.url = base_url.rstrip("/") + endpoint
        self.batch_size = batch_size
        self.timeout = timeout
        self.retries = retries

    def send(self, records: List[Dict[str, Any]]) -> bool:
        payload = {"readings": records}
        for attempt in range(self.retries):
            try:
                r = requests.post(self.url, json=payload, timeout=self.timeout)
                if r.status_code < 400:
                    return True
                print(f"  ⚠️  API respondió HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                wait = 1.5 * (attempt + 1)
                print(f"  ⚠️  Error API (intento {attempt+1}/{self.retries}): {e}")
                time.sleep(wait)
        return False

    def send_batch_chunked(self, records: List[Dict[str, Any]]) -> int:
        sent = 0
        for i in range(0, len(records), self.batch_size):
            chunk = records[i:i + self.batch_size]
            # Convertir ts a ISO UTC
            for rec in chunk:
                rec["ts"] = _to_utc_iso(rec["ts"])
            if self.send(chunk):
                sent += len(chunk)
        return sent


# ─────────────────────────────────────────────
#  Runner principal
# ─────────────────────────────────────────────

class SimulatorRunner:
    def __init__(
        self,
        n_plants: int = 4,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        api_url: Optional[str] = None,
        api_endpoint: str = "/ingest_batch",
        start_ts: Optional[str] = None,
        fault_level: int = 2,         # 1=poco, 5=muchas fallas
        enable_soiling: bool = True,
        verbose: bool = True,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = output_dir / DEFAULT_CSV_NAME
        self.state_path = output_dir / DEFAULT_STATE_FILE
        self.verbose = verbose

        # Cargar estado previo
        prev_state = load_state(self.state_path)
        ts_str = start_ts or prev_state.get("last_ts") or "2025-01-01 00:00:00"
        ts = pd.Timestamp(ts_str)

        # Crear plantas
        plant_configs = self._build_plant_configs(n_plants, fault_level, enable_soiling)
        self.simulator = MultiPlantSimulator(plant_configs, start_ts=ts)

        # Publisher opcional
        self.publisher = APIPublisher(api_url, api_endpoint) if api_url else None

        self._total_records = int(prev_state.get("total_records", 0))
        self._total_faults = int(prev_state.get("total_faults", 0))

    def _build_plant_configs(self, n: int, fault_level: int, enable_soiling: bool) -> List[PlantConfig]:
        """Genera configuraciones variadas de plantas."""
        fault_scale = {1: 0.3, 2: 0.6, 3: 1.0, 4: 1.8, 5: 3.0}.get(fault_level, 1.0)

        base_probs = {
            FaultType.INVERTER_DERATE: 0.0015 * fault_scale,
            FaultType.SENSOR_FLATLINE: 0.0008 * fault_scale,
            FaultType.PANEL_SOILING:   0.0,
            FaultType.STRING_FAULT:    0.0006 * fault_scale,
            FaultType.PID_EFFECT:      0.0,
            FaultType.GRID_DISCONNECT: 0.0004 * fault_scale,
            FaultType.MPPT_FAILURE:    0.0010 * fault_scale,
            FaultType.PARTIAL_SHADING: 0.0020 * fault_scale,
        }

        templates = [
            dict(plant_id=1, name="Planta Norte – Atlántico",  latitude=10.99, longitude=-74.78,
                 capacity_kw=120.0, panel_count=350, inverter_count=4, tilt_deg=12),
            dict(plant_id=2, name="Planta Sur – Cundinamarca", latitude=4.71,  longitude=-74.07,
                 capacity_kw=85.0,  panel_count=250, inverter_count=3, tilt_deg=8),
            dict(plant_id=3, name="Planta Este – Antioquia",   latitude=6.25,  longitude=-75.56,
                 capacity_kw=200.0, panel_count=580, inverter_count=6, tilt_deg=15),
            dict(plant_id=4, name="Planta Oeste – Valle",      latitude=3.43,  longitude=-76.52,
                 capacity_kw=60.0,  panel_count=180, inverter_count=2, tilt_deg=10),
            dict(plant_id=5, name="Planta Centro – Boyacá",    latitude=5.53,  longitude=-73.36,
                 capacity_kw=150.0, panel_count=430, inverter_count=5, tilt_deg=18),
            dict(plant_id=6, name="Planta Caribe",             latitude=11.24, longitude=-74.20,
                 capacity_kw=250.0, panel_count=720, inverter_count=8, tilt_deg=10),
            dict(plant_id=7, name="Planta Llanos",             latitude=4.15,  longitude=-73.63,
                 capacity_kw=90.0,  panel_count=270, inverter_count=3, tilt_deg=5),
            dict(plant_id=8, name="Planta Sierra Nevada",      latitude=11.0,  longitude=-74.05,
                 capacity_kw=180.0, panel_count=520, inverter_count=6, tilt_deg=20),
        ]

        configs = []
        for i in range(min(n, len(templates))):
            t = templates[i]
            # Variaciones únicas por planta
            plant_probs = {k: v * (0.7 + 0.6 * ((i * 17 + 3) % 7) / 7) for k, v in base_probs.items()}

            init_soiling = 0.05 * i if enable_soiling else 0.0
            cfg = PlantConfig(
                **t,
                soiling_level=init_soiling,
                degradation_pct=0.1 * i,
                fault_probs=plant_probs,
            )
            configs.append(cfg)

        return configs

    def _append_to_csv(self, records: List[Dict[str, Any]]):
        df = pd.DataFrame(records)
        header = not self.csv_path.exists()
        df.to_csv(self.csv_path, mode="a", header=header, index=False)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def step(self) -> List[Dict[str, Any]]:
        """Ejecuta un paso de simulación para todas las plantas."""
        raw_records = self.simulator.step_all()
        clean_records = [_sanitize_record(r) for r in raw_records]

        # Guardar CSV
        self._append_to_csv(clean_records)

        # Enviar a API si configurada
        if self.publisher:
            sent = self.publisher.send_batch_chunked(
                [{**r, "ts": _to_utc_iso(r["ts"])} for r in clean_records]
            )
            if sent:
                self._log(f"  ✅ Enviados {sent} registros a API")

        # Stats
        n_faults = sum(1 for r in clean_records if r["label_is_fault"])
        self._total_records += len(clean_records)
        self._total_faults += n_faults

        return clean_records

    def run_batch(self, n_steps: int) -> pd.DataFrame:
        """Ejecuta n_steps y retorna DataFrame."""
        all_records = []
        for i in range(n_steps):
            records = self.step()
            all_records.extend(records)
            if i % 10 == 0:
                faults_this = sum(r["label_is_fault"] for r in records)
                fault_types = [r["fault_type"] for r in records if r["fault_type"]]
                self._log(f"  Step {i+1}/{n_steps} | Fallas activas: {faults_this} {fault_types}")

        df = pd.DataFrame(all_records)
        self._save_state()
        return df

    def run_realtime(self, step_delay_s: float = DEFAULT_STEP_DELAY):
        """Corre indefinidamente simulando tiempo real."""
        self._log("🌞 Simulador solar iniciado (modo real-time). Ctrl+C para detener.")
        self._log(f"   Plantas: {len(self.simulator.simulators)}")
        self._log(f"   CSV: {self.csv_path}")
        if self.publisher:
            self._log(f"   API: {self.publisher.url}")
        print()

        try:
            step = 0
            while True:
                records = self.step()
                step += 1

                if self.verbose:
                    ts = records[0]["ts"] if records else "?"
                    faults = [(r["plant_id"], r["fault_type"]) for r in records if r["fault_type"]]
                    print(f"[{step:>5}] ts={ts} | Records: {len(records)} | "
                          f"Faults: {len(faults)} {faults if faults else ''}")

                self._save_state()
                time.sleep(step_delay_s)

        except KeyboardInterrupt:
            print("\n🛑 Simulador detenido.")
            self._save_state()

    def _save_state(self):
        last_ts = None
        for sim in self.simulator.simulators.values():
            ts = sim.current_ts.isoformat()
            if last_ts is None or ts > last_ts:
                last_ts = ts
        save_state(self.state_path, {
            "last_ts": last_ts,
            "total_records": self._total_records,
            "total_faults": self._total_faults,
        })

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_records": self._total_records,
            "total_faults": self._total_faults,
            "fault_rate_pct": round(self._total_faults / max(1, self._total_records) * 100, 2),
            "csv_path": str(self.csv_path),
            "plants": len(self.simulator.simulators),
        }


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Solar Plant Simulator")
    parser.add_argument("--plants",    type=int,   default=4,         help="Número de plantas (1-8)")
    parser.add_argument("--batch",     type=int,   default=None,      help="Pasos batch (None=tiempo real)")
    parser.add_argument("--api",       type=str,   default=None,      help="URL API p.ej. http://localhost:8000")
    parser.add_argument("--endpoint",  type=str,   default="/ingest_batch")
    parser.add_argument("--delay",     type=float, default=2.0,       help="Delay segundos entre pasos (real-time)")
    parser.add_argument("--fault-level", type=int, default=2,         help="Nivel de fallas 1-5")
    parser.add_argument("--start-ts",  type=str,   default=None,      help="Timestamp inicio ISO")
    parser.add_argument("--output",    type=str,   default=str(DEFAULT_OUTPUT_DIR), help="Dir salida")
    parser.add_argument("--no-soiling", action="store_true",          help="Deshabilitar suciedad")
    parser.add_argument("--quiet",     action="store_true")
    args = parser.parse_args()

    runner = SimulatorRunner(
        n_plants=min(8, max(1, args.plants)),
        output_dir=Path(args.output),
        api_url=args.api,
        api_endpoint=args.endpoint,
        start_ts=args.start_ts,
        fault_level=args.fault_level,
        enable_soiling=not args.no_soiling,
        verbose=not args.quiet,
    )

    if args.batch:
        print(f"🔄 Generando batch de {args.batch} pasos para {args.plants} plantas...")
        df = runner.run_batch(args.batch)
        stats = runner.get_stats()
        print(f"\n✅ Completado!")
        print(f"   Registros: {stats['total_records']}")
        print(f"   Fallas:    {stats['total_faults']} ({stats['fault_rate_pct']}%)")
        print(f"   CSV:       {stats['csv_path']}")

        # Resumen de fallas por tipo
        if df["label_is_fault"].sum() > 0:
            fault_summary = df[df["label_is_fault"] == 1]["fault_type"].value_counts()
            print(f"\n   Tipos de fallas:")
            for ft, cnt in fault_summary.items():
                print(f"     {ft}: {cnt}")
    else:
        runner.run_realtime(step_delay_s=args.delay)


if __name__ == "__main__":
    main()
