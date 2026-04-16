#!/usr/bin/env bash
# run_tests.sh — build and run the full test suite + auth smoke-check in Docker.
#
# Usage:
#   bash run_tests.sh             # build image (no cache) and run all tests
#   bash run_tests.sh --no-build  # skip build, use existing cached image
#
# What this does:
#   1. Builds a clean Docker test image (Dockerfile.test).
#   2. Runs the full pytest suite in an isolated container.
#   3. Seeds the database with the standard demo users (seed.py).
#   4. Performs a quick RBAC smoke-check: logs in as every seed user and
#      verifies the /api/auth/me response contains the expected role.
set -euo pipefail

IMAGE="wildlifelens-test"
SMOKE_IMAGE="wildlifelens-smoke"
SMOKE_NET="wildlifelens-smoke-net"
SERVER_NAME="wildlifelens-smoke-server"

NO_BUILD=false
for arg in "$@"; do
  [[ "$arg" == "--no-build" ]] && NO_BUILD=true
done

# ── 1. Build the test image ────────────────────────────────────────────────
if [[ "$NO_BUILD" == false ]]; then
  echo "==> Building Docker test image: $IMAGE"
  docker build \
    --file Dockerfile.test \
    --tag "$IMAGE" \
    --no-cache \
    .
fi

# ── 2. Run pytest suite ────────────────────────────────────────────────────
echo "==> Running test suite in Docker"
docker run \
  --rm \
  --env SECRET_KEY=test-docker-secret-key \
  --env PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" \
  pytest --tb=short -q

echo "==> All tests passed."

# ── 3. RBAC smoke-check: seed + verify each role ──────────────────────────
echo ""
echo "==> Running RBAC smoke-check (seed users + /api/auth/me)"

# Use the main app image for the smoke server
if [[ "$NO_BUILD" == false ]]; then
  docker build \
    --file Dockerfile \
    --tag "$SMOKE_IMAGE" \
    --no-cache \
    .
fi

# Isolated bridge network so the smoke client can reach the server by name
docker network create "$SMOKE_NET" 2>/dev/null || true

# Start app server in background: seed.py runs first, then wsgi.py
docker run \
  --rm \
  --detach \
  --name "$SERVER_NAME" \
  --network "$SMOKE_NET" \
  --env SECRET_KEY=smoke-secret-$(date +%s) \
  --env CLOCKIN_STRICT=false \
  "$SMOKE_IMAGE" >/dev/null

# Give the server a moment to seed and start
sleep 4

# Run smoke-check script inside a one-shot container on the same network
docker run \
  --rm \
  --network "$SMOKE_NET" \
  --env SERVER="http://${SERVER_NAME}:5000" \
  "$SMOKE_IMAGE" \
  python - <<'PYEOF'
import os, sys, json, urllib.request, urllib.error

BASE = os.environ["SERVER"]

USERS = [
    ("admin",        "Admin1234!",    "admin"),
    ("staff",        "Staff1234!",    "staff"),
    ("photographer", "Photo1234!",    "photographer"),
    ("kitchen",      "Kitchen1234!",  "kitchen"),
    ("member",       "Member1234!",   "member"),
]

errors = []
for username, password, expected_role in USERS:
    # --- login ---
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            cookie = resp.headers.get("Set-Cookie", "")
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        errors.append(f"FAIL login {username}: HTTP {e.code}")
        continue

    # --- /api/auth/me ---
    me_req = urllib.request.Request(
        f"{BASE}/api/auth/me",
        headers={"Cookie": cookie.split(";")[0]},
    )
    try:
        with urllib.request.urlopen(me_req) as resp:
            me = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        errors.append(f"FAIL /me {username}: HTTP {e.code}")
        continue

    roles = me.get("roles", [])
    if expected_role not in roles:
        errors.append(f"FAIL role {username}: expected '{expected_role}', got {roles}")
    else:
        print(f"  OK  {username:15s} role={expected_role}")

if errors:
    print("\nSmoke-check FAILED:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print("\nAll role checks passed.")
PYEOF

# Tear down smoke server and network
docker stop "$SERVER_NAME" 2>/dev/null || true
docker network rm "$SMOKE_NET" 2>/dev/null || true

echo "==> Smoke-check complete."
