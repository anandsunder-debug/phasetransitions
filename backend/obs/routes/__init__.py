"""FastAPI route handlers — Phase 1 (facade re-export of api_router).

All route handlers (`@api_router.get(...)`, etc.) still live in
`obs_server.py`. Phase 2 will physically extract them into per-domain
modules with the structure documented below.

    from obs.routes import api_router

Planned future grouping (Phase 2):
  - obs.routes.metrics    — /api/metrics/*
  - obs.routes.healing    — /api/healing/*
  - obs.routes.alerts     — /api/alerts*, /api/admin/webhooks/*
  - obs.routes.cx         — /api/cx/*
  - obs.routes.rum        — /api/rum/*
  - obs.routes.internal   — /api/internal/events/*
"""
from obs_server import api_router, app

__all__ = ["api_router", "app"]
