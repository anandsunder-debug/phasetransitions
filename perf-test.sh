
#!/usr/bin/env bash
# =============================================================================
# FreshCart — Full API + Customer-Experience Performance Test
#
# Six end-to-end CX journeys (every step fires RUM beacon + business event):
#   Journey A  Landing → Category Browse → Product Detail
#   Journey B  Browse → Add-to-Cart → View Cart → Update → Checkout
#   Journey C  Buy-Now (one-click purchase)
#   Journey D  Multi-Product Cart → Checkout
#   Journey E  Order History → Reorder
#   Journey F  Guest Browse → Register → First Purchase
#
# Load phases:
#   Phase 1 Warm-up    1 worker   1 000 ms  10 s
#   Phase 2 Ramp-up    3 workers    300 ms  15 s
#   Phase 3 Peak       N workers     50 ms  20 s
#   Phase 4 Sustained  N/2 workers  100 ms  <sustain-s>
#   Phase 5 Cool-down  1 worker   1 000 ms  10 s
#
# Usage:
#   ./perf-test.sh [--base-url URL] [--peak-tps N] [--sustain-s N]
#                  [--no-admin] [--report FILE]
#
# Requirements: curl  (jq bundled as ./jq.exe)
# =============================================================================
set -euo pipefail

BASE_URL="http://localhost:8001"
PEAK_TPS=10
SUSTAIN_S=30
RUN_ADMIN=1
REPORT_FILE=""
ADMIN_EMAIL="admin@freshcart.com"
ADMIN_PASSWORD="admin123"
UNIQUE="$(date +%s)"
TEST_EMAIL="cx_perf_${UNIQUE}@freshcart.test"
TEST_PASSWORD="CXPerf#Pass1"

while [[ $# -gt 0 ]]; do
	case "$1" in
		--base-url)  BASE_URL="$2";    shift 2 ;;
		--peak-tps)  PEAK_TPS="$2";    shift 2 ;;
		--sustain-s) SUSTAIN_S="$2";   shift 2 ;;
		--no-admin)  RUN_ADMIN=0;      shift   ;;
		--report)    REPORT_FILE="$2"; shift 2 ;;
		*) echo "Unknown arg: $1"; exit 1 ;;
	esac
done

# ── Resolve jq ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v jq >/dev/null 2>&1; then
	JQ="jq"
elif [[ -x "$SCRIPT_DIR/jq.exe" ]]; then
	JQ="$SCRIPT_DIR/jq.exe"
else
	echo "jq not found. Place jq.exe in the repo root or install jq." >&2
	exit 1
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

TOTAL=0; PASSED=0; FAILED=0
TIMINGS_DIR="$(mktemp -d /tmp/perf_timings_XXXXXX)"
COOKIE_ADMIN="$(mktemp /tmp/cjar_admin_XXXXXX)"
COOKIE_USER="$(mktemp /tmp/cjar_user_XXXXXX)"
PRODUCT_ID=""; PRODUCT_ID2=""; PRODUCT_ID3=""; ORDER_ID=""
trap 'rm -rf "$TIMINGS_DIR" "$COOKIE_ADMIN" "$COOKIE_USER"' EXIT

section()      { echo -e "\n${BOLD}${CYAN}━━━  $1  ━━━${RESET}"; }
phase_banner() { echo -e "\n${BOLD}${BLUE}▶▶▶  LOAD PHASE $1: $2  ◀◀◀${RESET}"; }
ms_now()       { date +%s%3N; }

_body() {
	local method="$1" url="$2" cjar="$3"; shift 3
	curl -s -X "$method" "$url" -b "$cjar" -c "$cjar" \
		-H "Content-Type: application/json" --max-time 20 "$@" 2>/dev/null || true
}

req() {
	if (( $# < 4 )); then
		TOTAL=$((TOTAL+1))
		FAILED=$((FAILED+1))
		printf "  ${RED}✗${RESET} %-62s ${RED}%s${RESET}  %s\n" "req() argument error" "ARG" "expected: label method url cookie"
		return 0
	fi
	local label="$1" method="$2" url="$3" cjar="${4-}"
	shift 4 || true
	TOTAL=$((TOTAL+1))
	local t0; t0=$(ms_now)
	local code
	code=$(curl -s -o /dev/null -w "%{http_code}" \
		-X "$method" "$url" -b "$cjar" -c "$cjar" \
		-H "Content-Type: application/json" --max-time 20 "$@" 2>/dev/null) || code="000"
	local elapsed=$(( $(ms_now) - t0 ))
	echo "$elapsed" >> "$TIMINGS_DIR/all.ms"
	if [[ "$code" =~ ^[23] ]]; then
		PASSED=$((PASSED+1))
		printf "  ${GREEN}✓${RESET} %-62s ${GREEN}%s${RESET}  %dms\n" "$label" "$code" "$elapsed"
	else
		FAILED=$((FAILED+1))
		printf "  ${RED}✗${RESET} %-62s ${RED}%s${RESET}  %dms\n" "$label" "$code" "$elapsed"
	fi
	echo "$code"
}

silent_req() {
	local method="$1" url="$2" cjar="$3"; shift 3
	local t0; t0=$(ms_now)
	local code
	code=$(curl -s -o /dev/null -w "%{http_code}" \
		-X "$method" "$url" -b "$cjar" -c "$cjar" \
		-H "Content-Type: application/json" --max-time 20 "$@" 2>/dev/null) || code="000"
	local elapsed=$(( $(ms_now) - t0 ))
	echo "$elapsed" >> "$TIMINGS_DIR/all.ms"
	if [[ "$code" =~ ^[23] ]]; then PASSED=$((PASSED+1)); else FAILED=$((FAILED+1)); fi
	TOTAL=$((TOTAL+1))
	echo "$code"
}

rum_beacon() {
	# rum_beacon SESSION PAGE FCP LCP LONG_TASKS AXIOS JS_ERRORS CJAR
	local sess="$1" page="$2" fcp="$3" lcp="$4" lt="$5" ax="$6" je="$7" cjar="$8"
	local js_errors="[]"
	if (( je > 0 )); then
		js_errors='[{"message":"Synthetic JS error","source":"perf-test.js","line":1}]'
	fi
	silent_req POST "$BASE_URL/api/rum/beacon" "$cjar" \
		-d "{\"session_id\":\"$sess\",\"page\":\"$page\",\"page_load_ms\":$lcp,\"first_contentful_paint_ms\":$fcp,\"largest_contentful_paint_ms\":$lcp,\"long_tasks_count\":$lt,\"api_calls\":[{\"path\":\"/api/products\",\"duration_ms\":$ax,\"status\":200,\"error\":false}],\"js_errors\":$js_errors}" >/dev/null
}

biz_event() {
	local etype="$1" val="$2" cjar="$3"
	curl -s -o /dev/null -X POST "$BASE_URL/api/metrics/generate-traffic" \
		-b "$cjar" -c "$cjar" -H "Content-Type: application/json" \
		-d "{\"event_type\":\"$etype\",\"value\":$val}" --max-time 5 2>/dev/null || true
}

percentile() {
	local file="$1" pct="$2"
	[[ ! -f "$file" ]] && { echo "N/A"; return; }
	sort -n "$file" | awk -v p="$pct" \
		'BEGIN{n=0}{a[n++]=$1}END{if(n==0){print "N/A";exit}idx=int(n*p/100);if(idx>=n)idx=n-1;print a[idx]"ms"}'
}
avg_ms() {
	local file="$1"
	[[ ! -f "$file" ]] && { echo "N/A"; return; }
	awk '{s+=$1;n++}END{if(n>0)printf "%dms",s/n;else print "N/A"}' "$file"
}

# ─────────────────────────────────────────────────────────────────────────────
section "0. Connectivity"
req "GET /health"     GET "$BASE_URL/health"     "$COOKIE_USER"
req "GET /api/health" GET "$BASE_URL/api/health" "$COOKIE_USER"

if ! curl -sf --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
	echo -e "${RED}${BOLD}Backend unreachable at $BASE_URL — aborting.${RESET}"
	exit 1
fi

section "1. Auth Bootstrap"
req "POST /api/auth/register (test user)" POST "$BASE_URL/api/auth/register" "$COOKIE_USER" \
	-d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"CX Perf User\"}"
req "POST /api/auth/login (test user)"    POST "$BASE_URL/api/auth/login"    "$COOKIE_USER" \
	-d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}"
req "POST /api/auth/login (admin)"        POST "$BASE_URL/api/auth/login"    "$COOKIE_ADMIN" \
	-d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
req "GET  /api/auth/me (user)"            GET  "$BASE_URL/api/auth/me"        "$COOKIE_USER"
req "GET  /api/auth/me (admin)"           GET  "$BASE_URL/api/auth/me"        "$COOKIE_ADMIN"
req "GET  /api/user/delivery-preferences" GET  "$BASE_URL/api/user/delivery-preferences" "$COOKIE_USER"

PRODS_JSON="$(_body GET "$BASE_URL/api/products" "$COOKIE_USER")"
PRODUCT_ID="$(echo  "$PRODS_JSON" | $JQ -r '.[0].id // .[0]._id // empty' 2>/dev/null | head -1)"
PRODUCT_ID2="$(echo "$PRODS_JSON" | $JQ -r '.[1].id // .[1]._id // empty' 2>/dev/null | head -1)"
PRODUCT_ID3="$(echo "$PRODS_JSON" | $JQ -r '.[2].id // .[2]._id // empty' 2>/dev/null | head -1)"
[[ -z "$PRODUCT_ID" ]] && echo -e "  ${YELLOW}⚠  No products found — cart/order tests skipped${RESET}"

# ═════════════════════════════════════════════════════════════════════════════
#  CX JOURNEYS
# ═════════════════════════════════════════════════════════════════════════════
S="${UNIQUE}"

section "Journey A — Landing → Browse → Product Detail"
rum_beacon "${S}_a1" "home"           480  920 0  55 0 "$COOKIE_USER"
req "GET /api/products"    GET "$BASE_URL/api/products"   "$COOKIE_USER"
req "GET /api/categories"  GET "$BASE_URL/api/categories" "$COOKIE_USER"
rum_beacon "${S}_a2" "products"       390  760 0  70 0 "$COOKIE_USER"
if [[ -n "$PRODUCT_ID" ]]; then
	req "GET /api/products/:id (prefetch)" GET "$BASE_URL/api/products/$PRODUCT_ID"  "$COOKIE_USER"
	rum_beacon "${S}_a3" "product_detail" 510 1050 1 120 0 "$COOKIE_USER"
fi
[[ -n "$PRODUCT_ID2" ]] && req "GET /api/products/:id2" GET "$BASE_URL/api/products/$PRODUCT_ID2" "$COOKIE_USER"
[[ -n "$PRODUCT_ID3" ]] && req "GET /api/products/:id3" GET "$BASE_URL/api/products/$PRODUCT_ID3" "$COOKIE_USER"

section "Journey B — Browse → Cart → Checkout"
if [[ -n "$PRODUCT_ID" ]]; then
	rum_beacon "${S}_b1" "products"      360  710 0  60 0 "$COOKIE_USER"
	req "GET /api/products (browse)"  GET "$BASE_URL/api/products" "$COOKIE_USER"
	rum_beacon "${S}_b2" "product_detail" 440 880 0  95 0 "$COOKIE_USER"
	req "POST /api/cart/add (qty 2)"  POST "$BASE_URL/api/cart/add" "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":2}"
	rum_beacon "${S}_b3" "cart"          400  800 0  80 0 "$COOKIE_USER"
	req "GET  /api/cart (view)"       GET  "$BASE_URL/api/cart"       "$COOKIE_USER"
	req "PUT  /api/cart/update (qty 1)" PUT "$BASE_URL/api/cart/update" "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
	rum_beacon "${S}_b4" "checkout"      600 1200 1 150 0 "$COOKIE_USER"
	ORDER_RESP="$(_body POST "$BASE_URL/api/orders" "$COOKIE_USER" \
		-d '{"delivery_address":"42 Test Street, Bench City","phone":"555-0101"}')"
	ORDER_ID="$(echo "$ORDER_RESP" | $JQ -r '.id // ._id // empty' 2>/dev/null | head -1)"
	req "POST /api/orders (checkout)" POST "$BASE_URL/api/orders" "$COOKIE_USER" \
		-d '{"delivery_address":"42 Test Street, Bench City","phone":"555-0101"}' >/dev/null
	rum_beacon "${S}_b5" "order_confirm" 550 1100 0 130 0 "$COOKIE_USER"
fi

section "Journey C — Buy-Now (one-click)"
if [[ -n "$PRODUCT_ID" ]]; then
	rum_beacon "${S}_c1" "product_detail" 430  850 0  90 0 "$COOKIE_USER"
		req "POST /api/orders/buy-now" POST "$BASE_URL/api/orders/buy-now?product_id=$PRODUCT_ID&quantity=1" "$COOKIE_USER"
	rum_beacon "${S}_c2" "order_confirm"  520 1050 0 120 0 "$COOKIE_USER"
fi

section "Journey D — Multi-Product Cart → Checkout"
if [[ -n "$PRODUCT_ID" ]]; then
	rum_beacon "${S}_d1" "home"           440  870 0  60 0 "$COOKIE_USER"
	req "POST /api/cart/add (D-item1)" POST "$BASE_URL/api/cart/add" "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
	[[ -n "$PRODUCT_ID2" ]] && req "POST /api/cart/add (D-item2)" POST "$BASE_URL/api/cart/add" "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID2\",\"quantity\":2}"
	[[ -n "$PRODUCT_ID3" ]] && req "POST /api/cart/add (D-item3)" POST "$BASE_URL/api/cart/add" "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID3\",\"quantity\":1}"
	rum_beacon "${S}_d2" "cart"           380  750 0  75 0 "$COOKIE_USER"
	req "GET  /api/cart (D-multi)"     GET  "$BASE_URL/api/cart" "$COOKIE_USER"
	rum_beacon "${S}_d3" "checkout"       650 1300 2 170 0 "$COOKIE_USER"
	req "POST /api/orders (D-multi)"   POST "$BASE_URL/api/orders" "$COOKIE_USER" \
		-d '{"delivery_address":"7 Multi Ave, Load Town","phone":"555-0103"}'
	rum_beacon "${S}_d4" "order_confirm"  570 1140 0 140 0 "$COOKIE_USER"
fi

section "Journey E — Order History → Reorder"
rum_beacon "${S}_e1" "orders"           370  730 0  65 0 "$COOKIE_USER"
req "GET /api/orders (history)"       GET "$BASE_URL/api/orders" "$COOKIE_USER"
if [[ -n "$ORDER_ID" && "$ORDER_ID" != "null" ]]; then
	req "GET /api/orders/:id (detail)"  GET "$BASE_URL/api/orders/$ORDER_ID" "$COOKIE_USER"
	rum_beacon "${S}_e2" "order_detail"  420  840 0  85 0 "$COOKIE_USER"
fi
if [[ -n "$PRODUCT_ID" ]]; then
	req "POST /api/cart/add (reorder)"    POST "$BASE_URL/api/cart/add"  "$COOKIE_USER" \
		-d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
	req "GET  /api/user/delivery-preferences (autofill)" \
		GET "$BASE_URL/api/user/delivery-preferences" "$COOKIE_USER"
	req "POST /api/orders (reorder)"      POST "$BASE_URL/api/orders" "$COOKIE_USER" \
		-d '{"delivery_address":"42 Test Street, Bench City","phone":"555-0101"}'
	rum_beacon "${S}_e3" "order_confirm"  490  980 0 105 0 "$COOKIE_USER"
fi

section "Journey F — Guest → Register → First Purchase"
GUEST_JAR="$(mktemp /tmp/cjar_guest_XXXXXX)"
GUEST_EMAIL="guest_${UNIQUE}_f@freshcart.test"
rum_beacon "${S}_f1" "home"            460  910 0  58 0 "$GUEST_JAR"
req "GET /api/products (guest)"   GET "$BASE_URL/api/products"   "$GUEST_JAR"
req "GET /api/categories (guest)" GET "$BASE_URL/api/categories" "$GUEST_JAR"
[[ -n "$PRODUCT_ID" ]] && req "GET /api/products/:id (guest)" \
	GET "$BASE_URL/api/products/$PRODUCT_ID" "$GUEST_JAR"
rum_beacon "${S}_f2" "product_detail"  500 1000 1 115 0 "$GUEST_JAR"
req "POST /api/auth/register (guest→member)" POST "$BASE_URL/api/auth/register" "$GUEST_JAR" \
	-d "{\"email\":\"$GUEST_EMAIL\",\"password\":\"GuestPass#1\",\"name\":\"New Member\"}"
rum_beacon "${S}_f3" "register"        550 1100 0 130 0 "$GUEST_JAR"
if [[ -n "$PRODUCT_ID" ]]; then
	req "POST /api/cart/add (F-first)" POST "$BASE_URL/api/cart/add" "$GUEST_JAR" \
		-d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"
	rum_beacon "${S}_f4" "checkout"      680 1360 2 180 0 "$GUEST_JAR"
	req "POST /api/orders (F-first purchase)" POST "$BASE_URL/api/orders" "$GUEST_JAR" \
		-d '{"delivery_address":"First Time Rd, New City","phone":"555-0199"}'
	rum_beacon "${S}_f5" "order_confirm" 580 1160 0 145 0 "$GUEST_JAR"
fi
rm -f "$GUEST_JAR"

# ─────────────────────────────────────────────────────────────────────────────
section "Cart — Remaining Verbs"
[[ -n "$PRODUCT_ID" ]] && req "DELETE /api/cart/remove/:id" \
	DELETE "$BASE_URL/api/cart/remove/$PRODUCT_ID" "$COOKIE_USER"
req "DELETE /api/cart/clear" DELETE "$BASE_URL/api/cart/clear" "$COOKIE_USER"

section "Admin — Products & Orders"
req "GET /api/admin/orders" GET "$BASE_URL/api/admin/orders" "$COOKIE_ADMIN"
if [[ "$RUN_ADMIN" -eq 1 ]]; then
	req "POST /api/admin/products" POST "$BASE_URL/api/admin/products" "$COOKIE_ADMIN" \
		-d '{"name":"PerfItem","description":"Perf test product","price":1.99,"category":"Bakery","image_url":"https://example.com/p.png","stock":999,"unit":"unit"}'
	ADMIN_ORDERS="$(_body GET "$BASE_URL/api/admin/orders" "$COOKIE_ADMIN")"
	ADM_OID="$(echo "$ADMIN_ORDERS" | $JQ -r '.[0].id // .[0]._id // empty' 2>/dev/null | head -1)"
	[[ -n "$ADM_OID" && "$ADM_OID" != "null" ]] && \
		req "PUT /api/admin/orders/:id/status" PUT "$BASE_URL/api/admin/orders/$ADM_OID/status" "$COOKIE_ADMIN" \
			-d '{"status":"processing"}'
fi

section "Alerts"
req "GET    /api/alerts"        GET    "$BASE_URL/api/alerts"        "$COOKIE_USER"
req "GET    /api/alerts/config" GET    "$BASE_URL/api/alerts/config" "$COOKIE_USER"
req "PUT    /api/alerts/config" PUT    "$BASE_URL/api/alerts/config" "$COOKIE_ADMIN" \
	-d '{"sri_critical":0.1,"sri_warning":0.3,"latency_critical":300,"error_rate_critical":0.15}'
req "DELETE /api/alerts"        DELETE "$BASE_URL/api/alerts"        "$COOKIE_ADMIN"

section "Metrics — All Endpoints"
req "GET /api/metrics/real"                GET  "$BASE_URL/api/metrics/real"              "$COOKIE_USER"
req "GET /api/metrics/golden-signals"      GET  "$BASE_URL/api/metrics/golden-signals"    "$COOKIE_USER"
req "GET /api/metrics/customer-experience" GET  "$BASE_URL/api/metrics/customer-experience" "$COOKIE_USER"
req "GET /api/metrics/business"            GET  "$BASE_URL/api/metrics/business"          "$COOKIE_USER"
req "GET /api/metrics/reliability"         GET  "$BASE_URL/api/metrics/reliability"       "$COOKIE_USER"
req "GET /api/metrics/attribution"         GET  "$BASE_URL/api/metrics/attribution"       "$COOKIE_USER"
req "GET /api/metrics/sri-history"         GET  "$BASE_URL/api/metrics/sri-history"       "$COOKIE_USER"
req "GET /api/metrics/history"             GET  "$BASE_URL/api/metrics/history"           "$COOKIE_USER"
req "GET /api/metrics/summary"             GET  "$BASE_URL/api/metrics/summary"           "$COOKIE_USER"
req "GET /api/metrics/transactions"        GET  "$BASE_URL/api/metrics/transactions"      "$COOKIE_USER"
req "GET /api/metrics/grafana-url"         GET  "$BASE_URL/api/metrics/grafana-url"       "$COOKIE_USER"
req "GET /api/grafana"                     GET  "$BASE_URL/api/grafana"                   "$COOKIE_USER"
req "GET /api/metrics/correlation (30s)"   GET  "$BASE_URL/api/metrics/correlation?window_seconds=30"  "$COOKIE_USER"
req "GET /api/metrics/correlation (120s)"  GET  "$BASE_URL/api/metrics/correlation?window_seconds=120" "$COOKIE_USER"
req "POST /api/metrics/simulate"           POST "$BASE_URL/api/metrics/simulate"          "$COOKIE_ADMIN" \
	-d '{"traffic_scale":1200,"latency_scale":90,"error_rate":0.12,"saturation":0.6,"failure_mode":"Latency Spike"}'
req "POST /api/metrics/generate-traffic"   POST "$BASE_URL/api/metrics/generate-traffic"  "$COOKIE_ADMIN"

section "CX & RUM — Dedicated Endpoints + Stress Beacons"
req "GET  /api/cx/metrics (30s)"      GET  "$BASE_URL/api/cx/metrics?window_seconds=30"  "$COOKIE_USER"
req "GET  /api/cx/metrics (300s)"     GET  "$BASE_URL/api/cx/metrics?window_seconds=300" "$COOKIE_USER"
req "POST /api/cx/synthetic-user/run" POST "$BASE_URL/api/cx/synthetic-user/run"         "$COOKIE_USER" -d '{}'
rum_beacon "stress_1" "checkout"       2800 5600 5 1300 2 "$COOKIE_USER"
rum_beacon "stress_2" "product_detail" 4200 8100 8 2200 4 "$COOKIE_USER"
rum_beacon "stress_3" "home"            380  760 0   55 0 "$COOKIE_USER"

section "Healing — All Read Endpoints"
req "GET /api/healing"                           GET "$BASE_URL/api/healing"                           "$COOKIE_USER"
req "GET /api/healing/status"                    GET "$BASE_URL/api/healing/status"                    "$COOKIE_USER"
req "GET /api/healing/fea?granularity=service"   GET "$BASE_URL/api/healing/fea?granularity=service"   "$COOKIE_USER"
req "GET /api/healing/fea?granularity=component" GET "$BASE_URL/api/healing/fea?granularity=component" "$COOKIE_USER"
req "GET /api/healing/fea?granularity=endpoint"  GET "$BASE_URL/api/healing/fea?granularity=endpoint"  "$COOKIE_USER"
req "GET /api/healing/rca"                       GET "$BASE_URL/api/healing/rca"                       "$COOKIE_USER"
req "GET /api/healing/trend"                     GET "$BASE_URL/api/healing/trend"                     "$COOKIE_USER"
req "GET /api/healing/resilience-debt"           GET "$BASE_URL/api/healing/resilience-debt"           "$COOKIE_USER"
req "GET /api/healing/resilience-debt/history"   GET "$BASE_URL/api/healing/resilience-debt/history"   "$COOKIE_USER"
req "GET /api/healing/adaptation"                GET "$BASE_URL/api/healing/adaptation"                "$COOKIE_USER"
req "GET /api/healing/intelligence"              GET "$BASE_URL/api/healing/intelligence"              "$COOKIE_USER"
req "GET /api/healing/recommendations"           GET "$BASE_URL/api/healing/recommendations"           "$COOKIE_USER"
req "GET /api/healing/history"                   GET "$BASE_URL/api/healing/history"                   "$COOKIE_USER"
req "GET /api/healing/topology"                  GET "$BASE_URL/api/healing/topology"                  "$COOKIE_USER"
req "GET /api/healing/topology/schema"           GET "$BASE_URL/api/healing/topology/schema"           "$COOKIE_USER"
req "GET /api/healing/path-to-stable"            GET "$BASE_URL/api/healing/path-to-stable"            "$COOKIE_USER"
req "GET /api/healing/active-propagations"       GET "$BASE_URL/api/healing/active-propagations"       "$COOKIE_USER"
req "GET /api/healing/permanent-fixes"           GET "$BASE_URL/api/healing/permanent-fixes"           "$COOKIE_USER"
req "GET /api/healing/aggressive/status"         GET "$BASE_URL/api/healing/aggressive/status"         "$COOKIE_USER"
req "GET /api/healing/aggressive/preview-ranking"GET "$BASE_URL/api/healing/aggressive/preview-ranking" "$COOKIE_USER"
req "GET /api/healing/ladder/current"            GET "$BASE_URL/api/healing/ladder/current"            "$COOKIE_USER"
req "GET /api/healing/ladder/history"            GET "$BASE_URL/api/healing/ladder/history?limit=20"   "$COOKIE_USER"
req "GET /api/healing/ladder/gain-matrix"        GET "$BASE_URL/api/healing/ladder/gain-matrix"        "$COOKIE_USER"
req "GET /api/healing/rum-sequences/top"         GET "$BASE_URL/api/healing/rum-sequences/top?limit=10" "$COOKIE_USER"
req "GET /api/healing/rum-sequences/status"      GET "$BASE_URL/api/healing/rum-sequences/status"      "$COOKIE_USER"
req "GET /api/healing/stagnation/state"          GET "$BASE_URL/api/healing/stagnation/state"          "$COOKIE_USER"
req "GET /api/healing/stagnation/events"         GET "$BASE_URL/api/healing/stagnation/events"         "$COOKIE_USER"

section "Healing — Write/Action Endpoints"
req "POST /api/healing/toggle (disable)" POST "$BASE_URL/api/healing/toggle" "$COOKIE_ADMIN" -d '{"enabled":false}'
req "POST /api/healing/toggle (enable)"  POST "$BASE_URL/api/healing/toggle" "$COOKIE_ADMIN" -d '{"enabled":true}'
for action_id in queue_drain rate_limit cache_flush connection_pool_reset circuit_breaker api_error_suppression; do
	req "POST /api/healing/trigger ($action_id)" POST "$BASE_URL/api/healing/trigger" "$COOKIE_ADMIN" \
		-d "{\"action_id\":\"$action_id\"}"
done
req "POST /api/healing/path-to-stable/execute" POST "$BASE_URL/api/healing/path-to-stable/execute" "$COOKIE_ADMIN" \
	-d '{"node":"API","max_steps":3,"dry_run":false}'
req "POST /api/healing/auto-propagation/config" POST "$BASE_URL/api/healing/auto-propagation/config" "$COOKIE_ADMIN" \
	-d '{"enabled":true,"autonomous_heal":false}'
req "POST /api/healing/permanent-fixes/toggle"  POST "$BASE_URL/api/healing/permanent-fixes/toggle" "$COOKIE_ADMIN" \
	-d '{"enabled":true}'
req "DELETE /api/healing/permanent-fixes/API/latency" \
	DELETE "$BASE_URL/api/healing/permanent-fixes/API/latency" "$COOKIE_ADMIN"

section "Fault Propagation (18 calls — 6 sources × 3 granularities)"
for src in Frontend API Cache DB Queue Backend; do
	for gran in service component endpoint; do
		req "POST /api/healing/fault-propagation ($src/$gran)" \
			POST "$BASE_URL/api/healing/fault-propagation" "$COOKIE_USER" \
			-d "{\"source\":\"$src\",\"granularity\":\"$gran\",\"steps\":5,\"fault_strength\":0.6}"
	done
done

section "Auto-Dampen Wave (3 granularities)"
for gran in service component endpoint; do
	req "POST /api/healing/auto-dampen-wave ($gran)" \
		POST "$BASE_URL/api/healing/auto-dampen-wave" "$COOKIE_ADMIN" \
		-d "{\"source\":\"API\",\"granularity\":\"$gran\",\"steps\":6,\"fault_strength\":0.7,\"critical_arrival_threshold\":0.3}"
done

section "Sequence Optimizer & Executor"
req "POST /api/healing/optimize-sequence (5)" POST "$BASE_URL/api/healing/optimize-sequence" "$COOKIE_ADMIN" \
	-d '{"stressed_nodes":[{"node":"API","pressure":0.82,"yield_exceeded":true},{"node":"DB","pressure":0.73,"yield_exceeded":true}],"source":"API","granularity":"service"}'
SEQ_RESP="$(_body POST "$BASE_URL/api/healing/optimize-sequence" "$COOKIE_ADMIN" -d '{"stressed_nodes":[{"node":"API","pressure":0.8,"yield_exceeded":true},{"node":"Queue","pressure":0.66,"yield_exceeded":false}],"source":"API","granularity":"service"}')"
SEQ="$(echo "$SEQ_RESP" | $JQ -c '.sequence // .plan // empty' 2>/dev/null | head -1)"
if [[ -n "$SEQ" && "$SEQ" != "null" ]]; then
	req "POST /api/healing/execute-sequence" POST "$BASE_URL/api/healing/execute-sequence" "$COOKIE_ADMIN" \
		-d "{\"sequence\":$SEQ,\"delay_ms\":0}"
fi

section "Aggressive Healing"
req "GET  /api/healing/aggressive/status"          GET  "$BASE_URL/api/healing/aggressive/status"           "$COOKIE_USER"
req "GET  /api/healing/aggressive/preview-ranking" GET  "$BASE_URL/api/healing/aggressive/preview-ranking"  "$COOKIE_USER"
if [[ "$RUN_ADMIN" -eq 1 ]]; then
	req "POST /api/healing/aggressive/toggle (stress)"  POST "$BASE_URL/api/healing/aggressive/toggle" "$COOKIE_ADMIN" \
		-d '{"enabled":true,"debt_rate_threshold":0.001,"min_lift_threshold":0.001}'
	req "POST /api/healing/aggressive/toggle (restore)" POST "$BASE_URL/api/healing/aggressive/toggle" "$COOKIE_ADMIN" \
		-d '{"enabled":true,"debt_rate_threshold":0.002,"min_lift_threshold":0.003}'
fi

section "Ladder Synthesizer"
req "GET  /api/healing/ladder/current"     GET  "$BASE_URL/api/healing/ladder/current"          "$COOKIE_USER"
req "GET  /api/healing/ladder/history"     GET  "$BASE_URL/api/healing/ladder/history?limit=20" "$COOKIE_USER"
req "GET  /api/healing/ladder/gain-matrix" GET  "$BASE_URL/api/healing/ladder/gain-matrix"      "$COOKIE_USER"
if [[ "$RUN_ADMIN" -eq 1 ]]; then
	req "POST /api/healing/ladder/synthesize"   POST "$BASE_URL/api/healing/ladder/synthesize" "$COOKIE_ADMIN" -d '{}'
	req "POST /api/healing/ladder/rollback"     POST "$BASE_URL/api/healing/ladder/rollback"   "$COOKIE_ADMIN" -d '{}'
	req "POST /api/healing/ladder/toggle (off)" POST "$BASE_URL/api/healing/ladder/toggle"     "$COOKIE_ADMIN" -d '{"enabled":false}'
	req "POST /api/healing/ladder/toggle (on)"  POST "$BASE_URL/api/healing/ladder/toggle"     "$COOKIE_ADMIN" -d '{"enabled":true}'
fi

section "RUM Sequences"
req "GET  /api/healing/rum-sequences/top"    GET  "$BASE_URL/api/healing/rum-sequences/top?limit=10" "$COOKIE_USER"
req "GET  /api/healing/rum-sequences/status" GET  "$BASE_URL/api/healing/rum-sequences/status"       "$COOKIE_USER"
[[ "$RUN_ADMIN" -eq 1 ]] && \
	req "POST /api/healing/rum-sequences/run-now" POST "$BASE_URL/api/healing/rum-sequences/run-now" "$COOKIE_ADMIN" -d '{}'

section "Phase / Stagnation / Economic / Stability"
req "GET /api/phase/state"                GET  "$BASE_URL/api/phase/state"                         "$COOKIE_USER"
req "GET /api/phase/history"              GET  "$BASE_URL/api/phase/history?limit=60"              "$COOKIE_USER"
req "GET /api/healing/stagnation/state"   GET  "$BASE_URL/api/healing/stagnation/state"            "$COOKIE_USER"
req "GET /api/healing/stagnation/events"  GET  "$BASE_URL/api/healing/stagnation/events"           "$COOKIE_USER"
req "GET /api/economic-reliability/state" GET  "$BASE_URL/api/economic-reliability/state"          "$COOKIE_USER"
req "GET /api/economic-reliability/trend" GET  "$BASE_URL/api/economic-reliability/trend?limit=60" "$COOKIE_USER"
req "GET /api/stability/state"            GET  "$BASE_URL/api/stability/state"                     "$COOKIE_USER"
req "GET /api/stability/trend"            GET  "$BASE_URL/api/stability/trend"                     "$COOKIE_USER"
if [[ "$RUN_ADMIN" -eq 1 ]]; then
	req "POST /api/healing/stagnation/reset"   POST "$BASE_URL/api/healing/stagnation/reset"   "$COOKIE_ADMIN" -d '{}'
	req "POST /api/healing/stagnation/restore" POST "$BASE_URL/api/healing/stagnation/restore" "$COOKIE_ADMIN" \
		-d '{"node":"API","action":"rate_limit"}'
fi

section "Admin Webhooks"
req "GET  /api/admin/webhooks/status" GET  "$BASE_URL/api/admin/webhooks/status" "$COOKIE_ADMIN"
[[ "$RUN_ADMIN" -eq 1 ]] && \
	req "POST /api/admin/webhooks/test" POST "$BASE_URL/api/admin/webhooks/test"   "$COOKIE_ADMIN" -d '{}'

section "Logout"
LJAR="$(mktemp /tmp/cjar_lo_XXXXXX)"
_body POST "$BASE_URL/api/auth/login" "$LJAR" \
	-d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" >/dev/null
req "POST /api/auth/logout" POST "$BASE_URL/api/auth/logout" "$LJAR"
rm -f "$LJAR"
_body POST "$BASE_URL/api/auth/login" "$COOKIE_USER" \
	-d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" >/dev/null

echo -e "\n${BOLD}Functional sweep done.  ${GREEN}PASS=$PASSED${RESET}  ${RED}FAIL=$FAILED${RESET}  TOTAL=$TOTAL${RESET}"

# ══════════════════════════════════════════════════════════════════════════════
#  LOAD PHASES
# ══════════════════════════════════════════════════════════════════════════════
MIX_URLS=(); MIX_METHODS=(); MIX_BODY=()
m() { MIX_URLS+=("$1"); MIX_METHODS+=("$2"); MIX_BODY+=("$3"); }

# E-commerce reads (high weight)
for _i in 1 2 3; do
	m "$BASE_URL/api/products"   GET ""
	m "$BASE_URL/api/categories" GET ""
	m "$BASE_URL/api/cart"       GET ""
	m "$BASE_URL/api/orders"     GET ""
done
[[ -n "$PRODUCT_ID" ]]  && m "$BASE_URL/api/products/$PRODUCT_ID"  GET ""
[[ -n "$PRODUCT_ID2" ]] && m "$BASE_URL/api/products/$PRODUCT_ID2" GET ""
# Observability reads
for _i in 1 2; do
	m "$BASE_URL/api/metrics/real"                    GET ""
	m "$BASE_URL/api/metrics/golden-signals"          GET ""
	m "$BASE_URL/api/metrics/reliability"             GET ""
	m "$BASE_URL/api/metrics/business"                GET ""
	m "$BASE_URL/api/metrics/customer-experience"     GET ""
	m "$BASE_URL/api/metrics/attribution"             GET ""
	m "$BASE_URL/api/metrics/correlation?window_seconds=30" GET ""
done
m "$BASE_URL/api/metrics/sri-history"               GET ""
m "$BASE_URL/api/metrics/history"                   GET ""
m "$BASE_URL/api/metrics/summary"                   GET ""
m "$BASE_URL/api/metrics/transactions"              GET ""
# Healing reads
m "$BASE_URL/api/healing"                           GET ""
m "$BASE_URL/api/healing/status"                    GET ""
m "$BASE_URL/api/healing/fea?granularity=service"   GET ""
m "$BASE_URL/api/healing/fea?granularity=component" GET ""
m "$BASE_URL/api/healing/fea?granularity=endpoint"  GET ""
m "$BASE_URL/api/healing/rca"                       GET ""
m "$BASE_URL/api/healing/trend"                     GET ""
m "$BASE_URL/api/healing/resilience-debt"           GET ""
m "$BASE_URL/api/healing/adaptation"                GET ""
m "$BASE_URL/api/healing/intelligence"              GET ""
m "$BASE_URL/api/healing/recommendations"           GET ""
m "$BASE_URL/api/healing/history"                   GET ""
m "$BASE_URL/api/healing/topology/schema"           GET ""
m "$BASE_URL/api/healing/path-to-stable"            GET ""
m "$BASE_URL/api/healing/active-propagations"       GET ""
m "$BASE_URL/api/healing/ladder/current"            GET ""
m "$BASE_URL/api/healing/ladder/gain-matrix"        GET ""
m "$BASE_URL/api/healing/rum-sequences/status"      GET ""
m "$BASE_URL/api/healing/stagnation/state"          GET ""
m "$BASE_URL/api/healing/aggressive/status"         GET ""
m "$BASE_URL/api/phase/state"                       GET ""
m "$BASE_URL/api/phase/history?limit=30"            GET ""
m "$BASE_URL/api/economic-reliability/state"        GET ""
m "$BASE_URL/api/stability/state"                   GET ""
m "$BASE_URL/api/cx/metrics?window_seconds=30"      GET ""
m "$BASE_URL/api/alerts"                            GET ""
# Write endpoints (realistic CX frequency)
m "$BASE_URL/api/rum/beacon" POST \
	'{"session_id":"load_rx","page":"products","page_load_ms":1300,"first_contentful_paint_ms":650,"largest_contentful_paint_ms":1300,"long_tasks_count":0,"api_calls":[{"path":"/api/products","duration_ms":105,"status":200,"error":false}],"js_errors":[]}'
m "$BASE_URL/api/rum/beacon" POST \
	'{"session_id":"load_ry","page":"checkout","page_load_ms":3800,"first_contentful_paint_ms":1900,"largest_contentful_paint_ms":3800,"long_tasks_count":2,"api_calls":[{"path":"/api/orders","duration_ms":750,"status":200,"error":false}],"js_errors":[]}'
m "$BASE_URL/api/cx/synthetic-user/run" POST '{}'
m "$BASE_URL/api/healing/fault-propagation" POST \
	'{"source":"API","granularity":"service","steps":3,"fault_strength":0.5}'
[[ -n "$PRODUCT_ID" ]] && \
	m "$BASE_URL/api/cart/add" POST "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"

MIX_LEN="${#MIX_URLS[@]}"

run_worker() {
	local phase_tag="$1" wjar="$2"
	local i
	for (( i=0; i<MIX_LEN; i++ )); do
		local url="${MIX_URLS[$i]}" method="${MIX_METHODS[$i]}" body="${MIX_BODY[$i]}"
		local t0; t0=$(ms_now)
		local code
		if [[ -n "$body" ]]; then
			code=$(curl -s -o /dev/null -w "%{http_code}" \
				-X "$method" "$url" -b "$wjar" -c "$wjar" \
				-H "Content-Type: application/json" -d "$body" \
				--max-time 20 2>/dev/null) || code="000"
		else
			code=$(curl -s -o /dev/null -w "%{http_code}" \
				-X "$method" "$url" -b "$wjar" -c "$wjar" \
				-H "Content-Type: application/json" \
				--max-time 20 2>/dev/null) || code="000"
		fi
		local elapsed=$(( $(ms_now) - t0 ))
		echo "$elapsed" >> "$TIMINGS_DIR/all.ms"
		echo "$elapsed" >> "$TIMINGS_DIR/phase_${phase_tag}.ms"
		if [[ "$code" =~ ^[23] ]]; then echo "P"; else echo "F"; fi \
			>> "$TIMINGS_DIR/phase_${phase_tag}_r.txt"
	done
}

run_phase() {
	local num="$1" label="$2" workers="$3" spacing_ms="$4" duration_s="$5"
	phase_banner "$num" "$label  [workers=$workers  spacing=${spacing_ms}ms  dur=${duration_s}s  urls=$MIX_LEN]"
	local pf="$TIMINGS_DIR/phase_${num}.ms"
	local rf="$TIMINGS_DIR/phase_${num}_r.txt"
	: > "$pf"; : > "$rf"
	local t_start; t_start=$(ms_now)
	local deadline=$(( t_start + duration_s * 1000 ))
	local batch=0

	while [[ $(ms_now) -lt $deadline ]]; do
		batch=$((batch+1))
		local pids=()
		for (( w=1; w<=workers; w++ )); do
			local wjar; wjar="$(mktemp /tmp/cjar_ph_XXXXXX)"
			cp "$COOKIE_USER" "$wjar"
			( run_worker "$num" "$wjar"; rm -f "$wjar" ) &
			pids+=($!)
			local sl; sl=$(awk "BEGIN{printf \"%.3f\",$spacing_ms/1000}")
			sleep "$sl" 2>/dev/null || true
		done
		for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
		printf "\r  ${DIM}[%s] batch=%d elapsed=%ds workers=%d${RESET}" \
			"$label" "$batch" "$(( ($(ms_now)-t_start)/1000 ))" "$workers"
	done
	echo ""

	local p=0 f=0
	[[ -f "$rf" ]] && p=$(grep -c "^P$" "$rf" 2>/dev/null || echo 0)
	[[ -f "$rf" ]] && f=$(grep -c "^F$" "$rf" 2>/dev/null || echo 0)
	PASSED=$((PASSED+p)); FAILED=$((FAILED+f)); TOTAL=$((TOTAL+p+f))

	local total_req=$((p+f)) actual_s tps=0
	actual_s=$(( ($(ms_now)-t_start)/1000 ))
	[[ "$actual_s" -gt 0 ]] && tps=$((total_req/actual_s))
	printf "  %-12s  ${GREEN}ok=%-6d${RESET}${RED}fail=%-5d${RESET}  req=%-7d  TPS=%-5d  " \
		"[$label]" "$p" "$f" "$total_req" "$tps"
	printf "avg=%s  p50=%s  p95=%s  p99=%s\n" \
		"$(avg_ms "$pf")" "$(percentile "$pf" 50)" "$(percentile "$pf" 95)" "$(percentile "$pf" 99)"
}

HALF_PEAK=$(( PEAK_TPS/2 < 1 ? 1 : PEAK_TPS/2 ))
run_phase 1 "Warm-up"   1           1000  10
run_phase 2 "Ramp-up"   3            300  15
run_phase 3 "Peak"      "$PEAK_TPS"   50  20
run_phase 4 "Sustained" "$HALF_PEAK" 100  "$SUSTAIN_S"
run_phase 5 "Cool-down" 1           1000  10

ALL="$TIMINGS_DIR/all.ms"
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  PERFORMANCE TEST REPORT${RESET}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
printf "  Target        : %s\n"   "$BASE_URL"
printf "  URL mix size  : %d\n"   "$MIX_LEN"
printf "  Peak workers  : %d\n"   "$PEAK_TPS"
printf "  Sustain s     : %d\n\n" "$SUSTAIN_S"
printf "  Total requests: %d\n"   "$TOTAL"
echo -e "  ${GREEN}Passed        : $PASSED${RESET}"
echo -e "  ${RED}Failed        : $FAILED${RESET}"
echo ""
echo -e "  ${BOLD}Overall Latency${RESET}"
printf "    avg  : %s\n" "$(avg_ms     "$ALL")"
printf "    p50  : %s\n" "$(percentile "$ALL" 50)"
printf "    p75  : %s\n" "$(percentile "$ALL" 75)"
printf "    p95  : %s\n" "$(percentile "$ALL" 95)"
printf "    p99  : %s\n" "$(percentile "$ALL" 99)"

if [[ -n "$REPORT_FILE" ]]; then
	$JQ -n \
		--arg url "$BASE_URL" --argjson total "$TOTAL" \
		--argjson passed "$PASSED" --argjson failed "$FAILED" \
		--arg avg "$(avg_ms "$ALL")" \
		--arg p50 "$(percentile "$ALL" 50)" \
		--arg p95 "$(percentile "$ALL" 95)" \
		--arg p99 "$(percentile "$ALL" 99)" \
		'{base_url:$url,total:$total,passed:$passed,failed:$failed,
			latency:{avg:$avg,p50:$p50,p95:$p95,p99:$p99}}' > "$REPORT_FILE"
	echo -e "\n  JSON report → ${CYAN}$REPORT_FILE${RESET}"
fi

echo ""
if   [[ "$FAILED" -eq 0 ]];               then echo -e "  ${GREEN}${BOLD}ALL TESTS PASSED${RESET}";                         exit 0
elif [[ "$FAILED" -lt $((TOTAL/10)) ]];   then echo -e "  ${YELLOW}${BOLD}MOSTLY PASSED — $FAILED failures < 10%${RESET}"; exit 1
else                                           echo -e "  ${RED}${BOLD}SIGNIFICANT FAILURES — $FAILED / $TOTAL${RESET}";   exit 1
fi

