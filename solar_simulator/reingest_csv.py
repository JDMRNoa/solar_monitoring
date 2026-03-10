"""
reingest_csv.py
Lee solar_stream.csv (o el backup más reciente) y lo envía al backend en batches via POST /ingest_batch.

Uso:
    python reingest_csv.py                                          # auto: último backup en /app/output/backups/
    python reingest_csv.py --csv /app/output/solar_stream.csv      # archivo específico
    python reingest_csv.py --url http://backend:8000 --batch 200
"""

import argparse
import glob
import json
import math
import os
import sys
import urllib.request
import urllib.error

import pandas as pd


def find_latest_backup(backups_dir: str) -> str | None:
    """Busca el CSV más reciente en backups_dir."""
    pattern = os.path.join(backups_dir, "*.csv")
    files = sorted(glob.glob(pattern))
    if files:
        return files[-1]  # orden alfabético = cronológico por nombre de fecha
    return None


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--csv",         default=None,
                   help="Ruta al CSV. Si no se pasa, usa el más reciente en --backups-dir")
    p.add_argument("--backups-dir", default="/app/output/backups",
                   help="Carpeta donde buscar backups si no se especifica --csv")
    p.add_argument("--url",         default="http://backend:8000")
    p.add_argument("--batch",       type=int, default=200)
    return p.parse_args()


def post_batch(url: str, readings: list) -> dict:
    payload = json.dumps({"readings": readings}).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/ingest_batch",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    args = parse_args()

    # ── Resolver el CSV a usar ────────────────────────────────────────────────
    csv_path = args.csv
    if csv_path is None:
        csv_path = find_latest_backup(args.backups_dir)
        if csv_path is None:
            # Fallback: solar_stream.csv en /app/output/
            fallback = "/app/output/solar_stream.csv"
            if os.path.exists(fallback):
                csv_path = fallback
                print(f"Sin backups encontrados — usando fallback: {fallback}")
            else:
                print(f"ERROR — no se encontro ningun CSV en {args.backups_dir} ni en /app/output/")
                sys.exit(1)
        else:
            print(f"Backup mas reciente encontrado: {csv_path}")
    else:
        if not os.path.exists(csv_path):
            print(f"ERROR — archivo no encontrado: {csv_path}")
            sys.exit(1)

    # ── Leer CSV ──────────────────────────────────────────────────────────────
    print(f"Leyendo {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"  Filas totales: {len(df):,}")

    df.columns = [c.strip().lower() for c in df.columns]

    required = [
        "ts", "plant_id", "inverter_id",
        "irradiance_wm2", "temp_ambient_c", "temp_module_c",
        "power_ac_kw", "power_dc_kw", "energy_daily_kwh", "energy_total_kwh",
        "label_is_fault", "fault_type", "fault_severity",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR — columnas faltantes en CSV: {missing}")
        print(f"Columnas disponibles: {list(df.columns)}")
        sys.exit(1)

    df = df[required].copy()

    # ── Limpiar NaN ANTES de serializar ──────────────────────────────────────
    df["ts"]             = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    # Integer columns
    df["label_is_fault"] = df["label_is_fault"].fillna(0).astype(int)
    df["fault_severity"] = df["fault_severity"].fillna(0).astype(int)
    df["plant_id"]       = df["plant_id"].fillna(1).astype(int)
    # String columns — fill all object columns (fault_type, inverter_id, etc.)
    str_cols = df.select_dtypes(include=["object"]).columns.tolist()
    df[str_cols] = df[str_cols].fillna("")
    # Float columns — fill any remaining NaN with 0.0
    float_cols = df.select_dtypes(include=["float", "float64"]).columns.tolist()
    df[float_cols] = df[float_cols].fillna(0.0)

    # ── Enviar en batches ─────────────────────────────────────────────────────
    total   = len(df)
    n_batch = math.ceil(total / args.batch)
    ok      = 0
    errors  = 0

    print(f"  Enviando {total:,} registros en {n_batch} batches de {args.batch} -> {args.url}")

    for i in range(n_batch):
        chunk   = df.iloc[i * args.batch : (i + 1) * args.batch]
        # to_dict is safe now — no NaN left in any column
        records = chunk.to_dict(orient="records")

        try:
            res  = post_batch(args.url, records)
            ok  += res.get("inserted_readings", 0)
        except urllib.error.HTTPError as e:
            errors += 1
            print(f"  [batch {i+1}] HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            errors += 1
            print(f"  [batch {i+1}] ERROR: {e}")

        if (i + 1) % 50 == 0 or (i + 1) == n_batch:
            pct = round((i + 1) / n_batch * 100)
            print(f"  [{pct:3d}%] {i+1}/{n_batch} batches — {ok:,} insertados, {errors} errores")

    print(f"\nListo. Insertados: {ok:,} / {total:,} | Errores: {errors}")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()