#!/usr/bin/env bash
set -euo pipefail
export PATH="/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:${PATH}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker does not appear to be running. Start Docker Desktop and retry." >&2
  exit 1
fi

docker rm -f puzzle-server >/dev/null 2>&1 || true
docker pull ifajardov/puzzle-server
docker run -d --name puzzle-server -p 8080:8080 ifajardov/puzzle-server
echo "Server listening on http://127.0.0.1:8080/fragment?id=1"
curl -sS "http://127.0.0.1:8080/fragment?id=1"
echo
