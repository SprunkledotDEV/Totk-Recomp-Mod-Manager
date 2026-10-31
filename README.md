WARNING: This project is a temporary dud for mod support, it probably will be abandoned when the original recomp dev adds the support for modding.

# TotK Recomp Mod Manager

A standalone Windows mod manager for **TotK Recomp**, with a local mod library,
saved load order, TKMM package options, and one-click merging and launching.

This repository contains manager source code only. It includes no game, game
assets, console keys, installed mods, saves, or prepared mod output. You supply
your own compiled TotK Recomp installation.

## Features

- Choose the game folder on first launch; change it later from **Change game folder**.
- Keep the manager anywhere. Its `mods` and `merged-mods` directories live beside
  the manager, independently of the game installation.
- Import unpacked RomFS mods, ZIP archives, and TKCL packages, or copy them into
  `mods` and refresh. New imports start disabled.
- Enable or disable mods with checkboxes. Move mods up/down to set load order.
- Merge enabled mods in order. Later folder mods win whole-file conflicts; the
  report identifies the overridden path and winning mod.
- Apply TKCL changesets with the TkSharp engine used by TKMM, on top of earlier
  content rather than treating a changeset as a complete game file.
- Read TKCL descriptions, authors, package versions, and optional features through
  **Details / options**. Save selections and validate single-choice and required groups.
- Compare the TKCL build game-version field with the installed game's version.
  Warn on mismatches or missing machine-readable version information. This is a
  warning, not proof that a mod is compatible or incompatible.
- Combine resource-size tables conservatively, preserving installed allocation
  requirements. TkSharp also calculates requirements while applying changesets.
- Preserve the selected built-in frame-rate/UI/controller patch layer. Resolution
  and controller settings determine which installed patch variant is used.
- Generate verification manifests against the original RomFS image, including
  hashes for replacements and declarations for added files.
- Publish successful merges into separate immutable builds. Failed merges retain
  the previous output; unchanged inputs reuse the cached build.
- Launch the existing game with the merged overlay. No executable rebuild is
  needed for supported RomFS mods. Saves and the base RomFS are not replaced.

## Use

1. Install and extract the release ZIP anywhere on your PC (preferrably on the same disk as your Totk Recomp build)
2. Open **Mod Manager.exe** and select the folder containing `totk.exe` and
   `romfs/index.json`.
3. Import mods, tick the ones you want, and arrange the load order. Lower entries
   have higher priority.
4. Select a TKCL mod and choose **Details / options** to configure it.
5. Click **Merge**, or **Launch game** to merge and start the game.

Changes apply on the next launch. Close and reopen the manager after updating its
code. Directly launching `totk.exe` does not use this manager's overlay unless you
have separately configured one.

```text
Mod Manager/
  Mod Manager.exe
  portable.json           # selected game location
  mod-manager/            # application, backend, bundled Python
  mods/                   # mods and load-order.json
  merged-mods/            # immutable builds and active.json
```

Old builds remain available so an already-running game does not lose its files.
With the game and manager closed, remove unused build directories to reclaim
space; retain the build referenced by `active.json`.

## Compatibility and limits

**Tested target:** TotK Recomp 0.2.1 and Tears of the Kingdom 1.2.1 on Windows x64.
Other game/recompiler versions are not validated by this project.

- **ExeFS/IPS patches, cheats, and SubSDK executable plugins are unsupported.**
  ARM64 emulator plugins cannot be loaded directly into this x86-64 executable.
  Material Columns, for example, is not currently supported.
- `romfslite` exports and dependency-bearing TKCL packages are rejected. This is
  not TKMM's full dependency resolver or profile system.
- Folder mods merge at file level, not inside archives. Later replacement files
  can overwrite earlier changes, including built-in patches. Review overlaps.
- TKCL options are supported for direct packages and packages inside an imported
  folder. ZIP-wrapped TKCL packages merge with defaults; unpack them to configure
  their options or inspect their version metadata before merging.
- Unpack RAR and 7z archives before importing. ZIP input must resolve to one mod.
- Raw folder mods adding or enlarging resources should supply resource-size data.
  Merging a resource table is not a general conversion of assets between versions.
- Version warnings use package build metadata, not a complete compatibility
  database. There is no reliable version inference for arbitrary folder mods.
- Package thumbnails, mod downloads, automatic updates, and option dependency
  editing are not implemented.
- This does not guarantee that arbitrary combinations of mods work together.

## Linkle startup compatibility fix

The pinned TkSharp backend originally removed model materials that were not
referenced by mesh shapes. Game code can still access those materials directly.
The included [patch](patches/preserve-model-materials.patch) disables that cleanup
while retaining shader-version conversion.

The previous merged Linkle build reproducibly crashed during startup. The patched
build completed startup and survived a 45-second isolated-profile test without a
fatal error. That is a startup regression check, not a claim of full playthrough
compatibility. Original game files and saves were not patched.

## Source layout and tests

- `src/app`: Python/Tk UI, library/merge orchestration, manifest utility, C launcher,
  and synthetic regression tests.
- `src/backend`: C# adapter exposing the recompiler's indexed RomFS to TkSharp.
- `patches`: the small compatibility change applied to the pinned upstream engine.
- `UPSTREAM.json`: upstream revision and target information.
- `licenses`: retained dependency notices and the resolved NuGet component list.

Eight manager tests cover load-order precedence, disabling, persistence, ZIP
paths, failed-merge rollback, cache invalidation, patch selection, cleanup scope,
and UI controls/layout at different sizes and scaling factors. Actual game tests
require a local installation and are not included as data in this repository.

## Credits and licensing

See [CREDITS.md](CREDITS.md) for upstream projects and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for license metadata. This is not an all-MIT dependency stack: the resolved
MessageStudio, SarcLibrary, and Tkmm.BymlLibrary packages declare
`AGPL-3.0-or-later` in their NuGet metadata.

No new project-wide license was assigned as part of preparing this source folder.
Existing upstream license texts are retained; they do not automatically license
all newly written manager code. A project license still needs to be chosen before
presenting this as a licensed open-source release.

Independent community tooling; not affiliated with Nintendo or endorsed by the
upstream projects. Nintendo's game and assets are not included or relicensed.
