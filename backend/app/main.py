"""Acopio FastAPI application.

Serves the JSON API under /api/* and the built React SPA for everything else,
so the whole product ships as a single service (like crypto-pay-poc).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import init_db
from .routers import admin, agent, auth, dashboard, export, help, inventory, needs, org, uploads, voice

app = FastAPI(title="Acopio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Backfill the semantic index (cache) from the DB (source of truth).
    try:
        from .db import SessionLocal
        from .services.inventory import reindex_missing

        with SessionLocal() as db:
            reindex_missing(db)
    except Exception:
        pass


@app.get("/healthz")
def healthz():
    return {"ok": True, "app": settings.app_name, "ai_enabled": settings.ai_enabled}


# API routers
app.include_router(auth.router)
app.include_router(org.router)
app.include_router(admin.router)
app.include_router(help.router)
app.include_router(inventory.router)
app.include_router(uploads.router)
app.include_router(dashboard.router)
app.include_router(needs.router)
app.include_router(export.router)
app.include_router(agent.router)
app.include_router(voice.router)


# --- static SPA ----------------------------------------------------------
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Never swallow API/health routes.
        if full_path.startswith("api/") or full_path == "healthz":
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
else:
    @app.get("/")
    def root():
        return {
            "app": settings.app_name,
            "status": "API running. Frontend not built yet — run `npm --prefix frontend run build`.",
            "docs": "/docs",
        }
