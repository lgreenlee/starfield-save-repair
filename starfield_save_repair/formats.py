"""BCPS and version-153 change-form reader. Unknown save data remains opaque.

Format research and adapted layout logic: ReSaver++ (Apache-2.0), see NOTICE.
No game installation, executable, or third-party runtime is required.
"""
from dataclasses import dataclass
import struct
import zlib


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, data, offset=0):
        self.data, self.pos = data, offset

    def take(self, size):
        if size < 0 or self.pos < 0 or self.pos + size > len(self.data):
            raise FormatError(f"Truncated data at offset {self.pos}")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def number(self, size):
        return int.from_bytes(self.take(size), "little")

    def string(self):
        return self.take(self.number(2)).decode("utf-8", errors="strict")

    def count(self):
        if self.pos >= len(self.data):
            raise FormatError("Missing variable-length count")
        width = self.data[self.pos] & 3
        if width == 3:
            raise FormatError("Invalid variable-length count width")
        return self.number((1, 2, 4)[width]) >> 2

    def ref(self):
        return int.from_bytes(self.take(3), "big")


@dataclass
class Chunk:
    raw: bytes
    stored: bytes
    padding: bytes


class Container:
    MAX_SIZE = 512 * 1024 * 1024

    def __init__(self, file):
        self.file = file
        if len(file) < 72 or file[:4] != b"BCPS":
            raise FormatError("Expected a BCPS .sfs container")
        version = struct.unpack_from("<I", file, 4)[0]
        self.table, unknown, self.data_offset, total, maximum, self.chunk_size, self.alignment = struct.unpack_from("<7Q", file, 8)
        if version != 1 or file[68:72] != b"ZIP ":
            raise FormatError("Unsupported BCPS version or compression codec")
        if not 0 < total <= self.MAX_SIZE:
            raise FormatError("Decoded save exceeds the supported size limit")
        if not 65536 <= self.chunk_size <= self.MAX_SIZE or self.chunk_size & (self.chunk_size - 1):
            raise FormatError("Invalid BCPS chunk size")
        a = self.alignment
        if not 1 <= a <= 65536 or a & (a - 1) or unknown % a or self.data_offset % a or maximum < self.chunk_size:
            raise FormatError("Invalid BCPS header")
        count = (total + self.chunk_size - 1) // self.chunk_size
        if self.table < 72 or self.table + 4 * count > min(self.data_offset, 65536) or self.data_offset > len(file):
            raise FormatError("Invalid BCPS chunk table")
        self.chunks = []
        p = self.data_offset
        for i in range(count):
            size = struct.unpack_from("<I", file, self.table + 4 * i)[0]
            expected = min(self.chunk_size, total - i * self.chunk_size)
            end = p + size
            padded_end = p + self.align(size)
            if not 0 < size <= expected or padded_end > len(file):
                raise FormatError("Invalid or truncated BCPS chunk")
            stored = file[p:end]
            if size == expected:
                raw = stored
            else:
                decoder = zlib.decompressobj()
                try:
                    raw = decoder.decompress(stored, expected + 1)
                except zlib.error as exc:
                    raise FormatError("Invalid compressed chunk") from exc
                if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise FormatError("Chunk decompressed size/stream mismatch")
            self.chunks.append(Chunk(raw, stored, file[end:padded_end]))
            p = padded_end
        if p != len(file):
            raise FormatError("Unexpected trailing container bytes")
        self.inner = b"".join(c.raw for c in self.chunks)

    def align(self, size):
        return (size + self.alignment - 1) // self.alignment * self.alignment

    def replace(self, inner):
        if len(inner) != len(self.inner):
            raise FormatError("Only same-size targeted edits are supported")
        out = bytearray(self.file[:self.data_offset])
        for i, chunk in enumerate(self.chunks):
            raw = inner[i * self.chunk_size:(i + 1) * self.chunk_size]
            if raw == chunk.raw:
                stored, padding = chunk.stored, chunk.padding
            else:
                stored = zlib.compress(raw, 1)
                if len(stored) >= len(raw):
                    stored = raw
                count = self.align(len(stored)) - len(stored)
                padding = (b"padding\0" * ((count + 7) // 8))[:count]
            struct.pack_into("<I", out, self.table + i * 4, len(stored))
            out.extend(stored)
            out.extend(padding)
        encoded = bytes(out)
        if Container(encoded).inner != inner:
            raise FormatError("Repacked container failed readback")
        return encoded


@dataclass
class ChangeForm:
    form_id: int
    version: int
    flags: int
    refs: list
    data_offset: int
    data_size: int
    type_code: int = -1


class Save:
    def __init__(self, data):
        self.data = data
        r = Reader(data)
        if r.take(12) != b"SFS_SAVEGAME":
            raise FormatError("Expected SFS_SAVEGAME data")
        size = r.number(4)
        header = Reader(r.take(size))
        self.engine_version = header.number(4)
        self.save_version = header.number(1)
        if self.engine_version != 27 or self.save_version != 153:
            raise FormatError(f"Unsupported engine/save layout: {self.engine_version}/{self.save_version}; supported: 27/153")
        self.form_version = r.number(1)
        self.game_version, self.created_version = r.string(), r.string()
        plugins = Reader(r.take(r.number(4)))
        def group(width):
            count = plugins.number(width)
            if count > 4096:
                raise FormatError("Invalid plugin count")
            names = []
            for _ in range(count):
                names.append(plugins.string())
                creation = plugins.number(1)
                if creation not in (0, 1):
                    raise FormatError("Invalid creation flag")
                if creation:
                    plugins.string(); plugins.string(); plugins.string(); plugins.number(1)
            return names
        self.full_plugins, self.light_plugins, self.medium_plugins = group(1), group(2), group(4)
        if len(plugins.data) - plugins.pos == 2:
            plugins.take(2)
        if plugins.pos != len(plugins.data):
            raise FormatError("Unrecognized plugin list layout")
        self.flt = struct.unpack("<25I", r.take(100))
        ids_offset, unknown_offset, t1, t2, cf_offset, t3 = self.flt[:6]
        runs_offset = self.flt[11]
        if not r.pos <= t1 <= t2 <= cf_offset <= t3 <= ids_offset <= unknown_offset <= runs_offset < len(data):
            raise FormatError("Invalid section order/offsets")
        ids = Reader(data, ids_offset)
        count = ids.number(4)
        if count > 4000000 or ids.pos + 4 * count != unknown_offset:
            raise FormatError("Invalid form ID array")
        self.form_ids = struct.unpack(f"<{count}I", ids.take(count * 4))
        r = Reader(data, cf_offset)
        count = self.flt[9]
        if count > 2000000:
            raise FormatError("Too many change forms")
        self.forms = []
        for _ in range(count):
            fl = r.number(1)
            if fl & ~0x3B:
                raise FormatError("Unknown change-form header flags")
            version = r.number(1) if fl & 1 else self.save_version
            form_id = self.resolve_ref(r.ref())
            flags = r.number(4) if fl & 2 else 0x80008000
            refs = r.count() if fl & 8 else 0
            strings = r.count() if fl & 16 else 0
            length = r.count() if fl & 32 else 0
            if r.pos + refs * 3 + strings * 2 + length > t3:
                raise FormatError("Change form overlaps next section")
            references = [self.resolve_ref(r.ref()) for _ in range(refs)]
            r.take(strings * 2)
            self.forms.append(ChangeForm(form_id, version, flags, references, r.pos, length))
            r.take(length)
        if r.pos + self.flt[10] != t3:
            raise FormatError("Change forms do not end at table 3")
        runs = Reader(data, runs_offset)
        count = runs.count()
        if count > len(self.forms):
            raise FormatError("Invalid type-run count")
        index = 0
        for _ in range(count):
            code, length = runs.number(1), runs.count()
            if code >= 59 or not length or index + length > len(self.forms):
                raise FormatError("Invalid change-form type run")
            for cf in self.forms[index:index + length]:
                cf.type_code = code
            index += length
        if index != len(self.forms):
            raise FormatError("Incomplete change-form type list")

    def resolve_ref(self, value):
        kind, index = value >> 22, value & 0x3FFFFF
        if kind == 0:
            if index == 0:
                return 0
            if index > len(self.form_ids):
                raise FormatError("Reference outside form ID array")
            return self.form_ids[index - 1]
        if kind == 1:
            return index
        if kind == 2:
            return 0xFF000000 | index
        raise FormatError("Invalid packed reference")

    def plugin_form(self, plugin, local_id):
        matches = []
        for names, prefix, shift, mask in ((self.full_plugins, 0, 24, 0xFFFFFF), (self.light_plugins, 0xFE000000, 12, 0xFFF), (self.medium_plugins, 0xFD000000, 16, 0xFFFF)):
            for index, name in enumerate(names):
                if name.casefold() == plugin.casefold():
                    if not 0 < local_id <= mask:
                        raise FormatError("Local form ID exceeds plugin namespace")
                    matches.append(prefix | index << shift | local_id)
        if len(matches) != 1:
            raise FormatError("Target plugin absent or ambiguous")
        return matches[0]

    def find(self, form_id):
        matches = [cf for cf in self.forms if cf.form_id == form_id]
        if len(matches) != 1:
            raise FormatError("Target change form absent or duplicated")
        return matches[0]

    def position(self, cf):
        if cf.version != 153 or cf.type_code != 0 or cf.form_id >> 24 == 0xFF:
            raise FormatError("Only existing version-153 REFR positions are supported")
        # Initial type 6 (move cell / promoted) or 4 (move / physics).
        if not cf.flags & 0x200000E:
            raise FormatError("Reference has no supported saved position")
        r = Reader(self.data[cf.data_offset:cf.data_offset + cf.data_size])
        fl = r.number(1)
        if fl & ~0x1F or not cf.refs:
            raise FormatError("Unknown position flags or missing parent cell")
        position = struct.unpack("<3f", r.take(12))
        for bit in range(3):
            if fl & (1 << bit):
                r.take(4)
        if not fl & 0x18:
            r.take(1)
        if cf.flags & 0x2000008:
            if len(cf.refs) < 2:
                raise FormatError("Missing starting cell reference")
            r.take(4)
        return {"cellId": f"{cf.refs[0]:08X}", "position": list(position), "positionOffset": cf.data_offset + 1}
