#!/usr/bin/env python3
"""Build and verify Korean subtitles for the pinned HoMM2 Gold beta6 patch.

Only the caller-provided beta6 HEROES2.EXE/KOREAN.BIN and the public mapping
and cue table are read.  Proprietary outputs are written only to the requested
output directory and are never part of this repository.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
RELEASE_TOOLS = REPO_ROOT / "tools" / "release"
for module_path in (HERE, RELEASE_TOOLS):
    if str(module_path) not in sys.path:
        sys.path.insert(0, str(module_path))

from h2k3_bank import parse_bank, serialize_bank  # noqa: E402
import homm2_font  # noqa: E402


SOURCE_EXE_ID = (1_523_420, "52AE3BA15AE309327D698EDEE8844684F91B3BA056B9215854002265A9F6E3EF")
SOURCE_BANK_ID = (11_286, "DD30DD967E81BB179BC1D33903D0B8926FB799D969A3C36FFAA6CA3FA0C89AAF")
FINAL_EXE_ID = (1_523_420, "B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C")
FINAL_BANK_ID = (36_265, "95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A")
MAPPING_ID = (42_302, "3033584F6E65A36220F61EA58F8D7173A493FC83A72807D6FB43488AAE6DF164")
CUE_SOURCE_ID = (59_940, "E2A9B763D629D14EB0C661D09F3DACD61CFEF2ED27DE7A86D1CE7209E0E2222D")
SAFE_RUNTIME_ID = (1_856, "AFB5B05FF8CCBC053A45714DE0F816083131EAA605ACE6ECE3E8639FBD8C9239")
CANONICAL_RUNTIME_ID = (1_856, "27553D288F7FF27099ADB382434700989BD18BF7643BE0DB23AF1FFD206BB179")
MAPPING_PATH = REPO_ROOT / "translations" / "font" / "mapping874.fixed-interface-font.txt"
SCENE_CUES_PATH = REPO_ROOT / "translations" / "subtitles" / "scene_cues_ko.tsv"
SCENE_CUE_COLUMNS = (
    "scene", "track", "start_ms", "end_ms", "text", "campaign", "block",
    "timing_basis_movie", "timing_status",
)

PARSE_TARGET_START = 0x0010E920
PARSE_TARGET_END = 0x00315520
OLD_DESCRIPTOR_COUNT = 178
OLD_RENDER_COUNT = 16
CUE_TOKEN = 0x3F8
CODE_TOKEN = 0x3FC
ACTIVE_STATE_TOKEN = 0x3F4
CLOCK_INIT_TOKEN = 0x3F0
CUE_PREFIX = b"{KSX2:CUES}!"
CODE_PREFIX = b"{KSXR:CODE}!"
MAPPING_TAG = 0x4F583330

OBJECT1_PREFERRED_BASE = 0x10000
OBJECT1_ACTUAL_BASE = 0x21F000
CALL_SITE_OBJECT_OFFSET = 0x7425D
CALL_SITE_PREFERRED = OBJECT1_PREFERRED_BASE + CALL_SITE_OBJECT_OFFSET
CALL_SITE_ORIGINAL = bytes.fromhex("E8 EE F7 00 00")
ORIGINAL_POST_VIDEO_ROUTINE = 0x93A50
ORIGINAL_POST_VIDEO_OBJECT_OFFSET = ORIGINAL_POST_VIDEO_ROUTINE - OBJECT1_PREFERRED_BASE
ORIGINAL_POST_VIDEO_BYTES = b"\xC3"
PRIMARY_FRAME_CALL_OBJECT_OFFSET = 0x74048
PRIMARY_FRAME_CALL_BYTES = bytes.fromhex("E8 F8 F7 FF FF")
SECONDARY_FRAME_CALL_A_OBJECT_OFFSET = 0x741CB
SECONDARY_FRAME_CALL_A_BYTES = bytes.fromhex("E8 75 F6 FF FF")
SECONDARY_FRAME_CALL_B_OBJECT_OFFSET = 0x74236
SECONDARY_FRAME_CALL_B_BYTES = bytes.fromhex("E8 0A F6 FF FF")
LATE_MERGE_BRANCHES = {
    0x7413D: bytes.fromhex("0F 84 1A 01 00 00"),
    0x74145: bytes.fromhex("0F 84 12 01 00 00"),
    0x74153: bytes.fromhex("0F 85 04 01 00 00"),
    0x74243: bytes.fromhex("0F 84 14 00 00 00"),
    0x74250: bytes.fromhex("0F 86 07 00 00 00"),
}
VIDEO_REFRESH_CALL_OBJECT_OFFSET = 0x7396D
VIDEO_REFRESH_CALL_PREFERRED = OBJECT1_PREFERRED_BASE + VIDEO_REFRESH_CALL_OBJECT_OFFSET
VIDEO_REFRESH_CALL_ORIGINAL = bytes.fromhex("E8 97 1A 01 00")
VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET = 0x73953
VIDEO_REFRESH_CALL_CONTEXT = bytes.fromhex(
    "6A 00 6A 00 68 DF 01 00 00 A1 70 AD 03 00 8B 40 46 "
    "B9 7F 02 00 00 31 DB 31 D2 E8 97 1A 01 00"
)
CALLER_ARGUMENT_OBJECT_OFFSET = 0x7400D
CALLER_ARGUMENT_BYTES = bytes.fromhex("6A 00")
ORIGINAL_FRAME_RETURN_OBJECT_OFFSET = 0x739F7
ORIGINAL_FRAME_RETURN_BYTES = bytes.fromhex("C2 04 00")
CAVE_OBJECT_OFFSET = 0xC4E8F
CAVE_PREFERRED = OBJECT1_PREFERRED_BASE + CAVE_OBJECT_OFFSET
CAVE_CAPACITY = 0x71
CAVE_SOURCE_SHA256 = "0A781558AC722EC58738C7C17D3BD92C2B117DE8B306CBA5336A51A795BEA88C"
SAFE_REFRESH_BRIDGE_SIZE = 6
SAFE_REFRESH_BRIDGE_PREFERRED = CAVE_PREFERRED + CAVE_CAPACITY - SAFE_REFRESH_BRIDGE_SIZE
H2K3_OBJECT_OFFSET = 0xC4F00
H2K3_SIZE = 0x100
MALLOC_INSTRUCTION_OFFSET = 0x2E
MALLOC_BEFORE = bytes.fromhex("B8 00 10 01 00")
MALLOC_AFTER = bytes.fromhex("B8 00 E0 01 00")
FALSE_CAVE_OBJECT_OFFSET = 0x877D6
FALSE_CAVE_SIZE = 0x50
FALSE_CAVE_SOURCE_SHA256 = "B14AB536D0077DA41D57A3E994B78B8226FF935D4E604E1CFDEBE79D48C3FF69"

BANK_CONTROL = 0x00182E90
SCENE_BYTE = 0x0031F22D
VIDEO_SCENE_MIN = 0x04
VIDEO_SCENE_MAX = 0x3F
PRIMARY_HANDLE = 0x0031F248
SECONDARY_HANDLE = 0x0031F24C
SUBTITLE_FONT_OBJECT = 0x0031D550
SURFACE_OWNER = 0x0031F1C0
TEXT_DRAW_ACTUAL = OBJECT1_ACTUAL_BASE + 0x8905E
RECT_REFRESH_OBJECT_OFFSET = 0x85409
RECT_REFRESH_ACTUAL = OBJECT1_ACTUAL_BASE + RECT_REFRESH_OBJECT_OFFSET
SAFE_REFRESH_DISPATCH_OBJECT_OFFSET = 0x3EAC
SAFE_REFRESH_DISPATCH_POINTER = 0x00182EAC
SAFE_REFRESH_DISPATCH_SOURCE = b"H2K3"
SMACK_START_TICK_FIELD = 0x490
TIMER_PROVIDER_POINTER = 0x00316648

SLOT_OFFSET = 0xFF00
CUE_SLOT_OFFSET = SLOT_OFFSET + CUE_TOKEN
CODE_SLOT_OFFSET = SLOT_OFFSET + CODE_TOKEN
ACTIVE_STATE_OFFSET = SLOT_OFFSET + ACTIVE_STATE_TOKEN
CLOCK_INIT_OFFSET = SLOT_OFFSET + CLOCK_INIT_TOKEN
TEXT_BUFFER_OFFSET = 0x10300
TEXT_BUFFER_LIMIT = 0x600
CLOCK_PRIMARY_OFFSET = 0x10900
CLOCK_SECONDARY_OFFSET = 0x10920
CLOCK_STATE_SIZE = 0x20
CLOCK_HANDLE_FIELD = 0x00
CLOCK_LAST_FIELD = 0x04
CLOCK_ELAPSED_FIELD = 0x08
CLOCK_SCENE_FIELD = 0x0C
CLOCK_VALID_FIELD = 0x10
CLOCK_GENERATION_FIELD = 0x14
CLOCK_ELAPSED_MS_FIELD = 0x18
CLOCK_MS_VALID_FIELD = 0x1C
CLOCK_STATE_END = 0x10940
SCRATCH_OFFSET = 0x11000
ALLOCATION_SIZE = 0x1E000
VIDEO_WIDTH = 640
SUBTITLE_SCALE_NUMERATOR = 2
SUBTITLE_SCALE_DENOMINATOR = 1
SCALE_REPEAT = 2
SUBTITLE_Y = 406
SUBTITLE_HEIGHT = 68
SAFE_REFRESH_HEIGHT = 0x1DF - SUBTITLE_Y
SUBTITLE_BYTES = VIDEO_WIDTH * SUBTITLE_HEIGHT
FRAMEBUFFER_BAND_OFFSET = VIDEO_WIDTH * SUBTITLE_Y
SOURCE_X = 0
SOURCE_Y = 408
SOURCE_WIDTH = 280
SOURCE_HEIGHT = 32
SOURCE_FRAMEBUFFER_OFFSET = VIDEO_WIDTH * SOURCE_Y + SOURCE_X
SCALED_WIDTH = SOURCE_WIDTH * 2
SCALED_HEIGHT = SOURCE_HEIGHT * 2
SCALED_X = (VIDEO_WIDTH - SCALED_WIDTH) // 2
SCALED_Y = 408
SINGLE_LINE_SCALED_Y = 424
SUBTITLE_FONT_LINE_BOX = 16
GLYPH_SCRATCH_OFFSET = SCRATCH_OFFSET + SUBTITLE_BYTES
LAYOUT_FLAG_OFFSET = GLYPH_SCRATCH_OFFSET + SOURCE_WIDTH * SOURCE_HEIGHT
SCALE_SIGNATURE = b"S2O1"
REFRESH_CLIP_SIGNATURE = b"VCL1"
STAGING_SENTINEL = 0xFF
SOURCE_INK_PALETTE_MIN = 10
SOURCE_INK_PALETTE_MAX = 20
SUBTITLE_OUTLINE_PALETTE_INDEX = 0
SUBTITLE_FOREGROUND_PALETTE_INDEX = 0xFF
SUBTITLE_OUTLINE_PIXELS = 1
RUNTIME_XOR_KEY = 0x0D
RUNTIME_PADDING_BYTE = 0x90
D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH = 1_856

KSX_MAGIC = b"KSX2"
KSX_VERSION = 2
KSX_KEY = 0xA5
KSX_HEADER_SIZE = 12
KSX_ROW_SIZE = 12
TRACK_PRIMARY = 1
TRACK_SECONDARY = 2
TRACK_PRIMARY_MS = 3
TRACK_SECONDARY_MS = 4
TRACK_NAME_TO_ID = {"primary_ms": TRACK_PRIMARY_MS, "secondary_ms": TRACK_SECONDARY_MS}
TRACK_ID_TO_NAME = {value: key for key, value in TRACK_NAME_TO_ID.items()}
CODE_SIGNATURE = b"KSXR"
EXPECTED_FIXUP_ROWS = 28_095


class BuildError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BuildError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def identity(raw: bytes) -> tuple[int, str]:
    return len(raw), sha256(raw)


def read_u16(raw: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<H", raw, offset)[0]


def read_u32(raw: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


@dataclass(frozen=True)
class ObjectRecord:
    number: int
    entry_offset: int
    virtual_size: int
    reloc_base: int
    flags: int
    page_map_index: int
    page_count: int


class LeImage:
    def __init__(self, raw: bytes | bytearray):
        self.data = raw
        self.le_offset = raw.find(b"LE\0\0")
        require(self.le_offset >= 0, "LE header not found")
        self.mz_offset = self._find_nested_mz()
        self.page_count = read_u32(raw, self.le_offset + 0x14)
        self.page_size = read_u32(raw, self.le_offset + 0x28)
        self.object_table_offset = read_u32(raw, self.le_offset + 0x40)
        self.object_count = read_u32(raw, self.le_offset + 0x44)
        self.page_map_offset = read_u32(raw, self.le_offset + 0x48)
        self.data_pages_offset = read_u32(raw, self.le_offset + 0x80)
        self.data_base = self.mz_offset + self.data_pages_offset
        self.objects = tuple(self._read_object(number) for number in range(1, self.object_count + 1))

    def _find_nested_mz(self) -> int:
        for offset in range(self.le_offset, -1, -1):
            if self.data[offset:offset + 2] == b"MZ" and offset + read_u32(self.data, offset + 0x3C) == self.le_offset:
                return offset
        raise BuildError("nested MZ header not found")

    def _read_object(self, number: int) -> ObjectRecord:
        entry = self.le_offset + self.object_table_offset + (number - 1) * 24
        return ObjectRecord(
            number, entry, read_u32(self.data, entry), read_u32(self.data, entry + 4),
            read_u32(self.data, entry + 8), read_u32(self.data, entry + 12),
            read_u32(self.data, entry + 16),
        )

    def object_to_file(self, object_number: int, object_offset: int) -> int:
        record = self.objects[object_number - 1]
        require(0 <= object_offset < record.page_count * self.page_size, "object offset exceeds page capacity")
        logical_page = record.page_map_index + object_offset // self.page_size
        map_entry = self.le_offset + self.page_map_offset + (logical_page - 1) * 4
        physical_page = read_u16(self.data, map_entry + 2)
        require(1 <= physical_page <= self.page_count, "invalid physical LE page")
        return self.data_base + (physical_page - 1) * self.page_size + object_offset % self.page_size


@dataclass(frozen=True)
class Cue:
    scene: int
    track: int
    start_frame: int
    end_frame: int
    text: bytes


@dataclass(frozen=True)
class SubtitleMapping:
    by_character: dict[str, bytes]


def load_subtitle_mapping(path: Path = MAPPING_PATH) -> SubtitleMapping:
    raw = path.read_bytes()
    require(identity(raw) == MAPPING_ID, "874-glyph mapping identity changed")
    try:
        rows = homm2_font.parse_mapping(path)
    except (OSError, homm2_font.FontBuildError) as exc:
        raise BuildError(f"cannot load subtitle mapping: {exc}") from exc
    by_character = {row.character: bytes((row.lead, row.trail)) for row in rows}
    require(len(rows) == len(by_character) == 874, "subtitle mapping must contain 874 unique glyphs")
    return SubtitleMapping(by_character)


def encode_text(text: str, mapping: SubtitleMapping) -> bytes:
    require("\0" not in text, "subtitle text contains NUL")
    result = bytearray()
    for character in text:
        encoded = mapping.by_character.get(character)
        if encoded is not None:
            result.extend(encoded)
        elif ord(character) <= 0x7F:
            result.append(ord(character))
        else:
            raise BuildError(f"subtitle has no mapped glyph: U+{ord(character):04X} {character}")
    return bytes(result)


def load_scene_cues(
    path: Path = SCENE_CUES_PATH,
    mapping: SubtitleMapping | None = None,
) -> tuple[tuple[Cue, ...], dict[str, object]]:
    raw = path.read_bytes()
    require(identity(raw) == CUE_SOURCE_ID, "canonical Korean subtitle cue table identity changed")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildError("subtitle cue table is not UTF-8") from exc
    require("\0" not in text and "\r" not in text, "subtitle cue table contains NUL or CR")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    require(tuple(reader.fieldnames or ()) == SCENE_CUE_COLUMNS, "subtitle cue columns changed")
    mapping = mapping or load_subtitle_mapping()
    cues: list[Cue] = []
    scenes: set[int] = set()
    movies: set[str] = set()
    track_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for line_number, row in enumerate(reader, 2):
        require(None not in row and all(value is not None for value in row.values()), f"cue row {line_number} column count changed")
        scene_text = row["scene"]
        require(len(scene_text) == 4 and scene_text.startswith("0x") and scene_text[2:].upper() == scene_text[2:], f"cue row {line_number} scene is not canonical hex")
        try:
            scene = int(scene_text, 16)
        except ValueError as exc:
            raise BuildError(f"cue row {line_number} scene is invalid") from exc
        require(VIDEO_SCENE_MIN <= scene <= VIDEO_SCENE_MAX, f"cue row {line_number} scene is outside the narrated range")
        track_name = row["track"]
        require(track_name in TRACK_NAME_TO_ID, f"cue row {line_number} track is invalid")
        require(row["start_ms"].isdigit() and row["end_ms"].isdigit(), f"cue row {line_number} timing is not decimal")
        start_ms, end_ms = int(row["start_ms"]), int(row["end_ms"])
        require(0 <= start_ms < end_ms <= 0xFFFFFFFF, f"cue row {line_number} interval is invalid")
        authored = row["text"]
        require(authored and authored == authored.strip(), f"cue row {line_number} text is empty or padded")
        require("{" not in authored and "}" not in authored and "\t" not in authored, f"cue row {line_number} text has a control character")
        require("\\" not in authored.replace("\\n", ""), f"cue row {line_number} text has an unsupported escape")
        subtitle = authored.replace("\\n", "\n")
        lines = subtitle.split("\n")
        require(1 <= len(lines) <= 2 and all(line and line == line.strip() for line in lines), f"cue row {line_number} is not one or two canonical lines")
        encoded = encode_text(subtitle, mapping)
        require(0 < len(encoded) < TEXT_BUFFER_LIMIT and b"\0" not in encoded, f"cue row {line_number} encoded text is invalid")
        movie = row["timing_basis_movie"]
        require(movie.endswith(".SMK") and movie == movie.upper(), f"cue row {line_number} movie name is invalid")
        require(row["campaign"] and row["block"] and row["timing_status"], f"cue row {line_number} provenance is incomplete")
        cues.append(Cue(scene, TRACK_NAME_TO_ID[track_name], start_ms, end_ms, encoded))
        scenes.add(scene)
        movies.add(movie)
        track_counts[track_name] = track_counts.get(track_name, 0) + 1
        status = row["timing_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    result = tuple(cues)
    require(len(result) == 388, "subtitle cue count changed")
    require(len(scenes) == 57 and len(movies) == 51, "subtitle scene/movie coverage changed")
    require(track_counts == {"primary_ms": 27, "secondary_ms": 361}, "dual-ms cue distribution changed")
    require(parse_cues(serialize_cues(result)) == result, "subtitle cues do not round-trip through KSX2")
    return result, {
        "file": "translations/subtitles/scene_cues_ko.tsv",
        "size": len(raw),
        "sha256": sha256(raw),
        "cue_count": len(result),
        "scene_count": len(scenes),
        "movie_count": len(movies),
        "track_counts": dict(sorted(track_counts.items())),
        "timing_status_counts": dict(sorted(status_counts.items())),
    }



@dataclass(frozen=True)
class Fixup:
    source_object: int
    source_offset: int
    target_object: int
    target_offset: int
    src: int
    flags: int
    record_file_offset: int
    record_bytes: bytes



@dataclass(frozen=True)
class ClockState:
    valid: bool = False
    scene: int = 0
    handle: int = 0
    last: int = 0
    elapsed: int = 0
    generation: int = 0
    elapsed_ms: int = 0



class Assembler:
    """Small fixed-purpose IA-32 assembler with checked branch fixups."""

    def __init__(self, base: int = 0):
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, int, str]] = []

    @property
    def offset(self) -> int:
        return len(self.code)

    @property
    def address(self) -> int:
        return self.base + self.offset

    def emit(self, raw: bytes | str) -> None:
        self.code.extend(bytes.fromhex(raw) if isinstance(raw, str) else raw)

    def u8(self, value: int) -> None:
        self.code.append(value & 0xFF)

    def u16(self, value: int) -> None:
        self.code.extend(struct.pack("<H", value & 0xFFFF))

    def u32(self, value: int) -> None:
        self.code.extend(struct.pack("<I", value & 0xFFFFFFFF))

    def label(self, name: str) -> None:
        require(name not in self.labels, f"duplicate label: {name}")
        self.labels[name] = self.offset

    def branch8(self, opcode: int, label: str) -> None:
        self.u8(opcode)
        self.fixups.append((self.offset, 1, label))
        self.u8(0)

    def branch32(self, opcode: bytes, label: str) -> None:
        self.emit(opcode)
        self.fixups.append((self.offset, 4, label))
        self.u32(0)

    def jump_absolute(self, target: int) -> None:
        after = self.address + 5
        self.u8(0xE9)
        self.emit(struct.pack("<i", target - after))

    def call_absolute(self, target: int) -> None:
        after = self.address + 5
        self.u8(0xE8)
        self.emit(struct.pack("<i", target - after))

    def finish(self) -> bytes:
        for patch, width, label in self.fixups:
            require(label in self.labels, f"undefined label: {label}")
            displacement = self.labels[label] - (patch + width)
            if width == 1:
                require(-128 <= displacement <= 127, f"short branch out of range: {label}")
                self.code[patch] = displacement & 0xFF
            else:
                struct.pack_into("<i", self.code, patch, displacement)
        return bytes(self.code)



def raw_fixup_blobs(raw: bytes, image: LeImage) -> tuple[bytes, bytes]:
    table = image.le_offset + struct.unpack_from("<I", raw, image.le_offset + 0x68)[0]
    records = image.le_offset + struct.unpack_from("<I", raw, image.le_offset + 0x6C)[0]
    sentinel = struct.unpack_from("<I", raw, table + image.page_count * 4)[0]
    return (
        raw[table : table + (image.page_count + 1) * 4],
        raw[records : records + sentinel],
    )



def parse_raw_fixups(raw: bytes, image: LeImage) -> tuple[Fixup, ...]:
    """Parse the candidate's real LE fixup graph, including 32-bit targets.

    The older CSV remains useful as a source-span cross-check, but it was made
    from a different executable revision and reports the preserved operand's
    old 0x3ADF8 target.  The pinned beta6 record is authoritative here.
    """
    page_table = image.le_offset + struct.unpack_from("<I", raw, image.le_offset + 0x68)[0]
    record_base = image.le_offset + struct.unpack_from("<I", raw, image.le_offset + 0x6C)[0]
    sentinel = struct.unpack_from("<I", raw, page_table + image.page_count * 4)[0]
    require((page_table, record_base) == (0x38448, 0x38848), "beta6 LE fixup geometry changed")
    require(record_base + sentinel <= image.data_base, "LE fixup records overlap data pages")
    rows: list[Fixup] = []
    for logical in range(1, image.page_count + 1):
        start_rel = struct.unpack_from("<I", raw, page_table + (logical - 1) * 4)[0]
        end_rel = struct.unpack_from("<I", raw, page_table + logical * 4)[0]
        require(start_rel <= end_rel <= sentinel, "LE fixup page table is not monotonic")
        pos = record_base + start_rel
        page_end = record_base + end_rel
        owners = [
            obj for obj in image.objects
            if obj.page_map_index <= logical < obj.page_map_index + obj.page_count
        ]
        require(len(owners) == 1, "LE fixup page has no unique object owner")
        owner = owners[0]
        while pos < page_end:
            record_start = pos
            require(pos + 4 <= page_end, "truncated LE fixup record header")
            src, flags = raw[pos], raw[pos + 1]
            pos += 2
            require((src & 0x0F) == 7 and not (src & 0x20), "unsupported LE source form")
            require((flags & 3) == 0, "unsupported non-internal LE target")
            raw_source = struct.unpack_from("<H", raw, pos)[0]
            pos += 2
            object_width = 2 if flags & 0x40 else 1
            require(pos + object_width <= page_end, "truncated LE target object")
            target_object = struct.unpack_from("<H", raw, pos)[0] if object_width == 2 else raw[pos]
            pos += object_width
            target_width = 4 if flags & 0x10 else 2
            require(pos + target_width <= page_end, "truncated LE target offset")
            target_offset = struct.unpack_from("<I" if target_width == 4 else "<H", raw, pos)[0]
            pos += target_width
            if flags & 0x04:
                additive_width = 4 if flags & 0x20 else 2
                require(pos + additive_width <= page_end, "truncated LE additive field")
                pos += additive_width
            signed_source = raw_source if raw_source < 0x8000 else raw_source - 0x10000
            source_offset = (logical - owner.page_map_index) * image.page_size + signed_source
            require(
                0 <= source_offset and source_offset + 4 <= owner.page_count * image.page_size,
                "LE fixup source escaped owner object",
            )
            rows.append(Fixup(
                owner.number,
                source_offset,
                target_object,
                target_offset,
                src,
                flags,
                record_start,
                raw[record_start:pos],
            ))
        require(pos == page_end, f"LE fixup page {logical} did not parse exactly")
    require(len(rows) == EXPECTED_FIXUP_ROWS, "beta6 LE fixup row count changed")
    return tuple(rows)



def _xor_u32(value: int, key: int = KSX_KEY) -> bytes:
    mask = key * 0x01010101
    return struct.pack("<I", value ^ mask)



def _xor_u16(value: int, key: int = KSX_KEY) -> bytes:
    mask = key * 0x0101
    return struct.pack("<H", value ^ mask)



def serialize_cues(cues: Sequence[Cue]) -> bytes:
    require(1 <= len(cues) <= 0xFFFF, "KSX2 cue count must be 1..65535")
    body = bytearray(
        KSX_MAGIC
        + bytes((KSX_VERSION, KSX_KEY, KSX_HEADER_SIZE, KSX_KEY))
        + _xor_u16(len(cues))
        + b"\xA5\xA5"
    )
    keys: list[tuple[int, int, int, int]] = []
    for index, cue in enumerate(cues):
        require(0 <= cue.scene <= 0xFF, f"cue {index} scene must be uint8")
        require(cue.track in TRACK_ID_TO_NAME, f"cue {index} track is invalid")
        require(0 <= cue.start_frame < cue.end_frame <= 0xFFFFFFFF, f"cue {index} frame interval is invalid")
        require(0 < len(cue.text) < TEXT_BUFFER_LIMIT, f"cue {index} text is too long")
        require(b"\0" not in cue.text, f"cue {index} text contains NUL")
        body.extend((cue.scene ^ KSX_KEY, cue.track ^ KSX_KEY))
        body.extend(_xor_u32(cue.start_frame))
        body.extend(_xor_u32(cue.end_frame))
        body.extend(_xor_u16(len(cue.text)))
        body.extend(cue.text)
        keys.append((cue.scene, cue.track, cue.start_frame, cue.end_frame))
    require(keys == sorted(keys), "cues must be sorted by scene/track/start/end")
    for previous, current in zip(cues, cues[1:]):
        if (previous.scene, previous.track) == (current.scene, current.track):
            require(previous.end_frame <= current.start_frame, "cues for one scene/track overlap")
    body[10:12] = _xor_u16(len(body))
    require(b"\0" not in body, "KSX2 descriptor contains NUL")
    return bytes(body)



def parse_cues(raw: bytes) -> tuple[Cue, ...]:
    require(len(raw) >= KSX_HEADER_SIZE, "KSX2 header is truncated")
    require(raw[:4] == KSX_MAGIC, "KSX2 magic mismatch")
    require(
        raw[4:8] == bytes((KSX_VERSION, KSX_KEY, KSX_HEADER_SIZE, KSX_KEY)),
        "KSX2 header mismatch",
    )
    count = struct.unpack_from("<H", raw, 8)[0] ^ 0xA5A5
    total = struct.unpack_from("<H", raw, 10)[0] ^ 0xA5A5
    require(total == len(raw), "KSX2 total length mismatch")
    require(count != 0, "KSX2 cue count is zero")
    cursor = KSX_HEADER_SIZE
    cues: list[Cue] = []
    for index in range(count):
        require(cursor + KSX_ROW_SIZE <= len(raw), f"cue {index} row is truncated")
        scene = raw[cursor] ^ KSX_KEY
        track = raw[cursor + 1] ^ KSX_KEY
        require(track in TRACK_ID_TO_NAME, f"cue {index} track is invalid")
        start = struct.unpack_from("<I", raw, cursor + 2)[0] ^ 0xA5A5A5A5
        end = struct.unpack_from("<I", raw, cursor + 6)[0] ^ 0xA5A5A5A5
        length = struct.unpack_from("<H", raw, cursor + 10)[0] ^ 0xA5A5
        cursor += KSX_ROW_SIZE
        require(0 < length < TEXT_BUFFER_LIMIT and cursor + length <= len(raw), f"cue {index} text range is invalid")
        cues.append(Cue(scene, track, start, end, raw[cursor : cursor + length]))
        cursor += length
    require(cursor == len(raw), "KSX2 trailing bytes remain")
    return tuple(cues)



def lookup_cue(cues: Iterable[Cue], scene: int, track: int, frame: int) -> Cue | None:
    for cue in cues:
        if cue.scene == scene and cue.track == track and cue.start_frame <= frame < cue.end_frame:
            return cue
    return None



def sample_dual_ms_clocks(
    *,
    now_tick: int,
    primary_handle: int,
    primary_start_tick: int,
    secondary_handle: int,
    secondary_start_tick: int,
    timer_available: bool = True,
) -> dict[int, int | None]:
    """Semantic model of the runtime's one-sample, two-start-tick clocks."""

    return {
        TRACK_PRIMARY_MS: elapsed_since_start_ms(
            start_tick=primary_start_tick,
            now_tick=now_tick,
            timer_available=timer_available and primary_handle != 0,
        ),
        TRACK_SECONDARY_MS: elapsed_since_start_ms(
            start_tick=secondary_start_tick,
            now_tick=now_tick,
            timer_available=timer_available and secondary_handle != 0,
        ),
    }



def select_ms_timeline(track: int, samples: dict[int, int | None]) -> int | None:
    """Select only an approved KSX2 millisecond track, failing closed."""

    return samples.get(track) if track in TRACK_ID_TO_NAME else None



def simulate_active_transition(
    active: int,
    *,
    cue_matches: bool,
    font_available: bool,
    surface_available: bool,
) -> tuple[int, str]:
    """Semantic model of the final once-per-tick subtitle-band publication."""
    require(active in (0, 1), "active state must be 0 or 1")
    if cue_matches and font_available and surface_available:
        return 1, "draw"
    if surface_available:
        return 0, "band"
    return active, "none"



def simulate_frame_publish_lifecycle(*, secondary_refresh: bool, late_hook: bool) -> tuple[str, ...]:
    """Model screen publications within one primary/secondary video-loop tick.

    With the late runtime active, Smacker publications are clipped above the
    band and the late hook publishes the band once.  Restoring P remains absent
    because it changes only clean backing pixels and does not publish them.
    """
    events = ["primary_upper_refresh" if late_hook else "primary_clean_refresh"]
    if not late_hook:
        events.append("subtitle_refresh")
    if secondary_refresh:
        events.append("secondary_upper_refresh" if late_hook else "secondary_clean_refresh")
    if late_hook:
        events.append("subtitle_band_refresh")
    return tuple(events)



def advance_unwrapped_clock(
    state: ClockState,
    *,
    scene: int,
    handle: int,
    frame_count: int,
    current_frame: int,
    generation: int = 1,
) -> tuple[ClockState, int | None]:
    """Advance one track's wrapping uint32 frame counter fail-closed.

    ``generation`` is Smacker's first-decode start tick (handle+0x490).  It is
    part of the identity so a reused allocator address does not inherit the
    prior movie's timeline.  A non-terminal backwards jump is retained as a
    conservative secondary reset heuristic.
    """
    require(0 <= scene <= 0xFF, "clock scene must be uint8")
    if (
        not (0 < handle <= 0xFFFFFFFF)
        or not (0 < generation <= 0xFFFFFFFF)
        or not (0 < frame_count <= 0xFFFFFFFF)
        or not (0 <= current_frame < frame_count)
    ):
        return ClockState(), None
    if (
        not state.valid
        or state.scene != scene
        or state.handle != handle
        or state.generation != generation
    ):
        reset = ClockState(True, scene, handle, current_frame, current_frame, generation, 0)
        return reset, reset.elapsed
    if not (0 <= state.last < frame_count):
        return ClockState(), None
    if current_frame < state.last and state.last != frame_count - 1:
        reset = ClockState(True, scene, handle, current_frame, current_frame, generation, 0)
        return reset, reset.elapsed
    delta = (
        current_frame - state.last
        if current_frame >= state.last
        else (frame_count - state.last) + current_frame
    )
    elapsed = state.elapsed + delta
    if elapsed > 0xFFFFFFFF:
        return ClockState(), None
    advanced = ClockState(True, scene, handle, current_frame, elapsed, generation, state.elapsed_ms)
    return advanced, advanced.elapsed



def elapsed_since_start_ms(*, start_tick: int, now_tick: int, timer_available: bool = True) -> int | None:
    """Return Smacker session elapsed milliseconds with uint32 timer wrap."""
    if (
        not timer_available
        or not (0 < start_tick <= 0xFFFFFFFF)
        or not (0 <= now_tick <= 0xFFFFFFFF)
    ):
        return None
    return (now_tick - start_tick) & 0xFFFFFFFF



def advance_ms_clock(
    state: ClockState,
    *,
    scene: int,
    handle: int,
    frame_count: int,
    current_frame: int,
    start_tick: int,
    now_tick: int,
    timer_available: bool = True,
) -> tuple[ClockState, int | None]:
    """Model one Smacker handle's session time, independent of frame loops."""
    state, _raw = advance_unwrapped_clock(
        state,
        scene=scene,
        handle=handle,
        frame_count=frame_count,
        current_frame=current_frame,
        generation=start_tick,
    )
    if not state.valid:
        return state, None
    elapsed_ms = elapsed_since_start_ms(
        start_tick=start_tick,
        now_tick=now_tick,
        timer_available=timer_available,
    )
    if elapsed_ms is None:
        return ClockState(
            state.valid,
            state.scene,
            state.handle,
            state.last,
            state.elapsed,
            state.generation,
            0,
        ), None
    state = ClockState(
        state.valid,
        state.scene,
        state.handle,
        state.last,
        state.elapsed,
        state.generation,
        elapsed_ms,
    )
    return state, elapsed_ms



def advance_primary_ms_clock(
    state: ClockState,
    **kwargs: object,
) -> tuple[ClockState, int | None]:
    """Compatibility wrapper for the primary Smacker millisecond clock."""

    return advance_ms_clock(state, **kwargs)  # type: ignore[arg-type]



def advance_secondary_ms_clock(
    state: ClockState,
    **kwargs: object,
) -> tuple[ClockState, int | None]:
    """Model TRACK_SECONDARY_MS from the secondary voice handle's start tick."""

    return advance_ms_clock(state, **kwargs)  # type: ignore[arg-type]



def verify_scaled_runtime_contract(runtime: bytes) -> dict[str, object]:
    """Pin the unchanged dual-ms/2x compositor used as the safe-runtime base."""

    require(identity(runtime) == CANONICAL_RUNTIME_ID, "canonical dual-ms 2x runtime changed")
    require(runtime[:6] == b"\xEB\x04" + CODE_SIGNATURE, "canonical runtime signature changed")
    require(runtime.count(b"\xEB\x04" + SCALE_SIGNATURE) == 1, "2x compositor marker changed")
    require(runtime.count(b"\xEB\x04" + REFRESH_CLIP_SIGNATURE) == 1, "refresh helper marker changed")
    require(runtime.count(struct.pack("<I", SUBTITLE_FONT_OBJECT)) == 2, "big-font runtime operands changed")
    require(runtime.count(struct.pack("<I", TIMER_PROVIDER_POINTER)) == 1, "dual-ms timer sampling changed")
    require(len(runtime) == D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "runtime/bootstrap length contract changed")
    require(b"\0" not in bytes(value ^ RUNTIME_XOR_KEY for value in runtime), "encrypted canonical runtime contains NUL")
    return {
        "runtime_size": len(runtime),
        "runtime_sha256": sha256(runtime),
        "dual_ms": True,
        "scale": 2,
        "outline": "1px black",
    }


def verify_safe_refresh_runtime_contract(runtime: bytes) -> dict[str, object]:
    """Verify the isolated no-false-cave refresh-dispatch runtime."""

    canonical = build_heap_runtime()
    require(len(runtime) == len(canonical) == D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "safe runtime length changed")
    require(runtime[:6] == canonical[:6] == b"\xEB\x04" + CODE_SIGNATURE, "safe runtime entry signature changed")
    require(runtime != canonical, "safe runtime did not change")

    helper_marker = b"\xEB\x04" + REFRESH_CLIP_SIGNATURE
    parser_marker = b"\x8B\xB5" + struct.pack("<I", CUE_SLOT_OFFSET)
    require(runtime.count(helper_marker) == canonical.count(helper_marker) == 1, "safe refresh marker is not exact-one")
    require(runtime.count(parser_marker) == canonical.count(parser_marker) == 1, "safe parser marker is not exact-one")
    helper_entry = runtime.index(helper_marker) + len(helper_marker)
    canonical_helper_entry = canonical.index(helper_marker) + len(helper_marker)
    parser_offset = runtime.index(parser_marker)
    canonical_parser_offset = canonical.index(parser_marker)

    publish_prefix = b"\x8B\x85" + struct.pack("<I", CODE_SLOT_OFFSET) + b"\x05"
    publish_at = runtime.find(publish_prefix)
    require(publish_at >= 0 and runtime.count(publish_prefix) == 1, "safe dispatch publication is not exact-one")
    encoded_helper_offset = struct.unpack_from("<I", runtime, publish_at + len(publish_prefix))[0]
    publish_tail = b"\xA3" + struct.pack("<I", SAFE_REFRESH_DISPATCH_POINTER)
    require(encoded_helper_offset == helper_entry, "safe dispatch helper offset is wrong")
    require(
        runtime[publish_at + len(publish_prefix) + 4 : publish_at + len(publish_prefix) + 4 + len(publish_tail)]
        == publish_tail,
        "safe dispatch pointer publication changed",
    )

    gate_prefix = (
        b"\x50\x57\xA0" + struct.pack("<I", SCENE_BYTE)
        + b"\x2C" + bytes((VIDEO_SCENE_MIN,))
        + b"\x3C" + bytes((VIDEO_SCENE_MAX - VIDEO_SCENE_MIN,))
    )
    require(runtime[helper_entry : helper_entry + len(gate_prefix)] == gate_prefix, "safe refresh scene gate changed")
    helper_region = runtime[helper_entry : len(runtime.rstrip(bytes((RUNTIME_PADDING_BYTE,))))]
    require(helper_region.count(b"\x8B\x3D" + struct.pack("<I", BANK_CONTROL)) == 1, "safe refresh bank gate changed")
    require(
        helper_region.count(b"\x80\xBF" + struct.pack("<I", ACTIVE_STATE_OFFSET) + b"\x01") == 1,
        "safe refresh active-state gate changed",
    )
    require(
        helper_region.count(b"\x8B\xBF" + struct.pack("<I", CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD)) == 1,
        "safe refresh armed-generation load changed",
    )
    require(
        runtime.count(b"\x89\x95" + struct.pack("<I", CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD)) == 1,
        "safe runtime does not publish the primary generation exact-once",
    )
    require(helper_region.endswith(b"\x5F\x58\x68" + struct.pack("<I", RECT_REFRESH_ACTUAL) + b"\xC3"), "safe original refresh fallback changed")

    # Everything from the cue parser through the refresh-helper signature is
    # the canonical D timing/font/compositor byte stream except the two final
    # publication-height immediates.  Dispatch publication and generation
    # capture add exactly 32 bytes before the parser.
    require(parser_offset == canonical_parser_offset + 32, "safe dispatch/generation state did not shift the parser by exactly 32 bytes")
    canonical_slice = canonical[canonical_parser_offset : canonical_helper_entry]
    old_refresh = b"\x6A\x00\x6A" + bytes((SUBTITLE_HEIGHT,)) + b"\x31\xD2\xBB" + struct.pack("<I", SUBTITLE_Y)
    safe_refresh = b"\x6A\x00\x6A" + bytes((SAFE_REFRESH_HEIGHT,)) + b"\x31\xD2\xBB" + struct.pack("<I", SUBTITLE_Y)
    require(canonical_slice.count(old_refresh) == 2, "canonical late refresh-height sites changed")
    expected_safe_slice = canonical_slice.replace(old_refresh, safe_refresh)
    require(
        runtime[parser_offset : helper_entry]
        == expected_safe_slice,
        "safe dispatch changed parser/font/compositor bytes outside the two publication heights",
    )
    require(runtime.count(struct.pack("<I", SUBTITLE_FONT_OBJECT)) == 2, "safe runtime font operands changed")
    require(runtime.count(struct.pack("<I", TIMER_PROVIDER_POINTER)) == 1, "safe runtime timer sampling changed")
    require(runtime.count(struct.pack("<I", PRIMARY_HANDLE)) == 2, "safe runtime primary clock/generation reads changed")
    require(runtime.count(struct.pack("<I", SECONDARY_HANDLE)) == 1, "safe runtime secondary clock changed")

    unpadded = runtime.rstrip(bytes((RUNTIME_PADDING_BYTE,)))
    require(unpadded and unpadded[-1] == 0xC3, "safe runtime padding lacks a terminal RET")
    require(runtime[len(unpadded) :] == bytes((RUNTIME_PADDING_BYTE,)) * (len(runtime) - len(unpadded)), "safe runtime NOP padding changed")
    require(b"\0" not in bytes(value ^ RUNTIME_XOR_KEY for value in runtime), "safe encrypted runtime contains NUL")
    return {
        "runtime_size": len(runtime),
        "runtime_sha256": sha256(runtime),
        "canonical_parser_bytes_preserved": True,
        "dispatch_pointer": f"0x{SAFE_REFRESH_DISPATCH_POINTER:X}",
        "helper_offset": f"0x{helper_entry:X}",
        "scene_gate": [f"0x{VIDEO_SCENE_MIN:02X}", f"0x{VIDEO_SCENE_MAX:02X}"],
        "active_state_gate": f"B+0x{ACTIVE_STATE_OFFSET:X} == 1",
        "active_generation_gate": f"B+0x{CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD:X} == PRIMARY_HANDLE+0x{SMACK_START_TICK_FIELD:X}",
        "late_publication_height": SAFE_REFRESH_HEIGHT,
        "initial_original_refresh_fallback": f"0x{RECT_REFRESH_ACTUAL:X}",
        "encrypted_nul_free": True,
    }



def build_heap_runtime(*, safe_refresh_dispatch: bool = False) -> bytes:
    """Build the generic cue lookup, band-preserving draw, and refresh code.

    ``safe_refresh_dispatch`` selects the released flicker-safe form.  It
    publishes the heap-resident, active-state-gated clip helper through a
    writable Object3 pointer.  The default remains available as a byte-exact
    baseline for contract tests.
    """
    a = Assembler()
    dispatch_helper_offset_patch: int | None = None
    refresh_height = SAFE_REFRESH_HEIGHT if safe_refresh_dispatch else SUBTITLE_HEIGHT

    def emit_elapsed_ms(prefix: str, state_offset: int, handle_address: int) -> None:
        """Store uint32(shared-now-handle[0x490]) for one checked handle."""
        done = f"{prefix}_ms_done"
        a.emit("8B 3D"); a.u32(handle_address)
        a.emit("85 FF"); a.branch8(0x74, done)
        a.emit("8B 97"); a.u32(SMACK_START_TICK_FIELD)
        if safe_refresh_dispatch and handle_address == PRIMARY_HANDLE:
            a.emit("89 95"); a.u32(CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD)
        a.emit("85 D2"); a.branch8(0x74, done)
        a.emit("89 F0 29 D0")                               # eax=(shared now-start) mod 2^32
        a.emit("89 85"); a.u32(state_offset + CLOCK_ELAPSED_MS_FIELD)
        a.emit("C6 85"); a.u32(state_offset + CLOCK_MS_VALID_FIELD); a.u8(1)
        a.label(done)

    a.emit("EB 04")
    a.emit(CODE_SIGNATURE)
    a.label("entry")
    a.emit("1E 06 1E 07")                                  # save DS/ES; flat ES for REP MOVS
    a.emit("8B 2D"); a.u32(BANK_CONTROL)                 # mov ebp,[bank]
    a.emit("85 ED"); a.branch32(b"\x0F\x84", "done")
    if safe_refresh_dispatch:
        # The bootstrap has already replaced CODE_SLOT with this decoded
        # runtime's entry address.  Publish the helper address without any
        # self-modifying code; the patched Smacker CALL reaches it through a
        # six-byte indirect-jump bridge in the proven bootstrap cave.
        a.emit("8B 85"); a.u32(CODE_SLOT_OFFSET)
        a.emit("05")
        dispatch_helper_offset_patch = a.offset
        a.u32(0)
        a.emit("A3"); a.u32(SAFE_REFRESH_DISPATCH_POINTER)
    # Read the game's millisecond provider once so primary visual and secondary
    # voice clocks share one observation.  Reload the bank after the ABI call,
    # then fail each handle independently when it or its first-decode tick is
    # absent.  A primary that started earlier can therefore never advance a
    # TRACK_SECONDARY_MS cue.
    a.emit("A1"); a.u32(TIMER_PROVIDER_POINTER)
    a.emit("85 C0"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("FF D0 89 C6")                                   # ESI=shared now tick
    a.emit("8B 2D"); a.u32(BANK_CONTROL)
    a.emit("85 ED"); a.branch32(b"\x0F\x84", "done")
    a.emit("C6 85"); a.u32(CLOCK_PRIMARY_OFFSET + CLOCK_MS_VALID_FIELD); a.u8(0)
    a.emit("C6 85"); a.u32(CLOCK_SECONDARY_OFFSET + CLOCK_MS_VALID_FIELD); a.u8(0)
    if safe_refresh_dispatch:
        # Reuse the otherwise idle primary generation field as the identity of
        # the video session that armed ACTIVE_STATE.  Clearing before sampling
        # makes a missing handle fail closed.
        a.emit("C7 85"); a.u32(CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD); a.u32(0)
    emit_elapsed_ms("primary", CLOCK_PRIMARY_OFFSET, PRIMARY_HANDLE)
    emit_elapsed_ms("secondary", CLOCK_SECONDARY_OFFSET, SECONDARY_HANDLE)
    a.emit("8B B5"); a.u32(CUE_SLOT_OFFSET)             # mov esi,[ebp+cue slot]
    a.emit("85 F6"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("80 3E 40"); a.branch32(b"\x0F\x85", "no_match")
    a.emit("46 81 3E"); a.emit(KSX_MAGIC); a.branch32(b"\x0F\x85", "no_match")
    a.emit("80 7E 04 02"); a.branch32(b"\x0F\x85", "no_match")
    a.emit("80 7E 05 A5"); a.branch32(b"\x0F\x85", "no_match")
    a.emit("80 7E 06 0C"); a.branch32(b"\x0F\x85", "no_match")
    a.emit("80 7E 07 A5"); a.branch32(b"\x0F\x85", "no_match")
    # Decode the cue descriptor's total length, keep its exclusive end in EBX,
    # and pin it below the H2K3 slot table.  The byte at that end must be the
    # outer descriptor terminator.
    a.emit("0F B7 46 0A 66 35 A5 A5 0F B7 C0 83 F8 0C")
    a.branch32(b"\x0F\x82", "no_match")
    a.emit("8D 1C 06 39 F3"); a.branch32(b"\x0F\x82", "no_match")
    a.emit("8D 95"); a.u32(SLOT_OFFSET)
    a.emit("39 D3"); a.branch32(b"\x0F\x87", "no_match")
    a.emit("80 3B 00"); a.branch32(b"\x0F\x85", "no_match")
    a.emit("0F B7 4E 08 66 81 F1 A5 A5 0F B7 C9 85 C9")
    a.branch32(b"\x0F\x84", "no_match")
    a.emit("8D 76 0C 89 F7 51")                         # first row; save count

    # Validate the complete cue directory before using even the first match.
    # Thus a semantically malformed, but outer-H2K3-checksummed, KSX2 block
    # still disables subtitles atomically.
    a.label("validate_loop")
    a.emit("85 C9"); a.branch8(0x74, "validated")
    a.emit("8D 46 0C 39 D8"); a.branch8(0x77, "invalid_cues")
    a.emit("8A 46 01 34 A5 2C 03 3C 01"); a.branch8(0x77, "invalid_cues")
    a.emit("8B 46 02 35 A5 A5 A5 A5 8B 56 06 81 F2 A5 A5 A5 A5 39 D0")
    a.branch8(0x73, "invalid_cues")
    a.emit("0F B7 46 0A 66 35 A5 A5 0F B7 C0 85 C0")
    a.branch8(0x74, "invalid_cues")
    a.emit("3D"); a.u32(TEXT_BUFFER_LIMIT - 1)
    a.branch8(0x77, "invalid_cues")
    a.emit("8D 54 06 0C 39 DA"); a.branch8(0x77, "invalid_cues")
    a.emit("89 D6 49"); a.branch8(0xEB, "validate_loop")
    a.label("validated")
    a.emit("39 DE"); a.branch8(0x75, "invalid_cues")
    a.emit("59 89 FE")                                      # restore count/first row
    a.branch8(0xEB, "cue_loop")
    a.label("invalid_cues")
    a.emit("59")
    a.branch32(b"\xE9", "no_match")

    a.label("cue_loop")
    a.emit("85 C9"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("8D 46 0C 39 D8"); a.branch32(b"\x0F\x87", "no_match")
    a.emit("51 8A 06 34 A5 3A 05"); a.u32(SCENE_BYTE)
    a.branch32(b"\x0F\x85", "next")
    a.emit("8A 46 01 34 A5 3C 03"); a.branch8(0x74, "primary_ms")
    a.emit("3C 04"); a.branch32(b"\x0F\x85", "next")
    a.emit("8D BD"); a.u32(CLOCK_SECONDARY_OFFSET)
    a.branch8(0xEB, "ms_clock")
    a.label("primary_ms")
    a.emit("8D BD"); a.u32(CLOCK_PRIMARY_OFFSET)
    a.label("ms_clock")
    a.emit("80 7F 1C 01"); a.branch32(b"\x0F\x85", "next")
    a.emit("8B 47 18")                                      # eax=selected handle elapsed ms
    a.label("timeline")
    a.emit("8B 56 02 81 F2 A5 A5 A5 A5 39 D0")
    a.branch32(b"\x0F\x82", "next")                  # frame < start
    a.emit("8B 56 06 81 F2 A5 A5 A5 A5 39 D0")
    a.branch32(b"\x0F\x83", "next")                  # frame >= end
    a.emit("0F B7 4E 0A 66 81 F1 A5 A5 85 C9")
    a.branch8(0x74, "abort_pop")
    a.emit("81 F9"); a.u32(TEXT_BUFFER_LIMIT - 1)
    a.branch8(0x77, "abort_pop")
    a.emit("8D 44 0E 0C 39 D8")
    a.branch8(0x77, "abort_pop")
    a.emit("8D 76 0C 8D BD"); a.u32(TEXT_BUFFER_OFFSET)
    a.emit("FC F3 A4 C6 07 00 59")                     # copy; NUL; discard saved count
    a.branch32(b"\xE9", "render")

    a.label("next")
    a.emit("0F B7 46 0A 66 35 A5 A5 0F B7 C0 3D")
    a.u32(TEXT_BUFFER_LIMIT - 1)
    a.branch8(0x77, "abort_pop")
    a.emit("8D 54 06 0C 39 DA")
    a.branch8(0x77, "abort_pop")
    a.emit("89 D6 59 49")
    a.branch32(b"\xE9", "cue_loop")
    a.label("abort_pop")
    a.emit("59")
    a.branch32(b"\xE9", "no_match")

    a.label("render")
    a.emit("A1"); a.u32(SUBTITLE_FONT_OBJECT)
    a.emit("85 C0"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("A1"); a.u32(SURFACE_OWNER)
    a.emit("85 C0"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("8B 40 46 85 C0"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("8B 50 16 85 D2"); a.branch32(b"\x0F\x84", "no_match")
    a.emit("50 52 FC")                                      # save S/P; cld
    a.emit("8D B2"); a.u32(FRAMEBUFFER_BAND_OFFSET)
    a.emit("8D BD"); a.u32(SCRATCH_OFFSET)
    a.emit("B9"); a.u32(SUBTITLE_BYTES // 4)
    a.emit("F3 A5")                                         # save clean band

    # Watcom text ABI: EAX font, EDX text, EBX x, ECX y;
    # callee-clean stack width, height, style, alignment.  The native draw is
    # deliberately confined to a 280x32 two-line staging cell; the helper
    # below turns its bright font core into a centered 560x64 overlay with a
    # stable one-output-pixel black outline.
    a.emit("6A 01 6A 01 6A"); a.u8(SOURCE_HEIGHT); a.emit("68"); a.u32(SOURCE_WIDTH)
    a.emit("A1"); a.u32(SUBTITLE_FONT_OBJECT)
    a.emit("8D 95"); a.u32(TEXT_BUFFER_OFFSET)
    a.emit("BB"); a.u32(SOURCE_X)
    a.emit("B9"); a.u32(SOURCE_Y)
    # Keep the approved main renderer byte length unchanged: replace the
    # seven-byte indirect TEXT_DRAW call with a five-byte relative helper call
    # plus two NOPs.  Thus every timing/cue and no-match branch target remains
    # at its manually approved offset.
    a.branch32(b"\xE8", "scale_helper")
    a.emit("90 90")

    # RECT_REFRESH consumes counts, not inclusive maxima: exactly 640x68.
    a.emit("8B 44 24 04 68"); a.u32(SUBTITLE_Y)
    a.emit("6A 00 6A"); a.u8(refresh_height); a.emit("31 D2 BB"); a.u32(SUBTITLE_Y)
    a.emit("B9"); a.u32(VIDEO_WIDTH)
    a.emit("BF"); a.u32(RECT_REFRESH_ACTUAL)
    a.emit("FF D7")                                         # call edi; ret 0x0C

    # Restore the clean backing pixels without another refresh.  Smacker's
    # next delta frame therefore never sees subtitle pixels as source data.
    a.emit("5A 58 1E 07 FC 8B 2D"); a.u32(BANK_CONTROL)
    a.emit("8D BA"); a.u32(FRAMEBUFFER_BAND_OFFSET)
    a.emit("8D B5"); a.u32(SCRATCH_OFFSET)
    a.emit("B9"); a.u32(SUBTITLE_BYTES // 4)
    a.emit("F3 A5")
    a.emit("C6 85"); a.u32(ACTIVE_STATE_OFFSET); a.u8(1)
    a.branch8(0xEB, "done")

    # The inner Smacker refresh is clipped above this band once the runtime is
    # active, so every late tick publishes the clean band even when there is no
    # cue.  This replaces the former clean-video then subtitle double refresh
    # with one final band publication and keeps uncued movie frames current.
    a.label("no_match")
    a.emit("A1"); a.u32(SURFACE_OWNER)
    a.emit("85 C0"); a.branch8(0x74, "done")
    a.emit("8B 40 46 85 C0"); a.branch8(0x74, "done")
    a.emit("8B 50 16 85 D2"); a.branch8(0x74, "done")
    a.emit("68"); a.u32(SUBTITLE_Y)
    a.emit("6A 00 6A"); a.u8(refresh_height); a.emit("31 D2 BB"); a.u32(SUBTITLE_Y)
    a.emit("B9"); a.u32(VIDEO_WIDTH)
    a.emit("BF"); a.u32(RECT_REFRESH_ACTUAL)
    a.emit("FF D7")
    a.emit("8B 2D"); a.u32(BANK_CONTROL)
    a.emit("85 ED"); a.branch8(0x74, "done")
    a.emit("C6 85"); a.u32(ACTIVE_STATE_OFFSET); a.u8(0)
    a.label("done")
    a.emit("07 1F C3")                                     # restore ES/DS; return to wrapper
    main_runtime_length = a.offset

    # This helper is unreachable by fall-through because the approved main
    # runtime has already returned.  The relative call above enters after the
    # signature, invokes the native font renderer with its original ABI, then
    # snapshots the 280x32 result, restores the clean video, and converts the
    # font's bright grayscale core to fixed movie-white 2x2 blocks surrounded
    # by a one-pixel movie-black outline.  FONT.ICN never uses palette index
    # 0xFF for an opaque pixel, so the staging sentinel remains unambiguous;
    # output index 0xFF is assigned only after that test.
    a.emit("EB 04")
    a.emit(SCALE_SIGNATURE)
    a.label("scale_helper")

    # Preserve every Watcom register argument, make the native staging cell a
    # palette-independent transparent sentinel, then restore the arguments.
    # PUSHAD moves the saved framebuffer from helper ESP+20 to ESP+52 (0x34).
    a.emit("60 1E 07 FC")
    # Record whether this cue contains an explicit second line.  A single-line
    # cue keeps the user-approved y=424 position; only true two-line cues use
    # the full cell beginning at y=408.  PUSHAD preserves the original text
    # pointer and every TEXT_DRAW register argument while this scan runs.
    a.emit("89 D6 8B 2D"); a.u32(BANK_CONTROL)
    a.emit("C6 85"); a.u32(LAYOUT_FLAG_OFFSET); a.u8(0)
    a.label("scan_layout_line")
    a.emit("8A 06 84 C0"); a.branch8(0x74, "layout_scan_done")
    a.emit("3C 0A"); a.branch8(0x74, "layout_two_lines")
    a.emit("46"); a.branch8(0xEB, "scan_layout_line")
    a.label("layout_two_lines")
    a.emit("C6 85"); a.u32(LAYOUT_FLAG_OFFSET); a.u8(1)
    a.label("layout_scan_done")
    a.emit("8B 7C 24 34 81 C7"); a.u32(SOURCE_FRAMEBUFFER_OFFSET)
    a.emit("B8"); a.u32(STAGING_SENTINEL * 0x01010101)
    a.emit("BA"); a.u32(SOURCE_HEIGHT)
    a.label("fill_scale_source_row")
    a.emit("B9"); a.u32(SOURCE_WIDTH // 4)
    a.emit("F3 AB 81 C7"); a.u32(VIDEO_WIDTH - SOURCE_WIDTH)
    a.emit("4A"); a.branch8(0x75, "fill_scale_source_row")
    a.emit("61")

    # Remove our own return address while forwarding the untouched Watcom
    # stack arguments.  EBP is callee-saved; pushing it back after TEXT_DRAW
    # recreates an ordinary helper frame so the final RET resumes the caller.
    a.emit("5D")
    a.emit("BF"); a.u32(TEXT_DRAW_ACTUAL)
    a.emit("FF D7")                                         # native callee cleans 16 argument bytes
    a.emit("55")
    a.emit("1E 07 FC")                                      # engine call may change ES/DF
    a.emit("8B 2D"); a.u32(BANK_CONTROL)

    # Compact the rendered native staging rectangle to B+GLYPH_SCRATCH_OFFSET.
    # At this point helper [ESP+4] is the saved framebuffer pointer.
    a.emit("8B 74 24 04 81 C6"); a.u32(SOURCE_FRAMEBUFFER_OFFSET)
    a.emit("8D BD"); a.u32(GLYPH_SCRATCH_OFFSET)
    a.emit("BA"); a.u32(SOURCE_HEIGHT)
    a.label("capture_scale_source_row")
    a.emit("B9"); a.u32(SOURCE_WIDTH // 4)
    a.emit("F3 A5 81 C6"); a.u32(VIDEO_WIDTH - SOURCE_WIDTH)
    a.emit("4A"); a.branch8(0x75, "capture_scale_source_row")

    # Remove the native-size staging draw before composing the enlarged text.
    a.emit("8B 7C 24 04 81 C7"); a.u32(FRAMEBUFFER_BAND_OFFSET)
    a.emit("8D B5"); a.u32(SCRATCH_OFFSET)
    a.emit("B9"); a.u32(SUBTITLE_BYTES // 4)
    a.emit("F3 A5")

    # First pass: synthesize a one-output-pixel black outline around every 2x2
    # foreground block.  Four zero dwords form a 4x4 square; the second pass
    # overwrites its center 2x2 with white.  The saved band includes a guard
    # row above and below the 560x64 cell.
    a.emit("8D B5"); a.u32(GLYPH_SCRATCH_OFFSET)
    a.emit("8B 7C 24 04 81 C7"); a.u32(VIDEO_WIDTH * SCALED_Y + SCALED_X)
    a.emit("BA"); a.u32(SOURCE_HEIGHT)
    a.emit("A1"); a.u32(BANK_CONTROL)
    a.emit("80 B8"); a.u32(LAYOUT_FLAG_OFFSET); a.u8(1)
    a.branch8(0x74, "outline_output_y_ready")
    a.emit("81 C7"); a.u32(VIDEO_WIDTH * (SINGLE_LINE_SCALED_Y - SCALED_Y))
    a.emit("BA"); a.u32(SUBTITLE_FONT_LINE_BOX)
    a.label("outline_output_y_ready")
    a.label("outline_row")
    a.emit("B9"); a.u32(SOURCE_WIDTH)
    a.label("outline_pixel")
    a.emit("8A 06 3C"); a.u8(STAGING_SENTINEL)
    a.branch8(0x74, "outline_pixel_done")
    a.emit("3C"); a.u8(SOURCE_INK_PALETTE_MIN)
    a.branch8(0x72, "outline_pixel_done")
    a.emit("3C"); a.u8(SOURCE_INK_PALETTE_MAX)
    a.branch8(0x77, "outline_pixel_done")
    for offset in (-VIDEO_WIDTH - 1, -1, VIDEO_WIDTH - 1, VIDEO_WIDTH * 2 - 1):
        a.emit("C7 87"); a.u32(offset); a.u32(SUBTITLE_OUTLINE_PALETTE_INDEX)
    a.label("outline_pixel_done")
    a.emit("46 83 C7 02 49")                                # next source pixel / 2 output pixels
    a.branch32(b"\x0F\x85", "outline_pixel")
    a.emit("81 C7"); a.u32(VIDEO_WIDTH * SCALE_REPEAT - SCALED_WIDTH)
    a.emit("4A")                                             # next source row / 2 output rows
    a.branch32(b"\x0F\x85", "outline_row")

    # Second pass: write only the bright native core as fixed white.  Native
    # palette 21 (the old +1,+1 UI shadow) and the dark antialias fringe never
    # reach the movie surface, eliminating the enlarged duplicate-letter look.
    a.emit("8D B5"); a.u32(GLYPH_SCRATCH_OFFSET)
    a.emit("8B 7C 24 04 81 C7"); a.u32(VIDEO_WIDTH * SCALED_Y + SCALED_X)
    a.emit("BA"); a.u32(SOURCE_HEIGHT)
    a.emit("A1"); a.u32(BANK_CONTROL)
    a.emit("80 B8"); a.u32(LAYOUT_FLAG_OFFSET); a.u8(1)
    a.branch8(0x74, "scale_output_y_ready")
    a.emit("81 C7"); a.u32(VIDEO_WIDTH * (SINGLE_LINE_SCALED_Y - SCALED_Y))
    a.emit("BA"); a.u32(SUBTITLE_FONT_LINE_BOX)
    a.label("scale_output_y_ready")
    a.label("scale_row")
    a.emit("B9"); a.u32(SOURCE_WIDTH)
    a.label("scale_pixel")
    a.emit("8A 06 3C"); a.u8(STAGING_SENTINEL)
    a.branch8(0x74, "scale_pixel_done")
    a.emit("3C"); a.u8(SOURCE_INK_PALETTE_MIN)
    a.branch8(0x72, "scale_pixel_done")
    a.emit("3C"); a.u8(SOURCE_INK_PALETTE_MAX)
    a.branch8(0x77, "scale_pixel_done")
    a.emit("B0"); a.u8(SUBTITLE_FOREGROUND_PALETTE_INDEX)
    a.emit("88 07 88 47 01")
    for offset in (VIDEO_WIDTH, VIDEO_WIDTH + 1):
        a.emit("88 87"); a.u32(offset)
    a.label("scale_pixel_done")
    a.emit("46 83 C7 02 49")
    a.branch8(0x75, "scale_pixel")
    a.emit("81 C7"); a.u32(VIDEO_WIDTH * SCALE_REPEAT - SCALED_WIDTH)
    a.emit("4A")
    a.branch8(0x75, "scale_row")
    a.emit("C3")

    # Tail-called in place of the Smacker wrapper's RECT_REFRESH.  Rectangles
    # that overlap the subtitle band are clipped to its top edge; rectangles
    # wholly inside the band are deferred completely.  The original ABI is
    # retained (EAX surface, EDX/EBX/ECX x/y/width, three callee-clean stack
    # arguments), and the late runtime owns the single band publication.
    a.emit("EB 04")
    a.emit(REFRESH_CLIP_SIGNATURE)
    a.label("refresh_clip")
    if safe_refresh_dispatch:
        # Preserve RECT_REFRESH's EAX surface argument while gating the clip.
        # Only a narrated scene with a valid bank and an already-active cue may
        # suppress the clean subtitle band.  The first cue frame therefore
        # takes the original publication path; subsequent cue frames are
        # single-published by the late runtime.  A scene transition or cue end
        # fails back to the original stateful function.
        a.emit("50 57")
        a.emit("A0"); a.u32(SCENE_BYTE)
        a.emit("2C"); a.u8(VIDEO_SCENE_MIN)
        a.emit("3C"); a.u8(VIDEO_SCENE_MAX - VIDEO_SCENE_MIN)
        a.branch8(0x77, "refresh_clip_original")
        a.emit("8B 3D"); a.u32(BANK_CONTROL)
        a.emit("85 FF"); a.branch8(0x74, "refresh_clip_original")
        a.emit("80 BF"); a.u32(ACTIVE_STATE_OFFSET); a.u8(1)
        a.branch8(0x75, "refresh_clip_original")
        a.emit("8B BF"); a.u32(CLOCK_PRIMARY_OFFSET + CLOCK_GENERATION_FIELD)
        a.emit("85 FF"); a.branch8(0x74, "refresh_clip_original")
        a.emit("A1"); a.u32(PRIMARY_HANDLE)
        a.emit("85 C0"); a.branch8(0x74, "refresh_clip_original")
        a.emit("8B 80"); a.u32(SMACK_START_TICK_FIELD)
        a.emit("39 F8"); a.branch8(0x75, "refresh_clip_original")
        a.emit("5F 58")
    a.emit("81 FB"); a.u32(SUBTITLE_Y)
    a.branch8(0x73, "refresh_clip_defer")
    a.emit("57 BF"); a.u32(SUBTITLE_Y)                       # preserve EDI; top edge
    a.emit("29 DF")                                         # available height = top - y
    # RECT_REFRESH's first stack argument is height.  At helper entry it is
    # [ESP+4]; preserving EDI moves it to [ESP+8].  The later two arguments
    # are x/y destinations and must never be rewritten.
    a.emit("39 7C 24 08")
    a.branch8(0x76, "refresh_clip_forward")
    a.emit("89 7C 24 08")
    a.label("refresh_clip_forward")
    a.emit("5F 68"); a.u32(RECT_REFRESH_ACTUAL); a.emit("C3")
    a.label("refresh_clip_defer")
    a.emit("C2 0C 00")
    if safe_refresh_dispatch:
        a.label("refresh_clip_original")
        a.emit("5F 58 68"); a.u32(RECT_REFRESH_ACTUAL); a.emit("C3")
    else:
        a.emit("C3")                                         # unreachable identity terminator

    # The already field-tested D executable decrypts exactly 1,856 bytes.
    # Keep that bootstrap contract byte-exact while allowing the BIN-hosted
    # runtime implementation to shrink; trailing NOPs are unreachable after
    # the refresh helper's RET and remain non-NUL after XOR 0x0D encryption.
    require(a.offset <= D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "heap runtime exceeds the D bootstrap payload length")
    a.emit(bytes((RUNTIME_PADDING_BYTE,)) * (D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH - a.offset))

    result_array = bytearray(a.finish())
    if safe_refresh_dispatch:
        require(dispatch_helper_offset_patch is not None, "safe refresh dispatch immediate was not emitted")
        helper_offset = a.labels["refresh_clip"]
        struct.pack_into("<I", result_array, dispatch_helper_offset_patch, helper_offset)
    result = bytes(result_array)
    require(result[:6] == b"\xEB\x04" + CODE_SIGNATURE, "heap runtime signature changed")
    require(main_runtime_length < 0x1000, "KSX2 main runtime unexpectedly exceeds one page")
    require(result[main_runtime_length : main_runtime_length + 6] == b"\xEB\x04" + SCALE_SIGNATURE, "2x helper marker changed")
    require(result.count(b"\xEB\x04" + REFRESH_CLIP_SIGNATURE) == 1, "video refresh clip helper marker changed")
    require(len(result) == D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "heap runtime no longer matches the D bootstrap payload length")
    require(TEXT_BUFFER_OFFSET + TEXT_BUFFER_LIMIT == CLOCK_PRIMARY_OFFSET, "clock state no longer follows text buffer")
    require(CLOCK_PRIMARY_OFFSET + CLOCK_STATE_SIZE <= CLOCK_SECONDARY_OFFSET, "primary/secondary clock state overlaps")
    require(CLOCK_SECONDARY_OFFSET + CLOCK_STATE_SIZE <= CLOCK_STATE_END <= SCRATCH_OFFSET, "clock state escaped reserved gap")
    require((CLOCK_STATE_END - CLOCK_PRIMARY_OFFSET) % 4 == 0, "clock state zero-fill is not dword aligned")
    require(SOURCE_WIDTH % 4 == 0 and SUBTITLE_BYTES % 4 == 0, "REP MOVS regions are not dword aligned")
    require(
        SUBTITLE_SCALE_DENOMINATOR == 1
        and SUBTITLE_SCALE_NUMERATOR == SCALE_REPEAT == 2,
        "2x fixed repeat contract changed",
    )
    require(
        SOURCE_WIDTH * SCALE_REPEAT == SCALED_WIDTH
        and SOURCE_HEIGHT * SCALE_REPEAT == SCALED_HEIGHT,
        "2x repeat totals do not match the scaled cell",
    )
    require(SOURCE_Y >= SUBTITLE_Y and SOURCE_Y + SOURCE_HEIGHT <= SUBTITLE_Y + SUBTITLE_HEIGHT, "native staging escaped saved band")
    require(SCALED_WIDTH == 560 and SCALED_X + SCALED_WIDTH <= VIDEO_WIDTH, "scaled subtitle escaped screen width")
    require(SCALED_Y >= SUBTITLE_Y and SCALED_Y + SCALED_HEIGHT <= SUBTITLE_Y + SUBTITLE_HEIGHT, "scaled subtitle escaped saved band")
    require(SCALED_X >= SUBTITLE_OUTLINE_PIXELS and SCALED_X + SCALED_WIDTH + SUBTITLE_OUTLINE_PIXELS <= VIDEO_WIDTH, "subtitle outline escaped screen width")
    require(SCALED_Y - SUBTITLE_OUTLINE_PIXELS >= SUBTITLE_Y and SCALED_Y + SCALED_HEIGHT + SUBTITLE_OUTLINE_PIXELS <= SUBTITLE_Y + SUBTITLE_HEIGHT, "subtitle outline escaped saved band")
    require(LAYOUT_FLAG_OFFSET + 1 <= ALLOCATION_SIZE, "2x scratch/layout flag escaped allocation")
    if safe_refresh_dispatch:
        verify_safe_refresh_runtime_contract(result)
    else:
        verify_scaled_runtime_contract(result)
    return result



def choose_xor_key(payload: bytes) -> int:
    for key in range(1, 256):
        if key not in payload:
            encrypted = bytes(value ^ key for value in payload)
            if b"\0" not in encrypted:
                return key
    raise BuildError("no NUL-free XOR key exists for heap runtime")



def build_bootstrap(payload_length: int, xor_key: int) -> bytes:
    a = Assembler(CAVE_PREFERRED)
    # This late CALL wrapper runs only after the primary and optional secondary
    # frame paths converge.  The displaced target is a pinned single RET with
    # no arguments, so a normal CALL/RET relay preserves its exact ABI.
    a.call_absolute(ORIGINAL_POST_VIDEO_ROUTINE)
    a.emit("9C 60")                                        # preserve returned flags/registers
    # Startup logos (scene 0..3) reach this call site before the subtitle bank
    # is guaranteed ready.  Narrated original/expansion videos occupy the
    # compact scene range 0x04..0x3F; non-cued scenes inside it fail closed in
    # the heap lookup.
    a.emit("A0"); a.u32(SCENE_BYTE)
    a.emit("2C"); a.u8(VIDEO_SCENE_MIN)
    a.emit("3C"); a.u8(VIDEO_SCENE_MAX - VIDEO_SCENE_MIN)
    a.branch8(0x77, "restore")
    a.emit("8B 1D"); a.u32(BANK_CONTROL)
    a.emit("85 DB"); a.branch8(0x74, "restore")
    a.emit("8B 83"); a.u32(CODE_SLOT_OFFSET)
    a.emit("85 C0"); a.branch8(0x74, "restore")
    a.emit("80 38 40"); a.branch8(0x75, "already")
    a.emit("80 B8"); a.u32(payload_length + 1); a.u8(0)
    a.branch8(0x75, "invalid")
    a.emit("8D 70 01 B9"); a.u32(payload_length)
    a.emit("B2"); a.u8(xor_key)
    a.label("decode")
    a.emit("30 16 46"); a.branch8(0xE2, "decode")
    a.emit("40 81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x75, "invalid")
    a.emit("89 83"); a.u32(CODE_SLOT_OFFSET)
    a.branch8(0xEB, "invoke")
    a.label("already")
    a.emit("81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x75, "invalid")
    a.label("invoke")
    a.emit("FF D0")                                        # call eax
    a.branch8(0xEB, "restore")
    a.label("invalid")
    a.emit("31 C0 89 83"); a.u32(CODE_SLOT_OFFSET)
    a.label("restore")
    a.emit("61 9D C3")                                     # restore displaced-call result; return
    result = a.finish()
    require(len(result) <= CAVE_CAPACITY, f"bootstrap is {len(result)} bytes; cave is {CAVE_CAPACITY}")
    return result



def build_safe_refresh_bootstrap(payload_length: int, xor_key: int) -> bytes:
    """Build the D-equivalent bootstrap while reserving six bridge bytes.

    The descriptor terminator is checked through ``[ESI+ECX]`` before any XOR
    mutation.  With ESI at ``marker+1`` and ECX at the exact payload length,
    this preserves the original fail-before-mutation guard while saving three
    instruction bytes.
    """

    a = Assembler(CAVE_PREFERRED)
    a.call_absolute(ORIGINAL_POST_VIDEO_ROUTINE)
    a.emit("9C 60")
    a.emit("A0"); a.u32(SCENE_BYTE)
    a.emit("2C"); a.u8(VIDEO_SCENE_MIN)
    a.emit("3C"); a.u8(VIDEO_SCENE_MAX - VIDEO_SCENE_MIN)
    a.branch8(0x77, "restore")
    a.emit("8B 1D"); a.u32(BANK_CONTROL)
    a.emit("85 DB"); a.branch8(0x74, "restore")
    a.emit("8B 83"); a.u32(CODE_SLOT_OFFSET)
    a.emit("85 C0"); a.branch8(0x74, "restore")
    a.emit("80 38 40"); a.branch8(0x75, "already")
    a.emit("8D 70 01 B9"); a.u32(payload_length)
    a.emit("80 3C 0E 00"); a.branch8(0x75, "invalid")
    a.emit("B2"); a.u8(xor_key)
    a.label("decode")
    a.emit("30 16 46"); a.branch8(0xE2, "decode")
    a.emit("40 81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x75, "invalid")
    a.emit("89 83"); a.u32(CODE_SLOT_OFFSET)
    a.branch8(0xEB, "invoke")
    a.label("already")
    a.emit("81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x75, "invalid")
    a.label("invoke")
    a.emit("FF D0")
    a.branch8(0xEB, "restore")
    a.label("invalid")
    a.emit("31 C0 89 83"); a.u32(CODE_SLOT_OFFSET)
    a.label("restore")
    a.emit("61 9D C3")
    result = a.finish()
    require(
        len(result) <= CAVE_CAPACITY - SAFE_REFRESH_BRIDGE_SIZE,
        f"safe bootstrap is {len(result)} bytes; only {CAVE_CAPACITY - SAFE_REFRESH_BRIDGE_SIZE} are available",
    )
    return result



def build_safe_refresh_bridge() -> bytes:
    """Return ``jmp dword ptr [dispatch]`` for the original Smacker CALL."""

    result = b"\xFF\x25" + struct.pack("<I", SAFE_REFRESH_DISPATCH_POINTER)
    require(len(result) == SAFE_REFRESH_BRIDGE_SIZE, "safe refresh bridge size changed")
    return result


def build_subtitle_bank(source: bytes, cues: Sequence[Cue], encrypted_runtime: bytes) -> bytes:
    """Append the KSX2 cue and KSXR code descriptors to beta6 KOREAN.BIN."""

    require(identity(source) == SOURCE_BANK_ID, "input is not the pinned beta6 KOREAN.BIN")
    require(len(encrypted_runtime) == D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "runtime descriptor length changed")
    require(b"\0" not in encrypted_runtime, "encrypted runtime descriptor contains NUL")
    parsed = parse_bank(
        source,
        expected_mapping_tag=MAPPING_TAG,
        unit_start=PARSE_TARGET_START,
        unit_end=PARSE_TARGET_END,
    )
    require((len(parsed.descriptors), len(parsed.render_rows)) == (OLD_DESCRIPTOR_COUNT, OLD_RENDER_COUNT), "beta6 bank shape changed")
    reserved = {ACTIVE_STATE_TOKEN, CLOCK_INIT_TOKEN, CUE_TOKEN, CODE_TOKEN}
    require(not any(row.token in reserved for row in parsed.render_rows), "a reserved subtitle slot already has a render owner")
    require(not any(row.target in reserved for row in parsed.descriptors), "a reserved subtitle slot already has a descriptor owner")

    cue_blob = serialize_cues(cues)
    render_rows = [(row.prefix, row.token) for row in parsed.render_rows]
    render_rows.extend(((CUE_PREFIX, CUE_TOKEN), (CODE_PREFIX, CODE_TOKEN)))
    descriptors = [(row.target, row.expected, row.encoded) for row in parsed.descriptors]
    descriptors.extend(((CUE_TOKEN, 0, cue_blob), (CODE_TOKEN, 0, encrypted_runtime)))
    output, _rows, _descriptors = serialize_bank(
        render_rows,
        descriptors,
        mapping_tag=MAPPING_TAG,
        unit_start=PARSE_TARGET_START,
        unit_end=PARSE_TARGET_END,
    )
    reparsed = parse_bank(
        output,
        expected_mapping_tag=MAPPING_TAG,
        unit_start=PARSE_TARGET_START,
        unit_end=PARSE_TARGET_END,
    )
    require(len(output) <= 0xFEFF, "subtitle bank exceeds the DOS one-read limit")
    require((len(reparsed.descriptors), len(reparsed.render_rows)) == (180, 18), "subtitle bank shape changed")
    require(
        [(row.target, row.expected, row.encoded) for row in reparsed.descriptors[:OLD_DESCRIPTOR_COUNT]]
        == [(row.target, row.expected, row.encoded) for row in parsed.descriptors],
        "an existing beta6 bank descriptor changed",
    )
    require(
        [(row.prefix, row.token) for row in reparsed.render_rows[:OLD_RENDER_COUNT]]
        == [(row.prefix, row.token) for row in parsed.render_rows],
        "an existing beta6 render row changed",
    )
    return output


def _patch_file_ranges(source: bytes, image: LeImage) -> dict[str, tuple[int, int]]:
    offsets = {
        "late_call": image.object_to_file(1, CALL_SITE_OBJECT_OFFSET),
        "video_call": image.object_to_file(1, VIDEO_REFRESH_CALL_OBJECT_OFFSET),
        "video_context": image.object_to_file(1, VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET),
        "post_video": image.object_to_file(1, ORIGINAL_POST_VIDEO_OBJECT_OFFSET),
        "primary_call": image.object_to_file(1, PRIMARY_FRAME_CALL_OBJECT_OFFSET),
        "secondary_call_a": image.object_to_file(1, SECONDARY_FRAME_CALL_A_OBJECT_OFFSET),
        "secondary_call_b": image.object_to_file(1, SECONDARY_FRAME_CALL_B_OBJECT_OFFSET),
        "caller_argument": image.object_to_file(1, CALLER_ARGUMENT_OBJECT_OFFSET),
        "frame_return": image.object_to_file(1, ORIGINAL_FRAME_RETURN_OBJECT_OFFSET),
        "cave": image.object_to_file(1, CAVE_OBJECT_OFFSET),
        "loader": image.object_to_file(1, H2K3_OBJECT_OFFSET),
        "false_cave": image.object_to_file(1, FALSE_CAVE_OBJECT_OFFSET),
        "dispatch": image.object_to_file(3, SAFE_REFRESH_DISPATCH_OBJECT_OFFSET),
    }
    offsets["malloc"] = offsets["loader"] + MALLOC_INSTRUCTION_OFFSET
    return {
        "late_call": (offsets["late_call"], 5),
        "video_call": (offsets["video_call"], 5),
        "video_context": (offsets["video_context"], len(VIDEO_REFRESH_CALL_CONTEXT)),
        "post_video": (offsets["post_video"], 1),
        "primary_call": (offsets["primary_call"], 5),
        "secondary_call_a": (offsets["secondary_call_a"], 5),
        "secondary_call_b": (offsets["secondary_call_b"], 5),
        "caller_argument": (offsets["caller_argument"], 2),
        "frame_return": (offsets["frame_return"], 3),
        "cave": (offsets["cave"], CAVE_CAPACITY),
        "loader": (offsets["loader"], H2K3_SIZE),
        "malloc": (offsets["malloc"], 5),
        "false_cave": (offsets["false_cave"], FALSE_CAVE_SIZE),
        "dispatch": (offsets["dispatch"], 4),
    }


def patch_executable(source: bytes) -> bytes:
    """Install the late hook and safe active-only refresh dispatcher."""

    require(identity(source) == SOURCE_EXE_ID, "input is not the pinned beta6 HEROES2.EXE")
    image = LeImage(source)
    require(image.objects[0].virtual_size == 0xC5000 and image.page_count == 0xFF, "beta6 LE geometry changed")
    spans = _patch_file_ranges(source, image)

    def source_span(name: str) -> bytes:
        start, length = spans[name]
        return source[start:start + length]

    require(source_span("late_call") == CALL_SITE_ORIGINAL, "late post-video CALL changed")
    require(source_span("video_call") == VIDEO_REFRESH_CALL_ORIGINAL, "Smacker refresh CALL changed")
    require(source_span("video_context") == VIDEO_REFRESH_CALL_CONTEXT, "Smacker refresh call ABI context changed")
    require(source_span("post_video") == ORIGINAL_POST_VIDEO_BYTES, "displaced post-video routine changed")
    require(source_span("primary_call") == PRIMARY_FRAME_CALL_BYTES, "primary frame CALL changed")
    require(source_span("secondary_call_a") == SECONDARY_FRAME_CALL_A_BYTES, "first secondary frame CALL changed")
    require(source_span("secondary_call_b") == SECONDARY_FRAME_CALL_B_BYTES, "second secondary frame CALL changed")
    require(source_span("caller_argument") == CALLER_ARGUMENT_BYTES, "caller zero argument changed")
    require(source_span("frame_return") == ORIGINAL_FRAME_RETURN_BYTES, "frame wrapper return ABI changed")
    for offset, expected in LATE_MERGE_BRANCHES.items():
        file_offset = image.object_to_file(1, offset)
        require(source[file_offset:file_offset + len(expected)] == expected, f"late merge branch 0x{offset:X} changed")
    require(sha256(source_span("cave")) == CAVE_SOURCE_SHA256, "reviewed bootstrap cave changed")
    require(sha256(source_span("false_cave")) == FALSE_CAVE_SOURCE_SHA256, "startup metadata source span changed")
    require(source_span("dispatch") == SAFE_REFRESH_DISPATCH_SOURCE, "safe dispatch ownership marker changed")
    require(source_span("malloc") == MALLOC_BEFORE, "H2K3 allocation immediate changed")
    require(spans["cave"][0] + CAVE_CAPACITY == spans["loader"][0], "bootstrap cave no longer borders H2K3 loader")

    fixups = parse_raw_fixups(source, image)
    patched_object_ranges = (
        (1, CALL_SITE_OBJECT_OFFSET, CALL_SITE_OBJECT_OFFSET + 5),
        (1, VIDEO_REFRESH_CALL_OBJECT_OFFSET, VIDEO_REFRESH_CALL_OBJECT_OFFSET + 5),
        (1, CAVE_OBJECT_OFFSET, CAVE_OBJECT_OFFSET + CAVE_CAPACITY),
        (1, H2K3_OBJECT_OFFSET + MALLOC_INSTRUCTION_OFFSET, H2K3_OBJECT_OFFSET + MALLOC_INSTRUCTION_OFFSET + 5),
        (3, SAFE_REFRESH_DISPATCH_OBJECT_OFFSET, SAFE_REFRESH_DISPATCH_OBJECT_OFFSET + 4),
    )
    for owner, start, end in patched_object_ranges:
        require(
            not any(row.source_object == owner and row.source_offset < end and start < row.source_offset + 4 for row in fixups),
            f"EXE patch Object{owner}:0x{start:X} overlaps an LE fixup source",
        )
    require(
        not any(row.target_object == 3 and row.target_offset == SAFE_REFRESH_DISPATCH_OBJECT_OFFSET for row in fixups),
        "safe dispatch marker has an LE fixup consumer",
    )
    source_fixup_blobs = raw_fixup_blobs(source, image)

    runtime = build_heap_runtime(safe_refresh_dispatch=True)
    require(identity(runtime) == SAFE_RUNTIME_ID, "safe subtitle runtime identity changed")
    safe_bootstrap = build_safe_refresh_bootstrap(len(runtime), RUNTIME_XOR_KEY)
    bridge = build_safe_refresh_bridge()
    prefix_capacity = CAVE_CAPACITY - len(bridge)
    require(len(safe_bootstrap) == 106 and len(bridge) == 6, "safe bootstrap/bridge reviewed sizes changed")
    cave = safe_bootstrap.ljust(prefix_capacity, bytes((RUNTIME_PADDING_BYTE,))) + bridge
    require(len(cave) == CAVE_CAPACITY, "safe cave layout changed")

    output = bytearray(source)
    late_call, _ = spans["late_call"]
    output[late_call:late_call + 5] = b"\xE8" + struct.pack("<i", CAVE_PREFERRED - (CALL_SITE_PREFERRED + 5))
    video_call, _ = spans["video_call"]
    output[video_call:video_call + 5] = b"\xE8" + struct.pack("<i", SAFE_REFRESH_BRIDGE_PREFERRED - (VIDEO_REFRESH_CALL_PREFERRED + 5))
    cave_file, _ = spans["cave"]
    output[cave_file:cave_file + CAVE_CAPACITY] = cave
    malloc_file, _ = spans["malloc"]
    output[malloc_file:malloc_file + 5] = MALLOC_AFTER
    dispatch_file, _ = spans["dispatch"]
    output[dispatch_file:dispatch_file + 4] = struct.pack("<I", RECT_REFRESH_ACTUAL)
    result = bytes(output)

    allowed_file_ranges = tuple(
        (spans[name][0], spans[name][0] + spans[name][1])
        for name in ("late_call", "video_call", "cave", "malloc", "dispatch")
    )
    changed = [index for index, pair in enumerate(zip(source, result)) if pair[0] != pair[1]]
    require(len(result) == len(source) and changed, "patched EXE size/change contract failed")
    require(all(any(start <= index < end for start, end in allowed_file_ranges) for index in changed), "EXE byte escaped the patch allowlist")
    require(result[spans["false_cave"][0]:spans["false_cave"][0] + FALSE_CAVE_SIZE] == source_span("false_cave"), "startup metadata source span was not byte-preserved")
    require(raw_fixup_blobs(result, LeImage(result)) == source_fixup_blobs, "LE fixup metadata changed")
    require(identity(result) == FINAL_EXE_ID, "patched EXE does not match the tested final identity")
    return result


def build_artifacts(source_exe: bytes, source_bank: bytes) -> tuple[bytes, bytes, dict[str, object]]:
    mapping = load_subtitle_mapping()
    cues, cue_meta = load_scene_cues(mapping=mapping)
    runtime = build_heap_runtime(safe_refresh_dispatch=True)
    require(identity(runtime) == SAFE_RUNTIME_ID, "safe runtime identity changed")
    encrypted_runtime = bytes(value ^ RUNTIME_XOR_KEY for value in runtime)
    require(b"\0" not in encrypted_runtime, "safe encrypted runtime is not descriptor-safe")
    exe = patch_executable(source_exe)
    bank = build_subtitle_bank(source_bank, cues, encrypted_runtime)
    require(identity(exe) == FINAL_EXE_ID, "final EXE identity mismatch")
    require(identity(bank) == FINAL_BANK_ID, "final KOREAN.BIN identity mismatch")
    report = {
        "verified": True,
        "inputs": {
            "HEROES2.EXE": {"size": SOURCE_EXE_ID[0], "sha256": SOURCE_EXE_ID[1]},
            "KOREAN.BIN": {"size": SOURCE_BANK_ID[0], "sha256": SOURCE_BANK_ID[1]},
            "mapping": {"size": MAPPING_ID[0], "sha256": MAPPING_ID[1]},
            "scene_cues": cue_meta,
        },
        "outputs": {
            "HEROES2.EXE": {"size": len(exe), "sha256": sha256(exe)},
            "KOREAN.BIN": {"size": len(bank), "sha256": sha256(bank)},
        },
        "runtime": {
            "size": len(runtime),
            "sha256": sha256(runtime),
            "xor_key": "0x0D",
            "encrypted_nul_free": True,
        },
        "coverage": {"movies": 51, "scenes": 57, "cues": 388, "primary_ms": 27, "secondary_ms": 361},
        "safety": {
            "startup_metadata_span_byte_preserved": True,
            "le_fixup_metadata_byte_preserved": True,
            "safe_dispatch_pointer": "0x182EAC",
            "safe_dispatch_initial_target": "0x2A4409",
            "active_and_generation_gated_flicker_suppression": True,
        },
    }
    return exe, bank, report


def verify_artifacts(source_exe: bytes, source_bank: bytes, candidate_exe: bytes, candidate_bank: bytes) -> dict[str, object]:
    expected_exe, expected_bank, report = build_artifacts(source_exe, source_bank)
    require(candidate_exe == expected_exe, "candidate HEROES2.EXE is not the canonical final build")
    require(candidate_bank == expected_bank, "candidate KOREAN.BIN is not the canonical final build")
    parsed = parse_bank(
        candidate_bank,
        expected_mapping_tag=MAPPING_TAG,
        unit_start=PARSE_TARGET_START,
        unit_end=PARSE_TARGET_END,
    )
    by_target = {row.target: row for row in parsed.descriptors}
    require(CUE_TOKEN in by_target and CODE_TOKEN in by_target, "subtitle descriptors are missing")
    cues = parse_cues(by_target[CUE_TOKEN].encoded)
    require(len(cues) == 388, "candidate cue count changed")
    runtime = bytes(value ^ RUNTIME_XOR_KEY for value in by_target[CODE_TOKEN].encoded)
    require(identity(runtime) == SAFE_RUNTIME_ID, "candidate runtime identity changed")
    verify_safe_refresh_runtime_contract(runtime)

    image = LeImage(candidate_exe)
    spans = _patch_file_ranges(candidate_exe, image)
    video_call, _ = spans["video_call"]
    displacement = struct.unpack_from("<i", candidate_exe, video_call + 1)[0]
    target = VIDEO_REFRESH_CALL_PREFERRED + 5 + displacement
    require(target == SAFE_REFRESH_BRIDGE_PREFERRED, "Smacker refresh CALL does not target the safe bridge")
    dispatch_file, _ = spans["dispatch"]
    require(candidate_exe[dispatch_file:dispatch_file + 4] == struct.pack("<I", RECT_REFRESH_ACTUAL), "safe dispatch pointer initializer changed")
    report["verified"] = True
    return report


def _refuse_repository_output(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    require(not resolved.is_relative_to(REPO_ROOT.resolve()), "refusing to store proprietary HEROES2.EXE/KOREAN.BIN inside the source repository")
    return resolved


def _prepare_build_output(output_dir: Path, source_exe_path: Path, source_bank_path: Path) -> Path:
    resolved = _refuse_repository_output(output_dir)
    source_parents = {source_exe_path.resolve().parent, source_bank_path.resolve().parent}
    require(resolved not in source_parents, "output directory must not be either source file directory")
    if resolved.exists():
        require(resolved.is_dir(), "output path exists and is not a directory")
        require(not any(resolved.iterdir()), "output directory must be empty")
    else:
        resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def _write_new_bytes(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)


def _write_new_text(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def build_command(source_exe_path: Path, source_bank_path: Path, output_dir: Path) -> dict[str, object]:
    output_dir = _prepare_build_output(output_dir, source_exe_path, source_bank_path)
    exe, bank, report = build_artifacts(source_exe_path.read_bytes(), source_bank_path.read_bytes())
    exe_path = output_dir / "HEROES2.EXE"
    bank_path = output_dir / "KOREAN.BIN"
    manifest_path = output_dir / "video_subtitles_manifest.json"
    _write_new_bytes(exe_path, exe)
    _write_new_bytes(bank_path, bank)
    manifest = {
        "schema": "homm2-korean-video-subtitles-v1",
        "proprietary_outputs_not_for_source_control": True,
        **report,
    }
    _write_new_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def verify_command(source_exe_path: Path, source_bank_path: Path, output_dir: Path) -> dict[str, object]:
    output_dir = _refuse_repository_output(output_dir)
    exe_path = output_dir / "HEROES2.EXE"
    bank_path = output_dir / "KOREAN.BIN"
    require(exe_path.is_file() and bank_path.is_file(), "output directory must contain HEROES2.EXE and KOREAN.BIN")
    return verify_artifacts(
        source_exe_path.read_bytes(),
        source_bank_path.read_bytes(),
        exe_path.read_bytes(),
        bank_path.read_bytes(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--source-exe", type=Path, required=True, help="pinned beta6 HEROES2.EXE")
        subparser.add_argument("--source-bank", type=Path, required=True, help="pinned beta6 KOREAN.BIN")
        subparser.add_argument("--output-dir", type=Path, required=True, help="directory outside this repository")
    args = parser.parse_args()
    try:
        if args.command == "build":
            report = build_command(args.source_exe, args.source_bank, args.output_dir)
        else:
            report = verify_command(args.source_exe, args.source_bank, args.output_dir)
    except (OSError, BuildError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
