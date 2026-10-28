#!/usr/bin/env python3
"""Load ./compatibility.json: the patch tag + supported host-app version range.

App-agnostic: the host app is named by `app` and its range by
`app_min` / `app_max` / `app_current`. Reads compatibility.json from the current
directory (the consuming repo's root) by default.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load(path=None) -> dict:
    data = json.loads(Path(path or "compatibility.json").read_text(encoding="utf-8"))
    if not re.fullmatch(r"v\d+\.\d+\.\d+", str(data.get("patch", ""))):
        raise ValueError("patch must be vMAJOR.MINOR.PATCH")
    for key in ("app", "app_min", "app_max", "platform"):
        if not data.get(key):
            raise ValueError(f"{key} required in compatibility.json")
    return data


def parse_ver(s) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", s or "")]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])


def covers(version, data=None) -> bool:
    data = data or load()
    v = parse_ver(version)
    return parse_ver(data["app_min"]) <= v <= parse_ver(data["app_max"])


def tag(data=None) -> str:
    return (data or load())["patch"]


def title(data=None) -> str:
    data = data or load()
    return f"{data['patch']} ({data['app'].lower()}_{data['app_min']}-{data['app_max']})"


def notes(data=None) -> str:
    data = data or load()
    return (
        f"{data['patch']} - {data['app']} {data['app_min']} to {data['app_max']}\n\n"
        "Install: sideload the patched IPA (AltStore / Sideloadly / TrollStore), "
        "or install the .deb on a jailbroken device.\n"
    )


def main(argv) -> int:
    data = load()
    if not argv or argv[0] == "--notes":
        sys.stdout.write(notes(data))
    elif argv[0] == "--tag":
        sys.stdout.write(tag(data) + "\n")
    elif argv[0] == "--title":
        sys.stdout.write(title(data) + "\n")
    elif argv[0] == "--covers":
        if len(argv) < 2:
            sys.stderr.write("usage: compat.py --covers VERSION\n")
            return 2
        sys.stdout.write("yes\n" if covers(argv[1], data) else "no\n")
    else:
        sys.stderr.write("usage: compat.py [--notes|--tag|--title|--covers VERSION]\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
