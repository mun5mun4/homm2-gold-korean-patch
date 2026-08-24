#!/usr/bin/env python3
"""Fast contracts for dynamic HoMM2 font and AGG generation."""

from __future__ import annotations

import unittest
import shutil
import tempfile
from unittest import mock
from pathlib import Path

from tools.release import homm2_font as font


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "translations" / "font" / "mapping874.fixed-interface-font.txt"
DEFAULT_FONT = ROOT / "packaging" / "release_assets" / "fonts" / "NanumGothicCoding-Regular.ttf"
LOCAL_GOG_ORIGINAL_AGG = (
    ROOT.parent.parent / "_codex_probe" / "release_staging" / "originals" / "DATA" / "HEROES2.AGG"
)

LOCALIZED_BIN_RESOURCES = (
    "THIEFWIN.BIN",
    "WELLWIND.BIN",
    "RECRUIT0.BIN",
    "RECRUIT1.BIN",
    "RECRUIQ0.BIN",
    "RECRUIQ1.BIN",
    "TRADPOST.BIN",
)
RESTORED_UI_ICN_RESOURCES = (
    "SYSTEM.ICN",
    "REQUEST.ICN",
    "REQUESTS.ICN",
    "SYSTEME.ICN",
)
EXPECTED_MAIN_AGG_CHANGES = (
    *font.FONT_RESOURCE_NAMES,
    *LOCALIZED_BIN_RESOURCES,
    *RESTORED_UI_ICN_RESOURCES,
)


def make_sprite(value: int, *, offset_x: int = 0) -> font.Sprite:
    """Return a valid opaque 1x1 ICN sprite with a distinguishable payload."""

    return font.Sprite(offset_x, 0, 1, 1, 0, b"\x01" + bytes([value]) + b"\x00\x80")


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


def legacy_icn(seed: int) -> bytes:
    sprites = tuple(make_sprite((seed + index) % 255 + 1, offset_x=index) for index in range(font.LEGACY_SPRITE_COUNT))
    return font.pack_icn(sprites)


def opaque_points(sprite: font.Sprite) -> tuple[tuple[int, int, int], ...]:
    """Decode opaque ICN pixels into logical-cell coordinates."""

    position = 0
    points: list[tuple[int, int, int]] = []
    for y in range(sprite.height):
        x = 0
        while True:
            command = sprite.payload[position]
            position += 1
            if command == 0:
                break
            if command > 0x80:
                x += command - 0x80
                continue
            values = sprite.payload[position : position + command]
            position += command
            for value in values:
                points.append((sprite.offset_x + x, sprite.offset_y + y, value))
                x += 1
        if x != sprite.width:
            raise AssertionError("decoded sprite row width mismatch")
    if position + 1 != len(sprite.payload) or sprite.payload[position] != 0x80:
        raise AssertionError("decoded sprite terminator mismatch")
    return tuple(points)


class MappingAndDefaultFontTests(unittest.TestCase):
    def test_mapping_has_exact_874_slots_and_escape_formula(self) -> None:
        rows = font.parse_mapping(MAPPING)

        self.assertEqual(len(rows), font.KOREAN_GLYPH_COUNT)
        self.assertEqual(rows[0].index, 0x100)
        self.assertEqual((rows[0].lead, rows[0].trail), (0x82, 0x80))
        self.assertEqual(rows[-1].index, 0x469)
        self.assertEqual((rows[-1].lead, rows[-1].trail), (0x88, 0xE9))
        self.assertEqual(len({row.codepoint for row in rows}), font.KOREAN_GLYPH_COUNT)

        for row in rows:
            offset = row.index - font.KOREAN_FIRST_INDEX
            self.assertEqual(row.lead, 0x82 + (offset >> 7))
            self.assertEqual(row.trail, 0x80 + (offset & 0x7F))
            decoded_index = font.KOREAN_FIRST_INDEX + ((row.lead - 0x82) << 7) + (row.trail - 0x80)
            self.assertEqual(decoded_index, row.index)

        by_character = {row.character: row.index for row in rows}
        self.assertEqual("".join(character for character, _, _ in font.RECRUIT_COST_GLYPHS), font.RECRUIT_COST_LABEL)
        for character, index, korean in font.RECRUIT_COST_GLYPHS:
            self.assertEqual(by_character[character] if korean else ord(character) - 0x20, index)

    def test_default_nanum_font_covers_mapping_and_has_pinned_metadata(self) -> None:
        plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        metadata = plan.metadata()

        self.assertEqual(len(plan.mapping), font.KOREAN_GLYPH_COUNT)
        self.assertEqual(plan.primary_codepoints, frozenset(row.codepoint for row in plan.mapping))
        self.assertEqual(plan.fallback_codepoints, frozenset())
        self.assertIsNone(plan.fallback)
        self.assertEqual(metadata["mode"], "default")
        self.assertEqual(metadata["renderer"], font.RENDERER_ID)
        self.assertEqual(metadata["renderer"], "pillow-freetype-monochrome-v2-fixed-baseline")
        self.assertEqual(
            metadata["normal_cell"],
            {"width": font.NORMAL_CELL_WIDTH, "height": font.NORMAL_CELL_HEIGHT},
        )
        self.assertEqual(
            metadata["small_cell"],
            {"width": font.SMALL_CELL_WIDTH, "height": font.SMALL_CELL_HEIGHT},
        )
        self.assertEqual(metadata["shadow_offset"], [font.SHADOW_OFFSET_X, font.SHADOW_OFFSET_Y])
        self.assertEqual(metadata["baseline_policy"], font.BASELINE_POLICY)
        self.assertEqual(metadata["fit_policy"], font.FIT_POLICY)
        self.assertEqual(metadata["crop_policy"], font.CROP_POLICY)
        self.assertEqual(metadata["shadow_policy"], font.SHADOW_POLICY)
        self.assertEqual(metadata["mapping_glyph_count"], font.KOREAN_GLYPH_COUNT)
        self.assertEqual(metadata["primary_glyph_count"], font.KOREAN_GLYPH_COUNT)
        self.assertEqual(metadata["fallback_glyph_count"], 0)
        self.assertEqual(metadata["primary"]["file_name"], "NanumGothicCoding-Regular.ttf")
        self.assertEqual(metadata["primary"]["family"], "NanumGothicCoding")
        self.assertEqual(metadata["primary"]["subfamily"], "Regular")
        self.assertEqual(metadata["primary"]["face_count"], 1)
        self.assertEqual(metadata["primary"]["face_index"], 0)
        self.assertEqual(metadata["primary"]["size"], 2_315_924)
        self.assertEqual(
            metadata["primary"]["sha256"],
            "787EFFD7EFED2ABCA88ADE231FAA8191F4E9FCF85B1805A13EE1DC3724B72089",
        )
        self.assertIsNone(metadata["fallback"])

    def test_render_uses_inspected_font_bytes_after_source_disappears(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "selected-local-font.ttf"
            shutil.copyfile(DEFAULT_FONT, selected)
            plan = font.make_font_plan(MAPPING, selected, mode="custom")
            selected.unlink()

            rendered = font.render_font(plan)

        self.assertEqual(len(rendered.normal), font.KOREAN_GLYPH_COUNT)
        self.assertEqual(len(rendered.small), font.KOREAN_GLYPH_COUNT)
        self.assertEqual(rendered.metadata["primary"]["file_name"], "selected-local-font.ttf")


class DynamicFontCellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        cls.rendered = font.render_font(cls.plan)
        cls.offset_by_character = {
            row.character: row.index - font.KOREAN_FIRST_INDEX for row in cls.plan.mapping
        }
        characters = {row.codepoint: row.character for row in cls.plan.mapping}
        cls.normal_layout = font._build_face_layout(
            cls.plan.primary,
            characters,
            requested_pixel_size=font.NORMAL_PIXEL_SIZE,
            cell_width=font.NORMAL_CELL_WIDTH,
            cell_height=font.NORMAL_CELL_HEIGHT,
        )
        cls.small_layout = font._build_face_layout(
            cls.plan.primary,
            characters,
            requested_pixel_size=font.SMALL_PIXEL_SIZE,
            cell_width=font.SMALL_CELL_WIDTH,
            cell_height=font.SMALL_CELL_HEIGHT,
        )
        if cls.normal_layout is None or cls.small_layout is None:
            raise AssertionError("default face layout unexpectedly missing")

    def test_default_face_uses_the_largest_fitting_integer_size(self) -> None:
        self.assertEqual(self.normal_layout.resolved_pixel_size, 14)
        self.assertEqual(self.small_layout.resolved_pixel_size, 12)
        self.assertEqual(self.normal_layout.baseline_y, font.NORMAL_CELL_HEIGHT)
        self.assertEqual(self.small_layout.baseline_y, font.SMALL_CELL_HEIGHT)

        expected_keys = {
            "requested_pixel_size",
            "resolved_pixel_size",
            "cell_width",
            "cell_height",
            "origin_x",
            "baseline_y",
            "ink_union",
            "glyph_count",
            "foreground_clip_count",
            "shadow_edge_clip_count",
        }
        resolved = self.rendered.metadata["resolved_faces"]
        self.assertEqual(set(resolved), {"primary", "fallback"})
        self.assertIsNone(resolved["fallback"])
        self.assertEqual(set(resolved["primary"]["normal"]), expected_keys)
        self.assertEqual(set(resolved["primary"]["small"]), expected_keys)
        self.assertEqual(resolved["primary"]["normal"]["glyph_count"], font.KOREAN_GLYPH_COUNT)
        self.assertEqual(resolved["primary"]["small"]["glyph_count"], font.KOREAN_GLYPH_COUNT)
        self.assertEqual(resolved["primary"]["normal"]["foreground_clip_count"], 0)
        self.assertEqual(resolved["primary"]["small"]["foreground_clip_count"], 0)
        self.assertEqual(resolved["primary"]["normal"]["shadow_edge_clip_count"], 5_003)
        self.assertEqual(resolved["primary"]["small"]["shadow_edge_clip_count"], 4_583)

        characters = {row.codepoint: row.character for row in self.plan.mapping}
        for layout, cell_width, cell_height in (
            (self.normal_layout, font.NORMAL_CELL_WIDTH, font.NORMAL_CELL_HEIGHT),
            (self.small_layout, font.SMALL_CELL_WIDTH, font.SMALL_CELL_HEIGHT),
        ):
            if layout.resolved_pixel_size == layout.requested_pixel_size:
                continue
            next_size = layout.resolved_pixel_size + 1
            next_font = font._load_freetype(self.plan.primary, next_size)
            masks = [font._rasterize_glyph(next_font, character) for character in characters.values()]
            self.assertTrue(
                max(mask.mask.width for mask in masks) > cell_width
                or max(mask.mask.height for mask in masks) > cell_height
            )

    def test_fit_checks_each_integer_size_without_ratio_jump(self) -> None:
        loaded_sizes: list[int] = []

        def fake_load(_face: font.FontFace, pixel_size: int) -> int:
            loaded_sizes.append(pixel_size)
            return pixel_size

        def fake_raster(pixel_size: int, character: str) -> font._GlyphMask:
            side = 20 if pixel_size == font.NORMAL_PIXEL_SIZE else pixel_size
            return font._GlyphMask(character, 0, -side, font.Image.new("1", (side, side), 1))

        with mock.patch.object(font, "_load_freetype", side_effect=fake_load), mock.patch.object(
            font, "_rasterize_glyph", side_effect=fake_raster
        ):
            layout = font._build_face_layout(
                self.plan.primary,
                {ord("\ud55c"): "\ud55c"},
                requested_pixel_size=font.NORMAL_PIXEL_SIZE,
                cell_width=font.NORMAL_CELL_WIDTH,
                cell_height=font.NORMAL_CELL_HEIGHT,
            )

        self.assertIsNotNone(layout)
        self.assertEqual(layout.resolved_pixel_size, font.NORMAL_PIXEL_SIZE - 1)
        self.assertEqual(loaded_sizes, [font.NORMAL_PIXEL_SIZE, font.NORMAL_PIXEL_SIZE - 1])

    def test_all_874_glyphs_preserve_foreground_inside_fixed_cells(self) -> None:
        for sprites, layout, cell_width, cell_height in (
            (
                self.rendered.normal,
                self.normal_layout,
                font.NORMAL_CELL_WIDTH,
                font.NORMAL_CELL_HEIGHT,
            ),
            (
                self.rendered.small,
                self.small_layout,
                font.SMALL_CELL_WIDTH,
                font.SMALL_CELL_HEIGHT,
            ),
        ):
            self.assertEqual(len(sprites), font.KOREAN_GLYPH_COUNT)
            for row, sprite in zip(self.plan.mapping, sprites):
                self.assertGreaterEqual(sprite.offset_x, 0)
                self.assertGreaterEqual(sprite.offset_y, 0)
                self.assertEqual(sprite.offset_x + sprite.width, cell_width)
                self.assertEqual(sprite.offset_y + sprite.height, cell_height)

                points = opaque_points(sprite)
                self.assertTrue(points)
                self.assertTrue(all(0 <= x < cell_width and 0 <= y < cell_height for x, y, _ in points))
                self.assertTrue(
                    all(value in {font.FOREGROUND_PALETTE_INDEX, font.SHADOW_PALETTE_INDEX} for _, _, value in points)
                )
                foreground = [(x, y) for x, y, value in points if value == font.FOREGROUND_PALETTE_INDEX]
                expected_ink = sum(layout.glyphs[row.codepoint].mask.getdata())
                self.assertEqual(len(foreground), expected_ink)
                self.assertEqual(max(y for _, y in foreground), cell_height - 1)

    def test_three_glyph_line_keeps_real_crop_tops_and_one_baseline(self) -> None:
        expected = {
            "\ud55c": {
                "normal": ((0, 1, 13, 13), (0, 1, 12, 14)),
                "small": ((0, 1, 11, 11), (0, 1, 10, 12)),
            },
            "\ud14c": {
                "normal": ((0, 1, 13, 13), (0, 1, 11, 14)),
                "small": ((0, 1, 11, 11), (0, 1, 9, 12)),
            },
            "\ud06c": {
                "normal": ((0, 4, 13, 10), (0, 4, 12, 14)),
                "small": ((0, 3, 11, 9), (0, 3, 10, 12)),
            },
        }
        for character, cases in expected.items():
            offset = self.offset_by_character[character]
            for kind, sprites in (("normal", self.rendered.normal), ("small", self.rendered.small)):
                sprite = sprites[offset]
                foreground = [
                    (x, y)
                    for x, y, value in opaque_points(sprite)
                    if value == font.FOREGROUND_PALETTE_INDEX
                ]
                bbox = (
                    min(x for x, _ in foreground),
                    min(y for _, y in foreground),
                    max(x for x, _ in foreground) + 1,
                    max(y for _, y in foreground) + 1,
                )
                self.assertEqual(
                    ((sprite.offset_x, sprite.offset_y, sprite.width, sprite.height), bbox),
                    cases[kind],
                )

        normal_tops = [self.rendered.normal[self.offset_by_character[ch]].offset_y for ch in expected]
        small_tops = [self.rendered.small[self.offset_by_character[ch]].offset_y for ch in expected]
        self.assertGreater(len(set(normal_tops)), 1)
        self.assertGreater(len(set(small_tops)), 1)
        self.assertTrue(
            all(
                self.rendered.normal[self.offset_by_character[ch]].offset_y
                + self.rendered.normal[self.offset_by_character[ch]].height
                == font.NORMAL_CELL_HEIGHT
                for ch in expected
            )
        )
        self.assertTrue(
            all(
                self.rendered.small[self.offset_by_character[ch]].offset_y
                + self.rendered.small[self.offset_by_character[ch]].height
                == font.SMALL_CELL_HEIGHT
                for ch in expected
            )
        )

    def test_primary_and_fallback_share_the_same_logical_baseline(self) -> None:
        primary_codepoints = frozenset(row.codepoint for index, row in enumerate(self.plan.mapping) if index % 2 == 0)
        fallback_codepoints = frozenset(row.codepoint for index, row in enumerate(self.plan.mapping) if index % 2 == 1)
        mixed = font.FontPlan(
            self.plan.mapping,
            self.plan.primary,
            self.plan.primary,
            primary_codepoints,
            fallback_codepoints,
            "custom",
        )
        rendered = font.render_font(mixed)
        resolved = rendered.metadata["resolved_faces"]

        self.assertEqual(
            resolved["primary"]["normal"]["baseline_y"],
            resolved["fallback"]["normal"]["baseline_y"],
        )
        self.assertEqual(
            resolved["primary"]["small"]["baseline_y"],
            resolved["fallback"]["small"]["baseline_y"],
        )
        self.assertEqual(resolved["primary"]["normal"]["baseline_y"], font.NORMAL_CELL_HEIGHT)
        self.assertEqual(resolved["primary"]["small"]["baseline_y"], font.SMALL_CELL_HEIGHT)
        self.assertTrue(all(sprite.offset_y + sprite.height == font.NORMAL_CELL_HEIGHT for sprite in rendered.normal))
        self.assertTrue(all(sprite.offset_y + sprite.height == font.SMALL_CELL_HEIGHT for sprite in rendered.small))


class AggBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        resources = (
            ("FONT.ICN", legacy_icn(1)),
            ("SMALFONT.ICN", legacy_icn(101)),
            *((name, f"original:{name}".encode("ascii")) for name in LOCALIZED_BIN_RESOURCES),
            *((name, f"original:{name}".encode("ascii")) for name in RESTORED_UI_ICN_RESOURCES),
            ("UNCHANGED.BIN", b"unchanged"),
        )
        self.original_raw = make_agg(resources)
        original = font.parse_agg(self.original_raw, label="synthetic-original")
        replacements = {
            name: f"patched:{name}".encode("ascii")
            for name in (*LOCALIZED_BIN_RESOURCES, *RESTORED_UI_ICN_RESOURCES)
        }
        replacements.update(
            {
                "FONT.ICN": b"patched-normal-font",
                "SMALFONT.ICN": b"patched-small-font",
            }
        )
        self.patched_raw = font.repack_agg(original, replacements)

    def test_localized_base_keeps_only_eight_bins_and_restores_icns(self) -> None:
        base_raw = font.make_localized_font_base(
            self.original_raw,
            self.patched_raw,
            keep_localized_resources=LOCALIZED_BIN_RESOURCES,
            expected_patched_changes=EXPECTED_MAIN_AGG_CHANGES,
            label="synthetic-main",
        )
        original = font.parse_agg(self.original_raw, label="synthetic-original-check")
        patched = font.parse_agg(self.patched_raw, label="synthetic-patched-check")
        base = font.parse_agg(base_raw, label="synthetic-base-check")

        self.assertEqual(
            set(font.changed_agg_resources(self.original_raw, base_raw, label="synthetic-base-diff")),
            set(LOCALIZED_BIN_RESOURCES),
        )
        for name in LOCALIZED_BIN_RESOURCES:
            self.assertEqual(base.get(name).payload, patched.get(name).payload)
        for name in (*RESTORED_UI_ICN_RESOURCES, *font.FONT_RESOURCE_NAMES):
            self.assertEqual(base.get(name).payload, original.get(name).payload)
        self.assertEqual(base.get("UNCHANGED.BIN").payload, original.get("UNCHANGED.BIN").payload)

    def test_localized_base_rejects_an_unexpected_active_change(self) -> None:
        with self.assertRaises(font.FontBuildError):
            font.make_localized_font_base(
                self.original_raw,
                self.patched_raw,
                keep_localized_resources=LOCALIZED_BIN_RESOURCES,
                expected_patched_changes=EXPECTED_MAIN_AGG_CHANGES[:-1],
                label="synthetic-missing-allowlist-entry",
            )


class FontLayoutTests(unittest.TestCase):
    def test_rebuild_blanks_at_sign_fills_gap_and_appends_874_glyphs(self) -> None:
        base_raw = make_agg(
            (
                ("FONT.ICN", legacy_icn(1)),
                ("SMALFONT.ICN", legacy_icn(101)),
                ("KEEP.BIN", b"localized-interface-data"),
            )
        )
        normal_addition = make_sprite(font.FOREGROUND_PALETTE_INDEX, offset_x=-1)
        small_addition = make_sprite(font.SHADOW_PALETTE_INDEX, offset_x=-2)
        rendered = font.RenderedFont(
            normal=(normal_addition,) * font.KOREAN_GLYPH_COUNT,
            small=(small_addition,) * font.KOREAN_GLYPH_COUNT,
            metadata={"fixture": True},
        )

        rebuilt_raw = font.rebuild_agg_fonts(base_raw, rendered, label="synthetic-layout")
        before_agg = font.parse_agg(base_raw, label="synthetic-layout-before")
        after_agg = font.parse_agg(rebuilt_raw, label="synthetic-layout-after")

        self.assertEqual(
            set(font.changed_agg_resources(base_raw, rebuilt_raw, label="synthetic-layout-diff")),
            set(font.FONT_RESOURCE_NAMES),
        )
        self.assertEqual(after_agg.get("KEEP.BIN").payload, before_agg.get("KEEP.BIN").payload)

        expected_blank = font.Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80")
        for resource_name, additions in (
            ("FONT.ICN", rendered.normal),
            ("SMALFONT.ICN", rendered.small),
        ):
            before = font.parse_icn(before_agg.get(resource_name).payload, label=f"before:{resource_name}")
            after = font.parse_icn(after_agg.get(resource_name).payload, label=f"after:{resource_name}")

            self.assertEqual(len(before.sprites), font.LEGACY_SPRITE_COUNT)
            self.assertEqual(len(after.sprites), font.FINAL_SPRITE_COUNT)
            self.assertEqual(after.sprites[: font.AT_SIGN_SPRITE_INDEX], before.sprites[: font.AT_SIGN_SPRITE_INDEX])
            self.assertEqual(after.sprites[font.AT_SIGN_SPRITE_INDEX], expected_blank)
            self.assertEqual(
                after.sprites[font.AT_SIGN_SPRITE_INDEX + 1 : font.LEGACY_SPRITE_COUNT],
                before.sprites[font.AT_SIGN_SPRITE_INDEX + 1 :],
            )
            self.assertEqual(
                after.sprites[font.LEGACY_SPRITE_COUNT : font.KOREAN_FIRST_INDEX],
                (before.sprites[0],) * font.FILLER_SPRITE_COUNT,
            )
            self.assertEqual(after.sprites[font.KOREAN_FIRST_INDEX :], additions)

    def test_rebuild_rejects_a_non_pristine_recruit_background(self) -> None:
        base_raw = make_agg(
            (
                ("FONT.ICN", legacy_icn(1)),
                ("SMALFONT.ICN", legacy_icn(101)),
                (font.RECRUIT_COST_RESOURCE_NAME, b"not-the-pinned-pristine-raster"),
            )
        )
        addition = make_sprite(font.FOREGROUND_PALETTE_INDEX)
        rendered = font.RenderedFont(
            normal=(addition,) * font.KOREAN_GLYPH_COUNT,
            small=(addition,) * font.KOREAN_GLYPH_COUNT,
            metadata={"fixture": True},
        )

        with self.assertRaises(font.FontBuildError):
            font.rebuild_agg_fonts(base_raw, rendered, label="synthetic-recruit-wrong-source")

    def test_local_gog_main_agg_rebuilds_only_fonts_and_recruit_cost_raster(self) -> None:
        if not LOCAL_GOG_ORIGINAL_AGG.is_file():
            self.skipTest("local pristine GOG HEROES2.AGG fixture is unavailable")

        base_raw = LOCAL_GOG_ORIGINAL_AGG.read_bytes()
        plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        rendered = font.render_font(plan)
        rebuilt_raw = font.rebuild_agg_fonts(base_raw, rendered, label="local-gog-main")
        before = font.parse_agg(base_raw, label="local-gog-main-before")
        after = font.parse_agg(rebuilt_raw, label="local-gog-main-after")

        self.assertEqual(
            set(font.changed_agg_resources(base_raw, rebuilt_raw, label="local-gog-main-diff")),
            {*font.FONT_RESOURCE_NAMES, font.RECRUIT_COST_RESOURCE_NAME},
        )
        before_cost = before.get(font.RECRUIT_COST_RESOURCE_NAME)
        after_cost = after.get(font.RECRUIT_COST_RESOURCE_NAME)
        self.assertEqual(len(before_cost.payload), font.RECRUIT_COST_SOURCE_SIZE)
        self.assertEqual(font.sha256_bytes(before_cost.payload), font.RECRUIT_COST_SOURCE_SHA256)
        self.assertEqual(len(after_cost.payload), font.RECRUIT_COST_OUTPUT_SIZE)
        self.assertEqual(font.sha256_bytes(after_cost.payload), font.RECRUIT_COST_OUTPUT_SHA256)

        before_icn = font.parse_icn(before_cost.payload, label="local-gog-cost-before")
        after_icn = font.parse_icn(after_cost.payload, label="local-gog-cost-after")
        self.assertEqual(after_icn.sprites[1:], before_icn.sprites[1:])
        before_background = font._decode_sprite(before_icn.sprites[0], label="local-gog-background-before")
        after_background = font._decode_sprite(after_icn.sprites[0], label="local-gog-background-after")
        x0, y0, width, height = font.RECRUIT_COST_ROI
        for y in range(before_background.height):
            for x in range(before_background.width):
                if x0 <= x < x0 + width and y0 <= y < y0 + height:
                    continue
                offset = y * before_background.width + x
                self.assertEqual(after_background.pixels[offset], before_background.pixels[offset])
                self.assertEqual(after_background.transform[offset], before_background.transform[offset])

        for before_entry, after_entry in zip(before.entries, after.entries):
            if before_entry.name.upper() in {
                *(name.upper() for name in font.FONT_RESOURCE_NAMES),
                font.RECRUIT_COST_RESOURCE_NAME,
            }:
                continue
            self.assertEqual(after_entry.payload, before_entry.payload, before_entry.name)


if __name__ == "__main__":
    unittest.main()
