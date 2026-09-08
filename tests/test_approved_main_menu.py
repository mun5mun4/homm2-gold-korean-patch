"""Approved-menu delta contracts; copyrighted fixtures stay on the local PC."""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.release import approved_main_menu as menu
from tools.release import homm2_font as font


ORIGINAL_AGG_ENV = "HOMM2_TEST_GOG_ORIGINAL_AGG"


def make_agg(resources):
    entries = tuple(
        font.AggEntry(
            index=index, name=name, name_slot=name.encode("ascii").ljust(font.AGG_NAME_SIZE, b"\0"),
            hash_word=font.agg_filename_hash(name), payload=payload,
        )
        for index, (name, payload) in enumerate(resources)
    )
    return font.repack_agg(font.AggArchive(entries, b""), {})


class ApprovedMenuContracts(unittest.TestCase):
    def test_repository_contains_only_three_validated_deltas_and_metadata(self):
        expected_files = {spec["delta_path"] for spec in menu.RESOURCE_SPECS} | {"identities.json"}
        self.assertEqual({entry.name for entry in menu.DATA_DIRECTORY.iterdir()}, expected_files)
        deltas = menu.load_deltas()
        self.assertEqual(set(deltas), {
            ("HEROES2.AGG", "BTNSHNGL.ICN"), ("HEROES2.AGG", "HEROES.ICN"), ("HEROES2X.AGG", "HEROES.ICN"),
        })
        self.assertTrue(all(raw.startswith(b"BSDIFF40") for raw in deltas.values()))

    def test_corrupt_delta_is_rejected_before_application(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "menu"
            shutil.copytree(menu.DATA_DIRECTORY, directory)
            path = directory / menu.RESOURCE_SPECS[0]["delta_path"]
            raw = bytearray(path.read_bytes())
            raw[-1] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(menu.MainMenuError, "checksum mismatch"):
                menu.load_deltas(directory)

    def test_manifest_cannot_redirect_delta_or_replace_approved_identity(self):
        for key in ("path", "target"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary) / "menu"
                shutil.copytree(menu.DATA_DIRECTORY, directory)
                path = directory / "identities.json"
                document = json.loads(path.read_text())
                if key == "path":
                    document["resources"][0]["delta"]["path"] = "../outside.bsdiff"
                else:
                    document["resources"][0]["target"]["sha256"] = "0" * 64
                path.write_text(json.dumps(document))
                with self.assertRaises(menu.MainMenuError):
                    menu.load_deltas(directory)

    def fixture_sprite(self):
        return font._DecodedSprite(4, 7, 4, 4, 0, bytes([60] * 16), bytes(16))

    def test_geometry_transparency_and_pixels_outside_face_are_protected(self):
        original = self.fixture_sprite()
        outside = bytearray(original.pixels)
        outside[0] = 120
        fixtures = (
            (replace(original, offset_x=5), "geometry"),
            (replace(original, transform=b"\1" + original.transform[1:]), "transparency"),
            (replace(original, pixels=bytes(outside)), "outside approved menu face"),
        )
        for candidate, message in fixtures:
            with self.subTest(message=message), self.assertRaisesRegex(menu.MainMenuError, message):
                menu.validate_sprite_changes(original, candidate, ((1, 1, 2, 2),), label="synthetic")

    def test_every_cycling_color_is_rejected_but_static_tail_colors_are_allowed(self):
        original = self.fixture_sprite()
        for index in (214, 215, 216, 217, 218, 219, 220, 221, 231, 232, 233, 234, 235, 238, 239, 240, 241):
            pixels = bytearray(original.pixels)
            pixels[5] = index
            with self.subTest(index=index), self.assertRaisesRegex(menu.MainMenuError, "cycling palette"):
                menu.validate_sprite_changes(original, replace(original, pixels=bytes(pixels)), ((1, 1, 2, 2),), label="synthetic")
        for index in (120, 229, 230, 236, 237):
            pixels = bytearray(original.pixels)
            pixels[5] = index
            menu.validate_sprite_changes(original, replace(original, pixels=bytes(pixels)), ((1, 1, 2, 2),), label="synthetic")

    def test_background_keeps_existing_animation_but_buttons_cannot_have_it(self):
        original = replace(self.fixture_sprite(), pixels=bytes([221] + [60] * 15))
        menu.validate_sprite_changes(original, original, ((1, 1, 2, 2),), label="background")
        with self.assertRaisesRegex(menu.MainMenuError, "cycling palette"):
            menu.validate_sprite_changes(original, original, ((1, 1, 2, 2),), label="button", all_visible_pixels_static=True)


@unittest.skipUnless(os.environ.get(ORIGINAL_AGG_ENV), f"set {ORIGINAL_AGG_ENV} to a local original HEROES2.AGG")
class LocalOriginalMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_root = Path(os.environ[ORIGINAL_AGG_ENV]).resolve().parent.parent
        cls.resources = menu.reconstruct_resources(cls.original_root)

    def test_original_deltas_reproduce_pinned_approved_artwork_and_all_state_invariants(self):
        # Reconstruction verifies all 20 sprite layouts, transforms, face
        # bounds, static palette colors and both embedded default backgrounds.
        for spec in menu.RESOURCE_SPECS:
            self.assertEqual(menu.identity(self.resources[spec["archive"]][spec["resource"]]), spec["target"])

    def test_application_preserves_unrelated_localizations_and_is_idempotent(self):
        for archive_name, resource_names in menu.ARCHIVE_RESOURCES.items():
            with self.subTest(archive=archive_name):
                original = font.parse_agg((self.original_root / "DATA" / archive_name).read_bytes(), label="local original")
                entries = [(name, original.get(name).payload) for name in resource_names]
                entries.extend((("FONT.ICN", b"custom font fixture"), ("TRANSLAT.BIN", b"latest translation fixture")))
                before_raw = make_agg(entries)
                after_raw = menu.apply_to_archive(before_raw, archive_name, self.resources)
                before = font.parse_agg(before_raw, label="before")
                after = font.parse_agg(after_raw, label="after")
                self.assertEqual(menu.apply_to_archive(after_raw, archive_name, self.resources), after_raw)
                self.assertEqual(set(font.changed_agg_resources(before_raw, after_raw, label="overlay")), set(resource_names))
                for name in ("FONT.ICN", "TRANSLAT.BIN"):
                    self.assertEqual(after.get(name).payload, before.get(name).payload)

    def test_unknown_existing_menu_is_rejected_instead_of_overwritten(self):
        original = font.parse_agg((self.original_root / "DATA/HEROES2.AGG").read_bytes(), label="original")
        corrupt = bytearray(original.get("BTNSHNGL.ICN").payload)
        corrupt[-1] ^= 1
        altered = make_agg((("BTNSHNGL.ICN", bytes(corrupt)), ("HEROES.ICN", original.get("HEROES.ICN").payload)))
        with self.assertRaisesRegex(menu.MainMenuError, "unknown existing menu"):
            menu.apply_to_archive(altered, "HEROES2.AGG", self.resources)


if __name__ == "__main__":
    unittest.main()
