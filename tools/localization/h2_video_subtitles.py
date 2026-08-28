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

from h2k3_bank import parse_bank, serialize_bank, token_allowed  # noqa: E402
import homm2_font  # noqa: E402


SOURCE_EXE_ID = (1_523_420, "52AE3BA15AE309327D698EDEE8844684F91B3BA056B9215854002265A9F6E3EF")
SOURCE_BANK_ID = (11_286, "DD30DD967E81BB179BC1D33903D0B8926FB799D969A3C36FFAA6CA3FA0C89AAF")
FINAL_EXE_ID = (1_523_420, "87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365")
FINAL_BANK_ID = (36_159, "37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA")
MAPPING_ID = (42_302, "3033584F6E65A36220F61EA58F8D7173A493FC83A72807D6FB43488AAE6DF164")
CUE_SOURCE_ID = (59_955, "0F5DF72829709851454D73B2A24B8D54752EDE7D96B40C55D86B18BAED136B8E")
STABLE_HEIGHT_RUNTIME_ID = (1_856, "B2EB2965514009DF9DEEDFF276D0471DE41C08B304EE04FDF394E87B0AD00575")
CANONICAL_RUNTIME_ID = (1_856, "9EB151BC4F1AD62AA0EF0BB77A627A96733DCCA9971A4015A6F10D309BBC25E8")
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
OBJECT2_PREFERRED_BASE = 0xE0000
OBJECT3_PREFERRED_BASE = 0x130000
OBJECT1_ACTUAL_BASE = 0x21F000
OBJECT2_ACTUAL_BASE = 0x2E4000
OBJECT3_ACTUAL_BASE = 0x17F000
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
LATE_REFRESH_JOIN_BRANCH_OBJECT_OFFSET = 0x739E8
LATE_REFRESH_JOIN_BRANCH_BYTES = bytes.fromhex("EB 83")
VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET = 0x73953
VIDEO_REFRESH_CALL_CONTEXT = bytes.fromhex(
    "6A 00 6A 00 68 DF 01 00 00 A1 70 AD 03 00 8B 40 46 "
    "B9 7F 02 00 00 31 DB 31 D2 E8 97 1A 01 00"
)
VIDEO_REFRESH_CONTEXT_PREFERRED = OBJECT1_PREFERRED_BASE + VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET
VIDEO_REFRESH_SURFACE_FIXUP_SOURCE = VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET + 10
VIDEO_REFRESH_SURFACE_FIXUP_TARGET_OBJECT = 2
VIDEO_REFRESH_SURFACE_FIXUP_TARGET_OFFSET = 0x3B1C0
REFRESH_CLIP_CAVE_A_OBJECT_OFFSET = 0x956C5
REFRESH_CLIP_CAVE_A_SIZE = 0x0B
REFRESH_CLIP_CAVE_B_OBJECT_OFFSET = 0x95741
REFRESH_CLIP_CAVE_B_SIZE = 0x0F
REFRESH_CLIP_CAVE_C_OBJECT_OFFSET = 0x95755
REFRESH_CLIP_CAVE_C_SIZE = 0x0B
REFRESH_CLIP_HEIGHT_FIXUP_SOURCE = REFRESH_CLIP_CAVE_A_OBJECT_OFFSET + 3
REFRESH_CLIP_CAVE_A_BEFORE = bytes.fromhex("C2 04 00")
REFRESH_CLIP_CAVE_A_AFTER = bytes.fromhex("8B 44 24 08")
REFRESH_CLIP_CAVE_B_BEFORE = b"\xC3"
REFRESH_CLIP_CAVE_B_AFTER = bytes.fromhex("E9 C9 53 01 00")
REFRESH_CLIP_CAVE_C_BEFORE = REFRESH_CLIP_CAVE_B_AFTER
REFRESH_CLIP_CAVE_C_AFTER = bytes.fromhex("56 57 55")
CALLER_ARGUMENT_OBJECT_OFFSET = 0x7400D
CALLER_ARGUMENT_BYTES = bytes.fromhex("6A 00")
ORIGINAL_FRAME_RETURN_OBJECT_OFFSET = 0x739F7
ORIGINAL_FRAME_RETURN_BYTES = bytes.fromhex("C2 04 00")
CAVE_OBJECT_OFFSET = 0xC4E8F
CAVE_PREFERRED = OBJECT1_PREFERRED_BASE + CAVE_OBJECT_OFFSET
CAVE_CAPACITY = 0x71
CAVE_SOURCE_SHA256 = "0A781558AC722EC58738C7C17D3BD92C2B117DE8B306CBA5336A51A795BEA88C"
H2K3_OBJECT_OFFSET = 0xC4F00
H2K3_SIZE = 0x100
MALLOC_INSTRUCTION_OFFSET = 0x2E
MALLOC_BEFORE = bytes.fromhex("B8 00 10 01 00")
MALLOC_AFTER = bytes.fromhex("B8 00 E0 01 00")
FALSE_CAVE_OBJECT_OFFSET = 0x877D6
FALSE_CAVE_SIZE = 0x50
FALSE_CAVE_SOURCE_SHA256 = "B14AB536D0077DA41D57A3E994B78B8226FF935D4E604E1CFDEBE79D48C3FF69"
DESCRIPTOR_VALIDATOR_OBJECT_OFFSET = 0xBEDA0
DESCRIPTOR_VALIDATOR_SIZE = 0x60
DESCRIPTOR_VALIDATOR_SOURCE_SHA256 = "3A54999B4BA34A343929D7A6C7543569072FFCB2BB543AB08EA8FDD0983C3375"
DESCRIPTOR_VALIDATOR_O2_BASE_FIXUP_SOURCE = DESCRIPTOR_VALIDATOR_OBJECT_OFFSET + 0x24
DESCRIPTOR_VALIDATOR_SLOT_FIXUP_SOURCE = DESCRIPTOR_VALIDATOR_OBJECT_OFFSET + 0x33
PORTABLE_GENERAL_TARGET_START = 0x2E920
PORTABLE_GENERAL_TARGET_END = 0x31520
SOURCE_UNIT_TARGET_START = OBJECT2_ACTUAL_BASE + 0x2E71C
SOURCE_UNIT_TARGET_END = OBJECT2_ACTUAL_BASE + 0x2E824
SOURCE_GENERAL_TARGET_START = OBJECT2_ACTUAL_BASE + PORTABLE_GENERAL_TARGET_START
SOURCE_GENERAL_TARGET_END = OBJECT2_ACTUAL_BASE + PORTABLE_GENERAL_TARGET_END
NATIVE_UNIT_DESCRIPTOR_COUNT = 7
PORTABLE_GENERAL_DESCRIPTOR_COUNT = 155

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
STABLE_REFRESH_HEIGHT_OBJECT_OFFSET = 0x3EAC
STABLE_REFRESH_HEIGHT_POINTER = 0x00182EAC
STABLE_REFRESH_HEIGHT_SOURCE = b"H2K3"
FULL_VIDEO_REFRESH_HEIGHT = 0x1DF
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
RUNTIME_RELOC_SIGNATURE = b"RLC1"
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
SOURCE_FIXUP_ROWS = 28_095

# Object3's last 40 bytes are a data-only table.  The LE loader relocates each
# entry for the process's actual object layout; the heap runtime then patches
# its own absolute operands from this table before using any of them.
RUNTIME_RELOC_TABLE_OBJECT_OFFSET = 0x3FD8
RUNTIME_RELOC_TABLE_SIZE = 0x28
RUNTIME_RELOC_TARGETS = (
    ("bank_control", 3, 0x3E90, BANK_CONTROL),
    ("scene_byte", 2, 0x3B22D, SCENE_BYTE),
    ("primary_handle", 2, 0x3B248, PRIMARY_HANDLE),
    ("secondary_handle", 2, 0x3B24C, SECONDARY_HANDLE),
    ("subtitle_font", 2, 0x39550, SUBTITLE_FONT_OBJECT),
    ("surface_owner", 2, 0x3B1C0, SURFACE_OWNER),
    ("timer_provider", 2, 0x32648, TIMER_PROVIDER_POINTER),
    ("text_draw", 1, 0x8905E, TEXT_DRAW_ACTUAL),
    ("rect_refresh", 1, RECT_REFRESH_OBJECT_OFFSET, RECT_REFRESH_ACTUAL),
    ("refresh_boundary", 3, STABLE_REFRESH_HEIGHT_OBJECT_OFFSET, STABLE_REFRESH_HEIGHT_POINTER),
)
STABLE_RUNTIME_RELOC_EXPECTED_COUNTS = (7, 1, 1, 1, 2, 2, 1, 1, 2, 2)
CANONICAL_RUNTIME_RELOC_EXPECTED_COUNTS = (8, 1, 1, 1, 2, 2, 1, 1, 3, 0)

# The pre-existing H2K3 loader used addresses observed in DOSBox-X.  These
# operand locations are now registered as real LE relocations too, so loading
# KOREAN.BIN does not depend on a particular emulator's object bases.
H2K3_ABSOLUTE_RELOCS = (
    (0xBED28, 3, 0x3E94),
    (0xBED2D, 3, 0x3E9D),
    (0xBED61, 3, 0x3E90),
    (0xBED81, 3, 0x3E90),
    (0xC4F08, 3, 0x3E9C),
    (0xC4F15, 3, 0x3E9C),
    (0xC4F1B, 3, 0x3EA0),
    (0xC4F41, 3, 0x3E90),
    (0xC4F4F, 3, 0x3E98),
    (0xC4F78, 3, 0x3E90),
    (0xC4F95, 3, 0x3E94),
    (0xC4FB0, 3, 0x3E9D),
    (0xC4FB6, 3, 0x3E9C),
    (0xC4FD9, 3, 0x3E9C),
    (0xC4FE2, 3, 0x3E9C),
    (0x3F36, 3, 0x3E98, 3),
)
H2K3_RELATIVE_RELOCS = (
    (0xBED4C, 3, 0x3F2C, 1),
    (0xC4F7D, 3, 0x3ED4, 1),
    (0xC4F86, 3, 0x3F45, 1),
    (0x3F41, 1, 0xC4FF0, 3),
    (0x3F5B, 1, 0xBEDA0, 3),
)

# DOS/4GW's source-type-8 path crashes the GOG DOSBox host when these five
# cross-object edges are installed, even though the loader contains a handler
# for that record type.  Keep every branch relative only within its own LE
# object, then cross the object boundary through PUSH imm32 / RET veneers whose
# immediates use the field-tested source-type-7 loader path.
H2K3_VENEER_CAVE_A_OBJECT_OFFSET = 0x8E913
H2K3_VENEER_CAVE_A_SIZE = 0x0D
H2K3_VENEER_CAVE_A_BEFORE = bytes.fromhex("FC E9 43 FF FF FF")
H2K3_VENEER_CAVE_A_AFTER = bytes.fromhex("56 57 55")
H2K3_VENEER_CAVE_B_OBJECT_OFFSET = 0x91F59
H2K3_VENEER_CAVE_B_SIZE = 0x07
H2K3_VENEER_CAVE_B_BEFORE = b"\xC3"
H2K3_VENEER_CAVE_B_AFTER = bytes.fromhex("56 57 55")
H2K3_O1_EDGE_VENEERS = (
    (0xBED4C, 0xE9, H2K3_VENEER_CAVE_A_OBJECT_OFFSET, 3, 0x3F2C),
    (0xC4F7D, 0xE8, H2K3_VENEER_CAVE_A_OBJECT_OFFSET + 6, 3, 0x3ED4),
    (0xC4F86, 0xE8, H2K3_VENEER_CAVE_B_OBJECT_OFFSET, 3, 0x3F46),
)
H2K3_O3_PORTABLE_PATCH_OBJECT_OFFSET = 0x3F40
H2K3_O3_PORTABLE_PATCH_SIZE = 0x24
H2K3_O3_PORTABLE_SOURCE = bytes.fromhex(
    "E9 AB 10 16 00 0F B6 47 0C C1 E0 04 83 C0 20 39 47 14 "
    "75 0D 8D 1C 07 57 89 DE E8 41 AE 15 00 5F C3 B0 01 C3"
)
H2K3_O3_ABSOLUTE_TRANSFER_FIXUPS = (
    (0x3F41, 1, 0xC4FF0),
    (0x3F5C, 1, DESCRIPTOR_VALIDATOR_OBJECT_OFFSET),
)


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
class FixupSpec:
    source_object: int
    source_offset: int
    target_object: int
    target_offset: int
    src: int = 7



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



def parse_raw_fixups(
    raw: bytes,
    image: LeImage,
    *,
    expected_rows: int | None = None,
) -> tuple[Fixup, ...]:
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
            require((src & 0x0F) in (7, 8) and not (src & 0x20), "unsupported LE source form")
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
    if expected_rows is not None:
        require(len(rows) == expected_rows, "LE fixup row count changed")
    return tuple(rows)


def fixup_semantics(row: Fixup) -> tuple[int, int, int, int, int, int, bytes]:
    """Return the loader-visible identity without the record's moving file offset."""

    return (
        row.source_object,
        row.source_offset,
        row.target_object,
        row.target_offset,
        row.src,
        row.flags,
        row.record_bytes,
    )


def _encode_internal_fixup(spec: FixupSpec, image: LeImage) -> bytes:
    # This diagnostic build deliberately installs only ordinary 32-bit offset
    # records.  The five cross-object rel32 operands below stay byte-identical
    # to the known-launching source while we isolate the -05 startup crash.
    require(spec.src == 7, "new LE fixup must be a 32-bit offset")
    require(1 <= spec.source_object <= len(image.objects), "new LE fixup source object is invalid")
    require(1 <= spec.target_object <= len(image.objects), "new LE fixup target object is invalid")
    source_object = image.objects[spec.source_object - 1]
    target_object = image.objects[spec.target_object - 1]
    require(0 <= spec.source_offset and spec.source_offset + 4 <= source_object.virtual_size, "new LE fixup source escaped its object")
    require(0 <= spec.target_offset < target_object.virtual_size, "new LE fixup target escaped its object")
    source_in_page = spec.source_offset % image.page_size
    require(source_in_page + 4 <= image.page_size, "new LE fixup source crosses an LE page")
    flags = 0x10 if spec.target_offset > 0xFFFF else 0
    target = struct.pack("<I" if flags else "<H", spec.target_offset)
    return bytes((spec.src, flags)) + struct.pack("<H", source_in_page) + bytes((spec.target_object,)) + target


def install_internal_fixups(
    raw: bytes,
    image: LeImage,
    specs: Sequence[FixupSpec],
) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    """Append internal LE fixups page-by-page without moving any data page.

    The pinned executable has no imports and 331 zero bytes between the empty
    import-procedure terminator and the first data page.  New records consume
    only that slack.  Existing record bytes stay in their original order.
    """

    require(specs, "at least one LE fixup must be requested")
    require(len(set(specs)) == len(specs), "duplicate new LE fixup requested")
    le = image.le_offset
    fixup_size_offset = le + 0x30
    loader_size_offset = le + 0x38
    page_table_rel = read_u32(raw, le + 0x68)
    record_table_rel = read_u32(raw, le + 0x6C)
    import_module_offset = le + 0x70
    import_count_offset = le + 0x74
    import_proc_offset = le + 0x78
    checksum_table_offset = le + 0x7C
    page_table = le + page_table_rel
    record_base = le + record_table_rel
    old_offsets = [read_u32(raw, page_table + index * 4) for index in range(image.page_count + 1)]
    require(old_offsets[0] == 0 and all(a <= b for a, b in zip(old_offsets, old_offsets[1:])), "source LE fixup page table is invalid")
    old_sentinel = old_offsets[-1]
    old_record_end = record_base + old_sentinel
    old_import_module = read_u32(raw, import_module_offset)
    old_import_proc = read_u32(raw, import_proc_offset)
    old_fixup_size = read_u32(raw, fixup_size_offset)
    old_loader_size = read_u32(raw, loader_size_offset)
    require(read_u32(raw, import_count_offset) == 0, "pinned executable unexpectedly imports modules")
    require(read_u32(raw, checksum_table_offset) == 0, "pinned executable unexpectedly has page checksums")
    require(old_import_module == old_import_proc == old_record_end - le, "empty import tables do not follow the fixup records")
    require(page_table_rel + old_fixup_size == old_import_proc + 1, "fixup section end invariant changed")
    require(image.object_table_offset + old_loader_size == old_import_proc + 1, "loader section end invariant changed")
    require(raw[old_record_end] == 0, "empty import-procedure table lost its terminator")
    require(not any(raw[old_record_end + 1:image.data_base]), "LE metadata slack is not zero-filled")

    existing = parse_raw_fixups(raw, image, expected_rows=SOURCE_FIXUP_ROWS)
    existing_keys = {
        (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src)
        for row in existing
    }
    additions_by_page: dict[int, list[tuple[FixupSpec, bytes]]] = {}
    for spec in specs:
        key = (spec.source_object, spec.source_offset, spec.target_object, spec.target_offset, spec.src)
        require(key not in existing_keys, "new LE fixup already exists")
        source_object = image.objects[spec.source_object - 1]
        logical_page = source_object.page_map_index + spec.source_offset // image.page_size
        require(source_object.page_map_index <= logical_page < source_object.page_map_index + source_object.page_count, "new LE fixup page ownership failed")
        additions_by_page.setdefault(logical_page, []).append((spec, _encode_internal_fixup(spec, image)))

    new_records = bytearray()
    new_offsets = [0]
    encoded_additions: list[bytes] = []
    for logical_page in range(1, image.page_count + 1):
        start, end = old_offsets[logical_page - 1], old_offsets[logical_page]
        new_records.extend(raw[record_base + start:record_base + end])
        page_additions = sorted(additions_by_page.get(logical_page, ()), key=lambda item: item[0].source_offset)
        for _spec, encoded in page_additions:
            new_records.extend(encoded)
            encoded_additions.append(encoded)
        new_offsets.append(len(new_records))

    growth = len(new_records) - old_sentinel
    require(growth == sum(len(item) for item in encoded_additions) > 0, "LE fixup growth accounting failed")
    new_record_end = record_base + len(new_records)
    require(new_record_end + 1 <= image.data_base, "new LE fixups exhausted metadata slack")
    require(not any(raw[old_record_end:image.data_base]), "LE metadata growth would overwrite nonzero bytes")

    output = bytearray(raw)
    for index, value in enumerate(new_offsets):
        struct.pack_into("<I", output, page_table + index * 4, value)
    output[record_base:new_record_end] = new_records
    output[new_record_end] = 0
    struct.pack_into("<I", output, fixup_size_offset, old_fixup_size + growth)
    struct.pack_into("<I", output, loader_size_offset, old_loader_size + growth)
    struct.pack_into("<I", output, import_module_offset, old_import_module + growth)
    struct.pack_into("<I", output, import_proc_offset, old_import_proc + growth)
    result = bytes(output)

    candidate_image = LeImage(result)
    require(candidate_image.data_base == image.data_base and len(result) == len(raw), "LE data pages moved while adding fixups")
    candidate = parse_raw_fixups(result, candidate_image, expected_rows=SOURCE_FIXUP_ROWS + len(specs))
    addition_keys = {
        (spec.source_object, spec.source_offset, spec.target_object, spec.target_offset, spec.src)
        for spec in specs
    }
    retained = [row for row in candidate if (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src) not in addition_keys]
    require([fixup_semantics(row) for row in retained] == [fixup_semantics(row) for row in existing], "an existing LE fixup changed")
    added = [row for row in candidate if (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src) in addition_keys]
    require(len(added) == len(specs), "new LE fixup semantic set is incomplete")
    require(result[image.data_base:] == raw[image.data_base:], "LE data page bytes changed while adding fixups")
    require(read_u32(result, fixup_size_offset) == old_fixup_size + growth, "LE fixup size was not updated")
    require(read_u32(result, loader_size_offset) == old_loader_size + growth, "LE loader size was not updated")
    require(read_u32(result, import_module_offset) == old_import_module + growth, "LE import-module offset was not updated")
    require(read_u32(result, import_proc_offset) == old_import_proc + growth, "LE import-procedure offset was not updated")
    require(result[new_record_end] == 0 and not any(result[new_record_end + 1:image.data_base]), "remaining LE metadata slack is not zero")

    changed_ranges = (
        (fixup_size_offset, fixup_size_offset + 4),
        (loader_size_offset, loader_size_offset + 4),
        (import_module_offset, import_module_offset + 4),
        (import_proc_offset, import_proc_offset + 4),
        (page_table, page_table + (image.page_count + 1) * 4),
        (record_base, new_record_end + 1),
    )
    return result, changed_ranges



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



def next_stable_refresh_height(*, subtitle_published: bool) -> int:
    """Model the data-only height consumed by the next Smacker refresh."""

    return SUBTITLE_Y if subtitle_published else FULL_VIDEO_REFRESH_HEIGHT


def simulate_data_height_frame(
    prior_height: int,
    *,
    late_hook: bool,
    subtitle_published: bool = False,
) -> tuple[int, int]:
    """Return the current inner height and state left for the next frame.

    A skipped late hook deliberately exposes the one-frame stale-state bound:
    no code runs that could replace the previous data value.  Any executed
    late hook resets to full height unless it publishes a subtitle.
    """

    require(prior_height in (SUBTITLE_Y, FULL_VIDEO_REFRESH_HEIGHT), "invalid prior refresh height")
    if not late_hook:
        return prior_height, prior_height
    return prior_height, next_stable_refresh_height(subtitle_published=subtitle_published)



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
    require(runtime[:7] == b"\xEB\x05" + CODE_SIGNATURE + b"\0", "canonical runtime signature changed")
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


def verify_stable_refresh_runtime_contract(runtime: bytes) -> dict[str, object]:
    """Verify that the release runtime publishes only a refresh-height byte."""

    canonical = build_heap_runtime()
    require(len(runtime) == len(canonical) == D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "stable-height runtime length changed")
    require(runtime[:7] == canonical[:7] == b"\xEB\x05" + CODE_SIGNATURE + b"\0", "stable-height runtime entry signature changed")
    require(runtime != canonical, "stable-height runtime did not change")
    require(identity(runtime) == STABLE_HEIGHT_RUNTIME_ID, "stable-height runtime identity changed")

    parser_marker = b"\x8B\xB5" + struct.pack("<I", CUE_SLOT_OFFSET)
    require(runtime.count(parser_marker) == canonical.count(parser_marker) == 1, "stable-height parser marker is not exact-one")
    require(runtime.index(parser_marker) == canonical.index(parser_marker), "stable-height state shifted the parser unexpectedly")
    require(runtime.count(b"\xEB\x04" + REFRESH_CLIP_SIGNATURE) == 0, "heap refresh callback survived in the stable-height runtime")
    require(
        runtime.count(b"\x8B\x85" + struct.pack("<I", CODE_SLOT_OFFSET) + b"\x05") == 0,
        "stable runtime still computes a heap callback address",
    )

    clipped_height = b"\xC6\x05" + struct.pack("<I", STABLE_REFRESH_HEIGHT_POINTER) + bytes((SUBTITLE_Y & 0xFF,))
    full_height = b"\xC6\x05" + struct.pack("<I", STABLE_REFRESH_HEIGHT_POINTER) + bytes((FULL_VIDEO_REFRESH_HEIGHT & 0xFF,))
    require(runtime.count(clipped_height) == 1, "subtitle refresh-height publication is not exact-one")
    require(runtime.count(full_height) == 1, "full refresh-height restoration is not exact-one")
    require(runtime.count(struct.pack("<I", STABLE_REFRESH_HEIGHT_POINTER)) == 2, "unexpected refresh-height operand survived")
    require(runtime.index(clipped_height) < runtime.index(full_height), "refresh-height state order changed")
    require(
        runtime.count(b"\xC6\x85" + struct.pack("<I", ACTIVE_STATE_OFFSET)) == 0,
        "obsolete heap active-state writes survived",
    )
    old_refresh = b"\x6A\x00\x6A" + bytes((SUBTITLE_HEIGHT,)) + b"\x31\xD2\xBB" + struct.pack("<I", SUBTITLE_Y)
    stable_refresh = b"\x6A\x00\x6A" + bytes((SAFE_REFRESH_HEIGHT,)) + b"\x31\xD2\xBB" + struct.pack("<I", SUBTITLE_Y)
    require(canonical.count(old_refresh) == 2, "canonical late refresh-height sites changed")
    require(runtime.count(stable_refresh) == 2 and runtime.count(old_refresh) == 0, "stable late publication heights changed")
    require(runtime.count(struct.pack("<I", RECT_REFRESH_ACTUAL)) == 2, "stable runtime must call only the two late band refreshes")
    require(runtime.count(struct.pack("<I", SUBTITLE_FONT_OBJECT)) == 2, "stable runtime font operands changed")
    require(runtime.count(struct.pack("<I", TIMER_PROVIDER_POINTER)) == 1, "stable runtime timer sampling changed")
    require(runtime.count(struct.pack("<I", PRIMARY_HANDLE)) == 1, "stable runtime primary clock reads changed")
    require(runtime.count(struct.pack("<I", SECONDARY_HANDLE)) == 1, "stable runtime secondary clock reads changed")

    unpadded = runtime.rstrip(bytes((RUNTIME_PADDING_BYTE,)))
    require(unpadded and unpadded[-1] == 0xC3, "stable runtime padding lacks a terminal RET")
    require(runtime[len(unpadded) :] == bytes((RUNTIME_PADDING_BYTE,)) * (len(runtime) - len(unpadded)), "stable runtime NOP padding changed")
    require(b"\0" not in bytes(value ^ RUNTIME_XOR_KEY for value in runtime), "stable encrypted runtime contains NUL")
    return {
        "runtime_size": len(runtime),
        "runtime_sha256": sha256(runtime),
        "heap_callback_published": False,
        "height_state_pointer": f"0x{STABLE_REFRESH_HEIGHT_POINTER:X}",
        "cross_object_code_call": False,
        "late_publication_height": SAFE_REFRESH_HEIGHT,
        "encrypted_nul_free": True,
    }



def build_heap_runtime(*, stable_refresh_height: bool = False) -> bytes:
    """Build the generic cue lookup, band-preserving draw, and refresh code.

    ``stable_refresh_height`` selects the heap-callback-free release form.
    The runtime publishes only the low byte of a fixed refresh-height dword;
    the original Smacker call context consumes that value directly.  The
    default remains a byte-exact baseline for contract tests.
    """
    a = Assembler()
    refresh_height = SAFE_REFRESH_HEIGHT if stable_refresh_height else SUBTITLE_HEIGHT

    def emit_elapsed_ms(prefix: str, state_offset: int, handle_address: int) -> None:
        """Store uint32(shared-now-handle[0x490]) for one checked handle."""
        done = f"{prefix}_ms_done"
        a.emit("8B 3D"); a.u32(handle_address)
        a.emit("85 FF"); a.branch8(0x74, done)
        a.emit("8B 97"); a.u32(SMACK_START_TICK_FIELD)
        a.emit("85 D2"); a.branch8(0x74, done)
        a.emit("89 F0 29 D0")                               # eax=(shared now-start) mod 2^32
        a.emit("89 85"); a.u32(state_offset + CLOCK_ELAPSED_MS_FIELD)
        a.emit("C6 85"); a.u32(state_offset + CLOCK_MS_VALID_FIELD); a.u8(1)
        a.label(done)

    a.emit("EB 05")
    a.emit(CODE_SIGNATURE)
    a.u8(0)                                                # exact-once relocation flag
    a.label("entry")
    a.emit("1E 06 1E 07")                                  # save DS/ES; flat ES for REP MOVS
    # EAX still points at this runtime's marker and EDI is the fixed Object3
    # relocation table supplied by the LE-relocated bootstrap.  Patch every
    # module address before the first one is dereferenced.  PUSHAD makes this
    # idempotent prologue invisible to the established runtime ABI.
    relocation_counts = (
        STABLE_RUNTIME_RELOC_EXPECTED_COUNTS
        if stable_refresh_height
        else CANONICAL_RUNTIME_RELOC_EXPECTED_COUNTS
    )
    relocation_entry_count = sum(relocation_counts)
    a.emit("80 78 06 01"); a.branch8(0x74, "runtime_reloc_ready")
    a.emit("60 89 C6 8D 98")
    relocation_list_offset_patch = a.offset
    a.u32(0)
    a.emit("B9"); a.u32(relocation_entry_count)
    a.label("runtime_reloc_loop")
    a.emit("0F B7 13")                                     # EDX=runtime operand offset
    a.emit("0F B6 6B 02")                                  # EBP=Object3 table index
    a.emit("8B 2C AF")                                     # EBP=loader-relocated address
    a.emit("89 2C 16")                                     # patch dword [runtime+offset]
    a.emit("83 C3 03")
    a.branch8(0xE2, "runtime_reloc_loop")
    a.emit("61")
    # DOSBox's dynamic core may cache the current translated block.  End this
    # call after self-modification so no freshly patched operand is executed
    # until the next late hook enters a new block.
    a.emit("C6 40 06 01 07 1F C3")
    a.label("runtime_reloc_ready")
    a.emit("8B 2D"); a.u32(BANK_CONTROL)                 # mov ebp,[bank]
    a.emit("85 ED"); a.branch32(b"\x0F\x84", "done")
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
    if stable_refresh_height:
        # The next inner Smacker refresh may clip at the subtitle boundary.
        # Only a frame that actually published a subtitle earns that state.
        a.emit("C6 05"); a.u32(STABLE_REFRESH_HEIGHT_POINTER); a.u8(SUBTITLE_Y)
    else:
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
    if stable_refresh_height:
        # A no-match frame has just published the clean lower band.  Restore
        # full-height refresh for the following Smacker frame.
        a.emit("C6 05"); a.u32(STABLE_REFRESH_HEIGHT_POINTER); a.u8(FULL_VIDEO_REFRESH_HEIGHT)
    else:
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

    if not stable_refresh_height:
        # Byte-exact canonical baseline.  Production no longer publishes or
        # enters this heap-resident callback.
        a.emit("EB 04")
        a.emit(REFRESH_CLIP_SIGNATURE)
        a.label("refresh_clip")
        a.emit("81 FB"); a.u32(SUBTITLE_Y)
        a.branch8(0x73, "refresh_clip_defer")
        a.emit("57 BF"); a.u32(SUBTITLE_Y)
        a.emit("29 DF")
        a.emit("39 7C 24 08")
        a.branch8(0x76, "refresh_clip_forward")
        a.emit("89 7C 24 08")
        a.label("refresh_clip_forward")
        a.emit("5F 68"); a.u32(RECT_REFRESH_ACTUAL); a.emit("C3")
        a.label("refresh_clip_defer")
        a.emit("C2 0C 00 C3")

    # The relocation manifest is data after terminal RETs.  Each compact row
    # is (uint16 runtime_operand_offset, uint8 Object3_table_index).
    relocation_rows: list[tuple[int, int]] = []
    runtime_body = bytes(a.code)
    for table_index, ((name, _target_object, _target_offset, placeholder), expected_count) in enumerate(
        zip(RUNTIME_RELOC_TARGETS, relocation_counts)
    ):
        needle = struct.pack("<I", placeholder)
        matches = [offset for offset in range(len(runtime_body) - 3) if runtime_body.startswith(needle, offset)]
        require(len(matches) == expected_count, f"runtime relocation operand count changed: {name}")
        relocation_rows.extend((offset, table_index) for offset in matches)
    relocation_rows.sort()
    require(len(relocation_rows) == relocation_entry_count, "runtime relocation manifest count changed")
    require(len({offset for offset, _index in relocation_rows}) == len(relocation_rows), "runtime relocation operands overlap")
    a.emit(RUNTIME_RELOC_SIGNATURE)
    a.u8(relocation_entry_count)
    a.label("runtime_reloc_entries")
    for operand_offset, table_index in relocation_rows:
        require(0 <= operand_offset <= 0xFFFF, "runtime relocation operand exceeds uint16")
        a.u16(operand_offset)
        a.u8(table_index)
    a.emit("C3")

    # The already field-tested D executable decrypts exactly 1,856 bytes.
    # Keep that bootstrap contract byte-exact while allowing the BIN-hosted
    # runtime implementation to shrink; trailing NOPs are unreachable after
    # the refresh helper's RET and remain non-NUL after XOR 0x0D encryption.
    require(a.offset <= D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, "heap runtime exceeds the D bootstrap payload length")
    a.emit(bytes((RUNTIME_PADDING_BYTE,)) * (D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH - a.offset))

    result_array = bytearray(a.finish())
    struct.pack_into("<I", result_array, relocation_list_offset_patch, a.labels["runtime_reloc_entries"])
    result = bytes(result_array)
    require(result[:7] == b"\xEB\x05" + CODE_SIGNATURE + b"\0", "heap runtime signature changed")
    require(main_runtime_length < 0x1000, "KSX2 main runtime unexpectedly exceeds one page")
    require(result[main_runtime_length : main_runtime_length + 6] == b"\xEB\x04" + SCALE_SIGNATURE, "2x helper marker changed")
    require(
        result.count(b"\xEB\x04" + REFRESH_CLIP_SIGNATURE) == (0 if stable_refresh_height else 1),
        "video refresh clip helper marker changed",
    )
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
    if stable_refresh_height:
        verify_stable_refresh_runtime_contract(result)
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



def build_stable_refresh_bootstrap(payload_length: int, xor_key: int) -> bytes:
    """Build the late hook with loader-relocated state and runtime table input.

    The descriptor terminator is checked through ``[ESI+ECX]`` before any XOR
    mutation.  With ESI at ``marker+1`` and ECX at the exact payload length,
    this preserves the original fail-before-mutation guard.  EDI supplies the
    heap runtime with Object3's loader-relocated address table.  Resetting the
    refresh boundary before every scene/bank gate prevents a subtitle frame's
    clipped value from surviving video teardown or an early-returning hook.
    """

    a = Assembler(CAVE_PREFERRED)
    a.call_absolute(ORIGINAL_POST_VIDEO_ROUTINE)
    a.emit("9C 60")
    a.emit("C6 05"); a.u32(OBJECT3_PREFERRED_BASE + STABLE_REFRESH_HEIGHT_OBJECT_OFFSET)
    a.u8(FULL_VIDEO_REFRESH_HEIGHT)
    a.emit("A0"); a.u32(OBJECT2_PREFERRED_BASE + 0x3B22D)
    a.emit("2C"); a.u8(VIDEO_SCENE_MIN)
    a.emit("3C"); a.u8(VIDEO_SCENE_MAX - VIDEO_SCENE_MIN)
    a.branch8(0x77, "restore")
    a.emit("BF"); a.u32(OBJECT3_PREFERRED_BASE + RUNTIME_RELOC_TABLE_OBJECT_OFFSET)
    a.emit("8B 1F 8B 1B")                               # ebx=*[table[bank_control]]
    a.emit("85 DB"); a.branch8(0x74, "restore")
    a.emit("8B 83"); a.u32(CODE_SLOT_OFFSET)
    a.emit("85 C0"); a.branch8(0x74, "restore")
    a.emit("80 38 40"); a.branch8(0x75, "already")
    a.emit("8D 70 01 B9"); a.u32(payload_length)
    a.emit("80 3C 0E 00"); a.branch8(0x75, "invalid")
    a.label("decode")
    a.emit("80 36"); a.u8(xor_key); a.emit("46")
    a.branch8(0xE2, "decode")
    a.emit("40 81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x75, "invalid")
    a.emit("89 83"); a.u32(CODE_SLOT_OFFSET)
    a.label("invoke")
    a.emit("FF D0")
    a.label("restore")
    a.emit("61 9D C3")
    a.label("already")
    a.emit("81 78 02"); a.emit(CODE_SIGNATURE)
    a.branch8(0x74, "invoke")
    a.label("invalid")
    a.emit("31 C0 89 83"); a.u32(CODE_SLOT_OFFSET)
    a.branch8(0xEB, "restore")
    result = a.finish()
    require(
        len(result) == CAVE_CAPACITY,
        f"stable-height bootstrap is {len(result)} bytes; cave is {CAVE_CAPACITY}",
    )
    return result



def build_stable_refresh_context() -> bytes:
    """Keep the original Smacker ABI and redirect its shared CALL entry."""

    a = Assembler(VIDEO_REFRESH_CONTEXT_PREFERRED)
    a.emit(VIDEO_REFRESH_CALL_CONTEXT[:VIDEO_REFRESH_CALL_OBJECT_OFFSET - VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET])
    # Object1:0x739E8 jumps to this exact opcode, so the CALL cannot move.
    a.call_absolute(OBJECT1_PREFERRED_BASE + REFRESH_CLIP_CAVE_A_OBJECT_OFFSET)
    result = a.finish()
    expected = bytes.fromhex(
        "6A 00 6A 00 68 DF 01 00 00 A1 70 AD 03 00 8B 40 46 "
        "B9 7F 02 00 00 31 DB 31 D2 E8 53 1D 02 00"
    )
    require(result == expected and len(result) == len(VIDEO_REFRESH_CALL_CONTEXT), "shared refresh context bytes changed")
    return result


def build_refresh_clip_fragments() -> tuple[bytes, bytes, bytes]:
    """Build a fixed Object1-only clipper across three alignment gaps."""

    cave_a = bytearray(b"\x57\x8B\x3D")
    cave_a.extend(struct.pack("<I", OBJECT3_PREFERRED_BASE + STABLE_REFRESH_HEIGHT_OBJECT_OFFSET))
    cave_a.extend(b"\x29\xDF\xEB")
    after_a = OBJECT1_PREFERRED_BASE + REFRESH_CLIP_CAVE_A_OBJECT_OFFSET + REFRESH_CLIP_CAVE_A_SIZE
    cave_a.append((OBJECT1_PREFERRED_BASE + REFRESH_CLIP_CAVE_B_OBJECT_OFFSET - after_a) & 0xFF)

    cave_b = bytes.fromhex("76 12 39 7C 24 08 76 10 89 7C 24 08 EB 0A 90")

    cave_c = bytearray(bytes.fromhex("5F C2 0C 00 5F E9"))
    after_c_jump = OBJECT1_PREFERRED_BASE + REFRESH_CLIP_CAVE_C_OBJECT_OFFSET + 10
    cave_c.extend(struct.pack("<i", OBJECT1_PREFERRED_BASE + RECT_REFRESH_OBJECT_OFFSET - after_c_jump))
    cave_c.append(0x90)

    result = (bytes(cave_a), cave_b, bytes(cave_c))
    require(
        tuple(map(len, result))
        == (REFRESH_CLIP_CAVE_A_SIZE, REFRESH_CLIP_CAVE_B_SIZE, REFRESH_CLIP_CAVE_C_SIZE),
        "fixed refresh clipper escaped its reviewed caves",
    )
    require(result == (
        bytes.fromhex("57 8B 3D AC 3E 13 00 29 DF EB 71"),
        bytes.fromhex("76 12 39 7C 24 08 76 10 89 7C 24 08 EB 0A 90"),
        bytes.fromhex("5F C2 0C 00 5F E9 AA FC FE FF 90"),
    ), "fixed refresh clipper bytes changed")
    return result


def build_portable_descriptor_validator() -> bytes:
    """Resolve Object2-relative direct descriptors in fixed Object1 code."""

    body = bytes.fromhex(
        "8D 46 09 39 E8 77 52 89 F2 AD A9 03 FC FF FF 74 20 "
        "3D 20 E9 02 00 72 41 3D 20 15 03 00 73 3A A8 03 75 36 "
        "BF 00 00 0E 00 01 C7 89 3A AD 01 F8 EB 0B "
        "8B 3D 98 3E 13 00 01 C7 89 3A AD 39 07 75 19 "
        "80 3E 40 75 14 46 39 EE 73 0F 80 3E 00 75 F6 46 E2 AE "
        "39 EE 75 03 31 C0 C3 B0 01 C3"
    )
    require(len(body) == 0x5C, "portable descriptor validator body size changed")
    result = body + b"\x90" * (DESCRIPTOR_VALIDATOR_SIZE - len(body))
    require(len(result) == DESCRIPTOR_VALIDATOR_SIZE, "portable descriptor validator escaped its fixed routine")
    require(read_u32(result, 0x24) == OBJECT2_PREFERRED_BASE, "validator Object2 base operand moved")
    require(
        read_u32(result, 0x33) == OBJECT3_PREFERRED_BASE + 0x3E98,
        "validator private-slot operand moved",
    )
    return result


def simulate_refresh_clip(boundary: int, source_y: int, height: int) -> int | None:
    """Model the fixed dispatcher's unsigned clamp; None means defer."""

    require(0 <= boundary <= 0xFFFFFFFF, "refresh boundary must be uint32")
    require(0 <= source_y <= 0xFFFFFFFF, "refresh source y must be uint32")
    require(0 <= height <= 0xFFFFFFFF, "refresh height must be uint32")
    if source_y >= boundary:
        return None
    return min(height, boundary - source_y)


def build_subtitle_bank(source: bytes, cues: Sequence[Cue], encrypted_runtime: bytes) -> bytes:
    """Build an Object-relative beta6 bank with KSX2/KSXR descriptors."""

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
    unit_rows = [
        row for row in parsed.descriptors
        if not token_allowed(row.target) and SOURCE_UNIT_TARGET_START <= row.target < SOURCE_UNIT_TARGET_END
    ]
    general_rows = [
        row for row in parsed.descriptors
        if not token_allowed(row.target) and SOURCE_GENERAL_TARGET_START <= row.target < SOURCE_GENERAL_TARGET_END
    ]
    token_rows = [row for row in parsed.descriptors if token_allowed(row.target)]
    require(
        (len(unit_rows), len(general_rows), len(token_rows))
        == (NATIVE_UNIT_DESCRIPTOR_COUNT, PORTABLE_GENERAL_DESCRIPTOR_COUNT, OLD_RENDER_COUNT),
        "beta6 descriptor ownership changed",
    )
    require(len(unit_rows) + len(general_rows) + len(token_rows) == OLD_DESCRIPTOR_COUNT, "beta6 direct descriptor escaped its reviewed ranges")
    require(all(OBJECT3_ACTUAL_BASE <= row.expected < OBJECT3_ACTUAL_BASE + 0x4000 for row in unit_rows), "native unit expected pointer escaped Object3")
    require(all(OBJECT2_ACTUAL_BASE <= row.expected < OBJECT2_ACTUAL_BASE + 0x45190 for row in general_rows), "general expected pointer escaped Object2")

    descriptors: list[tuple[int, int, bytes]] = []
    for row in parsed.descriptors:
        if token_allowed(row.target):
            descriptors.append((row.target, row.expected, row.encoded))
        elif SOURCE_UNIT_TARGET_START <= row.target < SOURCE_UNIT_TARGET_END:
            # These seven translations are byte-identical to the native O3
            # strings already selected by the EXE's original LE fixups.
            continue
        else:
            target_offset = row.target - OBJECT2_ACTUAL_BASE
            expected_delta = (row.expected - row.target) & 0xFFFFFFFF
            require(PORTABLE_GENERAL_TARGET_START <= target_offset < PORTABLE_GENERAL_TARGET_END, "general target offset escaped Object2")
            descriptors.append((target_offset, expected_delta, row.encoded))
    portable_existing = tuple(descriptors)
    descriptors.extend(((CUE_TOKEN, 0, cue_blob), (CODE_TOKEN, 0, encrypted_runtime)))
    output, _rows, _descriptors = serialize_bank(
        render_rows,
        descriptors,
        mapping_tag=MAPPING_TAG,
        unit_start=PORTABLE_GENERAL_TARGET_START,
        unit_end=PORTABLE_GENERAL_TARGET_END,
    )
    reparsed = parse_bank(
        output,
        expected_mapping_tag=MAPPING_TAG,
        unit_start=PORTABLE_GENERAL_TARGET_START,
        unit_end=PORTABLE_GENERAL_TARGET_END,
    )
    require(len(output) <= 0xFEFF, "subtitle bank exceeds the DOS one-read limit")
    require(
        (len(reparsed.descriptors), len(reparsed.render_rows))
        == (OLD_DESCRIPTOR_COUNT - NATIVE_UNIT_DESCRIPTOR_COUNT + 2, OLD_RENDER_COUNT + 2),
        "subtitle bank shape changed",
    )
    require(
        [(row.target, row.expected, row.encoded) for row in reparsed.descriptors[:len(portable_existing)]]
        == list(portable_existing),
        "portable beta6 descriptor transform changed",
    )
    require(
        [(row.prefix, row.token) for row in reparsed.render_rows[:OLD_RENDER_COUNT]]
        == [(row.prefix, row.token) for row in parsed.render_rows],
        "an existing beta6 render row changed",
    )
    return output


def verify_native_unit_fallbacks(source_exe: bytes, source_bank: bytes) -> tuple[tuple[int, int], ...]:
    """Prove that the seven omitted unit rows already exist natively in O3."""

    require(identity(source_exe) == SOURCE_EXE_ID and identity(source_bank) == SOURCE_BANK_ID, "native unit proof requires pinned beta6 inputs")
    image = LeImage(source_exe)
    fixups = parse_raw_fixups(source_exe, image, expected_rows=SOURCE_FIXUP_ROWS)
    parsed = parse_bank(
        source_bank,
        expected_mapping_tag=MAPPING_TAG,
        unit_start=PARSE_TARGET_START,
        unit_end=PARSE_TARGET_END,
    )
    unit_rows = [
        row for row in parsed.descriptors
        if SOURCE_UNIT_TARGET_START <= row.target < SOURCE_UNIT_TARGET_END
    ]
    require(len(unit_rows) == NATIVE_UNIT_DESCRIPTOR_COUNT, "native unit descriptor count changed")
    proof: list[tuple[int, int]] = []
    for row in unit_rows:
        target_offset = row.target - OBJECT2_ACTUAL_BASE
        expected_offset = row.expected - OBJECT3_ACTUAL_BASE
        owners = [
            fixup for fixup in fixups
            if fixup.source_object == 2 and fixup.source_offset == target_offset
        ]
        require(
            len(owners) == 1
            and owners[0].target_object == 3
            and owners[0].target_offset == expected_offset
            and owners[0].src == 7,
            "native unit pointer is not owned by its original LE fixup",
        )
        native_file = image.object_to_file(3, expected_offset)
        native = source_exe[native_file:native_file + len(row.encoded) + 2]
        require(native == b"@" + row.encoded + b"\0", "native unit fallback text differs from the bank")
        proof.append((target_offset, expected_offset))
    require(len(set(proof)) == NATIVE_UNIT_DESCRIPTOR_COUNT, "native unit fallback proof is duplicated")
    general_rows = [
        row for row in parsed.descriptors
        if SOURCE_GENERAL_TARGET_START <= row.target < SOURCE_GENERAL_TARGET_END
    ]
    require(len(general_rows) == PORTABLE_GENERAL_DESCRIPTOR_COUNT, "general descriptor count changed")
    for row in general_rows:
        target_offset = row.target - OBJECT2_ACTUAL_BASE
        expected_offset = row.expected - OBJECT2_ACTUAL_BASE
        owners = [
            fixup for fixup in fixups
            if fixup.source_object == 2 and fixup.source_offset == target_offset
        ]
        require(
            len(owners) == 1
            and owners[0].target_object == 2
            and owners[0].target_offset == expected_offset
            and owners[0].src == 7,
            "general descriptor does not match its original Object2 LE fixup",
        )
    return tuple(sorted(proof))


def _object_preferred_base(object_number: int) -> int:
    return (OBJECT1_PREFERRED_BASE, OBJECT2_PREFERRED_BASE, OBJECT3_PREFERRED_BASE)[object_number - 1]


def _object_observed_actual_base(object_number: int) -> int:
    return (OBJECT1_ACTUAL_BASE, OBJECT2_ACTUAL_BASE, OBJECT3_ACTUAL_BASE)[object_number - 1]


def build_runtime_relocation_table() -> bytes:
    table = b"".join(
        struct.pack("<I", _object_preferred_base(target_object) + target_offset)
        for _name, target_object, target_offset, _placeholder in RUNTIME_RELOC_TARGETS
    )
    require(len(table) == RUNTIME_RELOC_TABLE_SIZE, "runtime relocation table size changed")
    return table


def _absolute_transfer_veneer(target_object: int, target_offset: int) -> bytes:
    """Return a register-transparent absolute JMP/CALL continuation."""

    return b"\x68" + struct.pack("<I", _object_preferred_base(target_object) + target_offset) + b"\xC3"


def build_h2k3_portable_veneers() -> tuple[bytes, bytes]:
    """Build three Object1 veneers while preserving unused alignment bytes."""

    rows = tuple(
        _absolute_transfer_veneer(target_object, target_offset)
        for _source, _opcode, _veneer, target_object, target_offset in H2K3_O1_EDGE_VENEERS
    )
    require(all(len(row) == 6 for row in rows), "H2K3 absolute veneer size changed")
    cave_a = rows[0] + rows[1] + b"\0"
    cave_b = rows[2] + b"\0"
    require(
        (len(cave_a), len(cave_b))
        == (H2K3_VENEER_CAVE_A_SIZE, H2K3_VENEER_CAVE_B_SIZE),
        "H2K3 veneer cave layout changed",
    )
    return cave_a, cave_b


def build_h2k3_o3_portable_patch() -> bytes:
    """Replace two Object3->Object1 rel32 edges with type-7 immediates."""

    patch = (
        _absolute_transfer_veneer(1, 0xC4FF0)
        + bytes.fromhex(
            "0F B6 47 0C C1 E0 04 83 C0 20 39 47 14 75 D4 "
            "8D 1C 07 57 89 DE B8"
        )
        + struct.pack("<I", OBJECT1_PREFERRED_BASE + DESCRIPTOR_VALIDATOR_OBJECT_OFFSET)
        + bytes.fromhex("FF D0 5F C3")
    )
    require(len(patch) == H2K3_O3_PORTABLE_PATCH_SIZE, "H2K3 Object3 portable patch size changed")
    # The shifted descriptor helper keeps MOVZX and therefore has no hidden
    # dependency on the caller's upper EAX bits.  Its failure branch reuses the
    # existing Object3:3F29 `mov al,1; ret` epilogue.
    require(patch[6:10] == bytes.fromhex("0F B6 47 0C"), "H2K3 descriptor helper lost MOVZX")
    require(patch[0x13:0x15] == bytes.fromhex("75 D4"), "H2K3 shared failure branch changed")
    require(patch[0x1B] == 0xB8 and patch[0x20:0x22] == bytes.fromhex("FF D0"), "H2K3 absolute validator call changed")
    return patch


def _unique_u32_operand(code: bytes, value: int, name: str) -> int:
    needle = struct.pack("<I", value)
    offsets = [index for index in range(len(code) - 3) if code.startswith(needle, index)]
    require(len(offsets) == 1, f"bootstrap {name} operand is not unique")
    return offsets[0]


def build_executable_fixup_specs(source: bytes, image: LeImage, bootstrap: bytes) -> tuple[FixupSpec, ...]:
    """Describe every new loader relocation used by the portable subtitle path."""

    specs: list[FixupSpec] = [
        FixupSpec(1, REFRESH_CLIP_HEIGHT_FIXUP_SOURCE, 3, STABLE_REFRESH_HEIGHT_OBJECT_OFFSET),
        FixupSpec(
            1,
            CAVE_OBJECT_OFFSET + _unique_u32_operand(
                bootstrap,
                OBJECT3_PREFERRED_BASE + STABLE_REFRESH_HEIGHT_OBJECT_OFFSET,
                "refresh boundary reset",
            ),
            3,
            STABLE_REFRESH_HEIGHT_OBJECT_OFFSET,
        ),
        FixupSpec(
            1,
            CAVE_OBJECT_OFFSET + _unique_u32_operand(bootstrap, OBJECT2_PREFERRED_BASE + 0x3B22D, "scene"),
            2,
            0x3B22D,
        ),
        FixupSpec(
            1,
            CAVE_OBJECT_OFFSET + _unique_u32_operand(
                bootstrap,
                OBJECT3_PREFERRED_BASE + RUNTIME_RELOC_TABLE_OBJECT_OFFSET,
                "relocation table",
            ),
            3,
            RUNTIME_RELOC_TABLE_OBJECT_OFFSET,
        ),
    ]
    specs.extend(
        FixupSpec(3, RUNTIME_RELOC_TABLE_OBJECT_OFFSET + index * 4, target_object, target_offset)
        for index, (_name, target_object, target_offset, _placeholder) in enumerate(RUNTIME_RELOC_TARGETS)
    )

    for row in H2K3_ABSOLUTE_RELOCS:
        source_offset, target_object, target_offset, *source_owner = row
        source_object = source_owner[0] if source_owner else 1
        source_file = image.object_to_file(source_object, source_offset)
        observed = read_u32(source, source_file)
        expected = _object_observed_actual_base(target_object) + target_offset
        require(observed == expected, f"H2K3 absolute operand Object{source_object}:0x{source_offset:X} changed")
        specs.append(FixupSpec(source_object, source_offset, target_object, target_offset, 7))

    # Validate the five pre-existing cross-object rel32 edges.  The portable
    # patch redirects the three Object1 edges to same-object veneers and
    # rewrites the two Object3 edges as absolute transfers below; no source
    # type 8 record is emitted.
    for source_offset, target_object, target_offset, source_object in H2K3_RELATIVE_RELOCS:
        source_file = image.object_to_file(source_object, source_offset)
        displacement = struct.unpack_from("<i", source, source_file)[0]
        observed_target = _object_observed_actual_base(source_object) + source_offset + 4 + displacement
        expected_target = _object_observed_actual_base(target_object) + target_offset
        require(observed_target == expected_target, f"H2K3 relative operand Object{source_object}:0x{source_offset:X} changed")

    specs.extend(
        FixupSpec(1, veneer_offset + 1, target_object, target_offset, 7)
        for _source, _opcode, veneer_offset, target_object, target_offset in H2K3_O1_EDGE_VENEERS
    )
    specs.extend(
        FixupSpec(3, source_offset, target_object, target_offset, 7)
        for source_offset, target_object, target_offset in H2K3_O3_ABSOLUTE_TRANSFER_FIXUPS
    )

    specs.extend((
        FixupSpec(1, DESCRIPTOR_VALIDATOR_O2_BASE_FIXUP_SOURCE, 2, 0, 7),
        FixupSpec(1, DESCRIPTOR_VALIDATOR_SLOT_FIXUP_SOURCE, 3, 0x3E98, 7),
    ))

    require(len(specs) == 37 and len(set(specs)) == 37, "portable subtitle LE fixup set changed")
    return tuple(specs)


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
        "descriptor_validator": image.object_to_file(1, DESCRIPTOR_VALIDATOR_OBJECT_OFFSET),
        "false_cave": image.object_to_file(1, FALSE_CAVE_OBJECT_OFFSET),
        "height": image.object_to_file(3, STABLE_REFRESH_HEIGHT_OBJECT_OFFSET),
        "clip_cave_a": image.object_to_file(1, REFRESH_CLIP_CAVE_A_OBJECT_OFFSET),
        "clip_cave_b": image.object_to_file(1, REFRESH_CLIP_CAVE_B_OBJECT_OFFSET),
        "clip_cave_c": image.object_to_file(1, REFRESH_CLIP_CAVE_C_OBJECT_OFFSET),
        "h2k3_veneer_cave_a": image.object_to_file(1, H2K3_VENEER_CAVE_A_OBJECT_OFFSET),
        "h2k3_veneer_cave_b": image.object_to_file(1, H2K3_VENEER_CAVE_B_OBJECT_OFFSET),
        "h2k3_o1_edge_a": image.object_to_file(1, H2K3_O1_EDGE_VENEERS[0][0]),
        "h2k3_o1_edge_b": image.object_to_file(1, H2K3_O1_EDGE_VENEERS[1][0]),
        "h2k3_o1_edge_c": image.object_to_file(1, H2K3_O1_EDGE_VENEERS[2][0]),
        "h2k3_o3_portable": image.object_to_file(3, H2K3_O3_PORTABLE_PATCH_OBJECT_OFFSET),
        "runtime_reloc_table": image.object_to_file(3, RUNTIME_RELOC_TABLE_OBJECT_OFFSET),
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
        "descriptor_validator": (offsets["descriptor_validator"], DESCRIPTOR_VALIDATOR_SIZE),
        "false_cave": (offsets["false_cave"], FALSE_CAVE_SIZE),
        "height": (offsets["height"], 4),
        "clip_cave_a": (offsets["clip_cave_a"], REFRESH_CLIP_CAVE_A_SIZE),
        "clip_cave_b": (offsets["clip_cave_b"], REFRESH_CLIP_CAVE_B_SIZE),
        "clip_cave_c": (offsets["clip_cave_c"], REFRESH_CLIP_CAVE_C_SIZE),
        "h2k3_veneer_cave_a": (offsets["h2k3_veneer_cave_a"], H2K3_VENEER_CAVE_A_SIZE),
        "h2k3_veneer_cave_b": (offsets["h2k3_veneer_cave_b"], H2K3_VENEER_CAVE_B_SIZE),
        "h2k3_o1_edge_a": (offsets["h2k3_o1_edge_a"], 4),
        "h2k3_o1_edge_b": (offsets["h2k3_o1_edge_b"], 4),
        "h2k3_o1_edge_c": (offsets["h2k3_o1_edge_c"], 4),
        "h2k3_o3_portable": (offsets["h2k3_o3_portable"], H2K3_O3_PORTABLE_PATCH_SIZE),
        "runtime_reloc_table": (offsets["runtime_reloc_table"], RUNTIME_RELOC_TABLE_SIZE),
    }


def patch_executable(source: bytes) -> bytes:
    """Install a load-base-independent subtitle runtime and shared refresh clip."""

    require(identity(source) == SOURCE_EXE_ID, "input is not the pinned beta6 HEROES2.EXE")
    image = LeImage(source)
    require(image.objects[0].virtual_size == 0xC5000 and image.page_count == 0xFF, "beta6 LE geometry changed")
    spans = _patch_file_ranges(source, image)

    def source_span(name: str) -> bytes:
        start, length = spans[name]
        return source[start:start + length]

    def require_cave_boundaries(name: str, before: bytes, after: bytes) -> None:
        start, length = spans[name]
        require(source_span(name) == b"\0" * length, f"{name} is not a zero-filled alignment gap")
        require(source[start - len(before):start] == before, f"{name} preceding instruction boundary changed")
        require(source[start + length:start + length + len(after)] == after, f"{name} following instruction boundary changed")

    require(source_span("late_call") == CALL_SITE_ORIGINAL, "late post-video CALL changed")
    require(source_span("video_call") == VIDEO_REFRESH_CALL_ORIGINAL, "Smacker refresh CALL changed")
    require(source_span("video_context") == VIDEO_REFRESH_CALL_CONTEXT, "Smacker refresh call ABI context changed")
    require_cave_boundaries("clip_cave_a", REFRESH_CLIP_CAVE_A_BEFORE, REFRESH_CLIP_CAVE_A_AFTER)
    require_cave_boundaries("clip_cave_b", REFRESH_CLIP_CAVE_B_BEFORE, REFRESH_CLIP_CAVE_B_AFTER)
    require_cave_boundaries("clip_cave_c", REFRESH_CLIP_CAVE_C_BEFORE, REFRESH_CLIP_CAVE_C_AFTER)
    require_cave_boundaries("h2k3_veneer_cave_a", H2K3_VENEER_CAVE_A_BEFORE, H2K3_VENEER_CAVE_A_AFTER)
    require_cave_boundaries("h2k3_veneer_cave_b", H2K3_VENEER_CAVE_B_BEFORE, H2K3_VENEER_CAVE_B_AFTER)
    require(source_span("h2k3_o3_portable") == H2K3_O3_PORTABLE_SOURCE, "H2K3 Object3 helper source changed")
    for source_offset, opcode, _veneer, _target_object, _target_offset in H2K3_O1_EDGE_VENEERS:
        opcode_file = image.object_to_file(1, source_offset - 1)
        require(source[opcode_file] == opcode, f"H2K3 Object1 edge opcode 0x{source_offset - 1:X} changed")
    require(source_span("runtime_reloc_table") == b"\0" * RUNTIME_RELOC_TABLE_SIZE, "runtime relocation table tail changed")
    late_refresh_join_file = image.object_to_file(1, LATE_REFRESH_JOIN_BRANCH_OBJECT_OFFSET)
    require(source[late_refresh_join_file:late_refresh_join_file + 2] == LATE_REFRESH_JOIN_BRANCH_BYTES, "Smacker shared-call inbound branch changed")
    require(
        LATE_REFRESH_JOIN_BRANCH_OBJECT_OFFSET + 2
        + int.from_bytes(LATE_REFRESH_JOIN_BRANCH_BYTES[1:2], "little", signed=True)
        == VIDEO_REFRESH_CALL_OBJECT_OFFSET,
        "Smacker inbound branch no longer lands on the shared CALL",
    )
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
    require(sha256(source_span("descriptor_validator")) == DESCRIPTOR_VALIDATOR_SOURCE_SHA256, "H2K3 descriptor validator source changed")
    require(sha256(source_span("false_cave")) == FALSE_CAVE_SOURCE_SHA256, "Watcom runtime metadata span changed")
    require(source_span("height") == STABLE_REFRESH_HEIGHT_SOURCE, "refresh boundary ownership marker changed")
    require(source_span("malloc") == MALLOC_BEFORE, "H2K3 allocation immediate changed")
    require(spans["cave"][0] + CAVE_CAPACITY == spans["loader"][0], "bootstrap cave no longer borders H2K3 loader")

    source_fixups = parse_raw_fixups(source, image, expected_rows=SOURCE_FIXUP_ROWS)
    surface_fixups = [
        row for row in source_fixups
        if row.source_object == 1 and row.source_offset == VIDEO_REFRESH_SURFACE_FIXUP_SOURCE
    ]
    require(len(surface_fixups) == 1, "Smacker surface operand fixup is not unique")
    surface_fixup = surface_fixups[0]
    require(
        surface_fixup.target_object == VIDEO_REFRESH_SURFACE_FIXUP_TARGET_OBJECT
        and surface_fixup.target_offset == VIDEO_REFRESH_SURFACE_FIXUP_TARGET_OFFSET
        and surface_fixup.src == 7 and surface_fixup.flags == 0x10,
        "Smacker surface operand fixup contract changed",
    )
    require(
        [row for row in source_fixups if row.source_object == 1 and VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET <= row.source_offset < VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET + len(VIDEO_REFRESH_CALL_CONTEXT)]
        == [surface_fixup],
        "Smacker context has an unexpected LE fixup source",
    )

    runtime = build_heap_runtime(stable_refresh_height=True)
    require(identity(runtime) == STABLE_HEIGHT_RUNTIME_ID, "relocatable subtitle runtime identity changed")
    bootstrap = build_stable_refresh_bootstrap(len(runtime), RUNTIME_XOR_KEY)
    context = build_stable_refresh_context()
    clip_fragments = build_refresh_clip_fragments()
    descriptor_validator = build_portable_descriptor_validator()
    relocation_table = build_runtime_relocation_table()
    h2k3_veneer_caves = build_h2k3_portable_veneers()
    h2k3_o3_portable = build_h2k3_o3_portable_patch()
    fixup_specs = build_executable_fixup_specs(source, image, bootstrap)
    require(len(bootstrap) == CAVE_CAPACITY and len(context) == len(VIDEO_REFRESH_CALL_CONTEXT), "portable EXE layout changed")

    patched_object_ranges = (
        (1, CALL_SITE_OBJECT_OFFSET, CALL_SITE_OBJECT_OFFSET + 5),
        (1, VIDEO_REFRESH_CALL_OBJECT_OFFSET, VIDEO_REFRESH_CALL_OBJECT_OFFSET + 5),
        (1, CAVE_OBJECT_OFFSET, CAVE_OBJECT_OFFSET + CAVE_CAPACITY),
        (1, H2K3_OBJECT_OFFSET + MALLOC_INSTRUCTION_OFFSET, H2K3_OBJECT_OFFSET + MALLOC_INSTRUCTION_OFFSET + 5),
        (1, DESCRIPTOR_VALIDATOR_OBJECT_OFFSET, DESCRIPTOR_VALIDATOR_OBJECT_OFFSET + DESCRIPTOR_VALIDATOR_SIZE),
        (1, REFRESH_CLIP_CAVE_A_OBJECT_OFFSET, REFRESH_CLIP_CAVE_A_OBJECT_OFFSET + REFRESH_CLIP_CAVE_A_SIZE),
        (1, REFRESH_CLIP_CAVE_B_OBJECT_OFFSET, REFRESH_CLIP_CAVE_B_OBJECT_OFFSET + REFRESH_CLIP_CAVE_B_SIZE),
        (1, REFRESH_CLIP_CAVE_C_OBJECT_OFFSET, REFRESH_CLIP_CAVE_C_OBJECT_OFFSET + REFRESH_CLIP_CAVE_C_SIZE),
        (1, H2K3_VENEER_CAVE_A_OBJECT_OFFSET, H2K3_VENEER_CAVE_A_OBJECT_OFFSET + H2K3_VENEER_CAVE_A_SIZE),
        (1, H2K3_VENEER_CAVE_B_OBJECT_OFFSET, H2K3_VENEER_CAVE_B_OBJECT_OFFSET + H2K3_VENEER_CAVE_B_SIZE),
        *((1, source_offset, source_offset + 4) for source_offset, _opcode, _veneer, _target_object, _target_offset in H2K3_O1_EDGE_VENEERS),
        (3, H2K3_O3_PORTABLE_PATCH_OBJECT_OFFSET, H2K3_O3_PORTABLE_PATCH_OBJECT_OFFSET + H2K3_O3_PORTABLE_PATCH_SIZE),
        (3, STABLE_REFRESH_HEIGHT_OBJECT_OFFSET, STABLE_REFRESH_HEIGHT_OBJECT_OFFSET + 4),
        (3, RUNTIME_RELOC_TABLE_OBJECT_OFFSET, RUNTIME_RELOC_TABLE_OBJECT_OFFSET + RUNTIME_RELOC_TABLE_SIZE),
    )
    for owner, start, end in patched_object_ranges:
        require(
            not any(row.source_object == owner and row.source_offset < end and start < row.source_offset + 4 for row in source_fixups),
            f"EXE patch Object{owner}:0x{start:X} overlaps an existing LE fixup source",
        )
        require(
            not any(row.target_object == owner and start <= row.target_offset < end for row in source_fixups),
            f"EXE patch Object{owner}:0x{start:X} has an existing LE fixup target",
        )

    output = bytearray(source)
    late_call, _ = spans["late_call"]
    output[late_call:late_call + 5] = b"\xE8" + struct.pack("<i", CAVE_PREFERRED - (CALL_SITE_PREFERRED + 5))
    video_context, _ = spans["video_context"]
    output[video_context:video_context + len(context)] = context
    cave_file, _ = spans["cave"]
    output[cave_file:cave_file + CAVE_CAPACITY] = bootstrap
    malloc_file, _ = spans["malloc"]
    output[malloc_file:malloc_file + 5] = MALLOC_AFTER
    descriptor_validator_file, _ = spans["descriptor_validator"]
    output[descriptor_validator_file:descriptor_validator_file + DESCRIPTOR_VALIDATOR_SIZE] = descriptor_validator
    height_file, _ = spans["height"]
    output[height_file:height_file + 4] = struct.pack("<I", FULL_VIDEO_REFRESH_HEIGHT)
    for name, fragment in zip(("clip_cave_a", "clip_cave_b", "clip_cave_c"), clip_fragments):
        file_offset, length = spans[name]
        require(len(fragment) == length, f"{name} fragment length changed")
        output[file_offset:file_offset + length] = fragment
    for name, veneer_cave in zip(("h2k3_veneer_cave_a", "h2k3_veneer_cave_b"), h2k3_veneer_caves):
        file_offset, length = spans[name]
        require(len(veneer_cave) == length, f"{name} layout changed")
        output[file_offset:file_offset + length] = veneer_cave
    for index, (source_offset, _opcode, veneer_offset, _target_object, _target_offset) in enumerate(H2K3_O1_EDGE_VENEERS):
        file_offset, length = spans[f"h2k3_o1_edge_{chr(ord('a') + index)}"]
        require(length == 4, "H2K3 Object1 edge operand size changed")
        output[file_offset:file_offset + length] = struct.pack("<i", veneer_offset - (source_offset + 4))
    o3_portable_file, o3_portable_length = spans["h2k3_o3_portable"]
    require(len(h2k3_o3_portable) == o3_portable_length, "H2K3 Object3 patch layout changed")
    output[o3_portable_file:o3_portable_file + o3_portable_length] = h2k3_o3_portable
    table_file, _ = spans["runtime_reloc_table"]
    output[table_file:table_file + len(relocation_table)] = relocation_table

    pre_fixup = bytes(output)
    result, metadata_ranges = install_internal_fixups(pre_fixup, LeImage(pre_fixup), fixup_specs)
    allowed_file_ranges = tuple(
        (spans[name][0], spans[name][0] + spans[name][1])
        for name in (
            "late_call", "video_call", "cave", "malloc", "descriptor_validator", "height",
            "clip_cave_a", "clip_cave_b", "clip_cave_c",
            "h2k3_veneer_cave_a", "h2k3_veneer_cave_b",
            "h2k3_o1_edge_a", "h2k3_o1_edge_b", "h2k3_o1_edge_c", "h2k3_o3_portable",
            "runtime_reloc_table",
        )
    ) + metadata_ranges
    changed = [index for index, pair in enumerate(zip(source, result)) if pair[0] != pair[1]]
    require(len(result) == len(source) and changed, "patched EXE size/change contract failed")
    require(all(any(start <= index < end for start, end in allowed_file_ranges) for index in changed), "EXE byte escaped the patch allowlist")
    require(result[video_context:video_context + len(context)] == context, "shared refresh context changed")
    call_index = VIDEO_REFRESH_CALL_OBJECT_OFFSET - VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET
    require(context[call_index] == 0xE8, "Smacker shared CALL opcode moved away from its inbound branch")
    call_target = VIDEO_REFRESH_CONTEXT_PREFERRED + call_index + 5 + struct.unpack_from("<i", context, call_index + 1)[0]
    require(call_target == OBJECT1_PREFERRED_BASE + REFRESH_CLIP_CAVE_A_OBJECT_OFFSET, "Smacker shared CALL does not enter the fixed clipper")
    require(result[descriptor_validator_file:descriptor_validator_file + DESCRIPTOR_VALIDATOR_SIZE] == descriptor_validator, "portable descriptor validator changed")
    for index, (source_offset, _opcode, veneer_offset, _target_object, _target_offset) in enumerate(H2K3_O1_EDGE_VENEERS):
        edge_file, _ = spans[f"h2k3_o1_edge_{chr(ord('a') + index)}"]
        displacement = struct.unpack_from("<i", result, edge_file)[0]
        require(source_offset + 4 + displacement == veneer_offset, "H2K3 Object1 edge missed its same-object veneer")
    require(result[o3_portable_file:o3_portable_file + o3_portable_length] == h2k3_o3_portable, "H2K3 Object3 absolute transfers changed")
    require(result[spans["false_cave"][0]:spans["false_cave"][0] + FALSE_CAVE_SIZE] == source_span("false_cave"), "Watcom runtime metadata was not byte-preserved")

    candidate_fixups = parse_raw_fixups(result, LeImage(result), expected_rows=SOURCE_FIXUP_ROWS + len(fixup_specs))
    spec_keys = {
        (spec.source_object, spec.source_offset, spec.target_object, spec.target_offset, spec.src)
        for spec in fixup_specs
    }
    added = [
        row for row in candidate_fixups
        if (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src) in spec_keys
    ]
    require(len(added) == len(fixup_specs), "portable subtitle LE fixups are incomplete")
    retained = [
        row for row in candidate_fixups
        if (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src) not in spec_keys
    ]
    require([fixup_semantics(row) for row in retained] == [fixup_semantics(row) for row in source_fixups], "an original LE fixup changed")
    retained_surface = [row for row in retained if row.source_object == 1 and row.source_offset == VIDEO_REFRESH_SURFACE_FIXUP_SOURCE]
    require(len(retained_surface) == 1 and fixup_semantics(retained_surface[0]) == fixup_semantics(surface_fixup), "Smacker surface fixup was not preserved")
    require(identity(result) == FINAL_EXE_ID, "patched EXE does not match the tested final identity")
    return result


def build_artifacts(source_exe: bytes, source_bank: bytes) -> tuple[bytes, bytes, dict[str, object]]:
    native_unit_proof = verify_native_unit_fallbacks(source_exe, source_bank)
    mapping = load_subtitle_mapping()
    cues, cue_meta = load_scene_cues(mapping=mapping)
    runtime = build_heap_runtime(stable_refresh_height=True)
    require(identity(runtime) == STABLE_HEIGHT_RUNTIME_ID, "stable-height runtime identity changed")
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
            "native_unit_fallback_count": len(native_unit_proof),
            "relative_object2_descriptor_count": PORTABLE_GENERAL_DESCRIPTOR_COUNT,
            "watcom_runtime_metadata_byte_preserved": True,
            "surface_fixup_preserved": True,
            "loader_relocated_runtime_operands": True,
            "heap_callback_published": False,
            "heap_cross_object_callback_published": False,
            "refresh_height_pointer": f"0x{STABLE_REFRESH_HEIGHT_POINTER:X}",
            "fixed_code_refresh_clipper": True,
            "cross_object_self_relative_fixups": 0,
            "type7_absolute_transfer_veneers": 5,
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
        unit_start=PORTABLE_GENERAL_TARGET_START,
        unit_end=PORTABLE_GENERAL_TARGET_END,
    )
    require(
        (len(parsed.descriptors), len(parsed.render_rows))
        == (OLD_DESCRIPTOR_COUNT - NATIVE_UNIT_DESCRIPTOR_COUNT + 2, OLD_RENDER_COUNT + 2),
        "candidate relative bank shape changed",
    )
    direct_rows = [row for row in parsed.descriptors if not token_allowed(row.target)]
    require(
        len(direct_rows) == PORTABLE_GENERAL_DESCRIPTOR_COUNT
        and all(PORTABLE_GENERAL_TARGET_START <= row.target < PORTABLE_GENERAL_TARGET_END for row in direct_rows),
        "candidate direct descriptor is not Object2-relative",
    )
    by_target = {row.target: row for row in parsed.descriptors}
    require(CUE_TOKEN in by_target and CODE_TOKEN in by_target, "subtitle descriptors are missing")
    cues = parse_cues(by_target[CUE_TOKEN].encoded)
    require(len(cues) == 388, "candidate cue count changed")
    runtime = bytes(value ^ RUNTIME_XOR_KEY for value in by_target[CODE_TOKEN].encoded)
    require(identity(runtime) == STABLE_HEIGHT_RUNTIME_ID, "candidate runtime identity changed")
    verify_stable_refresh_runtime_contract(runtime)

    image = LeImage(candidate_exe)
    spans = _patch_file_ranges(candidate_exe, image)
    video_context, _ = spans["video_context"]
    require(candidate_exe[video_context:video_context + len(VIDEO_REFRESH_CALL_CONTEXT)] == build_stable_refresh_context(), "data-only refresh context changed")
    height_file, _ = spans["height"]
    require(candidate_exe[height_file:height_file + 4] == struct.pack("<I", FULL_VIDEO_REFRESH_HEIGHT), "refresh-height initializer changed")
    cave_file, _ = spans["cave"]
    bootstrap = build_stable_refresh_bootstrap(D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH, RUNTIME_XOR_KEY)
    require(candidate_exe[cave_file:cave_file + CAVE_CAPACITY] == bootstrap, "relocated bootstrap changed")
    reset_state = b"\xC6\x05" + struct.pack("<I", OBJECT3_PREFERRED_BASE + STABLE_REFRESH_HEIGHT_OBJECT_OFFSET) + bytes((FULL_VIDEO_REFRESH_HEIGHT & 0xFF,))
    require(bootstrap.count(reset_state) == 1, "bootstrap height reset changed")
    validator_file, _ = spans["descriptor_validator"]
    require(
        candidate_exe[validator_file:validator_file + DESCRIPTOR_VALIDATOR_SIZE]
        == build_portable_descriptor_validator(),
        "portable descriptor validator changed",
    )
    false_cave_file, _ = spans["false_cave"]
    source_image = LeImage(source_exe)
    source_false_cave = source_image.object_to_file(1, FALSE_CAVE_OBJECT_OFFSET)
    require(
        candidate_exe[false_cave_file:false_cave_file + FALSE_CAVE_SIZE]
        == source_exe[source_false_cave:source_false_cave + FALSE_CAVE_SIZE],
        "Watcom runtime metadata changed",
    )
    veneer_caves = build_h2k3_portable_veneers()
    for name, expected in zip(("h2k3_veneer_cave_a", "h2k3_veneer_cave_b"), veneer_caves):
        file_offset, length = spans[name]
        require(candidate_exe[file_offset:file_offset + length] == expected, f"{name} changed")
    o3_portable_file, o3_portable_length = spans["h2k3_o3_portable"]
    require(
        candidate_exe[o3_portable_file:o3_portable_file + o3_portable_length]
        == build_h2k3_o3_portable_patch(),
        "H2K3 Object3 portable transfer patch changed",
    )
    candidate_fixups = parse_raw_fixups(
        candidate_exe,
        image,
        expected_rows=SOURCE_FIXUP_ROWS + 37,
    )
    require(not any(row.src == 8 for row in candidate_fixups), "self-relative LE fixup survived")
    for source_offset, _opcode, veneer_offset, _target_object, _target_offset in H2K3_O1_EDGE_VENEERS:
        source_file = image.object_to_file(1, source_offset)
        displacement = struct.unpack_from("<i", candidate_exe, source_file)[0]
        require(source_offset + 4 + displacement == veneer_offset, "H2K3 edge is not same-object relative")
    require(b"\xFF\x25" + struct.pack("<I", STABLE_REFRESH_HEIGHT_POINTER) not in candidate_exe, "heap indirect-jump bridge survived")
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
