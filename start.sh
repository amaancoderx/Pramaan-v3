#!/usr/bin/env bash
# One-command local run without Docker: installs dependencies on first run, then starts API (:8000) and web (:3000).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/backend"

if [ -n "${PYTHON:-}" ]; then
  PY="$PYTHON"
else
  PY=""
  for candidate in python3.12 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 python3.11 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        PY="$candidate"
        break
      fi
    fi
  done
fi
if [ -z "$PY" ] || { ! command -v "$PY" >/dev/null 2>&1 && [ ! -x "$PY" ]; }; then
  echo "Python 3.11 or newer is required. Install Python from https://www.python.org/downloads/macos/"
  echo "If already installed, run: PYTHON=/path/to/python3.12 ./start.sh"
  exit 1
fi
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required; selected interpreter is too old: $PY"
  echo "Your system python3 may be older. Install Python 3.12 or set PYTHON=/path/to/python3.12."
  exit 1
fi
if [ ! -d .venv ]; then
  echo "Creating Python virtualenv (backend/.venv)..."
  "$PY" -m venv .venv
fi
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python; fi
REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
INSTALLED_HASH=""
[ -f .venv/.requirements-hash ] && INSTALLED_HASH="$(cat .venv/.requirements-hash)"
if [ "$INSTALLED_HASH" != "$REQ_HASH" ] || ! "$VPY" -c "import fastapi, rapidocr_onnxruntime, reportlab, bcrypt" >/dev/null 2>&1; then
  echo "Installing backend dependencies..."
  "$VPY" -m pip install -q --upgrade pip
  "$VPY" -m pip install -q -r requirements.txt
  printf '%s' "$REQ_HASH" > .venv/.requirements-hash
fi
if [ ! -f storage/benchmark_results.json ] && [ ! -f storage/dataset/manifest.json ]; then
  "$VPY" ../scripts/generate_dataset.py >/dev/null
fi

cd "$ROOT/frontend"
[ -d node_modules ] || { echo "Installing frontend dependencies..."; npm ci --no-audit --no-fund; }

cd "$ROOT/backend"
"$VPY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 75 &
API_PID=$!
trap 'echo; echo "Stopping Pramaan..."; kill $API_PID 2>/dev/null || true' INT TERM EXIT

cd "$ROOT/frontend"
echo
echo "  Web app   http://localhost:3000   (demo login: merchant@pramaan.local / shopkeeper123)"
echo "  API docs  http://localhost:8000/docs"
echo
npm run dev
