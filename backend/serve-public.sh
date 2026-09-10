#!/usr/bin/env bash
#
# Put CROVIA on the internet, free, from this machine.
#
# Nokia sends congestion and geofence notifications TO us, and it cannot reach
# a laptop. A tunnel gives this machine a public HTTPS address so those two
# APIs can finally be used, without paying for hosting.
#
# The order matters: the tunnel has to exist before the backend starts, because
# the backend hands its own address to Nokia when it creates a subscription.
# Starting them the other way round registers subscriptions pointing at
# localhost, and the notifications go nowhere.
#
#   ./serve-public.sh              live Nokia if a key is set, simulator if not
#   ./serve-public.sh --twin       the simulated city, so a crowd actually forms
#
set -euo pipefail

cd "$(dirname "$0")"

CLOUDFLARED="${CLOUDFLARED:-$HOME/.local/bin/cloudflared}"
PORT="${PORT:-8000}"
LOGDIR="${TMPDIR:-/tmp}/crovia"
mkdir -p "$LOGDIR"

if [ ! -x "$CLOUDFLARED" ]; then
  echo "cloudflared is not installed. Install it with:"
  echo "  mkdir -p ~/.local/bin"
  echo "  curl -sL -o ~/.local/bin/cloudflared \\"
  echo "    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
  echo "  chmod +x ~/.local/bin/cloudflared"
  exit 1
fi

# Everything started here is stopped on the way out, including on Ctrl+C.
# A tunnel left running after the backend has gone is an address that answers
# with an error, which is more confusing than one that does not answer at all.
PIDS=()
cleanup() {
  echo
  echo "stopping..."
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

echo "opening a public address..."
"$CLOUDFLARED" tunnel --url "http://localhost:${PORT}" > "$LOGDIR/tunnel.log" 2>&1 &
PIDS+=($!)

URL=""
for _ in $(seq 1 40); do
  sleep 1
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOGDIR/tunnel.log" 2>/dev/null | head -1 || true)
  [ -n "$URL" ] && break
done

if [ -z "$URL" ]; then
  echo "the tunnel did not start. Its log:"
  tail -20 "$LOGDIR/tunnel.log"
  exit 1
fi

TWIN=""
if [ "${1:-}" = "--twin" ]; then
  TWIN="1"
  echo "mode: simulated city (a crowd will form)"
else
  echo "mode: live - Nokia if NOKIA_NAC_API_KEY is set, their test numbers if not"
fi

echo
echo "======================================================================"
echo "  public address:  $URL"
echo "  give Nokia:      $URL/webhooks/congestion"
echo "                   $URL/webhooks/geofencing"
echo "  check it:        curl $URL/health"
echo "======================================================================"
echo
echo "  point the app at it with:"
echo "    cd ../crovia-ui && EXPO_PUBLIC_API_BASE=$URL npm run web"
echo
echo "  Ctrl+C stops both the backend and the tunnel."
echo

# WEBHOOK_BASE_URL is what the backend gives Nokia when creating a
# subscription, so it has to be the tunnel address rather than localhost.
CROVIA_TWIN="$TWIN" \
WEBHOOK_BASE_URL="$URL" \
PYTHONPATH=. \
  ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
PIDS+=($!)

wait
