#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the X Impact Simulator.
# Refreshes backend (FastAPI) and frontend (Next.js) dependencies after checkout.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Python virtualenv creation needs the stdlib venv/ensurepip package, which is
# not part of the base Ubuntu Python. Install it only when missing so this stays
# a no-op on snapshots that already contain it.
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# Backend: create the venv if absent, then sync pinned dependencies.
cd "$repo_root/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Frontend: install exactly what package-lock.json pins.
cd "$repo_root/frontend"
npm ci

# Provide local defaults (CORS origins, model names, ports) for development.
# The Groq key stays empty by default; the pipeline falls back to heuristic
# scoring when GROQ_API_KEY is unset.
cd "$repo_root"
if [ ! -f .env ]; then
  cp .env.example .env
fi
