from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "ml" / "artifacts"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://solar_user:solar_pass@localhost:5432/solar_db"
)