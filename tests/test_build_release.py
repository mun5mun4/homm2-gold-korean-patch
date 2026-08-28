#!/usr/bin/env python3
"""Release-builder contracts for deterministic non-font AGG corrections."""

from __future__ import annotations

import struct
import unittest
from pathlib import Path
from unittest import mock

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
    def test_beta10_core_targets_are_pinned(self) -> None:
        self.assertEqual(
            release.PINNED_BETA10_TARGETS,
            {
                Path("HEROES2.EXE"): {
                    "size": 1_523_420,
                    "sha256": "87B175EF0698C65893BAF6A0581E74BEA60CCECA0D8DF57E9DF7614B27DB2365",
                },
                Path("KOREAN.BIN"): {
                    "size": 36_159,
                    "sha256": "37FDC1F372627E7B637EEEBFC15610E26B427E66947D7AA699B46B807F7338DA",
                },
            },
        )

    def test_builder_rejects_beta9_before_reading_inputs(self) -> None:
        with self.assertRaisesRegex(release.BuildError, "pinned to v0.9.0-beta.10"):
            release.build(
                Path("missing-original"),
                Path("missing-patched"),
                Path("missing-output"),
                "v0.9.0-beta.9",
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
            (
                "v0.9.0-beta.7",
                "upgrades/v0.9.0-beta.7-manifest.json",
                {"size": 33_369, "sha256": "F71C83895BDC3581F1C8BA4BC7919153E14F0500831D941DAE9B34D17519E2CE"},
            ),
            (
                "v0.9.0-beta.8",
                "upgrades/v0.9.0-beta.8-manifest.json",
                {"size": 33_656, "sha256": "A6D0DC07FD27ADC73D3925C76CFBC01CBFE7B6727029EACD87A570132E5B5BB5"},
            ),
            (
                "v0.9.0-beta.9",
                "upgrades/v0.9.0-beta.9-manifest.json",
                {"size": 34_263, "sha256": "CEB8E7D765DBFA2FBB6D955364E68A0D2A158B31BDA7DA70C1F04A85C37AEBDD"},
            ),
        )

        self.assertEqual(release.CURRENT_VERSION, "v0.9.0-beta.10")
        self.assertEqual(release.RELEASE_DATE, "2026-08-28")
        self.assertEqual(len(release.UPGRADE_RELEASES), len(expected))
        for upgrade, (version, manifest_path, identity) in zip(release.UPGRADE_RELEASES, expected):
            with self.subTest(version=version):
                self.assertEqual(upgrade["version"], version)
                self.assertEqual(upgrade["manifest_path"].as_posix(), manifest_path)
                self.assertEqual(upgrade["manifest"], identity)
                raw = (release.ASSETS / upgrade["manifest_path"]).read_bytes()
                self.assertEqual(release.digest(raw), identity)

    def test_font_generation_v2_pins_iropke_default_and_nanum_fallback(self) -> None:
        mapping = b"mapping"
        default_font = b"iropke"
        fallback_font = b"nanum"

        manifest = release.font_generation_manifest(mapping, default_font, fallback_font)

        self.assertEqual(manifest["schema"], "homm2-font-generation-v2")
        self.assertEqual(
            manifest["default_font"],
            {
                "name": "Iropke Batang Medium",
                "package_path": "fonts/IropkeBatangM.ttf",
                "package": release.digest(default_font),
                "face_index": 0,
                "license_path": "THIRD_PARTY_LICENSES/IROPKE_BATANG_OFL.txt",
            },
        )
        self.assertEqual(
            manifest["fallback_font"],
            {
                "name": "NanumGothicCoding Regular",
                "package_path": "fonts/NanumGothicCoding-Regular.ttf",
                "package": release.digest(fallback_font),
                "face_index": 0,
                "license_path": "THIRD_PARTY_LICENSES/NANUM_GOTHIC_CODING_OFL.txt",
            },
        )
        self.assertEqual(
            release.PINNED_DEFAULT_FONT,
            {
                "size": 3_202_516,
                "sha256": "5910F97BAED6C6E0B8538E40D326B169E0A510357E20DD9003ABABCE2CE1CC69",
            },
        )
        self.assertEqual(
            release.PINNED_FALLBACK_FONT,
            {
                "size": 2_315_924,
                "sha256": "787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089",
            },
        )

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


class DynamicFontAggContractTests(unittest.TestCase):
    def test_explicit_archive_contracts_cover_every_dynamic_raster(self) -> None:
        release.validate_dynamic_font_agg_contracts()
        heroes2_expected, heroes2_keep = release.font_agg_contract(Path("DATA/HEROES2.AGG"))
        heroes2x_expected, heroes2x_keep = release.font_agg_contract(Path("DATA/HEROES2X.AGG"))

        self.assertEqual(len(release.HEROES2_DYNAMIC_FONT_RESOURCES), 67)
        self.assertEqual(len(release.HEROES2X_DYNAMIC_FONT_RESOURCES), 6)
        self.assertEqual(len(heroes2_expected), 67 + len(release.HEROES2_LOCALIZED_BIN_RESOURCES))
        self.assertEqual(set(heroes2_keep), set(release.HEROES2_LOCALIZED_BIN_RESOURCES))
        self.assertEqual(
            set(heroes2_expected),
            set(release.HEROES2_DYNAMIC_FONT_RESOURCES) | set(heroes2_keep),
        )
        self.assertEqual(tuple(heroes2x_expected), release.HEROES2X_DYNAMIC_FONT_RESOURCES)
        self.assertEqual(heroes2x_keep, ())

        protected = set(release.ORIGINAL_MENU_AND_CAMPAIGN_BACKGROUND_RESOURCES)
        self.assertEqual(
            protected,
            {"BTNSHNGL.ICN", "HEROES.ICN", "CAMPBKGG.ICN", "CAMPBKGE.ICN", "X_CMPBKG.ICN"},
        )
        self.assertTrue(protected.isdisjoint(heroes2_expected))
        self.assertTrue(protected.isdisjoint(heroes2x_expected))

    def test_font_free_bases_keep_only_the_localized_bin_allowlist(self) -> None:
        for relative in release.FONT_AGG_PATHS:
            with self.subTest(relative=relative.as_posix()):
                expected, keep = release.font_agg_contract(relative)
                resources = tuple((name, f"original:{name}".encode("ascii")) for name in expected) + (
                    ("UNCHANGED.BIN", b"unchanged"),
                )
                original = make_agg(resources)
                archive = font.parse_agg(original, label=f"{relative}:fixture-original")
                patched = font.repack_agg(
                    archive,
                    {name: f"patched:{name}".encode("ascii") for name in expected},
                )

                base = font.make_localized_font_base(
                    original,
                    patched,
                    keep_localized_resources=keep,
                    expected_patched_changes=expected,
                    label=f"{relative}:fixture",
                )

                self.assertEqual(
                    set(font.changed_agg_resources(original, patched, label=f"{relative}:patched")),
                    set(expected),
                )
                self.assertEqual(
                    set(font.changed_agg_resources(original, base, label=f"{relative}:base")),
                    set(keep),
                )
                original_archive = font.parse_agg(original, label=f"{relative}:original-check")
                patched_archive = font.parse_agg(patched, label=f"{relative}:patched-check")
                base_archive = font.parse_agg(base, label=f"{relative}:base-check")
                for name in expected:
                    if name in keep:
                        self.assertEqual(base_archive.get(name).payload, patched_archive.get(name).payload)
                    else:
                        self.assertEqual(base_archive.get(name).payload, original_archive.get(name).payload)

    def test_contract_fails_closed_when_explicit_allowlist_loses_a_resource(self) -> None:
        incomplete = release.HEROES2_DYNAMIC_FONT_RESOURCES[:-1]
        with mock.patch.object(release, "HEROES2_DYNAMIC_FONT_RESOURCES", incomplete):
            with self.assertRaisesRegex(release.BuildError, "HEROES2 dynamic font allowlist drifted"):
                release.font_agg_contract(Path("DATA/HEROES2.AGG"))

    def test_contract_fails_closed_when_a_localizer_declares_a_new_target(self) -> None:
        undeclared = dict(font.IMAGE_UI_TEXT_TARGETS[0])
        undeclared["resource"] = "UNDECLARED.ICN"
        targets = font.IMAGE_UI_TEXT_TARGETS + (undeclared,)
        with mock.patch.object(font, "IMAGE_UI_TEXT_TARGETS", targets):
            with self.assertRaisesRegex(release.BuildError, "image UI source/output/target resource declarations drifted"):
                release.font_agg_contract(Path("DATA/HEROES2.AGG"))


if __name__ == "__main__":
    unittest.main()
