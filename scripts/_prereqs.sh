#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Shared prerequisite checks for setup scripts.
# Source this file, don't execute it directly.
#
# Usage in other scripts:
#   source "$(dirname "$0")/_prereqs.sh"
#   check_docker_prereqs   # for Docker mode
#   check_host_prereqs     # for host mode
# ─────────────────────────────────────────────────────────────────────

set -e

_BOLD="\033[1m"
_GREEN="\033[32m"
_YELLOW="\033[33m"
_RED="\033[31m"
_RESET="\033[0m"

_ok()   { echo -e "  ${_GREEN}✓${_RESET} $1"; }
_warn() { echo -e "  ${_YELLOW}⚠${_RESET} $1"; }
_fail() { echo -e "  ${_RED}✗${_RESET} $1"; }

# ── Individual checks ────────────────────────────────────────────────

_check_docker() {
  if command -v docker &>/dev/null; then
    _ok "docker ($(docker --version 2>&1 | head -1))"
    return 0
  fi

  _fail "docker not found"
  echo ""
  echo "    Install Docker Desktop: https://www.docker.com/products/docker-desktop"
  echo "    Or Finch (macOS):       brew install --cask finch && finch vm init"
  echo ""
  return 1
}

_check_docker_compose() {
  if docker compose version &>/dev/null; then
    _ok "docker compose ($(docker compose version 2>&1 | head -1))"
    return 0
  fi

  _fail "docker compose not found"
  echo "    Docker Compose is included with Docker Desktop."
  echo "    For standalone: https://docs.docker.com/compose/install/"
  return 1
}

_check_python() {
  local py=""
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver=$("$cmd" --version 2>&1)
      # Check minimum version 3.11
      local minor
      minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
      if [ "$minor" -ge 11 ] 2>/dev/null; then
        _ok "$cmd ($ver)"
        return 0
      else
        _warn "$cmd found but version too old ($ver). Need 3.11+"
      fi
    fi
  done

  _fail "python 3.11+ not found"
  echo ""
  echo "    macOS:   brew install python@3.13"
  echo "    Ubuntu:  sudo apt install python3.13"
  echo "    Or:      https://www.python.org/downloads/"
  echo ""
  return 1
}

_check_uv() {
  if command -v uv &>/dev/null; then
    _ok "uv ($(uv --version 2>&1))"
    return 0
  fi

  _warn "uv not found — installing..."
  if command -v curl &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh 2>&1
    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if command -v uv &>/dev/null; then
      _ok "uv installed ($(uv --version 2>&1))"
      return 0
    fi
  fi

  _fail "Could not install uv automatically"
  echo "    Install manually: https://docs.astral.sh/uv/getting-started/installation/"
  return 1
}

_check_ffmpeg() {
  if command -v ffmpeg &>/dev/null; then
    _ok "ffmpeg ($(ffmpeg -version 2>&1 | head -1 | awk '{print $3}'))"
    return 0
  fi

  _warn "ffmpeg not found — attempting install..."
  if command -v brew &>/dev/null; then
    brew install ffmpeg 2>&1
    if command -v ffmpeg &>/dev/null; then
      _ok "ffmpeg installed via Homebrew"
      return 0
    fi
  elif command -v apt-get &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg 2>&1
    if command -v ffmpeg &>/dev/null; then
      _ok "ffmpeg installed via apt"
      return 0
    fi
  fi

  _fail "Could not install ffmpeg automatically"
  echo "    macOS:   brew install ffmpeg"
  echo "    Ubuntu:  sudo apt install ffmpeg"
  echo "    Other:   https://ffmpeg.org/download.html"
  return 1
}

_check_curl() {
  if command -v curl &>/dev/null; then
    _ok "curl"
    return 0
  fi
  _fail "curl not found (needed for API calls)"
  return 1
}

_check_env_file() {
  local dir="$1"
  if [ -f "$dir/.env" ]; then
    _ok ".env file exists"
    return 0
  fi

  _warn ".env not found — creating from .env.example..."
  if [ -f "$dir/.env.example" ]; then
    cp "$dir/.env.example" "$dir/.env"
    _ok ".env created from template"
    echo ""
    echo -e "    ${_YELLOW}Please edit .env with your Signal number and LLM settings${_RESET}"
    echo ""
    return 0
  fi

  _fail ".env.example not found either"
  return 1
}

# ── Composite checks ─────────────────────────────────────────────────

check_docker_prereqs() {
  echo -e "${_BOLD}Checking Docker prerequisites...${_RESET}"
  local failed=0
  _check_docker       || failed=1
  _check_docker_compose || failed=1
  _check_curl         || failed=1
  _check_env_file "." || failed=1

  if [ $failed -ne 0 ]; then
    echo ""
    echo -e "${_RED}Some prerequisites are missing. Please install them and try again.${_RESET}"
    exit 1
  fi
  echo ""
}

check_host_prereqs() {
  echo -e "${_BOLD}Checking host prerequisites...${_RESET}"
  local failed=0
  _check_docker       || failed=1   # still needed for signal-api
  _check_docker_compose || failed=1
  _check_python       || failed=1
  _check_uv           || failed=1
  _check_ffmpeg       || failed=1
  _check_curl         || failed=1
  _check_env_file "." || failed=1

  if [ $failed -ne 0 ]; then
    echo ""
    echo -e "${_RED}Some prerequisites are missing. Please install them and try again.${_RESET}"
    exit 1
  fi
  echo ""
}
