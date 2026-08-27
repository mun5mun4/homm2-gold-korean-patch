#!/usr/bin/env python3
"""Tests for game-directory discovery without touching a real installation."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.release import homm2_ko_patcher as patcher


class GameDirectoryDetectionTests(unittest.TestCase):
    def test_documented_gog_galaxy_default_path(self) -> None:
        self.assertEqual(
            patcher.DEFAULT_GOG_DIR,
            Path(r"C:\Program Files (x86)\GOG Galaxy\Games\HoMM 2 Gold"),
        )

    def test_default_candidate_is_detected_before_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary) / "HoMM 2 Gold"
            game.mkdir()
            (game / patcher.INFO_NAME).write_text("{}", encoding="utf-8")
            (game / "HEROES2.EXE").write_bytes(b"fixture")

            with mock.patch.object(patcher, "DEFAULT_GOG_DIR", game), mock.patch.object(
                patcher, "package_root", return_value=Path(temporary) / "package"
            ), mock.patch.object(patcher.Path, "cwd", return_value=Path(temporary) / "cwd"):
                self.assertEqual(patcher.detect_game_dir(None), game.resolve())

    def test_custom_font_file_and_face_index_are_forwarded_to_install(self) -> None:
        package = Path("package")
        manifest = {"version": "fixture"}
        game = Path("game")
        with mock.patch.object(
            patcher.sys,
            "argv",
            ["homm2-ko-patcher", "install", "--font-file", "Fixture.ttc", "--font-index", "2"],
        ), mock.patch.object(
            patcher,
            "load_manifest",
            return_value=(package, manifest, "A" * 64),
        ), mock.patch.object(
            patcher,
            "detect_game_dir",
            return_value=game,
        ), mock.patch.object(patcher, "operation_lock"), mock.patch.object(
            patcher,
            "install",
            return_value={},
        ) as install:
            self.assertEqual(patcher.main(), 0)

        install.assert_called_once_with(
            game,
            package,
            manifest,
            "A" * 64,
            "Fixture.ttc",
            2,
        )

    def test_choose_font_is_forwarded_to_preflight(self) -> None:
        package = Path("package")
        manifest = {"version": "fixture"}
        game = Path("game")
        selected = r"C:\Fonts\Selected.otc"
        with mock.patch.object(
            patcher.sys,
            "argv",
            ["homm2-ko-patcher", "preflight", "--choose-font", "--font-index", "3"],
        ), mock.patch.object(
            patcher,
            "choose_font_file",
            return_value=selected,
        ) as choose_font, mock.patch.object(
            patcher,
            "load_manifest",
            return_value=(package, manifest, "B" * 64),
        ), mock.patch.object(
            patcher,
            "detect_game_dir",
            return_value=game,
        ), mock.patch.object(patcher, "operation_lock"), mock.patch.object(
            patcher,
            "preflight",
            return_value={},
        ) as preflight:
            self.assertEqual(patcher.main(), 0)

        choose_font.assert_called_once_with()
        preflight.assert_called_once_with(
            game,
            package,
            manifest,
            "B" * 64,
            selected,
            3,
        )

    def test_mutually_exclusive_font_sources_are_rejected_before_loading_the_package(self) -> None:
        with mock.patch.object(
            patcher.sys,
            "argv",
            ["homm2-ko-patcher", "install", "--font-file", "Fixture.ttf", "--choose-font"],
        ), mock.patch.object(patcher, "load_manifest") as load_manifest:
            with mock.patch.object(patcher.sys, "stderr", new_callable=io.StringIO), self.assertRaises(
                SystemExit
            ) as raised:
                patcher.main()

        self.assertEqual(raised.exception.code, 2)
        load_manifest.assert_not_called()

    def test_font_options_are_rejected_for_non_install_actions_before_package_loading(self) -> None:
        cases = (
            ["verify", "--font-file", "Fixture.ttf"],
            ["verify", "--font-file", ""],
            ["uninstall", "--choose-font"],
            ["recover", "--font-index", "1", "--font-file", "Fixture.ttc"],
            ["install", "--font-index", "1"],
            ["install", "--font-index", "-1", "--font-file", "Fixture.ttc"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), mock.patch.object(
                patcher.sys,
                "argv",
                ["homm2-ko-patcher", *arguments],
            ), mock.patch.object(patcher, "load_manifest") as load_manifest, mock.patch.object(
                patcher.sys,
                "stderr",
                new_callable=io.StringIO,
            ):
                self.assertEqual(patcher.main(), 1)
                load_manifest.assert_not_called()

    def test_cancelled_font_picker_stops_before_package_loading(self) -> None:
        with mock.patch.object(
            patcher.sys,
            "argv",
            ["homm2-ko-patcher", "install", "--choose-font"],
        ), mock.patch.object(
            patcher,
            "choose_font_file",
            side_effect=patcher.PatchError("글꼴 선택을 취소했습니다"),
        ), mock.patch.object(patcher, "load_manifest") as load_manifest, mock.patch.object(
            patcher.sys,
            "stderr",
            new_callable=io.StringIO,
        ):
            self.assertEqual(patcher.main(), 1)

        load_manifest.assert_not_called()

    def test_prepare_custom_font_plan_uses_bundled_default_only_as_fallback(self) -> None:
        package = Path("package")
        mapping = Path("package/fonts/mapping.txt")
        default = Path("package/fonts/NanumGothicCoding-Regular.ttf")
        selected = r"C:\Private Fonts\Selected.ttc"
        manifest = {
            "font_generation": {
                "mapping": {"package_path": "fonts/mapping.txt"},
                "default_font": {
                    "package_path": "fonts/NanumGothicCoding-Regular.ttf",
                    "face_index": 0,
                },
            }
        }
        plan = mock.Mock()
        plan.metadata.return_value = {
            "primary": {"family": "Selected Family", "file_name": "Selected.ttc"},
            "primary_glyph_count": 800,
            "fallback_glyph_count": 74,
        }
        with mock.patch.object(
            patcher,
            "verify_package_artifact",
            side_effect=(mapping, default),
        ), mock.patch.object(
            patcher.homm2_font,
            "make_font_plan",
            return_value=plan,
        ) as make_plan, mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertIs(patcher.prepare_font_plan(package, manifest, selected, 2), plan)

        make_plan.assert_called_once_with(
            mapping,
            Path(selected),
            primary_face_index=2,
            fallback_path=default,
            fallback_face_index=0,
            mode="custom",
        )
        self.assertNotIn(selected, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
