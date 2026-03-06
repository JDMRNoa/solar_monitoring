"""
reingest_csv.py
Lee solar_stream.csv y lo envía al backend en batches via POST /ingest_batch.

Uso:
    python reingest_csv.py --csv solar_stream.csv --url http://localhost:8000 --batch 100
"""

import argparse
import json
import math
import sys
import urllib.request
import urllib.error

import pandas as pd


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--csv",   default="solar_stream.csv")
    p.add_argument("--url",   default="http://localhost:8000")
    p.add_argument("--batch", type=int, default=100)
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

    print(f"Leyendo {args.csv}...")
    df = pd.read_csv(args.csv)
    print(f"  Filas totales: {len(df)}")

    # Normalizar columnas — el CSV puede tener nombres distintos
    df.columns = [c.strip().lower() for c in df.columns]

    # Columnas requeridas
    required = ["ts", "plant_id", "irradiance_wm2", "temp_ambient_c", "temp_module_c",
                "power_ac_kw", "power_dc_kw", "energy_daily_kwh", "energy_total_kwh",
                "label_is_fault", "fault_type", "fault_severity"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR — columnas faltantes en CSV: {missing}")
        print(f"Columnas disponibles: {list(df.columns)}")
        sys.exit(1)

    df = df[required].copy()
    df["fault_type"]     = df["fault_type"].fillna("").astype(str)
    df["label_is_fault"] = df["label_is_fault"].fillna(0).astype(int)
    df["fault_severity"] = df["fault_severity"].fillna(0).astype(int)
    df["ts"]             = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S")

    total   = len(df)
    n_batch = math.ceil(total / args.batch)
    ok = 0
    errors = 0

    print(f"  Enviando {total} registros en {n_batch} batches de {args.batch}...")

    for i in range(n_batch):
        chunk = df.iloc[i * args.batch : (i + 1) * args.batch]
        records = chunk.where(pd.notnull(chunk), None).to_dict(orient="records")

        try:
            res = post_batch(args.url, records)
            ok += res.get("inserted_readings", 0)
        except urllib.error.HTTPError as e:
            errors += 1
            print(f"  [batch {i+1}] HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception as e:
            errors += 1
            print(f"  [batch {i+1}] ERROR: {e}")

        if (i + 1) % 50 == 0 or (i + 1) == n_batch:
            pct = round((i + 1) / n_batch * 100)
            print(f"  [{pct}%] {i+1}/{n_batch} batches — {ok} insertados, {errors} errores")

    print(f"\nListo. Insertados: {ok} / {total} | Errores: {errors}")


if __name__ == "__main__":
    main()