#!/usr/bin/env python3
"""Transactional upgrade tests using only isolated, tiny fixtures."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.release import homm2_font
from tools.release import homm2_ko_patcher as patcher


PREVIOUS_VERSION = "v0.9.0-beta.4"
BETA5_VERSION = "v0.9.0-beta.5"
BETA6_VERSION = "v0.9.0-beta.6"
BETA7_VERSION = "v0.9.0-beta.7"
BETA8_VERSION = "v0.9.0-beta.8"
CURRENT_VERSION = "v0.9.0-beta.9"
PREVIOUS_SHA256 = "A" * 64
CURRENT_SHA256 = "B" * 64


def identity(raw: bytes) -> dict[str, int | str]:
    return {"size": len(raw), "sha256": patcher.sha256_bytes(raw)}


def font_face(raw: bytes, file_name: str = "Fixture.ttf") -> dict[str, int | str]:
    return {
        "file_name": file_name,
        "size": len(raw),
        "sha256": patcher.sha256_bytes(raw),
        "face_index": 0,
        "face_count": 1,
        "family": "Fixture",
        "subfamily": "Regular",
        "full_name": "Fixture Regular",
        "postscript_name": "Fixture-Regular",
    }


def renderer(*, legacy: bool, historical_v2: bool = False) -> dict[str, object]:
    if historical_v2:
        return copy.deepcopy(patcher.HISTORICAL_V2_RENDERER)
    if legacy:
        return {
            "id": "pillow-freetype-monochrome-v1",
            "normal_pixel_size": 14,
            "small_pixel_size": 12,
            "foreground_palette_index": 10,
            "shadow_palette_index": 21,
        }
    return {
        "id": homm2_font.RENDERER_ID,
        "normal_pixel_size": homm2_font.NORMAL_PIXEL_SIZE,
        "small_pixel_size": homm2_font.SMALL_PIXEL_SIZE,
        "normal_cell": {"width": homm2_font.NORMAL_CELL_WIDTH, "height": homm2_font.NORMAL_CELL_HEIGHT},
        "small_cell": {"width": homm2_font.SMALL_CELL_WIDTH, "height": homm2_font.SMALL_CELL_HEIGHT},
        "shadow_offset": [homm2_font.SHADOW_OFFSET_X, homm2_font.SHADOW_OFFSET_Y],
        "baseline_policy": homm2_font.BASELINE_POLICY,
        "fit_policy": homm2_font.FIT_POLICY,
        "crop_policy": homm2_font.CROP_POLICY,
        "shadow_policy": homm2_font.SHADOW_POLICY,
        "foreground_palette_index": homm2_font.FOREGROUND_PALETTE_INDEX,
        "shadow_palette_index": homm2_font.SHADOW_PALETTE_INDEX,
    }


def generation(
    default_font_raw: bytes,
    *,
    fallback_font_raw: bytes | None = None,
    legacy: bool,
    historical_v2: bool = False,
    frozen_legacy: bool = False,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "homm2-font-generation-v1" if frozen_legacy else "homm2-font-generation-v2",
        "mapping": {"package_path": "fonts/mapping.txt", "package": identity(b"mapping")},
        "default_font": {
            "name": "Legacy Nanum Fixture" if frozen_legacy else "Iropke Fixture",
            "package_path": "fonts/Legacy.ttf" if frozen_legacy else "fonts/Iropke.ttf",
            "package": identity(default_font_raw),
            "face_index": 0,
            "license_path": "licenses/FONT.txt",
        },
        "renderer": renderer(legacy=legacy, historical_v2=historical_v2),
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
    if not frozen_legacy:
        assert fallback_font_raw is not None
        value["fallback_font"] = {
            "name": "Nanum Fallback Fixture",
            "package_path": "fonts/Nanum.ttf",
            "package": identity(fallback_font_raw),
            "face_index": 0,
            "license_path": "licenses/FALLBACK_FONT.txt",
        }
    return value


def resolved_face(
    requested: int,
    width: int,
    height: int,
    glyph_count: int = homm2_font.KOREAN_GLYPH_COUNT,
    *,
    historical_v2: bool = False,
) -> dict[str, object]:
    ink_union = [0, -requested + 2, width - 1, 2]
    return {
        "requested_pixel_size": requested,
        "resolved_pixel_size": requested,
        "cell_width": width,
        "cell_height": height,
        "origin_x": width // 2,
        "baseline_y": height if historical_v2 else -ink_union[1],
        "ink_union": ink_union,
        "glyph_count": glyph_count,
        "foreground_clip_count": 0,
        "shadow_edge_clip_count": 0,
    }


def font_receipt(
    font_raw: bytes,
    *,
    legacy: bool,
    mode: str = "default",
    historical_v2: bool = False,
) -> dict[str, object]:
    selected_raw = font_raw if mode == "default" else b"custom-font"
    value: dict[str, object] = {
        "schema": "homm2-generated-font-receipt-v1",
        "mode": mode,
        "renderer": (
            "pillow-freetype-monochrome-v1"
            if legacy
            else patcher.HISTORICAL_V2_RENDERER["id"]
            if historical_v2
            else homm2_font.RENDERER_ID
        ),
        "normal_pixel_size": 14,
        "small_pixel_size": 12,
        "mapping_glyph_count": homm2_font.KOREAN_GLYPH_COUNT,
        "first_index": homm2_font.KOREAN_FIRST_INDEX,
        "last_index": homm2_font.KOREAN_LAST_INDEX,
        "blank_legacy_sprite_index": homm2_font.AT_SIGN_SPRITE_INDEX,
        "primary_glyph_count": homm2_font.KOREAN_GLYPH_COUNT,
        "fallback_glyph_count": 0,
        "primary": font_face(selected_raw, "Fixture.ttf" if mode == "default" else "Custom.ttf"),
        "fallback": None,
    }
    if not legacy:
        value.update(
            {
                "normal_cell": {"width": homm2_font.NORMAL_CELL_WIDTH, "height": homm2_font.NORMAL_CELL_HEIGHT},
                "small_cell": {"width": homm2_font.SMALL_CELL_WIDTH, "height": homm2_font.SMALL_CELL_HEIGHT},
                "shadow_offset": [homm2_font.SHADOW_OFFSET_X, homm2_font.SHADOW_OFFSET_Y],
                "baseline_policy": (
                    patcher.HISTORICAL_V2_RENDERER["baseline_policy"]
                    if historical_v2
                    else homm2_font.BASELINE_POLICY
                ),
                "fit_policy": (
                    patcher.HISTORICAL_V2_RENDERER["fit_policy"]
                    if historical_v2
                    else homm2_font.FIT_POLICY
                ),
                "crop_policy": (
                    patcher.HISTORICAL_V2_RENDERER["crop_policy"]
                    if historical_v2
                    else homm2_font.CROP_POLICY
                ),
                "shadow_policy": (
                    patcher.HISTORICAL_V2_RENDERER["shadow_policy"]
                    if historical_v2
                    else homm2_font.SHADOW_POLICY
                ),
                "resolved_faces": {
                    "primary": {
                        "normal": resolved_face(
                            homm2_font.NORMAL_PIXEL_SIZE,
                            homm2_font.NORMAL_CELL_WIDTH,
                            homm2_font.NORMAL_CELL_HEIGHT,
                            historical_v2=historical_v2,
                        ),
                        "small": resolved_face(
                            homm2_font.SMALL_PIXEL_SIZE,
                            homm2_font.SMALL_CELL_WIDTH,
                            homm2_font.SMALL_CELL_HEIGHT,
                            historical_v2=historical_v2,
                        ),
                    },
                    "fallback": None,
                },
            }
        )
    return value


class UpgradeFixture:
    original = b"pure-original"
    old_static = b"beta4-static"
    old_copy = b"beta4-copy"
    new_static = b"beta5-static"
    new_copy = b"beta5-copy"
    old_cloud = b"cloud-before-beta4"
    default_font = b"iropke-fixture-font"
    fallback_font = b"nanum-fixture-font"

    def __init__(
        self,
        root: Path,
        *,
        custom: bool = False,
        previous_version: str = PREVIOUS_VERSION,
        previous_legacy: bool = True,
    ) -> None:
        self.game = root / "game"
        self.package = root / "package"
        self.game.mkdir()
        self.package.mkdir()
        self.state = self.game / patcher.STATE_DIR_NAME
        self.state.mkdir()
        self.previous_run_id = "20260824T010203_1234abcd"
        self.previous_backup = self.state / "backups" / self.previous_run_id

        (self.game / "DATA").mkdir()
        (self.game / "DATA" / "A.BIN").write_bytes(self.old_static)
        (self.game / "KOREAN.BIN").write_bytes(self.old_copy)
        old_root_backup = self.previous_backup / "root" / "DATA" / "A.BIN"
        old_root_backup.parent.mkdir(parents=True)
        old_root_backup.write_bytes(self.original)
        old_cloud_backup = self.previous_backup / "cloud_saves" / "DATA" / "A.BIN"
        old_cloud_backup.parent.mkdir(parents=True)
        old_cloud_backup.write_bytes(self.old_cloud)

        previous_static = self.row("DATA/A.BIN", "bsdiff40", self.old_static)
        previous_copy = self.row("KOREAN.BIN", "copy", self.old_copy)
        current_static = self.row("DATA/A.BIN", "bsdiff40", self.new_static)
        current_copy = self.row("KOREAN.BIN", "copy", self.new_copy)
        previous_historical_v2 = not previous_legacy and previous_version in {
            BETA5_VERSION,
            BETA6_VERSION,
            BETA7_VERSION,
        }
        self.previous_manifest = self.manifest(
            previous_version,
            [previous_static, previous_copy],
            legacy=previous_legacy,
            historical_v2=previous_historical_v2,
            frozen_legacy=True,
        )
        self.current_manifest = self.manifest(CURRENT_VERSION, [current_static, current_copy], legacy=False)

        previous_font = font_receipt(
            self.fallback_font,
            legacy=previous_legacy,
            mode="custom" if custom else "default",
            historical_v2=previous_historical_v2,
        )
        records = [
            {
                "path": "DATA/A.BIN",
                "root_before": identity(self.original),
                "root_backup": str(old_root_backup),
                "cloud_before": identity(self.old_cloud),
                "cloud_backup": str(old_cloud_backup),
                "installed": identity(self.old_static),
                "committed": True,
            },
            {
                "path": "KOREAN.BIN",
                "root_before": None,
                "root_backup": str(self.previous_backup / "root" / "KOREAN.BIN"),
                "cloud_before": None,
                "cloud_backup": str(self.previous_backup / "cloud_saves" / "KOREAN.BIN"),
                "installed": identity(self.old_copy),
                "committed": True,
            },
        ]
        self.previous_receipt = {
            "schema": "homm2-korean-install-receipt-v1",
            "status": "installed",
            "version": previous_version,
            "run_id": self.previous_run_id,
            "manifest_sha256": PREVIOUS_SHA256,
            "font_generation": previous_font,
            "backup": str(self.previous_backup),
            "records": records,
        }
        (self.state / patcher.RECEIPT_NAME).write_bytes(patcher.canonical(self.previous_receipt))

    def row(self, path: str, method: str, target_raw: bytes) -> dict[str, object]:
        return {
            "path": path,
            "package_path": f"patches/{path}.patch",
            "method": method,
            "package": identity(b"package"),
            "source": None if method == "copy" else identity(self.original),
            "target": identity(target_raw),
        }

    def manifest(
        self,
        version: str,
        files: list[dict[str, object]],
        *,
        legacy: bool,
        historical_v2: bool = False,
        frozen_legacy: bool = False,
    ) -> dict[str, object]:
        return {
            "schema": "homm2-korean-release-manifest-v2",
            "version": version,
            "game": {"game_id": patcher.GAME_ID, "build_id": patcher.BUILD_ID, "language": "English"},
            "font_generation": generation(
                self.fallback_font if frozen_legacy else self.default_font,
                fallback_font_raw=None if frozen_legacy else self.fallback_font,
                legacy=legacy,
                historical_v2=historical_v2,
                frozen_legacy=frozen_legacy,
            ),
            "files": files,
        }

    def staged(self, package: Path, game: Path, manifest: dict, stage: Path, font_plan: object, source_paths=None):
        self.seen_source_paths = source_paths
        outputs = {"DATA/A.BIN": self.new_static, "KOREAN.BIN": self.new_copy}
        for relative, raw in outputs.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        return {path: identity(raw) for path, raw in outputs.items()}, font_receipt(self.default_font, legacy=False)


class PatcherUpgradeTests(unittest.TestCase):
    def patches(self, fixture: UpgradeFixture, stage_side_effect=None):
        return (
            mock.patch.object(patcher, "require_no_blockers"),
            mock.patch.object(patcher, "validate_game_info", return_value={}),
            mock.patch.object(
                patcher,
                "load_upgrade_manifest",
                return_value=(fixture.previous_manifest, PREVIOUS_SHA256),
            ),
            mock.patch.object(patcher, "prepare_font_plan", return_value=object()),
            mock.patch.object(patcher, "stage_outputs", side_effect=stage_side_effect or fixture.staged),
        )

    def test_upgrade_stages_from_first_original_and_new_uninstall_restores_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(fixture)
            with blockers, game_info, previous_manifest, font_plan, stage_outputs:
                result = patcher.install(
                    fixture.game,
                    fixture.package,
                    fixture.current_manifest,
                    CURRENT_SHA256,
                )
                self.assertEqual(result["version"], CURRENT_VERSION)
                self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.new_static)
                self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.new_copy)
                self.assertEqual(fixture.seen_source_paths["DATA/A.BIN"].read_bytes(), fixture.original)

                receipt = patcher.read_json(fixture.state / patcher.RECEIPT_NAME)
                self.assertEqual(receipt["upgraded_from"]["version"], PREVIOUS_VERSION)
                self.assertEqual(receipt["records"][0]["root_before"], identity(fixture.original))
                new_backup = patcher.backup_file_for(fixture.game, receipt["run_id"], "root", "DATA/A.BIN")
                self.assertEqual(new_backup.read_bytes(), fixture.original)

                removed = patcher.uninstall(
                    fixture.game,
                    fixture.current_manifest,
                    CURRENT_SHA256,
                    fixture.package,
                )
                self.assertEqual(removed["status"], "uninstalled_and_restored")
                self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.original)
                self.assertFalse((fixture.game / "KOREAN.BIN").exists())
                self.assertEqual((fixture.game / "cloud_saves" / "DATA" / "A.BIN").read_bytes(), fixture.old_cloud)

    def test_preflight_recognizes_custom_beta4_as_an_upgrade_source_and_selects_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary), custom=True)
            plan = mock.Mock()
            plan.metadata.return_value = font_receipt(fixture.default_font, legacy=False)
            with mock.patch.object(patcher, "require_no_blockers"), mock.patch.object(
                patcher, "validate_game_info", return_value={}
            ), mock.patch.object(
                patcher,
                "load_upgrade_manifest",
                return_value=(fixture.previous_manifest, PREVIOUS_SHA256),
            ), mock.patch.object(patcher, "verify_package_file"), mock.patch.object(
                patcher, "prepare_font_plan", return_value=plan
            ):
                result = patcher.preflight(
                    fixture.game,
                    fixture.package,
                    fixture.current_manifest,
                    manifest_sha256=CURRENT_SHA256,
                )
            self.assertEqual(result["status"], "preflight_upgrade_passed")
            self.assertEqual(result["upgrade_from"], PREVIOUS_VERSION)
            self.assertEqual(result["original_file_count"], 1)
            self.assertEqual(result["font_mode"], "default")

    def test_failed_commit_rolls_back_every_file_to_beta4_and_recovery_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(fixture)
            actual_replace = patcher.os.replace
            failed = False

            def fail_second_stage_replace(source, destination):
                nonlocal failed
                source_path = Path(source)
                if not failed and "staging" in source_path.parts and source_path.name == "KOREAN.BIN":
                    failed = True
                    raise OSError("injected commit failure")
                return actual_replace(source, destination)

            with blockers, game_info, previous_manifest, font_plan, stage_outputs, mock.patch.object(
                patcher.os, "replace", side_effect=fail_second_stage_replace
            ):
                with self.assertRaisesRegex(OSError, "injected"):
                    patcher.install(fixture.game, fixture.package, fixture.current_manifest, CURRENT_SHA256)

            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.old_static)
            self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.old_copy)
            self.assertEqual(patcher.read_json(fixture.state / patcher.RECEIPT_NAME)["version"], PREVIOUS_VERSION)
            self.assertTrue((fixture.state / patcher.JOURNAL_NAME).is_file())

            with mock.patch.object(patcher, "require_no_blockers"), mock.patch.object(
                patcher,
                "load_upgrade_manifest",
                return_value=(fixture.previous_manifest, PREVIOUS_SHA256),
            ):
                recovered = patcher.recover_pending(
                    fixture.game,
                    fixture.current_manifest,
                    CURRENT_SHA256,
                    fixture.package,
                )
            self.assertEqual(recovered["status"], "incomplete_upgrade_rolled_back")
            self.assertFalse((fixture.state / patcher.JOURNAL_NAME).exists())
            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.old_static)
            self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.old_copy)

    def test_receipt_write_failure_rolls_back_fully_committed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(fixture)
            actual_atomic_write = patcher.atomic_write

            def fail_new_receipt(path: Path, raw: bytes) -> None:
                if path.name == patcher.RECEIPT_NAME and CURRENT_VERSION.encode() in raw:
                    raise OSError("injected receipt failure")
                actual_atomic_write(path, raw)

            with blockers, game_info, previous_manifest, font_plan, stage_outputs, mock.patch.object(
                patcher, "atomic_write", side_effect=fail_new_receipt
            ):
                with self.assertRaisesRegex(OSError, "receipt"):
                    patcher.install(fixture.game, fixture.package, fixture.current_manifest, CURRENT_SHA256)
            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.old_static)
            self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.old_copy)
            self.assertEqual(patcher.read_json(fixture.state / patcher.RECEIPT_NAME)["version"], PREVIOUS_VERSION)
            self.assertEqual(patcher.read_json(fixture.state / patcher.JOURNAL_NAME)["status"], "rolled_back")

    def test_recovery_finalizes_when_new_receipt_was_committed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(fixture)
            actual_unlink = Path.unlink
            failed = False

            def fail_journal_unlink(path: Path, *args, **kwargs):
                nonlocal failed
                if not failed and path.name == patcher.JOURNAL_NAME:
                    failed = True
                    raise OSError("injected journal unlink failure")
                return actual_unlink(path, *args, **kwargs)

            with blockers, game_info, previous_manifest, font_plan, stage_outputs, mock.patch.object(
                Path, "unlink", side_effect=fail_journal_unlink, autospec=True
            ):
                with self.assertRaisesRegex(OSError, "journal unlink"):
                    patcher.install(fixture.game, fixture.package, fixture.current_manifest, CURRENT_SHA256)
            self.assertEqual(patcher.read_json(fixture.state / patcher.RECEIPT_NAME)["version"], CURRENT_VERSION)
            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.new_static)
            self.assertTrue((fixture.state / patcher.JOURNAL_NAME).is_file())

            with mock.patch.object(patcher, "require_no_blockers"):
                recovered = patcher.recover_pending(
                    fixture.game,
                    fixture.current_manifest,
                    CURRENT_SHA256,
                    fixture.package,
                )
            self.assertEqual(recovered["status"], "completed_upgrade_finalized")
            self.assertFalse((fixture.state / patcher.JOURNAL_NAME).exists())
            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.new_static)

    def test_beta4_through_beta8_upgrade_to_iropke_default_without_reselection(self) -> None:
        cases = (
            (PREVIOUS_VERSION, True),
            (BETA5_VERSION, False),
            (BETA6_VERSION, False),
            (BETA7_VERSION, False),
            (BETA8_VERSION, False),
        )
        for previous_version, previous_legacy in cases:
            with self.subTest(previous_version=previous_version), tempfile.TemporaryDirectory() as temporary:
                fixture = UpgradeFixture(
                    Path(temporary),
                    custom=True,
                    previous_version=previous_version,
                    previous_legacy=previous_legacy,
                )
                blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(fixture)
                with blockers, game_info, previous_manifest, font_plan as font_plan_mock, stage_outputs:
                    result = patcher.install(
                        fixture.game,
                        fixture.package,
                        fixture.current_manifest,
                        CURRENT_SHA256,
                    )

                self.assertEqual(result["version"], CURRENT_VERSION)
                self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.new_static)
                self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.new_copy)
                receipt = patcher.read_json(fixture.state / patcher.RECEIPT_NAME)
                self.assertEqual(receipt["upgraded_from"]["version"], previous_version)
                self.assertEqual(receipt["font_generation"]["mode"], "default")
                self.assertEqual(receipt["font_generation"]["primary"], font_face(fixture.default_font))
                self.assertIsNone(receipt["font_generation"]["fallback"])
                font_plan_mock.assert_called_once_with(fixture.package, fixture.current_manifest, None, 0)

    def test_upgrade_uses_selected_custom_font_and_does_not_store_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            selected = Path(temporary) / "private-fonts" / "Custom.ttf"

            def staged_custom(*args, **kwargs):
                identities, _ = fixture.staged(*args, **kwargs)
                return identities, font_receipt(fixture.default_font, legacy=False, mode="custom")

            blockers, game_info, previous_manifest, font_plan, stage_outputs = self.patches(
                fixture,
                staged_custom,
            )
            with blockers, game_info, previous_manifest, font_plan as font_plan_mock, stage_outputs:
                result = patcher.install(
                    fixture.game,
                    fixture.package,
                    fixture.current_manifest,
                    CURRENT_SHA256,
                    str(selected),
                    0,
                )

            self.assertEqual(result["font_mode"], "custom")
            font_plan_mock.assert_called_once_with(
                fixture.package,
                fixture.current_manifest,
                str(selected),
                0,
            )
            receipt_path = fixture.state / patcher.RECEIPT_NAME
            receipt = patcher.read_json(receipt_path)
            self.assertEqual(receipt["font_generation"]["mode"], "custom")
            self.assertEqual(receipt["font_generation"]["primary"]["file_name"], "Custom.ttf")
            self.assertNotIn(str(selected.parent), receipt_path.read_text(encoding="utf-8"))

    def test_same_version_custom_font_change_requires_uninstall_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "game"
            package = Path(temporary) / "package"
            state = game / patcher.STATE_DIR_NAME
            state.mkdir(parents=True)
            (state / patcher.RECEIPT_NAME).write_bytes(
                patcher.canonical(
                    {
                        "version": CURRENT_VERSION,
                        "manifest_sha256": CURRENT_SHA256,
                    }
                )
            )
            with mock.patch.object(patcher, "require_no_blockers"), mock.patch.object(
                patcher,
                "validate_game_info",
                return_value={},
            ), mock.patch.object(patcher, "verify") as verify, mock.patch.object(
                patcher,
                "prepare_font_plan",
            ) as prepare_font_plan:
                with self.assertRaisesRegex(patcher.PatchError, "UNINSTALL.cmd"):
                    patcher.install(
                        game,
                        package,
                        {"version": CURRENT_VERSION},
                        CURRENT_SHA256,
                        r"C:\Fonts\Custom.ttf",
                        0,
                    )

            verify.assert_not_called()
            prepare_font_plan.assert_not_called()

    def test_frozen_beta4_manifest_accepts_only_historical_renderer(self) -> None:
        frozen = Path("packaging/release_assets/upgrades/v0.9.0-beta.4-manifest.json")
        self.assertEqual(frozen.stat().st_size, 31988)
        self.assertEqual(patcher.sha256_file(frozen), "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60")
        document = patcher.json.loads(frozen.read_text(encoding="utf-8"))
        patcher.validate_manifest_document(document, frozen_legacy=True)
        with self.assertRaisesRegex(patcher.PatchError, "font_generation"):
            patcher.validate_manifest_document(document)
        current = {
            "game": document["game"],
            "upgrades": {
                "schema": "homm2-korean-upgrades-v1",
                "from": [
                    {
                        "version": PREVIOUS_VERSION,
                        "manifest_path": f"upgrades/{PREVIOUS_VERSION}-manifest.json",
                        "manifest": patcher.file_identity(frozen),
                    }
                ],
            },
        }
        loaded, loaded_sha256 = patcher.load_upgrade_manifest(
            Path("packaging/release_assets"),
            current,
            PREVIOUS_VERSION,
            "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60",
        )
        self.assertEqual(loaded["version"], PREVIOUS_VERSION)
        self.assertEqual(loaded_sha256, "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60")

    def test_frozen_beta5_through_beta8_manifests_and_receipts_keep_renderer_compatibility(self) -> None:
        fixtures = (
            (
                BETA5_VERSION,
                32_845,
                "A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F",
                True,
            ),
            (
                BETA6_VERSION,
                33_107,
                "32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C",
                True,
            ),
            (
                BETA7_VERSION,
                33_369,
                "F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE",
                True,
            ),
            (
                BETA8_VERSION,
                33_656,
                "A6D0DC07FD27ADC73D3925C76CFBC01CBFE7B6727029EACD87A570132E5B5BB5",
                False,
            ),
        )
        for version, expected_size, expected_sha256, historical_v2 in fixtures:
            with self.subTest(version=version):
                frozen = Path(f"packaging/release_assets/upgrades/{version}-manifest.json")
                self.assertEqual(frozen.stat().st_size, expected_size)
                self.assertEqual(patcher.sha256_file(frozen), expected_sha256)
                document = patcher.json.loads(frozen.read_text(encoding="utf-8"))
                patcher.validate_manifest_document(document, frozen_legacy=True)
                with self.assertRaisesRegex(patcher.PatchError, "font_generation"):
                    patcher.validate_manifest_document(document)

                historical_receipt = font_receipt(
                    b"historical-custom-font",
                    legacy=False,
                    mode="custom",
                    historical_v2=historical_v2,
                )
                patcher.validate_font_receipt(historical_receipt, document)
                if version == BETA8_VERSION:
                    nanum = Path("packaging/release_assets/fonts/NanumGothicCoding-Regular.ttf")
                    beta8_default_receipt = font_receipt(nanum.read_bytes(), legacy=False)
                    patcher.validate_font_receipt(beta8_default_receipt, document)

    def test_current_receipt_rejects_impossible_bearing_layout_diagnostics(self) -> None:
        default_font = UpgradeFixture.default_font
        fallback_font = UpgradeFixture.fallback_font
        manifest = {
            "font_generation": generation(
                default_font,
                fallback_font_raw=fallback_font,
                legacy=False,
            )
        }
        valid = font_receipt(default_font, legacy=False)
        patcher.validate_font_receipt(valid, manifest)

        maximum_normal_shadow_clips = (
            homm2_font.KOREAN_GLYPH_COUNT
            * homm2_font.NORMAL_CELL_WIDTH
            * homm2_font.NORMAL_CELL_HEIGHT
        )
        mutations = (
            ("requested float", "normal", "requested_pixel_size", float(homm2_font.NORMAL_PIXEL_SIZE)),
            ("resolved below minimum", "normal", "resolved_pixel_size", homm2_font.MINIMUM_PIXEL_SIZE - 1),
            ("resolved above request", "small", "resolved_pixel_size", homm2_font.SMALL_PIXEL_SIZE + 1),
            ("cell width float", "normal", "cell_width", float(homm2_font.NORMAL_CELL_WIDTH)),
            ("wrong cell height", "small", "cell_height", homm2_font.SMALL_CELL_HEIGHT - 1),
            ("impossible origin", "normal", "origin_x", 10**9),
            ("wrong small origin", "small", "origin_x", homm2_font.SMALL_CELL_WIDTH // 2 + 1),
            ("impossible baseline", "normal", "baseline_y", -(10**9)),
            ("wrong small baseline", "small", "baseline_y", homm2_font.SMALL_CELL_HEIGHT - 1),
            ("short ink union", "normal", "ink_union", [0, -12, 13]),
            ("non-integer ink union", "normal", "ink_union", [False, -12, 13, 2]),
            ("far-left ink union", "normal", "ink_union", [-(10**9), -12, 13, 2]),
            ("far-top ink union", "normal", "ink_union", [0, -(10**9), 13, 2]),
            ("far-right ink union", "small", "ink_union", [0, -10, 10**9, 2]),
            ("far-bottom ink union", "small", "ink_union", [0, -10, 11, 10**9]),
            ("inverted ink union", "normal", "ink_union", [13, -12, 0, 2]),
            ("ink union taller than cell", "small", "ink_union", [0, -11, 10, 2]),
            ("boolean glyph count", "normal", "glyph_count", True),
            ("too many glyphs", "small", "glyph_count", homm2_font.KOREAN_GLYPH_COUNT + 1),
            ("boolean foreground count", "normal", "foreground_clip_count", False),
            ("clipped foreground", "small", "foreground_clip_count", 1),
            ("boolean shadow count", "normal", "shadow_edge_clip_count", False),
            ("negative shadow count", "small", "shadow_edge_clip_count", -1),
            ("impossible shadow count", "normal", "shadow_edge_clip_count", maximum_normal_shadow_clips + 1),
        )
        for label, size, key, replacement in mutations:
            with self.subTest(label=label):
                malicious = copy.deepcopy(valid)
                malicious["resolved_faces"]["primary"][size][key] = replacement
                with self.assertRaises(patcher.PatchError):
                    patcher.validate_font_receipt(malicious, manifest)

        top_level = copy.deepcopy(valid)
        top_level["normal_cell"]["width"] = float(homm2_font.NORMAL_CELL_WIDTH)
        with self.assertRaises(patcher.PatchError):
            patcher.validate_font_receipt(top_level, manifest)

    def test_current_receipt_allows_zero_primary_glyphs_with_complete_fallback(self) -> None:
        default_font = UpgradeFixture.default_font
        fallback_font = UpgradeFixture.fallback_font
        manifest = {
            "font_generation": generation(
                default_font,
                fallback_font_raw=fallback_font,
                legacy=False,
            )
        }
        receipt = font_receipt(default_font, legacy=False, mode="custom")
        fallback_layout = receipt["resolved_faces"]["primary"]
        receipt["primary_glyph_count"] = 0
        receipt["fallback_glyph_count"] = homm2_font.KOREAN_GLYPH_COUNT
        receipt["fallback"] = font_face(fallback_font)
        receipt["resolved_faces"] = {
            "primary": {"normal": None, "small": None},
            "fallback": fallback_layout,
        }
        patcher.validate_font_receipt(receipt, manifest)

        for label, primary_layout, fallback_layout_value in (
            (
                "one primary size unexpectedly rendered",
                {"normal": resolved_face(14, 13, 14), "small": None},
                fallback_layout,
            ),
            (
                "zero-count primary has rendered layouts",
                fallback_layout,
                fallback_layout,
            ),
            (
                "positive fallback count has no layout",
                {"normal": None, "small": None},
                None,
            ),
        ):
            with self.subTest(label=label):
                malicious = copy.deepcopy(receipt)
                malicious["resolved_faces"]["primary"] = copy.deepcopy(primary_layout)
                malicious["resolved_faces"]["fallback"] = copy.deepcopy(fallback_layout_value)
                with self.assertRaises(patcher.PatchError):
                    patcher.validate_font_receipt(malicious, manifest)

    def test_current_v2_receipt_enforces_iropke_primary_and_nanum_fallback(self) -> None:
        default_font = UpgradeFixture.default_font
        fallback_font = UpgradeFixture.fallback_font
        manifest = {
            "font_generation": generation(
                default_font,
                fallback_font_raw=fallback_font,
                legacy=False,
            )
        }
        receipt = font_receipt(default_font, legacy=False)
        receipt["primary_glyph_count"] = 800
        receipt["fallback_glyph_count"] = homm2_font.KOREAN_GLYPH_COUNT - 800
        for size in ("normal", "small"):
            receipt["resolved_faces"]["primary"][size]["glyph_count"] = 800
        receipt["fallback"] = font_face(fallback_font, "Nanum.ttf")
        receipt["resolved_faces"]["fallback"] = {
            "normal": resolved_face(
                homm2_font.NORMAL_PIXEL_SIZE,
                homm2_font.NORMAL_CELL_WIDTH,
                homm2_font.NORMAL_CELL_HEIGHT,
                glyph_count=homm2_font.KOREAN_GLYPH_COUNT - 800,
            ),
            "small": resolved_face(
                homm2_font.SMALL_PIXEL_SIZE,
                homm2_font.SMALL_CELL_WIDTH,
                homm2_font.SMALL_CELL_HEIGHT,
                glyph_count=homm2_font.KOREAN_GLYPH_COUNT - 800,
            ),
        }
        patcher.validate_font_receipt(receipt, manifest)

        wrong_primary = copy.deepcopy(receipt)
        wrong_primary["primary"] = font_face(fallback_font, "Nanum.ttf")
        with self.assertRaisesRegex(patcher.PatchError, "기본 설치 기록"):
            patcher.validate_font_receipt(wrong_primary, manifest)

        wrong_fallback = copy.deepcopy(receipt)
        wrong_fallback["fallback"] = font_face(default_font, "Iropke.ttf")
        with self.assertRaisesRegex(patcher.PatchError, "대체 글꼴"):
            patcher.validate_font_receipt(wrong_fallback, manifest)

        custom = copy.deepcopy(receipt)
        custom["mode"] = "custom"
        custom["primary"] = font_face(b"selected-font", "Selected.ttf")
        patcher.validate_font_receipt(custom, manifest)

    def test_font_generation_v2_requires_separate_default_and_fallback_descriptors(self) -> None:
        current = generation(
            UpgradeFixture.default_font,
            fallback_font_raw=UpgradeFixture.fallback_font,
            legacy=False,
        )
        self.assertEqual(
            patcher.validate_font_generation(current),
            ["fonts/mapping.txt", "fonts/Iropke.ttf", "fonts/Nanum.ttf"],
        )

        missing_fallback = copy.deepcopy(current)
        del missing_fallback["fallback_font"]
        with self.assertRaisesRegex(patcher.PatchError, "대체 글꼴"):
            patcher.validate_font_generation(missing_fallback)

        frozen = generation(
            UpgradeFixture.fallback_font,
            legacy=False,
            frozen_legacy=True,
        )
        self.assertEqual(
            patcher.validate_font_generation(frozen, frozen_legacy=True),
            ["fonts/mapping.txt", "fonts/Legacy.ttf"],
        )
        with self.assertRaisesRegex(patcher.PatchError, "font_generation"):
            patcher.validate_font_generation(frozen)

    def test_invalid_staged_font_metadata_blocks_upgrade_before_backup_or_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            blockers, game_info, previous_manifest, font_plan, _ = self.patches(fixture)
            backup_directories_before = set((fixture.state / "backups").iterdir())

            def invalid_staged(*args, **kwargs):
                identities, metadata = fixture.staged(*args, **kwargs)
                metadata["resolved_faces"]["primary"]["normal"]["baseline_y"] = 10**9
                return identities, metadata

            with blockers, game_info, previous_manifest, font_plan, mock.patch.object(
                patcher, "stage_outputs", side_effect=invalid_staged
            ), mock.patch.object(patcher, "copy_backup") as copy_backup, mock.patch.object(
                patcher.os, "replace"
            ) as replace:
                with self.assertRaisesRegex(patcher.PatchError, "원점"):
                    patcher.install(fixture.game, fixture.package, fixture.current_manifest, CURRENT_SHA256)

            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.old_static)
            self.assertEqual((fixture.game / "KOREAN.BIN").read_bytes(), fixture.old_copy)
            self.assertEqual(patcher.read_json(fixture.state / patcher.RECEIPT_NAME)["version"], PREVIOUS_VERSION)
            self.assertFalse((fixture.state / patcher.JOURNAL_NAME).exists())
            self.assertEqual(set((fixture.state / "backups").iterdir()), backup_directories_before)
            copy_backup.assert_not_called()
            replace.assert_not_called()

    def test_invalid_staged_font_metadata_blocks_fresh_install_before_backup_or_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UpgradeFixture(Path(temporary))
            (fixture.state / patcher.RECEIPT_NAME).unlink()
            (fixture.game / "DATA" / "A.BIN").write_bytes(fixture.original)
            (fixture.game / "KOREAN.BIN").unlink()
            backup_directories_before = set((fixture.state / "backups").iterdir())

            def invalid_staged(*args, **kwargs):
                identities, metadata = fixture.staged(*args, **kwargs)
                metadata["resolved_faces"]["primary"]["small"]["origin_x"] = -(10**9)
                return identities, metadata

            with mock.patch.object(patcher, "require_no_blockers"), mock.patch.object(
                patcher, "validate_game_info", return_value={}
            ), mock.patch.object(patcher, "prepare_font_plan", return_value=object()), mock.patch.object(
                patcher, "stage_outputs", side_effect=invalid_staged
            ), mock.patch.object(patcher, "copy_backup") as copy_backup, mock.patch.object(
                patcher.os, "replace"
            ) as replace:
                with self.assertRaisesRegex(patcher.PatchError, "원점"):
                    patcher.install(fixture.game, fixture.package, fixture.current_manifest, CURRENT_SHA256)

            self.assertEqual((fixture.game / "DATA" / "A.BIN").read_bytes(), fixture.original)
            self.assertFalse((fixture.game / "KOREAN.BIN").exists())
            self.assertFalse((fixture.state / patcher.RECEIPT_NAME).exists())
            self.assertFalse((fixture.state / patcher.JOURNAL_NAME).exists())
            self.assertEqual(set((fixture.state / "backups").iterdir()), backup_directories_before)
            copy_backup.assert_not_called()
            replace.assert_not_called()

    def test_current_rendered_font_receipt_matches_bearing_validator(self) -> None:
        mapping = Path("translations/font/mapping874.fixed-interface-font.txt")
        default_font = Path("packaging/release_assets/fonts/IropkeBatangM.ttf")
        fallback_font = Path("packaging/release_assets/fonts/NanumGothicCoding-Regular.ttf")
        plan = homm2_font.make_font_plan(
            mapping,
            default_font,
            fallback_path=fallback_font,
            mode="default",
        )
        metadata = homm2_font.render_font(plan).metadata
        manifest = {
            "font_generation": {
                **generation(
                    default_font.read_bytes(),
                    fallback_font_raw=fallback_font.read_bytes(),
                    legacy=False,
                ),
                "mapping": {"package_path": "fonts/mapping.txt", "package": patcher.file_identity(mapping)},
                "default_font": {
                    "name": "Iropke Batang Medium",
                    "package_path": "fonts/IropkeBatangM.ttf",
                    "package": patcher.file_identity(default_font),
                    "face_index": 0,
                    "license_path": "licenses/IROPKE_BATANG_OFL.txt",
                },
                "fallback_font": {
                    "name": "NanumGothicCoding Regular",
                    "package_path": "fonts/NanumGothicCoding-Regular.ttf",
                    "package": patcher.file_identity(fallback_font),
                    "face_index": 0,
                    "license_path": "licenses/NANUMFONT_LICENSE.txt",
                },
            }
        }
        patcher.validate_font_receipt(metadata, manifest)


if __name__ == "__main__":
    unittest.main()
