#!/usr/bin/env python3
"""Build HoMM2 bitmap-font resources from a user-selected OpenType font.

The module intentionally keeps the user's font local.  It reads the selected
face, rasterizes only the 874 characters declared by the release mapping, and
returns rebuilt AGG bytes to the transactional installer.
"""

from __future__ import annotations

import hashlib
import io
import re
import struct
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont


FONT_RESOURCE_NAMES = ("FONT.ICN", "SMALFONT.ICN")
LEGACY_SPRITE_COUNT = 96
AT_SIGN_SPRITE_INDEX = 32
KOREAN_FIRST_INDEX = 0x100
KOREAN_LAST_INDEX = 0x469
KOREAN_GLYPH_COUNT = KOREAN_LAST_INDEX - KOREAN_FIRST_INDEX + 1
FILLER_SPRITE_COUNT = KOREAN_FIRST_INDEX - LEGACY_SPRITE_COUNT
FINAL_SPRITE_COUNT = KOREAN_LAST_INDEX + 1
NORMAL_PIXEL_SIZE = 14
SMALL_PIXEL_SIZE = 12
NORMAL_CELL_WIDTH = 13
NORMAL_CELL_HEIGHT = 14
SMALL_CELL_WIDTH = 11
SMALL_CELL_HEIGHT = 12
FOREGROUND_PALETTE_INDEX = 10
SHADOW_PALETTE_INDEX = 21
SHADOW_OFFSET_X = 1
SHADOW_OFFSET_Y = 1
MINIMUM_PIXEL_SIZE = 4
RENDERER_ID = "pillow-freetype-monochrome-v2-fixed-baseline"
BASELINE_POLICY = "logical-cell-ink-bottom-common-v2"
FIT_POLICY = "largest-common-integer-pixel-size-foreground-fit-v2"
CROP_POLICY = "tight-mask-preserve-logical-cell-offset-v1"
SHADOW_POLICY = "clip-at-logical-cell-edge-v1"

RECRUIT_COST_RESOURCE_NAME = "RECRBKG.ICN"
RECRUIT_COST_LABEL = "병력당 비용:"
RECRUIT_COST_ROI = (157, 51, 96, 17)
RECRUIT_COST_BACKGROUND_SAMPLE_X = 151
RECRUIT_COST_TOP_ADJUST = 2
RECRUIT_COST_FOREGROUND_PALETTE_INDEX = 10
RECRUIT_COST_SHADOW_PALETTE_INDEX = 51
RECRUIT_COST_SOURCE_SIZE = 91_987
RECRUIT_COST_SOURCE_SHA256 = "D7B9EF7C819CADACFABF0BCB857976535945DC6F52DC60581D30AC69513E7024"
RECRUIT_COST_OUTPUT_SIZE = 102_017
RECRUIT_COST_OUTPUT_SHA256 = "F4A2C1B33BDA292E1F4DB06DDE6FF65F1DCF7CA554037FB1011360C6071C505D"
RECRUIT_COST_GLYPH_BOX = (62, 11)
RECRUIT_COST_INK_BBOX = (175, 56, 236, 67)
RECRUIT_COST_INK_PIXEL_COUNT = 339
# Absolute sprite indices pinned by mapping874.fixed-interface-font.txt.  Legacy
# ASCII sprites use ord(character) - 0x20; Korean sprites begin at 0x100.
RECRUIT_COST_GLYPHS = (
    ("병", 0x122, True),
    ("력", 0x115, True),
    ("당", 0x17D, True),
    (" ", 0x00, False),
    ("비", 0x163, True),
    ("용", 0x127, True),
    (":", 0x1A, False),
)

AGG_ENTRY_SIZE = 12
AGG_NAME_SIZE = 15
ICN_HEADER_SIZE = 6
ICN_SPRITE_HEADER_SIZE = 13
MAPPING_ROW = re.compile(
    r"^index 0x([0-9A-Fa-f]+) escape ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) = "
    r"U\+([0-9A-Fa-f]{4,6}) (.)$"
)


class FontBuildError(RuntimeError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise FontBuildError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def agg_filename_hash(name: str) -> int:
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise FontBuildError(f"AGG 리소스 이름이 ASCII가 아닙니다: {name!r}") from exc
    result = 0
    cumulative = 0
    for character in reversed(name):
        value = ord(character.upper())
        result = ((result << 5) + (result >> 25)) & 0xFFFFFFFF
        cumulative = (cumulative + value) & 0xFFFFFFFF
        result = (result + cumulative + value) & 0xFFFFFFFF
    return result


@dataclass(frozen=True)
class MappingRow:
    index: int
    lead: int
    trail: int
    codepoint: int
    character: str


def parse_mapping(path: Path) -> tuple[MappingRow, ...]:
    require(path.is_file(), f"글자 매핑 파일이 없습니다: {path}")
    rows: list[MappingRow] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = MAPPING_ROW.fullmatch(line)
        if match is None:
            continue
        index, lead, trail, codepoint = (int(value, 16) for value in match.groups()[:4])
        character = match.group(5)
        require(character == chr(codepoint), f"매핑 문자와 코드포인트가 다릅니다: {line}")
        rows.append(MappingRow(index, lead, trail, codepoint, character))

    require(len(rows) == KOREAN_GLYPH_COUNT, f"한글 매핑은 {KOREAN_GLYPH_COUNT}자여야 합니다: {len(rows)}")
    require(len({row.codepoint for row in rows}) == len(rows), "한글 매핑에 중복 문자가 있습니다")
    for offset, row in enumerate(rows):
        expected_index = KOREAN_FIRST_INDEX + offset
        expected_lead = 0x82 + (offset >> 7)
        expected_trail = 0x80 + (offset & 0x7F)
        require(row.index == expected_index, f"매핑 인덱스가 연속적이지 않습니다: 0x{row.index:X}")
        require(
            (row.lead, row.trail) == (expected_lead, expected_trail),
            f"매핑 escape가 인덱스와 맞지 않습니다: U+{row.codepoint:04X}",
        )
    return tuple(rows)


def _be_u16(raw: bytes, offset: int, label: str) -> int:
    require(0 <= offset <= len(raw) - 2, f"글꼴 {label} u16 범위가 잘못됐습니다")
    return struct.unpack_from(">H", raw, offset)[0]


def _be_u32(raw: bytes, offset: int, label: str) -> int:
    require(0 <= offset <= len(raw) - 4, f"글꼴 {label} u32 범위가 잘못됐습니다")
    return struct.unpack_from(">I", raw, offset)[0]


def _font_face_offsets(raw: bytes, label: str) -> tuple[int, ...]:
    require(len(raw) >= 12, f"글꼴 파일이 너무 짧습니다: {label}")
    if raw[:4] != b"ttcf":
        return (0,)
    count = _be_u32(raw, 8, f"{label}:ttc-count")
    require(0 < count <= 256 and 12 + count * 4 <= len(raw), f"글꼴 컬렉션 face 수가 잘못됐습니다: {label}")
    offsets = tuple(_be_u32(raw, 12 + index * 4, f"{label}:ttc-offset") for index in range(count))
    require(len(set(offsets)) == len(offsets), f"글꼴 컬렉션 face offset이 중복됐습니다: {label}")
    return offsets


def _sfnt_tables(raw: bytes, face_offset: int, label: str) -> dict[str, tuple[int, int]]:
    require(face_offset + 12 <= len(raw), f"글꼴 face 헤더가 잘렸습니다: {label}")
    require(
        raw[face_offset : face_offset + 4] in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"},
        f"지원되는 SFNT 글꼴 face가 아닙니다: {label}",
    )
    count = _be_u16(raw, face_offset + 4, f"{label}:table-count")
    require(0 < count <= 4096 and face_offset + 12 + count * 16 <= len(raw), f"글꼴 table 수가 잘못됐습니다: {label}")
    tables: dict[str, tuple[int, int]] = {}
    for index in range(count):
        p = face_offset + 12 + index * 16
        try:
            tag = raw[p : p + 4].decode("ascii")
        except UnicodeDecodeError as exc:
            raise FontBuildError(f"글꼴 table tag가 ASCII가 아닙니다: {label}") from exc
        offset = _be_u32(raw, p + 8, f"{label}:{tag}-offset")
        length = _be_u32(raw, p + 12, f"{label}:{tag}-length")
        require(tag not in tables and offset <= len(raw) and length <= len(raw) - offset, f"글꼴 table 범위가 잘못됐습니다: {label}:{tag}")
        tables[tag] = (offset, length)
    require("cmap" in tables, f"Unicode cmap table이 없는 글꼴입니다: {label}")
    return tables


def _decode_name(raw: bytes, platform: int) -> str:
    try:
        if platform in {0, 3}:
            return raw.decode("utf-16-be").strip("\0 ")
        if platform == 1:
            return raw.decode("mac_roman").strip("\0 ")
        return raw.decode("utf-8").strip("\0 ")
    except UnicodeDecodeError:
        return ""


def _font_names(raw: bytes, tables: Mapping[str, tuple[int, int]], label: str) -> dict[int, str]:
    if "name" not in tables:
        return {}
    offset, length = tables["name"]
    require(length >= 6, f"글꼴 name table이 너무 짧습니다: {label}")
    count = _be_u16(raw, offset + 2, f"{label}:name-count")
    strings_offset = _be_u16(raw, offset + 4, f"{label}:name-strings")
    require(6 + count * 12 <= length and strings_offset <= length, f"글꼴 name table 범위가 잘못됐습니다: {label}")
    candidates: dict[int, list[tuple[tuple[int, int, int], str]]] = {1: [], 2: [], 4: [], 6: []}
    for index in range(count):
        p = offset + 6 + index * 12
        platform, encoding, language, name_id, byte_length, relative = struct.unpack_from(">HHHHHH", raw, p)
        if name_id not in candidates:
            continue
        start = offset + strings_offset + relative
        end = start + byte_length
        if start < offset or end > offset + length:
            continue
        value = _decode_name(raw[start:end], platform)
        if not value:
            continue
        priority = (
            0 if platform == 3 and language == 0x0409 else 1 if platform == 3 else 2 if platform == 0 else 3,
            encoding,
            language,
        )
        candidates[name_id].append((priority, value))
    return {name_id: sorted(values, key=lambda item: item[0])[0][1] for name_id, values in candidates.items() if values}


def _cmap_format4_lookup(raw: bytes, offset: int, length: int, label: str) -> Callable[[int], int]:
    require(length >= 16, f"cmap format 4가 너무 짧습니다: {label}")
    seg_count = _be_u16(raw, offset + 6, f"{label}:seg-count") // 2
    require(0 < seg_count <= 0x8000 and 16 + seg_count * 8 <= length, f"cmap format 4 segment가 잘못됐습니다: {label}")
    ends_offset = offset + 14
    starts_offset = ends_offset + seg_count * 2 + 2
    deltas_offset = starts_offset + seg_count * 2
    ranges_offset = deltas_offset + seg_count * 2
    ends = tuple(_be_u16(raw, ends_offset + index * 2, label) for index in range(seg_count))
    starts = tuple(_be_u16(raw, starts_offset + index * 2, label) for index in range(seg_count))

    def lookup(codepoint: int) -> int:
        if not 0 <= codepoint <= 0xFFFF:
            return 0
        index = bisect_left(ends, codepoint)
        if index >= seg_count or codepoint < starts[index]:
            return 0
        delta = _be_u16(raw, deltas_offset + index * 2, label)
        range_offset = _be_u16(raw, ranges_offset + index * 2, label)
        if range_offset == 0:
            return (codepoint + delta) & 0xFFFF
        glyph_address = ranges_offset + index * 2 + range_offset + (codepoint - starts[index]) * 2
        if glyph_address + 2 > offset + length:
            return 0
        glyph = _be_u16(raw, glyph_address, label)
        return ((glyph + delta) & 0xFFFF) if glyph else 0

    return lookup


def _cmap_group_lookup(raw: bytes, offset: int, length: int, label: str, *, constant: bool) -> Callable[[int], int]:
    require(length >= 16, f"cmap group table이 너무 짧습니다: {label}")
    count = _be_u32(raw, offset + 12, f"{label}:group-count")
    require(count <= 0x100000 and 16 + count * 12 <= length, f"cmap group 수가 잘못됐습니다: {label}")
    starts: list[int] = []
    groups: list[tuple[int, int, int]] = []
    previous_end = -1
    for index in range(count):
        start, end, glyph = struct.unpack_from(">III", raw, offset + 16 + index * 12)
        require(start <= end <= 0x10FFFF and start > previous_end, f"cmap group 범위가 잘못됐습니다: {label}")
        starts.append(start)
        groups.append((start, end, glyph))
        previous_end = end

    def lookup(codepoint: int) -> int:
        index = bisect_right(starts, codepoint) - 1
        if index < 0:
            return 0
        start, end, glyph = groups[index]
        if codepoint > end:
            return 0
        return glyph if constant else glyph + codepoint - start

    return lookup


def _cmap_trimmed_lookup(
    raw: bytes, offset: int, length: int, label: str, *, wide: bool
) -> Callable[[int], int]:
    if wide:
        require(length >= 20, f"cmap format 10이 너무 짧습니다: {label}")
        start = _be_u32(raw, offset + 12, f"{label}:start")
        count = _be_u32(raw, offset + 16, f"{label}:count")
        glyphs_offset = offset + 20
        header_size = 20
    else:
        require(length >= 10, f"cmap format 6이 너무 짧습니다: {label}")
        start = _be_u16(raw, offset + 6, f"{label}:start")
        count = _be_u16(raw, offset + 8, f"{label}:count")
        glyphs_offset = offset + 10
        header_size = 10
    require(count <= 0x110000 and header_size + count * 2 <= length, f"cmap trimmed 범위가 잘못됐습니다: {label}")

    def lookup(codepoint: int) -> int:
        if codepoint < start or codepoint >= start + count:
            return 0
        return _be_u16(raw, glyphs_offset + (codepoint - start) * 2, label)

    return lookup


def _unicode_cmap_lookups(raw: bytes, tables: Mapping[str, tuple[int, int]], label: str) -> tuple[Callable[[int], int], ...]:
    cmap_offset, cmap_length = tables["cmap"]
    require(cmap_length >= 4, f"cmap table이 너무 짧습니다: {label}")
    count = _be_u16(raw, cmap_offset + 2, f"{label}:cmap-count")
    require(4 + count * 8 <= cmap_length, f"cmap encoding record가 잘렸습니다: {label}")
    lookups: list[Callable[[int], int]] = []
    seen_offsets: set[int] = set()
    for index in range(count):
        p = cmap_offset + 4 + index * 8
        platform, encoding = struct.unpack_from(">HH", raw, p)
        if platform != 0 and not (platform == 3 and encoding in {1, 10}):
            continue
        relative = _be_u32(raw, p + 4, f"{label}:cmap-subtable")
        subtable = cmap_offset + relative
        if relative >= cmap_length or subtable in seen_offsets or subtable + 4 > cmap_offset + cmap_length:
            continue
        seen_offsets.add(subtable)
        format_number = _be_u16(raw, subtable, f"{label}:cmap-format")
        if format_number in {4, 6}:
            length = _be_u16(raw, subtable + 2, f"{label}:cmap-length")
        elif format_number in {10, 12, 13}:
            require(subtable + 8 <= cmap_offset + cmap_length, f"cmap subtable 헤더가 잘렸습니다: {label}")
            length = _be_u32(raw, subtable + 4, f"{label}:cmap-length")
        else:
            continue
        if length < 4 or relative + length > cmap_length:
            continue
        sublabel = f"{label}:cmap-{format_number}"
        if format_number == 4:
            lookups.append(_cmap_format4_lookup(raw, subtable, length, sublabel))
        elif format_number == 6:
            lookups.append(_cmap_trimmed_lookup(raw, subtable, length, sublabel, wide=False))
        elif format_number == 10:
            lookups.append(_cmap_trimmed_lookup(raw, subtable, length, sublabel, wide=True))
        elif format_number == 12:
            lookups.append(_cmap_group_lookup(raw, subtable, length, sublabel, constant=False))
        else:
            lookups.append(_cmap_group_lookup(raw, subtable, length, sublabel, constant=True))
    require(lookups, f"지원되는 Unicode cmap 형식이 없습니다: {label}")
    return tuple(lookups)


@dataclass(frozen=True)
class FontFace:
    path: Path
    face_index: int
    face_count: int
    sha256: str
    size: int
    raw: bytes
    family: str
    subfamily: str
    full_name: str
    postscript_name: str
    codepoints: frozenset[int]

    def public_metadata(self) -> dict[str, Any]:
        return {
            "file_name": self.path.name,
            "size": self.size,
            "sha256": self.sha256,
            "face_index": self.face_index,
            "face_count": self.face_count,
            "family": self.family,
            "subfamily": self.subfamily,
            "full_name": self.full_name,
            "postscript_name": self.postscript_name,
        }


def inspect_font(
    path: Path,
    face_index: int = 0,
    required_codepoints: Iterable[int] | None = None,
) -> FontFace:
    path = path.expanduser().resolve(strict=True)
    require(path.is_file(), f"글꼴 파일이 아닙니다: {path}")
    try:
        raw = path.read_bytes()
        face_offsets = _font_face_offsets(raw, path.name)
        face_count = len(face_offsets)
        require(0 <= face_index < face_count, f"글꼴 face 번호 범위는 0..{face_count - 1}입니다: {face_index}")
        tables = _sfnt_tables(raw, face_offsets[face_index], f"{path.name}[{face_index}]")
        names = _font_names(raw, tables, f"{path.name}[{face_index}]")
        wanted = (
            {int(codepoint) for codepoint in required_codepoints}
            if required_codepoints is not None
            else set(range(0xAC00, 0xD7A4))
        )
        require(all(0 <= codepoint <= 0x10FFFF for codepoint in wanted), "확인할 Unicode 코드포인트가 잘못됐습니다")
        lookups = _unicode_cmap_lookups(raw, tables, f"{path.name}[{face_index}]")
        supported = frozenset(codepoint for codepoint in wanted if any(lookup(codepoint) != 0 for lookup in lookups))
        return FontFace(
            path=path,
            face_index=face_index,
            face_count=face_count,
            sha256=sha256_bytes(raw),
            size=len(raw),
            raw=raw,
            family=names.get(1, ""),
            subfamily=names.get(2, ""),
            full_name=names.get(4, ""),
            postscript_name=names.get(6, ""),
            codepoints=supported,
        )
    except FontBuildError:
        raise
    except Exception as exc:
        raise FontBuildError(f"지원되는 TTF/OTF/TTC/OTC 글꼴을 읽지 못했습니다: {path.name}: {exc}") from exc


@dataclass(frozen=True)
class FontPlan:
    mapping: tuple[MappingRow, ...]
    primary: FontFace
    fallback: FontFace | None
    primary_codepoints: frozenset[int]
    fallback_codepoints: frozenset[int]
    mode: str

    def metadata(self) -> dict[str, Any]:
        return {
            "schema": "homm2-generated-font-receipt-v1",
            "mode": self.mode,
            "renderer": RENDERER_ID,
            "normal_pixel_size": NORMAL_PIXEL_SIZE,
            "small_pixel_size": SMALL_PIXEL_SIZE,
            "normal_cell": {
                "width": NORMAL_CELL_WIDTH,
                "height": NORMAL_CELL_HEIGHT,
            },
            "small_cell": {
                "width": SMALL_CELL_WIDTH,
                "height": SMALL_CELL_HEIGHT,
            },
            "shadow_offset": [SHADOW_OFFSET_X, SHADOW_OFFSET_Y],
            "baseline_policy": BASELINE_POLICY,
            "fit_policy": FIT_POLICY,
            "crop_policy": CROP_POLICY,
            "shadow_policy": SHADOW_POLICY,
            "mapping_glyph_count": len(self.mapping),
            "first_index": KOREAN_FIRST_INDEX,
            "last_index": KOREAN_LAST_INDEX,
            "blank_legacy_sprite_index": AT_SIGN_SPRITE_INDEX,
            "primary_glyph_count": len(self.primary_codepoints),
            "fallback_glyph_count": len(self.fallback_codepoints),
            "primary": self.primary.public_metadata(),
            "fallback": self.fallback.public_metadata() if self.fallback else None,
        }


def make_font_plan(
    mapping_path: Path,
    primary_path: Path,
    *,
    primary_face_index: int = 0,
    fallback_path: Path | None = None,
    fallback_face_index: int = 0,
    mode: str,
) -> FontPlan:
    require(mode in {"default", "custom"}, f"글꼴 선택 모드가 잘못됐습니다: {mode}")
    mapping = parse_mapping(mapping_path)
    required = {row.codepoint for row in mapping}
    primary = inspect_font(primary_path, primary_face_index, required)
    primary_codepoints = frozenset(required & primary.codepoints)
    missing = required - primary_codepoints

    fallback: FontFace | None = None
    fallback_codepoints: frozenset[int] = frozenset()
    if missing and fallback_path is not None:
        fallback = inspect_font(fallback_path, fallback_face_index, missing)
        fallback_codepoints = frozenset(missing & fallback.codepoints)
        missing -= fallback_codepoints
    require(
        not missing,
        "선택 글꼴과 기본 대체 글꼴에 없는 문자가 있습니다: "
        + " ".join(f"U+{codepoint:04X}" for codepoint in sorted(missing)[:20]),
    )
    return FontPlan(mapping, primary, fallback, primary_codepoints, fallback_codepoints, mode)


@dataclass(frozen=True)
class Sprite:
    offset_x: int
    offset_y: int
    width: int
    height: int
    animation: int
    payload: bytes


@dataclass(frozen=True)
class _DecodedSprite:
    offset_x: int
    offset_y: int
    width: int
    height: int
    animation: int
    pixels: bytes
    transform: bytes


def _encode_sprite_data(width: int, height: int, pixels: bytes, transform: bytes) -> bytes:
    require(width > 0 and height > 0, "글리프 크기가 0입니다")
    require(len(pixels) == width * height == len(transform), "글리프 버퍼 크기가 잘못됐습니다")
    output = bytearray()
    for y in range(height):
        x = 0
        while x < width:
            position = y * width + x
            flag = transform[position]
            limit = 127 if flag == 0 else 63 if flag == 1 else 255
            run = 0
            while x + run < width and run < limit:
                if transform[y * width + x + run] != flag:
                    break
                run += 1
            require(run > 0, "글리프 RLE가 진행되지 않습니다")
            if flag == 0:
                output.append(run)
                start = y * width + x
                output.extend(pixels[start : start + run])
            elif flag == 1:
                output.append(0x80 + run)
            else:
                require(2 <= flag <= 15, f"지원하지 않는 ICN transform입니다: {flag}")
                tag = 0x40 | ((flag - 2) << 2)
                if run <= 3:
                    output.extend((0xC0, tag | run))
                else:
                    output.extend((0xC0, tag, run))
            x += run
        output.append(0)
    output.append(0x80)
    return bytes(output)


def _decode_sprite(sprite: Sprite, *, label: str) -> _DecodedSprite:
    pixels = bytearray(sprite.width * sprite.height)
    transform = bytearray([1]) * (sprite.width * sprite.height)
    position = 0
    row = 0
    x = 0
    monochrome = bool(sprite.animation & 0x20)
    ended = False

    def take() -> int:
        nonlocal position
        require(position < len(sprite.payload), f"ICN 명령이 잘렸습니다: {label}")
        value = sprite.payload[position]
        position += 1
        return value

    def put(target: bytearray, value: bytes | int, count: int) -> None:
        nonlocal x
        require(0 <= row < sprite.height and x + count <= sprite.width, f"ICN run이 스프라이트를 넘었습니다: {label}")
        start = row * sprite.width + x
        target[start : start + count] = bytes((value,)) * count if isinstance(value, int) else value

    while position < len(sprite.payload):
        command = take()
        if command == 0x80:
            ended = True
            break
        if command == 0:
            row += 1
            x = 0
            require(row <= sprite.height, f"ICN 행이 너무 많습니다: {label}")
            continue
        require(row < sprite.height, f"ICN이 마지막 행 뒤에 기록됩니다: {label}")
        if monochrome:
            if command < 0x80:
                put(transform, 0, command)
                x += command
            else:
                x += command - 0x80
            require(x <= sprite.width, f"ICN monochrome skip이 넘쳤습니다: {label}")
        elif command < 0x80:
            count = command
            require(position + count <= len(sprite.payload), f"ICN literal이 잘렸습니다: {label}")
            literal = sprite.payload[position : position + count]
            position += count
            put(pixels, literal, count)
            put(transform, 0, count)
            x += count
        elif command < 0xC0:
            x += command - 0x80
            require(x <= sprite.width, f"ICN skip이 넘쳤습니다: {label}")
        elif command == 0xC0:
            tag = take()
            count = tag & 3 or take()
            transform_type = ((tag & 0x3C) >> 2) + 2
            if tag & 0x40 and transform_type < 16:
                put(transform, transform_type, count)
            x += count
            require(x <= sprite.width, f"ICN transform이 넘쳤습니다: {label}")
        else:
            count = take() if command == 0xC1 else command - 0xC0
            color = take()
            put(pixels, color, count)
            put(transform, 0, count)
            x += count
    require(ended and position == len(sprite.payload), f"ICN 종료 marker가 잘못됐습니다: {label}")
    return _DecodedSprite(
        sprite.offset_x,
        sprite.offset_y,
        sprite.width,
        sprite.height,
        sprite.animation,
        bytes(pixels),
        bytes(transform),
    )


def _validate_sprite_payload(sprite: Sprite) -> None:
    position = 0
    for _ in range(sprite.height):
        x = 0
        while True:
            require(position < len(sprite.payload), "글리프 RLE 행이 잘렸습니다")
            command = sprite.payload[position]
            position += 1
            if command == 0:
                break
            require(command != 0x80, "글리프 RLE 종료가 행 안에 있습니다")
            if command > 0x80:
                x += command - 0x80
            else:
                require(position + command <= len(sprite.payload), "글리프 RLE literal이 잘렸습니다")
                position += command
                x += command
            require(x <= sprite.width, "글리프 RLE가 행 너비를 넘었습니다")
        require(x == sprite.width, "글리프 RLE 행 너비가 맞지 않습니다")
    require(position + 1 == len(sprite.payload) and sprite.payload[position] == 0x80, "글리프 RLE 끝이 잘못됐습니다")


@dataclass(frozen=True)
class _GlyphMask:
    character: str
    left: int
    top: int
    mask: Image.Image

    @property
    def right(self) -> int:
        return self.left + self.mask.width

    @property
    def bottom(self) -> int:
        return self.top + self.mask.height


@dataclass(frozen=True)
class _FaceLayout:
    requested_pixel_size: int
    resolved_pixel_size: int
    cell_width: int
    cell_height: int
    origin_x: int
    baseline_y: int
    union_left: int
    union_top: int
    union_right: int
    union_bottom: int
    glyphs: Mapping[int, _GlyphMask]

    def shadow_edge_clip_count(self) -> int:
        clipped = 0
        for glyph in self.glyphs.values():
            occupied_width = min(self.cell_width, glyph.mask.width + SHADOW_OFFSET_X)
            offset_x = (self.cell_width - occupied_width) // 2
            width = self.cell_width - offset_x
            height = glyph.mask.height
            for y in range(glyph.mask.height):
                for x in range(glyph.mask.width):
                    if not glyph.mask.getpixel((x, y)):
                        continue
                    if x + SHADOW_OFFSET_X >= width or y + SHADOW_OFFSET_Y >= height:
                        clipped += 1
        return clipped

    def metadata(self) -> dict[str, Any]:
        return {
            "requested_pixel_size": self.requested_pixel_size,
            "resolved_pixel_size": self.resolved_pixel_size,
            "cell_width": self.cell_width,
            "cell_height": self.cell_height,
            "origin_x": self.origin_x,
            "baseline_y": self.baseline_y,
            "ink_union": [self.union_left, self.union_top, self.union_right, self.union_bottom],
            "glyph_count": len(self.glyphs),
            "foreground_clip_count": 0,
            "shadow_edge_clip_count": self.shadow_edge_clip_count(),
        }


def _rasterize_glyph(font: ImageFont.FreeTypeFont, character: str) -> _GlyphMask:
    bbox = font.getbbox(character, anchor="ls")
    require(bbox is not None, f"빈 글리프입니다: U+{ord(character):04X}")
    left, top, right, bottom = (int(value) for value in bbox)
    require(left < right and top < bottom, f"글리프 bbox가 비었습니다: U+{ord(character):04X}")
    padding = 4
    anchor_x = padding - left
    anchor_y = padding - top
    image = Image.new("1", (right - left + padding * 2, bottom - top + padding * 2), 0)
    draw = ImageDraw.Draw(image)
    draw.text((anchor_x, anchor_y), character, font=font, fill=1, anchor="ls")
    crop = image.getbbox()
    require(crop is not None, f"렌더링 결과가 빈 글리프입니다: U+{ord(character):04X}")
    mask = image.crop(crop)
    actual_left = crop[0] - anchor_x
    actual_top = crop[1] - anchor_y
    return _GlyphMask(character, actual_left, actual_top, mask)


def _load_freetype(face: FontFace, pixel_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        io.BytesIO(face.raw),
        pixel_size,
        index=face.face_index,
        layout_engine=ImageFont.Layout.BASIC,
    )


def _build_face_layout(
    face: FontFace,
    characters: Mapping[int, str],
    *,
    requested_pixel_size: int,
    cell_width: int,
    cell_height: int,
) -> _FaceLayout | None:
    if not characters:
        return None
    require(len(set(characters.values())) == len(characters), "face 글리프 문자가 중복됐습니다")
    require(
        requested_pixel_size >= MINIMUM_PIXEL_SIZE
        and cell_width > SHADOW_OFFSET_X
        and cell_height > SHADOW_OFFSET_Y,
        "글리프 논리 셀 설정이 잘못됐습니다",
    )

    pixel_size = requested_pixel_size
    while True:
        font = _load_freetype(face, pixel_size)
        glyphs = {codepoint: _rasterize_glyph(font, character) for codepoint, character in characters.items()}
        union_left = min(glyph.left for glyph in glyphs.values())
        union_top = min(glyph.top for glyph in glyphs.values())
        union_right = max(glyph.right for glyph in glyphs.values())
        union_bottom = max(glyph.bottom for glyph in glyphs.values())
        maximum_width = max(glyph.mask.width for glyph in glyphs.values())
        maximum_height = max(glyph.mask.height for glyph in glyphs.values())
        if maximum_width <= cell_width and maximum_height <= cell_height:
            origin_x = cell_width // 2
            baseline_y = cell_height
            return _FaceLayout(
                requested_pixel_size,
                pixel_size,
                cell_width,
                cell_height,
                origin_x,
                baseline_y,
                union_left,
                union_top,
                union_right,
                union_bottom,
                glyphs,
            )

        require(
            pixel_size > MINIMUM_PIXEL_SIZE,
            f"글리프 face를 {cell_width}x{cell_height} 논리 셀에 맞출 수 없습니다: {face.path.name}",
        )
        pixel_size -= 1


def _render_sprite(layout: _FaceLayout, codepoint: int) -> Sprite:
    glyph = layout.glyphs[codepoint]
    occupied_width = min(layout.cell_width, glyph.mask.width + SHADOW_OFFSET_X)
    offset_x = (layout.cell_width - occupied_width) // 2
    offset_y = layout.baseline_y - glyph.mask.height
    width = layout.cell_width - offset_x
    height = layout.cell_height - offset_y
    require(
        0 <= offset_x < layout.cell_width
        and 0 <= offset_y < layout.cell_height
        and width >= glyph.mask.width
        and height >= glyph.mask.height
        and offset_y + height <= layout.cell_height,
        f"글리프가 논리 셀을 넘었습니다: U+{codepoint:04X}",
    )
    pixels = bytearray(width * height)
    transform = bytearray([1]) * (width * height)

    points = [
        (x, y)
        for y in range(glyph.mask.height)
        for x in range(glyph.mask.width)
        if glyph.mask.getpixel((x, y))
    ]
    require(points, f"렌더링 결과에 점이 없습니다: U+{codepoint:04X}")
    for x, y in points:
        shadow_x = x + SHADOW_OFFSET_X
        shadow_y = y + SHADOW_OFFSET_Y
        if shadow_x < width and shadow_y < height:
            index = shadow_y * width + shadow_x
            pixels[index] = SHADOW_PALETTE_INDEX
            transform[index] = 0
    for x, y in points:
        index = y * width + x
        pixels[index] = FOREGROUND_PALETTE_INDEX
        transform[index] = 0

    sprite = Sprite(offset_x, offset_y, width, height, 0, _encode_sprite_data(width, height, bytes(pixels), bytes(transform)))
    _validate_sprite_payload(sprite)
    return sprite


@dataclass(frozen=True)
class RenderedFont:
    normal: tuple[Sprite, ...]
    small: tuple[Sprite, ...]
    metadata: dict[str, Any]


def render_font(plan: FontPlan) -> RenderedFont:
    try:
        primary_characters = {
            row.codepoint: row.character for row in plan.mapping if row.codepoint in plan.primary_codepoints
        }
        fallback_characters = {
            row.codepoint: row.character for row in plan.mapping if row.codepoint in plan.fallback_codepoints
        }
        primary_normal = _build_face_layout(
            plan.primary,
            primary_characters,
            requested_pixel_size=NORMAL_PIXEL_SIZE,
            cell_width=NORMAL_CELL_WIDTH,
            cell_height=NORMAL_CELL_HEIGHT,
        )
        primary_small = _build_face_layout(
            plan.primary,
            primary_characters,
            requested_pixel_size=SMALL_PIXEL_SIZE,
            cell_width=SMALL_CELL_WIDTH,
            cell_height=SMALL_CELL_HEIGHT,
        )
        fallback_normal = fallback_small = None
        if plan.fallback is not None:
            fallback_normal = _build_face_layout(
                plan.fallback,
                fallback_characters,
                requested_pixel_size=NORMAL_PIXEL_SIZE,
                cell_width=NORMAL_CELL_WIDTH,
                cell_height=NORMAL_CELL_HEIGHT,
            )
            fallback_small = _build_face_layout(
                plan.fallback,
                fallback_characters,
                requested_pixel_size=SMALL_PIXEL_SIZE,
                cell_width=SMALL_CELL_WIDTH,
                cell_height=SMALL_CELL_HEIGHT,
            )
    except FontBuildError:
        raise
    except Exception as exc:
        raise FontBuildError(f"FreeType으로 글꼴을 열지 못했습니다: {exc}") from exc

    normal: list[Sprite] = []
    small: list[Sprite] = []
    for row in plan.mapping:
        use_primary = row.codepoint in plan.primary_codepoints
        normal_font = primary_normal if use_primary else fallback_normal
        small_font = primary_small if use_primary else fallback_small
        require(normal_font is not None and small_font is not None, f"대체 글꼴 선택 오류: U+{row.codepoint:04X}")
        normal.append(_render_sprite(normal_font, row.codepoint))
        small.append(_render_sprite(small_font, row.codepoint))
    require(len(normal) == len(small) == KOREAN_GLYPH_COUNT, "생성된 글리프 수가 맞지 않습니다")
    metadata = plan.metadata()
    metadata["resolved_faces"] = {
        "primary": {
            "normal": primary_normal.metadata() if primary_normal else None,
            "small": primary_small.metadata() if primary_small else None,
        },
        "fallback": {
            "normal": fallback_normal.metadata() if fallback_normal else None,
            "small": fallback_small.metadata() if fallback_small else None,
        }
        if plan.fallback is not None
        else None,
    }
    return RenderedFont(tuple(normal), tuple(small), metadata)


@dataclass(frozen=True)
class IcnArchive:
    sprites: tuple[Sprite, ...]


def parse_icn(raw: bytes, *, label: str) -> IcnArchive:
    require(len(raw) >= ICN_HEADER_SIZE, f"ICN이 너무 짧습니다: {label}")
    count, total_size = struct.unpack_from("<HI", raw, 0)
    require(total_size + ICN_HEADER_SIZE == len(raw), f"ICN 크기 필드가 맞지 않습니다: {label}")
    headers_size = count * ICN_SPRITE_HEADER_SIZE
    require(ICN_HEADER_SIZE + headers_size <= len(raw), f"ICN 헤더가 잘렸습니다: {label}")
    offsets: list[int] = []
    headers: list[tuple[int, int, int, int, int]] = []
    for index in range(count):
        p = ICN_HEADER_SIZE + index * ICN_SPRITE_HEADER_SIZE
        offset_x, offset_y, width, height, animation, data_offset = struct.unpack_from("<hhHHBI", raw, p)
        require(headers_size <= data_offset < total_size, f"ICN 데이터 offset이 잘못됐습니다: {label}:{index}")
        require(not offsets or data_offset >= offsets[-1], f"ICN 데이터 offset 순서가 잘못됐습니다: {label}:{index}")
        offsets.append(data_offset)
        headers.append((offset_x, offset_y, width, height, animation))
    if count:
        require(offsets[0] == headers_size, f"ICN 첫 데이터 offset이 잘못됐습니다: {label}")
    sprites: list[Sprite] = []
    for index, data_offset in enumerate(offsets):
        data_end = offsets[index + 1] if index + 1 < count else total_size
        require(data_offset <= data_end <= total_size, f"ICN 데이터 범위가 잘못됐습니다: {label}:{index}")
        start = ICN_HEADER_SIZE + data_offset
        end = ICN_HEADER_SIZE + data_end
        sprites.append(Sprite(*headers[index], raw[start:end]))
    return IcnArchive(tuple(sprites))


def pack_icn(sprites: Sequence[Sprite]) -> bytes:
    require(0 < len(sprites) <= 0xFFFF, "ICN sprite 수가 범위를 벗어났습니다")
    offset = len(sprites) * ICN_SPRITE_HEADER_SIZE
    offsets: list[int] = []
    for sprite in sprites:
        require(0 <= sprite.width <= 0xFFFF and 0 <= sprite.height <= 0xFFFF, "ICN sprite 크기가 범위를 벗어났습니다")
        offsets.append(offset)
        offset += len(sprite.payload)
        require(offset <= 0xFFFFFFFF, "ICN 전체 크기가 범위를 벗어났습니다")
    output = bytearray(struct.pack("<HI", len(sprites), offset))
    for sprite, data_offset in zip(sprites, offsets):
        output.extend(
            struct.pack(
                "<hhHHBI",
                sprite.offset_x,
                sprite.offset_y,
                sprite.width,
                sprite.height,
                sprite.animation,
                data_offset,
            )
        )
    for sprite in sprites:
        output.extend(sprite.payload)
    return bytes(output)


def _localize_recruit_cost_label(
    source_raw: bytes,
    small_font_sprites: Sequence[Sprite],
    *,
    label: str,
) -> bytes:
    """Render the approved Korean cost label into the pristine recruit background."""

    require(
        len(source_raw) == RECRUIT_COST_SOURCE_SIZE
        and sha256_bytes(source_raw) == RECRUIT_COST_SOURCE_SHA256,
        f"순정 {RECRUIT_COST_RESOURCE_NAME} identity가 다릅니다: {label}",
    )
    source = parse_icn(source_raw, label=f"{label}:source")
    require(len(source.sprites) == 2, f"{RECRUIT_COST_RESOURCE_NAME} sprite 수가 다릅니다: {label}")
    background_sprite = source.sprites[0]
    require(
        (
            background_sprite.offset_x,
            background_sprite.offset_y,
            background_sprite.width,
            background_sprite.height,
            background_sprite.animation,
        )
        == (16, 0, 321, 304, 0),
        f"{RECRUIT_COST_RESOURCE_NAME}:0 layout이 다릅니다: {label}",
    )
    require(
        "".join(character for character, _, _ in RECRUIT_COST_GLYPHS) == RECRUIT_COST_LABEL,
        "모집 비용 문구 glyph 계약이 다릅니다",
    )
    require(
        all(0 <= index < len(small_font_sprites) for _, index, _ in RECRUIT_COST_GLYPHS),
        "모집 비용 문구 glyph index가 글꼴 범위를 넘었습니다",
    )

    decoded_background = _decode_sprite(background_sprite, label=f"{label}:background")
    decoded_glyphs = tuple(
        _decode_sprite(small_font_sprites[index], label=f"{label}:glyph:{character}")
        for character, index, _ in RECRUIT_COST_GLYPHS
    )
    total_width = sum(glyph.width for glyph in decoded_glyphs) + len(decoded_glyphs) - 1
    maximum_height = max(glyph.height for glyph in decoded_glyphs)
    require(
        (total_width, maximum_height) == RECRUIT_COST_GLYPH_BOX,
        f"모집 비용 문구 glyph 크기가 다릅니다: {label}: {(total_width, maximum_height)}",
    )

    x0, y0, width, height = RECRUIT_COST_ROI
    require(
        0 <= RECRUIT_COST_BACKGROUND_SAMPLE_X < x0
        and x0 + width <= decoded_background.width
        and y0 + height <= decoded_background.height,
        f"모집 비용 ROI가 배경 범위를 넘었습니다: {label}",
    )
    pixels = bytearray(decoded_background.pixels)
    transform = bytearray(decoded_background.transform)
    for y in range(y0, y0 + height):
        sample = y * decoded_background.width + RECRUIT_COST_BACKGROUND_SAMPLE_X
        for x in range(x0, x0 + width):
            destination = y * decoded_background.width + x
            pixels[destination] = decoded_background.pixels[sample]
            transform[destination] = decoded_background.transform[sample]

    cursor = x0 + (width - total_width) // 2
    logical_top = y0 + (height - SMALL_CELL_HEIGHT) // 2 + RECRUIT_COST_TOP_ADJUST
    ink: list[tuple[int, int]] = []
    for (character, _, korean), glyph in zip(RECRUIT_COST_GLYPHS, decoded_glyphs):
        if character != " ":
            for offset, flag in enumerate(glyph.transform):
                if flag:
                    continue
                x = cursor + glyph.offset_x + offset % glyph.width
                y = logical_top + glyph.offset_y + offset // glyph.width
                require(
                    x0 <= x < x0 + width and y0 <= y < y0 + height,
                    f"모집 비용 문구가 ROI를 넘었습니다: {label}:{character}",
                )
                palette = glyph.pixels[offset]
                if korean:
                    require(
                        palette in {FOREGROUND_PALETTE_INDEX, SHADOW_PALETTE_INDEX},
                        f"한글 glyph palette가 다릅니다: {label}:{character}:{palette}",
                    )
                destination = y * decoded_background.width + x
                pixels[destination] = (
                    RECRUIT_COST_FOREGROUND_PALETTE_INDEX
                    if palette == FOREGROUND_PALETTE_INDEX
                    else RECRUIT_COST_SHADOW_PALETTE_INDEX
                )
                transform[destination] = 0
                ink.append((x, y))
        cursor += glyph.width + 1

    require(ink, f"모집 비용 문구 ink가 비었습니다: {label}")
    ink_bbox = (
        min(x for x, _ in ink),
        min(y for _, y in ink),
        max(x for x, _ in ink) + 1,
        max(y for _, y in ink) + 1,
    )
    require(
        ink_bbox == RECRUIT_COST_INK_BBOX and len(ink) == RECRUIT_COST_INK_PIXEL_COUNT,
        f"모집 비용 문구 ink 계약이 다릅니다: {label}: {ink_bbox}/{len(ink)}",
    )

    localized_background = Sprite(
        decoded_background.offset_x,
        decoded_background.offset_y,
        decoded_background.width,
        decoded_background.height,
        decoded_background.animation,
        _encode_sprite_data(
            decoded_background.width,
            decoded_background.height,
            bytes(pixels),
            bytes(transform),
        ),
    )
    result = pack_icn((localized_background, *source.sprites[1:]))
    require(
        len(result) == RECRUIT_COST_OUTPUT_SIZE and sha256_bytes(result) == RECRUIT_COST_OUTPUT_SHA256,
        f"생성된 {RECRUIT_COST_RESOURCE_NAME} identity가 다릅니다: {label}",
    )

    candidate = parse_icn(result, label=f"{label}:candidate")
    require(candidate.sprites[1:] == source.sprites[1:], f"{RECRUIT_COST_RESOURCE_NAME}:1이 바뀌었습니다: {label}")
    decoded_candidate = _decode_sprite(candidate.sprites[0], label=f"{label}:candidate-background")
    for y in range(decoded_background.height):
        for x in range(decoded_background.width):
            if x0 <= x < x0 + width and y0 <= y < y0 + height:
                continue
            offset = y * decoded_background.width + x
            require(
                decoded_candidate.pixels[offset] == decoded_background.pixels[offset]
                and decoded_candidate.transform[offset] == decoded_background.transform[offset],
                f"{RECRUIT_COST_RESOURCE_NAME}:0 ROI 밖 픽셀이 바뀌었습니다: {label}:{x},{y}",
            )
    return result


@dataclass(frozen=True)
class AggEntry:
    index: int
    name: str
    name_slot: bytes
    hash_word: int
    payload: bytes


@dataclass(frozen=True)
class AggArchive:
    entries: tuple[AggEntry, ...]
    raw: bytes

    def get(self, name: str) -> AggEntry:
        folded = name.upper()
        for entry in self.entries:
            if entry.name.upper() == folded:
                return entry
        raise FontBuildError(f"AGG 리소스가 없습니다: {name}")


def parse_agg(raw: bytes, *, label: str) -> AggArchive:
    require(len(raw) >= 2, f"AGG가 너무 짧습니다: {label}")
    count = struct.unpack_from("<H", raw, 0)[0]
    table_end = 2 + count * AGG_ENTRY_SIZE
    names_start = len(raw) - count * AGG_NAME_SIZE
    require(table_end <= names_start, f"AGG 테이블과 이름 영역이 겹칩니다: {label}")
    expected_offset = table_end
    seen: set[str] = set()
    entries: list[AggEntry] = []
    for index in range(count):
        hash_word, offset, size = struct.unpack_from("<III", raw, 2 + index * AGG_ENTRY_SIZE)
        require(offset == expected_offset and offset + size <= names_start, f"AGG 데이터 범위가 잘못됐습니다: {label}:{index}")
        slot = raw[names_start + index * AGG_NAME_SIZE : names_start + (index + 1) * AGG_NAME_SIZE]
        nul = slot.find(b"\0")
        try:
            name = slot[: AGG_NAME_SIZE if nul < 0 else nul].decode("ascii")
        except UnicodeDecodeError as exc:
            raise FontBuildError(f"AGG 이름이 ASCII가 아닙니다: {label}:{index}") from exc
        folded = name.upper()
        require(name and folded not in seen, f"AGG 이름이 비었거나 중복됐습니다: {label}:{index}")
        require(hash_word == agg_filename_hash(name), f"AGG 이름 hash가 맞지 않습니다: {label}:{name}")
        seen.add(folded)
        entries.append(AggEntry(index, name, slot, hash_word, raw[offset : offset + size]))
        expected_offset = offset + size
    require(expected_offset == names_start, f"AGG 데이터와 이름 영역 사이에 빈 공간이 있습니다: {label}")
    return AggArchive(tuple(entries), raw)


def repack_agg(archive: AggArchive, replacements: Mapping[str, bytes]) -> bytes:
    folded = {name.upper(): payload for name, payload in replacements.items()}
    known = {entry.name.upper() for entry in archive.entries}
    require(not (set(folded) - known), f"AGG에 없는 리소스 교체 요청입니다: {sorted(set(folded) - known)}")
    payloads = [folded.get(entry.name.upper(), entry.payload) for entry in archive.entries]
    offset = 2 + len(archive.entries) * AGG_ENTRY_SIZE
    offsets: list[int] = []
    for payload in payloads:
        offsets.append(offset)
        offset += len(payload)
        require(offset <= 0xFFFFFFFF, "AGG 전체 크기가 범위를 벗어났습니다")
    output = bytearray(struct.pack("<H", len(archive.entries)))
    for entry, data_offset, payload in zip(archive.entries, offsets, payloads):
        output.extend(struct.pack("<III", entry.hash_word, data_offset, len(payload)))
    for payload in payloads:
        output.extend(payload)
    for entry in archive.entries:
        output.extend(entry.name_slot)
    return bytes(output)


def changed_agg_resources(left_raw: bytes, right_raw: bytes, *, label: str) -> tuple[str, ...]:
    left = parse_agg(left_raw, label=f"{label}:left")
    right = parse_agg(right_raw, label=f"{label}:right")
    require(len(left.entries) == len(right.entries), f"AGG 리소스 수가 다릅니다: {label}")
    changed: list[str] = []
    for a, b in zip(left.entries, right.entries):
        require(
            (a.index, a.name, a.name_slot, a.hash_word) == (b.index, b.name, b.name_slot, b.hash_word),
            f"AGG 리소스 목록이 다릅니다: {label}:{a.index}",
        )
        if a.payload != b.payload:
            changed.append(a.name)
    return tuple(changed)


def make_localized_font_base(
    original_raw: bytes,
    patched_raw: bytes,
    *,
    keep_localized_resources: Iterable[str],
    expected_patched_changes: Iterable[str],
    label: str,
) -> bytes:
    original = parse_agg(original_raw, label=f"{label}:original")
    patched = parse_agg(patched_raw, label=f"{label}:patched")
    actual_changes = {name.upper() for name in changed_agg_resources(original_raw, patched_raw, label=label)}
    expected = {name.upper() for name in expected_patched_changes}
    require(actual_changes == expected, f"활성 AGG 변경 리소스 집합이 예상과 다릅니다: {label}: {sorted(actual_changes)}")
    keep = {name.upper() for name in keep_localized_resources}
    require(keep <= actual_changes, f"유지할 AGG 리소스가 활성 변경 집합에 없습니다: {label}: {sorted(keep - actual_changes)}")
    patched_by_name = {entry.name.upper(): entry.payload for entry in patched.entries}
    replacements = {entry.name: patched_by_name[entry.name.upper()] for entry in original.entries if entry.name.upper() in keep}
    result = repack_agg(original, replacements)
    result_changes = {name.upper() for name in changed_agg_resources(original_raw, result, label=f"{label}:base")}
    require(result_changes == keep, f"font/raster-free AGG 변경 집합이 잘못됐습니다: {label}: {sorted(result_changes)}")
    return result


def rebuild_agg_fonts(base_raw: bytes, rendered: RenderedFont, *, label: str) -> bytes:
    base = parse_agg(base_raw, label=f"{label}:base")
    replacements: dict[str, bytes] = {}
    rebuilt_font_sprites: dict[str, tuple[Sprite, ...]] = {}
    for resource_name, additions in (("FONT.ICN", rendered.normal), ("SMALFONT.ICN", rendered.small)):
        resource = base.get(resource_name)
        legacy = parse_icn(resource.payload, label=f"{label}:{resource_name}")
        require(
            len(legacy.sprites) == LEGACY_SPRITE_COUNT,
            f"원본 {resource_name} sprite 수가 {LEGACY_SPRITE_COUNT}이 아닙니다: {len(legacy.sprites)}",
        )
        legacy_sprites = list(legacy.sprites)
        blank_at_sign = Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80")
        _validate_sprite_payload(blank_at_sign)
        legacy_sprites[AT_SIGN_SPRITE_INDEX] = blank_at_sign
        filler = (legacy.sprites[0],) * FILLER_SPRITE_COUNT
        sprites = tuple(legacy_sprites) + filler + additions
        require(len(sprites) == FINAL_SPRITE_COUNT, f"최종 {resource_name} sprite 수가 맞지 않습니다")
        replacements[resource_name] = pack_icn(sprites)
        rebuilt_font_sprites[resource_name] = sprites

    recruit_entries = [entry for entry in base.entries if entry.name.upper() == RECRUIT_COST_RESOURCE_NAME]
    require(len(recruit_entries) <= 1, f"{RECRUIT_COST_RESOURCE_NAME}가 중복됐습니다: {label}")
    if recruit_entries:
        recruit = recruit_entries[0]
        replacements[recruit.name] = _localize_recruit_cost_label(
            recruit.payload,
            rebuilt_font_sprites["SMALFONT.ICN"],
            label=f"{label}:{recruit.name}",
        )

    output = repack_agg(base, replacements)
    candidate = parse_agg(output, label=f"{label}:candidate")
    changed = {name.upper() for name in changed_agg_resources(base_raw, output, label=f"{label}:font-rebuild")}
    expected_changes = {name.upper() for name in FONT_RESOURCE_NAMES}
    if recruit_entries:
        expected_changes.add(RECRUIT_COST_RESOURCE_NAME)
    require(
        changed == expected_changes,
        f"폰트/모집 비용 명패 외 AGG 리소스가 바뀌었습니다: {label}: {sorted(changed)}",
    )
    for resource_name in FONT_RESOURCE_NAMES:
        before = parse_icn(base.get(resource_name).payload, label=f"{label}:before:{resource_name}")
        after = parse_icn(candidate.get(resource_name).payload, label=f"{label}:after:{resource_name}")
        require(len(after.sprites) == FINAL_SPRITE_COUNT, f"생성된 {resource_name} sprite 수가 맞지 않습니다")
        require(
            after.sprites[:AT_SIGN_SPRITE_INDEX] == before.sprites[:AT_SIGN_SPRITE_INDEX]
            and after.sprites[AT_SIGN_SPRITE_INDEX + 1 : LEGACY_SPRITE_COUNT]
            == before.sprites[AT_SIGN_SPRITE_INDEX + 1 :],
            f"기존 {resource_name} sprite가 @ 칸 외에서 바뀌었습니다",
        )
        require(
            after.sprites[AT_SIGN_SPRITE_INDEX] == Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80"),
            f"{resource_name}의 @ 칸이 투명 글리프가 아닙니다",
        )
        require(
            all(sprite == before.sprites[0] for sprite in after.sprites[LEGACY_SPRITE_COUNT:KOREAN_FIRST_INDEX]),
            f"{resource_name} filler가 원본 sprite 0과 다릅니다",
        )
    if recruit_entries:
        require(
            len(candidate.get(RECRUIT_COST_RESOURCE_NAME).payload) == RECRUIT_COST_OUTPUT_SIZE
            and sha256_bytes(candidate.get(RECRUIT_COST_RESOURCE_NAME).payload) == RECRUIT_COST_OUTPUT_SHA256,
            f"생성된 {RECRUIT_COST_RESOURCE_NAME} 검증이 실패했습니다: {label}",
        )
    return output
