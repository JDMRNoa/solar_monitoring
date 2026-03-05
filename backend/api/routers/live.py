# backend/api/routers/live.py
"""
GET /live/weather  →  SSE stream con datos de clima en tiempo real.
El frontend se suscribe y recibe un evento cada vez que el simulador
manda un batch a /ingest_batch.
"""
from __future__ import annotations

import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.services.event_bus import subscribe, unsubscribe

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/weather")
async def live_weather():
    async def stream():
        q = await subscribe()
        try:
            # Ping inicial para que el browser confirme la conexión
            yield "event: ping\ndata: {}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive cada 30s para evitar que proxies cierren la conexión
                    yield "event: ping\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # nginx: desactiva buffer
        },
    )