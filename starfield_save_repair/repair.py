"""Recipe-driven, same-length edits with exact preservation of unrelated bytes."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from .formats import Container, FormatError, Save


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_recipe(path=None):
    path = Path(path) if path else Path(__file__).parent / "recipes" / "anchorpoint-position.json"
    recipe = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(recipe, dict) or recipe.get("schemaVersion") != 1 or recipe.get("operation") != "restoreReferencePosition":
        raise FormatError("Unsupported repair recipe")
    target = recipe.get("target", {})
    if not isinstance(target, dict):
        raise FormatError("Invalid recipe target")
    for key in ("plugin", "cellPlugin"):
        value = target.get(key)
        if not isinstance(value, str) or not value or any(c in value for c in "/\\\0"):
            raise FormatError("Recipe plugin must be a filename")
    for key in ("localFormId", "cellLocalFormId"):
        value = target.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,6}", value) or int(value, 16) == 0:
            raise FormatError("Invalid recipe local form ID")
    position = recipe.get("position")
    if not isinstance(position, list) or len(position) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in position):
        raise FormatError("Recipe requires three finite position coordinates")
    try:
        packed = struct.pack("<3f", *position)
    except (OverflowError, struct.error) as exc:
        raise FormatError("Position exceeds float32 range") from exc
    if not all(math.isfinite(v) for v in struct.unpack("<3f", packed)):
        raise FormatError("Position exceeds float32 range")
    minimum = recipe.get("minimumDisplacement")
    if type(minimum) not in (int, float) or not math.isfinite(minimum) or minimum <= 0:
        raise FormatError("Recipe requires a positive minimumDisplacement")
    if recipe.get("supportedSaveVersions") != [153] or not isinstance(recipe.get("id"), str) or not recipe["id"]:
        raise FormatError("Recipe must identify itself and support save version 153")
    return recipe


class Repair:
    def __init__(self, file, recipe):
        self.original = file
        self.recipe = recipe
        self.container = Container(file)
        self.save = Save(self.container.inner)
        target = recipe["target"]
        form_id = self.save.plugin_form(target["plugin"], int(target["localFormId"], 16))
        cell_id = self.save.plugin_form(target["cellPlugin"], int(target["cellLocalFormId"], 16))
        self.form = self.save.find(form_id)
        self.observed = self.save.position(self.form)
        if self.observed["cellId"] != f"{cell_id:08X}":
            raise FormatError("Reference is in a different cell; this recipe cannot repair it")
        self.offset = self.observed["positionOffset"]
        self.before = self.container.inner[self.offset:self.offset + 12]
        self.after = struct.pack("<3f", *recipe["position"])
        if any(not math.isfinite(v) for v in self.observed["position"]):
            raise FormatError("Non-finite saved coordinates require a different repair")
        self.distance = math.dist(self.observed["position"], struct.unpack("<3f", self.after))
        if self.before == self.after:
            self.status = "alreadyAtDesiredPosition"
        elif self.distance < recipe["minimumDisplacement"]:
            self.status = "belowDisplacementThreshold"
        else:
            self.status = "eligible"

    def report(self):
        return {
            "schemaVersion": 1, "recipeId": self.recipe["id"], "status": self.status,
            "inputSha256": sha256(self.original), "decodedSha256": sha256(self.container.inner),
            "saveVersion": self.save.save_version, "gameVersion": self.save.game_version,
            "targetPlugin": self.recipe["target"]["plugin"], "formId": f"{self.form.form_id:08X}",
            "cellId": self.observed["cellId"], "changeFormCount": len(self.save.forms),
            "currentPosition": self.observed["position"], "desiredPosition": list(struct.unpack("<3f", self.after)),
            "displacement": self.distance, "coordinateUnits": "referenceLocalGameUnits",
            "decodedOffset": self.offset, "editLength": 12,
            "beforeHex": self.before.hex(), "afterHex": self.after.hex(),
            "gameValidated": False,
        }

    def candidate(self):
        if self.status != "eligible":
            raise FormatError(f"Repair refused: {self.status}")
        inner = self.container.inner
        changed = inner[:self.offset] + self.after + inner[self.offset + 12:]
        result = self.container.replace(changed)
        decoded = Container(result).inner
        # Compare everything outside the intended field, including opaque data.
        if decoded[:self.offset] != inner[:self.offset] or decoded[self.offset + 12:] != inner[self.offset + 12:] or len(decoded) != len(inner):
            raise FormatError("Unrelated decoded save data changed")
        verified = Save(decoded)
        observed = verified.position(verified.find(self.form.form_id))
        if struct.pack("<3f", *observed["position"]) != self.after or observed["cellId"] != self.observed["cellId"]:
            raise FormatError("Repaired reference failed structured readback")
        report = self.report()
        report.update(status="candidateVerified", outputSha256=sha256(result),
                      outputDecodedSha256=sha256(decoded), unrelatedDecodedBytesUnchanged=True,
                      changedByteCount=sum(a != b for a, b in zip(self.before, self.after)))
        return result, report


def write_new(path, data):
    """Exclusive creation; never overwrites an existing path or follows a link."""
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        import os
        os.fsync(stream.fileno())


def write_repair(source, output, recipe):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or output.exists() or output.is_symlink():
        raise FormatError("Output must be a new file distinct from the original")
    if output.suffix.lower() != ".sfs":
        raise FormatError("Output must have the .sfs extension")
    receipt = output.with_suffix(".repair.json")
    if receipt.exists() or receipt.is_symlink():
        raise FormatError("Receipt already exists; choose a new output name")
    repair = Repair(source.read_bytes(), recipe)
    data, report = repair.candidate()
    # Recheck after parsing/compression in case the game/cloud replaced the source.
    if sha256(source.read_bytes()) != report["inputSha256"]:
        raise FormatError("Input changed during repair; no output written")
    output.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = output.parent / "backups"
    if backup_dir.is_symlink():
        raise FormatError("Backup directory must not be a symlink")
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / (report["inputSha256"] + ".sfs")
    if backup.is_symlink():
        raise FormatError("Backup must not be a symlink")
    if backup.exists():
        if sha256(backup.read_bytes()) != report["inputSha256"]:
            raise FormatError("Existing backup does not match its hash")
    else:
        write_new(backup, repair.original)
    if sha256(backup.read_bytes()) != report["inputSha256"]:
        raise FormatError("Backup verification failed")
    write_new(output, data)
    if sha256(output.read_bytes()) != report["outputSha256"]:
        raise FormatError("Output verification failed; retain the original and backup")
    report.update(outputFile=output.name, backupFile=str(Path("backups") / backup.name))
    write_new(receipt, (json.dumps(report, indent=2, allow_nan=False) + "\n").encode())
    return report
