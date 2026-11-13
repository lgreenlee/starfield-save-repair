# Recipe format v1

Recipes are JSON objects. They contain no executable scripts or binary offsets.

| Field | Meaning |
|---|---|
| `schemaVersion` | Must be `1`. |
| `id` | Nonempty recipe identifier. |
| `operation` | `restoreReferencePosition`. |
| `supportedSaveVersions` | Currently `[153]`. |
| `target.plugin` | Full, light, or medium plugin filename in the save. |
| `target.localFormId` | One to six hexadecimal digits, without load-order prefix. |
| `target.cellPlugin` | Plugin defining the expected containing cell. |
| `target.cellLocalFormId` | Expected cell's plugin-local ID. |
| `position` | Three finite numbers encodable as float32, in reference-local units. |
| `minimumDisplacement` | Positive threshold in the same units; closer positions are refused. |
| `title`, `status`, `evidence`, `limitations` | Human-readable documentation. |

The target must be an existing placed REFR, not a created `FF` reference or an
actor. The expected cell must match the first resolved reference in its saved
initial-position data. The tool resolves each plugin using the save's own lists.

Obtain positions from validated plugin/reference data, not a HUD range or a
different coordinate frame. Position restoration does not repair an incorrect
cell or attachment; write a separate, validated operation for those cases.

Recipes should ship with evidence, an affected synthetic test, refusal tests,
and a documented in-game validation status. Do not publish player saves as tests.
