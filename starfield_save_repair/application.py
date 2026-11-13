"""Desktop workflow: inspect first, back up, then add a separate game save slot."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from .formats import FormatError
from .repair import Repair, load_recipe, sha256, write_new, write_repair
from .windows import repair_directory, starfield_running

SAVE_NAME = re.compile(r"^(?:Save\d+|Autosave\d+|Quicksave\d+|Exitsave\d*)_([A-Za-z0-9_]+)\.sfs$", re.IGNORECASE)


def latest_save(folder):
    return max((p for p in Path(folder).glob("*.sfs") if p.is_file()),
               key=lambda p: p.stat().st_mtime_ns, default=None)


def inspect_save(path):
    path = Path(path)
    if path.suffix.casefold() != ".sfs" or not path.is_file():
        raise FormatError("Choose a Starfield .sfs save file.")
    report = Repair(path.read_bytes(), load_recipe()).report()
    report["fileName"] = path.name
    report["writesPerformed"] = False
    return report


def next_slot(source):
    source = Path(source)
    match = SAVE_NAME.fullmatch(source.name)
    if not match:
        raise FormatError("Use a save with its original Starfield filename (Save, Autosave, Quicksave or Exitsave).")
    numbers = []
    for path in source.parent.glob("*.sfs"):
        slot = re.match(r"^Save(\d+)_", path.name, re.IGNORECASE)
        if slot:
            numbers.append(int(slot.group(1)))
    number = max(numbers, default=0) + 1
    return number, source.with_name(f"Save{number}_{match.group(1)}.sfs")


def install_new(data, target):
    """Stage in the destination folder; publish a complete file without overwrite."""
    target = Path(target)
    fd, temporary = tempfile.mkstemp(prefix=".starfield-repair-", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            # Windows rename refuses an existing destination, including a link.
            os.rename(temporary, target)
        else:
            os.link(temporary, target)  # POSIX rename would overwrite.
    finally:
        # Only our uniquely created temporary file is removed.
        if temporary.exists():
            temporary.unlink()


def create_repaired_slot(source, expected_hash, work_root=None):
    source = Path(source)
    if starfield_running():
        raise FormatError("Save and quit Starfield before creating a repaired save.")
    if sha256(source.read_bytes()) != expected_hash:
        raise FormatError("This save changed after it was checked. Check the save again.")
    number, destination = next_slot(source)
    work_root = Path(work_root) if work_root else repair_directory()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work = work_root / (stamp + "-" + uuid.uuid4().hex[:8])
    candidate = work / destination.name
    receipt = write_repair(source, candidate, load_recipe())
    if receipt["inputSha256"] != expected_hash or sha256(source.read_bytes()) != expected_hash:
        raise FormatError("The original save changed. No test slot was installed; check the latest save again.")
    if starfield_running():
        raise FormatError("Starfield started during repair. The backup is safe; close the game and try again.")
    data = candidate.read_bytes()
    if sha256(data) != receipt["outputSha256"]:
        raise FormatError("Candidate verification failed. No test slot was installed.")
    install_new(data, destination)
    if sha256(destination.read_bytes()) != receipt["outputSha256"]:
        raise FormatError("Installed copy did not verify. Keep the original; do not load the new test slot.")
    receipt.update(testSlot=number, installedFile=destination.name, sourceFile=source.name,
                   installedAt=datetime.now(timezone.utc).isoformat())
    installation = work / "installation.json"
    write_new(installation, (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode())
    return {"receipt": receipt, "installedPath": str(destination), "workDirectory": str(work),
            "backupPath": str(work / receipt["backupFile"]), "receiptPath": str(installation)}
