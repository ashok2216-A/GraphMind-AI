import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from graphmind.seed import seed
from graphmind.tools import (
    search_company_knowledge,
    trace_service_dependencies,
    get_incident_evidence,
    recall_memory,
    get_graph_snapshot,
)

app = FastAPI(title="GraphMind API", version="0.1.0",
              description="Graph-backed company intelligence and persistent agent memory.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    if os.getenv("AUTO_SEED", "false").lower() in ("true", "1", "yes"):
        try:
            print("AUTO_SEED enabled: seeding demo graph...")
            seed()
            print("Graph seeded successfully.")
        except Exception as exc:
            print(f"AUTO_SEED notice: seeding failed or database not ready: {exc}")

class SearchRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=160)

class ServiceRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=120)

class IncidentRequest(BaseModel):
    incident_id: str = Field(min_length=1, max_length=80)

class MemoryRequest(BaseModel):
    session_key: str = Field(min_length=1, max_length=100)
    keyword: str = Field(default="", max_length=160)

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"name": "GraphMind", "status": "running", "docs": "/docs"}

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    try:
        from graphmind.db import query_rows
        query_rows("RETURN 1 AS ok")
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

@app.post("/seed")
def seed_endpoint():
    try:
        return seed()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/search")
def search(req: SearchRequest):
    return search_company_knowledge(req.keyword)

@app.post("/dependencies")
def dependencies(req: ServiceRequest):
    return trace_service_dependencies(req.service_name)

@app.post("/incident")
def incident(req: IncidentRequest):
    return get_incident_evidence(req.incident_id)

@app.post("/memory/recall")
def memory(req: MemoryRequest):
    return recall_memory(req.session_key, req.keyword)

@app.get("/graph")
def graph():
    return get_graph_snapshot()
