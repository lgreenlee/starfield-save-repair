# Supported format and validation boundaries

The reader accepts BCPS version 1, ZIP codec, power-of-two chunks of at least
64 KiB, a bounded alignment and a decoded size no larger than 512 MiB. Stored
chunks (compressed size equals decoded size) are supported. Lengths, table
bounds, zlib EOF, and trailing compressed data are checked. Unmodified chunks
and their padding remain byte-identical on output.

The decoded stream is `SFS_SAVEGAME`, engine 27, header save version 153. The
version-153 plugin list includes creation flags and full/light/medium groups.
The file-location table has 25 uint32 fields. Change forms have separate packed
reference and string lists; their type codes are assigned by a later run table.
The reader parses those structures, while retaining global data and other
sections as opaque bytes. It is not a complete semantic validator of a save.

Packed references are three-byte big-endian values, with two type bits and a
22-bit value. Form-index references resolve through the save's form ID array;
default and created references use the corresponding namespaces.

For version-153 placed REFR records, initial position is selected by change flags
`0x02000008` (type 6) or `0x6` (type 4). Position consists of a flag byte, a cell
reference in the separate reference list, three float32 values, optional rotation
values, and optional additional state. Only the three position values are changed.
The unparsed remainder of the record is retained byte-for-byte.

This layout was cross-referenced with ReSaver++ revision
`61f69a87b3d21a1a37b6aeeaf2dda07c4e71074b` and checked against an affected
Starfield 1.16.244.0 save: the decoded record's position exactly matched live
read-only reference inspection. The repair changes 12 decoded bytes and leaves
all other decoded bytes identical. This is structural evidence only; a surviving
attachment/script could still reapply the problem after loading.

The tool never deletes change forms, drops flags, transplants records between
saves, or tries to reinterpret an unknown version. Byte-level preservation does
not imply that every cross-reference or game system is healthy.
