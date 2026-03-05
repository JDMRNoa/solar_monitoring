import pandas as pd
from backend.repositories.readings_repository import insert_reading
from backend.repositories.predictions_repository import insert_prediction
from backend.ml.registry import predict_batch

def ingest_single(payload):
    df = pd.DataFrame([payload.model_dump()])
    df["ts"] = pd.to_datetime(df["ts"], errors="raise")

    row = df.iloc[0].to_dict()
    row["ts"] = row["ts"].to_pydatetime()

    reading_id = insert_reading(row)

    expected, residual, proba, pred = predict_batch(df)

    pred_id = insert_prediction({
        "reading_id": reading_id,
        "model_version": "v1",
        "expected_power_ac_kw": float(expected[0]),
        "power_residual_kw": float(residual[0]),
        "fault_proba": float(proba[0]),
        "fault_pred": int(pred[0]),
    })

    return {
        "reading_id": reading_id,
        "prediction_id": pred_id,
        "expected_power_ac_kw": float(expected[0]),
        "power_residual_kw": float(residual[0]),
        "fault_probability": float(proba[0]),
        "fault_prediction": int(pred[0]),
    }