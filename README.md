# tweak-kit

Shared infrastructure for RobyRew's iOS tweaks. Exists so the tweaks **dedupe via
one versioned source** instead of copy-pasting the same plumbing into each repo.
A consuming tweak adds this as a pinned git submodule; nothing here is forked per
app.

## Contents

- **`zxPluginsInject/`** — the sideload compatibility shim (`SideloadFix.xm` +
  bundled `fishhook`). LC-injected into the main executable and every app
  extension during IPA packaging. Five fixes, all app-agnostic: keychain
  access-group rebind, CloudKit neuter, app-group container URL, appex
  `NSUserDefaults` redirect, and main→appex defaults fan-out. Build with its own
  `Makefile` (`make` inside the folder) → `zxPluginsInject.dylib`.
- **`tools/objcinventory.py`** — chained-fixup-aware Mach-O Objective-C metadata
  dumper. Emits `classes.txt` / `methods.txt` / `protocols.txt` / `categories.txt`
  from a decrypted binary. Re-run it per host version and diff to re-target hooks
  that moved. Usage: `python3 objcinventory.py <mach-o> <outdir>`.
- **`swift/Shared/`** — reusable Swift pieces compiled into the consuming tweak's
  module:
  - `UserDefault.swift` — a `Codable`-backed `@UserDefault` property wrapper.
  - `WindowHelper.swift` — scene-aware key-window / top-VC / find-VC-by-class.
  - `TweakLog.swift` — file + `NSLog` logger (USB-pullable log file).
  - `HookActivator.swift` — version-independent Orion `HookGroup` activation
    guarded by runtime class/selector presence checks.
- **`scripts/`** — IPA packaging + release helpers, generalized (app name /
  bundle id / tweak name passed in): `package-ipa.sh` (cyan inject + ipapatch +
  `patch_ipa.py`), `build-zxpi.sh` (builds `zxPluginsInject.dylib`), `compat.py`
  (version/release tagging from `compatibility.json`), `publish_release.sh`
  (GitHub Release), `make-altstore-source.py` (AltStore `apps.json`).

## Consuming it from a tweak

```sh
git submodule add https://github.com/RobyRew/tweak-kit Submodules/tweak-kit
# Also add the introspection console as its own submodule (independent repo):
git submodule add https://github.com/RobyRew/striker Submodules/striker
```

In the tweak `Makefile`, compile the shared Swift and the console into the tweak:

```make
<Tweak>_FILES += $(shell find Submodules/tweak-kit/swift -name '*.swift') \
                 Submodules/striker/src/striker.m
<Tweak>_SWIFTFLAGS += -ISubmodules/striker/src
```

Build `zxPluginsInject.dylib` from `Submodules/tweak-kit/zxPluginsInject` and
LC-inject it during sideload packaging (via `ipapatch`). Use `scripts/` in CI for
`.deb` → `.dylib` extraction, cyan injection, `patch_ipa.py`, and the release +
AltStore-source steps.

## Relationship to `striker`

`striker` (the USB introspection console) is a **separate, independent repo** — it
is useful in any app, not just RobyRew tweaks — so tweak-kit does **not** vendor
it. A consuming tweak adds both as sibling submodules.

## Status

- `zxPluginsInject`, `tools/objcinventory.py`, `swift/Shared/`, and `scripts/`
  are in place.
- `MIGRATING-SPOTIFY.md` describes repointing `spotify-pro-ios` at this kit.

## License

GPL-3.0. See [LICENSE](LICENSE).
