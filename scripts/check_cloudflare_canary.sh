#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://api-cf-test.aivison.it.com}"
WEB_ORIGIN="${WEB_ORIGIN:-https://web-cf-test.aivison.it.com}"
WEB_URL="${WEB_URL:-https://web-cf-test.aivison.it.com}"
CLOUD_WEB_URL="${CLOUD_WEB_URL:-http://100.107.220.127:8000}"

curl_timing() {
  local label="$1"
  local url="$2"
  curl -sS -o /dev/null \
    -w "${label} http=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" \
    --max-time 12 \
    "$url"
}

echo "== health =="
curl_timing "cloud-web-api" "${CLOUD_WEB_URL}/api/health"
curl_timing "api-cf-test" "${API_URL}/api/health"
curl_timing "web-cf-test" "${WEB_URL}/"

echo "== cors preflight =="
curl -sS -o /dev/null \
  -w "preflight http=%{http_code} total=%{time_total}\n" \
  --max-time 12 \
  -X OPTIONS \
  -H "Origin: ${WEB_ORIGIN}" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  "${API_URL}/api/health"
