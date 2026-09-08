#!/usr/bin/env python3
"""Reproduce the approved painted menu from exact original ICN deltas.

Only BSDIFF40 deltas and identity metadata are stored in the repository.
The release builder absorbs these fixed, font-independent resources into
its existing AGG base deltas; the installer needs no additional assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import bsdiff4

try:
    from . import homm2_font as font
except ImportError:
    import homm2_font as font


DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "translations/interface/main_menu"
SCHEMA = "homm2-approved-main-menu-v1"
APPROVED_DATE = "2026-09-08"
CYCLING_INDICES = frozenset((*range(214, 222), *range(231, 236), *range(238, 242)))
ARCHIVE_RESOURCES = {
    "HEROES2.AGG": ("BTNSHNGL.ICN", "HEROES.ICN"),
    "HEROES2X.AGG": ("HEROES.ICN",),
}
# The identity pins refer to the user's approved v7 menu, after the four
# accidental cycling-color pixels were removed. They are independent of
# the selected text font and the other resources in an installed AGG.
RESOURCE_SPECS = (
    {
        "archive": "HEROES2.AGG", "resource": "BTNSHNGL.ICN",
        "delta_path": "heroes2-btnshngl.bsdiff",
        "source": {"size": 89_377, "sha256": "63EADA2F70756BC49CE256F9C3C1BA21330C564A23E345B53649E983F94A61C7"},
        "target": {"size": 96_428, "sha256": "4B4AC170B417149BB48B15FEFB6894051C6CD3E0AC1A6ADAF60C0235A126CD28"},
    },
    {
        "archive": "HEROES2.AGG", "resource": "HEROES.ICN",
        "delta_path": "heroes2-heroes.bsdiff",
        "source": {"size": 288_082, "sha256": "0F5F01D354E5E38CB646C0CBC08DBD7D0E1050505B21923EA53A8CBE87F26721"},
        "target": {"size": 310_580, "sha256": "9CE77CBEC2D830F795513B68805B9D21FB1391E2D5058F70DA2AD13E4159F0C4"},
    },
    {
        "archive": "HEROES2X.AGG", "resource": "HEROES.ICN",
        "delta_path": "heroes2x-heroes.bsdiff",
        "source": {"size": 287_946, "sha256": "98E2233F7108842C93513915324E2D91C2AC85AEEE4A16496DC2A9D253B41534"},
        "target": {"size": 310_580, "sha256": "E9301B5BD4EC879B09C26163255787D40D2596E55244FDE72040B27ED1998310"},
    },
)
# Original button offsets, dimensions and the reviewed editable face bounds.
# The high-score states 1 and 2 have a native extra row, which stays intact.
BUTTON_LAYOUTS = (
    (482, 176, 81, 113), (195, 180, 80, 77), (408, 107, 80, 75),
    (303, 137, 76, 43), (0, 425, 86, 44),
)
BUTTON_ROIS = ((8, 24, 64, 56), (7, 14, 66, 51), (7, 8, 70, 55), (0, 8, 75, 26), (12, 10, 67, 29))
BACKGROUND_ROIS = tuple(
    (layout[0] + roi[0], layout[1] + roi[1], roi[2], roi[3])
    for layout, roi in zip(BUTTON_LAYOUTS, BUTTON_ROIS)
)


class MainMenuError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MainMenuError(message)


def identity(raw: bytes) -> dict[str, int | str]:
    return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest().upper()}


def _sprite_metadata(sprite: font._DecodedSprite) -> tuple[int, int, int, int, int]:
    return sprite.offset_x, sprite.offset_y, sprite.width, sprite.height, sprite.animation


def validate_sprite_changes(
    original: font._DecodedSprite,
    candidate: font._DecodedSprite,
    rois: Sequence[tuple[int, int, int, int]],
    *,
    label: str,
    all_visible_pixels_static: bool = False,
) -> None:
    """Protect native geometry and require all newly written pixels to be static."""
    require(_sprite_metadata(original) == _sprite_metadata(candidate), f"sprite geometry changed: {label}")
    require(original.transform == candidate.transform, f"sprite transparency changed: {label}")
    for index, (before, after, transform) in enumerate(zip(original.pixels, candidate.pixels, candidate.transform)):
        if before != after:
            y, x = divmod(index, original.width)
            require(
                any(left <= x < left + width and top <= y < top + height for left, top, width, height in rois),
                f"pixel outside approved menu face changed: {label}:{x},{y}",
            )
        if transform == 0 and (all_visible_pixels_static or before != after):
            require(after not in CYCLING_INDICES, f"cycling palette index in menu: {label}:{index}:{after}")


def validate_resource(source: bytes, target: bytes, spec: Mapping[str, Any]) -> None:
    label = f"{spec['archive']}/{spec['resource']}"
    require(identity(source) == spec["source"], f"unsupported original menu resource: {label}")
    require(identity(target) == spec["target"], f"menu resource differs from approved artwork: {label}")
    before = font.parse_icn(source, label=f"{label}:original")
    after = font.parse_icn(target, label=f"{label}:approved")
    require(font.pack_icn(after.sprites) == target, f"ICN roundtrip changed: {label}")
    count = 20 if spec["resource"] == "BTNSHNGL.ICN" else 1
    require(len(before.sprites) == len(after.sprites) == count, f"unexpected menu sprite count: {label}")
    for index, (old_sprite, new_sprite) in enumerate(zip(before.sprites, after.sprites)):
        old = font._decode_sprite(old_sprite, label=f"{label}:original:{index}")
        new = font._decode_sprite(new_sprite, label=f"{label}:approved:{index}")
        if count == 20:
            group, state = divmod(index, 4)
            x, y, width, height = BUTTON_LAYOUTS[group]
            if group == 2 and state in (1, 2):
                height += 1
            require(_sprite_metadata(old) == (x, y, width, height, 0), f"unexpected native button layout: {label}:{index}")
            rois = (BUTTON_ROIS[group],)
        else:
            require(_sprite_metadata(old) == (0, 0, 640, 480, 0), f"unexpected native background layout: {label}")
            rois = BACKGROUND_ROIS
        validate_sprite_changes(old, new, rois, label=f"{label}:{index}", all_visible_pixels_static=count == 20)


def validate_background_sync(resources: Mapping[str, Mapping[str, bytes]]) -> None:
    buttons = font.parse_icn(resources["HEROES2.AGG"]["BTNSHNGL.ICN"], label="approved buttons")
    for archive_name in ARCHIVE_RESOURCES:
        background_icn = font.parse_icn(resources[archive_name]["HEROES.ICN"], label=f"{archive_name}:background")
        background = font._decode_sprite(background_icn.sprites[0], label=f"{archive_name}:background")
        for group in range(5):
            button = font._decode_sprite(buttons.sprites[group * 4], label=f"button:{group}")
            for index, (pixel, transform) in enumerate(zip(button.pixels, button.transform)):
                if transform != 0:
                    continue
                y, x = divmod(index, button.width)
                position = (y + button.offset_y) * background.width + x + button.offset_x
                require(background.pixels[position] == pixel, f"background/button state 0 mismatch: {archive_name}:{group}:{x},{y}")


def load_deltas(data_directory: Path = DATA_DIRECTORY) -> dict[tuple[str, str], bytes]:
    document = json.loads((data_directory / "identities.json").read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unsupported approved-menu manifest schema")
    require(document.get("approved_date") == APPROVED_DATE, "approved-menu date changed")
    records = document.get("resources")
    require(isinstance(records, list) and len(records) == len(RESOURCE_SPECS), "approved-menu resource list changed")
    result = {}
    for record, spec in zip(records, RESOURCE_SPECS):
        label = f"{spec['archive']}/{spec['resource']}"
        require(
            all(record.get(key) == spec[key] for key in ("archive", "resource", "source", "target")),
            f"approved-menu identity pin changed: {label}",
        )
        delta = record.get("delta", {})
        require(delta.get("path") == spec["delta_path"], f"unexpected menu delta path: {label}")
        raw = (data_directory / spec["delta_path"]).read_bytes()
        require(identity(raw) == {key: delta.get(key) for key in ("size", "sha256")}, f"menu delta checksum mismatch: {label}")
        require(raw.startswith(b"BSDIFF40"), f"invalid menu delta format: {label}")
        result[(spec["archive"], spec["resource"])] = raw
    return result


def reconstruct_resources(original_root: Path, data_directory: Path = DATA_DIRECTORY) -> dict[str, dict[str, bytes]]:
    """Read an exact GOG tree and reconstruct all approved menu resources in memory."""
    deltas = load_deltas(data_directory)
    archives = {
        name: font.parse_agg((original_root / "DATA" / name).read_bytes(), label=f"original:{name}")
        for name in ARCHIVE_RESOURCES
    }
    palette = archives["HEROES2.AGG"].get("KB.PAL").payload
    require((len(palette), identity(palette)["sha256"]) == font.FANCY_MAIN_MENU_PALETTE_IDENTITY, "unsupported original menu palette")
    resources: dict[str, dict[str, bytes]] = {name: {} for name in ARCHIVE_RESOURCES}
    for spec in RESOURCE_SPECS:
        key = spec["archive"], spec["resource"]
        source = archives[key[0]].get(key[1]).payload
        require(identity(source) == spec["source"], f"unsupported original menu resource: {key}")
        target = bsdiff4.patch(source, deltas[key])
        validate_resource(source, target, spec)
        resources[key[0]][key[1]] = target
    validate_background_sync(resources)
    return resources


def apply_to_archive(patched_raw: bytes, archive_name: str, resources: Mapping[str, Mapping[str, bytes]]) -> bytes:
    """Accept pristine or approved menu inputs, preserving every unrelated resource."""
    require(archive_name in ARCHIVE_RESOURCES, f"unsupported menu archive: {archive_name}")
    archive = font.parse_agg(patched_raw, label=f"menu-input:{archive_name}")
    replacements = {}
    expected_changes = set()
    for spec in RESOURCE_SPECS:
        if spec["archive"] != archive_name:
            continue
        resource_name = spec["resource"]
        current = archive.get(resource_name).payload
        require(identity(current) in (spec["source"], spec["target"]), f"unknown existing menu artwork: {archive_name}/{resource_name}")
        target = resources[archive_name][resource_name]
        require(identity(target) == spec["target"], f"unapproved replacement menu: {archive_name}/{resource_name}")
        replacements[resource_name] = target
        if current != target:
            expected_changes.add(resource_name)
    output = font.repack_agg(archive, replacements)
    changed = set(font.changed_agg_resources(patched_raw, output, label=f"approved-menu:{archive_name}"))
    require(changed == expected_changes, f"non-menu resource changed: {archive_name}")
    candidate = font.parse_agg(output, label=f"menu-output:{archive_name}")
    require(font.repack_agg(candidate, {}) == output, f"AGG roundtrip changed: {archive_name}")
    for before, after in zip(archive.entries, candidate.entries):
        require(
            (before.index, before.name, before.name_slot, before.hash_word) == (after.index, after.name, after.name_slot, after.hash_word),
            f"AGG entry metadata changed: {archive_name}/{before.name}",
        )
        if before.name.upper() not in replacements:
            require(before.payload == after.payload, f"unrelated AGG payload changed: {archive_name}/{before.name}")
    return output


def generate_deltas(original_root: Path, approved_root: Path, output_directory: Path) -> dict[str, Any]:
    """Generate only the three pinned deltas; never modify game inputs or overwrite output."""
    require(not output_directory.exists(), f"output directory already exists: {output_directory}")
    sources = {name: font.parse_agg((original_root / "DATA" / name).read_bytes(), label=f"source:{name}") for name in ARCHIVE_RESOURCES}
    targets = {name: font.parse_agg((approved_root / "DATA" / name).read_bytes(), label=f"approved:{name}") for name in ARCHIVE_RESOURCES}
    resources: dict[str, dict[str, bytes]] = {name: {} for name in ARCHIVE_RESOURCES}
    deltas = {}
    records = []
    for spec in RESOURCE_SPECS:
        source = sources[spec["archive"]].get(spec["resource"]).payload
        target = targets[spec["archive"]].get(spec["resource"]).payload
        validate_resource(source, target, spec)
        delta = bsdiff4.diff(source, target)
        require(bsdiff4.patch(source, delta) == target, f"delta roundtrip changed: {spec['delta_path']}")
        deltas[spec["delta_path"]] = delta
        resources[spec["archive"]][spec["resource"]] = target
        records.append({
            key: spec[key] for key in ("archive", "resource", "source", "target")
        } | {"delta": {"path": spec["delta_path"], **identity(delta)}})
    validate_background_sync(resources)
    document = {"schema": SCHEMA, "approved_date": APPROVED_DATE, "resources": records}
    output_directory.mkdir(parents=True)
    for name, raw in deltas.items():
        (output_directory / name).write_bytes(raw)
    (output_directory / "identities.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--original-root", required=True, type=Path)
    verify.add_argument("--data-dir", type=Path, default=DATA_DIRECTORY)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--original-root", required=True, type=Path)
    generate.add_argument("--approved-root", required=True, type=Path)
    generate.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        result = generate_deltas(args.original_root, args.approved_root, args.output_dir)
    else:
        resources = reconstruct_resources(args.original_root, args.data_dir)
        result = {name: {resource: identity(raw) for resource, raw in entries.items()} for name, entries in resources.items()}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
