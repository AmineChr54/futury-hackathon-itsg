#!/usr/bin/env bash
# Install (or update) and start the EEL pipeline on a Linux host, as a normal user (no sudo needed).
#
#   cd ~/eel && bash deploy/setup.sh [port]
#   ON_BOOT=1 bash deploy/setup.sh [port]   # also start it again after a reboot (crontab @reboot)
#
# Needs pipeline/.env with HAI_API_KEY and PIPELINE_PASSWORD (the server holds the API key, so a
# reachable instance must ask for a password). The Login tab then asks for it; PIPELINE_PASSWORD_ISTG and
# PIPELINE_PASSWORD_DEV give the two accounts their own passwords. pypdf is fetched from PyPI into pipeline/vendor when
# the system Python lacks it (it is pure Python, so no pip or venv is required).
# The server runs in the background and keeps running after you log out; run.sh restarts it.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$(pwd)"
PORT="${1:-8787}"
ENV_FILE="$APP/pipeline/.env"
VENDOR="$APP/pipeline/vendor"

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE"; exit 1; }
grep -q '^HAI_API_KEY=.' "$ENV_FILE" || { echo "HAI_API_KEY is not set in $ENV_FILE"; exit 1; }
grep -q '^PIPELINE_PASSWORD=.' "$ENV_FILE" || { echo "set PIPELINE_PASSWORD in $ENV_FILE"; exit 1; }
chmod 600 "$ENV_FILE"

if ! PYTHONPATH="$VENDOR" python3 -c 'import pypdf' 2>/dev/null; then
  echo "fetching pypdf from PyPI into $VENDOR"
  url=$(curl -fsSL https://pypi.org/pypi/pypdf/json | python3 -c 'import json,sys; print(next(u["url"] for u in json.load(sys.stdin)["urls"] if u["packagetype"] == "bdist_wheel"))')
  mkdir -p "$VENDOR"
  curl -fsSL "$url" -o /tmp/pypdf.whl
  python3 -m zipfile -e /tmp/pypdf.whl "$VENDOR"
  rm -f /tmp/pypdf.whl
fi

cat > "$APP/run.sh" <<EOF
#!/usr/bin/env bash
# (re)start the EEL pipeline in the background
cd "$APP"
pkill -f "pipeline/server.py --host 0.0.0.0 --port $PORT" 2>/dev/null || true
for i in \$(seq 20); do pgrep -f "pipeline/server.py --host 0.0.0.0 --port $PORT" >/dev/null || break; sleep 0.5; done
PYTHONPATH="$VENDOR" setsid nohup python3 pipeline/server.py --host 0.0.0.0 --port $PORT >> "$APP/server.log" 2>&1 < /dev/null &
EOF
chmod +x "$APP/run.sh"
if [ "${ON_BOOT:-0}" = "1" ]; then  # opt in: start again after a reboot
  ( crontab -l 2>/dev/null | grep -v "$APP/run.sh"; echo "@reboot $APP/run.sh" ) | crontab -
fi

"$APP/run.sh"
sleep 2
page=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
api=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/users" || true)
echo "EEL pipeline on port $PORT: page HTTP $page, API without sign-in HTTP $api (401 = password required, as it should). Log: $APP/server.log"
