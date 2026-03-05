FROM python:3.11-slim

WORKDIR /app

# Copiamos requirements primero (mejor para cache)
COPY requirements.txt /app/requirements.txt

# Instalamos dependencias
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código
COPY . /app

# Exponemos puerto
EXPOSE 9000

# Arranque usando python -m para evitar problemas de PATH
CMD ["python", "-m", "uvicorn", "simulator_service:app", "--host", "0.0.0.0", "--port", "9000"]