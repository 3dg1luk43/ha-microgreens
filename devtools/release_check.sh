#!/usr/bin/env bash
# Release preflight: everything that must be true before a tag is cut.
#
#   devtools/release_check.sh                 verify (what CI runs)
#   devtools/release_check.sh --tag v0.2.0    also: tag == manifest, CHANGELOG entry dated
#
# Exit code is the number of failed checks.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

WANT_TAG=""
[[ "${1:-}" == "--tag" ]] && WANT_TAG="${2:-}"
PY="${PYTHON:-/root/ha_washdata/.venv/bin/python}"
[[ -x "$PY" ]] || PY="python3"
COMP="custom_components/ha_microgreens"
FAILED=0
pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILED=$((FAILED + 1)); }

echo "Version"
if WANT_TAG="$WANT_TAG" "$PY" - <<'PY'
import json, os, re, sys
mf = json.load(open("custom_components/ha_microgreens/manifest.json"))["version"]
m = re.search(r"^## (\S+)(?: - (.+))?$", open("CHANGELOG.md", encoding="utf-8").read(), re.M)
want = (os.environ.get("WANT_TAG") or "").lstrip("v")
bad = []
if not m or m.group(1) != mf: bad.append(f"manifest {mf} != CHANGELOG {m.group(1) if m else None}")
if want and want != mf: bad.append(f"tag {want} != manifest {mf}")
if want and not re.match(r"\d{4}-\d{2}-\d{2}$", (m.group(2) or "") if m else ""): bad.append("CHANGELOG entry is not dated")
if bad: print("\n".join(bad))
sys.exit(1 if bad else 0)
PY
then pass "manifest, CHANGELOG and tag agree"; else fail "version"; fi

echo "Syntax"
"$PY" -m compileall -q "$COMP" tests devtools >/dev/null && pass "python compiles" || fail "python compile"
for f in "$COMP"/www/*.js; do
  tmp="$(mktemp --suffix=.mjs)"; cp "$f" "$tmp"
  node --check "$tmp" 2>/dev/null && pass "node --check $(basename "$f")" || fail "node --check $(basename "$f")"
  rm -f "$tmp"
done
for f in "$COMP"/*.json "$COMP"/translations/*.json "$COMP"/www/i18n/*.json hacs.json; do
  "$PY" -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" "$f" 2>/dev/null || fail "json $f"
done
pass "json parses"

echo "Lint"
if "$PY" -m ruff --version >/dev/null 2>&1; then
  "$PY" -m ruff check --isolated --select F,E9 custom_components tests devtools >/dev/null && pass "ruff F,E9" || fail "ruff F,E9"
else
  echo "  skip  ruff not installed"
fi

echo "Tests"
LOG="$(mktemp)"
if "$PY" -m pytest -p no:sugar >"$LOG" 2>&1; then pass "pytest: $(grep -Eo '[0-9]+ passed[^=]*' "$LOG" | tail -1)"; else fail "pytest (log: $LOG)"; fi

echo
[[ $FAILED -eq 0 ]] && echo "release check passed" || echo "$FAILED check(s) failed"
exit $FAILED
