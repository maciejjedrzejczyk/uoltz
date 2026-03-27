#!/usr/bin/env bash
# Stop all services
set -e
cd "$(dirname "$0")/.."

echo "Stopping services..."
docker compose down
echo "Done."
