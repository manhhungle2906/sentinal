#!/usr/bin/env bash
# Start the four API Sentinel runtimes in one container.
#
# The Render free tier has no background worker, no private services and no
# one-off jobs, so the runtimes share a container. They stay separate OS
# processes with their own entry points:
#
#   1. the Core API             (port 8000)
#   2. the Ingestion API        (port 8001)
#   3. the detection worker     (no port)
#   4. nginx: SPA + same-origin proxy (port $PORT)
#
# The migration is the single schema owner and runs before any service
# starts. `alembic upgrade head` is idempotent, so a restart is safe.

set -euo pipefail

CORE_PORT="${CORE_PORT:-8000}"
INGEST_PORT="${INGEST_PORT:-8001}"
PORT="${PORT:-8080}"

echo "==> applying the database migrations"
alembic upgrade head

echo "==> starting the Core API on ${CORE_PORT}"
uvicorn sentinel.core.app:create_app --factory --host 0.0.0.0 --port "${CORE_PORT}" &
CORE_PID=$!

echo "==> starting the Ingestion API on ${INGEST_PORT}"
uvicorn sentinel.ingest.app:create_app --factory --host 0.0.0.0 --port "${INGEST_PORT}" &
INGEST_PID=$!

echo "==> starting the detection worker"
python -m sentinel.detector.worker &
DETECTOR_PID=$!

echo "==> starting nginx on ${PORT}"
/usr/local/bin/render-nginx-config.sh \
    /etc/nginx/templates/default.conf.template \
    /etc/nginx/conf.d/default.conf
nginx -g "daemon off;" &
NGINX_PID=$!

# Stop every process when the container is asked to stop, so the orchestrator
# sees a clean shutdown.
terminate() {
    echo "==> shutting down"
    kill -TERM "${CORE_PID}" "${INGEST_PID}" "${DETECTOR_PID}" "${NGINX_PID}" 2>/dev/null || true
    wait "${CORE_PID}" "${INGEST_PID}" "${DETECTOR_PID}" "${NGINX_PID}" 2>/dev/null || true
    exit 0
}
trap terminate TERM INT

# Exit as soon as any runtime dies, so the orchestrator restarts the container.
wait -n
exit 1
