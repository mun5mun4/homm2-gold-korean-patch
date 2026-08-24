#!/usr/bin/env python3
"""Apply or verify the cumulative v0.9.0-beta.3 hotfix against a pinned EXE.

This offline tool intentionally starts from the pre-beta.2 Korean-patch EXE
(5AE509...), replays the beta.2 text fixes, adds the startup loader and
spell-relocation fixes, and localizes the Followers fallback allocation. It
does not modify a game installation in place and does not launch Heroes II or
DOSBox.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SOURCE_IDENTITY = (
    1_523_420,
    "5AE509A2C44CD104D21B44F97EA6DE03BC853B0E04A8B54DBA858AFD1FE1134E",
)
TARGET_IDENTITY = (
    1_523_420,
    "52AE3BA15AE309327D698EDEE8844684F91B3BA056B9215854002265A9F6E3EF",
)
CHANGED_BYTE_COUNT = 141


class HotfixError(RuntimeError):
    pass


@dataclass(frozen=True)
class Patch:
    key: str
    offset: int
    before: bytes
    after: bytes
    before_text: str
    after_text: str


PATCHES = (
    Patch(
        key="hero_target_spell_template",
        offset=0x144189,
        before=bytes.fromhex(
            "25 73 3A 20 25 73 83 93 20 25 73 83 86 20 82 FA 82 A9 2E 00 00 00 00 00 00"
        ),
        after=bytes.fromhex(
            "25 73 3A 20 25 73 83 86 83 AF 20 25 73 20 82 FA 82 A9 2E 00 00 00 00 00 00"
        ),
        before_text="%s: %s을 %s에 시전.",
        after_text="%s: %s에게 %s 시전.",
    ),
    Patch(
        key="hero_target_spell_argument_order",
        offset=0xDAE29,
        before=bytes.fromhex("8D 95 0E 02 00 00 52 8B 88 24 F5 02 00 51"),
        after=bytes.fromhex("8B 88 24 F5 02 00 51 8D 95 0E 02 00 00 52"),
        before_text="hero / spell / target",
        after_text="hero / target / spell",
    ),
    Patch(
        key="hero_target_spell_relocation_source",
        offset=0x50FE7,
        before=b"\x56",
        after=b"\x4F",
        before_text="LE fixup source 0x0F56 (stale LEA displacement)",
        after_text="LE fixup source 0x0F4F (moved MOV displacement)",
    ),
    Patch(
        key="wrapped_renderer_hook_to_h2k3_resolver",
        offset=0xFDF4A,
        before=bytes.fromhex("E9 8D BE 03 00"),
        after=bytes.fromhex("E9 B2 5C 03 00"),
        before_text="wrapped renderer triggers H2K3 loading lazily",
        after_text="wrapped renderer enters the initialized H2K3 resolver",
    ),
    Patch(
        key="startup_main_call_to_h2k3_loader",
        offset=0x11AC74,
        before=bytes.fromhex("E8 FE 53 FC FF"),
        after=bytes.fromhex("E8 63 F1 01 00"),
        before_text="call game main directly",
        after_text="call H2K3 loader before game main",
    ),
    Patch(
        key="h2k3_loader_tail_to_game_main",
        offset=0x139EC7,
        before=bytes.fromhex("E9 35 9D FF FF"),
        after=bytes.fromhex("E9 AB 61 FA FF"),
        before_text="H2K3 loader continues into the renderer resolver",
        after_text="startup H2K3 loader continues into game main",
    ),
    Patch(
        key="h2k3_helper_first_range_start_unit",
        offset=0x133C8E,
        before=bytes.fromhex("20 E9 10 00"),
        after=bytes.fromhex("1C 27 31 00"),
        before_text="preferred Object2 general-pointer range start 0x0010E920",
        after_text="runtime unit-pointer range start 0x0031271C",
    ),
    Patch(
        key="h2k3_helper_first_range_end_unit",
        offset=0x133C95,
        before=bytes.fromhex("20 15 11 00"),
        after=bytes.fromhex("24 28 31 00"),
        before_text="preferred Object2 general-pointer range end 0x00111520",
        after_text="runtime unit-pointer range end 0x00312824",
    ),
    Patch(
        key="h2k3_helper_second_range_start_general",
        offset=0x133C9C,
        before=bytes.fromhex("1C 27 31 00"),
        after=bytes.fromhex("20 29 31 00"),
        before_text="runtime unit-pointer range start 0x0031271C",
        after_text="relocated Object2 general-pointer range start 0x00312920",
    ),
    Patch(
        key="h2k3_helper_second_range_end_general",
        offset=0x133CA3,
        before=bytes.fromhex("24 28 31 00"),
        after=bytes.fromhex("20 55 31 00"),
        before_text="runtime unit-pointer range end 0x00312824",
        after_text="relocated Object2 general-pointer range end 0x00315520",
    ),
    Patch(
        key="air_elementals_direct_fallback",
        offset=0x14E0BB,
        before=b"air elementals\0",
        after=bytes.fromhex("82 EE 82 A6 82 A3 82 8D 00 00 00 00 00 00 00"),
        before_text="air elementals",
        after_text="공기정령",
    ),
    Patch(
        key="followers_direct_fallback",
        offset=0x14F965,
        before=(
            b"{Followers}\n\nA group of %s with a desire for greater glory wish "
            b"to join you. Do you accept? \0"
        ),
        after=bytes.fromhex(
            "7B 83 E4 84 E6 82 FB 7D 0A 0A 25 73 20 83 A1 20 82 C7 83 84 "
            "82 C6 20 83 87 20 85 E9 20 82 8F 85 86 83 93 20 83 E6 82 CF "
            "83 C8 20 82 B2 82 AF 83 86 20 83 95 83 B0 82 D3 84 CF 20 83 "
            "95 82 BF 83 8C 2E 20 85 8F 83 A8 82 9D 82 BD 82 FA 84 D9 83 "
            "9B 82 BF 84 DA 3F 00 00 00 00 00 00 00"
        ),
        before_text=(
            "{Followers} A group of %s with a desire for greater glory wish "
            "to join you. Do you accept?"
        ),
        after_text=(
            "{추종자} %s 중 일부가 더 큰 영광을 바라며 군대에 합류하려 합니다. "
            "받아들이시겠습니까?"
        ),
    ),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HotfixError(message)


def identity(raw: bytes) -> tuple[int, str]:
    return len(raw), hashlib.sha256(raw).hexdigest().upper()


def patch_description(patch: Patch) -> dict[str, Any]:
    return {
        "key": patch.key,
        "offset": f"0x{patch.offset:X}",
        "allocation": len(patch.before),
        "before_text": patch.before_text,
        "after_text": patch.after_text,
        "before_sha256": hashlib.sha256(patch.before).hexdigest().upper(),
        "after_sha256": hashlib.sha256(patch.after).hexdigest().upper(),
    }


def transform(source: bytes) -> bytes:
    require(identity(source) == SOURCE_IDENTITY, "input EXE does not match the pinned pre-hotfix build")
    output = bytearray(source)
    ranges: list[tuple[int, int]] = []

    for patch in PATCHES:
        require(len(patch.before) == len(patch.after), f"allocation changed: {patch.key}")
        start = patch.offset
        end = start + len(patch.before)
        require(source[start:end] == patch.before, f"source slice changed: {patch.key}")
        output[start:end] = patch.after
        ranges.append((start, end))

    ranges.sort()
    for left, right in zip(ranges, ranges[1:]):
        require(left[1] <= right[0], "patch ranges overlap")

    result = bytes(output)
    require(identity(result) == TARGET_IDENTITY, "generated EXE hash does not match the v0.9.0-beta.3 target")
    changed = [index for index, pair in enumerate(zip(source, result)) if pair[0] != pair[1]]
    require(len(changed) == CHANGED_BYTE_COUNT, "unexpected changed-byte count")
    require(
        all(any(start <= index < end for start, end in ranges) for index in changed),
        "a changed byte escaped the patch allowlist",
    )
    return result


def apply(source_path: Path, output_path: Path) -> dict[str, Any]:
    source = source_path.read_bytes()
    result = transform(source)
    require(not output_path.exists(), f"output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as stream:
        stream.write(result)
        stream.flush()
        os.fsync(stream.fileno())
    require(output_path.read_bytes() == result, "output readback mismatch")
    return {
        "status": "hotfix_applied",
        "source": {"path": str(source_path), "size": SOURCE_IDENTITY[0], "sha256": SOURCE_IDENTITY[1]},
        "output": {"path": str(output_path), "size": TARGET_IDENTITY[0], "sha256": TARGET_IDENTITY[1]},
        "changed_byte_count": CHANGED_BYTE_COUNT,
        "operations": [patch_description(patch) for patch in PATCHES],
    }


def verify(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(identity(raw) == TARGET_IDENTITY, "EXE does not match the v0.9.0-beta.3 target")
    for patch in PATCHES:
        start = patch.offset
        require(raw[start : start + len(patch.after)] == patch.after, f"target slice changed: {patch.key}")
    return {
        "status": "beta3_hotfix_verified",
        "path": str(path),
        "size": TARGET_IDENTITY[0],
        "sha256": TARGET_IDENTITY[1],
        "operation_count": len(PATCHES),
    }


def describe() -> dict[str, Any]:
    return {
        "source": {"size": SOURCE_IDENTITY[0], "sha256": SOURCE_IDENTITY[1]},
        "target": {"size": TARGET_IDENTITY[0], "sha256": TARGET_IDENTITY[1]},
        "changed_byte_count": CHANGED_BYTE_COUNT,
        "operations": [patch_description(patch) for patch in PATCHES],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    apply_parser = subcommands.add_parser("apply", help="write a v0.9.0-beta.3 EXE from the pinned pre-hotfix EXE")
    apply_parser.add_argument("--source", type=Path, required=True)
    apply_parser.add_argument("--output", type=Path, required=True)

    verify_parser = subcommands.add_parser("verify", help="verify an existing v0.9.0-beta.3 EXE")
    verify_parser.add_argument("--exe", type=Path, required=True)

    subcommands.add_parser("describe", help="print the exact patch contract")

    args = parser.parse_args()
    if args.command == "apply":
        result = apply(args.source.resolve(strict=True), args.output.resolve(strict=False))
    elif args.command == "verify":
        result = verify(args.exe.resolve(strict=True))
    else:
        result = describe()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
