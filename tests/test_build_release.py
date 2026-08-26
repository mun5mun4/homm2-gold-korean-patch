#!/usr/bin/env python3
"""Release-builder contracts for deterministic non-font AGG corrections."""

from __future__ import annotations

import struct
import unittest
from pathlib import Path

from tools.release import build_release as release
from tools.release import homm2_font as font


def make_agg(resources: tuple[tuple[str, bytes], ...]) -> bytes:
    entries = tuple(
        font.AggEntry(
            index=index,
            name=name,
            name_slot=name.encode("ascii").ljust(font.AGG_NAME_SIZE, b"\0"),
            hash_word=font.agg_filename_hash(name),
            payload=payload,
        )
        for index, (name, payload) in enumerate(resources)
    )
    return font.repack_agg(font.AggArchive(entries, b""), {})


def herowind_payload(text: bytes = release.HEROWIND_KNOWLEDGE_ENGLISH) -> bytes:
    payload = bytearray((index * 17 + 3) & 0xFF for index in range(431))
    payload[release.HEROWIND_LENGTH_OFFSET : release.HEROWIND_TEXT_OFFSET] = b"\x0A\x00"
    payload[
        release.HEROWIND_TEXT_OFFSET : release.HEROWIND_TEXT_OFFSET + release.HEROWIND_TEXT_SIZE
    ] = text
    return bytes(payload)


class HerowindKnowledgeTests(unittest.TestCase):
    def test_beta7_core_targets_are_pinned(self) -> None:
        self.assertEqual(
            release.PINNED_BETA7_TARGETS,
            {
                Path("HEROES2.EXE"): {
                    "size": 1_523_420,
                    "sha256": "B5416C793354122762B67973ACF86D985C8B5ACA26B74F29FE62E707E7A1548C",
                },
                Path("KOREAN.BIN"): {
                    "size": 36_265,
                    "sha256": "95EA660215425E34FCB7CFD37405F8D1869845EB2EAED245613D2FF8AAE1D20A",
                },
            },
        )

    def test_builder_rejects_a_non_beta7_version_before_reading_inputs(self) -> None:
        with self.assertRaisesRegex(release.BuildError, "pinned to v0.9.0-beta.7"):
            release.build(
                Path("missing-original"),
                Path("missing-patched"),
                Path("missing-output"),
                "v0.9.0-beta.5",
                None,
            )

    def test_frozen_upgrade_manifests_match_published_identities(self) -> None:
        expected = (
            (
                "v0.9.0-beta.4",
                "upgrades/v0.9.0-beta.4-manifest.json",
                {"size": 31_988, "sha256": "D623C611962CE7F94CC3806DA81B00EDAD7809FB87E489001FE9F0ADF39BAC60"},
            ),
            (
                "v0.9.0-beta.5",
                "upgrades/v0.9.0-beta.5-manifest.json",
                {"size": 32_845, "sha256": "A9A402E1BD5A8ECD856EABA70BA2F88A828D42F68D37E6F2B82BF7659991B05F"},
            ),
            (
                "v0.9.0-beta.6",
                "upgrades/v0.9.0-beta.6-manifest.json",
                {"size": 33_107, "sha256": "32E731E43E6D00773867AF89A1BB0C0415099B69359B39C98153CE025279537C"},
            ),
        )

        self.assertEqual(release.CURRENT_VERSION, "v0.9.0-beta.7")
        self.assertEqual(len(release.UPGRADE_RELEASES), len(expected))
        for upgrade, (version, manifest_path, identity) in zip(release.UPGRADE_RELEASES, expected):
            with self.subTest(version=version):
                self.assertEqual(upgrade["version"], version)
                self.assertEqual(upgrade["manifest_path"].as_posix(), manifest_path)
                self.assertEqual(upgrade["manifest"], identity)
                raw = (release.ASSETS / upgrade["manifest_path"]).read_bytes()
                self.assertEqual(release.digest(raw), identity)

    def test_payload_changes_only_fixed_ten_byte_allocation_and_is_idempotent(self) -> None:
        original = herowind_payload()
        localized = release.localize_herowind_knowledge_payload(original, label="fixture")
        text_end = release.HEROWIND_TEXT_OFFSET + release.HEROWIND_TEXT_SIZE

        self.assertEqual(len(localized), len(original))
        self.assertEqual(localized[: release.HEROWIND_TEXT_OFFSET], original[: release.HEROWIND_TEXT_OFFSET])
        self.assertEqual(localized[release.HEROWIND_TEXT_OFFSET : text_end], release.HEROWIND_KNOWLEDGE_KOREAN)
        self.assertEqual(localized[text_end:], original[text_end:])
        self.assertEqual(
            localized[release.HEROWIND_LENGTH_OFFSET : release.HEROWIND_TEXT_OFFSET],
            b"\x0A\x00",
        )
        self.assertEqual(release.localize_herowind_knowledge_payload(localized, label="fixture-again"), localized)

    def test_payload_rejects_wrong_length_word_or_unknown_contents(self) -> None:
        wrong_length = bytearray(herowind_payload())
        wrong_length[release.HEROWIND_LENGTH_OFFSET : release.HEROWIND_TEXT_OFFSET] = b"\x09\x00"
        with self.assertRaises(release.BuildError):
            release.localize_herowind_knowledge_payload(bytes(wrong_length), label="wrong-length")

        with self.assertRaises(release.BuildError):
            release.localize_herowind_knowledge_payload(herowind_payload(b"Unexpected"), label="unknown")

    def test_agg_changes_only_herowind_payload_bytes_and_preserves_every_entry(self) -> None:
        original = make_agg(
            (
                ("FIRST.BIN", b"first-payload"),
                (release.HEROWIND_RESOURCE_NAME, herowind_payload()),
                ("LAST.ICN", b"last-payload"),
            )
        )
        before = font.parse_agg(original, label="fixture-before")
        herowind = before.get(release.HEROWIND_RESOURCE_NAME)
        _, payload_offset, payload_size = struct.unpack_from(
            "<III", original, 2 + herowind.index * font.AGG_ENTRY_SIZE
        )
        self.assertEqual(payload_size, len(herowind.payload))

        localized = release.localize_herowind_knowledge_agg(original, label="fixture")
        absolute_text_offset = payload_offset + release.HEROWIND_TEXT_OFFSET
        absolute_text_end = absolute_text_offset + release.HEROWIND_TEXT_SIZE
        expected = (
            original[:absolute_text_offset]
            + release.HEROWIND_KNOWLEDGE_KOREAN
            + original[absolute_text_end:]
        )

        self.assertEqual(localized, expected)
        self.assertEqual(
            font.changed_agg_resources(original, localized, label="fixture-diff"),
            (release.HEROWIND_RESOURCE_NAME,),
        )
        after = font.parse_agg(localized, label="fixture-after")
        for old, new in zip(before.entries, after.entries):
            self.assertEqual(
                (old.index, old.name, old.name_slot, old.hash_word),
                (new.index, new.name, new.name_slot, new.hash_word),
            )
            if old.name.upper() != release.HEROWIND_RESOURCE_NAME:
                self.assertEqual(new.payload, old.payload)

        self.assertEqual(release.localize_herowind_knowledge_agg(localized, label="fixture-again"), localized)

    def test_main_agg_release_contract_keeps_herowind(self) -> None:
        expected_changes, keep = release.font_agg_contract(Path("DATA/HEROES2.AGG"))

        self.assertIn(release.HEROWIND_RESOURCE_NAME, keep)
        self.assertIn(release.HEROWIND_RESOURCE_NAME, expected_changes)
        self.assertEqual(keep.count(release.HEROWIND_RESOURCE_NAME), 1)


if __name__ == "__main__":
    unittest.main()
