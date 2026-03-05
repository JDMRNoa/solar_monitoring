from backend.ingestion.schemas import ReadingIn, BatchIn
from backend.services.monitoring_service import ingest_single

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.services.ingestion_service import ingest_batch_service

router = APIRouter(tags=["ingestion"])

@router.post("/ingest_batch")
def ingest_batch(payload: BatchIn, db: Session = Depends(get_db)):
    return ingest_batch_service(payload, db)

