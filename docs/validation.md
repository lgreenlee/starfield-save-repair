# Validation status: 0.2.0

## Automated

39 synthetic-fixture tests pass. Coverage includes changing only the intended
coordinate bytes, load-order variation, stored and compressed BCPS chunks,
byte-identical no-op round trips, unchanged-chunk preservation, malformed headers,
truncation, compression errors, unsupported versions, duplicate references, wrong
cells, non-finite coordinates, actor/unmoved-record refusal, displacement gating,
original preservation, backup/receipt creation, and refusal to overwrite files.
The Windows workflow adds coverage for separate slot allocation, a game starting
during repair, a changed input, an output-name race, complete-file installation,
paths containing spaces, both observed save filename conventions, and keeping
backups outside the live Saves folder.

Packaging tests verify the public source allowlist, ZIP integrity and checksums,
refusal to replace an existing release, and rejection of save/credential/database
files or files outside the bundle root.

## Affected-save check

An affected engine-27/save-153 file from Starfield 1.16.244.0 was parsed and repaired
as a separate candidate. The station's saved coordinates matched read-only live
runtime observations. After repacking and reopening, the target held its authored
XYZ position. All decoded bytes outside the 12-byte coordinate field were identical.
The input save was not modified. The candidate, input backup, and detailed receipt
are private validation artifacts and are excluded from distribution.

## Player report

On November 13, 2026, the affected player reported "That worked" after being given
the repaired copy of their latest save as a separate slot. The repair changed only
the station's 12-byte position field; the original remained intact. This supports
recovery in that case. No detailed docking or persistence observations were
independently captured, so those specific checks remain outstanding.

## Windows application

The standalone Windows 11 application starts with its bundled Python/Tk runtime.
The player also reported testing the interface on November 13, 2026. Automated
tests exercise the inspection and repair workflow with synthetic saves, including
new-slot creation and refusal to repair an already restored position. The release
archives pass integrity and checksum checks and contain no player saves or private
project data.

## Outstanding

Normal approach/docking, interior and quest behavior, undocking, and persistence
after save/reload have not been independently verified.
The cause of the original displacement and any surviving attachment corruption
remain unknown. Do not promote the recipe from experimental on structural checks
alone or treat one successful report as broad compatibility evidence.
