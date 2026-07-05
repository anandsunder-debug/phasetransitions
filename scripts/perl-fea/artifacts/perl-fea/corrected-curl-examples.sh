#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8001"
COOKIE="${1:-cookie.txt}"

curl -s -X POST "$BASE_URL/api/orders/buy-now?product_id=<product_id>&quantity=1" -b "$COOKIE" -c "$COOKIE"

curl -s -X POST "$BASE_URL/api/rum/beacon" -b "$COOKIE" -c "$COOKIE" -H "Content-Type: application/json" -d '{"session_id":"load_rx","page":"checkout","page_load_ms":1800,"first_contentful_paint_ms":900,"largest_contentful_paint_ms":1800,"long_tasks_count":1,"api_calls":[{"path":"/api/orders","duration_ms":420,"status":200,"error":false}],"js_errors":[]}'

curl -s -X POST "$BASE_URL/api/healing/path-to-stable/execute" -b "$COOKIE" -c "$COOKIE" -H "Content-Type: application/json" -d '{"node":"API","max_steps":3,"dry_run":false}'

curl -s -X POST "$BASE_URL/api/healing/fault-propagation" -b "$COOKIE" -c "$COOKIE" -H "Content-Type: application/json" -d '{"source":"API","granularity":"service","steps":5,"fault_strength":0.6}'

curl -s -X POST "$BASE_URL/api/healing/optimize-sequence" -b "$COOKIE" -c "$COOKIE" -H "Content-Type: application/json" -d '{"stressed_nodes":[{"node":"API","pressure":0.82,"yield_exceeded":true},{"node":"DB","pressure":0.73,"yield_exceeded":true}],"source":"API","granularity":"service"}'
