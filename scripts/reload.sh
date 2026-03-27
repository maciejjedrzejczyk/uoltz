#!/usr/bin/env bash
# Rebuild and restart only the bot container (signal-api stays running)
set -e
cd "$(dirname "$0")/.."

echo "Stopping bot..."
docker compose stop bot
docker compose rm -f bot

echo "Rebuilding and starting bot..."
docker compose up -d --build bot
echo ""
docker compose ps
echo ""
echo "Use './scripts/logs.sh' to follow bot output."
