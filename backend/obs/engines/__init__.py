"""Healing engines — Phase 3 physical extraction complete (iter 29).

All four engine classes now physically live in `obs.engines.core`:
  - HealingEngine             (~1543 lines)
  - HealingSequenceOptimizer  (~122 lines)
  - AggressiveHealingMode     (~131 lines)
  - PermanentFunnelHealer     (~187 lines)

Their methods reference singletons that are instantiated in obs_server.py
*after* this module is imported. To break that cycle, obs.engines.core
forward-declares the names as None and obs_server.py calls
`_wire_extracted_modules()` after instantiation to bind them.

`HealingAction` is a pure data class — it physically lives in
obs.trackers.core (extracted in Phase 2 / iter 28) and is re-exported
here for ergonomic access.
"""
from obs.trackers.core import HealingAction

from .core import (
    HealingEngine,
    HealingSequenceOptimizer,
    AggressiveHealingMode,
    PermanentFunnelHealer,
)

def _from_server(name):
    import obs_server
    return getattr(obs_server, name)

# Module-level singletons (`healing_engine`, `sequence_optimizer`, …) still
# live in obs_server.py and are resolved lazily. Shared globals
# `TOPOLOGY_SCHEMA` / `PERMANENT_FIX_REGISTRY` are also obs_server's
# canonical source.
_LAZY_NAMES = {
    "healing_engine", "sequence_optimizer", "aggressive_healing",
    "permanent_funnel_healer",
    "TOPOLOGY_SCHEMA", "PERMANENT_FIX_REGISTRY",
}

def __getattr__(name):
    if name in _LAZY_NAMES:
        return _from_server(name)
    raise AttributeError(f"module 'obs.engines' has no attribute {name!r}")


__all__ = [
    "HealingAction",
    "HealingEngine", "HealingSequenceOptimizer",
    "AggressiveHealingMode", "PermanentFunnelHealer",
    "healing_engine", "sequence_optimizer",
    "aggressive_healing", "permanent_funnel_healer",
    "TOPOLOGY_SCHEMA", "PERMANENT_FIX_REGISTRY",
]
