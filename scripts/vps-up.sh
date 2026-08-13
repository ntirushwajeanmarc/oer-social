#!/usr/bin/env bash
# Start OER Social on a VPS with Cloudflare Tunnel (single connector).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and set COMPOSE_PROFILES=tunnel + CLOUDFLARE_TUNNEL_TOKEN"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  echo "CLOUDFLARE_TUNNEL_TOKEN is empty in .env — refusing to start a broken tunnel."
  exit 1
fi

if [[ "${COMPOSE_PROFILES:-}" != *"tunnel"* ]]; then
  echo "Hint: set COMPOSE_PROFILES=tunnel in .env so cloudflared starts with the stack."
  export COMPOSE_PROFILES=tunnel
fi

docker compose up -d --build "$@"
docker compose ps
echo
echo "Tunnel logs (Ctrl+C to stop following):"
docker compose logs -f --tail=40 cloudflared
