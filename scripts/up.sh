#!/usr/bin/env bash
# Start all services (signal-api + bot). Rebuilds bot if image is stale.
set -e
cd "$(dirname "$0")/.."

source scripts/_prereqs.sh
check_docker_prereqs

echo "Starting services..."
docker compose up -d --build
echo ""
docker compose ps
echo ""
echo "Use './scripts/logs.sh' to follow bot output."
