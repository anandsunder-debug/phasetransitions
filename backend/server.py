"""FreshCart Main App (e-commerce microservice).

Responsibilities:
  * Auth, products, cart, orders, admin user/order endpoints
  * Forward observability traffic to the Observability service (port 8002)
  * Fire-and-forget request + business events to the Observability service

Runs on port 8001 (the public ingress port). The Observability service runs
on port 8002 (in-cluster only). Both share the same MongoDB.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import logging
import secrets
import bcrypt
import jwt
import time
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from pydantic import BaseModel, EmailStr

# ==================== CONFIG ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("freshcart.main")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"

OBS_BASE = os.environ.get("OBS_SERVICE_URL", "http://localhost:8002")

# Single shared httpx client (kept alive for performance)
_obs_client: Optional[httpx.AsyncClient] = None

def get_obs_client() -> httpx.AsyncClient:
    global _obs_client
    if _obs_client is None:
        _obs_client = httpx.AsyncClient(base_url=OBS_BASE, timeout=httpx.Timeout(10.0, connect=2.0))
    return _obs_client

# ==================== FASTAPI APP ====================
app = FastAPI(title="FreshCart Main App")
api_router = APIRouter(prefix="/api")

# ==================== EVENT EMITTERS (fire-and-forget) ====================

async def _post_obs(path: str, payload: dict):
    """Best-effort HTTP POST to obs service. Swallows all errors so a
    misbehaving obs service can never block / fail the main app."""
    try:
        await get_obs_client().post(path, json=payload)
    except Exception as e:
        logger.debug(f"obs emit {path}: {e}")

def emit_request(path: str, method: str, latency: float, is_error: bool):
    asyncio.create_task(_post_obs("/api/internal/events/request", {
        "path": path, "method": method, "latency": latency, "is_error": is_error,
    }))

def emit_business(event_type: str, value: float = 0.0):
    asyncio.create_task(_post_obs("/api/internal/events/business", {
        "event_type": event_type, "value": float(value),
    }))

# ==================== METRICS MIDDLEWARE ====================

class _EventEmitMiddleware(BaseHTTPMiddleware):
    """Send every API request to obs as a request event (fire-and-forget)."""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") and not path.startswith("/ws"):
            return await call_next(request)
        start = time.time()
        is_error = False
        try:
            response = await call_next(request)
            is_error = response.status_code >= 400
            return response
        except Exception:
            is_error = True
            raise
        finally:
            # Don't loop: skip emit for paths we proxy/forward (those request
            # events get recorded by obs itself when it receives the call).
            # Also skip the obs internal endpoints.
            if "/internal/events/" not in path:
                latency = time.time() - start
                emit_request(path, request.method, latency, is_error)

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

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
            "role": user.get("role", "user"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ==================== MODELS ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int = 100
    unit: str = "kg"

class ProductResponse(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int
    unit: str

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int

class OrderCreate(BaseModel):
    delivery_address: str
    phone: str

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/register")
async def register(user_data: UserCreate, response: Response):
    email = user_data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user_data.password)
    user_doc = {
        "email": email, "password_hash": hashed,
        "name": user_data.name, "role": "user",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    await db.carts.insert_one({"user_id": user_id, "items": []})
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": email, "name": user_data.name, "role": "user"}

@api_router.post("/auth/login")
async def login(user_data: UserLogin, response: Response):
    email = user_data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=3600, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    return {"id": user_id, "email": user["email"], "name": user["name"], "role": user.get("role", "user")}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out successfully"}

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@api_router.get("/user/delivery-preferences")
async def get_delivery_preferences(user: dict = Depends(get_current_user)):
    user_doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"delivery_preferences": 1})
    prefs = user_doc.get("delivery_preferences", {}) if user_doc else {}
    return {"address": prefs.get("address", ""), "phone": prefs.get("phone", "")}

# ==================== PRODUCTS ====================

@api_router.get("/products", response_model=List[ProductResponse])
async def get_products(category: Optional[str] = None):
    query = {"category": category} if category else {}
    products = await db.products.find(query).to_list(100)
    emit_business("page_view")
    return [{"id": str(p["_id"]), **{k: p[k] for k in ["name","description","price","category","image_url","stock","unit"]}} for p in products]

@api_router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    product = await db.products.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"id": str(product["_id"]), **{k: product[k] for k in ["name","description","price","category","image_url","stock","unit"]}}

@api_router.get("/categories")
async def get_categories():
    categories = await db.products.distinct("category")
    return categories

# ==================== CART ====================

@api_router.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": user["id"]})
    if not cart:
        cart = {"user_id": user["id"], "items": []}
        await db.carts.insert_one(cart)
    items_with_details = []
    total = 0.0
    for item in cart["items"]:
        product = await db.products.find_one({"_id": ObjectId(item["product_id"])})
        if product:
            item_total = product["price"] * item["quantity"]
            items_with_details.append({
                "product_id": item["product_id"],
                "name": product["name"],
                "price": product["price"],
                "image_url": product["image_url"],
                "quantity": item["quantity"],
                "unit": product["unit"],
                "total": round(item_total, 2),
            })
            total += item_total
    return {"items": items_with_details, "total": round(total, 2), "count": len(items_with_details)}

@api_router.post("/cart/add")
async def add_to_cart(item: CartItemAdd, user: dict = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": user["id"]})
    if not cart:
        await db.carts.insert_one({"user_id": user["id"], "items": [item.model_dump()]})
    else:
        existing_item = next((i for i in cart["items"] if i["product_id"] == item.product_id), None)
        if existing_item:
            existing_item["quantity"] += item.quantity
        else:
            cart["items"].append(item.model_dump())
        await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": cart["items"]}})
    emit_business("add_to_cart")
    return {"message": "Added to cart"}

@api_router.put("/cart/update")
async def update_cart_item(item: CartItemAdd, user: dict = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": user["id"]})
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    for cart_item in cart["items"]:
        if cart_item["product_id"] == item.product_id:
            cart_item["quantity"] = item.quantity
            break
    else:
        raise HTTPException(status_code=404, detail="Item not in cart")
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": cart["items"]}})
    return {"message": "Cart updated"}

@api_router.delete("/cart/remove/{product_id}")
async def remove_from_cart(product_id: str, user: dict = Depends(get_current_user)):
    await db.carts.update_one(
        {"user_id": user["id"]},
        {"$pull": {"items": {"product_id": product_id}}}
    )
    return {"message": "Removed from cart"}

@api_router.delete("/cart/clear")
async def clear_cart(user: dict = Depends(get_current_user)):
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": []}})
    return {"message": "Cart cleared"}

# ==================== ORDERS ====================

@api_router.post("/orders")
async def create_order(order_data: OrderCreate, user: dict = Depends(get_current_user)):
    cart = await db.carts.find_one({"user_id": user["id"]})
    if not cart or not cart.get("items"):
        raise HTTPException(status_code=400, detail="Cart is empty")
    product_ids = [ObjectId(item["product_id"]) for item in cart["items"]]
    products = await db.products.find({"_id": {"$in": product_ids}}).to_list(100)
    products_map = {str(p["_id"]): p for p in products}
    order_items = []
    total = 0.0
    for item in cart["items"]:
        product = products_map.get(item["product_id"])
        if product:
            order_items.append({
                "product_id": item["product_id"],
                "name": product["name"],
                "price": product["price"],
                "quantity": item["quantity"],
                "unit": product["unit"],
            })
            total += product["price"] * item["quantity"]
    order_doc = {
        "user_id": user["id"], "items": order_items,
        "total": round(total, 2),
        "delivery_address": order_data.delivery_address,
        "phone": order_data.phone,
        "status": "pending", "payment_status": "mock_paid",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.orders.insert_one(order_doc)
    await db.carts.update_one({"user_id": user["id"]}, {"$set": {"items": []}})
    emit_business("checkout_start")
    emit_business("order_complete", total)
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$set": {"delivery_preferences": {"address": order_data.delivery_address, "phone": order_data.phone}}}
    )
    return {"id": str(result.inserted_id), "total": total, "status": "pending"}

@api_router.post("/orders/buy-now")
async def buy_now(product_id: str = "", quantity: int = 1, user: dict = Depends(get_current_user)):
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id required")
    product = await db.products.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    user_doc = await db.users.find_one({"_id": ObjectId(user["id"])}, {"delivery_preferences": 1})
    prefs = user_doc.get("delivery_preferences", {}) if user_doc else {}
    if not prefs.get("address") or not prefs.get("phone"):
        return {"needs_delivery_info": True, "product": {"id": str(product["_id"]), "name": product["name"], "price": product["price"]}}
    total = round(product["price"] * quantity, 2)
    order_doc = {
        "user_id": user["id"],
        "items": [{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "quantity": quantity, "unit": product["unit"]}],
        "total": total, "delivery_address": prefs["address"], "phone": prefs["phone"],
        "status": "pending", "payment_status": "mock_paid",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.orders.insert_one(order_doc)
    emit_business("checkout_start")
    emit_business("order_complete", total)
    return {"id": str(result.inserted_id), "total": total, "status": "pending"}

@api_router.get("/orders")
async def get_orders(user: dict = Depends(get_current_user)):
    orders = await db.orders.find({"user_id": user["id"]}).sort("created_at", -1).to_list(50)
    return [{
        "id": str(o["_id"]), "items": o["items"], "total": o["total"], "status": o["status"],
        "delivery_address": o["delivery_address"], "created_at": o["created_at"].isoformat(),
    } for o in orders]

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.orders.find_one({"_id": ObjectId(order_id), "user_id": user["id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "id": str(order["_id"]), "items": order["items"], "total": order["total"],
        "status": order["status"], "delivery_address": order["delivery_address"],
        "phone": order["phone"], "payment_status": order["payment_status"],
        "created_at": order["created_at"].isoformat(),
    }

# ==================== ADMIN ====================

@api_router.post("/admin/products")
async def create_product(product: ProductCreate, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    product_doc = product.model_dump()
    product_doc["created_at"] = datetime.now(timezone.utc)
    result = await db.products.insert_one(product_doc)
    return {"id": str(result.inserted_id), **product.model_dump()}

@api_router.put("/admin/orders/{order_id}/status")
async def update_order_status(order_id: str, status: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    valid = ["pending", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"]
    if status not in valid:
        raise HTTPException(status_code=400, detail="Invalid status")
    result = await db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Status updated"}

@api_router.get("/admin/orders")
async def get_all_orders(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    orders = await db.orders.find().sort("created_at", -1).to_list(100)
    return [{
        "id": str(o["_id"]), "user_id": o["user_id"], "items": o["items"], "total": o["total"],
        "status": o["status"], "delivery_address": o["delivery_address"],
        "created_at": o["created_at"].isoformat(),
    } for o in orders]

# ==================== ROOT / HEALTH ====================

@api_router.get("/")
async def root():
    return {"message": "FreshCart Grocery API (main app)", "obs_service": OBS_BASE}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/health")
async def root_health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== OBSERVABILITY PROXY ====================
# Forward observability traffic to the obs service (port 8002).
# Order matters: register the catch-all proxy AFTER the e-commerce routes.

_OBS_PROXY_PREFIXES = (
    "/metrics", "/healing", "/cx", "/rum",
    "/alerts", "/admin/webhooks", "/grafana",
    "/phase", "/economic-reliability", "/stability",
)

def _is_proxied_path(path: str) -> bool:
    # path here is the path after /api (no leading /api)
    for p in _OBS_PROXY_PREFIXES:
        if path == p.lstrip("/") or path.startswith(p.lstrip("/") + "/") or ("/" + path).startswith(p):
            return True
    return False

@api_router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def obs_proxy(full_path: str, request: Request):
    """Catch-all that forwards any /api/* not handled by the e-commerce
    routes above to the observability service. The router only reaches
    this handler when no other route matches, so it acts as a fallback."""
    if not _is_proxied_path(full_path):
        raise HTTPException(status_code=404, detail="Not found")
    target = f"/api/{full_path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
    try:
        resp = await get_obs_client().request(
            method=request.method,
            url=target,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Observability service unreachable: {e}")
    # Strip hop-by-hop headers
    out_headers = {k: v for k, v in resp.headers.items()
                   if k.lower() not in {"content-encoding", "transfer-encoding", "content-length", "connection"}}
    return StarletteResponse(content=resp.content, status_code=resp.status_code, headers=out_headers, media_type=resp.headers.get("content-type"))

# WebSocket proxy for /ws/alerts
@app.websocket("/ws/alerts")
async def proxy_alerts_ws(client_ws: WebSocket):
    """Bridges the frontend WS connection to obs /ws/alerts.

    Implemented as a fan-out via long-polling fallback: since `websockets`
    library is part of FastAPI stack, we open a server-side WS to obs and
    forward messages both ways.
    """
    await client_ws.accept()
    try:
        # Lazy import to avoid hard dep if obs is down
        import websockets
    except Exception:
        await client_ws.close(code=1011)
        return

    obs_ws_url = OBS_BASE.replace("http://", "ws://").replace("https://", "wss://") + "/ws/alerts"
    try:
        async with websockets.connect(obs_ws_url, ping_interval=20) as upstream:
            async def c2u():
                try:
                    while True:
                        msg = await client_ws.receive_text()
                        await upstream.send(msg)
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            async def u2c():
                try:
                    async for msg in upstream:
                        await client_ws.send_text(msg)
                except Exception:
                    pass

            await asyncio.gather(c2u(), u2c())
    except Exception as e:
        logger.warning(f"ws alerts proxy error: {e}")
    finally:
        try:
            await client_ws.close()
        except Exception:
            pass

# ==================== STARTUP ====================

@app.on_event("startup")
async def startup():
    # Indexes (idempotent)
    await db.users.create_index("email", unique=True)
    await db.products.create_index("category")
    await db.orders.create_index("user_id")
    await db.carts.create_index("user_id", unique=True)

    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@freshcart.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc),
        })
        logger.info(f"Admin user created: {admin_email}")

    # Seed products if empty
    product_count = await db.products.count_documents({})
    if product_count == 0:
        products = [
            {"name": "Fresh Tomatoes", "description": "Organic vine-ripened tomatoes", "price": 3.99, "category": "Vegetables", "image_url": "https://images.unsplash.com/photo-1546094096-0df4bcaaa337?w=400", "stock": 100, "unit": "kg"},
            {"name": "Organic Carrots", "description": "Sweet and crunchy organic carrots", "price": 2.49, "category": "Vegetables", "image_url": "https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?w=400", "stock": 80, "unit": "kg"},
            {"name": "Fresh Spinach", "description": "Crisp baby spinach leaves", "price": 4.29, "category": "Vegetables", "image_url": "https://images.unsplash.com/photo-1576045057995-568f588f82fb?w=400", "stock": 60, "unit": "bunch"},
            {"name": "Bell Peppers", "description": "Mixed color bell peppers", "price": 5.99, "category": "Vegetables", "image_url": "https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?w=400", "stock": 70, "unit": "kg"},
            {"name": "Fresh Apples", "description": "Crisp Fuji apples", "price": 4.49, "category": "Fruits", "image_url": "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=400", "stock": 100, "unit": "kg"},
            {"name": "Bananas", "description": "Ripe yellow bananas", "price": 1.99, "category": "Fruits", "image_url": "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=400", "stock": 120, "unit": "dozen"},
            {"name": "Fresh Oranges", "description": "Juicy navel oranges", "price": 3.99, "category": "Fruits", "image_url": "https://images.unsplash.com/photo-1547514701-42782101795e?w=400", "stock": 90, "unit": "kg"},
            {"name": "Strawberries", "description": "Sweet fresh strawberries", "price": 6.99, "category": "Fruits", "image_url": "https://images.unsplash.com/photo-1464965911861-746a04b4bca6?w=400", "stock": 50, "unit": "box"},
            {"name": "Whole Milk", "description": "Farm fresh whole milk", "price": 3.49, "category": "Dairy", "image_url": "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400", "stock": 80, "unit": "liter"},
            {"name": "Greek Yogurt", "description": "Creamy Greek yogurt", "price": 5.99, "category": "Dairy", "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400", "stock": 60, "unit": "pack"},
            {"name": "Cheddar Cheese", "description": "Aged cheddar cheese block", "price": 7.99, "category": "Dairy", "image_url": "https://images.unsplash.com/photo-1618164436241-4473940d1f5c?w=400", "stock": 40, "unit": "block"},
            {"name": "Free Range Eggs", "description": "Fresh free-range eggs", "price": 5.49, "category": "Dairy", "image_url": "https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=400", "stock": 100, "unit": "dozen"},
            {"name": "Sourdough Bread", "description": "Artisan sourdough loaf", "price": 4.99, "category": "Bakery", "image_url": "https://images.unsplash.com/photo-1549931319-a545dcf3bc73?w=400", "stock": 30, "unit": "loaf"},
            {"name": "Croissants", "description": "Buttery French croissants", "price": 3.99, "category": "Bakery", "image_url": "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=400", "stock": 40, "unit": "pack"},
            {"name": "Chicken Breast", "description": "Boneless skinless chicken breast", "price": 9.99, "category": "Meat", "image_url": "https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400", "stock": 50, "unit": "kg"},
            {"name": "Salmon Fillet", "description": "Fresh Atlantic salmon", "price": 14.99, "category": "Seafood", "image_url": "https://images.unsplash.com/photo-1499125562588-29fb8a56b5d5?w=400", "stock": 30, "unit": "kg"},
        ]
        for p in products:
            p["created_at"] = datetime.now(timezone.utc)
        await db.products.insert_many(products)
        logger.info(f"Seeded {len(products)} products")

    # Write test credentials (idempotent)
    try:
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write(f"""# Test Credentials

## Admin Account
- Email: {admin_email}
- Password: {admin_password}
- Role: admin

## Test User (Create via register)
- Email: test@example.com
- Password: test123
- Role: user

## Services
- Main App (e-commerce + proxy): port 8001 (public)
- Observability service: port 8002 (internal, OBS_SERVICE_URL={OBS_BASE})

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me

## Observability (proxied through main app)
- GET  /api/metrics/real
- GET  /api/healing
- GET  /api/healing/fea
- WS   /ws/alerts
""")
    except Exception as e:
        logger.error(f"Failed to write test credentials: {e}")

@app.on_event("shutdown")
async def shutdown():
    client.close()
    global _obs_client
    if _obs_client is not None:
        try:
            await _obs_client.aclose()
        except Exception:
            pass

# ==================== WIRE UP ====================

app.add_middleware(_EventEmitMiddleware)
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
