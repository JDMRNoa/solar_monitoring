# backend/api/routers/chat.py
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import json
import requests

from backend.db.session import get_db
from backend.core.security import get_current_user
from backend.services.dashboard_service import get_summary, get_fault_packages

router = APIRouter(prefix="/chat", tags=["chat"])

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3.5:latest")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    plant_id: int
    period_hours: int
    messages: List[ChatMessage]

@router.post("/")
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # 1. Fetch live context from the DB
    try:
        summary = get_summary(db, request.plant_id, request.period_hours)
    except Exception as e:
        summary = {"error": str(e)}

    # Gather recent faults to give context on PR drops
    # We use a higher min_proba (0.5) to match the "Events" log the user sees
    fault_packages = get_fault_packages(db, plant_id=request.plant_id, hours=request.period_hours, min_proba=0.5)
    faults_info = "Sin fallas significativas detectadas en el periodo."
    event_details = ""
    if fault_packages:
        count = len(fault_packages)
        faults_info = f"Se detectaron {count} eventos de falla (agrupación de lecturas anómalas)."
        types = set(f.get("fault_type_pred", "unknown") for f in fault_packages)
        event_details = "\nDETALLE DE EVENTOS:\n"
        for i, pkg in enumerate(fault_packages[:5], 1):
             event_details += f"- Evento {i}: {pkg.get('fault_type_pred')} (Prob: {pkg.get('max_fault_proba',0)*100:.1f}%, Lecturas: {pkg.get('reading_count')})\n"

    # 2. Build the System Prompt
    system_prompt = f"""### INSTRUCCIONES ESTRICTAS DE PERSONA ###
- Tu nombre es SOLAREX-AI.
- Eres ÚNICAMENTE un analizador técnico de telemetría solar. No eres un asistente general, ni una IA de propósito múltiple.
- ESTÁ PROHIBIDO responder saludos con listas de tus capacidades generales (ej. "puedo ayudarte con tareas, idiomas, etc.").
- Si el usuario te saluda, responde saludando y preguntando qué anomalía solar quieres revisar hoy, basándote en los datos de la planta {request.plant_id}.
- Si el usuario pregunta algo fuera de energía solar, fotovoltaica o este dashboard específico, RESPONDE SIEMPRE: "Lo siento, soy un modelo especializado exclusivamente en diagnóstico solar y no puedo asistir con otros temas."

### CONOCIMIENTO DE LA ARQUITECTURA DEL SISTEMA ###
- Backend: FastAPI (Python), DB: PostgreSQL.
- Frontend: React + Vite + TailwindCSS + Recharts.
- Simulación: Datos sintéticos generados por `solar_simulator`.
- Modelos ML: Clasificador de fallas Scikit-learn (Joblib).

### CONTEXTO DE OPERACIÓN (Planta {request.plant_id}, Últimas {request.period_hours}h) ###
- Datos analizados: {summary.get('total_readings', 0)} lecturas.
- Potencia: Media {summary.get('avg_power', 0):.2f} kW / Máx {summary.get('max_power', 0):.2f} kW.
- Estado de Fallas: {faults_info}{event_details}
- Riesgo ML: {summary.get('max_fault_proba', 0)*100:.1f}% de probabilidad de falla.

### ESTILO DE RESPUESTA ###
- Idioma: Español.
- Tono: Profesional, seco, técnico.
- Longitud: Máximo 3 párrafos cortos. No divagues.
"""

    # 3. Format messages for Ollama API
    # Prepend the system prompt and FEW-SHOT examples to force the persona
    ollama_messages = [
        {"role": "system", "content": system_prompt},
        # Example 1: Strict rejection
        {"role": "user", "content": "Hola, ¿puedes ayudarme con mi tarea de historia?"},
        {"role": "assistant", "content": "Lo siento, soy SOLAREX-AI, un modelo especializado exclusivamente en diagnóstico solar. Solo puedo asistirte con métricas de esta planta fotovoltaica y temas relacionados con energía solar."},
        # Example 2: Strict greeting
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola. Soy SOLAREX-AI. Detecto que la planta {request.plant_id} tiene un riesgo de falla del {summary.get('max_fault_proba', 0)*100:.1f}%. ¿Qué anomalía quieres lanzar hoy?"},
    ]
    for msg in request.messages:
        ollama_messages.append({"role": msg.role, "content": msg.content})

    # 4. Stream from Ollama
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": ollama_messages,
                "stream": True
            },
            stream=True,
                timeout=(5, 60) # Connect timeout 5s, read timeout 60s
        )
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error conectando con Ollama: {str(e)}")

    def stream_generator():
        # Using iter_lines to yield full JSON objects from Ollama's NDJSON stream
        for line in resp.iter_lines():
            if line:
                yield line + b"\n"

    return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
