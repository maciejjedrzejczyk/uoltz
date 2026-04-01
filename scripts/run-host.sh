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
#   ./scripts/run-host.sh              # start the bot interactively
#   ./scripts/run-host.sh --background # start the bot in the background
#   ./scripts/run-host.sh --stop       # stop background bot, switch to docker mode
# ─────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")/.."

source scripts/_prereqs.sh

ENV_FILE=".env"
PID_FILE="data/.bot.pid"
LOG_FILE="data/bot.log"

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

# ── Helper: stop any running background bot ──────────────────────────

stop_host_bot() {
  # Kill via PID file
  if [ -f "$PID_FILE" ]; then
    local pid
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping background bot (PID $pid)..."
      kill "$pid" 2>/dev/null || true
      # Wait up to 5 seconds for graceful shutdown
      for i in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
      done
      # Force kill if still running
      if kill -0 "$pid" 2>/dev/null; then
        echo "  Force killing PID $pid..."
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  # Also kill any orphaned bot.py processes (safety net)
  local pids
  pids=$(pgrep -f "python.*app/bot\.py" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Killing orphaned bot processes: $pids"
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 1
    # Force kill survivors
    pids=$(pgrep -f "python.*app/bot\.py" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
  fi
}

# ── Stop mode ────────────────────────────────────────────────────────

if [ "$1" = "--stop" ]; then
  stop_host_bot
  echo "Switching back to Docker mode..."
  switch_to_docker
  echo "You can now run ./scripts/up.sh to start in Docker."
  exit 0
fi

# ── Prerequisite checks ──────────────────────────────────────────────

check_host_prereqs

# ── Step 1: Stop any existing bot (Docker + background) ──────────────

echo ""
echo "Step 1: Stopping any existing bot..."
stop_host_bot
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

if [ "$1" = "--background" ] || [ "$1" = "--bg" ]; then
  mkdir -p data
  echo "Step 4: Starting bot in background..."
  PYTHONPATH=app nohup "$VENV_DIR/bin/python" app/bot.py >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "  Bot started (PID $(cat "$PID_FILE"))"
  echo "  Logs: tail -f $LOG_FILE"
  echo "  Stop: ./scripts/run-host.sh --stop"
else
  echo "Step 4: Starting bot on host..."
  echo "  Press Ctrl+C to stop."
  echo ""
  PYTHONPATH=app exec "$VENV_DIR/bin/python" app/bot.py
fi
