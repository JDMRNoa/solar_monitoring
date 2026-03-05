from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from backend.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_connection():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()