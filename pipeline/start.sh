#!/usr/bin/env sh
# Starts the AI test-case pipeline (Mac/Linux): sh pipeline/start.sh, then open http://localhost:8787
# Needs Python 3.10+ and pipeline/.env with HAI_API_KEY.
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3 || command -v python) || { echo "Python 3.10+ is needed: https://www.python.org/downloads/"; exit 1; }
if [ ! -f pipeline/.env ]; then
  cp pipeline/.env.example pipeline/.env
  echo "pipeline/.env was created. Put the team's API key after HAI_API_KEY= in that file, then run this again."
  exit 1
fi
"$PY" -c "import pypdf" 2>/dev/null || "$PY" -m pip install -q -r pipeline/requirements.txt || {
  echo "Could not install pypdf. Try: $PY -m pip install --user pypdf"; exit 1; }
echo "Open http://localhost:8787"
exec "$PY" pipeline/server.py "$@"
