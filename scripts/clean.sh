#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Clean up: stop services, remove containers, images, and Python venv.
#
# Usage:
#   ./scripts/clean.sh          # clean everything
#   ./scripts/clean.sh --keep-data   # clean but preserve data/
# ─────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")/.."

KEEP_DATA=false
[ "$1" = "--keep-data" ] && KEEP_DATA=true

echo "Signal Agent — Cleanup"
echo ""

# ── Stop running bot process ─────────────────────────────────────────
if pgrep -f "app/bot.py" > /dev/null 2>&1; then
  echo "Stopping host bot process..."
  pkill -f "app/bot.py" || true
fi

# ── Stop and remove Docker containers ────────────────────────────────
if command -v docker &>/dev/null; then
  echo "Stopping Docker containers..."
  docker compose down 2>/dev/null || true

  echo "Removing bot Docker image..."
  docker rmi signal-agent-bot 2>/dev/null || true
  # Also try the compose-generated name
  docker rmi signal-agent_bot 2>/dev/null || true
fi

# ── Remove Python virtual environment ────────────────────────────────
if [ -d ".venv" ]; then
  echo "Removing Python venv (.venv/)..."
  rm -rf .venv
fi

# ── Remove Python caches ─────────────────────────────────────────────
echo "Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# ── Optionally remove data ───────────────────────────────────────────
if [ "$KEEP_DATA" = false ]; then
  echo ""
  echo "WARNING: This will delete all data (Signal account, notes, brainstorms)."
  read -p "Delete data/ directory? [y/N] " confirm
  if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    echo "Removing data/..."
    rm -rf data
  else
    echo "Keeping data/."
  fi
else
  echo "Keeping data/ (--keep-data)."
fi

echo ""
echo "Done. To set up again, run:"
echo "  ./scripts/run-host.sh    (host mode)"
echo "  ./scripts/up.sh          (Docker mode)"
