# Migrating `spotify-pro-ios` (MakeItPlay) onto tweak-kit

`spotify-pro-ios` currently carries its own vendored copies of the pieces that
now live here. This note is for whoever picks up that migration later. The goal
is a behavior-preserving swap to the shared source — **do it on a branch and keep
the working tweak working**; verify a build before merging.

## What moves to the submodules

| spotify-pro-ios today | replace with |
|---|---|
| `modules/zxPluginsInject/` (SideloadFix.xm + `../../Sources/MakeItPlayC/fishhook.*`) | `Submodules/tweak-kit/zxPluginsInject/` (self-contained, bundles fishhook) |
| `Sources/MakeItPlayC/mip_analyzer.m` (generic console parts) | `Submodules/striker/src/striker.m` for the generic console; keep the Spotify-specific commands (speed/ogg/aes/player/keyget/…) in MakeItPlayC |
| the `@UserDefault` wrapper + `WindowHelper` in `Sources/MakeItPlay/Shared` | `Submodules/tweak-kit/swift/Shared/{UserDefault,WindowHelper}.swift` |
| `Scripts/{package-ipa.sh,patch_ipa.py,compat.py,publish_release.sh}` | `Submodules/tweak-kit/scripts/*` |
| `spotify-tweak/tools/objcinventory.py` | `Submodules/tweak-kit/tools/objcinventory.py` |

## Steps

1. `git submodule add https://github.com/RobyRew/tweak-kit Submodules/tweak-kit`
   and `... striker Submodules/striker`.
2. Delete `modules/zxPluginsInject/`; point `build-zxpi.sh` / the workflow at
   `Submodules/tweak-kit/zxPluginsInject` instead.
3. In the `Makefile`, replace the vendored shared-Swift paths with
   `find Submodules/tweak-kit/swift` and add `Submodules/striker/src/striker.m`
   to the C target; drop the now-duplicated files from `Sources/`.
4. Striker is the harder one: MakeItPlay's `mip_analyzer.m` mixes the generic
   console with Spotify-specific commands. Keep the Spotify commands in
   MakeItPlayC and have them register alongside striker, or extend striker with a
   command-registration hook so the app can add app-specific commands without
   forking the console. (Pick whichever is less invasive at the time.)
5. Repoint `Scripts/*` usages at `Submodules/tweak-kit/scripts/*`; pass the app
   name / bundle id / filter as arguments (they are parameters in the shared
   copies, hardcoded in MakeItPlay's).
6. Build `THEOS_PACKAGE_SCHEME=rootless make package` and confirm the `.deb`,
   extracted `.dylib`, and sideload `.ipa` match the pre-migration outputs
   (same files staged, same injection). Only then merge.

## Why

Both tweaks need the same sideload shim, the same RE inventory tool, the same
packaging scripts, and the same Swift plumbing. Keeping one versioned copy here
(consumed as a submodule) is the de-duplication rule applied to the tweak
ecosystem — no monorepo, no copy-paste, and each tweak stays independently
buildable from its own checkout plus pinned submodules.
