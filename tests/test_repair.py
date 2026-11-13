import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from starfield_save_repair.formats import Container, FormatError, Save
from starfield_save_repair.repair import Repair, load_recipe, write_repair


def count(n):
    if n < 64:
        return bytes([n << 2])
    if n < 16384:
        return struct.pack("<H", (n << 2) | 1)
    return struct.pack("<I", (n << 2) | 2)


def string(s):
    data = s.encode()
    return struct.pack("<H", len(data)) + data


def container(inner, stored=False):
    chunk_size, alignment = 65536, 16
    chunks = [inner[i:i + chunk_size] for i in range(0, len(inner), chunk_size)]
    encoded = []
    for raw in chunks:
        compressed = zlib.compress(raw)
        encoded.append(raw if stored or len(compressed) >= len(raw) else compressed)
    offset = (72 + 4 * len(chunks) + 15) // 16 * 16
    header = bytearray(offset)
    header[:4] = b"BCPS"
    struct.pack_into("<I7Q", header, 4, 1, 72, 65536, offset, len(inner), 2**32, chunk_size, alignment)
    header[64:72] = b"\x01\0\0\0ZIP "
    for i, chunk in enumerate(encoded):
        struct.pack_into("<I", header, 72 + i * 4, len(chunk))
        header.extend(chunk)
        header.extend(b"\0" * ((-len(chunk)) % alignment))
    return bytes(header)


def save_fixture(position=(-5e11, 1.4e12, 2e9), plugin_index=2, cell=0x032DFF,
                 version=153, flags=2, type_code=0, duplicate=False):
    names = [f"Other{i}.esm" for i in range(plugin_index)] + ["SFBGS00D.esm"]
    plugins = bytes([len(names)]) + b"".join(string(n) + b"\0" for n in names) + b"\0" * 8
    header = struct.pack("<IB", 27, version)
    prefix = b"SFS_SAVEGAME" + struct.pack("<I", len(header)) + header + bytes([version])
    prefix += string("1.16.244.0") + string("1.0") + struct.pack("<I", len(plugins)) + plugins
    body = b"\x08" + struct.pack("<3f", *position) + b"opaque-data-kept-exactly"
    # Header flags: explicit change flags, references, body. Packed references
    # are indices into the form ID array, not runtime form IDs.
    cf = b"\x2a\0\0\x01" + struct.pack("<I", flags) + count(1) + count(len(body)) + b"\0\0\x02" + body
    records = cf * (2 if duplicate else 1)
    cf_offset = len(prefix) + 100
    ids_offset = cf_offset + len(records)
    form_id, cell_id = plugin_index << 24 | 0x064B7D, plugin_index << 24 | cell
    ids = struct.pack("<3I", 2, form_id, cell_id)
    unknown_offset = ids_offset + len(ids)
    runs_offset = unknown_offset + 4
    flt = [0] * 25
    flt[:6] = [ids_offset, unknown_offset, cf_offset, cf_offset, cf_offset, ids_offset]
    flt[9], flt[11] = (2 if duplicate else 1), runs_offset
    inner = prefix + struct.pack("<25I", *flt) + records + ids + b"\0" * 4
    inner += count(1) + bytes([type_code]) + count(flt[9]) + b"unparsed-tail-preserved"
    return container(inner)


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.recipe = load_recipe()

    def test_only_coordinate_bytes_change(self):
        original = save_fixture()
        repair = Repair(original, self.recipe)
        candidate, report = repair.candidate()
        before, after = Container(original).inner, Container(candidate).inner
        self.assertEqual(len(before), len(after))
        changed = [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
        self.assertTrue(changed)
        self.assertTrue(all(repair.offset <= i < repair.offset + 12 for i in changed))
        self.assertTrue(report["unrelatedDecodedBytesUnchanged"])
        self.assertFalse(report["gameValidated"])
        self.assertEqual(Repair(candidate, self.recipe).status, "alreadyAtDesiredPosition")

    def test_load_order_independent(self):
        for index in (0, 1, 7):
            repair = Repair(save_fixture(plugin_index=index), self.recipe)
            self.assertEqual(repair.form.form_id, index << 24 | 0x064B7D)
            repair.candidate()

    def test_identity_container_roundtrip(self):
        raw = save_fixture()
        c = Container(raw)
        self.assertEqual(c.replace(c.inner), raw)

    def test_untouched_compressed_chunks_remain_identical(self):
        c = Container(container(b"a" * 65536 + b"b" * 65536 + b"c" * 12))
        replacement = c.inner[:65536] + b"X" + c.inner[65537:]
        rebuilt = Container(c.replace(replacement))
        self.assertEqual(rebuilt.chunks[0], c.chunks[0])
        self.assertEqual(rebuilt.chunks[2], c.chunks[2])
        self.assertEqual(rebuilt.inner, replacement)

    def test_stored_chunks(self):
        c = Container(container(b"abcd" * 19000, stored=True))
        self.assertEqual(c.replace(c.inner), c.file)
        self.assertEqual(Container(c.replace(b"x" + c.inner[1:])).inner[0], ord("x"))

    def test_refuses_size_changes(self):
        c = Container(save_fixture())
        with self.assertRaises(FormatError):
            c.replace(c.inner + b"x")

    def test_refuses_other_cell(self):
        with self.assertRaisesRegex(FormatError, "different cell"):
            Repair(save_fixture(cell=1), self.recipe)

    def test_refuses_duplicate_forms(self):
        with self.assertRaisesRegex(FormatError, "duplicated"):
            Repair(save_fixture(duplicate=True), self.recipe)

    def test_refuses_actor(self):
        with self.assertRaisesRegex(FormatError, "REFR"):
            Repair(save_fixture(type_code=1), self.recipe)

    def test_refuses_unmoved_record(self):
        with self.assertRaisesRegex(FormatError, "saved position"):
            Repair(save_fixture(flags=0), self.recipe)

    def test_refuses_unknown_version(self):
        with self.assertRaisesRegex(FormatError, "Unsupported"):
            Repair(save_fixture(version=152), self.recipe)

    def test_refuses_nonfinite_position(self):
        with self.assertRaisesRegex(FormatError, "Non-finite"):
            Repair(save_fixture(position=(float("nan"), 0, 0)), self.recipe)

    def test_threshold(self):
        r = Repair(save_fixture(position=(1, 2, 3)), self.recipe)
        self.assertEqual(r.status, "belowDisplacementThreshold")
        with self.assertRaises(FormatError):
            r.candidate()

    def test_noop_refused(self):
        r = Repair(save_fixture(position=self.recipe["position"]), self.recipe)
        with self.assertRaisesRegex(FormatError, "alreadyAtDesiredPosition"):
            r.candidate()

    def test_truncation(self):
        raw = save_fixture()
        for end in (0, 4, 71, len(raw) - 1):
            with self.assertRaises(FormatError):
                Container(raw[:end])

    def test_trailing_bytes(self):
        with self.assertRaisesRegex(FormatError, "trailing"):
            Container(save_fixture() + b"x")

    def test_bad_header(self):
        for offset, value in ((4, 9), (48, 123), (56, 3), (8, 0), (32, 2**40)):
            bad = bytearray(save_fixture())
            struct.pack_into("<Q" if offset != 4 else "<I", bad, offset, value)
            with self.assertRaises(FormatError):
                Container(bytes(bad))

    def test_bad_zlib(self):
        raw = bytearray(save_fixture())
        offset = struct.unpack_from("<Q", raw, 24)[0]
        raw[offset] ^= 255
        with self.assertRaises(FormatError):
            Container(bytes(raw))

    def test_invalid_form_reference(self):
        c = Container(save_fixture());s = Save(c.inner)
        with self.assertRaises(FormatError):
            s.resolve_ref(123456)
        with self.assertRaises(FormatError):
            s.resolve_ref(0xC00000)

    def test_unsupported_recipe(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "recipe.json"
            for field, value in (("operation", "deleteRecord"), ("position", [0, 1]), ("position", [0, 0, float("inf")]), ("minimumDisplacement", -1), ("supportedSaveVersions", [999])):
                recipe = copy.deepcopy(self.recipe);recipe[field] = value
                p.write_text(json.dumps(recipe))
                with self.assertRaises(FormatError):
                    load_recipe(p)

    def test_file_backup_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / "source.sfs", Path(td) / "candidate.sfs"
            original = save_fixture();source.write_bytes(original)
            report = write_repair(source, output, self.recipe)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual((Path(td) / report["backupFile"]).read_bytes(), original)
            self.assertEqual(json.loads(output.with_suffix(".repair.json").read_text()), report)
            with self.assertRaises(FormatError):
                write_repair(source, output, self.recipe)

    def test_refuses_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.sfs";p.write_bytes(save_fixture())
            with self.assertRaises(FormatError):
                write_repair(p, p, self.recipe)

    def test_no_output_for_ineligible_save(self):
        with tempfile.TemporaryDirectory() as td:
            p, out = Path(td) / "input.sfs", Path(td) / "out.sfs"
            p.write_bytes(save_fixture(position=(0, 0, 0)))
            with self.assertRaises(FormatError):
                write_repair(p, out, self.recipe)
            self.assertFalse(out.exists())
            self.assertFalse((Path(td) / "backups").exists())


if __name__ == "__main__":
    unittest.main()
