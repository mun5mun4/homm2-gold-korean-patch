#!/usr/bin/env python3
"""Portable contract tests for the pinned final hotfix tools."""

from __future__ import annotations

import struct
import subprocess
import sys
import unittest
from pathlib import Path

from tools.localization import final_bank_hotfix as bank
from tools.localization import final_text_hotfix as exe


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "translations" / "font" / "mapping874.fixed-interface-font.txt"


class FinalHotfixContractTests(unittest.TestCase):
    def test_exe_patch_ranges_and_rel32_targets(self) -> None:
        ranges = []
        changed = 0
        by_key = {patch.key: patch for patch in exe.PATCHES}
        for patch in exe.PATCHES:
            self.assertEqual(len(patch.before), len(patch.after), patch.key)
            ranges.append((patch.offset, patch.offset + len(patch.before)))
            changed += sum(left != right for left, right in zip(patch.before, patch.after))
        ranges.sort()
        self.assertTrue(all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:])))
        self.assertEqual(changed, exe.CHANGED_BYTE_COUNT)

        expected_targets = {
            "wrapped_renderer_hook_to_h2k3_resolver": 0x133C01,
            "startup_main_call_to_h2k3_loader": 0x139DDC,
            "h2k3_loader_tail_to_game_main": 0xE0077,
        }
        for key, target in expected_targets.items():
            patch = by_key[key]
            self.assertIn(patch.after[0], (0xE8, 0xE9))
            displacement = struct.unpack_from("<i", patch.after, 1)[0]
            self.assertEqual(patch.offset + 5 + displacement, target)

        helper_ranges = (
            struct.unpack("<I", by_key["h2k3_helper_first_range_start_unit"].after)[0],
            struct.unpack("<I", by_key["h2k3_helper_first_range_end_unit"].after)[0],
            struct.unpack("<I", by_key["h2k3_helper_second_range_start_general"].after)[0],
            struct.unpack("<I", by_key["h2k3_helper_second_range_end_general"].after)[0],
        )
        self.assertEqual(
            helper_ranges,
            (
                bank.UNIT_TARGET_START,
                bank.UNIT_TARGET_END,
                bank.TARGET_GENERAL_TARGET_START,
                bank.TARGET_GENERAL_TARGET_END,
            ),
        )

    def test_wrong_exe_identity_fails_closed(self) -> None:
        with self.assertRaises(exe.HotfixError):
            exe.transform(bytes(32))

    def test_mapping_and_followers_format_contracts(self) -> None:
        mapping = bank.load_mapping(MAPPING.read_bytes())
        self.assertEqual(len(mapping), 874)
        self.assertEqual(len(set(mapping.values())), 874)
        bank.validate_followers_format(bank.FOLLOWERS_BEFORE)
        bank.validate_followers_format(bank.FOLLOWERS_AFTER)
        for malformed in ("no token", "%s and %s", "%d", "%s %d"):
            with self.assertRaises(bank.BankHotfixError):
                bank.validate_followers_format(malformed)

        fallback = {patch.key: patch for patch in exe.PATCHES}["followers_direct_fallback"]
        self.assertEqual(len(fallback.before), 93)
        self.assertEqual(len(fallback.after), 93)
        self.assertEqual(fallback.after.count(b"%s"), 1)
        self.assertTrue(fallback.after.endswith(bytes(7)))

    def test_runtime_rebased_bank_contract(self) -> None:
        self.assertEqual(
            bank.EXPECTED_GENERAL_DESCRIPTOR_COUNT
            + bank.EXPECTED_UNIT_DESCRIPTOR_COUNT
            + bank.EXPECTED_TOKEN_DESCRIPTOR_COUNT,
            bank.EXPECTED_DESCRIPTOR_COUNT,
        )
        self.assertEqual(
            bank.TARGET_GENERAL_TARGET_START,
            bank.SOURCE_GENERAL_TARGET_START + bank.RUNTIME_REBASE,
        )
        self.assertEqual(
            bank.TARGET_GENERAL_TARGET_END,
            bank.SOURCE_GENERAL_TARGET_END + bank.RUNTIME_REBASE,
        )
        self.assertEqual(bank.FOLLOWERS_TARGET, bank.FOLLOWERS_SOURCE_TARGET + bank.RUNTIME_REBASE)
        self.assertEqual(bank.FOLLOWERS_EXPECTED, bank.FOLLOWERS_SOURCE_EXPECTED + bank.RUNTIME_REBASE)

    def test_bank_allowlist_gap_and_short_input_fail_closed(self) -> None:
        self.assertTrue(bank.direct_target_allowed(bank.SOURCE_GENERAL_TARGET_START))
        self.assertTrue(bank.direct_target_allowed(bank.TARGET_GENERAL_TARGET_START, rebased=True))
        self.assertTrue(bank.direct_target_allowed(bank.UNIT_TARGET_START))
        self.assertFalse(bank.direct_target_allowed(bank.SOURCE_GENERAL_TARGET_END))
        self.assertFalse(bank.direct_target_allowed(bank.TARGET_GENERAL_TARGET_END, rebased=True))
        self.assertFalse(bank.direct_target_allowed(0x00200000))
        self.assertFalse(bank.direct_target_allowed(bank.UNIT_TARGET_START + 1))
        with self.assertRaises(bank.BankHotfixError):
            bank.parsed_bank(b"")
        with self.assertRaises(bank.BankHotfixError):
            bank.transform(b"", MAPPING.read_bytes())

    def test_bank_tool_supports_direct_and_module_help(self) -> None:
        direct = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "localization" / "final_bank_hotfix.py"), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        module = subprocess.run(
            [sys.executable, "-m", "tools.localization.final_bank_hotfix", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(module.returncode, 0, module.stderr)


if __name__ == "__main__":
    unittest.main()
