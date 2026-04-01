#!/usr/bin/env bash
# Rebuild and restart the bot (Docker container or background host process)
set -e
cd "$(dirname "$0")/.."

PID_FILE="data/.bot.pid"

# Stop background host bot if running
if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping background bot (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 2
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

# Kill any orphaned bot.py processes
pids=$(pgrep -f "python.*app/bot\.py" 2>/dev/null || true)
if [ -n "$pids" ]; then
  echo "Killing orphaned bot processes: $pids"
  echo "$pids" | xargs kill 2>/dev/null || true
  sleep 1
  pids=$(pgrep -f "python.*app/bot\.py" 2>/dev/null || true)
  [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
fi

# Check if we're in host mode (host URLs uncommented in .env)
if grep -q "^SIGNAL_API_URL=http://localhost" .env 2>/dev/null; then
  echo "Host mode detected — restarting bot on host in background..."
  exec ./scripts/run-host.sh --background
else
  echo "Stopping Docker bot..."
  docker compose stop bot
  docker compose rm -f bot

  echo "Rebuilding and starting bot..."
  docker compose up -d --build bot
  echo ""
  docker compose ps
  echo ""
  echo "Use './scripts/logs.sh' to follow bot output."
fi
