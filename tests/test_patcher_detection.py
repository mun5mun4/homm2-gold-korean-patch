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

    def test_removed_custom_font_cli_options_are_rejected_before_loading_the_package(self) -> None:
        cases = (
            ("--font-file", ["Fixture.ttf"]),
            ("--font-index", ["1"]),
            ("--choose-font", []),
        )
        for option, values in cases:
            with self.subTest(option=option), mock.patch.object(
                patcher.sys,
                "argv",
                ["homm2-ko-patcher", "install", option, *values],
            ), mock.patch.object(patcher, "load_manifest") as load_manifest:
                with mock.patch.object(patcher.sys, "stderr", new_callable=io.StringIO), self.assertRaises(
                    SystemExit
                ) as raised:
                    patcher.main()
                self.assertEqual(raised.exception.code, 2)
                load_manifest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
