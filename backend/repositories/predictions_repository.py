from sqlalchemy import text
from backend.db.session import engine

def insert_prediction(row):
    sql = text("""
        INSERT INTO ai_predictions (
            reading_id, model_version,
            expected_power_ac_kw, power_residual_kw,
            fault_proba, fault_pred
        )
        VALUES (
            :reading_id, :model_version,
            :expected_power_ac_kw, :power_residual_kw,
            :fault_proba, :fault_pred
        )
        RETURNING id;
    """)

    with engine.begin() as conn:
        return conn.execute(sql, row).scalar_one()