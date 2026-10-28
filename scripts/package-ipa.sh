#!/usr/bin/env bash
# Turn a vanilla decrypted IPA + an extracted tweak .deb into a sideload IPA.
# App-agnostic: the tweak's dylib/bundle are found by --tweak-name in --deb-root.
#
#   package-ipa.sh --ipa <vanilla.ipa> --deb-root <dir> --tweak-name <Name> --out <out.ipa> [opts]
#     --name NAME               home-screen name (CFBundleDisplayName / CFBundleName)
#     --bundle-id ID            main bundle id (extensions keep their suffix)
#     --version VERSION         CFBundleShortVersionString + CFBundleVersion, every bundle
#     --min-ios VER|remove|keep MinimumOSVersion, every bundle (default keep)
#     --entitlements PLIST      merged into the main binary's entitlements
#     --icon IMAGE              home-screen icon (needs Pillow in cyan's env)
#     --sideload-fix DYLIB      LC-inject DYLIB (zxPluginsInject) into main exec + every appex
#     --appex DIR               add an .appex to PlugIns
#     --remove-device-limits    drop UISupportedDevices / UIRequiredDeviceCapabilities
#     --file-sharing            show the app's Documents folder in Files
#     --remove-extensions       drop the app's own extensions (an added --appex stays)
#     --tipa                    also write <out>.tipa, fakesigned for TrollStore
#
# Requires: cyan (pyzule-rw), ldid, python3, zip/unzip; ipapatch for --sideload-fix.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
die() { echo "package-ipa: $*" >&2; exit 1; }
color() { printf '\033[1;32m==> %s\033[0m\n' "$*"; }

IPA="" DEB_ROOT="" OUT="" TWEAK=""
NAME="" BUNDLE_ID="" VERSION="" MIN_IOS="keep" ENTITLEMENTS="" ICON=""
SIDELOAD_DYLIB="" APPEX="" DEVICE_LIMITS=0 FILE_SHARING=0 REMOVE_EXTENSIONS=0 TIPA=0

while [ $# -gt 0 ]; do
    case "$1" in
        --ipa)                  IPA="${2:?$1 needs a value}"; shift 2 ;;
        --deb-root)             DEB_ROOT="${2:?$1 needs a value}"; shift 2 ;;
        --tweak-name)           TWEAK="${2:?$1 needs a value}"; shift 2 ;;
        --out)                  OUT="${2:?$1 needs a value}"; shift 2 ;;
        --name)                 NAME="${2:?$1 needs a value}"; shift 2 ;;
        --bundle-id)            BUNDLE_ID="${2:?$1 needs a value}"; shift 2 ;;
        --version)              VERSION="${2:?$1 needs a value}"; shift 2 ;;
        --min-ios)              MIN_IOS="${2:?$1 needs a value}"; shift 2 ;;
        --entitlements)         ENTITLEMENTS="${2:?$1 needs a value}"; shift 2 ;;
        --icon)                 ICON="${2:?$1 needs a value}"; shift 2 ;;
        --sideload-fix)         SIDELOAD_DYLIB="${2:?$1 needs a value}"; shift 2 ;;
        --appex)                APPEX="${2:?$1 needs a value}"; shift 2 ;;
        --remove-device-limits) DEVICE_LIMITS=1; shift ;;
        --file-sharing)         FILE_SHARING=1; shift ;;
        --remove-extensions)    REMOVE_EXTENSIONS=1; shift ;;
        --tipa)                 TIPA=1; shift ;;
        *) die "unknown option $1 (see the header of $0)" ;;
    esac
done

[ -f "$IPA" ]      || die "--ipa $IPA not found"
[ -d "$DEB_ROOT" ] || die "--deb-root $DEB_ROOT not found"
[ -n "$TWEAK" ]    || die "--tweak-name is required"
[ -n "$OUT" ]      || die "--out is required"
[[ "$OUT" == *.ipa ]] || die "--out must end in .ipa"
[ -z "$ENTITLEMENTS" ] || plutil -lint "$ENTITLEMENTS" >/dev/null || die "$ENTITLEMENTS is not a valid plist"
[ -z "$ICON" ]     || [ -f "$ICON" ] || die "--icon $ICON not found"
[ -z "$SIDELOAD_DYLIB" ] || [ -f "$SIDELOAD_DYLIB" ] || die "--sideload-fix $SIDELOAD_DYLIB not found"
[ -z "$APPEX" ]    || [ -d "$APPEX" ] || die "--appex $APPEX not found"
[ -z "$BUNDLE_ID" ] || [[ "$BUNDLE_ID" =~ ^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$ ]] \
    || die "--bundle-id $BUNDLE_ID is not a reverse-DNS id"

DYLIB=$(find "$DEB_ROOT" -name "$TWEAK.dylib" | head -1)
BUNDLE=$(find "$DEB_ROOT" -type d -name "$TWEAK.bundle" | head -1)
[ -n "$DYLIB" ] || die "$TWEAK.dylib not in $DEB_ROOT"

mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
rm -f "$OUT"

color "cyan: inject tweak + name/bundle id/icon/entitlements"
INJECT=("$DYLIB")
[ -z "$BUNDLE" ]       || INJECT+=("$BUNDLE")
[ -z "$APPEX" ]        || INJECT+=("$APPEX")
# -w removes Watch apps; -c 9 is max compression.
CYAN=(-i "$IPA" -o "$OUT" -f "${INJECT[@]}" -w -c 9)
[ -z "$NAME" ]         || CYAN+=(-n "$NAME")
[ -z "$BUNDLE_ID" ]    || CYAN+=(-b "$BUNDLE_ID")
[ -z "$ICON" ]         || CYAN+=(-k "$ICON")
[ -z "$ENTITLEMENTS" ] || CYAN+=(-x "$ENTITLEMENTS")
[ "$REMOVE_EXTENSIONS" = 0 ] || CYAN+=(-e)
cyan "${CYAN[@]}"

if [ -n "$SIDELOAD_DYLIB" ]; then
    color "ipapatch: LC-inject $(basename "$SIDELOAD_DYLIB")"
    ipapatch --input "$OUT" --inplace --noconfirm --dylib "$SIDELOAD_DYLIB"
fi

# Sets Info.plist keys cyan misses on extensions, and moves each binary's
# LC_CODE_SIGNATURE back to the string-table end (ipapatch appends a second one;
# AltStore's ldid rejects that layout otherwise).
color "Info.plist keys + code-signature layout (ldid)"
PATCH=("$OUT" --min-ios "$MIN_IOS")
[ -z "$VERSION" ]        || PATCH+=(--version "$VERSION")
[ "$DEVICE_LIMITS" = 0 ] || PATCH+=(--remove-device-limits)
[ "$FILE_SHARING" = 0 ]  || PATCH+=(--file-sharing)
python3 "$SCRIPT_DIR/patch_ipa.py" "${PATCH[@]}"

if [ "$TIPA" = 1 ]; then
    color "TrollStore .tipa (fakesigned)"
    cyan -i "$OUT" -o "${OUT%.ipa}.tipa" -s -c 9
fi

color "Done"
if [ "$TIPA" = 1 ]; then ls -lh "$OUT" "${OUT%.ipa}.tipa"; else ls -lh "$OUT"; fi
