#!/usr/bin/env python3
"""Generate/refresh an AltStore source (apps.json) for a tweak release.

Reads ./compatibility.json for the version, and takes the released IPA plus its
download URL. Writes an AltStore source JSON a user adds once for one-tap install
and auto-updates.

  make-altstore-source.py --ipa OUT.ipa --download-url URL --bundle-id ID \
      --source-name NAME --app-name NAME --out docs/apps.json [--min-ios 18.0]
                                                              [--description TEXT]
                                                              [--tint 0a66c2]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import compat  # sibling module in this directory


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ipa", type=Path, required=True)
    p.add_argument("--download-url", required=True)
    p.add_argument("--bundle-id", required=True)
    p.add_argument("--source-name", required=True)
    p.add_argument("--app-name", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--min-ios", default="18.0")
    p.add_argument("--description", default="")
    p.add_argument("--tint", default="0a66c2")
    args = p.parse_args(argv)

    data = compat.load()
    version = compat.tag(data).lstrip("v")
    size = args.ipa.stat().st_size
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    app = {
        "name": args.app_name,
        "bundleIdentifier": args.bundle_id,
        "developerName": "RobyRew",
        "version": version,
        "versionDate": now,
        "versionDescription": compat.notes(data).strip(),
        "downloadURL": args.download_url,
        "localizedDescription": args.description or f"{args.app_name} - customization tweak.",
        "iconURL": "",
        "tintColor": args.tint,
        "size": size,
        "minOSVersion": args.min_ios,
    }
    source = {
        "name": args.source_name,
        "identifier": f"{args.bundle_id}.source",
        "apps": [app],
        "news": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} (version {version}, {size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
