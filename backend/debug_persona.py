import requests
import json
import os

OLLAMA_URL = "http://ollama:11434"
OLLAMA_MODEL = "phi3.5:latest"

def test_prompt(name, messages, options=None):
    print(f"\n--- TEST: {name} ---")
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": options or {"temperature": 0.0}
    }
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=20)
        if resp.status_code == 200:
            content = resp.json()['message']['content']
            print(f"RESPONSE:\n{content}")
        else:
            print(f"ERROR {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"EXCEPTION: {str(e)}")

# 1. Standard System Role
test_prompt("System Role only", [
    {"role": "system", "content": "Rersponde UNICAMENTE 'SOLO SOLAR'. No digas nada mas."},
    {"role": "user", "content": "¿Qué puedes hacer?"}
])

# 2. User Role for Instructions
test_prompt("User Role Instruct", [
    {"role": "user", "content": "REGLA CRITICA: Responde UNICAMENTE 'SOLO SOLAR'. No digas nada mas. ¿Qué puedes hacer?"}
])

# 3. Few-Shot + Temperature 0
test_prompt("Few-Shot + Temp 0", [
    {"role": "system", "content": "Eres SOLAREX. Especialista solar. Niega temas generales."},
    {"role": "user", "content": "Ayudame con mi tarea"},
    {"role": "assistant", "content": "Lo siento, soy SOLAREX y solo hago diagnostico solar."},
    {"role": "user", "content": "Hola, ¿que puedes hacer?"}
])
