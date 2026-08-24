#!/usr/bin/env python3
"""Inspect and byte-preservingly rebuild Heroes II H2C/MP2 map files.

The original H2C campaign maps use the same container layout as MP2 maps.
This tool intentionally implements only the container boundaries needed for a
safe no-op round trip and for resizing confirmed tail strings in information
blocks.  It does not try to decode tiles, addons, castles, or heroes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAP_INFO_SIZE = 428
TILE_SIZE = 20
ADDON_SIZE = 15
CASTLE_COUNT = 72
CASTLE_POSITION_SIZE = 3
CAPTURE_OBJECT_COUNT = 144
CAPTURE_OBJECT_POSITION_SIZE = 3
UID_SIZE = 4


class H2CFormatError(ValueError):
    """Raised when a file does not match the supported H2C/MP2 container."""


@dataclass
class InfoBlock:
    index: int
    prefix_offset: int
    data_offset: int
    data: bytearray


@dataclass(frozen=True)
class TextField:
    field_id: str
    kind: str
    absolute_offset: int
    block_index: int | None
    relative_offset: int | None
    byte_length: int
    capacity: int | None
    resizable: bool
    raw: bytes
    confidence: str

    @property
    def text(self) -> str:
        return self.raw.decode("latin-1")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.field_id,
            "kind": self.kind,
            "absolute_offset": self.absolute_offset,
            "absolute_offset_hex": f"0x{self.absolute_offset:X}",
            "block_index": self.block_index,
            "relative_offset": self.relative_offset,
            "relative_offset_hex": (
                None if self.relative_offset is None else f"0x{self.relative_offset:X}"
            ),
            "byte_length": self.byte_length,
            "capacity": self.capacity,
            "resizable": self.resizable,
            "confidence": self.confidence,
            "text_latin1": self.text,
            "raw_hex": self.raw.hex(" "),
        }


@dataclass
class H2CMap:
    source_path: Path
    source_size: int
    source_sha256: str
    width: int
    height: int
    tile_end: int
    addon_count: int
    addon_end: int
    obelisk_offset: int
    count_stream_offset: int
    count_stream: bytes
    block_start: int
    prefix: bytearray
    blocks: list[InfoBlock]
    uid_tail: bytes

    def rebuild(self) -> bytes:
        output = bytearray(self.prefix)
        for block in self.blocks:
            if len(block.data) > 0xFFFF:
                raise H2CFormatError(
                    f"information block {block.index} exceeds uint16: {len(block.data)}"
                )
            output.extend(struct.pack("<H", len(block.data)))
            output.extend(block.data)
        output.extend(self.uid_tail)
        return bytes(output)

    def fields(self) -> list[TextField]:
        fields: list[TextField] = []

        # These fixed offsets and capacities are part of the original MP2 map
        # info header.  Extra printable runs are reported for research, but are
        # not resizable because the header remains exactly 428 bytes.
        fields.extend(
            _fixed_region_fields(
                self.prefix,
                region_offset=58,
                region_size=16,
                id_prefix="header.name",
                kind="header_fixed_c_string",
            )
        )
        fields.extend(
            _fixed_region_fields(
                self.prefix,
                region_offset=118,
                region_size=200,
                id_prefix="header.description",
                kind="header_fixed_c_string",
            )
        )

        current_prefix = self.block_start
        for block in self.blocks:
            data_offset = current_prefix + 2
            raw = bytes(block.data)
            recognized: set[tuple[int, int]] = set()

            # Confirmed by the original MP2 loader: pblock[0] == 0 and
            # pblock[42] == 1 denotes a daily event.  The fixed event header is
            # 49 bytes in the two campaign originals, and its NUL-terminated
            # message occupies the tail.  This tail is safe to resize together
            # with the block's uint16 length prefix.
            if len(raw) >= 50 and raw[0] == 0 and raw[42] == 1:
                message = _tail_c_string(raw, 49)
                if message is not None:
                    fields.append(
                        TextField(
                            field_id=f"block.{block.index}.daily_event",
                            kind="daily_event_tail_c_string",
                            absolute_offset=data_offset + 49,
                            block_index=block.index,
                            relative_offset=49,
                            byte_length=len(message),
                            capacity=None,
                            resizable=True,
                            raw=message,
                            confidence="confirmed",
                        )
                    )
                    recognized.add((49, len(message)))

            # Confirmed rumor layout from the original loader is 8 fixed bytes
            # followed by a NUL-terminated tail.  Empty rumors are ignored.
            if len(raw) >= 9 and raw[0] == 0 and not (len(raw) >= 43 and raw[42] == 1):
                rumor = _tail_c_string(raw, 8)
                if rumor:
                    fields.append(
                        TextField(
                            field_id=f"block.{block.index}.rumor",
                            kind="rumor_tail_c_string",
                            absolute_offset=data_offset + 8,
                            block_index=block.index,
                            relative_offset=8,
                            byte_length=len(rumor),
                            capacity=None,
                            resizable=True,
                            raw=rumor,
                            confidence="confirmed",
                        )
                    )
                    recognized.add((8, len(rumor)))

            # Report other ASCII-looking NUL-terminated strings as research
            # candidates only.  Their enclosing object type is not decoded, so
            # resizing them would be unsafe (for example, castle blocks must
            # remain exactly 70 bytes).
            candidate_number = 0
            for relative, value in _scan_ascii_c_strings(raw):
                if (relative, len(value)) in recognized:
                    continue
                fields.append(
                    TextField(
                        field_id=f"block.{block.index}.candidate.{candidate_number}",
                        kind="unclassified_fixed_c_string",
                        absolute_offset=data_offset + relative,
                        block_index=block.index,
                        relative_offset=relative,
                        byte_length=len(value),
                        capacity=len(value) + 1,
                        resizable=False,
                        raw=value,
                        confidence="heuristic",
                    )
                )
                candidate_number += 1

            current_prefix = data_offset + len(raw)

        return fields

    def replace_resizable_field(self, field_id: str, replacement: bytes) -> TextField:
        matches = [field for field in self.fields() if field.field_id == field_id]
        if not matches:
            raise KeyError(f"text field not found: {field_id}")
        if len(matches) != 1:
            raise H2CFormatError(f"text field ID is ambiguous: {field_id}")

        field = matches[0]
        if not field.resizable or field.block_index is None or field.relative_offset is None:
            raise H2CFormatError(
                f"field is not proven safe to resize: {field_id} ({field.kind})"
            )
        if b"\x00" in replacement:
            raise ValueError("replacement payload must not contain NUL")

        block = self.blocks[field.block_index]
        start = field.relative_offset
        terminator = start + field.byte_length
        if terminator >= len(block.data) or block.data[terminator] != 0:
            raise H2CFormatError(f"field terminator moved unexpectedly: {field_id}")
        if terminator + 1 != len(block.data):
            raise H2CFormatError(f"resizable field is no longer at block tail: {field_id}")

        block.data = block.data[:start] + bytearray(replacement) + bytearray(b"\x00")
        return field

    def manifest(self) -> dict[str, object]:
        uid = struct.unpack("<I", self.uid_tail)[0]
        return {
            "format": "Heroes II original H2C/MP2",
            "source": str(self.source_path),
            "source_size": self.source_size,
            "source_sha256": self.source_sha256,
            "width": self.width,
            "height": self.height,
            "tile_end": self.tile_end,
            "tile_end_hex": f"0x{self.tile_end:X}",
            "addon_count": self.addon_count,
            "addon_end": self.addon_end,
            "addon_end_hex": f"0x{self.addon_end:X}",
            "obelisk_offset": self.obelisk_offset,
            "obelisk_offset_hex": f"0x{self.obelisk_offset:X}",
            "count_stream_offset": self.count_stream_offset,
            "count_stream_offset_hex": f"0x{self.count_stream_offset:X}",
            "count_stream_hex": self.count_stream.hex(" "),
            "block_start": self.block_start,
            "block_start_hex": f"0x{self.block_start:X}",
            "info_block_count": len(self.blocks),
            "blocks": [
                {
                    "index": block.index,
                    "prefix_offset": block.prefix_offset,
                    "prefix_offset_hex": f"0x{block.prefix_offset:X}",
                    "data_offset": block.data_offset,
                    "data_offset_hex": f"0x{block.data_offset:X}",
                    "size": len(block.data),
                    "sha256": hashlib.sha256(block.data).hexdigest(),
                }
                for block in self.blocks
            ],
            "last_object_uid": uid,
            "fields": [field.to_dict() for field in self.fields()],
        }


def _u32(data: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise H2CFormatError(f"uint32 outside file at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def _tail_c_string(data: bytes, offset: int) -> bytes | None:
    if offset >= len(data) or data[-1] != 0 or b"\x00" in data[offset:-1]:
        return None
    return data[offset:-1]


def _is_ascii_text_byte(value: int) -> bool:
    return value in (9, 10, 13) or 0x20 <= value <= 0x7E


def _scan_ascii_c_strings(data: bytes | bytearray, minimum_length: int = 4) -> Iterable[tuple[int, bytes]]:
    index = 0
    while index < len(data):
        if not _is_ascii_text_byte(data[index]):
            index += 1
            continue
        start = index
        while index < len(data) and _is_ascii_text_byte(data[index]):
            index += 1
        if index < len(data) and data[index] == 0 and index - start >= minimum_length:
            yield start, bytes(data[start:index])
        index += 1


def _fixed_region_fields(
    prefix: bytes | bytearray,
    region_offset: int,
    region_size: int,
    id_prefix: str,
    kind: str,
) -> list[TextField]:
    region = prefix[region_offset : region_offset + region_size]
    fields: list[TextField] = []
    for number, (relative, value) in enumerate(_scan_ascii_c_strings(region, minimum_length=1)):
        fields.append(
            TextField(
                field_id=f"{id_prefix}.{number}",
                kind=kind,
                absolute_offset=region_offset + relative,
                block_index=None,
                relative_offset=relative,
                byte_length=len(value),
                capacity=None,
                resizable=False,
                raw=value,
                confidence="confirmed" if number == 0 else "heuristic",
            )
        )
    return fields


def parse_h2c(path: Path) -> H2CMap:
    data = path.read_bytes()
    if len(data) < MAP_INFO_SIZE + UID_SIZE:
        raise H2CFormatError(f"file is too small: {len(data)} bytes")
    if data[:4] != b"\x5c\x00\x00\x00":
        raise H2CFormatError(f"invalid H2C/MP2 magic: {data[:4].hex(' ')}")

    width = _u32(data, MAP_INFO_SIZE - 8)
    height = _u32(data, MAP_INFO_SIZE - 4)
    if width not in (36, 72, 108, 144) or height != width:
        raise H2CFormatError(f"unsupported map dimensions: {width}x{height}")

    tile_end = MAP_INFO_SIZE + width * height * TILE_SIZE
    addon_count = _u32(data, tile_end)
    addon_end = tile_end + 4 + addon_count * ADDON_SIZE
    fixed_tables_end = (
        addon_end
        + CASTLE_COUNT * CASTLE_POSITION_SIZE
        + CAPTURE_OBJECT_COUNT * CAPTURE_OBJECT_POSITION_SIZE
    )
    if fixed_tables_end + 3 + UID_SIZE > len(data):
        raise H2CFormatError("addon or fixed-position tables extend beyond file")

    obelisk_offset = fixed_tables_end
    count_stream_offset = obelisk_offset + 1
    position = count_stream_offset
    info_block_count = 0
    while True:
        if position + 2 > len(data) - UID_SIZE:
            raise H2CFormatError("unterminated information-block count stream")
        low, high = data[position], data[position + 1]
        position += 2
        if low == 0 and high == 0:
            break
        encoded = high * 256 + low
        if encoded == 0:
            raise H2CFormatError("invalid zero information-block count marker")
        info_block_count = encoded - 1

    block_start = position
    blocks: list[InfoBlock] = []
    for index in range(info_block_count):
        if position + 2 > len(data) - UID_SIZE:
            raise H2CFormatError(f"missing size prefix for information block {index}")
        prefix_offset = position
        size = struct.unpack_from("<H", data, position)[0]
        position += 2
        data_offset = position
        end = data_offset + size
        if size == 0 or end > len(data) - UID_SIZE:
            raise H2CFormatError(
                f"invalid information block {index} size {size} at 0x{prefix_offset:X}"
            )
        blocks.append(
            InfoBlock(
                index=index,
                prefix_offset=prefix_offset,
                data_offset=data_offset,
                data=bytearray(data[data_offset:end]),
            )
        )
        position = end

    if position != len(data) - UID_SIZE:
        raise H2CFormatError(
            f"information blocks end at 0x{position:X}, expected UID at 0x{len(data) - UID_SIZE:X}"
        )

    return H2CMap(
        source_path=path,
        source_size=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        tile_end=tile_end,
        addon_count=addon_count,
        addon_end=addon_end,
        obelisk_offset=obelisk_offset,
        count_stream_offset=count_stream_offset,
        count_stream=data[count_stream_offset:block_start],
        block_start=block_start,
        prefix=bytearray(data[:block_start]),
        blocks=blocks,
        uid_tail=data[position:],
    )


def _payload_from_args(args: argparse.Namespace) -> bytes:
    if args.text is not None:
        try:
            return args.text.encode(args.encoding)
        except (LookupError, UnicodeEncodeError) as exc:
            raise SystemExit(f"cannot encode replacement with {args.encoding}: {exc}") from exc
    compact = "".join(args.hex.split())
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise SystemExit(f"invalid replacement hex: {exc}") from exc


def _print_summary(parsed: H2CMap) -> None:
    print(f"source: {parsed.source_path}")
    print(f"size: {parsed.source_size}")
    print(f"sha256: {parsed.source_sha256}")
    print(f"dimensions: {parsed.width}x{parsed.height}")
    print(f"addons: {parsed.addon_count}")
    print(f"information blocks: {len(parsed.blocks)}")
    print(f"block start: 0x{parsed.block_start:X}")
    print(f"last object UID: {struct.unpack('<I', parsed.uid_tail)[0]}")
    print("fields:")
    for field in parsed.fields():
        flag = "resize" if field.resizable else "fixed"
        escaped = field.text.encode("unicode_escape").decode("ascii")
        print(
            f"  {field.field_id}: offset=0x{field.absolute_offset:X} "
            f"length={field.byte_length} {flag} [{field.confidence}] {escaped}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="print parsed structure and text fields")
    inspect_parser.add_argument("input", type=Path)

    extract_parser = subparsers.add_parser("extract", help="write a JSON structure/text manifest")
    extract_parser.add_argument("input", type=Path)
    extract_parser.add_argument("output", type=Path)

    rebuild_parser = subparsers.add_parser("rebuild", help="write an unchanged structural rebuild")
    rebuild_parser.add_argument("input", type=Path)
    rebuild_parser.add_argument("output", type=Path)

    replace_parser = subparsers.add_parser(
        "replace", help="replace a confirmed resizable tail field and update its block size"
    )
    replace_parser.add_argument("input", type=Path)
    replace_parser.add_argument("output", type=Path)
    replace_parser.add_argument("--field", required=True)
    payload_group = replace_parser.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--text")
    payload_group.add_argument("--hex")
    replace_parser.add_argument("--encoding", default="latin-1")

    verify_parser = subparsers.add_parser("verify", help="compare an input with a no-op rebuild")
    verify_parser.add_argument("input", type=Path)

    args = parser.parse_args(argv)
    parsed = parse_h2c(args.input)

    if args.command == "inspect":
        _print_summary(parsed)
        return 0

    if args.command == "extract":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(parsed.manifest(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote manifest: {args.output}")
        return 0

    if args.command == "rebuild":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(parsed.rebuild())
        print(f"wrote rebuild: {args.output}")
        return 0

    if args.command == "replace":
        payload = _payload_from_args(args)
        old_field = parsed.replace_resizable_field(args.field, payload)
        output = parsed.rebuild()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output)
        print(
            f"replaced {args.field}: {old_field.byte_length} -> {len(payload)} bytes; "
            f"wrote {args.output} ({len(output)} bytes)"
        )
        return 0

    rebuilt = parsed.rebuild()
    source = args.input.read_bytes()
    if rebuilt != source:
        print("FAIL: no-op rebuild is not byte-identical")
        return 1
    print(
        "PASS: byte-identical no-op round trip; "
        f"sha256={hashlib.sha256(rebuilt).hexdigest()} size={len(rebuilt)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
