#!/usr/bin/env bash
# Follow logs for the bot (or pass a service name as argument)
set -e
cd "$(dirname "$0")/.."

SERVICE="${1:-bot}"
docker compose logs -f "$SERVICE"
