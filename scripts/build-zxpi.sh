#!/usr/bin/env bash
# Build zxPluginsInject.dylib from the tweak-kit copy. Output: ./packages/zxPluginsInject.dylib
# (relative to the current directory, i.e. the consuming repo root). Requires THEOS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD_DIR="$(cd "$SCRIPT_DIR/../zxPluginsInject" && pwd)"
OUT_DIR="$(pwd)/packages"

: "${THEOS:=$HOME/theos}"
[ -d "$THEOS" ] || { echo "THEOS not set and \$HOME/theos not found" >&2; exit 1; }
export THEOS

cd "$MOD_DIR"
[ "${1:-}" = "--clean" ] && make clean >/dev/null 2>&1 || true
make FINALPACKAGE=1

DYLIB=""
for c in ".theos/obj/zxPluginsInject.dylib" ".theos/obj/debug/zxPluginsInject.dylib"; do
    [ -f "$MOD_DIR/$c" ] && DYLIB="$MOD_DIR/$c" && break
done
[ -n "$DYLIB" ] || { echo "zxPluginsInject.dylib not produced" >&2; exit 1; }

mkdir -p "$OUT_DIR"
cp "$DYLIB" "$OUT_DIR/zxPluginsInject.dylib"
install_name_tool -id "@rpath/zxPluginsInject.dylib" "$OUT_DIR/zxPluginsInject.dylib" 2>/dev/null || true
ls -lh "$OUT_DIR/zxPluginsInject.dylib"
