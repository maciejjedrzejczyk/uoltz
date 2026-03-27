#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Switch back to Docker mode and start the bot in a container.
#
# This script:
#   1. Switches .env to Docker mode (container URLs)
#   2. Rebuilds and starts all services
# ─────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")/.."

source scripts/_prereqs.sh
check_docker_prereqs

ENV_FILE=".env"

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

echo "Starting Docker services..."
./scripts/up.sh
