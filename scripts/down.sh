#!/usr/bin/env bash
# Stop all services (Docker + any background host bot)
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

echo "Stopping Docker services..."
docker compose down
echo "Done."
