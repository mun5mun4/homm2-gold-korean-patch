#!/usr/bin/env python3
"""Apply or verify the pinned relocated-runtime H2K3 hotfix.

The tool rewrites the Followers sentence and rebases all 155 Object2-backed
general descriptors from LE preferred coordinates to the addresses observed in
the running game. Seven runtime unit-name descriptors and sixteen renderer
tokens remain unchanged. The tool refuses every input except the exact active
beta.2 ``KOREAN.BIN`` and never edits a game installation in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

if __package__:
    from .h2k3_bank import HEADER, parse_bank, serialize_bank, token_allowed
else:  # Support direct execution: python tools/localization/final_bank_hotfix.py
    from h2k3_bank import HEADER, parse_bank, serialize_bank, token_allowed


SOURCE_IDENTITY = (
    11_290,
    "6D154CEE42447F2BBCFC1717B0385A24F9146B8B5C8717E0361DBDCD5884C142",
)
TARGET_IDENTITY = (
    11_286,
    "DD30DD967E81BB179BC1D33903D0B8926FB799D969A3C36FFAA6CA3FA0C89AAF",
)
MAPPING_IDENTITY = (
    42_302,
    "3033584F6E65A36220F61EA58F8D7173A493FC83A72807D6FB43488AAE6DF164",
)
EXPECTED_MAPPING_TAG = 0x4F583330
EXPECTED_RENDER_COUNT = 16
EXPECTED_DESCRIPTOR_COUNT = 178
EXPECTED_GENERAL_DESCRIPTOR_COUNT = 155
EXPECTED_UNIT_DESCRIPTOR_COUNT = 7
EXPECTED_TOKEN_DESCRIPTOR_COUNT = 16
RUNTIME_REBASE = 0x00204000

SOURCE_GENERAL_TARGET_START = 0x0010E920
SOURCE_GENERAL_TARGET_END = 0x00111520
TARGET_GENERAL_TARGET_START = SOURCE_GENERAL_TARGET_START + RUNTIME_REBASE
TARGET_GENERAL_TARGET_END = SOURCE_GENERAL_TARGET_END + RUNTIME_REBASE
SOURCE_EXPECTED_START = 0x000E0000
SOURCE_EXPECTED_END = 0x00125190
TARGET_EXPECTED_START = SOURCE_EXPECTED_START + RUNTIME_REBASE
TARGET_EXPECTED_END = SOURCE_EXPECTED_END + RUNTIME_REBASE
UNIT_TARGET_START = 0x0031271C
UNIT_TARGET_END = 0x00312824

FOLLOWERS_SOURCE_TARGET = 0x0010EC64
FOLLOWERS_SOURCE_EXPECTED = 0x000F5A89
FOLLOWERS_TARGET = FOLLOWERS_SOURCE_TARGET + RUNTIME_REBASE
FOLLOWERS_EXPECTED = FOLLOWERS_SOURCE_EXPECTED + RUNTIME_REBASE
FOLLOWERS_INDEX = 146
FOLLOWERS_BEFORE = (
    "{추종자}\n\n더 큰 영광을 바라는 %s 무리가 당신의 군대에 합류하려 합니다. "
    "받아들이시겠습니까?"
)
FOLLOWERS_AFTER = (
    "{추종자}\n\n%s 중 일부가 더 큰 영광을 바라며 군대에 합류하려 합니다. "
    "받아들이시겠습니까?"
)

MAPPING_ROW = re.compile(
    r"^index 0x([0-9A-Fa-f]+) escape ([0-9A-Fa-f]{2}) ([0-9A-Fa-f]{2}) "
    r"= U\+([0-9A-Fa-f]{4,6}) (.)$"
)


class BankHotfixError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BankHotfixError(message)


def identity(raw: bytes) -> tuple[int, str]:
    return len(raw), hashlib.sha256(raw).hexdigest().upper()


def load_mapping(raw: bytes) -> dict[str, bytes]:
    require(identity(raw) == MAPPING_IDENTITY, "font mapping does not match the pinned 874-row mapping")
    mapping: dict[str, bytes] = {}
    escapes: set[bytes] = set()
    for line in raw.decode("utf-8-sig").splitlines():
        match = MAPPING_ROW.fullmatch(line)
        if match is None:
            continue
        index, lead, trail, codepoint, character = match.groups()
        require(int(index, 16) == 0x100 + len(mapping), "font mapping indices are not contiguous")
        require(ord(character) == int(codepoint, 16), "font mapping Unicode label mismatch")
        require(character not in mapping, f"font mapping character is duplicated: {character}")
        escape = bytes((int(lead, 16), int(trail, 16)))
        require(escape not in escapes, f"font mapping escape is duplicated: {escape.hex(' ').upper()}")
        mapping[character] = escape
        escapes.add(escape)
    require(len(mapping) == 874, "font mapping row count changed")
    require(len(escapes) == 874, "font mapping escape count changed")
    return mapping


def encode_text(text: str, mapping: dict[str, bytes]) -> bytes:
    output = bytearray()
    for character in text:
        if ord(character) < 0x80:
            require(character != "\0", "text contains NUL")
            output.append(ord(character))
        else:
            require(character in mapping, f"unmapped character: U+{ord(character):04X} {character}")
            output.extend(mapping[character])
    return bytes(output)


def direct_target_allowed(target: int, *, rebased: bool = False) -> bool:
    general_start = TARGET_GENERAL_TARGET_START if rebased else SOURCE_GENERAL_TARGET_START
    general_end = TARGET_GENERAL_TARGET_END if rebased else SOURCE_GENERAL_TARGET_END
    return (
        target & 3 == 0
        and (
            general_start <= target < general_end
            or UNIT_TARGET_START <= target < UNIT_TARGET_END
        )
    )


def expected_pointer_allowed(value: int, *, rebased: bool = False) -> bool:
    start = TARGET_EXPECTED_START if rebased else SOURCE_EXPECTED_START
    end = TARGET_EXPECTED_END if rebased else SOURCE_EXPECTED_END
    return start <= value < end


def validate_followers_format(text: str) -> None:
    require(text.count("%s") == 1, "Followers template must contain exactly one %s")
    require("%" not in text.replace("%s", ""), "Followers template contains another format token")


def parsed_bank(
    raw: bytes,
    *,
    rebased: bool = False,
):
    require(len(raw) >= HEADER.size, "bank header is truncated")
    mapping_tag = HEADER.unpack_from(raw)[-2]
    require(mapping_tag == EXPECTED_MAPPING_TAG, "bank mapping tag changed")
    parsed = parse_bank(
        raw,
        expected_mapping_tag=EXPECTED_MAPPING_TAG,
        unit_start=SOURCE_GENERAL_TARGET_START,
        unit_end=TARGET_GENERAL_TARGET_END,
    )
    require(len(parsed.render_rows) == EXPECTED_RENDER_COUNT, "render row count changed")
    require(len(parsed.descriptors) == EXPECTED_DESCRIPTOR_COUNT, "descriptor count changed")
    require(
        all(
            token_allowed(row.target) or direct_target_allowed(row.target, rebased=rebased)
            for row in parsed.descriptors
        ),
        "descriptor target escaped the runtime allowlist",
    )
    return parsed


def rebuild(parsed, descriptors: list[tuple[int, int, bytes]]) -> bytes:
    output, rows, rebuilt_descriptors = serialize_bank(
        [(row.prefix, row.token) for row in parsed.render_rows],
        descriptors,
        mapping_tag=EXPECTED_MAPPING_TAG,
        unit_start=SOURCE_GENERAL_TARGET_START,
        unit_end=TARGET_GENERAL_TARGET_END,
    )
    require(
        [(row.prefix, row.token) for row in rows]
        == [(row.prefix, row.token) for row in parsed.render_rows],
        "render rows changed during rebuild",
    )
    return output


def transform(source: bytes, mapping_raw: bytes) -> bytes:
    require(identity(source) == SOURCE_IDENTITY, "input bank does not match the pinned beta.2 bank")
    mapping = load_mapping(mapping_raw)
    validate_followers_format(FOLLOWERS_BEFORE)
    validate_followers_format(FOLLOWERS_AFTER)
    before = encode_text(FOLLOWERS_BEFORE, mapping)
    after = encode_text(FOLLOWERS_AFTER, mapping)
    require((len(before), len(after)) == (90, 86), "Followers encoded lengths changed")

    parsed = parsed_bank(source)
    source_rows = [(row.target, row.expected, row.encoded) for row in parsed.descriptors]
    require(rebuild(parsed, source_rows) == source, "source bank is not a canonical serialization")

    general_rows = [row for row in parsed.descriptors if direct_target_allowed(row.target) and row.target < UNIT_TARGET_START]
    unit_rows = [row for row in parsed.descriptors if UNIT_TARGET_START <= row.target < UNIT_TARGET_END]
    token_rows = [row for row in parsed.descriptors if token_allowed(row.target)]
    require(len(general_rows) == EXPECTED_GENERAL_DESCRIPTOR_COUNT, "general descriptor count changed")
    require(len(unit_rows) == EXPECTED_UNIT_DESCRIPTOR_COUNT, "unit descriptor count changed")
    require(len(token_rows) == EXPECTED_TOKEN_DESCRIPTOR_COUNT, "token descriptor count changed")
    require(
        all(expected_pointer_allowed(row.expected) for row in general_rows),
        "general expected pointer escaped the preferred Object2 interval",
    )

    matches = [
        (index, row)
        for index, row in enumerate(parsed.descriptors)
        if row.target == FOLLOWERS_SOURCE_TARGET
    ]
    require(len(matches) == 1, "Followers descriptor is missing or duplicated")
    index, descriptor = matches[0]
    require(index == FOLLOWERS_INDEX, "Followers descriptor index changed")
    require(descriptor.expected == FOLLOWERS_SOURCE_EXPECTED, "Followers source expected pointer changed")
    require(descriptor.encoded == before, "Followers source payload changed")

    target_rows: list[tuple[int, int, bytes]] = []
    for current_index, row in enumerate(parsed.descriptors):
        encoded = after if current_index == FOLLOWERS_INDEX else row.encoded
        if SOURCE_GENERAL_TARGET_START <= row.target < SOURCE_GENERAL_TARGET_END:
            target_rows.append((row.target + RUNTIME_REBASE, row.expected + RUNTIME_REBASE, encoded))
        else:
            target_rows.append((row.target, row.expected, encoded))
    result = rebuild(parsed, target_rows)
    require(identity(result) == TARGET_IDENTITY, "generated bank hash does not match the target")

    verified = parsed_bank(result, rebased=True)
    for current_index, (old_row, new_row) in enumerate(zip(parsed.descriptors, verified.descriptors)):
        if SOURCE_GENERAL_TARGET_START <= old_row.target < SOURCE_GENERAL_TARGET_END:
            require(new_row.target == old_row.target + RUNTIME_REBASE, "general target rebase mismatch")
            require(new_row.expected == old_row.expected + RUNTIME_REBASE, "general expected rebase mismatch")
            require(expected_pointer_allowed(new_row.expected, rebased=True), "rebased expected pointer escaped Object2")
        else:
            require(
                (new_row.target, new_row.expected) == (old_row.target, old_row.expected),
                "unit or token descriptor coordinates changed",
            )
        expected_payload = after if current_index == FOLLOWERS_INDEX else old_row.encoded
        require(new_row.encoded == expected_payload, f"unexpected payload change at descriptor {current_index}")
    return result


def operation_description(mapping_raw: bytes) -> dict[str, Any]:
    mapping = load_mapping(mapping_raw)
    validate_followers_format(FOLLOWERS_BEFORE)
    validate_followers_format(FOLLOWERS_AFTER)
    before = encode_text(FOLLOWERS_BEFORE, mapping)
    after = encode_text(FOLLOWERS_AFTER, mapping)
    return {
        "key": "followers_dynamic_join_template",
        "descriptor_index": FOLLOWERS_INDEX,
        "source_target": f"0x{FOLLOWERS_SOURCE_TARGET:08X}",
        "source_expected": f"0x{FOLLOWERS_SOURCE_EXPECTED:08X}",
        "target": f"0x{FOLLOWERS_TARGET:08X}",
        "expected": f"0x{FOLLOWERS_EXPECTED:08X}",
        "before_text": FOLLOWERS_BEFORE,
        "after_text": FOLLOWERS_AFTER,
        "before_encoded_length": len(before),
        "after_encoded_length": len(after),
        "runtime_rebase": f"0x{RUNTIME_REBASE:08X}",
        "rebased_general_descriptor_count": EXPECTED_GENERAL_DESCRIPTOR_COUNT,
        "unchanged_unit_descriptor_count": EXPECTED_UNIT_DESCRIPTOR_COUNT,
        "unchanged_renderer_token_count": EXPECTED_TOKEN_DESCRIPTOR_COUNT,
    }


def apply(source_path: Path, mapping_path: Path, output_path: Path) -> dict[str, Any]:
    source = source_path.read_bytes()
    mapping_raw = mapping_path.read_bytes()
    result = transform(source, mapping_raw)
    require(not output_path.exists(), f"output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(result)
        stream.flush()
        os.fsync(stream.fileno())
    require(output_path.read_bytes() == result, "output readback mismatch")
    return {
        "status": "bank_hotfix_applied",
        "source": {"path": str(source_path), "size": SOURCE_IDENTITY[0], "sha256": SOURCE_IDENTITY[1]},
        "output": {"path": str(output_path), "size": TARGET_IDENTITY[0], "sha256": TARGET_IDENTITY[1]},
        "operation": operation_description(mapping_raw),
    }


def verify(path: Path, mapping_path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(identity(raw) == TARGET_IDENTITY, "bank does not match the Followers hotfix target")
    mapping_raw = mapping_path.read_bytes()
    mapping = load_mapping(mapping_raw)
    parsed = parsed_bank(raw, rebased=True)
    descriptor = parsed.descriptors[FOLLOWERS_INDEX]
    require(descriptor.target == FOLLOWERS_TARGET, "Followers target changed")
    require(descriptor.expected == FOLLOWERS_EXPECTED, "Followers expected pointer changed")
    require(descriptor.encoded == encode_text(FOLLOWERS_AFTER, mapping), "Followers target payload changed")
    return {
        "status": "bank_hotfix_verified",
        "path": str(path),
        "size": TARGET_IDENTITY[0],
        "sha256": TARGET_IDENTITY[1],
        "operation": operation_description(mapping_raw),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    apply_parser = subcommands.add_parser("apply", help="write a new bank from the pinned beta.2 bank")
    apply_parser.add_argument("--source", type=Path, required=True)
    apply_parser.add_argument("--mapping", type=Path, required=True)
    apply_parser.add_argument("--output", type=Path, required=True)

    verify_parser = subcommands.add_parser("verify", help="verify an existing hotfixed bank")
    verify_parser.add_argument("--bank", type=Path, required=True)
    verify_parser.add_argument("--mapping", type=Path, required=True)

    args = parser.parse_args()
    mapping_path = args.mapping.resolve(strict=True)
    if args.command == "apply":
        result = apply(
            args.source.resolve(strict=True),
            mapping_path,
            args.output.resolve(strict=False),
        )
    else:
        result = verify(args.bank.resolve(strict=True), mapping_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
