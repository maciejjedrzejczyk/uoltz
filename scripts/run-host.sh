#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Run the bot directly on the host (not in Docker).
#
# This script:
#   1. Stops the Docker bot container (keeps signal-api running)
#   2. Switches .env to host mode (localhost URLs)
#   3. Creates/updates a uv venv and installs dependencies
#   4. Launches the bot
#
# Usage:
#   ./scripts/run-host.sh          # start the bot on host
#   ./scripts/run-host.sh --stop   # just stop and switch back to docker mode
# ─────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")/.."

source scripts/_prereqs.sh

ENV_FILE=".env"

# ── Helper: switch .env between modes ────────────────────────────────

switch_to_host() {
  echo "Switching .env to host mode..."
  # Comment out Docker URLs
  sed -i.bak \
    -e 's|^LLM_BASE_URL=http://10\.|#LLM_BASE_URL=http://10.|' \
    -e 's|^SIGNAL_API_URL=http://signal-api|#SIGNAL_API_URL=http://signal-api|' \
    "$ENV_FILE"
  # Uncomment Host URLs
  sed -i.bak \
    -e 's|^#LLM_BASE_URL=http://localhost|LLM_BASE_URL=http://localhost|' \
    -e 's|^#SIGNAL_API_URL=http://localhost|SIGNAL_API_URL=http://localhost|' \
    "$ENV_FILE"
  rm -f "${ENV_FILE}.bak"
}

switch_to_docker() {
  echo "Switching .env to Docker mode..."
  # Comment out Host URLs
  sed -i.bak \
    -e 's|^LLM_BASE_URL=http://localhost|#LLM_BASE_URL=http://localhost|' \
    -e 's|^SIGNAL_API_URL=http://localhost|#SIGNAL_API_URL=http://localhost|' \
    "$ENV_FILE"
  # Uncomment Docker URLs
  sed -i.bak \
    -e 's|^#LLM_BASE_URL=http://10\.|LLM_BASE_URL=http://10.|' \
    -e 's|^#SIGNAL_API_URL=http://signal-api|SIGNAL_API_URL=http://signal-api|' \
    "$ENV_FILE"
  rm -f "${ENV_FILE}.bak"
}

# ── Stop mode ────────────────────────────────────────────────────────

if [ "$1" = "--stop" ]; then
  echo "Switching back to Docker mode..."
  switch_to_docker
  echo "You can now run ./scripts/up.sh to start in Docker."
  exit 0
fi

# ── Prerequisite checks ──────────────────────────────────────────────

check_host_prereqs

# ── Step 1: Stop Docker bot (keep signal-api) ────────────────────────

echo ""
echo "Step 1: Stopping Docker bot container..."
docker compose stop bot 2>/dev/null || true
docker compose rm -f bot 2>/dev/null || true

# Make sure signal-api is running (we still need it)
echo "Ensuring signal-api is running..."
docker compose up -d signal-api 2>/dev/null

# Wait for signal-api
sleep 3
if curl -s http://localhost:9922/v1/about > /dev/null 2>&1; then
  echo "  signal-api is healthy."
else
  echo "  WARNING: signal-api not responding on localhost:9922"
fi

# ── Step 2: Switch .env to host mode ─────────────────────────────────

echo ""
echo "Step 2: Configuring .env for host mode..."
switch_to_host

# ── Step 3: Set up Python environment ────────────────────────────────

echo ""
echo "Step 3: Setting up Python environment..."

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "  Creating venv with uv..."
  uv venv "$VENV_DIR"
fi

echo "  Installing/updating dependencies..."
uv pip install -r app/requirements.txt --quiet

# Pre-download whisper model if not cached
"$VENV_DIR/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" 2>/dev/null

# ── Step 4: Launch the bot ───────────────────────────────────────────

echo ""
echo "Step 4: Starting bot on host..."
echo "  Press Ctrl+C to stop."
echo ""

PYTHONPATH=app exec "$VENV_DIR/bin/python" app/bot.py
