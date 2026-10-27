#!/usr/bin/env bash
# Build and (re)start the EEL pipeline container on a host with Docker. Data survives in the eel-data volume.
#
#   cd ~/eel && bash deploy/docker.sh [host-port]      # default 80 (the hackathon VM forwards 130.83.85.181:34080 to it)
#
# Needs pipeline/.env with HAI_API_KEY and PIPELINE_PASSWORD (the server holds the API key, so a reachable
# instance must ask for a password). Tune the AI workers with AI_CONCURRENCY / AI_PER_RUN in that file.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-80}"
ENV_FILE=pipeline/.env

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE"; exit 1; }
grep -q '^HAI_API_KEY=.' "$ENV_FILE" || { echo "HAI_API_KEY is not set in $ENV_FILE"; exit 1; }
grep -q '^PIPELINE_PASSWORD=.' "$ENV_FILE" || { echo "set PIPELINE_PASSWORD in $ENV_FILE"; exit 1; }
chmod 600 "$ENV_FILE"

docker build -t eel-pipeline .
docker rm -f eel >/dev/null 2>&1 || true
docker run -d --name eel --init --restart unless-stopped \
  -p "$PORT:8787" --env-file "$ENV_FILE" -v eel-data:/data \
  --log-opt max-size=10m --log-opt max-file=3 \
  eel-pipeline >/dev/null

for _ in $(seq 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' eel)" = healthy ] && break
  sleep 1
done
page=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" || true)
api=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/users" || true)
echo "EEL pipeline on port $PORT: page HTTP $page, API without sign-in HTTP $api (401 = password required, as it should)."
echo "Logs: docker logs -f eel"
