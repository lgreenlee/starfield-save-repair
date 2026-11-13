# Starfield Save Repair

An offline Python tool for narrowly targeted Starfield `.sfs` repairs. The first
recipe restores a severely displaced Anchorpoint station to its original local
position. The repair engine is reusable: recipes identify a reference by plugin
filename and local form ID, its expected cell, and the desired position.

**Windows beta, version 0.2.0.** An affected player reported that the repaired save
worked on November 13, 2026. Structural and byte-preservation checks also pass.
Detailed docking and persistence after save/reload were not independently recorded;
this is not a proven permanent fix for every affected save.

## Windows app — no Python installation needed

Download the **Windows x64 ZIP** from the
[v0.2.0 release](https://github.com/lgreenlee/starfield-save-repair/releases/tag/v0.2.0).
The release also includes source code and SHA-256 checksums.

1. Extract `starfield-save-repair-0.2.0-windows-x64.zip` completely.
2. Save and quit Starfield, then open `StarfieldSaveRepair.exe`.
3. Choose your `.sfs` save, or use **Use latest save**. Redirected Documents and
   OneDrive save folders are detected; **Browse** handles other locations.
4. Click **Check save**. If the position repair applies, click **Create repaired save**.
5. The app creates a separate `Save<number>` slot beside the selected save and
   shows its exact filename. In Starfield, use **Load** to select that new slot.

The original is preserved. A verified backup, repair candidate and JSON report
are kept in `%LOCALAPPDATA%\StarfieldSaveRepair\repairs`; **Open backup & report**
opens that repair's folder. The GUI refuses a running game, a changed input,
an existing output, unsupported save layouts, and already restored positions.
It never launches the game or changes security settings.

Keep `_internal` beside the EXE. This is an unsigned portable 64-bit Windows app,
tested on Windows 11. It needs no administrator access, account, Felix or SFSE.
See [START-HERE.txt](windows/START-HERE.txt) for recovery instructions.

## Requirements

- Python 3.11 or newer **only when running from source**. The Windows ZIP includes
  its own Python/Tk runtime. The repair engine has no third-party Python dependencies.
- A BCPS/ZIP `.sfs` save with engine layout 27 and save layout 153.
- An existing version-153 REFR record with a saved position in the expected cell.

Unsupported versions/layouts are refused. This release does not edit Xbox WGS
containers, dynamic references, actors, scripts, inventories, quests, docking
links, or physics blocks. It does not repair every cause of an unreachable station.

## Run from source

Open a terminal in this folder. Commands below work without installing a package:

```powershell
py -3 -m starfield_save_repair inspect "C:\path\affected.sfs"
py -3 -m starfield_save_repair plan "C:\path\affected.sfs"
py -3 -m starfield_save_repair repair "C:\path\affected.sfs" --output "C:\repair-work\candidate.sfs"
```

`inspect` and `plan` are read-only and report eligibility, the resolved form/cell,
current and proposed positions, decoded edit offset, and input hashes as JSON.
`repair` creates a **new** file, a hash-named original backup in `backups/`, and a
`.repair.json` receipt. Existing outputs and in-place repair are refused. Positions
already restored or below the recipe's displacement threshold are not written.

To install the CLI instead: `py -3 -m pip install .`, then use
`starfield-save-repair` in place of `py -3 -m starfield_save_repair`.

The default recipe is `starfield_save_repair/recipes/anchorpoint-position.json`.
Select another JSON recipe with `--recipe path/to/recipe.json` on any command.

## How the edit works

1. Validate and decompress the BCPS container with bounded decompression.
2. Read the save's plugin list and resolve its load-order-specific form ID.
3. Parse the change-form table and require exactly one matching REFR record.
4. Verify its version, saved-position layout, expected cell, finite coordinates,
   and minimum displacement.
5. Replace only the three float32 position values (12 bytes). Keep rotation,
   record sizes, flags, other references, and every opaque section unchanged.
6. Recompress changed chunks; reuse untouched compressed chunks verbatim.
7. Reopen and parse the candidate. Compare the entire decoded stream outside
   those 12 bytes for exact equality before writing output.

The compressed file can change size because the edited chunk compresses differently.
The decoded save size and all section offsets remain unchanged. A verification
receipt is evidence of these checks, **not** proof of in-game recovery.

## Anchorpoint finding and acceptance test

The examined save stored Anchorpoint at a vast offset while keeping it in the
correct scene. Its saved position matched the displaced live position. The
station's original position comes from `SFBGS00D.esm`, REFR local ID `064B7D`, in
cell `032DFF`. The recipe intentionally uses plugin-local IDs, not a fixed `02`
load-order prefix. It only proposes a repair for displacement above 100 million
reference-local game units.

This does not establish what initially displaced the station, nor whether an
attachment or script will move it again. The candidate preserves those systems.

Test a candidate separately from the only copy of your progress:

1. Keep the original and receipt. Close the game before installing a test save.
2. Use a separate test save slot, retaining a valid Starfield save filename pattern.
   The CLI's arbitrary output name is an offline artifact, not an automatic install.
3. Load the new slot and verify that Anchorpoint appears at ordinary approach range.
4. Hail and dock normally; check the interior and relevant mission state.
5. Undock normally, save to a new slot, reload, and revisit the station.
6. If anything fails, return to the untouched original. Do not describe the recipe
   as a permanent fix until this sequence succeeds.

The command-line `repair` operation creates an offline artifact at the requested
output path. The Windows app's **Create repaired save** action additionally installs
a separate game slot beside the selected original. Neither interface launches the game.

## Extending repairs

See [the recipe format](docs/recipe-format.md) and [format boundaries](docs/format-notes.md).
Version 1 recipes support restoring an existing reference's XYZ position only.
The engine can be extended with separately validated operations; there is no
generic arbitrary-offset patch command.

All externally emitted fields use camelCase and standard JSON. Receipts contain
save filenames and hashes, but omit full filesystem paths and parsed player
metadata. Save data remains on the PC; the tool makes no network requests.

## Tests and packaging

```powershell
py -3 -m unittest discover -s tests -v
py -3 scripts/package_release.py
```

For the self-contained Windows build, see [Windows build instructions](docs/windows-build.md).

Tests use synthetic saves, not redistributed player saves. The packaging script
uses explicit public source paths; `.private`, `.research`, saves, credentials,
local reports, and development environments are excluded. `--windows` also packages
the generated portable folder. Each release ZIP has a SHA-256 checksum. The build
scripts prepare packages locally; they never publish automatically. Published
packages are available under [Releases](https://github.com/lgreenlee/starfield-save-repair/releases).

## License and credits

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The format implementation
draws on [ReSaver++](https://github.com/Tonycubed2/ResaverPP) and the public
[StarfieldSaveTool format research](https://github.com/Nexus-Mods/StarfieldSaveTool).
No Bethesda binaries, plugin files, player saves, or third-party applications are
redistributed. This is an independent community tool, not a Bethesda product.
