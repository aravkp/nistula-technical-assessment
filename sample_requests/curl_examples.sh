#!/usr/bin/env bash
# Sample requests against a local instance of the webhook.
# Run `uvicorn app.main:app --reload` in another terminal first.

set -euo pipefail

URL="${URL:-http://localhost:8000/webhook/message}"

echo "=== Availability ==="
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d @sample_requests/availability.json
echo

echo "=== Pricing ==="
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d @sample_requests/pricing.json
echo

echo "=== Check-in (post-sales) ==="
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d @sample_requests/checkin.json
echo

echo "=== Special request ==="
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d @sample_requests/special_request.json
echo

echo "=== Complaint (should escalate) ==="
curl -sS -X POST "$URL" \
  -H 'Content-Type: application/json' \
  -d @sample_requests/complaint.json
echo
