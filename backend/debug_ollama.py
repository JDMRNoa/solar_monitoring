import requests
import json
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3.5:latest")

print(f"DEBUG: OLLAMA_URL={OLLAMA_URL}")
print(f"DEBUG: OLLAMA_MODEL={OLLAMA_MODEL}")

try:
    print("1. Testing GET /api/tags ...")
    resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    print(f"   Status: {resp.status_code}")
    print(f"   Body: {resp.text}")
    
    print(f"2. Testing POST /api/generate with {OLLAMA_MODEL} ...")
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "hi",
        "stream": False
    }
    resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=30)
    print(f"   Status: {resp.status_code}")
    print(f"   Body: {resp.text[:200]}")
    
except Exception as e:
    print(f"FATAL ERROR: {str(e)}")
