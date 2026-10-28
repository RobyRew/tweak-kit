#!/usr/bin/env bash
# Create or update the GitHub Release named in ./compatibility.json, attaching
# the given assets. Run from the consuming repo root (gh uses its remote/token).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=(python3); command -v python3 >/dev/null 2>&1 || PY=(python)
TAG="$("${PY[@]}" "$SCRIPT_DIR/compat.py" --tag | tr -d '\r')"
TITLE="$("${PY[@]}" "$SCRIPT_DIR/compat.py" --title | tr -d '\r')"
NOTES="$("${PY[@]}" "$SCRIPT_DIR/compat.py" --notes | tr -d '\r')"

for f in "$@"; do [ -f "$f" ] || { echo "missing asset $f" >&2; exit 1; }; done

if gh release view "$TAG" >/dev/null 2>&1; then
    [ $# -gt 0 ] && gh release upload "$TAG" "$@" --clobber
    gh release edit "$TAG" --title "$TITLE" --notes "$NOTES"
else
    gh release create "$TAG" "$@" --title "$TITLE" --notes "$NOTES"
fi
echo "published $TAG"
