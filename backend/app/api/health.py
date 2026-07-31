"""헬스 체크 — DB/Qdrant/Ollama 상태 점검."""
from __future__ import annotations

import httpx
from fastapi import APIRouter

from backend.app.core.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/deps")
def health_deps() -> dict:
    s = get_settings()
    out: dict = {"qdrant": False, "ollama": False}

    try:
        r = httpx.get(f"{s.qdrant_url}/collections/{s.qdrant_collection}", timeout=3.0)
        out["qdrant"] = r.status_code == 200
    except Exception as e:
        out["qdrant_err"] = str(e)[:120]

    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=3.0)
        out["ollama"] = r.status_code == 200
        if out["ollama"]:
            tags = r.json().get("models", [])
            out["ollama_models"] = [m.get("name") for m in tags][:10]
    except Exception as e:
        out["ollama_err"] = str(e)[:120]

    return out
