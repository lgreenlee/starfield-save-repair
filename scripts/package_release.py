"""Package public source and the optional portable Windows build."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from starfield_save_repair import __version__


def source_files():
    files = [ROOT / p for p in ("README.md", "LICENSE", "NOTICE", "pyproject.toml", ".gitignore", "requirements-build.txt")]
    for directory, suffixes in (("starfield_save_repair", {".py", ".json"}), ("tests", {".py"}),
                                ("docs", {".md"}), ("scripts", {".py"}), ("windows", {".py", ".txt", ".terms"})):
        files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and p.suffix in suffixes
                     and "__pycache__" not in p.parts)
    return files


def package(files, base, archive, prefix):
    names = []
    forbidden = {".sfs", ".dpapi", ".sqlite", ".sqlite3", ".db", ".jsonl", ".raw", ".bak"}
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()) or not path.is_file():
            raise RuntimeError("Release input is outside its public folder")
        relative = path.relative_to(base)
        if path.suffix.casefold() in forbidden or any(p.startswith((".private", ".research", ".venv")) for p in relative.parts):
            raise RuntimeError("Private data in release input")
        names.append((path, (Path(prefix) / relative).as_posix()))
    if archive.exists() or archive.with_suffix(".sha256").exists():
        raise FileExistsError("Release already exists; use a new version or --output-dir")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path, name in sorted(names):
            zipped.write(path, name)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert set(zipped.namelist()) == {name for _, name in names}
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(json.dumps({"file": archive.name, "files": len(files), "bytes": archive.stat().st_size, "sha256": digest}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", action="store_true", help="Also package build/windows/StarfieldSaveRepair")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.windows:
        bundle = ROOT / "build" / "windows" / "StarfieldSaveRepair"
        if not (bundle / "StarfieldSaveRepair.exe").is_file():
            raise RuntimeError("Run scripts/build_windows.py first")
        provenance = json.loads((bundle / "build-info.json").read_text())
        assert provenance["version"] == __version__
        for name, expected in provenance["sourceHashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, "Rebuild after source changes"
        package([p for p in bundle.rglob("*") if p.is_file()], bundle,
                args.output_dir / f"starfield-save-repair-{__version__}-windows-x64.zip", "StarfieldSaveRepair")
    package(source_files(), ROOT, args.output_dir / f"starfield-save-repair-{__version__}-source.zip", "starfield-save-repair")


if __name__ == "__main__":
    main()
