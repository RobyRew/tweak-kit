#!/usr/bin/env python3
"""Rewrite Info.plist keys and code-signature layout across an IPA.

cyan sets the name, bundle id, icon and entitlements. This sets the keys cyan
only touches on the main app, or not at all: version, MinimumOSVersion,
device limits and file sharing, on the app and every extension.

It also moves each thin 64-bit Mach-O's code signature back to the end of its
string table. ipapatch appends a new signature at the end of the file and
leaves the old one in place, and ldid (what AltStore signs with) asserts
`end >= size - 0x10` unless the signature starts within 16 bytes of the
string table end. The moved blob keeps its entitlements; its hashes are
stale, which is fine because every installer re-signs.

Only changed entries are re-encoded; every other zip entry is copied with its
original mode bits and symlink flag.

    patch_ipa.py App.ipa [--version V] [--min-ios VER|remove|keep]
                         [--remove-device-limits] [--file-sharing]

Does not sign. AltStore / Sideloadly / TrollStore sign on install.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

# Payload/X.app/Info.plist and Payload/X.app/{PlugIns,Extensions}/Y.appex/Info.plist
BUNDLE_PLIST = re.compile(
    r"^Payload/[^/]+\.app/(?:(?:PlugIns|Extensions)/[^/]+\.appex/)?Info\.plist$"
)
DEVICE_LIMIT_KEYS = ("UISupportedDevices", "UIRequiredDeviceCapabilities")
FILE_SHARING_KEYS = (
    "UIFileSharingEnabled",
    "LSSupportsOpeningDocumentsInPlace",
    "UISupportsDocumentBrowser",
)


def is_main_plist(name: str) -> bool:
    return name.count("/") == 2


def _is_symlink(entry: zipfile.ZipInfo) -> bool:
    return (entry.external_attr >> 16) & 0o170000 == 0o120000


def patch_info(
    info: dict,
    *,
    is_main: bool,
    version: str = "",
    min_ios: str = "keep",
    remove_device_limits: bool = False,
    file_sharing: bool = False,
) -> dict:
    if version:
        info["CFBundleShortVersionString"] = version
        info["CFBundleVersion"] = version
    if min_ios == "remove":
        info.pop("MinimumOSVersion", None)
    elif min_ios not in ("", "keep"):
        info["MinimumOSVersion"] = min_ios
    if remove_device_limits:
        for key in DEVICE_LIMIT_KEYS:
            info.pop(key, None)
    if file_sharing and is_main:
        for key in FILE_SHARING_KEYS:
            info[key] = True
    return info


def _encode(info: dict, original: bytes) -> bytes:
    fmt = plistlib.FMT_BINARY if original.startswith(b"bplist00") else plistlib.FMT_XML
    return plistlib.dumps(info, fmt=fmt)


MH_MAGIC_64 = b"\xcf\xfa\xed\xfe"  # little-endian 0xFEEDFACF
LC_SYMTAB, LC_SEGMENT_64, LC_CODE_SIGNATURE = 0x2, 0x19, 0x1D
ARM64_PAGE = 0x4000


def fix_signature_layout(data: bytes) -> bytes | None:
    """Return data with LC_CODE_SIGNATURE moved to the string table end, or
    None when the binary is not a thin 64-bit Mach-O or already fits ldid."""
    if len(data) < 32 or data[:4] != MH_MAGIC_64:
        return None
    (ncmds,) = struct.unpack_from("<I", data, 16)
    off, strtab_end, sig, linkedit = 32, None, None, None
    for _ in range(ncmds):
        if off + 8 > len(data):
            return None
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmdsize < 8 or off + cmdsize > len(data):
            return None
        if cmd == LC_SYMTAB:
            stroff, strsize = struct.unpack_from("<II", data, off + 16)
            strtab_end = stroff + strsize
        elif cmd == LC_CODE_SIGNATURE:
            sig = off
        elif cmd == LC_SEGMENT_64 and data[off + 8:off + 24].rstrip(b"\0") == b"__LINKEDIT":
            linkedit = off
        off += cmdsize
    if strtab_end is None or sig is None or linkedit is None:
        return None
    dataoff, datasize = struct.unpack_from("<II", data, sig + 8)
    # ldid needs strtab_end <= dataoff <= strtab_end + 0x10
    if dataoff - strtab_end <= 0x10 or dataoff + datasize > len(data):
        return None

    new_off = (strtab_end + 15) & ~15
    out = bytearray(data[:strtab_end])
    out += bytes(new_off - strtab_end)
    out += data[dataoff:dataoff + datasize]
    struct.pack_into("<II", out, sig + 8, new_off, datasize)
    # segment_command_64: vmsize at +32, fileoff at +40, filesize at +48
    (fileoff,) = struct.unpack_from("<Q", out, linkedit + 40)
    filesize = len(out) - fileoff
    struct.pack_into("<Q", out, linkedit + 32, (filesize + ARM64_PAGE - 1) & ~(ARM64_PAGE - 1))
    struct.pack_into("<Q", out, linkedit + 48, filesize)
    return bytes(out)


def patch_ipa(ipa: Path, **options) -> list[str]:
    """Patch bundle Info.plists and Mach-O signature layout in place.
    Returns the entry names changed."""
    ipa = Path(ipa).resolve()
    with zipfile.ZipFile(ipa) as zin:
        replacements: dict[str, bytes] = {}
        for entry in zin.infolist():
            name = entry.filename
            if BUNDLE_PLIST.match(name):
                original = zin.read(name)
                info = plistlib.loads(original)
                before = plistlib.dumps(info)
                patch_info(info, is_main=is_main_plist(name), **options)
                if plistlib.dumps(info) != before:
                    replacements[name] = _encode(info, original)
            elif not entry.is_dir() and entry.file_size > 32 and not _is_symlink(entry):
                with zin.open(entry) as f:
                    if f.read(4) != MH_MAGIC_64:
                        continue
                fixed = fix_signature_layout(zin.read(entry))
                if fixed is not None:
                    replacements[name] = fixed
        if not any(is_main_plist(n) for n in zin.namelist() if BUNDLE_PLIST.match(n)):
            raise SystemExit(f"no Payload/*.app/Info.plist in {ipa}")
        if not replacements:
            return []

        fd, tmp = tempfile.mkstemp(suffix=".ipa", dir=ipa.parent)
        os.close(fd)
        shutil.copymode(ipa, tmp)  # mkstemp creates 0600
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for entry in zin.infolist():
                    if entry.filename in replacements:
                        zout.writestr(entry, replacements[entry.filename])
                    elif entry.is_dir():
                        zout.writestr(entry, b"")
                    else:
                        with zin.open(entry) as src, zout.open(entry, "w") as dst:
                            shutil.copyfileobj(src, dst, 1 << 20)
            os.replace(tmp, ipa)
        except BaseException:
            os.unlink(tmp)
            raise
    return sorted(replacements)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ipa", type=Path)
    p.add_argument("--version", default="", help="CFBundleShortVersionString + CFBundleVersion")
    p.add_argument(
        "--min-ios",
        default="keep",
        help="MinimumOSVersion: a version such as 15.0, 'remove' to delete it, or 'keep'",
    )
    p.add_argument("--remove-device-limits", action="store_true")
    p.add_argument("--file-sharing", action="store_true")
    args = p.parse_args(argv)
    if args.min_ios not in ("keep", "remove") and not re.fullmatch(r"\d+(\.\d+){0,2}", args.min_ios):
        p.error(f"--min-ios must be a version, 'remove' or 'keep', not {args.min_ios!r}")
    changed = patch_ipa(
        args.ipa,
        version=args.version,
        min_ios=args.min_ios,
        remove_device_limits=args.remove_device_limits,
        file_sharing=args.file_sharing,
    )
    for name in changed:
        print(f"[patch_ipa] {name}")
    if not changed:
        print("[patch_ipa] nothing to change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
