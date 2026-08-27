#!/usr/bin/env python3
"""Build a binary-delta release without redistributing original game files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import bsdiff4

try:
    from . import homm2_font
except ImportError:
    import homm2_font


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
ASSETS = REPOSITORY / "packaging" / "release_assets"
PATCHER_SOURCE = HERE / "homm2_ko_patcher.py"
FONT_BUILDER_SOURCE = HERE / "homm2_font.py"
BASELINE_SOURCE = HERE / "gog_original_file_hashes.json"
MAPPING_SOURCE = REPOSITORY / "translations" / "font" / "mapping874.fixed-interface-font.txt"
DEFAULT_FONT_SOURCE = ASSETS / "fonts" / "NanumGothicCoding-Regular.ttf"
MAPPING_PACKAGE_PATH = Path("fonts/mapping874.fixed-interface-font.txt")
DEFAULT_FONT_PACKAGE_PATH = Path("fonts/NanumGothicCoding-Regular.ttf")
DEFAULT_FONT_LICENSE_PATH = Path("THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt")
CURRENT_VERSION = "v0.9.0-beta.8"
PINNED_BETA8_TARGETS = {
    Path("HEROES2.EXE"): {
        "size": 1_523_420,
        "sha256": "B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C",
    },
    Path("KOREAN.BIN"): {
        "size": 36_265,
        "sha256": "95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A",
    },
}
UPGRADE_RELEASES = (
    {
        "version": "v0.9.0-beta.4",
        "manifest_path": Path("upgrades/v0.9.0-beta.4-manifest.json"),
        "manifest": {
            "size": 31_988,
            "sha256": "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60",
        },
    },
    {
        "version": "v0.9.0-beta.5",
        "manifest_path": Path("upgrades/v0.9.0-beta.5-manifest.json"),
        "manifest": {
            "size": 32_845,
            "sha256": "A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F",
        },
    },
    {
        "version": "v0.9.0-beta.6",
        "manifest_path": Path("upgrades/v0.9.0-beta.6-manifest.json"),
        "manifest": {
            "size": 33_107,
            "sha256": "32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C",
        },
    },
    {
        "version": "v0.9.0-beta.7",
        "manifest_path": Path("upgrades/v0.9.0-beta.7-manifest.json"),
        "manifest": {
            "size": 33_369,
            "sha256": "F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE",
        },
    },
)
GAME_ID = "1207658785"
BUILD_ID = "52745329670822422"

FONT_AGG_PATHS = (Path("DATA/HEROES2.AGG"), Path("DATA/HEROES2X.AGG"))
HEROWIND_RESOURCE_NAME = "HEROWIND.BIN"
HEROWIND_LENGTH_OFFSET = 303
HEROWIND_TEXT_OFFSET = 305
HEROWIND_TEXT_SIZE = 10
HEROWIND_KNOWLEDGE_ENGLISH = b"Knowledge\0"
HEROWIND_KNOWLEDGE_KOREAN = b"\x82\xD8\x82\x95" + b"\0" * 6
HEROES2_LOCALIZED_BIN_RESOURCES = (
    HEROWIND_RESOURCE_NAME,
    "THIEFWIN.BIN",
    "WELLWIND.BIN",
    "RECRUIT0.BIN",
    "RECRUIT1.BIN",
    "RECRUIQ0.BIN",
    "RECRUIQ1.BIN",
    "TRADPOST.BIN",
)
# Every resource in these two tuples is rebuilt from the selected font during
# installation.  Keep the archive ownership explicit: if a new font-dependent
# localizer is added to homm2_font.py, validate_dynamic_font_agg_contracts()
# rejects the release build until this allowlist is deliberately updated.
HEROES2_DYNAMIC_FONT_RESOURCES = (
    "FONT.ICN",
    "SMALFONT.ICN",
    "REQUEST.ICN",
    "REQUESTS.ICN",
    "SYSTEM.ICN",
    "SYSTEME.ICN",
    "TREASURY.ICN",
    "WELLXTRA.ICN",
    "WELLBKG.ICN",
    "RECRUIT.ICN",
    "TRADPOST.ICN",
    "BTNCMPGN.ICN",
    "BTNCOM.ICN",
    "BTNHOTST.ICN",
    "BTNMODEM.ICN",
    "BTNMP.ICN",
    "BTNNET.ICN",
    "BTNNEWGM.ICN",
    "BTNNET2.ICN",
    "BTNMCFG.ICN",
    "BTNBAUD.ICN",
    "BTNDC.ICN",
    "BTNDCCFG.ICN",
    "CAMPXTRG.ICN",
    "CAMPXTRE.ICN",
    "SPANBTN.ICN",
    "SPANBTNE.ICN",
    "CSPANBTN.ICN",
    "CSPANBTE.ICN",
    "ESPANBTN.ICN",
    "SWAPBTN.ICN",
    "TRADPOSE.ICN",
    "VIEWARMY.ICN",
    "VIEWARME.ICN",
    "SURRENDR.ICN",
    "SURRENDE.ICN",
    "OVERVIEW.ICN",
    "APANEL.ICN",
    "APANELE.ICN",
    "CPANEL.ICN",
    "CPANELE.ICN",
    "WINCMBTB.ICN",
    "WINCMBBE.ICN",
    "NGEXTRA.ICN",
    "SPANBKG.ICN",
    "SPANBKGE.ICN",
    "CSPANBKG.ICN",
    "CSPANBKE.ICN",
    "ESPANBKG.ICN",
    "REQBKG.ICN",
    "REQSBKG.ICN",
    "RECR2BKG.ICN",
    "APANBKG.ICN",
    "APANBKGE.ICN",
    "CPANBKG.ICN",
    "CPANBKGE.ICN",
    "NGSPBKG.ICN",
    "NGHSBKG.ICN",
    "NGMPBKG.ICN",
    "SWAPWIN.ICN",
    "SCENIBKG.ICN",
    "WINLOSE.ICN",
    "WINLOSEE.ICN",
    "CASLWIND.ICN",
    "RECRBKG.ICN",
    "TOWNWIND.ICN",
    "TEXTBAR.ICN",
)
HEROES2X_DYNAMIC_FONT_RESOURCES = (
    "FONT.ICN",
    "SMALFONT.ICN",
    "X_CMPBTN.ICN",
    "X_NEWCMP.ICN",
    "X_LOADCM.ICN",
    "X_MAPMNU.ICN",
)
HEROES2_EXPECTED_PATCHED_RESOURCES = (
    *HEROES2_DYNAMIC_FONT_RESOURCES,
    *HEROES2_LOCALIZED_BIN_RESOURCES,
)
HEROES2X_EXPECTED_PATCHED_RESOURCES = HEROES2X_DYNAMIC_FONT_RESOURCES

# These image resources intentionally remain byte-exact originals.  They are
# named here as a release-policy guard even though the exact changed-resource
# allowlists above would also reject them.
ORIGINAL_MENU_AND_CAMPAIGN_BACKGROUND_RESOURCES = (
    "BTNSHNGL.ICN",
    "HEROES.ICN",
    "CAMPBKGG.ICN",
    "CAMPBKGE.ICN",
    "X_CMPBKG.ICN",
)


class BuildError(RuntimeError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise BuildError(message)


def digest(raw: bytes) -> dict[str, int | str]:
    return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest().upper()}


def source_digest(raw: bytes) -> dict[str, int | str]:
    result = digest(raw)
    result["md5"] = hashlib.md5(raw).hexdigest().upper()
    return result


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_baseline() -> tuple[list[Path], dict[str, dict[str, Any]]]:
    require(BASELINE_SOURCE.is_file(), f"source baseline missing: {BASELINE_SOURCE}")
    value = json.loads(BASELINE_SOURCE.read_text(encoding="utf-8"))
    require(value.get("schema") == "homm2-gog-source-baseline-v1", "source baseline schema mismatch")
    game = value.get("game", {})
    require(game.get("game_id") == GAME_ID and game.get("build_id") == BUILD_ID, "source baseline game mismatch")
    rows = value.get("files")
    require(isinstance(rows, list) and len(rows) == 50, "source baseline must contain exactly 50 files")
    paths = [Path(row["path"]) for row in rows]
    normalized = [path.as_posix().casefold() for path in paths]
    require(len(normalized) == len(set(normalized)), "source baseline paths are duplicated")
    require(paths[:3] == [Path("HEROES2.EXE"), Path("DATA/HEROES2.AGG"), Path("DATA/HEROES2X.AGG")], "core source baseline paths changed")
    campaign = paths[3:]
    require(len(campaign) == 47 and all(path.parent == Path("MAPS") and path.suffix.upper() in {".H2C", ".HXC"} for path in campaign), "campaign source allowlist changed")
    return paths, {row["path"].casefold(): row["source"] for row in rows}


def checked_file(root: Path, relative: Path, label: str) -> Path:
    root_resolved = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise BuildError(f"{label} path escaped its root: {relative}") from exc
    require(path.is_file(), f"{label} file missing: {relative}")
    return path


def write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, f"write readback mismatch: {path}")


def _target_resource_names(targets: Any, *, field: str = "resource") -> set[str]:
    return {str(target[field]).upper() for target in targets}


def _validate_localizer_resource_group(
    label: str,
    source_identities: Any,
    output_identities: Any,
    target_resources: set[str],
) -> set[str]:
    source = {str(name).upper() for name in source_identities}
    output = {str(name).upper() for name in output_identities}
    require(
        source == output == target_resources,
        f"{label} source/output/target resource declarations drifted: "
        f"source={sorted(source)} output={sorted(output)} targets={sorted(target_resources)}",
    )
    return source


def validate_dynamic_font_agg_contracts() -> None:
    """Cross-check explicit release allowlists against every live localizer.

    This deliberately does not derive the release allowlists from the font
    builder.  An added or moved localizer therefore fails closed until archive
    ownership is reviewed here.
    """

    font_resources = {str(name).upper() for name in homm2_font.FONT_RESOURCE_NAMES}
    require(
        font_resources == {"FONT.ICN", "SMALFONT.ICN"},
        f"font resource declaration drifted: {sorted(font_resources)}",
    )

    image_ui = _validate_localizer_resource_group(
        "image UI",
        homm2_font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.IMAGE_UI_TEXT_TARGETS)
        | {str(homm2_font.IMAGE_UI_WELL_MIRROR["target_resource"]).upper()},
    )
    menu132 = _validate_localizer_resource_group(
        "132-pixel menu",
        homm2_font.MENU132_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.MENU132_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.MENU132_TEXT_TARGETS),
    )
    campaign_buttons = _validate_localizer_resource_group(
        "campaign buttons",
        homm2_font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.CAMPAIGN_BUTTON_TEXT_TARGETS),
    )
    game_buttons = _validate_localizer_resource_group(
        "in-game buttons",
        homm2_font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.GAME_BUTTON_TEXT_TARGETS),
    )
    expansion_menu = _validate_localizer_resource_group(
        "expansion menu",
        homm2_font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.EXPANSION_MENU_TEXT_TARGETS),
    )
    embedded_ui = _validate_localizer_resource_group(
        "embedded UI",
        homm2_font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES,
        homm2_font.EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES,
        _target_resource_names(homm2_font.EMBEDDED_UI_MIRRORS, field="target_resource")
        | _target_resource_names(homm2_font.EMBEDDED_UI_TEXT_TARGETS),
    )

    heroes2_campaign_buttons = {"CAMPXTRG.ICN", "CAMPXTRE.ICN"}
    heroes2x_campaign_buttons = {"X_CMPBTN.ICN"}
    campaign_archive_sets = {
        frozenset(str(name).upper() for name in names)
        for names in homm2_font.CAMPAIGN_BUTTON_ARCHIVE_RESOURCE_SETS
    }
    require(
        campaign_buttons == heroes2_campaign_buttons | heroes2x_campaign_buttons
        and campaign_archive_sets
        == {frozenset(heroes2_campaign_buttons), frozenset(heroes2x_campaign_buttons)},
        f"campaign button archive ownership drifted: {sorted(campaign_buttons)}",
    )

    recruit_cost = {str(homm2_font.RECRUIT_COST_RESOURCE_NAME).upper()}
    townwind = {str(homm2_font.TOWNWIND_RESOURCE_NAME).upper()}
    textbar = {str(homm2_font.TEXTBAR_RESOURCE_NAME).upper()}
    require(
        _target_resource_names(homm2_font.TOWNWIND_COST_TARGETS)
        | _target_resource_names(homm2_font.TOWNWIND_BUTTON_TARGETS)
        == townwind,
        "TOWNWIND target declaration drifted",
    )
    require(
        _target_resource_names(homm2_font.TEXTBAR_TARGETS) == textbar,
        "TEXTBAR target declaration drifted",
    )

    heroes2_groups = (
        font_resources,
        image_ui,
        menu132,
        heroes2_campaign_buttons,
        game_buttons,
        embedded_ui,
        recruit_cost,
        townwind,
        textbar,
    )
    heroes2x_groups = (font_resources, heroes2x_campaign_buttons, expansion_menu)
    heroes2_declared = set().union(*heroes2_groups)
    heroes2x_declared = set().union(*heroes2x_groups)
    require(
        len(heroes2_declared) == sum(len(group) for group in heroes2_groups),
        "HEROES2 dynamic font resource groups overlap",
    )
    require(
        len(heroes2x_declared) == sum(len(group) for group in heroes2x_groups),
        "HEROES2X dynamic font resource groups overlap",
    )

    heroes2_explicit = {name.upper() for name in HEROES2_DYNAMIC_FONT_RESOURCES}
    heroes2x_explicit = {name.upper() for name in HEROES2X_DYNAMIC_FONT_RESOURCES}
    require(
        len(heroes2_explicit) == len(HEROES2_DYNAMIC_FONT_RESOURCES)
        and heroes2_explicit == heroes2_declared,
        f"HEROES2 dynamic font allowlist drifted: "
        f"missing={sorted(heroes2_declared - heroes2_explicit)} "
        f"extra={sorted(heroes2_explicit - heroes2_declared)}",
    )
    require(
        len(heroes2x_explicit) == len(HEROES2X_DYNAMIC_FONT_RESOURCES)
        and heroes2x_explicit == heroes2x_declared,
        f"HEROES2X dynamic font allowlist drifted: "
        f"missing={sorted(heroes2x_declared - heroes2x_explicit)} "
        f"extra={sorted(heroes2x_explicit - heroes2x_declared)}",
    )

    protected = {name.upper() for name in ORIGINAL_MENU_AND_CAMPAIGN_BACKGROUND_RESOURCES}
    declared_protected = {
        str(homm2_font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME).upper(),
        str(homm2_font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).upper(),
        *(str(name).upper() for name in homm2_font.CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES),
    }
    require(
        protected == declared_protected
        and not protected.intersection(heroes2_explicit | heroes2x_explicit),
        f"original menu/campaign-background policy drifted: {sorted(protected)}",
    )

    keep = {name.upper() for name in HEROES2_LOCALIZED_BIN_RESOURCES}
    heroes2_patched = {name.upper() for name in HEROES2_EXPECTED_PATCHED_RESOURCES}
    heroes2x_patched = {name.upper() for name in HEROES2X_EXPECTED_PATCHED_RESOURCES}
    require(not keep.intersection(heroes2_explicit), "HEROES2 BIN keep list overlaps dynamic raster resources")
    require(
        len(heroes2_patched) == len(HEROES2_EXPECTED_PATCHED_RESOURCES)
        and heroes2_patched == heroes2_explicit | keep,
        "HEROES2 patched-resource allowlist drifted",
    )
    require(
        len(heroes2x_patched) == len(HEROES2X_EXPECTED_PATCHED_RESOURCES)
        and heroes2x_patched == heroes2x_explicit,
        "HEROES2X patched-resource allowlist drifted",
    )


def font_agg_contract(relative: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    validate_dynamic_font_agg_contracts()
    if relative == Path("DATA/HEROES2.AGG"):
        return HEROES2_EXPECTED_PATCHED_RESOURCES, HEROES2_LOCALIZED_BIN_RESOURCES
    if relative == Path("DATA/HEROES2X.AGG"):
        return HEROES2X_EXPECTED_PATCHED_RESOURCES, ()
    raise BuildError(f"dynamic font AGG contract missing: {relative}")


def localize_herowind_knowledge_payload(payload: bytes, *, label: str) -> bytes:
    """Replace the fixed 10-byte Knowledge caption without touching its layout."""

    text_end = HEROWIND_TEXT_OFFSET + HEROWIND_TEXT_SIZE
    require(len(payload) >= text_end, f"HEROWIND.BIN payload is too short: {label}")
    require(
        payload[HEROWIND_LENGTH_OFFSET:HEROWIND_TEXT_OFFSET] == b"\x0A\x00",
        f"HEROWIND.BIN Knowledge allocation length changed: {label}",
    )
    current = payload[HEROWIND_TEXT_OFFSET:text_end]
    require(
        current in {HEROWIND_KNOWLEDGE_ENGLISH, HEROWIND_KNOWLEDGE_KOREAN},
        f"HEROWIND.BIN Knowledge allocation has unexpected bytes: {label}: {current.hex().upper()}",
    )
    if current == HEROWIND_KNOWLEDGE_KOREAN:
        return payload

    output = bytearray(payload)
    output[HEROWIND_TEXT_OFFSET:text_end] = HEROWIND_KNOWLEDGE_KOREAN
    result = bytes(output)
    require(len(result) == len(payload), f"HEROWIND.BIN payload size changed: {label}")
    require(
        result[:HEROWIND_TEXT_OFFSET] == payload[:HEROWIND_TEXT_OFFSET]
        and result[text_end:] == payload[text_end:],
        f"HEROWIND.BIN bytes outside the Knowledge allocation changed: {label}",
    )
    return result


def localize_herowind_knowledge_agg(raw: bytes, *, label: str) -> bytes:
    """Return an AGG whose only possible mutation is HEROWIND.BIN Knowledge."""

    archive = homm2_font.parse_agg(raw, label=f"{label}:before")
    resource = archive.get(HEROWIND_RESOURCE_NAME)
    localized = localize_herowind_knowledge_payload(resource.payload, label=f"{label}:{HEROWIND_RESOURCE_NAME}")
    if localized == resource.payload:
        return raw

    result = homm2_font.repack_agg(archive, {resource.name: localized})
    require(len(result) == len(raw), f"AGG size changed while localizing HEROWIND.BIN: {label}")
    changes = {name.upper() for name in homm2_font.changed_agg_resources(raw, result, label=f"{label}:hotfix")}
    require(
        changes == {HEROWIND_RESOURCE_NAME},
        f"HEROWIND.BIN hotfix changed unexpected AGG resources: {label}: {sorted(changes)}",
    )
    return result


def font_generation_manifest(mapping_raw: bytes, default_font_raw: bytes) -> dict[str, Any]:
    return {
        "schema": "homm2-font-generation-v1",
        "mapping": {
            "package_path": MAPPING_PACKAGE_PATH.as_posix(),
            "package": digest(mapping_raw),
        },
        "default_font": {
            "name": "NanumGothicCoding Regular",
            "package_path": DEFAULT_FONT_PACKAGE_PATH.as_posix(),
            "package": digest(default_font_raw),
            "face_index": 0,
            "license_path": DEFAULT_FONT_LICENSE_PATH.as_posix(),
        },
        "renderer": {
            "id": homm2_font.RENDERER_ID,
            "normal_pixel_size": homm2_font.NORMAL_PIXEL_SIZE,
            "small_pixel_size": homm2_font.SMALL_PIXEL_SIZE,
            "normal_cell": {
                "width": homm2_font.NORMAL_CELL_WIDTH,
                "height": homm2_font.NORMAL_CELL_HEIGHT,
            },
            "small_cell": {
                "width": homm2_font.SMALL_CELL_WIDTH,
                "height": homm2_font.SMALL_CELL_HEIGHT,
            },
            "shadow_offset": [homm2_font.SHADOW_OFFSET_X, homm2_font.SHADOW_OFFSET_Y],
            "baseline_policy": homm2_font.BASELINE_POLICY,
            "fit_policy": homm2_font.FIT_POLICY,
            "crop_policy": homm2_font.CROP_POLICY,
            "shadow_policy": homm2_font.SHADOW_POLICY,
            "foreground_palette_index": homm2_font.FOREGROUND_PALETTE_INDEX,
            "shadow_palette_index": homm2_font.SHADOW_PALETTE_INDEX,
        },
        "layout": {
            "legacy_sprite_count": homm2_font.LEGACY_SPRITE_COUNT,
            "filler_sprite_count": homm2_font.FILLER_SPRITE_COUNT,
            "first_index": homm2_font.KOREAN_FIRST_INDEX,
            "last_index": homm2_font.KOREAN_LAST_INDEX,
            "glyph_count": homm2_font.KOREAN_GLYPH_COUNT,
            "final_sprite_count": homm2_font.FINAL_SPRITE_COUNT,
            "blank_legacy_sprite_index": homm2_font.AT_SIGN_SPRITE_INDEX,
        },
    }


def build(original: Path, patched: Path, output: Path, version: str, patcher_exe: Path | None) -> dict[str, Any]:
    require(version == CURRENT_VERSION, f"release builder is pinned to {CURRENT_VERSION}")
    validate_dynamic_font_agg_contracts()
    require(original.is_dir(), f"original root missing: {original}")
    require(patched.is_dir(), f"patched root missing: {patched}")
    require(not output.exists(), f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    asset_names = (
        "README_KO.md",
        "INSTALL_KO.md",
        "CHANGELOG.md",
        "NOTICE.md",
        "THIRD_PARTY_NOTICES.md",
        "COPYING.GPL-2.0",
        "INSTALL.cmd",
        "INSTALL_CUSTOM_FONT.cmd",
        "VERIFY.cmd",
        "UNINSTALL.cmd",
        "RECOVER.cmd",
    )
    for asset in asset_names:
        require((ASSETS / asset).is_file(), f"release asset missing: {asset}")
    third_party_license_names = (
        "BSDIFF4_LICENSE.txt",
        "NANUM_GOTHIC_CODING_OFL.txt",
        "PILLOW_LICENSE.txt",
        "PYINSTALLER_COPYING.txt",
        "PYTHON_LICENSE.txt",
    )
    for name in third_party_license_names:
        require((ASSETS / "THIRD_PARTY_LICENSES" / name).is_file(), f"third-party license missing: {name}")
    require(PATCHER_SOURCE.is_file(), "patcher source missing")
    require(FONT_BUILDER_SOURCE.is_file(), "font builder source missing")
    require(MAPPING_SOURCE.is_file(), "font mapping source missing")
    require(DEFAULT_FONT_SOURCE.is_file(), "default Nanum font source missing")
    for upgrade in UPGRADE_RELEASES:
        require(
            (ASSETS / upgrade["manifest_path"]).is_file(),
            f"previous release manifest missing: {upgrade['version']}",
        )
    if patcher_exe is not None:
        require(patcher_exe.is_file(), f"patcher executable missing: {patcher_exe}")

    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        rows: list[dict[str, Any]] = []
        paths, baseline = load_baseline()
        for index, relative in enumerate(paths, 1):
            source_path = checked_file(original, relative, "original")
            target_path = checked_file(patched, relative, "patched")
            source = source_path.read_bytes()
            target = target_path.read_bytes()
            require(source_digest(source) == baseline[relative.as_posix().casefold()], f"original baseline mismatch: {relative}")
            if relative in PINNED_BETA8_TARGETS:
                require(
                    digest(target) == PINNED_BETA8_TARGETS[relative],
                    f"pinned beta.8 target mismatch: {relative}",
                )
            if relative == Path("DATA/HEROES2.AGG"):
                target = localize_herowind_knowledge_agg(target, label=f"{relative.as_posix()}:patched")
            if relative in FONT_AGG_PATHS:
                expected_changes, keep_localized_resources = font_agg_contract(relative)
                actual_changes = homm2_font.changed_agg_resources(source, target, label=relative.as_posix())
                require(
                    {name.upper() for name in actual_changes} == {name.upper() for name in expected_changes},
                    f"patched AGG resource set mismatch: {relative}: {actual_changes}",
                )
                base = homm2_font.make_localized_font_base(
                    source,
                    target,
                    keep_localized_resources=keep_localized_resources,
                    expected_patched_changes=expected_changes,
                    label=relative.as_posix(),
                )
                base_changes = homm2_font.changed_agg_resources(source, base, label=f"{relative.as_posix()}:base")
                require(
                    {name.upper() for name in base_changes}
                    == {name.upper() for name in keep_localized_resources},
                    f"font-free AGG base resource set mismatch: {relative}: {base_changes}",
                )
                patch = bsdiff4.diff(source, base)
                method = "bsdiff40_font_agg_v1"
                target_identity: dict[str, int | str] | None = None
                base_target_identity: dict[str, int | str] | None = digest(base)
            else:
                patch = bsdiff4.diff(source, target)
                method = "bsdiff40"
                target_identity = digest(target)
                base_target_identity = None
            package_relative = Path("patches") / Path(str(relative) + ".bsdiff")
            write(stage / package_relative, patch)
            row: dict[str, Any] = {
                "path": relative.as_posix(),
                "method": method,
                "source": source_digest(source),
                "target": target_identity,
                "package_path": package_relative.as_posix(),
                "package": digest(patch),
            }
            if method == "bsdiff40_font_agg_v1":
                row["base_target"] = base_target_identity
                row["keep_localized_resources"] = list(keep_localized_resources)
            rows.append(row)
            print(f"[{index:02d}/{len(paths):02d}] {relative.as_posix()} method={method} patch={len(patch)}")

        bank = checked_file(patched, Path("KOREAN.BIN"), "patched").read_bytes()
        require(
            digest(bank) == PINNED_BETA8_TARGETS[Path("KOREAN.BIN")],
            "pinned beta.8 target mismatch: KOREAN.BIN",
        )
        bank_relative = Path("payload/KOREAN.BIN")
        write(stage / bank_relative, bank)
        rows.append(
            {
                "path": "KOREAN.BIN",
                "method": "copy",
                "source": None,
                "target": digest(bank),
                "package_path": bank_relative.as_posix(),
                "package": digest(bank),
            }
        )
        mapping_raw = MAPPING_SOURCE.read_bytes()
        default_font_raw = DEFAULT_FONT_SOURCE.read_bytes()
        write(stage / MAPPING_PACKAGE_PATH, mapping_raw)
        write(stage / DEFAULT_FONT_PACKAGE_PATH, default_font_raw)
        upgrade_descriptors: list[dict[str, Any]] = []
        for upgrade in UPGRADE_RELEASES:
            manifest_path = upgrade["manifest_path"]
            manifest_raw = (ASSETS / manifest_path).read_bytes()
            require(
                digest(manifest_raw) == upgrade["manifest"],
                f"frozen {upgrade['version']} manifest identity mismatch",
            )
            write(stage / manifest_path, manifest_raw)
            upgrade_descriptors.append(
                {
                    "version": upgrade["version"],
                    "manifest_path": manifest_path.as_posix(),
                    "manifest": dict(upgrade["manifest"]),
                }
            )

        manifest = {
            "schema": "homm2-korean-release-manifest-v2",
            "version": version,
            "release_date": "2026-08-27",
            "channel": "beta",
            "game": {
                "game_id": GAME_ID,
                "build_id": BUILD_ID,
                "language": "English",
                "edition": "Heroes of Might and Magic 2 Gold (GOG DOS)",
            },
            "installation": {
                "mode": "transactional root patch with cloud_saves shadow backup",
                "state_directory": "_homm2_ko_install",
                "ordinary_maps_modified": False,
                "save_files_modified": False,
                "image_assets_translated": True,
            },
            "counts": {
                "bsdiff_files": len(paths) - len(FONT_AGG_PATHS),
                "dynamic_font_agg_files": len(FONT_AGG_PATHS),
                "campaign_maps": 47,
                "copied_project_files": 1,
                "installed_files": len(rows),
            },
            "font_generation": font_generation_manifest(mapping_raw, default_font_raw),
            "upgrades": {
                "schema": "homm2-korean-upgrades-v1",
                "from": upgrade_descriptors,
            },
            "files": rows,
        }
        write(stage / "manifest.json", canonical(manifest))
        shutil.copy2(PATCHER_SOURCE, stage / "homm2_ko_patcher.py")
        shutil.copy2(FONT_BUILDER_SOURCE, stage / "homm2_font.py")
        if patcher_exe is not None:
            shutil.copy2(patcher_exe, stage / "homm2-ko-patcher.exe")
        for name in asset_names:
            shutil.copy2(ASSETS / name, stage / name)
        for name in third_party_license_names:
            destination = stage / "THIRD_PARTY_LICENSES" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ASSETS / "THIRD_PARTY_LICENSES" / name, destination)
        stage.replace(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {
        "status": "release_directory_built",
        "output": str(output),
        "version": version,
        "file_count": len(rows),
        "manifest": digest((output / "manifest.json").read_bytes()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--patched-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=CURRENT_VERSION)
    parser.add_argument("--patcher-exe", type=Path)
    args = parser.parse_args()
    result = build(
        args.original_root.resolve(),
        args.patched_root.resolve(),
        args.output.resolve(),
        args.version,
        args.patcher_exe.resolve() if args.patcher_exe else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
