# Windows portable build

Build on 64-bit Windows with Python 3.12 and Tcl/Tk installed. The tested build
uses Python 3.12.10, Tcl/Tk 8.6.15 and PyInstaller 6.22.3. Build dependencies are
pinned in `requirements-build.txt`; they are separate from the dependency-free
repair engine. No network access is used by the finished app.

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-build\Scripts\python.exe scripts/build_windows.py
.\.venv-build\Scripts\python.exe scripts/package_release.py --windows
```

`build_windows.py` first runs the tests. It creates a PyInstaller one-folder,
windowed application at `build/windows/StarfieldSaveRepair`, including the repair
recipe and Python/Tk runtime. It copies project and runtime license notices, and
records version, build-tool versions and public module hashes in `build-info.json`.
The Tcl notice is from the official
[Tcl 8.6.15 source](https://github.com/tcltk/tcl/blob/core-8-6-15/license.terms).
Update it if using a different runtime. Python and Tk notices come from the local
Python distribution; a missing notice stops the build.

The bundle format follows
[PyInstaller's one-folder deployment](https://pyinstaller.org/en/stable/operating-mode.html).
Bundling includes the runtime; users do not install Python. The app loads its
recipe relative to its packaged module, using
[PyInstaller's documented resource layout](https://pyinstaller.org/en/stable/runtime-information.html).
No custom bootloader or altered third-party runtime is included.

The packager verifies source hashes before bundling the Windows folder, refuses
private save/credential/database files, and checks ZIP integrity. Existing release
archives are never overwritten; use a fresh `--output-dir` for a test package.
The source ZIP includes the GUI, CLI, tests, recipe, notices and build scripts.

Before publishing, launch an extracted copy from a path containing spaces, inspect
and repair a synthetic save, check original/backup hashes and the new slot, then
inspect that slot again to confirm the no-op case. Run without relying on the
build virtual environment. Do not include real player saves or private reports.

The generated EXE is unsigned. Signing and public hosting are separate release
operations; this build does not change Windows security settings.
