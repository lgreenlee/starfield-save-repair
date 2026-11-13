import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_packager", ROOT / "scripts/package_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PackagingTests(unittest.TestCase):
    def test_source_allowlist_contains_runtime_and_build_files_only(self):
        names = {p.relative_to(ROOT).as_posix() for p in release.source_files()}
        self.assertIn("starfield_save_repair/gui.py", names)
        self.assertIn("starfield_save_repair/recipes/anchorpoint-position.json", names)
        self.assertIn("windows/launch_gui.py", names)
        self.assertIn("windows/licenses/Tcl-license.terms", names)
        self.assertIn("requirements-build.txt", names)
        self.assertFalse(any(n.startswith((".private/", ".research/", ".venv-build/", "build/", "dist/")) for n in names))

    def test_archive_and_checksum_match_public_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "public.txt"
            content.write_text("public source")
            archive = root / "release.zip"
            release.package([content], root, archive, "project")
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(zipped.namelist(), ["project/public.txt"])
                self.assertEqual(zipped.read("project/public.txt"), content.read_bytes())
            self.assertEqual(archive.with_suffix(".sha256").read_text().split()[0], hashlib.sha256(archive.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError): release.package([content], root, archive, "project")

    def test_private_save_and_credential_files_are_rejected_before_zip_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("player.sfs", "token.dpapi", "observations.sqlite3", "trace.jsonl"):
                private = root / name
                private.write_bytes(b"private")
                with self.assertRaisesRegex(RuntimeError, "Private data"):
                    release.package([private], root, root / "release.zip", "project")
                self.assertFalse((root / "release.zip").exists())

    def test_file_outside_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "public"
            base.mkdir()
            outside = root / "secret.txt"
            outside.write_text("private")
            with self.assertRaisesRegex(RuntimeError, "outside"):
                release.package([outside], base, root / "release.zip", "project")
