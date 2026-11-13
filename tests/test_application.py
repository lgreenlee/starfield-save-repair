import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starfield_save_repair.application import create_repaired_slot, inspect_save, install_new, latest_save, next_slot
from starfield_save_repair.formats import FormatError
from starfield_save_repair.repair import Repair, load_recipe
from test_repair import save_fixture


class DesktopWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saves = self.root / "Saves with spaces"
        self.saves.mkdir()
        self.source = self.saves / "Autosave2_TEST_100000_20261113151918_136_13_4.sfs"
        self.original = save_fixture()
        self.source.write_bytes(self.original)
        self.work = self.root / "repair work"
        self.check = inspect_save(self.source)
        self.running = patch("starfield_save_repair.application.starfield_running", return_value=False).start()
        self.addCleanup(patch.stopall)

    def create(self):
        return create_repaired_slot(self.source, self.check["inputSha256"], self.work)

    def test_full_workflow_adds_valid_slot_and_keeps_backup_outside_saves(self):
        result = self.create()
        output = Path(result["installedPath"])
        self.assertEqual(output.name, "Save1_TEST_100000_20261113151918_136_13_4.sfs")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(Path(result["backupPath"]).read_bytes(), self.original)
        self.assertTrue(Path(result["backupPath"]).is_relative_to(self.work))
        self.assertFalse((self.saves / "backups").exists())
        self.assertEqual(Repair(output.read_bytes(), load_recipe()).status, "alreadyAtDesiredPosition")
        self.assertEqual(json.loads(Path(result["receiptPath"]).read_text()), result["receipt"])
        self.assertEqual(set(p.suffix for p in self.saves.iterdir()), {".sfs"})

    def test_running_game_blocks_all_writes(self):
        self.running.return_value = True
        with self.assertRaisesRegex(FormatError, "quit Starfield"):
            self.create()
        self.assertFalse(self.work.exists())
        self.assertEqual(list(self.saves.iterdir()), [self.source])

    def test_game_starts_during_repair_keeps_candidate_private(self):
        self.running.side_effect = [False, True]
        with self.assertRaisesRegex(FormatError, "started during"):
            self.create()
        self.assertEqual(list(self.saves.iterdir()), [self.source])
        self.assertTrue(list(self.work.rglob("*.sfs")))

    def test_changed_save_requires_reinspection(self):
        changed = save_fixture(position=(-6e11, 1.5e12, 3e9))
        self.source.write_bytes(changed)
        with self.assertRaisesRegex(FormatError, "changed after"):
            self.create()
        self.assertEqual(self.source.read_bytes(), changed)
        self.assertFalse(self.work.exists())

    def test_save_changes_during_candidate_build_never_installs_it(self):
        from starfield_save_repair.repair import write_repair
        def changed(*args):
            result = write_repair(*args)
            self.source.write_bytes(save_fixture(position=(-6e11, 1.5e12, 3e9)))
            return result
        with patch("starfield_save_repair.application.write_repair", side_effect=changed):
            with self.assertRaisesRegex(FormatError, "original save changed"):
                self.create()
        self.assertEqual(list(self.saves.iterdir()), [self.source])

    def test_no_write_when_station_already_restored(self):
        candidate, _ = Repair(self.original, load_recipe()).candidate()
        self.source.write_bytes(candidate)
        self.check = inspect_save(self.source)
        with self.assertRaisesRegex(FormatError, "alreadyAtDesiredPosition"):
            self.create()
        self.assertFalse(self.work.exists())

    def test_slot_allocation_keeps_every_existing_save(self):
        old = self.saves / "Save250_OTHER_1.sfs"
        old.write_bytes(b"older save")
        number, path = next_slot(self.source)
        self.assertEqual(number, 251)
        self.assertTrue(path.name.startswith("Save251_TEST_"))
        self.create()
        self.assertEqual(old.read_bytes(), b"older save")

    def test_unknown_filename_cannot_be_installed_as_a_game_slot(self):
        renamed = self.source.with_name("my copy.sfs")
        self.source.rename(renamed)
        with self.assertRaisesRegex(FormatError, "original Starfield filename"):
            create_repaired_slot(renamed, self.check["inputSha256"], self.work)
        self.assertFalse(self.work.exists())

    def test_read_only_inspection_and_no_saves_found(self):
        self.assertEqual(self.check["status"], "eligible")
        self.assertFalse(self.check["writesPerformed"])
        self.assertEqual(latest_save(self.saves), self.source)
        self.assertIsNone(latest_save(self.root / "missing"))
        self.assertFalse(self.work.exists())

    def test_install_refuses_existing_file_and_leaves_no_temporary_file(self):
        target = self.saves / "Save99_TEST.sfs"
        target.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            install_new(b"candidate", target)
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertFalse(list(self.saves.glob("*.tmp")))

    def test_destination_created_during_repair_is_not_overwritten(self):
        from starfield_save_repair.repair import write_repair
        _, target = next_slot(self.source)
        def colliding(*args):
            result = write_repair(*args)
            target.write_bytes(b"another writer")
            return result
        with patch("starfield_save_repair.application.write_repair", side_effect=colliding):
            with self.assertRaises(FileExistsError): self.create()
        self.assertEqual(target.read_bytes(), b"another writer")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_both_filename_conventions_preserve_character_identifiers(self):
        for name in ("Save249_ABCDEF01_50696C6F74_141120_20261110145155_135_13_4.sfs",
                     "Quicksave0_ABCDEF01M50696C6F74_151832_20261113002608_135_13_4.sfs"):
            number, target = next_slot(self.saves / name)
            self.assertEqual(target.name.split("_", 1)[1], name.split("_", 1)[1])
            self.assertGreaterEqual(number, 1)
