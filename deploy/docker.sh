#!/usr/bin/env bash
# Build and (re)start the EEL pipeline container on a workshop server (Docker preinstalled).
#
#   cd /srv/itsg && bash deploy/docker.sh [host_port]   # default 80 (the hessian.AI VM forwards 39080 to it)
#
# Needs pipeline/.env with HAI_API_KEY and PIPELINE_PASSWORD. App data and uploaded law files live in
# /srv/itsg-data, outside the container, so they survive rebuilds.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-80}"
DATA="${DATA_DIR:-/srv/itsg-data}"
ENV_FILE=pipeline/.env

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE"; exit 1; }
grep -q '^HAI_API_KEY=.' "$ENV_FILE" || { echo "HAI_API_KEY is not set in $ENV_FILE"; exit 1; }
grep -q '^PIPELINE_PASSWORD=.' "$ENV_FILE" || { echo "set PIPELINE_PASSWORD in $ENV_FILE"; exit 1; }
chmod 600 "$ENV_FILE"
mkdir -p "$DATA/data" "$DATA/law_file"

docker build -t itsg-pipeline .
docker rm -f itsg-pipeline 2>/dev/null || true
docker run -d --name itsg-pipeline --restart unless-stopped -p "$PORT:8787" --env-file "$ENV_FILE" \
  -v "$DATA/data:/app/pipeline/data" -v "$DATA/law_file:/app/docs/law_file" itsg-pipeline
sleep 3
page=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
api=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/users" || true)
echo "itsg-pipeline on port $PORT: page HTTP $page, API without sign-in HTTP $api (401 = password required). Logs: docker logs -f itsg-pipeline"
