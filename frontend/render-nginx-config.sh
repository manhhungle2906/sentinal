#!/bin/sh
# Render the nginx configuration from the template.
#
# The placeholders use the __NAME__ form so the native nginx variables keep
# their meaning. The script writes the result to the given output path.
#
# Usage: render-nginx-config.sh <template> <output>

set -eu

TEMPLATE="${1:?the template path is required}"
OUTPUT="${2:?the output path is required}"

PORT="${PORT:-8080}"
CORE_UPSTREAM="${CORE_UPSTREAM:?CORE_UPSTREAM is required}"
INGEST_UPSTREAM="${INGEST_UPSTREAM:?INGEST_UPSTREAM is required}"

sed \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__CORE_UPSTREAM__|${CORE_UPSTREAM}|g" \
    -e "s|__INGEST_UPSTREAM__|${INGEST_UPSTREAM}|g" \
    "${TEMPLATE}" > "${OUTPUT}"

echo "==> rendered the nginx configuration into ${OUTPUT}"
