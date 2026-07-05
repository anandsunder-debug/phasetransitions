from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.websockets import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import logging
import secrets
import bcrypt
import jwt
import time
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Set, Any, Tuple
import random
import numpy as np
from collections import defaultdict
from threading import Lock
import json

# InfluxDB Client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"

# InfluxDB Config
INFLUX_URL = os.environ.get("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "freshcart")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "metrics")

# Alert thresholds
SRI_CRITICAL_THRESHOLD = 0.1
SRI_WARNING_THRESHOLD = 0.3
LATENCY_CRITICAL_THRESHOLD = 200  # ms
ERROR_RATE_CRITICAL_THRESHOLD = 0.1  # 10%

# Initialize InfluxDB client
influx_client = None
write_api = None
query_api = None

def init_influxdb():
    global influx_client, write_api, query_api
    if INFLUX_TOKEN:
        try:
            influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            write_api = influx_client.write_api(write_options=ASYNCHRONOUS)
            query_api = influx_client.query_api()
            logger.info("InfluxDB client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB: {e}")

# Permanent fix registry — populated by PermanentFunnelHealer.
# Schema: { node_name: { signal: multiplier_in_[0,1] } }
# Persisted in MongoDB (collection `permanent_fixes`) on every change so it
# survives obs_server restarts.
PERMANENT_FIX_REGISTRY: Dict[str, Dict[str, float]] = {}

# Real-time metrics aggregator (in-memory for fast access)
# ==================== EXTRACTED CLASSES (obs.trackers.core) ====================
# Phase 2 (iter 28): the following classes were physically moved to
# obs/trackers/core.py — MetricsAggregator, SRIInterpolator, ResilienceDebtAccumulator, CorrelationTracker, AutoPropagationDetector, SRIAttributionEngine, WebhookNotifier, HealingAction
# The line below re-imports them so obs_server's existing references
# (decorators, instantiations) keep working unchanged.
from obs.trackers.core import (
    MetricsAggregator,
    SRIInterpolator,
    ResilienceDebtAccumulator,
    CorrelationTracker,
    AutoPropagationDetector,
    SRIAttributionEngine,
    WebhookNotifier,
    HealingAction,
)

metrics_aggregator = MetricsAggregator()

# SRI History tracking
sri_history = []
sri_lock = Lock()


# ==================== SRI INTERPOLATOR (Trend Analysis) ====================


sri_interpolator = SRIInterpolator()




resilience_debt = ResilienceDebtAccumulator()




correlation_tracker = CorrelationTracker()




# ==================== EXTRACTED CLASSES (Phase 3, iter 29) ====================
# These class bodies now live in obs.trackers.core and obs.engines.core.
# The wire_runtime() call near the bottom of this file binds the singletons
# instantiated below into those modules' globals so method bodies that
# reference `metrics_aggregator`, `business_metrics`, etc. find them.
from obs.trackers.core import (
    CustomerExperienceTracker,
    BusinessMetrics,
    AlertManager,
)
from obs.engines.core import (
    HealingEngine,
    HealingSequenceOptimizer,
    AggressiveHealingMode,
    PermanentFunnelHealer,
)
from obs.engines import ladder_synthesizer as ladder_synth_mod
from obs.engines.ladder_synthesizer import LadderSynthesizer
from obs.engines import phase_classifier as phase_mod
from obs.engines.phase_classifier import PhaseClassifier
from obs.engines import rum_ladder_learner as rum_learner_mod
from obs.engines.rum_ladder_learner import RumLadderLearner
from obs.engines import action_stagnation as action_stagnation_mod
from obs.engines.action_stagnation import ActionStagnationGuard
from obs.trackers import economic_reliability as econ_rel_mod
from obs.trackers.economic_reliability import EconomicReliabilityTracker
from obs.engines import stability_functional as stab_mod
from obs.engines.stability_functional import StabilityFunctional
from obs.engines import rst_engine as rst_mod
from obs.engines.rst_engine import RSTEngine


auto_propagation_detector = AutoPropagationDetector()




cx_tracker = CustomerExperienceTracker()


# ==================== BUSINESS METRICS & RELIABILITY ====================





business_metrics = BusinessMetrics()
attribution_engine = SRIAttributionEngine()

# Alert System

alert_manager = AlertManager()

# ==================== TOPOLOGY SCHEMA (shared) ====================
# Single source of truth for the FreshCart service mesh: parent services,
# sub-components, sub-component endpoints, inter-service edges, intra-service
# edges, endpoint edges, and default visual layout.
# Exposed via GET /api/healing/topology/schema so the frontend can drop its
# hardcoded mapping.
#
# Three granularity tiers:
#   tier 1 ("service")   — 6 nodes: Frontend, API, Cache, DB, Queue, Backend
#   tier 2 ("component") — 50 sub-components (one level below each service)
#   tier 3 ("endpoint")  — 100+ endpoints (one level below each component)
#
# Each tier is internally consistent: the FEA solver, the propagation
# simulator, the auto-dampener, and the sequence optimizer all accept
# `granularity ∈ {service, component, endpoint}` and operate on the
# correspondingly sized graph.
TOPOLOGY_SCHEMA: Dict[str, Any] = {
    "services": [
        {"name": "Frontend","position": {"x": 90,  "y": 80},  "corrective_action": "rate_limit"},
        {"name": "API",     "position": {"x": 300, "y": 80},  "corrective_action": "rate_limit"},
        {"name": "Cache",   "position": {"x": 110, "y": 200}, "corrective_action": "cache_flush"},
        {"name": "DB",      "position": {"x": 210, "y": 340}, "corrective_action": "connection_pool_reset"},
        {"name": "Queue",   "position": {"x": 410, "y": 340}, "corrective_action": "queue_drain"},
        {"name": "Backend", "position": {"x": 500, "y": 200}, "corrective_action": "circuit_breaker"},
    ],
    "inter_edges": [
        ["Frontend", "API"],
        ["API", "Cache"], ["API", "DB"], ["API", "Queue"],
        ["Cache", "DB"], ["Queue", "Backend"],
        # Enrichment: real-world fan-out lines we already model in latency chains
        ["Backend", "DB"], ["Backend", "Cache"],
    ],
    "components": {
        "Frontend": [
            "Frontend.page_load", "Frontend.render", "Frontend.api_calls",
            "Frontend.js_errors", "Frontend.assets", "Frontend.router",
            "Frontend.state_store", "Frontend.rum_beacon",
        ],
        "API": [
            "API.auth", "API.catalog", "API.cart", "API.checkout", "API.orders",
            "API.search", "API.recommendations", "API.admin", "API.rate_limiter",
        ],
        "Cache": [
            "Cache.session", "Cache.product", "Cache.price",
            "Cache.search_index", "Cache.cart_state", "Cache.rate_limit_buckets",
            "Cache.feature_flags",
        ],
        "DB": [
            "DB.users", "DB.products", "DB.orders", "DB.metrics",
            "DB.carts", "DB.inventory", "DB.audit_log", "DB.replica",
        ],
        "Queue": [
            "Queue.orders", "Queue.healing", "Queue.metrics",
            "Queue.email", "Queue.fulfillment", "Queue.dead_letter",
        ],
        "Backend": [
            "Backend.sri_engine", "Backend.healing_engine", "Backend.fea_engine",
            "Backend.analytics", "Backend.attribution", "Backend.cx_tracker",
            "Backend.webhook_dispatch", "Backend.scheduler",
        ],
    },
    "fine_edges": [
        # ---- Intra-Frontend ----
        ["Frontend.page_load", "Frontend.assets"],
        ["Frontend.assets", "Frontend.render"],
        ["Frontend.render", "Frontend.router"],
        ["Frontend.router", "Frontend.state_store"],
        ["Frontend.state_store", "Frontend.api_calls"],
        ["Frontend.api_calls", "Frontend.js_errors"],
        ["Frontend.render", "Frontend.rum_beacon"],
        ["Frontend.api_calls", "Frontend.rum_beacon"],
        # ---- Intra-API ----
        ["API.auth", "API.catalog"], ["API.auth", "API.cart"],
        ["API.catalog", "API.cart"], ["API.catalog", "API.search"],
        ["API.cart", "API.checkout"], ["API.checkout", "API.orders"],
        ["API.catalog", "API.recommendations"], ["API.recommendations", "API.search"],
        ["API.admin", "API.catalog"], ["API.admin", "API.orders"],
        ["API.rate_limiter", "API.auth"], ["API.rate_limiter", "API.checkout"],
        # ---- Intra-Cache ----
        ["Cache.session", "Cache.product"], ["Cache.product", "Cache.price"],
        ["Cache.product", "Cache.search_index"], ["Cache.cart_state", "Cache.session"],
        ["Cache.rate_limit_buckets", "Cache.session"],
        ["Cache.feature_flags", "Cache.session"],
        # ---- Intra-DB ----
        ["DB.users", "DB.orders"], ["DB.products", "DB.orders"],
        ["DB.products", "DB.inventory"], ["DB.orders", "DB.metrics"],
        ["DB.carts", "DB.orders"], ["DB.carts", "DB.users"],
        ["DB.audit_log", "DB.orders"], ["DB.audit_log", "DB.users"],
        ["DB.replica", "DB.users"], ["DB.replica", "DB.products"], ["DB.replica", "DB.orders"],
        # ---- Intra-Queue ----
        ["Queue.orders", "Queue.fulfillment"],
        ["Queue.orders", "Queue.email"],
        ["Queue.healing", "Queue.metrics"],
        ["Queue.fulfillment", "Queue.dead_letter"],
        ["Queue.email", "Queue.dead_letter"],
        # ---- Intra-Backend ----
        ["Backend.sri_engine", "Backend.healing_engine"],
        ["Backend.healing_engine", "Backend.fea_engine"],
        ["Backend.fea_engine", "Backend.analytics"],
        ["Backend.sri_engine", "Backend.analytics"],
        ["Backend.sri_engine", "Backend.attribution"],
        ["Backend.attribution", "Backend.analytics"],
        ["Backend.cx_tracker", "Backend.analytics"],
        ["Backend.healing_engine", "Backend.webhook_dispatch"],
        ["Backend.scheduler", "Backend.healing_engine"],
        ["Backend.scheduler", "Backend.cx_tracker"],
        # ---- Inter-service: Frontend → API ----
        ["Frontend.api_calls", "API.auth"],
        ["Frontend.api_calls", "API.catalog"],
        ["Frontend.api_calls", "API.cart"],
        ["Frontend.api_calls", "API.checkout"],
        ["Frontend.api_calls", "API.search"],
        ["Frontend.rum_beacon", "API.admin"],
        # ---- Inter-service: API → Cache ----
        ["API.auth", "Cache.session"],
        ["API.catalog", "Cache.product"],
        ["API.catalog", "Cache.search_index"],
        ["API.checkout", "Cache.price"],
        ["API.cart", "Cache.cart_state"],
        ["API.search", "Cache.search_index"],
        ["API.rate_limiter", "Cache.rate_limit_buckets"],
        ["API.admin", "Cache.feature_flags"],
        # ---- Inter-service: API → DB ----
        ["API.auth", "DB.users"],
        ["API.catalog", "DB.products"],
        ["API.orders", "DB.orders"],
        ["API.cart", "DB.carts"],
        ["API.admin", "DB.audit_log"],
        ["API.recommendations", "DB.products"],
        # ---- Inter-service: API → Queue ----
        ["API.checkout", "Queue.orders"],
        ["API.orders", "Queue.fulfillment"],
        ["API.admin", "Queue.email"],
        # ---- Inter-service: Cache → DB ----
        ["Cache.product", "DB.products"],
        ["Cache.cart_state", "DB.carts"],
        # ---- Inter-service: Queue → Backend ----
        ["Queue.orders", "Backend.sri_engine"],
        ["Queue.metrics", "Backend.analytics"],
        ["Queue.healing", "Backend.healing_engine"],
        # ---- Inter-service: Backend → DB / Cache ----
        ["Backend.analytics", "DB.metrics"],
        ["Backend.cx_tracker", "DB.metrics"],
        ["Backend.webhook_dispatch", "DB.audit_log"],
        ["Backend.attribution", "Cache.product"],
    ],
    # ---- Tier-3: endpoints / queries / cache-keys / queue-topics. Each
    # entry is "Service.Component.endpoint" — a leaf in the topology that
    # represents the unit of work the system actually executes.
    "endpoints": {
        "Frontend.page_load":   ["Frontend.page_load.home", "Frontend.page_load.products", "Frontend.page_load.cart", "Frontend.page_load.checkout"],
        "Frontend.render":      ["Frontend.render.tree", "Frontend.render.commit"],
        "Frontend.api_calls":   ["Frontend.api_calls.GET", "Frontend.api_calls.POST", "Frontend.api_calls.WS"],
        "Frontend.js_errors":   ["Frontend.js_errors.uncaught", "Frontend.js_errors.unhandled_rejection"],
        "Frontend.assets":      ["Frontend.assets.js_bundle", "Frontend.assets.css", "Frontend.assets.images"],
        "Frontend.router":      ["Frontend.router.transition"],
        "Frontend.state_store": ["Frontend.state_store.cart", "Frontend.state_store.auth"],
        "Frontend.rum_beacon":  ["Frontend.rum_beacon.tick"],

        "API.auth":            ["API.auth.login", "API.auth.register", "API.auth.me", "API.auth.logout"],
        "API.catalog":         ["API.catalog.list", "API.catalog.detail", "API.catalog.categories"],
        "API.cart":            ["API.cart.get", "API.cart.add", "API.cart.update", "API.cart.remove"],
        "API.checkout":        ["API.checkout.start", "API.checkout.pay", "API.checkout.confirm"],
        "API.orders":          ["API.orders.create", "API.orders.list", "API.orders.detail"],
        "API.search":          ["API.search.query", "API.search.suggest"],
        "API.recommendations": ["API.recommendations.related", "API.recommendations.trending"],
        "API.admin":           ["API.admin.products_create", "API.admin.orders_list", "API.admin.webhooks"],
        "API.rate_limiter":    ["API.rate_limiter.check", "API.rate_limiter.tick"],

        "Cache.session":            ["Cache.session.get", "Cache.session.set", "Cache.session.evict"],
        "Cache.product":            ["Cache.product.get", "Cache.product.set"],
        "Cache.price":              ["Cache.price.get"],
        "Cache.search_index":       ["Cache.search_index.lookup", "Cache.search_index.rebuild"],
        "Cache.cart_state":         ["Cache.cart_state.get", "Cache.cart_state.set"],
        "Cache.rate_limit_buckets": ["Cache.rate_limit_buckets.tick"],
        "Cache.feature_flags":      ["Cache.feature_flags.read"],

        "DB.users":     ["DB.users.find_by_email", "DB.users.insert", "DB.users.update_prefs"],
        "DB.products":  ["DB.products.find", "DB.products.by_id", "DB.products.by_category"],
        "DB.orders":    ["DB.orders.insert", "DB.orders.find_by_user", "DB.orders.find_by_id", "DB.orders.update_status"],
        "DB.metrics":   ["DB.metrics.append", "DB.metrics.aggregate"],
        "DB.carts":     ["DB.carts.find", "DB.carts.update", "DB.carts.upsert"],
        "DB.inventory": ["DB.inventory.decrement", "DB.inventory.read"],
        "DB.audit_log": ["DB.audit_log.append"],
        "DB.replica":   ["DB.replica.read"],

        "Queue.orders":       ["Queue.orders.publish", "Queue.orders.consume"],
        "Queue.healing":      ["Queue.healing.publish", "Queue.healing.consume"],
        "Queue.metrics":      ["Queue.metrics.publish", "Queue.metrics.consume"],
        "Queue.email":        ["Queue.email.publish", "Queue.email.consume"],
        "Queue.fulfillment":  ["Queue.fulfillment.publish", "Queue.fulfillment.consume"],
        "Queue.dead_letter":  ["Queue.dead_letter.append"],

        "Backend.sri_engine":       ["Backend.sri_engine.compute", "Backend.sri_engine.trend"],
        "Backend.healing_engine":   ["Backend.healing_engine.tick", "Backend.healing_engine.execute", "Backend.healing_engine.adapt"],
        "Backend.fea_engine":       ["Backend.fea_engine.solve", "Backend.fea_engine.cascade"],
        "Backend.analytics":        ["Backend.analytics.rollup"],
        "Backend.attribution":      ["Backend.attribution.decompose"],
        "Backend.cx_tracker":       ["Backend.cx_tracker.sample", "Backend.cx_tracker.percentiles"],
        "Backend.webhook_dispatch": ["Backend.webhook_dispatch.slack", "Backend.webhook_dispatch.discord"],
        "Backend.scheduler":        ["Backend.scheduler.heal_loop", "Backend.scheduler.propagation_loop"],
    },
}

# ---- Tier-3 endpoint edges. We pre-compute these once at import time:
#   (a) per-component "fan-out chain" between sibling endpoints (1→2→3) — captures
#       sequential execution order inside a unit of work.
#   (b) inter-endpoint edges projected down from `fine_edges`: for each
#       (component_a, component_b) edge in fine_edges, connect the first endpoint
#       of component_a to the first endpoint of component_b. This keeps the
#       endpoint graph connected and matches realistic call patterns
#       (the "primary" endpoint of each component is the entry point).
def _build_endpoint_edges() -> List[List[str]]:
    edges: List[List[str]] = []
    endpoints_map = TOPOLOGY_SCHEMA["endpoints"]
    # (a) intra-component chains
    for component, eps in endpoints_map.items():
        for i in range(len(eps) - 1):
            edges.append([eps[i], eps[i + 1]])
    # (b) inter-component edges projected to (first endpoint -> first endpoint)
    for a, b in TOPOLOGY_SCHEMA["fine_edges"]:
        eps_a = endpoints_map.get(a, [])
        eps_b = endpoints_map.get(b, [])
        if eps_a and eps_b:
            edges.append([eps_a[0], eps_b[0]])
    return edges

TOPOLOGY_SCHEMA["endpoint_edges"] = _build_endpoint_edges()

# ==================== WEBHOOK NOTIFIER (Slack / Discord) ====================



webhook_notifier = WebhookNotifier()

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ==================== MODELS ====================

class MetricsSimulation(BaseModel):
    traffic_scale: int = 1000
    latency_scale: int = 50
    error_rate: float = 0.05
    saturation: float = 0.3
    failure_mode: str = "None"

# ==================== AUTH HELPERS ====================

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user["name"],
            "role": user.get("role", "user")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_optional_user(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None

# ==================== INTERNAL EVENT ENDPOINTS (from main_app) ====================

class _RequestEvent(BaseModel):
    path: str
    method: str = "GET"
    latency: float  # seconds
    is_error: bool = False

class _BusinessEvent(BaseModel):
    event_type: str  # page_view | add_to_cart | checkout_start | order_complete
    value: float = 0.0

@api_router.post("/internal/events/request")
async def _ingest_request_event(evt: _RequestEvent):
    """Receive request telemetry from main_app middleware. Mirrors the
    classification + recording previously done by the in-process middleware."""
    path = evt.path
    chains = {
        "product":  ["API", "Cache", "DB"],
        "cart":     ["API", "Cache", "DB"],
        "order":    ["API", "DB", "Queue", "Backend"],
        "auth":     ["API", "Backend"],
        "healing":  ["API", "Queue", "Backend"],
        "metrics":  ["API", "Backend"],
    }
    if "/products" in path or "/categories" in path:
        chain = chains["product"]
    elif "/cart" in path:
        chain = chains["cart"]
    elif "/orders" in path:
        chain = chains["order"]
    elif "/auth" in path:
        chain = chains["auth"]
    elif "/healing" in path or "/alerts" in path:
        chain = chains["healing"]
    elif "/metrics" in path or "/grafana" in path:
        chain = chains["metrics"]
    else:
        chain = ["API", "Cache"]
    primary = chain[0]
    metrics_aggregator.record(primary, evt.latency, evt.is_error)
    for secondary in chain[1:]:
        trace_latency = random.uniform(0.001, 0.008)
        trace_error = random.random() < 0.005
        metrics_aggregator.record(secondary, trace_latency, trace_error)

    # InfluxDB write
    if write_api:
        try:
            point = Point("api_request")                 .tag("node", primary)                 .tag("method", evt.method)                 .tag("path", path)                 .tag("status", "error" if evt.is_error else "success")                 .field("latency_ms", evt.latency * 1000)                 .field("count", 1)                 .time(datetime.now(timezone.utc), WritePrecision.MS)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        except Exception as e:
            logger.debug(f"InfluxDB write failed: {e}")

    # Periodic correlation / alert pulse (replaces the old middleware tick)
    _INTERNAL_TICK["count"] += 1
    skip_alert = "/metrics/" in path or "/healing/" in path or "/grafana/" in path
    if _INTERNAL_TICK["count"] % 10 == 0 and not skip_alert:
        try:
            node_metrics = metrics_aggregator.get_all_metrics()
            sri_data = compute_sri_from_metrics(node_metrics)
            sri_interpolator.record(sri_data["sri"])
            try:
                topo = healing_engine.analyze_topology(node_metrics, sri_data, granularity="service")
                resilience_debt.record(float(topo.get("total_health_debt", 0.0)), sri_data["sri"])
            except Exception as e:
                logger.debug(f"resilience-debt update: {e}")
            avg_latency = np.mean([m["latency"] for m in node_metrics.values() if m["traffic"] > 0]) if any(m["traffic"] > 0 for m in node_metrics.values()) else 0
            avg_error = np.mean([m["error"] for m in node_metrics.values() if m["traffic"] > 0]) if any(m["traffic"] > 0 for m in node_metrics.values()) else 0
            try:
                funnel = business_metrics.get_funnel()
                conv = funnel.get("modeled_conversion", {}).get("effective_conversion_rate", 0.0)
                correlation_tracker.record(sri=sri_data["sri"], conversion=conv, latency_ms=float(avg_latency), error_pct=float(avg_error * 100))
                api_metrics = node_metrics.get("API", {})
                cache_metrics = node_metrics.get("Cache", {})
                cx_tracker.record(
                    latency_ms=float(api_metrics.get("latency", avg_latency) or avg_latency),
                    error_rate_pct=float(avg_error * 100),
                    conversion=conv,
                    add_to_cart_ms=float(cache_metrics.get("latency", 0) or 0) * 1000 if cache_metrics.get("latency", 0) < 1 else float(cache_metrics.get("latency", 0)),
                )
            except Exception as e:
                logger.debug(f"correlation/cx update: {e}")
            await alert_manager.check_and_alert(sri_data["sri"], avg_latency, avg_error, node_metrics)
        except Exception as e:
            logger.debug(f"alert tick: {e}")

    return {"ok": True}

# Module-level tick counter for internal event endpoint
_INTERNAL_TICK = {"count": 0}

@api_router.post("/internal/events/business")
async def _ingest_business_event(evt: _BusinessEvent):
    """Main app emits business events (page_view, add_to_cart, checkout_start, order_complete)."""
    business_metrics.record_event(evt.event_type, evt.value)
    return {"ok": True}


# ==================== REAL OBSERVABILITY / METRICS ====================

def compute_sri_from_metrics(node_metrics: Dict[str, Dict]) -> Dict:
    """Compute Spectral Resilience Index using the Physical Model of Software Systems.
    
    Based on: "A Rigorous Graph-Theoretic Model of Distributed Software Systems:
    Flow, Stiffness, and Layered Execution"
    
    Key formulation:
    - Node state: x_i = (q_i, c_i) where q=queue/load, c=capacity
    - Edge capacity (stiffness): K_ij = W_ij derived from service health
    - Flow: F_ij = W_ij * (q_i - q_j) driven by load differential
    - Energy Functional: E(q) = Σ W_ij * (q_i - q_j)² (total system stress)
    - SRI = 1 - E/E_max (low energy = high resilience)
    - Stability: L + γI > 0
    """
    nodes = list(node_metrics.keys())
    edges = [("Frontend", "API"), ("API", "Cache"), ("API", "DB"), ("API", "Queue"), ("Cache", "DB"), ("Queue", "Backend")]
    n_nodes = len(nodes)
    node_idx = {n: i for i, n in enumerate(nodes)}

    # === Node State: q_i (load/queue), c_i (capacity) ===
    # Load = normalized pressure from latency + errors + saturation
    # Capacity = how much the node can handle (inversely related to saturation)
    q = np.zeros(n_nodes)  # queue/load per node
    c = np.zeros(n_nodes)  # capacity per node
    for i, name in enumerate(nodes):
        m = node_metrics.get(name, {})
        # q_i: effective load = latency_pressure + error_pressure + saturation
        lat_p = min(m.get("latency", 0) / 200.0, 1.0)
        err_p = min(m.get("error", 0) / 0.15, 1.0)
        sat_p = m.get("saturation", 0)
        q[i] = lat_p * 0.3 + err_p * 0.4 + sat_p * 0.3
        # c_i: capacity = 1 - saturation (saturated = no capacity left)
        c[i] = max(1 - sat_p, 0.1)

    # === Edge Capacity (Stiffness): W_ij ===
    # Derived from how well the path between nodes can carry flow
    # High capacity = healthy connection, low latency, low errors
    edge_data = []
    W = np.zeros((n_nodes, n_nodes))
    for (a, b) in edges:
        if a in node_idx and b in node_idx:
            ia, ib = node_idx[a], node_idx[b]
            ma = node_metrics.get(a, {})
            # Capacity of edge = health of source node's path to target
            traffic_active = min(ma.get("traffic", 0) / 3, 1.0)
            health = (1 - min(ma.get("latency", 0) / 300, 1.0)) * (1 - ma.get("error", 0)) * (1 - ma.get("saturation", 0))
            w_ij = max(traffic_active * health, 0.01) * 10  # Scale to [0.01, 10]
            W[ia, ib] = w_ij
            W[ib, ia] = w_ij
            edge_data.append({"source": a, "target": b, "weight": round(float(w_ij), 4), "capacity": round(float(w_ij), 4)})

    # === Laplacian (Global Stiffness Matrix): L = D - W ===
    L = np.zeros((n_nodes, n_nodes))
    for (a, b) in edges:
        if a in node_idx and b in node_idx:
            ia, ib = node_idx[a], node_idx[b]
            w = W[ia, ib]
            L[ia, ib] -= w
            L[ib, ia] -= w
            L[ia, ia] += w
            L[ib, ib] += w

    # === Flow: F_ij = W_ij * (q_i - q_j) ===
    flows = []
    for (a, b) in edges:
        if a in node_idx and b in node_idx:
            ia, ib = node_idx[a], node_idx[b]
            flow = W[ia, ib] * (q[ia] - q[ib])
            flows.append({"source": a, "target": b, "flow": round(float(flow), 6)})

    # === Energy Functional: E(q) = Σ W_ij * (q_i - q_j)² ===
    energy = 0.0
    for (a, b) in edges:
        if a in node_idx and b in node_idx:
            ia, ib = node_idx[a], node_idx[b]
            energy += W[ia, ib] * (q[ia] - q[ib]) ** 2

    # Max possible energy (all nodes at max load differential)
    max_edge_cap = np.max(W[W > 0]) if np.any(W > 0) else 1.0
    e_max = max_edge_cap * len(edges) * 1.0  # max differential = 1.0

    # === SRI = 1 - E/E_max (low energy = high resilience) ===
    raw_sri = max(0, min(1, 1 - (energy / max(e_max, 0.01))))

    # === Stability Condition: L + γI > 0 ===
    # γ = average processing strength (capacity)
    gamma = float(np.mean(c))
    stability_matrix = L + gamma * np.eye(n_nodes)
    try:
        eig_stability = np.linalg.eigvalsh(stability_matrix)
        is_stable = bool(np.all(eig_stability > 0))
        min_stability_eigenvalue = float(np.min(eig_stability))
    except:
        is_stable = True
        min_stability_eigenvalue = 0.0

    # === Eigenvalues for spectral analysis ===
    try:
        eigenvalues = np.sort(np.real(np.linalg.eigvalsh(L)))
        lambda2 = float(eigenvalues[1]) if len(eigenvalues) > 1 else 0
    except:
        eigenvalues = [0.0] * n_nodes
        lambda2 = 0

    # Fiedler vector
    try:
        _, vecs = np.linalg.eigh(L)
        fiedler = vecs[:, 1].tolist() if vecs.shape[1] > 1 else [0] * n_nodes
    except:
        fiedler = [0] * n_nodes

    # === Baseline calibration during warmup ===
    if not metrics_aggregator.warmup_complete:
        blend = min(metrics_aggregator.warmup_requests / metrics_aggregator.warmup_target, 1.0)
        sri = metrics_aggregator.baseline_sri * (1 - blend) + raw_sri * blend
    else:
        sri = raw_sri

    # Weak edges: where Fiedler vector shows partition risk
    fiedler_mean = np.mean(np.abs(fiedler)) if fiedler else 0
    weak_edges = []
    for ew in edge_data:
        if ew["source"] in node_idx and ew["target"] in node_idx:
            i, j = node_idx[ew["source"]], node_idx[ew["target"]]
            if abs(fiedler[i] - fiedler[j]) > fiedler_mean:
                weak_edges.append({"source": ew["source"], "target": ew["target"]})

    # Golden signal contributions
    golden = metrics_aggregator.get_golden_signals()
    signal_contributions = {
        "latency": round(golden["latency"]["health"] * 0.3, 4),
        "traffic": round(golden["traffic"]["health"] * 0.1, 4),
        "errors": round(golden["errors"]["health"] * 0.4, 4),
        "saturation": round(golden["saturation"]["health"] * 0.2, 4)
    }

    return {
        "sri": float(sri),
        "raw_sri": float(raw_sri),
        "energy": round(float(energy), 6),
        "energy_max": round(float(e_max), 4),
        "stability": {
            "is_stable": is_stable,
            "gamma": round(gamma, 4),
            "min_eigenvalue": round(min_stability_eigenvalue, 6),
        },
        "node_state": {nodes[i]: {"load": round(float(q[i]), 4), "capacity": round(float(c[i]), 4)} for i in range(n_nodes)},
        "flows": flows,
        "lambda2": round(lambda2, 6),
        "baseline_sri": metrics_aggregator.baseline_sri,
        "warmup_complete": metrics_aggregator.warmup_complete,
        "eigenvalues": [round(float(e), 6) for e in eigenvalues],
        "fiedler": fiedler,
        "edge_weights": edge_data,
        "weak_edges": weak_edges,
        "signal_contributions": signal_contributions,
    }

@api_router.get("/metrics/real")
async def get_real_metrics():
    """Get real metrics derived from actual app interactions"""
    global sri_history
    
    # Get aggregated metrics from real requests
    node_metrics = metrics_aggregator.get_all_metrics()
    
    # Compute SRI from real data
    sri_data = compute_sri_from_metrics(node_metrics)
    
    # Build response
    nodes = [{"id": n, **node_metrics[n]} for n in node_metrics]
    
    avg_latency = np.mean([m["latency"] for m in node_metrics.values()])
    avg_error = np.mean([m["error"] for m in node_metrics.values()])
    avg_saturation = np.mean([m["saturation"] for m in node_metrics.values()])
    
    # Record SRI history
    with sri_lock:
        sri_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sri": sri_data["sri"]
        })
        # Keep last 100 entries
        if len(sri_history) > 100:
            sri_history = sri_history[-100:]
    
    # Write SRI to InfluxDB
    if write_api:
        try:
            point = Point("sri") \
                .field("value", sri_data["sri"]) \
                .field("avg_latency", avg_latency) \
                .field("avg_error", avg_error) \
                .field("avg_saturation", avg_saturation) \
                .time(datetime.now(timezone.utc), WritePrecision.MS)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        except Exception as e:
            logger.debug(f"Failed to write SRI metric: {e}")
    
    # Check for alerts
    await alert_manager.check_and_alert(sri_data["sri"], avg_latency, avg_error, node_metrics)
    
    return {
        "nodes": nodes,
        "edges": sri_data["edge_weights"],
        "eigenvalues": sri_data["eigenvalues"],
        "sri": sri_data["sri"],
        "raw_sri": sri_data.get("raw_sri", sri_data["sri"]),
        "energy": sri_data.get("energy", 0),
        "energy_max": sri_data.get("energy_max", 1),
        "stability": sri_data.get("stability", {}),
        "node_state": sri_data.get("node_state", {}),
        "flows": sri_data.get("flows", []),
        "lambda2": sri_data.get("lambda2", 0),
        "baseline_sri": sri_data.get("baseline_sri", 0.85),
        "warmup_complete": sri_data.get("warmup_complete", True),
        "signal_contributions": sri_data.get("signal_contributions", {}),
        "fiedler": sri_data["fiedler"],
        "weak_edges": sri_data["weak_edges"],
        "avg_latency": avg_latency,
        "avg_error": avg_error,
        "avg_saturation": avg_saturation,
        "golden_signals": metrics_aggregator.get_golden_signals(),
        "customer_experience": metrics_aggregator.get_customer_experience(),
        "source": "physical_model"
    }

@api_router.get("/metrics/sri-history")
async def get_sri_history():
    """Get historical SRI values"""
    with sri_lock:
        return sri_history

@api_router.post("/metrics/simulate")
async def simulate_metrics(config: MetricsSimulation):
    """Generate simulated system metrics for testing (fallback)"""
    nodes_list = ["API", "Cache", "DB", "Queue", "Backend"]
    edges = [("API", "Cache"), ("API", "DB"), ("API", "Queue"), ("Cache", "DB"), ("Queue", "Backend")]
    
    metrics = {}
    for n in nodes_list:
        metrics[n] = {
            "traffic": random.uniform(0.5, 1.5) * config.traffic_scale,
            "latency": random.uniform(0.5, 1.5) * config.latency_scale,
            "error": random.uniform(0, config.error_rate),
            "saturation": min(random.uniform(0.5, 1.5) * config.saturation, 1.0)
        }
    
    # Inject failures
    if config.failure_mode == "DB Overload":
        metrics["DB"]["saturation"] = 0.95
    elif config.failure_mode == "Latency Spike":
        metrics["Backend"]["latency"] *= 5
    elif config.failure_mode == "Error Storm":
        metrics["API"]["error"] = 0.4
    
    # Compute SRI
    sri_data = compute_sri_from_metrics(metrics)
    
    return {
        "nodes": [{"id": n, **metrics[n]} for n in nodes_list],
        "edges": sri_data["edge_weights"],
        "eigenvalues": sri_data["eigenvalues"],
        "sri": sri_data["sri"],
        "fiedler": sri_data["fiedler"],
        "weak_edges": sri_data["weak_edges"],
        "avg_latency": np.mean([metrics[n]["latency"] for n in nodes_list]),
        "avg_error": np.mean([metrics[n]["error"] for n in nodes_list]),
        "avg_saturation": np.mean([metrics[n]["saturation"] for n in nodes_list]),
        "source": "simulated"
    }

@api_router.get("/metrics/history")
async def get_metrics_history(limit: int = 50):
    """Get historical SRI values from InfluxDB"""
    if query_api:
        try:
            query = f'''
            from(bucket: "{INFLUX_BUCKET}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "sri")
                |> filter(fn: (r) => r._field == "value")
                |> sort(columns: ["_time"])
                |> limit(n: {limit})
            '''
            result = query_api.query(org=INFLUX_ORG, query=query)
            history = []
            for table in result:
                for record in table.records:
                    history.append({
                        "timestamp": record.get_time().isoformat(),
                        "sri": record.get_value()
                    })
            return history
        except Exception as e:
            logger.debug(f"Failed to query InfluxDB: {e}")
    
    # Fallback to in-memory
    with sri_lock:
        return sri_history[-limit:]

@api_router.get("/metrics/summary")
async def get_metrics_summary():
    """Get summary stats from recent orders and activity"""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    
    total_orders = await db.orders.count_documents({})
    today_orders = await db.orders.count_documents({"created_at": {"$gte": day_ago}})
    total_users = await db.users.count_documents({})
    total_products = await db.products.count_documents({})
    
    # Revenue
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total"}}}]
    revenue_result = await db.orders.aggregate(pipeline).to_list(1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0
    
    return {
        "total_orders": total_orders,
        "today_orders": today_orders,
        "total_users": total_users,
        "total_products": total_products,
        "total_revenue": round(total_revenue, 2)
    }

@api_router.get("/metrics/transactions")
async def get_transaction_metrics():
    """Get detailed transaction metrics for business analytics"""
    # Sales by category
    category_pipeline = [
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.name",
            "value": {"$sum": {"$multiply": ["$items.price", "$items.quantity"]}}
        }},
        {"$sort": {"value": -1}},
        {"$limit": 5}
    ]
    category_result = await db.orders.aggregate(category_pipeline).to_list(10)
    by_category = [{"name": r["_id"], "value": round(r["value"], 2)} for r in category_result]
    
    # Orders by status
    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    status_result = await db.orders.aggregate(status_pipeline).to_list(10)
    by_status = [{"status": r["_id"].replace("_", " ").title(), "count": r["count"]} for r in status_result]
    
    # Hourly distribution (mock for now based on created_at)
    hourly_pipeline = [
        {"$group": {
            "_id": {"$hour": "$created_at"},
            "count": {"$sum": 1},
            "revenue": {"$sum": "$total"}
        }},
        {"$sort": {"_id": 1}}
    ]
    hourly_result = await db.orders.aggregate(hourly_pipeline).to_list(24)
    hourly = [{"hour": f"{r['_id']}:00", "orders": r["count"], "revenue": round(r["revenue"], 2)} for r in hourly_result]
    
    # Recent orders for live feed
    recent_orders = await db.orders.find().sort("created_at", -1).limit(10).to_list(10)
    recent = [{
        "id": str(o["_id"]),
        "total": o["total"],
        "status": o["status"],
        "items_count": len(o["items"]),
        "created_at": o["created_at"].isoformat()
    } for o in recent_orders]
    
    return {
        "by_category": by_category,
        "by_status": by_status,
        "hourly": hourly,
        "recent_orders": recent
    }

@api_router.post("/metrics/generate-traffic")
async def generate_traffic():
    """Generate synthetic traffic for testing"""
    # This endpoint is mainly used to trigger metrics collection
    # The actual traffic generation happens on the frontend
    return {"message": "Traffic generation triggered", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== ALERTS API ====================

@api_router.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent alerts"""
    return alert_manager.get_recent_alerts(limit)

@api_router.get("/alerts/config")
async def get_alert_config():
    """Get current alert thresholds"""
    return {
        "sri_critical": SRI_CRITICAL_THRESHOLD,
        "sri_warning": SRI_WARNING_THRESHOLD,
        "latency_critical": LATENCY_CRITICAL_THRESHOLD,
        "error_rate_critical": ERROR_RATE_CRITICAL_THRESHOLD,
        "cooldown_seconds": alert_manager.alert_cooldown
    }

class AlertConfigUpdate(BaseModel):
    sri_critical: Optional[float] = None
    sri_warning: Optional[float] = None
    latency_critical: Optional[float] = None
    error_rate_critical: Optional[float] = None
    cooldown_seconds: Optional[int] = None

@api_router.put("/alerts/config")
async def update_alert_config(config: AlertConfigUpdate, user: dict = Depends(get_current_user)):
    """Update alert thresholds (admin only)"""
    global SRI_CRITICAL_THRESHOLD, SRI_WARNING_THRESHOLD, LATENCY_CRITICAL_THRESHOLD, ERROR_RATE_CRITICAL_THRESHOLD
    
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if config.sri_critical is not None:
        SRI_CRITICAL_THRESHOLD = config.sri_critical
    if config.sri_warning is not None:
        SRI_WARNING_THRESHOLD = config.sri_warning
    if config.latency_critical is not None:
        LATENCY_CRITICAL_THRESHOLD = config.latency_critical
    if config.error_rate_critical is not None:
        ERROR_RATE_CRITICAL_THRESHOLD = config.error_rate_critical
    if config.cooldown_seconds is not None:
        alert_manager.alert_cooldown = config.cooldown_seconds
    
    return {"message": "Alert config updated", "config": await get_alert_config()}

@api_router.delete("/alerts")
async def clear_alerts(user: dict = Depends(get_current_user)):
    """Clear all alerts (admin only)"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with alert_manager.lock:
        alert_manager.alerts = []
    
    return {"message": "Alerts cleared"}


@api_router.get("/admin/webhooks/status")
async def get_webhook_status(user: dict = Depends(get_current_user)):
    """Return which external webhooks are configured for critical SRI alerts."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    configured = webhook_notifier.is_configured()
    return {
        "configured": configured,
        "any_configured": any(configured.values()),
        "cooldown_seconds": webhook_notifier.cooldown_sec,
        "fires_on": "critical",
    }


@api_router.post("/admin/webhooks/test")
async def test_webhook(user: dict = Depends(get_current_user)):
    """Send a test alert to all configured webhooks (bypasses cooldown)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    now = datetime.now(timezone.utc)
    test_alert = {
        "id": f"webhook_test_{now.timestamp()}",
        "type": "critical",
        "category": "test",
        "title": "Webhook Test — FreshCart SRI Engine",
        "message": "This is a manual test alert sent from the admin dashboard.",
        "value": 0.0,
        "threshold": 0.0,
        "timestamp": now.isoformat(),
        "action": "No action required — delivery verification only",
    }
    results = await webhook_notifier.dispatch(test_alert, force=True)
    return {
        "sent_at": now.isoformat(),
        "configured": webhook_notifier.is_configured(),
        "results": results,
    }

# WebSocket for real-time alerts
@app.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time alert notifications"""
    await alert_manager.add_client(websocket)
    try:
        while True:
            # Keep connection alive, listen for any client messages
            data = await websocket.receive_text()
            # Handle ping/pong or other client messages
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        alert_manager.remove_client(websocket)
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
        alert_manager.remove_client(websocket)

@api_router.get("/metrics/golden-signals")
async def get_golden_signals():
    """Get the 4 Golden Signals (Latency, Traffic, Errors, Saturation)"""
    golden = metrics_aggregator.get_golden_signals()
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    
    # Track history point
    metrics_aggregator.golden_signals_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency": golden["latency"]["value"],
        "traffic": golden["traffic"]["value"],
        "errors": golden["errors"]["value"],
        "saturation": golden["saturation"]["value"],
        "sri": sri_data["sri"]
    })
    if len(metrics_aggregator.golden_signals_history) > 100:
        metrics_aggregator.golden_signals_history = metrics_aggregator.golden_signals_history[-100:]
    
    return {
        "signals": golden,
        "sri": round(sri_data["sri"], 4),
        "signal_contributions": sri_data.get("signal_contributions", {}),
        "history": metrics_aggregator.golden_signals_history[-30:]
    }


@api_router.get("/metrics/customer-experience")
async def get_customer_experience():
    """Get customer experience metrics (Apdex, P50/P95/P99, Availability, Error Budget)"""
    return metrics_aggregator.get_customer_experience()


@api_router.get("/metrics/business")
async def get_business_metrics():
    """Get business conversion funnel and revenue metrics"""
    return business_metrics.get_funnel()


@api_router.get("/metrics/reliability")
async def get_reliability_score():
    """Get composite Reliability Score — resilience (SRI) as means to business reliability.
    Combines SRI, Apdex, Availability, and Conversion into one business-outcome metric."""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    cx = metrics_aggregator.get_customer_experience()
    reliability = business_metrics.compute_reliability_score(
        sri=sri_data["sri"], apdex=cx["apdex"], availability=cx["availability"]
    )
    reliability["funnel"] = business_metrics.get_funnel()
    reliability["trend"] = sri_interpolator.analyze()
    return reliability


@api_router.get("/metrics/attribution")
async def get_sri_attribution():
    """Decompose current SRI state into per-node, per-signal attributions
    with business impact mapping (which signal hurts conversion/apdex/revenue)."""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    golden = metrics_aggregator.get_golden_signals()
    attribution = attribution_engine.attribute_dip(node_metrics, sri_data, golden)
    attribution["current_sri"] = round(sri_data["sri"], 4)
    attribution["golden_signals"] = golden
    return attribution


# ==================== AUTO-HEALING ENGINE ====================




healing_engine = HealingEngine()
sequence_optimizer = HealingSequenceOptimizer(healing_engine)


# ==================== AGGRESSIVE / RELIABILITY-AWARE HEALING ====================


aggressive_healing = AggressiveHealingMode()


async def aggressive_healing_loop():
    """Runs every 5 s. Proactively fires the highest-scoring action when
    resilience debt is accumulating or a dip is predicted."""
    logger.info("aggressive_healing_loop started")
    await asyncio.sleep(15)  # warm-up
    while True:
        try:
            if not aggressive_healing.enabled:
                await asyncio.sleep(5)
                continue
            node_metrics = metrics_aggregator.get_all_metrics()
            if not any(m.get("traffic", 0) > 0 for m in node_metrics.values()):
                await asyncio.sleep(5)
                continue
            sri_data = compute_sri_from_metrics(node_metrics)
            sri = float(sri_data["sri"])
            # Pull recent debt + SRI trend (debt rate = current Φ since E = ∫Φ dt)
            debt_summary = resilience_debt.snapshot()
            debt_rate = float(debt_summary.get("current_phi", 0.0))

            # === Resolve pending phi-before measurements: any fire whose
            # 5-second window has elapsed gets its phi reduction recorded.
            now_ts = time.time()
            for aid_p, pendings in list(aggressive_healing._pending_phi.items()):
                resolved = []
                kept = []
                for t_fired, phi_before, fire_idx in pendings:
                    if now_ts - t_fired >= 4.5:
                        # Δ = phi_before − phi_now  (positive = action reduced debt rate)
                        reduction = phi_before - debt_rate
                        resolved.append(reduction)
                    else:
                        kept.append((t_fired, phi_before, fire_idx))
                if resolved:
                    aggressive_healing.action_phi_reduction.setdefault(aid_p, []).extend(resolved)
                    if len(aggressive_healing.action_phi_reduction[aid_p]) > 50:
                        aggressive_healing.action_phi_reduction[aid_p] = aggressive_healing.action_phi_reduction[aid_p][-50:]
                if kept:
                    aggressive_healing._pending_phi[aid_p] = kept
                else:
                    del aggressive_healing._pending_phi[aid_p]

            trend = sri_interpolator.analyze()
            v = float(trend.get("velocity", 0.0))
            a = float(trend.get("acceleration", 0.0))
            # Find target: highest service_pressure node
            topo = healing_engine.analyze_topology(node_metrics, sri_data, granularity="service")
            stressed = sorted(topo.get("services", []), key=lambda s: s.get("service_pressure", 0), reverse=True)
            target = stressed[0] if stressed else None
            max_pressure = float(target.get("service_pressure", 0.0)) if target else 0.0
            reason = aggressive_healing.should_fire(sri, debt_rate, v, a, max_pressure)
            # Always track reliability for the 60-s gain metric + counterfactual baseline
            try:
                apdex = float(metrics_aggregator.get_golden_signals().get("apdex_score", 0.95))
                error_rate = float(metrics_aggregator.get_all_metrics().get("API", {}).get("error", 0) or 0)
                avail_pct = max(0.0, min(100.0, (1.0 - min(1.0, error_rate)) * 100.0))
                rel = business_metrics.compute_reliability_score(sri, apdex, avail_pct)
                aggressive_healing.reliability_with_aggressive.append(float(rel.get("score", 0.0)))
                if len(aggressive_healing.reliability_with_aggressive) > 60:
                    aggressive_healing.reliability_with_aggressive = aggressive_healing.reliability_with_aggressive[-60:]
            except Exception as _e:
                logger.debug(f"reliability sample: {_e}")
            if not reason or not target:
                await asyncio.sleep(5)
                continue
            target_node = target.get("service")
            available_actions = list(healing_engine.actions.keys())
            ranked = aggressive_healing.rank_actions(available_actions)
            # Skip actions in cooldown / exhausted
            chosen = None
            for aid, score, breakdown in ranked:
                if not healing_engine._is_action_exhausted(aid):
                    chosen = (aid, score, breakdown)
                    break
            if not chosen or chosen[1] < -aggressive_healing.min_lift_threshold:
                # Score is too negative — don't fire to avoid making things worse
                await asyncio.sleep(5)
                continue
            aid, score, breakdown = chosen
            result = healing_engine.execute_action(
                action_id=aid,
                triggered_by="aggressive_mode",
                target_node_override=target_node,
            )
            if result.get("success"):
                fire_idx = len(aggressive_healing.recent_actions)
                sri_delta_val = float(result["record"].get("sri_delta", 0) or 0)
                # Accumulate positive SRI lift for counterfactual reliability
                if sri_delta_val > 0:
                    aggressive_healing.cumulative_proactive_sri_lift += sri_delta_val
                # Queue a phi-after check for the next tick to compute Φ reduction
                aggressive_healing._pending_phi.setdefault(aid, []).append(
                    (time.time(), debt_rate, fire_idx)
                )
                aggressive_healing.recent_actions.append({
                    "t": datetime.now(timezone.utc).isoformat(),
                    "action_id": aid,
                    "target": target_node,
                    "reason": reason,
                    "score": score,
                    "breakdown": breakdown,
                    "sri_delta": result["record"].get("sri_delta"),
                    "phi_before": round(debt_rate, 6),
                })
                if len(aggressive_healing.recent_actions) > 50:
                    aggressive_healing.recent_actions = aggressive_healing.recent_actions[-50:]
                logger.info(f"aggressive_heal: {aid}@{target_node} reason={reason} score={score:.4f}")
        except Exception as e:
            logger.debug(f"aggressive_healing_loop: {e}")
        await asyncio.sleep(5)


@api_router.get("/healing/aggressive/status")
async def get_aggressive_status():
    return aggressive_healing.status()


@api_router.get("/healing/aggressive/preview-ranking")
async def aggressive_preview_ranking():
    """iter 40 — compute the current rank order on-demand for operator
    visibility, even when the aggressive engine isn't actively firing.
    Surfaces the cheap-first escalation in real time."""
    available = list(healing_engine.actions.keys())
    ranked = aggressive_healing.rank_actions(available)
    return {
        "ranked": [
            {"action": aid, "score": score, **breakdown}
            for aid, score, breakdown in ranked
        ],
        "low_cost_bias": aggressive_healing.AGGR_LOW_COST_BIAS,
        "plateau_threshold": aggressive_healing.AGGR_PLATEAU_THRESHOLD,
    }


class AggressiveToggleRequest(BaseModel):
    enabled: Optional[bool] = None
    debt_rate_threshold: Optional[float] = None
    min_lift_threshold: Optional[float] = None


@api_router.post("/healing/aggressive/toggle")
async def toggle_aggressive(req: AggressiveToggleRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if req.enabled is not None:
        aggressive_healing.enabled = bool(req.enabled)
    if req.debt_rate_threshold is not None:
        aggressive_healing.debt_rate_threshold = max(0.0, float(req.debt_rate_threshold))
    if req.min_lift_threshold is not None:
        aggressive_healing.min_lift_threshold = max(0.0, float(req.min_lift_threshold))
    return aggressive_healing.status()

# ==================== END AGGRESSIVE HEALING ====================


# ==================== PERMANENT FUNNEL HEALER (iter 25) ====================



permanent_funnel_healer = PermanentFunnelHealer()


# ==================== LADDER SYNTHESIZER (iter 30) ====================
# "Programs writing programs" — synthesizes new escalation_ladder configs
# from observed reliability gains and atomically swaps them into the engine.
ladder_synthesizer = LadderSynthesizer(healing_engine, business_metrics, db=db)
ladder_synth_mod.synthesizer = ladder_synthesizer


# ==================== OPERATIONAL PHASE CLASSIFIER (iter 31) ====================
# Implements the Operational Phase-Transition Diagram. Computes composite stress
# σ = αL+βQ+γM+δE, classifies each service into one of 7 phases, exposes
# retry-amplification and healing-saturation flags consumed by AggressiveHealing
# and LadderSynthesizer.
phase_classifier_instance = PhaseClassifier()
phase_mod.classifier = phase_classifier_instance


@api_router.get("/phase/state")
async def phase_state():
    return phase_classifier_instance.status()


@api_router.get("/phase/history")
async def phase_history(limit: int = 60):
    return {"samples": phase_classifier_instance.history_snapshot(limit=limit)}


# ==================== RUM LADDER LEARNER (iter 32) ====================
# Mines healing-action sequences whose RUM (real-user) outcomes
# improved page_load / perceived_speed / error_shown_rate. Feeds a
# sequence-bonus term into LadderSynthesizer.compute_gain_matrix so the
# next synthesised ladder favors actions that have *user-felt* impact.
rum_ladder_learner_instance = RumLadderLearner()
rum_learner_mod.learner = rum_ladder_learner_instance


@api_router.get("/healing/rum-sequences/top")
async def rum_sequences_top(limit: int = 20):
    return {
        "status": rum_ladder_learner_instance.status(),
        "sequences": rum_ladder_learner_instance.top(limit=limit),
    }


@api_router.get("/healing/rum-sequences/status")
async def rum_sequences_status():
    return rum_ladder_learner_instance.status()


@api_router.post("/healing/rum-sequences/run-now")
async def rum_sequences_run_now(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return await rum_ladder_learner_instance.pass_once()


# ==================== ACTION STAGNATION GUARD (iter 34) ====================
# Inner-loop complement to LadderSynthesizer. Watches every healing
# execution; pairs (node, action) that produce N consecutive |ΔSRI|<ε
# attempts are dynamically removed from the available action set until
# a cooldown expires.
action_stagnation_guard = ActionStagnationGuard()
action_stagnation_mod.guard = action_stagnation_guard


class StagnationRestoreReq(BaseModel):
    node: str
    action: str


@api_router.get("/healing/stagnation/state")
async def stagnation_state():
    return action_stagnation_guard.status()


@api_router.get("/healing/stagnation/events")
async def stagnation_events(limit: int = 30):
    return {"events": action_stagnation_guard.events(limit=limit)}


@api_router.post("/healing/stagnation/restore")
async def stagnation_restore(req: StagnationRestoreReq, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = action_stagnation_guard.force_restore(req.node, req.action)
    return {"restored": ok, "node": req.node, "action": req.action}


@api_router.post("/healing/stagnation/reset")
async def stagnation_reset(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    cleared = action_stagnation_guard.reset()
    return {"cleared": cleared}


# ==================== ECONOMIC RELIABILITY (iter 35, Phase 3) ====================
# Ties resilience metrics to actual conversion-funnel + revenue.
# Implements R_econ = W/C_T (Eq. 57) and R = W·R_S/C_T (Eq. 58) from RSM.
economic_reliability_tracker = EconomicReliabilityTracker()
econ_rel_mod.tracker = economic_reliability_tracker


@api_router.get("/economic-reliability/state")
async def economic_reliability_state():
    return economic_reliability_tracker.status()


@api_router.get("/economic-reliability/trend")
async def economic_reliability_trend(limit: int = 60):
    return economic_reliability_tracker.trend(limit=limit)


# ==================== STABILITY FUNCTIONAL Ψ (iter 42, Phase 2) ====================
# Lyapunov-style scalar Ψ(L̂, Q, M, E) over the live phase-space.
# Ψ → 0 iff every node sits at Ψ_c; dΨ/dt < 0 ⇒ system stabilising.
stability_functional = StabilityFunctional()
stab_mod.functional = stability_functional


@api_router.get("/stability/state")
async def stability_state():
    return stability_functional.status()


@api_router.get("/stability/trend")
async def stability_trend(limit: int = 60):
    return stability_functional.trend(limit=limit)


# ==================== RUNTIME STIFFNESS TENSOR ====================
# RST models each service as a structural element with a 6-component
# stiffness tensor K = (K_A, K_H, K_S, K_D, K_F, K_R).
# Effective stiffness: K_eff = geometric weighted mean of components.
# Stress σ and Strain ε follow Hooke's analogy: ε = σ / K_eff.
rst_engine_instance = RSTEngine()
rst_mod.metrics_aggregator       = metrics_aggregator
rst_mod.phase_classifier_instance = phase_classifier_instance
rst_mod.healing_engine            = healing_engine


class RSTScenarioRequest(BaseModel):
    name: str
    overrides: Dict[str, Any]
    duration_s: float = 30.0


@api_router.get("/rst/state")
async def rst_state():
    return rst_engine_instance.state()


@api_router.get("/rst/history")
async def rst_history(limit: int = 60):
    return {"samples": rst_engine_instance.history_snapshot(limit=limit)}


@api_router.post("/rst/scenario")
async def rst_scenario(req: RSTScenarioRequest):
    rst_engine_instance.apply_scenario(req.name, req.overrides, req.duration_s)
    return {"ok": True, "name": req.name, "duration_s": req.duration_s}


@api_router.delete("/rst/scenario")
async def rst_scenario_clear():
    rst_engine_instance.clear_scenario()
    return {"ok": True}


class LadderToggleRequest(BaseModel):
    enabled: Optional[bool] = None


@api_router.get("/healing/ladder/current")
async def ladder_current():
    from obs.engines.ladder_synthesizer import _ACTION_COMPLEXITY
    s = ladder_synthesizer.status()
    # iter 39 — annotate the live ladder with per-position complexity
    # tier so the dashboard can show the low→high complexity ramp.
    ladder = s.get("current_ladder") or {}
    s["complexity_ladder"] = {
        node: [
            {"action": a, "complexity": _ACTION_COMPLEXITY.get(a, 0.30)}
            for a in actions
        ]
        for node, actions in ladder.items()
    }
    return s


@api_router.get("/healing/ladder/history")
async def ladder_history(limit: int = 20):
    return {"versions": ladder_synthesizer.list_history(limit=limit)}


@api_router.get("/healing/ladder/gain-matrix")
async def ladder_gain_matrix():
    from obs.engines.ladder_synthesizer import _ACTION_COMPLEXITY, LADDER_COMPLEXITY_BIAS
    return {
        "gain_matrix": ladder_synthesizer.compute_gain_matrix(),
        "version": ladder_synthesizer.version,
        # iter 39 — expose the per-action complexity tier so the
        # dashboard can render the "low-complexity → high-complexity"
        # escalation order clearly.
        "complexity": dict(_ACTION_COMPLEXITY),
        "complexity_bias": LADDER_COMPLEXITY_BIAS,
    }


@api_router.post("/healing/ladder/synthesize")
async def ladder_synthesize(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return await ladder_synthesizer.synthesize(reason="manual", force=True)


@api_router.post("/healing/ladder/rollback")
async def ladder_rollback(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return await ladder_synthesizer.rollback_to_previous(reason="manual")


@api_router.post("/healing/ladder/toggle")
async def ladder_toggle(req: LadderToggleRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if req.enabled is not None:
        ladder_synthesizer.enabled = bool(req.enabled)
    return ladder_synthesizer.status()



async def permanent_funnel_healing_loop():
    """Runs every 30 s. Detects funnel stagnation and installs permanent fixes."""
    logger.info("permanent_funnel_healing_loop started")
    # Wait for the rest of the obs service to initialise + load persisted state
    await asyncio.sleep(20)
    await permanent_funnel_healer.load_persisted()
    while True:
        try:
            if not permanent_funnel_healer.enabled:
                await asyncio.sleep(30)
                continue
            funnel = business_metrics.get_funnel()
            stagnation = permanent_funnel_healer.detect_stagnation(funnel)
            if stagnation:
                node_metrics = metrics_aggregator.get_all_metrics()
                sri_data = compute_sri_from_metrics(node_metrics)
                golden = metrics_aggregator.get_golden_signals()
                attribution = attribution_engine.attribute_dip(node_metrics, sri_data, golden)
                await permanent_funnel_healer.install_fix(attribution, stagnation)
            else:
                # Idle tick — auto-decay existing permanent fixes
                await permanent_funnel_healer.decay_idle()
        except Exception as e:
            logger.debug(f"permanent_funnel_healing_loop: {e}")
        await asyncio.sleep(30)


@api_router.get("/healing/permanent-fixes")
async def get_permanent_fixes():
    return permanent_funnel_healer.status()


class PermanentFixToggleRequest(BaseModel):
    enabled: Optional[bool] = None
    stagnation_window: Optional[int] = None
    conversion_stagnation_threshold: Optional[float] = None
    decay_factor: Optional[float] = None


@api_router.post("/healing/permanent-fixes/toggle")
async def toggle_permanent_fixes(req: PermanentFixToggleRequest, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if req.enabled is not None:
        permanent_funnel_healer.enabled = bool(req.enabled)
    if req.stagnation_window is not None:
        permanent_funnel_healer.stagnation_window = max(2, int(req.stagnation_window))
    if req.conversion_stagnation_threshold is not None:
        permanent_funnel_healer.conversion_stagnation_threshold = max(0.0, min(1.0, float(req.conversion_stagnation_threshold)))
    if req.decay_factor is not None:
        permanent_funnel_healer.decay_factor = max(0.5, min(1.0, float(req.decay_factor)))
    return permanent_funnel_healer.status()


@api_router.delete("/healing/permanent-fixes/{node}/{signal}")
async def revert_permanent_fix(node: str, signal: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if node in PERMANENT_FIX_REGISTRY and signal in PERMANENT_FIX_REGISTRY[node]:
        del PERMANENT_FIX_REGISTRY[node][signal]
        if not PERMANENT_FIX_REGISTRY[node]:
            del PERMANENT_FIX_REGISTRY[node]
    await db.permanent_fixes.delete_one({"node": node, "signal": signal})
    return {"reverted": True, "node": node, "signal": signal}

# ==================== END PERMANENT FUNNEL HEALER ====================


# Background auto-propagation detector — predicts failure cascades from
# naturally-stressed services and (optionally) auto-heals along the path.
async def auto_propagation_loop():
    logger.info("auto_propagation_loop started")
    while True:
        try:
            cfg = auto_propagation_detector.snapshot()
            interval = cfg["interval_sec"]
            logger.info(f"auto_propagation tick: enabled={cfg['enabled']}")
            if not cfg["enabled"]:
                await asyncio.sleep(interval)
                continue

            node_metrics = metrics_aggregator.get_all_metrics()
            sri_data = compute_sri_from_metrics(node_metrics)
            # Use perform_fea (which calls analyze_topology service-mode + renames
            # services→elements + von_mises_stress) so the field names match.
            topo = healing_engine.perform_fea(node_metrics, sri_data)
            with auto_propagation_detector._lock:
                auto_propagation_detector.last_run_at = time.time()
            logger.info(f"auto_propagation: scanned {len(topo['elements'])} services, threshold={cfg['stress_pressure_threshold']}")

            threshold = cfg["stress_pressure_threshold"]
            stressed = [
                {
                    "node": svc["node"],
                    "pressure": svc["von_mises_stress"],
                    "yield_exceeded": svc["yield_exceeded"],
                }
                for svc in topo["elements"]
                if svc["von_mises_stress"] >= threshold or svc.get("yield_exceeded")
            ]

            new_active: Dict[str, Dict] = {}
            for sn in stressed:
                src = sn["node"]
                # Quick propagation simulation (tight steps to keep latency low)
                try:
                    prop = healing_engine.simulate_fault_propagation(
                        source=src,
                        fault_strength=min(1.0, max(0.3, sn["pressure"] * 6)),
                        steps=15,
                        dt=0.5,
                        granularity="service",
                    )
                except Exception:
                    continue

                downstream = [
                    n for n in prop["node_summary"]
                    if not n["is_source"] and n["peak_fault"] >= 0.05
                ]
                snap = {
                    "source": src,
                    "pressure": sn["pressure"],
                    "yield_exceeded": sn["yield_exceeded"],
                    "downstream": downstream,
                    "max_phi": prop["max_phi"],
                    "max_infected": prop["max_infected"],
                    "detected_at": time.time(),
                }
                new_active[src] = snap

                # Fire alert (deduplicated by AlertManager id-key + cooldown)
                if downstream:
                    try:
                        await alert_manager.check_and_alert(
                            sri=sri_data["sri"],
                            avg_latency=node_metrics.get(src, {}).get("latency", 0) or 0,
                            avg_error=node_metrics.get(src, {}).get("error", 0) or 0,
                            node_metrics=node_metrics,
                        )
                    except Exception as e:
                        logger.debug(f"propagation alert error: {e}")

                # Autonomous path-based healing
                if cfg["autonomous_heal"]:
                    # Build stressed-nodes input: source + first ~3 downstream
                    candidates = [{"node": src, "pressure": sn["pressure"], "yield_exceeded": sn["yield_exceeded"]}]
                    for d in downstream[:3]:
                        candidates.append({
                            "node": d["node"],
                            "pressure": float(d["peak_fault"]) * 0.3,
                            "yield_exceeded": False,
                        })
                    try:
                        plan = sequence_optimizer.optimize(stressed_nodes=candidates, source=src, granularity="service")
                        executed_actions = []
                        for step in plan["sequence"][:2]:  # cap at 2 actions per cycle to avoid thrash
                            action = healing_engine.actions.get(step["action_id"])
                            if action and action.can_execute():
                                try:
                                    r = healing_engine.execute_action(
                                        action_id=step["action_id"],
                                        triggered_by="auto_propagation",
                                        target_node_override=step["target_node"],
                                    )
                                    executed_actions.append({
                                        "action_id": step["action_id"],
                                        "target_node": step["target_node"],
                                        "sri_delta": r.get("record", {}).get("sri_delta"),
                                    })
                                except Exception as e:
                                    logger.debug(f"auto-prop heal exec error: {e}")
                        snap["healing_executed"] = executed_actions
                        snap["plan"] = plan
                    except Exception as e:
                        logger.debug(f"auto-prop optimize error: {e}")

            with auto_propagation_detector._lock:
                auto_propagation_detector._active = new_active
                auto_propagation_detector.detection_count += len(new_active)
                auto_propagation_detector.last_run_at = time.time()
                if new_active:
                    auto_propagation_detector._history.append({
                        "t": time.time(),
                        "count": len(new_active),
                        "sources": list(new_active.keys()),
                    })
                    if len(auto_propagation_detector._history) > 30:
                        auto_propagation_detector._history = auto_propagation_detector._history[-30:]

        except Exception as e:
            logger.warning(f"auto_propagation_loop error: {e}", exc_info=True)
        await asyncio.sleep(auto_propagation_detector.interval_sec)


# Background auto-healing loop (precision mode, every 7s for swift response)
async def auto_healing_loop():
    while True:
        try:
            if healing_engine.enabled:
                executed = await healing_engine.auto_heal_cycle()
                if executed:
                    actions_log = [f"{r['action_id']}>{r['target_node']}({r.get('target_signal','?')})" for r in executed]
                    logger.info(f"Precision heal: {actions_log}")
        except Exception as e:
            logger.error(f"Auto-healing loop error: {e}")
        await asyncio.sleep(7)


class HealingToggle(BaseModel):
    enabled: Optional[bool] = None
    alert_driven: Optional[bool] = None

class HealingTrigger(BaseModel):
    action_id: str


@api_router.get("/healing")
async def get_healing_overview():
    """Healing engine overview — RCA-based auto-healing status"""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    golden = metrics_aggregator.get_golden_signals()
    fea = healing_engine.perform_fea(node_metrics, sri_data)
    rca = healing_engine.perform_rca(node_metrics, sri_data)
    trend = sri_interpolator.analyze()
    dip = healing_engine._detect_sri_dip(sri_data["sri"])
    return {
        "mode": "emergent_intelligence",
        "current_sri": round(sri_data["sri"], 4),
        "sri_dip": dip,
        "sri_trend": trend,
        "rca": {
            "root_cause_node": rca["root_cause_node"],
            "confidence": rca["confidence"],
            "rca_score": rca["rca_score"],
            "recommended_action": rca["recommended_action"],
            "multi_ca_targets": rca["multi_ca_targets"],
        },
        "fea": {
            "yield_threshold": fea["yield_threshold"],
            "yield_nodes": [{"node": yn["node"], "von_mises_stress": yn["von_mises_stress"],
                             "corrective_action": yn["corrective_action"]} for yn in fea["yield_nodes"]],
            "multi_ca_recommended": fea["multi_ca_recommended"],
            "recommended_cas": fea["recommended_cas"],
        },
        "adaptation": healing_engine.get_adaptation_status(),
        "engine": {
            "enabled": healing_engine.enabled,
            "alert_driven": healing_engine.alert_driven,
            "total_actions_executed": sum(a.execution_count for a in healing_engine.actions.values()),
            "loop_interval_s": 7,
        },
        "golden_signals": golden,
        "endpoints": [
            "/api/healing/status", "/api/healing/fea", "/api/healing/rca",
            "/api/healing/trend", "/api/healing/adaptation", "/api/healing/recommendations",
            "/api/healing/history", "/api/healing/toggle", "/api/healing/trigger"
        ]
    }



@api_router.get("/healing/status")
async def get_healing_status():
    """Get auto-healing engine status with FEA analysis, RCA, trend, and correction factors"""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    golden = metrics_aggregator.get_golden_signals()

    # Single FEA computation (cached for this request)
    fea = healing_engine.perform_fea(node_metrics, sri_data)

    status = healing_engine.get_status()
    status["current_sri"] = round(sri_data["sri"], 4)
    status["golden_signals"] = golden
    status["signal_contributions"] = sri_data.get("signal_contributions", {})
    status["recommendations"] = healing_engine.get_recommendations(node_metrics, sri_data["sri"])
    status["rca"] = {
        "root_cause_node": fea["elements"][0]["node"] if fea["elements"] else None,
        "yield_node_count": len(fea["yield_nodes"]),
    }
    status["fea_summary"] = {
        k: v for k, v in fea.items()
        if k in ("yield_nodes", "yield_threshold", "total_strain_energy", "max_von_mises",
                 "multi_ca_recommended", "recommended_cas", "sri_trend")
    }
    # iter 36 — active capacity boosts (scale-out persistence). Surface so
    # operators can verify scale-out actions are actually moving the
    # saturation denominator and we're no longer in the yielding state.
    now = time.time()
    status["capacity_boosts"] = {
        node: {
            "multiplier": round(b["multiplier"], 3),
            "expires_in_s": max(0, round(b["expires"] - now, 1)),
        }
        for node, b in metrics_aggregator.capacity_boosts.items()
        if b["expires"] > now
    }
    return status


@api_router.post("/healing/toggle")
async def toggle_healing(toggle: HealingToggle, user: dict = Depends(get_current_user)):
    """Enable/disable auto-healing and alert-driven healing"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if toggle.enabled is not None:
        healing_engine.enabled = toggle.enabled
    if toggle.alert_driven is not None:
        healing_engine.alert_driven = toggle.alert_driven
    return {
        "enabled": healing_engine.enabled,
        "alert_driven": healing_engine.alert_driven,
        "message": f"Auto-healing: {'on' if healing_engine.enabled else 'off'}, Alert-driven: {'on' if healing_engine.alert_driven else 'off'}"
    }


@api_router.post("/healing/trigger")
async def trigger_healing(trigger: HealingTrigger, user: dict = Depends(get_current_user)):
    """Manually trigger a healing action"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = healing_engine.execute_action(trigger.action_id, triggered_by="manual")
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # Broadcast healing event
    await alert_manager.broadcast({"type": "healing", "record": result["record"]})

    # Write to InfluxDB
    if write_api:
        try:
            point = Point("healing_action") \
                .tag("action_id", trigger.action_id) \
                .tag("triggered_by", "manual") \
                .field("sri_before", result["record"]["sri_before"]) \
                .field("sri_after", result["record"]["sri_after"]) \
                .field("sri_delta", result["record"]["sri_delta"]) \
                .time(datetime.now(timezone.utc), WritePrecision.MS)
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        except:
            pass

    return result["record"]


@api_router.get("/healing/history")
async def get_healing_history(limit: int = 50):
    """Get healing action history"""
    return healing_engine.history[-limit:]


@api_router.get("/healing/adaptation")
async def get_adaptation_status():
    """Get adaptive action selector status — shows exhausted vs effective actions,
    escalation ladders, and cross-node healing state."""
    adaptation = healing_engine.get_adaptation_status()
    adaptation["escalation_ladders"] = healing_engine.escalation_ladder
    adaptation["cross_node_map"] = healing_engine.node_neighbors
    # For each node, show which action would be selected and why
    node_metrics = metrics_aggregator.get_all_metrics()
    next_actions = {}
    for node in ["API", "Cache", "Backend", "DB", "Queue"]:
        selected = healing_engine._select_adaptive_action(node, node_metrics)
        if selected:
            next_actions[node] = {"action": selected, "status": "ready"}
        else:
            # Determine reason: all on cooldown or all exhausted?
            ladder = healing_engine.escalation_ladder.get(node, [])
            all_exhausted = all(
                healing_engine._is_action_exhausted(a) for a in ladder if a in healing_engine.actions
            )
            if all_exhausted and ladder:
                next_actions[node] = {"action": None, "status": "ALL_EXHAUSTED"}
            else:
                next_actions[node] = {"action": None, "status": "ALL_ON_COOLDOWN"}
    adaptation["next_action_per_node"] = next_actions
    return adaptation


@api_router.get("/healing/intelligence")
async def get_intelligence_state():
    """Get the Emergent Intelligence state: golden-signal-derived weights,
    multi-objective optimization weights, per-node signal importance, and hop history."""
    state = healing_engine.get_intelligence_state()
    state["current_sri"] = round(compute_sri_from_metrics(metrics_aggregator.get_all_metrics())["sri"], 4)
    # Recent learning history
    recent_hops = [h.get("intelligence") for h in healing_engine.history[-20:] if h.get("intelligence")]
    state["recent_hops"] = recent_hops[-10:]
    # Golden signals that drive the weights
    golden = metrics_aggregator.get_golden_signals()
    state["golden_signals"] = {k: {"value": v["value"], "health": v["health"]} for k, v in golden.items()}
    return state




@api_router.get("/healing/rca")
async def get_rca_analysis():
    """Combined Spectral + FEA Root Cause Analysis with multi-CA targets"""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    rca = healing_engine.perform_rca(node_metrics, sri_data)
    rca["golden_signals"] = metrics_aggregator.get_golden_signals()
    rca["current_sri"] = round(sri_data["sri"], 4)
    rca["fiedler_vector"] = sri_data.get("fiedler", [])
    return rca


@api_router.get("/healing/fea")
async def get_fea_analysis(granularity: str = "service"):
    """FEA topology endpoint with optional hierarchical drill-down.

    Parameters:
    - granularity: 'service' | 'component' | 'endpoint'
        * 'service'   — 6 core services (Frontend, API, Cache, DB, Queue, Backend)
        * 'component' — each service element embeds a `components` array with
                        sub-component FEA metrics + intra_edges
        * 'endpoint'  — each component (returned via 'component' first) is further
                        decomposed into its endpoint leaves (tier-3 mesh)
    """
    if granularity not in ("service", "component", "endpoint"):
        granularity = "service"

    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    fea = healing_engine.perform_fea(node_metrics, sri_data)
    fea["golden_signals"] = metrics_aggregator.get_golden_signals()
    fea["fiedler_vector"] = sri_data.get("fiedler", [])
    fea["eigenvalues"] = sri_data.get("eigenvalues", [])
    fea["granularity"] = granularity

    if granularity in ("component", "endpoint"):
        # Run fine-grained topology for sub-component stress/yield metrics
        fine = healing_engine.analyze_topology(node_metrics, sri_data, granularity="fine")
        fine_services = fine.get("services", [])
        fine_edges = fine.get("path_analysis", [])
        fine_threshold = fine.get("failure_threshold", fea.get("yield_threshold", 0.1))

        # Group fine services by parent (name before '.')
        children_by_parent: Dict[str, List[Dict]] = {}
        for s in fine_services:
            name = s.get("service", "")
            parent = name.split(".")[0] if "." in name else name
            child = {
                "component": name,
                "short_name": name.split(".")[-1] if "." in name else name,
                "von_mises_stress": s["service_pressure"],
                "service_pressure": s["service_pressure"],
                "strain_energy": s["health_debt"],
                "health_debt": s["health_debt"],
                "yield_exceeded": bool(s["service_pressure"] > fine_threshold),
                "load": s["degradation_load"],
                "displacement": s["service_drift"],
                "corrective_action": s.get("corrective_action"),
                "metrics": s.get("metrics", {}),
            }
            children_by_parent.setdefault(parent, []).append(child)

        # Intra-service edges (within a parent)
        intra_edges_by_parent: Dict[str, List[Dict]] = {}
        for e in fine_edges:
            src_parent = e["source"].split(".")[0]
            tgt_parent = e["target"].split(".")[0]
            if src_parent == tgt_parent:
                intra_edges_by_parent.setdefault(src_parent, []).append({
                    "source": e["source"],
                    "target": e["target"],
                    "short_source": e["source"].split(".")[-1],
                    "short_target": e["target"].split(".")[-1],
                    "edge_strain": e["path_fragility"],
                    "stiffness": e["connection_strength"],
                    "elongation": e["drift_differential"],
                })

        # Attach components + intra-edges to each service element
        for svc in fea["elements"]:
            parent = svc["node"]
            svc["components"] = children_by_parent.get(parent, [])
            svc["intra_edges"] = intra_edges_by_parent.get(parent, [])
            svc["component_yield_count"] = sum(1 for c in svc["components"] if c["yield_exceeded"])
            svc["max_component_stress"] = max([c["von_mises_stress"] for c in svc["components"]], default=0)

        fea["component_yield_threshold"] = round(float(fine_threshold), 4)
        fea["mesh_size_fine"] = fine.get("mesh_size", 0)

    if granularity == "endpoint":
        # Tier-3 drill-down: run endpoint topology and attach endpoints + intra-component
        # endpoint edges to each component object.
        ep_topo = healing_engine.analyze_topology(node_metrics, sri_data, granularity="endpoint")
        ep_services = ep_topo.get("services", [])
        ep_paths = ep_topo.get("path_analysis", [])
        ep_threshold = ep_topo.get("failure_threshold", fea.get("yield_threshold", 0.1))

        # Group endpoints by their parent component (first two dotted segments)
        leaves_by_component: Dict[str, List[Dict]] = {}
        for s in ep_services:
            name = s.get("service", "")
            parts = name.split(".")
            parent_component = ".".join(parts[:2]) if len(parts) >= 2 else name
            leaf = {
                "endpoint": name,
                "short_name": parts[-1],
                "von_mises_stress": s["service_pressure"],
                "service_pressure": s["service_pressure"],
                "strain_energy": s["health_debt"],
                "yield_exceeded": bool(s["service_pressure"] > ep_threshold),
                "load": s["degradation_load"],
                "displacement": s["service_drift"],
                "metrics": s.get("metrics", {}),
            }
            leaves_by_component.setdefault(parent_component, []).append(leaf)

        # Intra-component endpoint edges (both endpoints under same component)
        intra_edges_by_component: Dict[str, List[Dict]] = {}
        for e in ep_paths:
            src_comp = ".".join(e["source"].split(".")[:2])
            tgt_comp = ".".join(e["target"].split(".")[:2])
            if src_comp == tgt_comp:
                intra_edges_by_component.setdefault(src_comp, []).append({
                    "source": e["source"],
                    "target": e["target"],
                    "short_source": e["source"].split(".")[-1],
                    "short_target": e["target"].split(".")[-1],
                    "edge_strain": e["path_fragility"],
                    "stiffness": e["connection_strength"],
                })

        # Attach endpoints + edges to each component already on each service
        for svc in fea["elements"]:
            for comp in svc.get("components", []):
                cname = comp["component"]
                comp["endpoints"] = leaves_by_component.get(cname, [])
                comp["endpoint_edges"] = intra_edges_by_component.get(cname, [])
                comp["endpoint_yield_count"] = sum(1 for ep in comp["endpoints"] if ep["yield_exceeded"])
                comp["max_endpoint_stress"] = max(
                    [ep["von_mises_stress"] for ep in comp["endpoints"]], default=0
                )

        fea["endpoint_yield_threshold"] = round(float(ep_threshold), 4)
        fea["mesh_size_endpoint"] = ep_topo.get("mesh_size", 0)

    return fea


@api_router.get("/healing/topology/schema")
async def get_topology_schema():
    """Shared topology schema (services, components, endpoints, edges, layout).

    Single source of truth consumed by the frontend FEA topology map so the
    same service/component/endpoint names and positions aren't duplicated across
    frontend and backend. Extend TOPOLOGY_SCHEMA in obs_server.py to change both.
    """
    return {
        "services": [dict(s) for s in TOPOLOGY_SCHEMA["services"]],
        "inter_edges": [list(e) for e in TOPOLOGY_SCHEMA["inter_edges"]],
        "components": {k: list(v) for k, v in TOPOLOGY_SCHEMA["components"].items()},
        "fine_edges": [list(e) for e in TOPOLOGY_SCHEMA["fine_edges"]],
        "endpoints": {k: list(v) for k, v in TOPOLOGY_SCHEMA["endpoints"].items()},
        "endpoint_edges": [list(e) for e in TOPOLOGY_SCHEMA["endpoint_edges"]],
        "tier_counts": {
            "services": len(TOPOLOGY_SCHEMA["services"]),
            "components": sum(len(v) for v in TOPOLOGY_SCHEMA["components"].values()),
            "endpoints": sum(len(v) for v in TOPOLOGY_SCHEMA["endpoints"].values()),
        },
        "version": 2,
    }


@api_router.get("/healing/topology")
async def get_topology_analysis(granularity: str = "service"):
    """Service Mesh Topology Analysis with dynamic granularity.
    
    Parameters:
    - granularity: 'service' (5 core nodes) or 'fine' (sub-components, ~12 nodes)
    
    Returns: services, critical_services, path_analysis, degradation_load,
    service_drift, failure_threshold, and multi-CA recommendations."""
    if granularity not in ("service", "fine"):
        granularity = "service"
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    topo = healing_engine.analyze_topology(node_metrics, sri_data, granularity=granularity)
    topo["golden_signals"] = metrics_aggregator.get_golden_signals()
    return topo


@api_router.get("/healing/trend")
async def get_sri_trend():
    """SRI trend analysis via polynomial interpolation.
    Returns velocity (dSRI/dt), acceleration, predicted future values, trend label.
    Also reports the non-recoverable-state criterion (Eq. 7 from SRI/SAI paper):
      d(SRI)/dt ≈ 0 ∧ SRI < SRI_threshold."""
    trend = sri_interpolator.analyze()
    trend["thresholds"] = {
        "critical": SRI_CRITICAL_THRESHOLD,
        "warning": SRI_WARNING_THRESHOLD,
    }
    return trend


@api_router.get("/healing/path-to-stable")
async def healing_path_to_stable(node: Optional[str] = None, max_steps: int = 5):
    """iter 45 — fastest path to Ψ_s.

    Per-node greedy forward-simulation: returns the minimum-cost sequence
    of healing actions that takes each node from its current phase-space
    coordinates toward the stable operating point Ψ_s, with monotonically
    decreasing d². If `node` is provided, returns a single plan; otherwise
    returns a per-node map of plans for all classified nodes.
    """
    if node:
        return healing_engine.plan_path_to_stable(node, max_steps=max_steps)
    snap = getattr(phase_classifier_instance, "latest", None)
    if snap is None:
        return {"applicable": False, "reason": "phase_classifier not ready"}
    plans = {n: healing_engine.plan_path_to_stable(n, max_steps=max_steps)
             for n in snap.per_node.keys()}
    # Aggregate stats
    total_actions = sum(p.get("total_actions", 0) for p in plans.values() if p.get("applicable"))
    total_cost    = sum(p.get("total_cost", 0.0) for p in plans.values() if p.get("applicable"))
    worst = max(plans.values(),
                key=lambda p: p.get("final_d2", 0.0) if p.get("applicable") else -1,
                default=None)
    return {
        "applicable": True,
        "plans": plans,
        "summary": {
            "total_actions_across_nodes": total_actions,
            "total_cost": round(total_cost, 4),
            "worst_node": (worst or {}).get("node"),
            "worst_final_d2": (worst or {}).get("final_d2"),
        },
    }


class ExecutePathRequest(BaseModel):
    node: str
    max_steps: int = 5
    dry_run: bool = False  # if True, just return the plan without firing


@api_router.post("/healing/path-to-stable/execute")
async def healing_path_to_stable_execute(req: ExecutePathRequest,
                                         user: dict = Depends(get_current_user)):
    """iter 45 — fire the planner's sequence (admin-only).

    For each step in the plan, calls healing_engine.execute_action with
    triggered_by='path_to_stable'. Skips actions in cooldown or
    exhaustion — these are recorded in the response so the operator can
    see why a step was skipped. If `dry_run=True`, returns the plan
    without executing anything.
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    plan = healing_engine.plan_path_to_stable(req.node, max_steps=req.max_steps)
    if not plan.get("applicable"):
        return {"executed": [], "plan": plan}
    if req.dry_run:
        return {"executed": [], "plan": plan, "dry_run": True}
    executed: List[Dict[str, Any]] = []
    for step in plan.get("steps", []):
        aid = step["action"]
        if healing_engine._is_action_exhausted(aid):
            executed.append({"step": step["step"], "action": aid, "fired": False, "reason": "exhausted_or_cooldown"})
            continue
        try:
            result = healing_engine.execute_action(
                action_id=aid,
                triggered_by="path_to_stable",
                target_node_override=req.node,
                reason=f"path-to-stable step {step['step']} → Δd²={step['delta_d2']}",
            )
            executed.append({"step": step["step"], "action": aid, "fired": True,
                             "sri_delta": result.get("sri_delta")})
        except Exception as e:
            executed.append({"step": step["step"], "action": aid, "fired": False, "reason": str(e)})
    return {"executed": executed, "plan": plan, "dry_run": False}


@api_router.get("/healing/resilience-debt")
async def get_resilience_debt():
    """Cumulative resilience debt: E(t) = ∫₀ᵗ Φ(t) dt (Unified-View paper).

    Reports the time-integrated stability potential and the cost-equivalent
    Cost ∝ 1/SRI. Useful for showing the dollar value of healing actions.
    """
    return resilience_debt.snapshot()


@api_router.get("/healing/resilience-debt/history")
async def get_resilience_debt_history(limit: int = 240):
    """iter 43 — Phase 1 of the Unified Model. Per-sample history of
    (t, Φ, E, cost, sri) for plotting the D(t) integral curve."""
    return resilience_debt.history(limit=limit)


class FaultPropagationRequest(BaseModel):
    source: str
    fault_strength: float = 1.0
    steps: int = 30
    dt: float = 0.5
    granularity: str = "service"  # 'service' | 'component' | 'endpoint'


class AutoDampenWaveRequest(BaseModel):
    source: str
    fault_strength: float = 1.0
    steps: int = 30
    dt: float = 0.5
    granularity: str = "service"  # 'service' | 'component' | 'endpoint'
    critical_arrival_threshold: float = 0.30
    auto_execute: bool = False


@api_router.post("/healing/fault-propagation")
async def simulate_fault_propagation(req: FaultPropagationRequest):
    """Simulate Laplacian fault propagation from a source node.

    Returns a time-series `timeline[t] = {x: {node: fault_intensity}}` showing
    how a fault at `source` diffuses through the topology, plus per-node
    `peak_fault` and `first_arrival_t`.
    """
    if req.granularity not in ("service", "component", "endpoint"):
        raise HTTPException(status_code=400, detail="granularity must be 'service', 'component', or 'endpoint'")
    if req.steps < 1 or req.steps > 200:
        raise HTTPException(status_code=400, detail="steps must be between 1 and 200")
    if not (0.0 < req.fault_strength <= 1.0):
        raise HTTPException(status_code=400, detail="fault_strength must be in (0, 1]")
    try:
        return healing_engine.simulate_fault_propagation(
            source=req.source,
            fault_strength=req.fault_strength,
            steps=req.steps,
            dt=req.dt,
            granularity=req.granularity,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.post("/healing/auto-dampen-wave")
async def auto_dampen_wave(req: AutoDampenWaveRequest):
    """Auto-compute a dampening action that arrests a traveling fault wave.

    Returns BEFORE/AFTER simulated timelines, the recommended healing action,
    the cut-edge that absorbs the wave, and (if `auto_execute=true`) the
    real execution result. The frontend uses this for the "Auto-Dampen"
    button and Auto-Arrest mode.
    """
    if req.granularity not in ("service", "component", "endpoint"):
        raise HTTPException(status_code=400, detail="granularity must be 'service', 'component', or 'endpoint'")
    if req.steps < 1 or req.steps > 200:
        raise HTTPException(status_code=400, detail="steps must be between 1 and 200")
    if not (0.0 < req.fault_strength <= 1.0):
        raise HTTPException(status_code=400, detail="fault_strength must be in (0, 1]")
    if not (0.0 < req.critical_arrival_threshold < 1.0):
        raise HTTPException(status_code=400, detail="critical_arrival_threshold must be in (0,1)")
    try:
        return healing_engine.auto_dampen_wave(
            source=req.source,
            fault_strength=req.fault_strength,
            steps=req.steps,
            dt=req.dt,
            granularity=req.granularity,
            critical_arrival_threshold=req.critical_arrival_threshold,
            auto_execute=req.auto_execute,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.get("/metrics/correlation")
async def get_sri_conversion_correlation(window_seconds: int = 300):
    """Time-aligned SRI ↔ Conversion correlation series.

    Shows whether infra resilience improvements track with conversion-rate
    improvements (the central thesis of the SRI/Unified-View papers).
    Includes annotations for every healing action so the UI can mark
    "heal at t=42s → SRI 0.62→0.87 → conversion bumped" on the chart.
    """
    if window_seconds < 30 or window_seconds > 3600:
        raise HTTPException(status_code=400, detail="window_seconds must be between 30 and 3600")
    return correlation_tracker.snapshot(window_seconds=window_seconds)


@api_router.get("/healing/active-propagations")
async def get_active_propagations():
    """Currently-detected real failure propagations (NOT chaos-injected).

    The AutoPropagationDetector continuously scans for stressed services
    and pre-computes how a fault originating there would diffuse — so the
    UI can show predictive failure paths before they actually cascade.
    """
    return auto_propagation_detector.snapshot()


class RumBeacon(BaseModel):
    """Real User Monitoring beacon — sent by the browser to feed Frontend
    metrics into the SRI engine. Treated as a first-class node in the topology."""
    session_id: Optional[str] = None
    page: Optional[str] = None
    page_load_ms: Optional[float] = None        # navigation timing
    first_contentful_paint_ms: Optional[float] = None
    largest_contentful_paint_ms: Optional[float] = None
    long_tasks_count: Optional[int] = 0          # > 50ms blocking tasks
    api_calls: Optional[List[Dict[str, Any]]] = None  # [{path,duration_ms,status,error}]
    js_errors: Optional[List[Dict[str, Any]]] = None  # [{message,source,line}]


_RUM_LAST_RECEIVED: Dict[str, float] = {}
_RUM_LOCK = Lock()

def _rum_rate_limit_ok(key: str, min_gap_sec: float = 1.0) -> bool:
    """Per-session/per-IP rate limit for RUM beacons. Default 1 beacon / sec.
    Returns True if accepted, False if dropped."""
    now = time.time()
    with _RUM_LOCK:
        last = _RUM_LAST_RECEIVED.get(key, 0)
        if now - last < min_gap_sec:
            return False
        _RUM_LAST_RECEIVED[key] = now
        # Garbage-collect stale entries
        if len(_RUM_LAST_RECEIVED) > 5000:
            cutoff = now - 300
            for k in [k for k, v in _RUM_LAST_RECEIVED.items() if v < cutoff]:
                _RUM_LAST_RECEIVED.pop(k, None)
    return True


@api_router.post("/rum/beacon")
async def ingest_rum_beacon(beacon: RumBeacon, request: Request):
    """Ingest browser RUM signals → record into the metrics aggregator under
    `Frontend` so it participates fully in SRI computation and topology FEA.

    Rate-limited to 1 beacon per second per session_id (or per client IP if
    no session_id is provided)."""
    rl_key = beacon.session_id or (request.client.host if request.client else "anon")
    if not _rum_rate_limit_ok(rl_key):
        return {"ok": True, "rate_limited": True, "key": rl_key[:32]}
    # Record page-load as a synthetic "request" on the Frontend node
    if beacon.page_load_ms and beacon.page_load_ms > 0:
        # Convert ms→s and store; use 8s as upper sanity bound to ignore stale beacons
        latency_s = min(8.0, beacon.page_load_ms / 1000.0)
        # Page-load itself rarely fails; only report failed if explicit JS error count > 0
        is_error = bool(beacon.js_errors and len(beacon.js_errors) > 0)
        metrics_aggregator.record("Frontend", latency_s, is_error)

    # Each browser-side API call also contributes (duplicated weight is fine —
    # if the user's browser felt 800ms but server logged 200ms, the user's
    # experience drives SRI down, which is the intent).
    for call in (beacon.api_calls or []):
        try:
            dur_ms = float(call.get("duration_ms") or 0)
            if dur_ms <= 0:
                continue
            err = bool(call.get("error")) or (call.get("status") and int(call.get("status", 0)) >= 400)
            metrics_aggregator.record("Frontend", min(8.0, dur_ms / 1000.0), err)
        except Exception:
            continue

    # JS error count without timing → treat as zero-latency error pulses
    extra_errs = max(0, (len(beacon.js_errors) if beacon.js_errors else 0) - 1)
    for _ in range(min(extra_errs, 5)):
        metrics_aggregator.record("Frontend", 0.05, True)

    # Long tasks (main thread blocking) → small latency penalty
    long_tasks = beacon.long_tasks_count or 0
    if long_tasks > 0:
        metrics_aggregator.record("Frontend", min(0.5, 0.05 * long_tasks), False)

    return {
        "ok": True,
        "frontend_metrics_now": metrics_aggregator.get_node_metrics("Frontend"),
        "received": {
            "page_load_ms": beacon.page_load_ms,
            "api_calls": len(beacon.api_calls or []),
            "js_errors": len(beacon.js_errors or []),
            "long_tasks": long_tasks,
        },
    }


@api_router.get("/cx/metrics")
async def get_cx_metrics(window_seconds: int = 300):
    """Customer-experience metrics time series with healing annotations
    and before/after deltas. Exposes what the END USER feels, not infra
    abstractions."""
    if window_seconds < 30 or window_seconds > 3600:
        raise HTTPException(status_code=400, detail="window_seconds must be between 30 and 3600")
    return cx_tracker.snapshot(window_seconds=window_seconds)


@api_router.post("/cx/synthetic-user/run")
async def run_synthetic_user_journey():
    """Execute a real end-user journey against the portal and report per-step
    latency, success, and errors as the user would see them.

    Journey: landing page_view → /products → /products/:id → (optional
    /cart/add) → /checkout/preview. We use in-process calls so we measure
    the same code path a real request would hit.
    """
    from httpx import AsyncClient, ASGITransport
    steps = []
    journey_start = time.time()
    errors_seen = 0

    async def step(name: str, method: str, path: str, **kwargs):
        nonlocal errors_seen
        started = time.perf_counter()
        status = 0
        error_msg = None
        body_preview = None
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://internal") as client:
                resp = await client.request(method, path, **kwargs)
                status = resp.status_code
                if status >= 400:
                    errors_seen += 1
                    error_msg = resp.text[:200]
                else:
                    try:
                        body_preview = resp.json()
                        if isinstance(body_preview, list):
                            body_preview = f"[{len(body_preview)} items]"
                        elif isinstance(body_preview, dict):
                            keys = list(body_preview.keys())[:4]
                            body_preview = f"{{{', '.join(keys)}{'...' if len(body_preview) > 4 else ''}}}"
                    except Exception:
                        body_preview = None
        except Exception as e:
            error_msg = str(e)[:200]
            errors_seen += 1
        elapsed_ms = (time.perf_counter() - started) * 1000
        steps.append({
            "name": name,
            "method": method,
            "path": path,
            "status_code": status,
            "latency_ms": round(elapsed_ms, 1),
            "perceived_speed": CustomerExperienceTracker.perceived_speed(elapsed_ms),
            "success": 200 <= status < 400,
            "error": error_msg,
            "body_preview": body_preview,
        })
        return status, body_preview

    # 1. Landing: fetch products list
    await step("Landing — browse products", "GET", "/api/products")

    # 2. View a product detail page
    try:
        first = await db.products.find_one({}, {"_id": 1})
        if first:
            await step("View product", "GET", f"/api/products/{str(first['_id'])}")
    except Exception as e:
        steps.append({"name": "View product", "error": str(e)[:200], "success": False, "latency_ms": 0, "perceived_speed": 0})

    # 3. Browse a category
    try:
        cats = await db.products.distinct("category")
        if cats:
            await step(f"Filter: {cats[0]}", "GET", f"/api/products?category={cats[0]}")
    except Exception as e:
        logger.debug(f"synth user filter step: {e}")

    # 4. Checkout preview (anonymous — may 401, counts as error shown to user)
    await step("Checkout preview (anon)", "GET", "/api/orders")

    total_ms = (time.time() - journey_start) * 1000
    total_steps = len(steps)
    successful = sum(1 for s in steps if s.get("success"))
    avg_latency = sum(s.get("latency_ms", 0) for s in steps) / max(total_steps, 1)
    avg_perceived = sum(s.get("perceived_speed", 0) for s in steps) / max(total_steps, 1)

    # Overall verdict
    if avg_perceived >= 85 and errors_seen == 0:
        verdict = "delightful"
        verdict_color = "#00FF9D"
    elif avg_perceived >= 60 and errors_seen <= 1:
        verdict = "acceptable"
        verdict_color = "#FFCC00"
    elif avg_perceived >= 30:
        verdict = "frustrating"
        verdict_color = "#FF9500"
    else:
        verdict = "broken"
        verdict_color = "#FF3B30"

    journey = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_ms": round(total_ms, 1),
        "total_steps": total_steps,
        "successful_steps": successful,
        "errors_seen": errors_seen,
        "avg_latency_ms": round(avg_latency, 1),
        "avg_perceived_speed": round(avg_perceived, 1),
        "verdict": verdict,
        "verdict_color": verdict_color,
        "sri_at_run": round(compute_sri_from_metrics(metrics_aggregator.get_all_metrics())["sri"], 4),
        "steps": steps,
    }
    cx_tracker.add_journey(journey)
    return journey





class AutoPropagationConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    autonomous_heal: Optional[bool] = None
    interval_sec: Optional[int] = None
    threshold: Optional[float] = None


@api_router.post("/healing/auto-propagation/config")
async def set_auto_propagation_config(req: AutoPropagationConfigRequest):
    """Enable/disable the auto-propagation detector and its autonomous healing."""
    return auto_propagation_detector.set_config(
        enabled=req.enabled,
        autonomous_heal=req.autonomous_heal,
        interval_sec=req.interval_sec,
        threshold=req.threshold,
    )


class StressedNodeIn(BaseModel):
    node: str
    pressure: float = 0.0
    yield_exceeded: bool = False


class OptimizeSequenceRequest(BaseModel):
    stressed_nodes: List[StressedNodeIn]
    source: Optional[str] = None
    granularity: str = "service"


@api_router.post("/healing/optimize-sequence")
async def optimize_healing_sequence(req: OptimizeSequenceRequest):
    """Compute the optimal ordering of healing actions for a list of stressed nodes.

    Returns the ordered sequence, expected cumulative SRI gain, and skipped
    duplicates. Used by the UI's "Optimized Plan" panel and by the autonomous
    healing loop along propagation paths.
    """
    if req.granularity not in ("service", "component"):
        raise HTTPException(status_code=400, detail="granularity must be 'service' or 'component'")
    return sequence_optimizer.optimize(
        stressed_nodes=[s.model_dump() for s in req.stressed_nodes],
        source=req.source,
        granularity=req.granularity,
    )


class ExecuteSequenceRequest(BaseModel):
    sequence: List[Dict[str, Any]]   # output of /healing/optimize-sequence "sequence"
    delay_ms: int = 800              # gap between actions to let SRI settle


@api_router.post("/healing/execute-sequence")
async def execute_healing_sequence(req: ExecuteSequenceRequest):
    """Execute a (typically optimizer-produced) ordered list of healing actions
    with a small delay between each to let SRI settle and effectiveness be
    recorded."""
    if not req.sequence:
        raise HTTPException(status_code=400, detail="sequence must be non-empty")
    if req.delay_ms < 0 or req.delay_ms > 5000:
        raise HTTPException(status_code=400, detail="delay_ms must be in [0,5000]")

    results = []
    for step in req.sequence:
        action_id = step.get("action_id")
        target = step.get("target_node")
        if not action_id or not target:
            results.append({"step": step, "skipped": True, "reason": "missing action_id/target_node"})
            continue
        action = healing_engine.actions.get(action_id)
        if action is None:
            results.append({"step": step, "skipped": True, "reason": "unknown action"})
            continue
        if not action.can_execute():
            results.append({
                "step": step,
                "skipped": True,
                "reason": "cooldown",
                "cooldown_remaining_seconds": round(action.cooldown_remaining(), 1),
            })
            continue
        try:
            r = healing_engine.execute_action(
                action_id=action_id,
                triggered_by="optimized_sequence",
                target_node_override=target,
            )
            results.append({
                "step": step,
                "executed": True,
                "success": r.get("success"),
                "sri_before": r.get("record", {}).get("sri_before"),
                "sri_after": r.get("record", {}).get("sri_after"),
                "sri_delta": r.get("record", {}).get("sri_delta"),
            })
        except Exception as e:
            results.append({"step": step, "executed": False, "error": str(e)})
        if req.delay_ms > 0:
            await asyncio.sleep(req.delay_ms / 1000.0)

    executed = [r for r in results if r.get("executed")]
    cumulative_sri_delta = sum(r.get("sri_delta") or 0 for r in executed)
    return {
        "results": results,
        "executed_count": len(executed),
        "cumulative_sri_delta": round(cumulative_sri_delta, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api_router.get("/healing/recommendations")
async def get_healing_recommendations():
    """Get recommended healing actions with recovery path and correction factors"""
    node_metrics = metrics_aggregator.get_all_metrics()
    sri_data = compute_sri_from_metrics(node_metrics)
    golden = metrics_aggregator.get_golden_signals()
    rca = healing_engine.perform_rca(node_metrics, sri_data)
    return {
        "current_sri": round(sri_data["sri"], 4),
        "golden_signals": golden,
        "signal_contributions": sri_data.get("signal_contributions", {}),
        "recommendations": healing_engine.get_recommendations(node_metrics, sri_data["sri"]),
        "recovery_path": _build_recovery_path(node_metrics, sri_data["sri"]),
        "correction_history": metrics_aggregator.correction_history[-20:],
        "rca": rca
    }


def _build_recovery_path(node_metrics: Dict, current_sri: float) -> list:
    """Build optimal recovery path showing step-by-step SRI improvement"""
    path = []
    running_sri = current_sri
    executed_set = set()

    for _ in range(len(healing_engine.actions)):
        best = None
        best_impact = 0

        for action_id, action in healing_engine.actions.items():
            if action_id in executed_set:
                continue
            if not healing_engine._should_trigger(action_id, node_metrics):
                continue
            if action.sri_impact > best_impact:
                best = action
                best_impact = action.sri_impact

        if not best:
            break

        new_sri = min(running_sri + best.sri_impact, 1.0)
        path.append({
            "step": len(path) + 1,
            "action_id": best.action_id,
            "action_name": best.name,
            "target_node": best.target_node,
            "sri_before": round(running_sri, 4),
            "sri_after": round(new_sri, 4),
            "improvement": round(best.sri_impact, 4),
            "cumulative_improvement": round(new_sri - current_sri, 4)
        })
        running_sri = new_sri
        executed_set.add(best.action_id)

    return path


@api_router.get("/metrics/grafana-url")
async def get_grafana_url():
    """Return Grafana dashboard URL"""
    return {
        "grafana_url": "/api/grafana/",
        "internal_port": 3002,
        "dashboards": [
            {"name": "Spectral Resilience", "uid": "spectral-resilience"}
        ]
    }

# ==================== GRAFANA PROXY ====================

GRAFANA_URL = "http://localhost:3002"

@api_router.get("/grafana")
async def grafana_redirect():
    """Redirect to Grafana dashboard via proxy"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Grafana - FreshCart Observability</title>
        <style>
            body { margin: 0; padding: 0; background: #0A0A0A; }
            .header { 
                background: #121212; 
                padding: 12px 24px; 
                display: flex; 
                align-items: center; 
                justify-content: space-between;
                border-bottom: 1px solid #262626;
            }
            .header h1 { 
                color: #F5F5F5; 
                font-family: 'Outfit', sans-serif; 
                font-size: 18px; 
                margin: 0;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .header a { 
                color: #8A8A8E; 
                text-decoration: none; 
                font-size: 14px;
            }
            .header a:hover { color: #F5F5F5; }
            iframe { 
                width: 100%; 
                height: calc(100vh - 50px); 
                border: none; 
            }
            .status { 
                display: inline-block;
                width: 8px;
                height: 8px;
                background: #00FF9D;
                border-radius: 50%;
                animation: pulse 2s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1><span class="status"></span> Grafana - FreshCart Observability</h1>
            <a href="/dashboard">&larr; Back to Dashboard</a>
        </div>
        <iframe src="/api/grafana/d/spectral-resilience?orgId=1&kiosk&refresh=5s" allowfullscreen></iframe>
    </body>
    </html>
    """, status_code=200)

@api_router.api_route("/grafana/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def grafana_proxy(path: str, request: Request):
    """Proxy requests to Grafana"""
    async with httpx.AsyncClient() as client:
        try:
            # Build the target URL - Grafana serves from /api/grafana/ subpath
            target_url = f"{GRAFANA_URL}/api/grafana/{path}"
            if request.url.query:
                target_url += f"?{request.url.query}"
            
            # Forward the request
            response = await client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']},
                content=await request.body() if request.method in ["POST", "PUT", "PATCH"] else None,
                timeout=30.0
            )
            
            content = response.content
            content_type = response.headers.get('content-type', '')
            
            # Inject CSS fix for Grafana HTML pages to fix layout issues through proxy
            if 'text/html' in content_type and b'grafanaBootData' in content:
                css_fix = b'<style>#reactRoot{height:100vh;position:relative;z-index:1;}.preloader,.preloader__text{display:none!important;}</style>'
                content = content.replace(b'</head>', css_fix + b'</head>')
            
            # Return the response, stripping headers that block iframe embedding
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'x-frame-options', 'content-security-policy']
            headers = {k: v for k, v in response.headers.items() if k.lower() not in excluded_headers}
            
            return Response(
                content=content,
                status_code=response.status_code,
                headers=headers,
                media_type=content_type
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Grafana service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

# ==================== ROOT ====================

@api_router.get("/")
async def root():
    return {"message": "FreshCart Observability API"}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== STARTUP ====================

@app.on_event("startup")
async def startup():
    init_influxdb()
    logger.info("Observability service starting on port %s", os.environ.get("OBS_PORT", "8002"))

    # Start auto-healing background loop
    asyncio.create_task(auto_healing_loop())
    asyncio.create_task(auto_propagation_loop())
    asyncio.create_task(aggressive_healing_loop())
    asyncio.create_task(permanent_funnel_healing_loop())
    asyncio.create_task(ladder_synth_mod.synthesis_loop())
    asyncio.create_task(phase_mod.phase_classifier_loop())
    asyncio.create_task(rum_learner_mod.rum_ladder_learner_loop())
    asyncio.create_task(action_stagnation_mod.stagnation_guard_loop())
    asyncio.create_task(econ_rel_mod.economic_reliability_loop())
    asyncio.create_task(stab_mod.stability_functional_loop())
    await rst_engine_instance.start()

@app.on_event("shutdown")
async def shutdown():
    client.close()
    if influx_client:
        influx_client.close()

# Include router and CORS
app.include_router(api_router)

# Root-level health check for Kubernetes liveness/readiness probes
@app.get("/health")
async def root_health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}



# ==================== WIRE RUNTIME (Phase 3) ====================
# Bind obs_server's now-instantiated singletons + module globals into the
# extracted modules' namespaces so class method bodies that reference them
# (e.g. `metrics_aggregator.foo()`) resolve correctly at call time.
def _wire_extracted_modules() -> None:
    import obs.trackers.core as _trackers_core
    import obs.engines.core as _engines_core
    from obs.engines import ladder_synthesizer as _ladder_synth
    from obs.engines import phase_classifier as _phase_classifier
    from obs.engines import rum_ladder_learner as _rum_learner
    from obs.engines import action_stagnation as _action_stagnation
    from obs.trackers import economic_reliability as _econ_rel
    from obs.engines import stability_functional as _stab_func
    from obs.engines import rst_engine as _rst_engine
    _names = (
        "metrics_aggregator", "sri_interpolator", "resilience_debt",
        "correlation_tracker", "auto_propagation_detector", "cx_tracker",
        "business_metrics", "attribution_engine", "alert_manager",
        "webhook_notifier", "healing_engine", "sequence_optimizer",
        "aggressive_healing", "permanent_funnel_healer", "ladder_synthesizer",
        "TOPOLOGY_SCHEMA", "PERMANENT_FIX_REGISTRY", "compute_sri_from_metrics",
        "db", "write_api", "INFLUX_BUCKET", "INFLUX_ORG", "ws_manager",
        "SRI_CRITICAL_THRESHOLD", "SRI_WARNING_THRESHOLD",
        "LATENCY_CRITICAL_THRESHOLD", "ERROR_RATE_CRITICAL_THRESHOLD",
        "phase_classifier_instance", "rum_ladder_learner_instance",
        "action_stagnation_guard",
        # iter 42 — stability functional needs phase classifier + (optional) debt accumulator
        "resilience_debt_accumulator",
    )
    _g = globals()
    for _mod in (_trackers_core, _engines_core, _ladder_synth, _phase_classifier, _rum_learner, _action_stagnation, _econ_rel, _stab_func, _rst_engine):
        for _n in _names:
            if _n in _g:
                setattr(_mod, _n, _g[_n])

_wire_extracted_modules()

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

