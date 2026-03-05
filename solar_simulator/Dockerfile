FROM python:3.11-slim

WORKDIR /app

# Dependencias primero (cache layer)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Código
COPY simulator_core.py simulator_service.py ./

# Directorio de salida (montar como volumen en producción)
RUN mkdir -p /app/output

EXPOSE 9000

# Arranca DETENIDO por defecto.
# Para que arranque automáticamente: -e AUTOSTART=true
CMD ["python", "-m", "uvicorn", "simulator_service:app", "--host", "0.0.0.0", "--port", "9000"]
