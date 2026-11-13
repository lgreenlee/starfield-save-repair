"""Build a portable Windows folder; dependencies belong in an isolated venv."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from starfield_save_repair import __version__


def main():
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise RuntimeError("Build the Windows release with 64-bit Python on Windows.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True)
    output = ROOT / "build" / "windows"
    scratch = ROOT / "build" / "pyinstaller"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed",
               "--name", "StarfieldSaveRepair", "--noupx", "--paths", str(ROOT),
               "--add-data", str(ROOT / "starfield_save_repair" / "recipes") + ":starfield_save_repair/recipes",
               "--distpath", str(output), "--workpath", str(scratch), "--specpath", str(scratch),
               str(ROOT / "windows" / "launch_gui.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    bundle = output / "StarfieldSaveRepair"
    for name in ("LICENSE", "NOTICE"):
        shutil.copyfile(ROOT / name, bundle / name)
    shutil.copyfile(ROOT / "windows" / "START-HERE.txt", bundle / "START-HERE.txt")
    licenses = bundle / "licenses"
    licenses.mkdir(exist_ok=True)
    python_root = Path(sys.base_prefix)
    for source, name in ((python_root / "LICENSE.txt", "Python-LICENSE.txt"),
                         (ROOT / "windows" / "licenses" / "Tcl-license.terms", "Tcl-license.terms"),
                         (python_root / "tcl" / "tk8.6" / "license.terms", "Tk-license.terms")):
        if not source.is_file():
            raise RuntimeError("Missing bundled runtime license: " + name)
        shutil.copyfile(source, licenses / name)
    provenance = {"version": __version__, "pythonVersion": sys.version.split()[0],
                  "pyinstallerVersion": importlib.metadata.version("pyinstaller"),
                  "tclVersion": tkinter.Tcl().eval("info patchlevel"),
                  "platform": "windowsX64", "signed": False,
                  "sourceHashes": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted((ROOT / "starfield_save_repair").rglob("*"))
                                   if p.suffix in (".py", ".json")}}
    (bundle / "build-info.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Portable folder: " + str(bundle))


if __name__ == "__main__":
    main()
