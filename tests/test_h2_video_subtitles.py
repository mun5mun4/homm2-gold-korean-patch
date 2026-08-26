#!/usr/bin/env python3
"""Portable contracts for the Korean campaign-video subtitle builder."""

from __future__ import annotations

import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools.localization import h2_video_subtitles as subtitles


ROOT = Path(__file__).resolve().parents[1]


class VideoSubtitleContractTests(unittest.TestCase):
    def test_pinned_public_inputs_and_coverage(self) -> None:
        self.assertEqual(subtitles.identity(subtitles.MAPPING_PATH.read_bytes()), subtitles.MAPPING_ID)
        self.assertEqual(subtitles.identity(subtitles.SCENE_CUES_PATH.read_bytes()), subtitles.CUE_SOURCE_ID)
        mapping = subtitles.load_subtitle_mapping()
        cues, meta = subtitles.load_scene_cues(mapping=mapping)
        self.assertEqual(len(mapping.by_character), 874)
        self.assertEqual((meta["movie_count"], meta["scene_count"], meta["cue_count"]), (51, 57, 388))
        self.assertEqual(meta["track_counts"], {"primary_ms": 27, "secondary_ms": 361})
        self.assertEqual(
            meta["timing_status_counts"],
            {"voice_aligned": 254, "voice_aligned_combined": 3, "voice_aligned_split": 131},
        )
        self.assertEqual(sum(cue.track == subtitles.TRACK_PRIMARY_MS for cue in cues), 27)
        self.assertEqual(sum(cue.track == subtitles.TRACK_SECONDARY_MS for cue in cues), 361)

    def test_ksx2_round_trip_lookup_and_fail_closed_parse(self) -> None:
        cues = (
            subtitles.Cue(4, subtitles.TRACK_PRIMARY_MS, 100, 200, b"first"),
            subtitles.Cue(4, subtitles.TRACK_PRIMARY_MS, 250, 350, b"second"),
            subtitles.Cue(5, subtitles.TRACK_SECONDARY_MS, 10, 20, b"voice"),
        )
        encoded = subtitles.serialize_cues(cues)
        self.assertNotIn(b"\0", encoded)
        self.assertEqual(subtitles.parse_cues(encoded), cues)
        self.assertEqual(subtitles.lookup_cue(cues, 4, subtitles.TRACK_PRIMARY_MS, 100), cues[0])
        self.assertIsNone(subtitles.lookup_cue(cues, 4, subtitles.TRACK_PRIMARY_MS, 200))
        damaged = bytearray(encoded)
        damaged[0] ^= 1
        with self.assertRaises(subtitles.BuildError):
            subtitles.parse_cues(bytes(damaged))

    def test_dual_ms_tracks_share_now_but_keep_separate_starts(self) -> None:
        samples = subtitles.sample_dual_ms_clocks(
            now_tick=10_000,
            primary_handle=1,
            primary_start_tick=9_000,
            secondary_handle=2,
            secondary_start_tick=9_500,
        )
        self.assertEqual(samples, {subtitles.TRACK_PRIMARY_MS: 1_000, subtitles.TRACK_SECONDARY_MS: 500})
        self.assertEqual(subtitles.select_ms_timeline(subtitles.TRACK_PRIMARY_MS, samples), 1_000)
        self.assertEqual(subtitles.select_ms_timeline(subtitles.TRACK_SECONDARY_MS, samples), 500)
        self.assertIsNone(subtitles.select_ms_timeline(subtitles.TRACK_PRIMARY, samples))
        unavailable = subtitles.sample_dual_ms_clocks(
            now_tick=10_000,
            primary_handle=0,
            primary_start_tick=9_000,
            secondary_handle=2,
            secondary_start_tick=9_500,
        )
        self.assertIsNone(unavailable[subtitles.TRACK_PRIMARY_MS])
        self.assertEqual(unavailable[subtitles.TRACK_SECONDARY_MS], 500)

    def test_runtime_and_descriptor_encryption_contract(self) -> None:
        canonical = subtitles.build_heap_runtime()
        runtime = subtitles.build_heap_runtime(safe_refresh_dispatch=True)
        self.assertEqual(subtitles.identity(canonical), subtitles.CANONICAL_RUNTIME_ID)
        self.assertEqual(subtitles.identity(runtime), subtitles.SAFE_RUNTIME_ID)
        self.assertNotEqual(runtime, canonical)
        encrypted = bytes(value ^ subtitles.RUNTIME_XOR_KEY for value in runtime)
        self.assertEqual(len(encrypted), 1_856)
        self.assertNotIn(b"\0", encrypted)
        contract = subtitles.verify_safe_refresh_runtime_contract(runtime)
        self.assertEqual(contract["dispatch_pointer"], "0x182EAC")
        self.assertEqual(contract["late_publication_height"], 73)

    def test_bootstrap_bridge_and_dispatch_contract(self) -> None:
        bootstrap = subtitles.build_safe_refresh_bootstrap(1_856, subtitles.RUNTIME_XOR_KEY)
        bridge = subtitles.build_safe_refresh_bridge()
        self.assertEqual(len(bootstrap), 106)
        self.assertIn(bytes.fromhex("80 3C 0E 00"), bootstrap)
        self.assertEqual(bridge, b"\xFF\x25" + struct.pack("<I", subtitles.SAFE_REFRESH_DISPATCH_POINTER))
        self.assertEqual(subtitles.SAFE_REFRESH_BRIDGE_PREFERRED, subtitles.CAVE_PREFERRED + 0x71 - 6)
        self.assertEqual(subtitles.RECT_REFRESH_ACTUAL, 0x2A4409)

    def test_flicker_lifecycle_is_single_band_publication(self) -> None:
        events = subtitles.simulate_frame_publish_lifecycle(secondary_refresh=True, late_hook=True)
        self.assertEqual(events, ("primary_upper_refresh", "secondary_upper_refresh", "subtitle_band_refresh"))
        self.assertEqual(events.count("subtitle_band_refresh"), 1)
        self.assertEqual(
            subtitles.simulate_frame_publish_lifecycle(secondary_refresh=False, late_hook=False),
            ("primary_clean_refresh", "subtitle_refresh"),
        )
        self.assertEqual(
            subtitles.simulate_active_transition(0, cue_matches=True, font_available=True, surface_available=True),
            (1, "draw"),
        )
        self.assertEqual(
            subtitles.simulate_active_transition(1, cue_matches=False, font_available=True, surface_available=True),
            (0, "band"),
        )

    def test_pinned_source_and_final_hash_contracts(self) -> None:
        self.assertEqual(
            subtitles.SOURCE_EXE_ID,
            (1_523_420, "52AE3BA15AE309327D698EDEE8844684F91B3BA056B9215854002265A9F6E3EF"),
        )
        self.assertEqual(
            subtitles.SOURCE_BANK_ID,
            (11_286, "DD30DD967E81BB179BC1D33903D0B8926FB799D969A3C36FFAA6CA3FA0C89AAF"),
        )
        self.assertEqual(
            subtitles.FINAL_EXE_ID,
            (1_523_420, "B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C"),
        )
        self.assertEqual(
            subtitles.FINAL_BANK_ID,
            (36_265, "95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A"),
        )
        tool_source = Path(subtitles.__file__).read_bytes()
        self.assertNotIn(b"_codex_probe", tool_source)
        self.assertNotIn(b"WATCOM C/C++", tool_source)

    def test_builder_refuses_proprietary_outputs_in_repository(self) -> None:
        with self.assertRaises(subtitles.BuildError):
            subtitles._refuse_repository_output(ROOT / "build" / "video-subtitles")

    def test_builder_refuses_source_directories_and_nonempty_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="homm2-video-subtitles-safety-") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            source_exe = source / "HEROES2.EXE"
            source_bank = source / "KOREAN.BIN"
            source_exe.write_bytes(b"source-exe")
            source_bank.write_bytes(b"source-bank")

            with self.assertRaisesRegex(subtitles.BuildError, "source file directory"):
                subtitles._prepare_build_output(source, source_exe, source_bank)
            self.assertEqual(source_exe.read_bytes(), b"source-exe")
            self.assertEqual(source_bank.read_bytes(), b"source-bank")

            occupied = root / "occupied"
            occupied.mkdir()
            sentinel = occupied / "keep.txt"
            sentinel.write_bytes(b"keep")
            with self.assertRaisesRegex(subtitles.BuildError, "must be empty"):
                subtitles._prepare_build_output(occupied, source_exe, source_bank)
            self.assertEqual(sentinel.read_bytes(), b"keep")

            empty = root / "empty"
            empty.mkdir()
            self.assertEqual(
                subtitles._prepare_build_output(empty, source_exe, source_bank),
                empty.resolve(),
            )

            new_output = root / "new-output"
            self.assertEqual(
                subtitles._prepare_build_output(new_output, source_exe, source_bank),
                new_output.resolve(),
            )
            self.assertTrue(new_output.is_dir())

    def test_opt_in_beta6_build_and_verify_exact_outputs(self) -> None:
        exe_value = os.environ.get("HOMM2_BETA6_EXE")
        bank_value = os.environ.get("HOMM2_BETA6_BANK")
        if not exe_value or not bank_value:
            self.skipTest("set HOMM2_BETA6_EXE and HOMM2_BETA6_BANK for the proprietary integration test")
        source_exe = Path(exe_value)
        source_bank = Path(bank_value)
        self.assertTrue(source_exe.is_file(), source_exe)
        self.assertTrue(source_bank.is_file(), source_bank)
        with tempfile.TemporaryDirectory(prefix="homm2-video-subtitles-") as directory:
            output_dir = Path(directory)
            built = subtitles.build_command(source_exe, source_bank, output_dir)
            self.assertEqual(
                (built["outputs"]["HEROES2.EXE"]["size"], built["outputs"]["HEROES2.EXE"]["sha256"]),
                subtitles.FINAL_EXE_ID,
            )
            self.assertEqual(
                (built["outputs"]["KOREAN.BIN"]["size"], built["outputs"]["KOREAN.BIN"]["sha256"]),
                subtitles.FINAL_BANK_ID,
            )
            verified = subtitles.verify_command(source_exe, source_bank, output_dir)
            self.assertTrue(verified["verified"])


if __name__ == "__main__":
    unittest.main()
