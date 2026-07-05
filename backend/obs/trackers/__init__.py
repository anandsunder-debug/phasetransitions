"""Tracker classes — Phase 2 + Phase 3 (physical extraction complete).

All tracker classes now physically live in `obs.trackers.core`:

  Phase 2 (iter 28): MetricsAggregator, SRIInterpolator, ResilienceDebtAccumulator,
                     CorrelationTracker, AutoPropagationDetector,
                     SRIAttributionEngine, WebhookNotifier, HealingAction
  Phase 3 (iter 29): CustomerExperienceTracker, BusinessMetrics, AlertManager

Module-level singletons (metrics_aggregator, business_metrics, etc.) are
still instantiated in `obs_server.py` (that's where the wire_runtime call
runs). They're re-exposed here via PEP 562 lazy __getattr__ so callers
can still write `from obs.trackers import metrics_aggregator` without
worrying about the import-time vs runtime-instantiation ordering.
"""
from .core import (
    # Phase 2 (iter 28)
    MetricsAggregator,
    SRIInterpolator,
    ResilienceDebtAccumulator,
    CorrelationTracker,
    AutoPropagationDetector,
    SRIAttributionEngine,
    WebhookNotifier,
    HealingAction,
    # Phase 3 (iter 29)
    CustomerExperienceTracker,
    BusinessMetrics,
    AlertManager,
)

def _from_server(name):
    import obs_server
    return getattr(obs_server, name)

# All singletons live in obs_server.py and are resolved lazily.
_LAZY_NAMES = {
    "metrics_aggregator", "sri_interpolator", "resilience_debt",
    "correlation_tracker", "auto_propagation_detector", "cx_tracker",
    "business_metrics", "attribution_engine", "alert_manager",
    "webhook_notifier",
}

def __getattr__(name):
    if name in _LAZY_NAMES:
        return _from_server(name)
    raise AttributeError(f"module 'obs.trackers' has no attribute {name!r}")


__all__ = [
    # Phase 2 classes
    "MetricsAggregator", "SRIInterpolator", "ResilienceDebtAccumulator",
    "CorrelationTracker", "AutoPropagationDetector", "SRIAttributionEngine",
    "WebhookNotifier", "HealingAction",
    # Phase 3 classes
    "CustomerExperienceTracker", "BusinessMetrics", "AlertManager",
    # Singletons
    "metrics_aggregator", "sri_interpolator", "resilience_debt",
    "correlation_tracker", "auto_propagation_detector", "cx_tracker",
    "business_metrics", "attribution_engine", "alert_manager",
    "webhook_notifier",
]
