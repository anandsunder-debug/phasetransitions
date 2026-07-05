"""FreshCart Observability package.

Modular layout (Phase 1 — facade pattern). The runtime entry-point remains
`obs_server.py` (still the uvicorn target on port 8002); this package
exposes the classes and singletons defined there under a clean import
hierarchy so callers can write:

    from obs.trackers import MetricsAggregator, metrics_aggregator
    from obs.engines  import HealingEngine, healing_engine, aggressive_healing
    from obs.routes   import api_router

Subpackages
-----------
- `obs.trackers` : per-domain state collectors (MetricsAggregator,
  SRIInterpolator, ResilienceDebtAccumulator, CorrelationTracker,
  AutoPropagationDetector, CustomerExperienceTracker, BusinessMetrics,
  SRIAttributionEngine, AlertManager, WebhookNotifier).
- `obs.engines`  : self-healing, sequence optimizer, aggressive proactive
  healer, permanent funnel healer (with auto-decay).
- `obs.routes`   : the shared FastAPI `api_router` instance. Per-domain
  route extraction is reserved for Phase 2.

Phase 2 (future)
----------------
Physically move class bodies into `obs/trackers/core.py`,
`obs/engines/core.py`, and route handlers into per-domain
`obs/routes/<domain>.py`. Required prerequisite: refactor
class-to-singleton references to use either dependency injection or a
shared `obs._shared` module to break the circular-import that currently
keeps everything in `obs_server.py`.
"""
