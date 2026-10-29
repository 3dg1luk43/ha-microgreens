#!/usr/bin/env bash
# Bring the test box up and leave it onboarded.
#   ./up.sh            keep config/
#   ./up.sh --fresh    start from an empty config/
#   ./up.sh --legacy   (with --fresh) seed a 0.1.x .storage/microgreens to import
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
cd "$HERE"
FRESH=0; LEGACY=0
for a in "$@"; do
  case "$a" in --fresh) FRESH=1 ;; --legacy) LEGACY=1 ;; *) echo "unknown arg $a" >&2; exit 2 ;; esac
done
if [ "$FRESH" = 1 ]; then docker compose down --remove-orphans >/dev/null 2>&1 || true; rm -rf config; fi
mkdir -p config/.storage
[ -f config/configuration.yaml ] || cp support/configuration.yaml config/configuration.yaml
: > config/notify_capture.jsonl
if [ "$LEGACY" = 1 ]; then cp support/legacy_store.json config/.storage/microgreens; fi
docker compose up -d
"$PY" hactl.py wait --timeout 240
"$PY" hactl.py onboard
echo "box: http://127.0.0.1:8324  (testbox / testbox-pw-0123)   drive: $PY $HERE/hactl.py --help"
