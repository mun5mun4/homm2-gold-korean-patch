#!/usr/bin/env python3
"""Portable contracts for the Korean campaign-video subtitle builder."""

from __future__ import annotations

import os
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
        self.assertFalse(
            any(0x30 <= value <= 0x39 for cue in cues for value in cue.text),
            "원작 ASCII 숫자 글리프는 한글 자막의 기준선과 높이가 다릅니다",
        )

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
        runtime = subtitles.build_heap_runtime(stable_refresh_height=True)
        self.assertEqual(subtitles.identity(canonical), subtitles.CANONICAL_RUNTIME_ID)
        self.assertEqual(subtitles.identity(runtime), subtitles.STABLE_HEIGHT_RUNTIME_ID)
        self.assertNotEqual(runtime, canonical)
        encrypted = bytes(value ^ subtitles.RUNTIME_XOR_KEY for value in runtime)
        self.assertEqual(len(encrypted), 1_856)
        self.assertNotIn(b"\0", encrypted)
        contract = subtitles.verify_stable_refresh_runtime_contract(runtime)
        self.assertFalse(contract["heap_callback_published"])
        self.assertFalse(contract["cross_object_code_call"])
        self.assertEqual(contract["height_state_pointer"], "0x182EAC")
        self.assertEqual(contract["late_publication_height"], 73)

    def test_bootstrap_and_fixed_refresh_context_contract(self) -> None:
        bootstrap = subtitles.build_stable_refresh_bootstrap(1_856, subtitles.RUNTIME_XOR_KEY)
        context = subtitles.build_stable_refresh_context()
        expected_bootstrap = bytes.fromhex(
            "E8 BC EB FB FF 9C 60 C6 05 AC 3E 13 00 DF "
            "A0 2D B2 11 00 2C 04 3C 3B 77 42 BF D8 3F 13 00 "
            "8B 1F 8B 1B 85 DB 74 35 8B 83 FC 02 01 00 85 C0 74 2B "
            "80 38 40 75 29 8D 70 01 B9 40 07 00 00 80 3C 0E 00 75 24 "
            "80 36 0D 46 E2 FA 40 81 78 02 4B 53 58 52 75 14 "
            "89 83 FC 02 01 00 FF D0 61 9D C3 81 78 02 4B 53 58 52 74 F2 "
            "31 C0 89 83 FC 02 01 00 EB EA"
        )
        expected_context = bytes.fromhex(
            "6A 00 6A 00 68 DF 01 00 00 A1 70 AD 03 00 8B 40 46 "
            "B9 7F 02 00 00 31 DB 31 D2 E8 53 1D 02 00"
        )
        self.assertEqual(bootstrap, expected_bootstrap)
        self.assertEqual(len(bootstrap), subtitles.CAVE_CAPACITY)
        self.assertEqual(context, expected_context)
        self.assertEqual(len(context), len(subtitles.VIDEO_REFRESH_CALL_CONTEXT))

        # The bootstrap contains only preferred addresses.  The LE loader owns
        # their conversion to each process's actual Object2/Object3 bases.
        preferred_height = subtitles.OBJECT3_PREFERRED_BASE + subtitles.STABLE_REFRESH_HEIGHT_OBJECT_OFFSET
        preferred_scene = subtitles.OBJECT2_PREFERRED_BASE + 0x3B22D
        preferred_table = subtitles.OBJECT3_PREFERRED_BASE + subtitles.RUNTIME_RELOC_TABLE_OBJECT_OFFSET
        self.assertEqual(
            bootstrap.count(b"\xC6\x05" + preferred_height.to_bytes(4, "little") + b"\xDF"),
            1,
        )
        self.assertEqual(bootstrap.count(b"\xA0" + preferred_scene.to_bytes(4, "little")), 1)
        self.assertEqual(bootstrap.count(b"\xBF" + preferred_table.to_bytes(4, "little")), 1)
        self.assertNotIn(subtitles.STABLE_REFRESH_HEIGHT_POINTER.to_bytes(4, "little"), bootstrap)
        self.assertNotIn(subtitles.SCENE_BYTE.to_bytes(4, "little"), bootstrap)

        relocation_table = subtitles.build_runtime_relocation_table()
        self.assertEqual(len(relocation_table), subtitles.RUNTIME_RELOC_TABLE_SIZE)
        preferred_bases = {
            1: subtitles.OBJECT1_PREFERRED_BASE,
            2: subtitles.OBJECT2_PREFERRED_BASE,
            3: subtitles.OBJECT3_PREFERRED_BASE,
        }
        self.assertEqual(
            tuple(
                int.from_bytes(relocation_table[index:index + 4], "little")
                for index in range(0, len(relocation_table), 4)
            ),
            tuple(
                preferred_bases[target_object] + target_offset
                for _name, target_object, target_offset, _placeholder in subtitles.RUNTIME_RELOC_TARGETS
            ),
        )

        # Preserve the original Smacker setup and replace only its shared CALL.
        call_index = subtitles.VIDEO_REFRESH_CALL_OBJECT_OFFSET - subtitles.VIDEO_REFRESH_CALL_CONTEXT_OBJECT_OFFSET
        self.assertEqual(call_index, 26)
        self.assertEqual(context[:call_index], subtitles.VIDEO_REFRESH_CALL_CONTEXT[:call_index])
        self.assertEqual(context[call_index], 0xE8)
        call_after = subtitles.VIDEO_REFRESH_CONTEXT_PREFERRED + call_index + 5
        displacement = int.from_bytes(context[call_index + 1:call_index + 5], "little", signed=True)
        self.assertEqual(
            call_after + displacement,
            subtitles.OBJECT1_PREFERRED_BASE + subtitles.REFRESH_CLIP_CAVE_A_OBJECT_OFFSET,
        )
        # The unmodified Smacker CFG joins the common call at 0x7396D.
        # Pin the exact branch so a future context rewrite cannot again move
        # the CALL while leaving this inbound edge behind.
        self.assertEqual(subtitles.LATE_REFRESH_JOIN_BRANCH_OBJECT_OFFSET, 0x739E8)
        self.assertEqual(subtitles.LATE_REFRESH_JOIN_BRANCH_BYTES, bytes.fromhex("EB 83"))
        self.assertEqual(
            subtitles.LATE_REFRESH_JOIN_BRANCH_OBJECT_OFFSET + 2
            + int.from_bytes(subtitles.LATE_REFRESH_JOIN_BRANCH_BYTES[1:2], "little", signed=True),
            subtitles.VIDEO_REFRESH_CALL_OBJECT_OFFSET,
        )
        self.assertNotIn(bytes.fromhex("E8 80 06 EF FF"), context)
        self.assertNotIn(b"\xFF\x25", bootstrap + context)
        self.assertEqual(subtitles.RECT_REFRESH_ACTUAL, 0x2A4409)

        self.assertEqual(
            subtitles.build_refresh_clip_fragments(),
            (
                bytes.fromhex("57 8B 3D AC 3E 13 00 29 DF EB 71"),
                bytes.fromhex("76 12 39 7C 24 08 76 10 89 7C 24 08 EB 0A 90"),
                bytes.fromhex("5F C2 0C 00 5F E9 AA FC FE FF 90"),
            ),
        )
        self.assertEqual(subtitles.simulate_refresh_clip(406, 0, 479), 406)
        self.assertEqual(subtitles.simulate_refresh_clip(406, 405, 100), 1)
        self.assertIsNone(subtitles.simulate_refresh_clip(406, 406, 73))
        self.assertEqual(subtitles.simulate_refresh_clip(479, 0, 479), 479)

    def test_portable_descriptor_validator_exact_relative_contract(self) -> None:
        validator = subtitles.build_portable_descriptor_validator()
        expected = bytes.fromhex(
            "8D 46 09 39 E8 77 52 89 F2 AD A9 03 FC FF FF 74 20 "
            "3D 20 E9 02 00 72 41 3D 20 15 03 00 73 3A A8 03 75 36 "
            "BF 00 00 0E 00 01 C7 89 3A AD 01 F8 EB 0B "
            "8B 3D 98 3E 13 00 01 C7 89 3A AD 39 07 75 19 "
            "80 3E 40 75 14 46 39 EE 73 0F 80 3E 00 75 F6 46 E2 AE "
            "39 EE 75 03 31 C0 C3 B0 01 C3 90 90 90 90"
        )
        self.assertEqual(subtitles.DESCRIPTOR_VALIDATOR_OBJECT_OFFSET, 0xBEDA0)
        self.assertEqual(subtitles.DESCRIPTOR_VALIDATOR_SIZE, 0x60)
        self.assertEqual(validator, expected)
        self.assertEqual(len(validator) - 4, 0x5C)
        self.assertEqual(validator[0x5C:], b"\x90" * 4)
        self.assertEqual(
            subtitles.read_u32(validator, 0x24),
            subtitles.OBJECT2_PREFERRED_BASE,
        )
        self.assertEqual(
            subtitles.read_u32(validator, 0x33),
            subtitles.OBJECT3_PREFERRED_BASE + 0x3E98,
        )
        self.assertNotIn(subtitles.OBJECT2_ACTUAL_BASE.to_bytes(4, "little"), validator)

        self.assertIn(
            (0x3F5C, 1, subtitles.DESCRIPTOR_VALIDATOR_OBJECT_OFFSET),
            subtitles.H2K3_O3_ABSOLUTE_TRANSFER_FIXUPS,
        )

        veneer_a, veneer_b = subtitles.build_h2k3_portable_veneers()
        self.assertEqual(
            veneer_a,
            bytes.fromhex("68 2C 3F 13 00 C3 68 D4 3E 13 00 C3 00"),
        )
        self.assertEqual(veneer_b, bytes.fromhex("68 46 3F 13 00 C3 00"))
        self.assertEqual(
            subtitles.build_h2k3_o3_portable_patch(),
            bytes.fromhex(
                "68 F0 4F 0D 00 C3 0F B6 47 0C C1 E0 04 83 C0 20 39 47 14 "
                "75 D4 8D 1C 07 57 89 DE B8 A0 ED 0C 00 FF D0 5F C3"
            ),
        )

        # Direct rows carry an Object2 offset and an expected-pointer delta.
        # Relocating Object2 must therefore shift both resolved pointers by the
        # same amount, including when the delta wraps as an unsigned dword.
        for object2_base, target_offset, expected_offset in (
            (0x240000, 0x2E920, 0x3151C),
            (0x580000, 0x3151C, 0x2E920),
        ):
            expected_delta = (expected_offset - target_offset) & 0xFFFFFFFF
            resolved_target = (object2_base + target_offset) & 0xFFFFFFFF
            resolved_expected = (resolved_target + expected_delta) & 0xFFFFFFFF
            self.assertEqual(resolved_expected, object2_base + expected_offset)

    def test_data_only_refresh_height_transition(self) -> None:
        self.assertEqual(subtitles.next_stable_refresh_height(subtitle_published=False), 479)
        self.assertEqual(subtitles.next_stable_refresh_height(subtitle_published=True), 406)
        self.assertEqual(
            subtitles.simulate_data_height_frame(479, late_hook=True, subtitle_published=True),
            (479, 406),
        )
        self.assertEqual(
            subtitles.simulate_data_height_frame(406, late_hook=True, subtitle_published=True),
            (406, 406),
        )
        self.assertEqual(
            subtitles.simulate_data_height_frame(406, late_hook=True, subtitle_published=False),
            (406, 479),
        )
        # If teardown skips the late hook entirely, stale clipping is bounded
        # and explicit: one following inner refresh may still consume 406.
        self.assertEqual(
            subtitles.simulate_data_height_frame(406, late_hook=False),
            (406, 406),
        )

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
            (1_523_420, "87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365"),
        )
        self.assertEqual(
            subtitles.FINAL_BANK_ID,
            (36_159, "37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA"),
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
        source_exe_bytes = source_exe.read_bytes()
        source_bank_bytes = source_bank.read_bytes()
        self.assertEqual(subtitles.identity(source_exe_bytes), subtitles.SOURCE_EXE_ID)
        self.assertEqual(subtitles.identity(source_bank_bytes), subtitles.SOURCE_BANK_ID)

        native_proof = subtitles.verify_native_unit_fallbacks(source_exe_bytes, source_bank_bytes)
        self.assertEqual(
            native_proof,
            (
                (0x2E71C, 0x0000),
                (0x2E720, 0x2516),
                (0x2E748, 0x00C4),
                (0x2E79C, 0x021C),
                (0x2E7E0, 0x033E),
                (0x2E7F4, 0x039C),
                (0x2E820, 0x0432),
            ),
        )
        source_parsed = subtitles.parse_bank(
            source_bank_bytes,
            expected_mapping_tag=subtitles.MAPPING_TAG,
            unit_start=subtitles.PARSE_TARGET_START,
            unit_end=subtitles.PARSE_TARGET_END,
        )
        source_unit_rows = [
            row for row in source_parsed.descriptors
            if subtitles.SOURCE_UNIT_TARGET_START
            <= row.target
            < subtitles.SOURCE_UNIT_TARGET_END
        ]
        source_general_rows = [
            row for row in source_parsed.descriptors
            if subtitles.SOURCE_GENERAL_TARGET_START
            <= row.target
            < subtitles.SOURCE_GENERAL_TARGET_END
        ]
        self.assertEqual((len(source_unit_rows), len(source_general_rows)), (7, 155))

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
            self.assertEqual(built["safety"]["native_unit_fallback_count"], 7)
            self.assertEqual(built["safety"]["relative_object2_descriptor_count"], 155)
            self.assertTrue(built["safety"]["loader_relocated_runtime_operands"])

            candidate_exe = (output_dir / "HEROES2.EXE").read_bytes()
            candidate_bank = (output_dir / "KOREAN.BIN").read_bytes()
            parsed_bank = subtitles.parse_bank(
                candidate_bank,
                expected_mapping_tag=subtitles.MAPPING_TAG,
                unit_start=subtitles.PORTABLE_GENERAL_TARGET_START,
                unit_end=subtitles.PORTABLE_GENERAL_TARGET_END,
            )
            self.assertEqual((len(parsed_bank.descriptors), len(parsed_bank.render_rows)), (173, 18))
            direct_rows = [
                row for row in parsed_bank.descriptors
                if not subtitles.token_allowed(row.target)
            ]
            self.assertEqual(len(direct_rows), subtitles.PORTABLE_GENERAL_DESCRIPTOR_COUNT)
            self.assertTrue(
                all(
                    subtitles.PORTABLE_GENERAL_TARGET_START
                    <= row.target
                    < subtitles.PORTABLE_GENERAL_TARGET_END
                    for row in direct_rows
                )
            )
            self.assertEqual(
                [(row.target, row.expected, row.encoded) for row in direct_rows],
                [
                    (
                        row.target - subtitles.OBJECT2_ACTUAL_BASE,
                        (row.expected - row.target) & 0xFFFFFFFF,
                        row.encoded,
                    )
                    for row in source_general_rows
                ],
            )
            self.assertFalse(
                any(
                    subtitles.SOURCE_UNIT_TARGET_START
                    <= row.target
                    < subtitles.SOURCE_UNIT_TARGET_END
                    for row in parsed_bank.descriptors
                )
            )
            token_targets = {
                row.target for row in parsed_bank.descriptors
                if subtitles.token_allowed(row.target)
            }
            self.assertIn(subtitles.CUE_TOKEN, token_targets)
            self.assertIn(subtitles.CODE_TOKEN, token_targets)

            source_image = subtitles.LeImage(source_exe_bytes)
            bootstrap = subtitles.build_stable_refresh_bootstrap(
                subtitles.D_BOOTSTRAP_RUNTIME_PAYLOAD_LENGTH,
                subtitles.RUNTIME_XOR_KEY,
            )
            specs = subtitles.build_executable_fixup_specs(source_exe_bytes, source_image, bootstrap)
            self.assertEqual((len(specs), len(set(specs))), (37, 37))
            self.assertTrue(all(spec.src == 7 for spec in specs))
            for expected in (
                subtitles.FixupSpec(1, 0x8E914, 3, 0x3F2C, 7),
                subtitles.FixupSpec(1, 0x8E91A, 3, 0x3ED4, 7),
                subtitles.FixupSpec(1, 0x91F5A, 3, 0x3F46, 7),
                subtitles.FixupSpec(3, 0x3F41, 1, 0xC4FF0, 7),
                subtitles.FixupSpec(3, 0x3F5C, 1, subtitles.DESCRIPTOR_VALIDATOR_OBJECT_OFFSET, 7),
            ):
                self.assertIn(expected, specs)
            self.assertIn(
                subtitles.FixupSpec(
                    1,
                    subtitles.DESCRIPTOR_VALIDATOR_O2_BASE_FIXUP_SOURCE,
                    2,
                    0,
                    7,
                ),
                specs,
            )
            self.assertIn(
                subtitles.FixupSpec(
                    1,
                    subtitles.DESCRIPTOR_VALIDATOR_SLOT_FIXUP_SOURCE,
                    3,
                    0x3E98,
                    7,
                ),
                specs,
            )
            candidate_fixups = subtitles.parse_raw_fixups(
                candidate_exe,
                subtitles.LeImage(candidate_exe),
                expected_rows=subtitles.SOURCE_FIXUP_ROWS + 37,
            )
            spec_keys = {
                (spec.source_object, spec.source_offset, spec.target_object, spec.target_offset, spec.src)
                for spec in specs
            }
            installed = [
                row for row in candidate_fixups
                if (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src)
                in spec_keys
            ]
            self.assertEqual(len(installed), 37)
            self.assertEqual(
                {
                    (row.source_object, row.source_offset, row.target_object, row.target_offset, row.src)
                    for row in installed
                },
                spec_keys,
            )

            # Pin the original five cross-object edges before confirming that
            # the candidate contains no cross-object rel32 transfer at all.
            expected_rel32 = {
                (1, 0xBED4C): bytes.fromhex("DC 51 EA FF"),
                (1, 0xC4F7D): bytes.fromhex("53 EF E9 FF"),
                (1, 0xC4F86): bytes.fromhex("BB EF E9 FF"),
                (3, 0x3F41): bytes.fromhex("AB 10 16 00"),
                (3, 0x3F5B): bytes.fromhex("41 AE 15 00"),
            }
            for source_offset, target_object, target_offset, source_object in subtitles.H2K3_RELATIVE_RELOCS:
                source_file = source_image.object_to_file(source_object, source_offset)
                raw = source_exe_bytes[source_file:source_file + 4]
                self.assertEqual(raw, expected_rel32[(source_object, source_offset)])
                displacement = int.from_bytes(raw, "little", signed=True)
                self.assertEqual(
                    subtitles._object_observed_actual_base(source_object) + source_offset + 4 + displacement,
                    subtitles._object_observed_actual_base(target_object) + target_offset,
                )

            candidate_image = subtitles.LeImage(candidate_exe)
            for source_offset, _opcode, veneer_offset, _target_object, _target_offset in subtitles.H2K3_O1_EDGE_VENEERS:
                source_file = candidate_image.object_to_file(1, source_offset)
                displacement = int.from_bytes(candidate_exe[source_file:source_file + 4], "little", signed=True)
                self.assertEqual(source_offset + 4 + displacement, veneer_offset)
            for name, expected in (
                ("h2k3_veneer_cave_a", subtitles.build_h2k3_portable_veneers()[0]),
                ("h2k3_veneer_cave_b", subtitles.build_h2k3_portable_veneers()[1]),
                ("h2k3_o3_portable", subtitles.build_h2k3_o3_portable_patch()),
            ):
                file_offset, length = subtitles._patch_file_ranges(candidate_exe, candidate_image)[name]
                self.assertEqual(candidate_exe[file_offset:file_offset + length], expected)

            verified = subtitles.verify_command(source_exe, source_bank, output_dir)
            self.assertTrue(verified["verified"])


if __name__ == "__main__":
    unittest.main()
