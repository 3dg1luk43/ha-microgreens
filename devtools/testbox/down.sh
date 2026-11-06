#!/usr/bin/env bash
# Stop the test box. --wipe also deletes config/.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker compose down --remove-orphans
[ "${1:-}" = "--wipe" ] && rm -rf config
exit 0
