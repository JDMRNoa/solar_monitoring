import pandas as pd
from backend.repositories.readings_repository import insert_reading, insert_batch_predictions
from backend.ml.registry import predict_batch


def ingest_single(payload, db):
    """
    Ingesta una sola lectura. predict_batch retorna list[dict] — API actual.
    Requiere db = Session de SQLAlchemy (inyectada por FastAPI).
    """
    df = pd.DataFrame([payload.model_dump()])
    df["ts"] = pd.to_datetime(df["ts"], errors="raise")

    row = df.iloc[0].to_dict()
    row["ts"] = row["ts"].to_pydatetime()

    reading_id = insert_reading(db, row)

    # predict_batch retorna list[dict], NO una tupla
    preds = predict_batch(df)
    pred = preds[0] if preds else {
        "expected_power_ac_kw": 0.0,
        "power_residual_kw":    0.0,
        "fault_proba":          0.0,
        "fault_pred":           0,
    }

    insert_batch_predictions(db, [reading_id], [pred])
    db.commit()

    return {
        "reading_id":           reading_id,
        "expected_power_ac_kw": pred["expected_power_ac_kw"],
        "power_residual_kw":    pred["power_residual_kw"],
        "fault_probability":    pred["fault_proba"],
        "fault_prediction":     pred["fault_pred"],
    }