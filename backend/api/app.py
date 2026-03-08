from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routers import ingestion, dashboard_routers, live, explain, auth, admin

app = FastAPI(title="Solar Monitoring AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(ingestion.router)
app.include_router(dashboard_routers.router)
app.include_router(live.router)
app.include_router(explain.router)
app.include_router(auth.router)
app.include_router(admin.router)