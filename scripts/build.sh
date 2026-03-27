#!/usr/bin/env bash
# Build (or rebuild) the bot container image
set -e
cd "$(dirname "$0")/.."

echo "Building signal-bot image..."
docker compose build bot
echo "Done."
