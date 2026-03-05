# backend/services/event_bus.py
"""
Cola en memoria para broadcast SSE.
No requiere Redis ni ninguna dependencia externa.
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, Any

# Una cola por cliente conectado
_subscribers: list[asyncio.Queue] = []


def publish(data: Dict[str, Any]) -> None:
    """Llamado desde ingestion_service al recibir datos del simulador."""
    msg = json.dumps(data)
    for q in list(_subscribers):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # cliente lento — se descarta


async def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass