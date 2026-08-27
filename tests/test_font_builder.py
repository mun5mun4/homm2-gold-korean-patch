#!/usr/bin/env python3
"""Fast contracts for dynamic HoMM2 font and AGG generation."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.release import homm2_font as font


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "translations" / "font" / "mapping874.fixed-interface-font.txt"
DEFAULT_FONT = ROOT / "packaging" / "release_assets" / "fonts" / "NanumGothicCoding-Regular.ttf"
LOCAL_GOG_ORIGINAL_AGG_ENV = "HOMM2_TEST_GOG_ORIGINAL_AGG"
LOCAL_CUSTOM_FONT_ENV = "HOMM2_TEST_CUSTOM_FONT"
LOCAL_IROPKE_FONT_ENV = "HOMM2_TEST_IROPKE_FONT"
WINDOWS_MALGUN_FONT = Path(r"C:\Windows\Fonts\malgun.ttf")
IROPKE_FONT_SHA256 = "5910F97BAED6C6E0B8538E40D326B169E0A510357E20DD9003ABABCE2CE1CC69"

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
        self.assertEqual(metadata["renderer"], "pillow-freetype-monochrome-v3-typographic-baseline")
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
        self.assertEqual(self.normal_layout.baseline_y, 12)
        self.assertEqual(self.small_layout.baseline_y, 10)
        self.assertEqual(self.normal_layout.baseline_y, -self.normal_layout.union_top)
        self.assertEqual(self.small_layout.baseline_y, -self.small_layout.union_top)

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
        self.assertEqual(resolved["primary"]["normal"]["shadow_edge_clip_count"], 4_367)
        self.assertEqual(resolved["primary"]["small"]["shadow_edge_clip_count"], 4_030)

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
            union_top = min(mask.top for mask in masks)
            union_bottom = max(mask.bottom for mask in masks)
            self.assertTrue(
                max(mask.mask.width for mask in masks) > cell_width
                or max(mask.mask.height for mask in masks) > cell_height
                or union_bottom - union_top > cell_height
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

    def test_fit_rejects_a_combined_ink_union_taller_than_the_cell(self) -> None:
        loaded_sizes: list[int] = []

        def fake_load(_face: font.FontFace, pixel_size: int) -> int:
            loaded_sizes.append(pixel_size)
            return pixel_size

        def fake_raster(pixel_size: int, character: str) -> font._GlyphMask:
            if pixel_size == font.SMALL_PIXEL_SIZE:
                top = -10 if character == "가" else -3
                height = 7
            else:
                top = -9 if character == "가" else -3
                height = 6
            return font._GlyphMask(character, 0, top, font.Image.new("1", (6, height), 1))

        with mock.patch.object(font, "_load_freetype", side_effect=fake_load), mock.patch.object(
            font, "_rasterize_glyph", side_effect=fake_raster
        ):
            layout = font._build_face_layout(
                self.plan.primary,
                {ord("가"): "가", ord("나"): "나"},
                requested_pixel_size=font.SMALL_PIXEL_SIZE,
                cell_width=font.SMALL_CELL_WIDTH,
                cell_height=font.SMALL_CELL_HEIGHT,
            )

        self.assertIsNotNone(layout)
        self.assertEqual(layout.resolved_pixel_size, font.SMALL_PIXEL_SIZE - 1)
        self.assertEqual(layout.union_bottom - layout.union_top, font.SMALL_CELL_HEIGHT)
        self.assertEqual(layout.baseline_y, -layout.union_top)
        self.assertEqual(loaded_sizes, [font.SMALL_PIXEL_SIZE, font.SMALL_PIXEL_SIZE - 1])

    def test_shadow_clip_metadata_uses_the_remaining_logical_cell_height(self) -> None:
        glyph = font._GlyphMask("가", 0, -2, font.Image.new("1", (1, 1), 1))
        layout = font._FaceLayout(
            requested_pixel_size=4,
            resolved_pixel_size=4,
            cell_width=4,
            cell_height=4,
            origin_x=2,
            baseline_y=2,
            union_left=0,
            union_top=-2,
            union_right=1,
            union_bottom=-1,
            glyphs={ord("가"): glyph},
        )

        self.assertEqual(layout.shadow_edge_clip_count(), 0)

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
                glyph = layout.glyphs[row.codepoint]
                expected_ink = sum(glyph.mask.getdata())
                self.assertEqual(len(foreground), expected_ink)
                self.assertEqual(sprite.offset_y, layout.baseline_y + glyph.top)
                self.assertEqual(min(y for _, y in foreground), sprite.offset_y)
                self.assertEqual(max(y for _, y in foreground), sprite.offset_y + glyph.mask.height - 1)

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
                "normal": ((0, 2, 13, 12), (0, 2, 12, 12)),
                "small": ((0, 1, 11, 11), (0, 1, 10, 10)),
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
        self.assertEqual(normal_tops, [1, 1, 2])
        self.assertEqual(small_tops, [1, 1, 1])
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
        primary_codepoints = frozenset({ord("\ud06c")})
        fallback_codepoints = frozenset(row.codepoint for row in self.plan.mapping) - primary_codepoints
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
        self.assertEqual(resolved["primary"]["normal"]["baseline_y"], 12)
        self.assertEqual(resolved["primary"]["small"]["baseline_y"], 10)
        self.assertEqual(
            resolved["primary"]["normal"]["ink_union"],
            resolved["fallback"]["normal"]["ink_union"],
        )
        self.assertEqual(
            resolved["primary"]["small"]["ink_union"],
            resolved["fallback"]["small"]["ink_union"],
        )
        for kind, sprites in (("normal", rendered.normal), ("small", rendered.small)):
            face_metadata = resolved["primary"][kind]
            freetype = font._load_freetype(
                self.plan.primary,
                int(face_metadata["resolved_pixel_size"]),
            )
            for character in ("\ud06c", "\ud55c"):
                glyph = font._rasterize_glyph(freetype, character)
                sprite = sprites[self.offset_by_character[character]]
                self.assertEqual(
                    sprite.offset_y,
                    int(face_metadata["baseline_y"]) + glyph.top,
                )
                foreground = [
                    (x, y)
                    for x, y, value in opaque_points(sprite)
                    if value == font.FOREGROUND_PALETTE_INDEX
                ]
                self.assertEqual(
                    max(y for _, y in foreground),
                    int(face_metadata["baseline_y"]) + glyph.bottom - 1,
                )

        # The sprite canvas still reaches the fixed logical-cell edge for a
        # fixed advance; the assertions above prove its ink is not bottom-aligned.
        self.assertTrue(all(sprite.offset_y + sprite.height == font.NORMAL_CELL_HEIGHT for sprite in rendered.normal))
        self.assertTrue(all(sprite.offset_y + sprite.height == font.SMALL_CELL_HEIGHT for sprite in rendered.small))


class IropkeTypographicBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get(LOCAL_IROPKE_FONT_ENV)
        if not configured:
            raise unittest.SkipTest(
                f"set {LOCAL_IROPKE_FONT_ENV} to a locally owned IropkeBatangM.ttf fixture"
            )
        cls.font_path = Path(configured)
        if not cls.font_path.is_file():
            raise unittest.SkipTest(
                f"{LOCAL_IROPKE_FONT_ENV} does not point to a readable IropkeBatangM.ttf fixture"
            )
        cls.plan = font.make_font_plan(MAPPING, cls.font_path, mode="custom")
        if cls.plan.primary.sha256 != IROPKE_FONT_SHA256:
            raise AssertionError(
                f"unexpected IropkeBatangM.ttf fixture: {cls.plan.primary.sha256}"
            )
        cls.rendered = font.render_font(cls.plan)
        cls.offset_by_character = {
            row.character: row.index - font.KOREAN_FIRST_INDEX for row in cls.plan.mapping
        }

    def test_iropke_resolves_to_the_handoff_sizes_and_typographic_baselines(self) -> None:
        resolved = self.rendered.metadata["resolved_faces"]["primary"]

        self.assertEqual(resolved["normal"]["resolved_pixel_size"], 14)
        self.assertEqual(resolved["normal"]["baseline_y"], 12)
        self.assertEqual(resolved["normal"]["ink_union"], [0, -12, 12, 2])
        self.assertEqual(resolved["small"]["resolved_pixel_size"], 11)
        self.assertEqual(resolved["small"]["baseline_y"], 10)
        self.assertEqual(resolved["small"]["ink_union"], [0, -10, 10, 2])

    def test_juso_preserves_one_source_top_and_one_cell_top(self) -> None:
        for kind, sprites, cell_height in (
            ("normal", self.rendered.normal, font.NORMAL_CELL_HEIGHT),
            ("small", self.rendered.small, font.SMALL_CELL_HEIGHT),
        ):
            layout = self.rendered.metadata["resolved_faces"]["primary"][kind]
            pixel_size = int(layout["resolved_pixel_size"])
            freetype = font._load_freetype(self.plan.primary, pixel_size)
            glyphs = [font._rasterize_glyph(freetype, character) for character in "주조소"]
            selected = [sprites[self.offset_by_character[character]] for character in "주조소"]

            self.assertEqual(len({glyph.top for glyph in glyphs}), 1)
            self.assertEqual([sprite.offset_y for sprite in selected], [1, 1, 1])
            self.assertTrue(
                all(
                    sprite.offset_y == int(layout["baseline_y"]) + glyph.top
                    and sprite.offset_y + sprite.height == cell_height
                    for sprite, glyph in zip(selected, glyphs)
                )
            )

    def test_all_874_iropke_glyphs_are_unclipped_fixed_advance_roundtrips(self) -> None:
        resolved = self.rendered.metadata["resolved_faces"]["primary"]
        self.assertEqual(len(self.rendered.normal), font.KOREAN_GLYPH_COUNT)
        self.assertEqual(len(self.rendered.small), font.KOREAN_GLYPH_COUNT)

        for kind, sprites, cell_width, cell_height in (
            ("normal", self.rendered.normal, font.NORMAL_CELL_WIDTH, font.NORMAL_CELL_HEIGHT),
            ("small", self.rendered.small, font.SMALL_CELL_WIDTH, font.SMALL_CELL_HEIGHT),
        ):
            self.assertEqual(resolved[kind]["foreground_clip_count"], 0)
            pixel_size = int(resolved[kind]["resolved_pixel_size"])
            freetype = font._load_freetype(self.plan.primary, pixel_size)
            glyphs = {
                row.codepoint: font._rasterize_glyph(freetype, row.character)
                for row in self.plan.mapping
            }
            for row, sprite in zip(self.plan.mapping, sprites):
                self.assertEqual(sprite.offset_x + sprite.width, cell_width)
                self.assertEqual(sprite.offset_y + sprite.height, cell_height)
                points = opaque_points(sprite)
                self.assertTrue(
                    all(0 <= x < cell_width and 0 <= y < cell_height for x, y, _ in points)
                )
                foreground = [
                    (x, y)
                    for x, y, value in points
                    if value == font.FOREGROUND_PALETTE_INDEX
                ]
                self.assertEqual(
                    len(foreground),
                    sum(glyphs[row.codepoint].mask.getdata()),
                )

            packed = font.pack_icn(sprites)
            parsed = font.parse_icn(packed, label=f"iropke-v3-{kind}-roundtrip")
            self.assertEqual(parsed.sprites, sprites)


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


class ImageUiContractTests(unittest.TestCase):
    def test_image_ui_resource_target_and_preservation_contracts_are_exact(self) -> None:
        source_resources = set(font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(set(font.IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES), source_resources)
        self.assertEqual(len(source_resources), 9)

        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in font.IMAGE_UI_TEXT_TARGETS
        )
        self.assertEqual(len(target_keys), 52)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertNotIn("HSBTNS.ICN", {resource for resource, _ in target_keys})

        mirror = font.IMAGE_UI_WELL_MIRROR
        self.assertEqual(str(mirror["source_resource"]), "WELLXTRA.ICN")
        self.assertEqual(str(mirror["target_resource"]), "WELLBKG.ICN")
        self.assertEqual(
            {resource for resource, _ in target_keys},
            source_resources - {str(mirror["target_resource"])},
        )
        self.assertEqual(tuple(mirror["source_roi"])[2:], tuple(mirror["target_roi"])[2:])

        for target in font.IMAGE_UI_TEXT_TARGETS:
            donor_fields = {"donor_resource", "donor_sprite", "donor_clear_roi"}
            present = donor_fields & set(target)
            self.assertIn(len(present), {0, len(donor_fields)})
            if present:
                self.assertIn(str(target["donor_resource"]), source_resources)

    def test_del_is_not_treated_as_a_printable_ascii_glyph(self) -> None:
        with self.assertRaises(font.FontBuildError):
            font._image_ui_glyph_index("\x7f", ())


class Menu132ContractTests(unittest.TestCase):
    def test_menu132_resource_and_target_contracts_are_exact(self) -> None:
        source_resources = set(font.MENU132_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(set(font.MENU132_RESOURCE_OUTPUT_IDENTITIES), source_resources)
        self.assertEqual(len(source_resources), 12)

        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in font.MENU132_TEXT_TARGETS
        )
        self.assertEqual(len(target_keys), 70)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertEqual({resource for resource, _ in target_keys}, source_resources)

    def test_menu132_technical_label_sprites_are_not_targets(self) -> None:
        target_keys = {
            (str(target["resource"]), int(target["sprite"]))
            for target in font.MENU132_TEXT_TARGETS
        }
        preserved_technical_sprites = {
            "BTNCMPGN.ICN": set(range(8)),
            "BTNCOM.ICN": set(range(8)),
            "BTNMP.ICN": {4, 5},
            "BTNNET2.ICN": set(range(6)),
            "BTNBAUD.ICN": set(range(8)),
        }
        for resource_name, sprite_indices in preserved_technical_sprites.items():
            self.assertTrue(
                target_keys.isdisjoint(
                    (resource_name, sprite_index)
                    for sprite_index in sprite_indices
                ),
                resource_name,
            )


class CampaignButtonContractTests(unittest.TestCase):
    def test_campaign_button_resource_archive_and_target_contracts_are_exact(self) -> None:
        source_resources = set(font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(
            set(font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES),
            source_resources,
        )
        self.assertEqual(
            source_resources,
            {"CAMPXTRG.ICN", "CAMPXTRE.ICN", "X_CMPBTN.ICN"},
        )
        self.assertEqual(
            set(font.CAMPAIGN_BUTTON_ARCHIVE_RESOURCE_SETS),
            {
                frozenset(("CAMPXTRG.ICN", "CAMPXTRE.ICN")),
                frozenset(("X_CMPBTN.ICN",)),
            },
        )

        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in font.CAMPAIGN_BUTTON_TEXT_TARGETS
        )
        self.assertEqual(len(target_keys), 24)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertEqual({resource for resource, _ in target_keys}, source_resources)
        for resource_name in source_resources:
            resource_sprites = {
                sprite_index
                for resource, sprite_index in target_keys
                if resource == resource_name
            }
            self.assertEqual(resource_sprites, set(range(8)), resource_name)


class CampProgressContractTests(unittest.TestCase):
    def test_camp_progress_identity_archive_text_and_clone_contracts_are_exact(self) -> None:
        source_resources = set(font.CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(
            source_resources,
            {"CAMPBKGG.ICN", "CAMPBKGE.ICN", "X_CMPBKG.ICN"},
        )
        self.assertEqual(
            set(font.CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES),
            source_resources,
        )
        self.assertEqual(set(font.CAMP_PROGRESS_SPECS), source_resources)
        self.assertEqual(
            set(font.CAMP_PROGRESS_ARCHIVE_RESOURCE_SETS),
            {
                frozenset(("CAMPBKGG.ICN", "CAMPBKGE.ICN")),
                frozenset(("X_CMPBKG.ICN",)),
            },
        )
        self.assertEqual(
            font.CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES,
            {
                "CAMPBKGG.ICN": (
                    282_547,
                    "F98DBAF55DD3A5AA0A53E8E763C1BFDEB221D1CFE6754862053ECBCC69EA6806",
                ),
                "CAMPBKGE.ICN": (
                    282_033,
                    "5574FBF2908870662FE5F1D6B0AE2B26E7B9529FCAA2C9BBF3B355A98C2577E2",
                ),
                "X_CMPBKG.ICN": (
                    285_412,
                    "D1EF57097A52B57A016F9C8DB3E29F7633FE552CD01A5B12AE8C3B1DE19A266C",
                ),
            },
        )
        self.assertEqual(
            font.CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES,
            {
                "CAMPBKGG.ICN": (
                    310_580,
                    "77E189C4E3F7AA778D17D8217B197259BCB848B3F3BE0DA1680BDDE39249AC2A",
                ),
                "CAMPBKGE.ICN": (
                    310_580,
                    "2F3E0BA725AA06E7B75315A6D3B1CA8EAC2F2269936AAA6293C438B0F1EEEEB6",
                ),
                "X_CMPBKG.ICN": (
                    310_580,
                    "1AA00F02FEBD3BF686B263AB74F903A5328567D2073F371558A64C8C38476FDF",
                ),
            },
        )
        self.assertEqual(
            font.CAMP_PROGRESS_PALETTE_MAPS,
            {
                "good": {
                    font.FOREGROUND_PALETTE_INDEX: 113,
                    font.SHADOW_PALETTE_INDEX: 62,
                },
                "evil": {
                    font.FOREGROUND_PALETTE_INDEX: 12,
                    font.SHADOW_PALETTE_INDEX: 36,
                },
            },
        )

        text_keys = []
        for resource_name, resource_spec in font.CAMP_PROGRESS_SPECS.items():
            texts = tuple(resource_spec["texts"])
            self.assertEqual(len(texts), 4 if resource_name == "X_CMPBKG.ICN" else 5)
            self.assertEqual(
                tuple(str(spec["text"]) for spec in texts if spec["key"] != "title"),
                ("진행 일수", "시나리오", "보상", "선택"),
            )
            for spec in texts:
                key = (resource_name, str(spec["key"]))
                text_keys.append(key)
                for roi_name in ("mask_roi", "layout_roi"):
                    x0, y0, width, height = (int(value) for value in spec[roi_name])
                    self.assertGreaterEqual(x0, 0, key)
                    self.assertGreaterEqual(y0, 0, key)
                    self.assertGreater(width, 0, key)
                    self.assertGreater(height, 0, key)
                    self.assertLessEqual(x0 + width, 640, key)
                    self.assertLessEqual(y0 + height, 480, key)
                self.assertEqual(int(spec["dilate"]), 3, key)
                self.assertEqual(int(spec["scale"]), 2, key)
                self.assertIn(str(spec["font"]), {"normal", "small"}, key)
                self.assertIn(str(spec["clone"][0]), {"same_y_bands", "offset"}, key)
        self.assertEqual(len(text_keys), 14)
        self.assertEqual(len(set(text_keys)), len(text_keys))
        self.assertEqual(
            str(font.CAMP_PROGRESS_SPECS["CAMPBKGG.ICN"]["texts"][0]["text"]),
            "롤란드의 캠페인",
        )
        self.assertEqual(
            str(font.CAMP_PROGRESS_SPECS["CAMPBKGE.ICN"]["texts"][0]["text"]),
            "아치발드의 캠페인",
        )

    def test_camp_progress_missing_is_noop_and_partial_archive_set_is_rejected(self) -> None:
        no_resources = font.AggArchive((), b"")
        with mock.patch.object(font, "_render_camp_progress_resource") as render:
            self.assertEqual(
                font._localize_camp_progress_resources(
                    no_resources,
                    (),
                    (),
                    (),
                    label="camp-progress-noop",
                ),
                {},
            )
        render.assert_not_called()

        resource_name = "CAMPBKGG.ICN"
        partial = font.AggArchive(
            (
                font.AggEntry(
                    index=0,
                    name=resource_name,
                    name_slot=resource_name.encode("ascii").ljust(font.AGG_NAME_SIZE, b"\0"),
                    hash_word=font.agg_filename_hash(resource_name),
                    payload=b"partial-campaign-progress",
                ),
            ),
            b"",
        )
        with self.assertRaises(font.FontBuildError):
            font._localize_camp_progress_resources(
                partial,
                (),
                (),
                (),
                label="camp-progress-partial",
            )


class GameButtonContractTests(unittest.TestCase):
    def test_game_button_resource_pair_and_target_contracts_are_exact(self) -> None:
        source_resources = set(font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(len(source_resources), 19)
        self.assertEqual(
            set(font.GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES),
            source_resources,
        )
        self.assertEqual(set(font.GAME_BUTTON_PAIR_SPECS), source_resources)
        self.assertEqual(
            set(font.GAME_BUTTON_EVIL_RESOURCES),
            {
                "SPANBTNE.ICN",
                "CSPANBTE.ICN",
                "TRADPOSE.ICN",
                "VIEWARME.ICN",
                "SURRENDE.ICN",
                "APANELE.ICN",
                "CPANELE.ICN",
                "WINCMBBE.ICN",
            },
        )
        self.assertTrue(set(font.GAME_BUTTON_EVIL_RESOURCES) < source_resources)

        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in font.GAME_BUTTON_TEXT_TARGETS
        )
        self.assertEqual(len(target_keys), 80)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertEqual({resource for resource, _ in target_keys}, source_resources)
        for resource_name, pair_specs in font.GAME_BUTTON_PAIR_SPECS.items():
            self.assertEqual(
                sum(resource == resource_name for resource, _ in target_keys),
                len(pair_specs) * 2,
                resource_name,
            )


class ExpansionMenuContractTests(unittest.TestCase):
    def test_expansion_menu_resource_action_and_target_contracts_are_exact(self) -> None:
        source_resources = set(font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(
            source_resources,
            {"X_NEWCMP.ICN", "X_LOADCM.ICN", "X_MAPMNU.ICN"},
        )
        self.assertEqual(
            set(font.EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES),
            source_resources,
        )
        self.assertEqual(
            set(font.EXPANSION_MENU_ACTION_PAIRS),
            {"X_LOADCM.ICN", "X_MAPMNU.ICN"},
        )

        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in font.EXPANSION_MENU_TEXT_TARGETS
        )
        self.assertEqual(len(target_keys), 19)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertEqual({resource for resource, _ in target_keys}, source_resources)
        self.assertEqual(
            {
                sprite_index
                for resource_name, sprite_index in target_keys
                if resource_name == "X_NEWCMP.ICN"
            },
            {0, 2, 4, 6, 8, 10, 11},
        )
        for resource_name in ("X_LOADCM.ICN", "X_MAPMNU.ICN"):
            self.assertEqual(
                {
                    sprite_index
                    for resource, sprite_index in target_keys
                    if resource == resource_name
                },
                set(range(6)),
                resource_name,
            )
        self.assertTrue(
            set(target_keys).isdisjoint(
                ("X_NEWCMP.ICN", sprite_index)
                for sprite_index in (1, 3, 5, 7, 9)
            )
        )


class EmbeddedUiContractTests(unittest.TestCase):
    def test_embedded_ui_resource_mirror_and_roi_contracts_are_exact(self) -> None:
        source_resources = set(font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES)
        self.assertEqual(len(source_resources), 20)
        self.assertEqual(
            set(font.EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES),
            source_resources,
        )
        self.assertEqual(len(font.EMBEDDED_UI_MIRRORS), 41)

        mirror_targets = {
            str(mirror["target_resource"])
            for mirror in font.EMBEDDED_UI_MIRRORS
        }
        direct_targets = {
            str(target["resource"])
            for target in font.EMBEDDED_UI_TEXT_TARGETS
        }
        self.assertEqual(len(mirror_targets), 19)
        self.assertEqual(direct_targets, {"WINLOSEE.ICN"})
        self.assertEqual(mirror_targets | direct_targets, source_resources)
        self.assertTrue(mirror_targets.isdisjoint(direct_targets))

        localized_source_resources = {
            *font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
            *font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            font.RECRUIT_COST_RESOURCE_NAME,
        }
        mirror_sources = {
            str(mirror["source_resource"])
            for mirror in font.EMBEDDED_UI_MIRRORS
        }
        self.assertTrue(
            mirror_sources <= localized_source_resources,
            sorted(mirror_sources - localized_source_resources),
        )

        target_rois_by_sprite: dict[tuple[str, int], list[tuple[int, int, int, int]]] = {}
        mirror_keys: list[tuple[object, ...]] = []
        for mirror in font.EMBEDDED_UI_MIRRORS:
            source_roi = tuple(int(value) for value in mirror["source_roi"])
            target_roi = tuple(int(value) for value in mirror["target_roi"])
            self.assertEqual(source_roi[2:], target_roi[2:])
            self.assertGreater(target_roi[2], 0)
            self.assertGreater(target_roi[3], 0)
            target_key = (
                str(mirror["target_resource"]),
                int(mirror["target_sprite"]),
            )
            target_rois_by_sprite.setdefault(target_key, []).append(target_roi)
            mirror_keys.append(
                (
                    str(mirror["source_resource"]),
                    int(mirror["source_sprite"]),
                    source_roi,
                    *target_key,
                    target_roi,
                )
            )
        self.assertEqual(len(set(mirror_keys)), len(mirror_keys))

        for target in font.EMBEDDED_UI_TEXT_TARGETS:
            roi = tuple(int(value) for value in target["roi"])
            self.assertGreater(roi[2], 0)
            self.assertGreater(roi[3], 0)
            target_rois_by_sprite.setdefault(
                (str(target["resource"]), int(target["sprite"])),
                [],
            ).append(roi)

        for target_key, rois in target_rois_by_sprite.items():
            for index, (x0, y0, width, height) in enumerate(rois):
                for other_x, other_y, other_width, other_height in rois[index + 1 :]:
                    overlaps = (
                        x0 < other_x + other_width
                        and other_x < x0 + width
                        and y0 < other_y + other_height
                        and other_y < y0 + height
                    )
                    self.assertFalse(overlaps, target_key)


class TownwindContractTests(unittest.TestCase):
    def test_townwind_targets_cost_label_and_buttons_exactly(self) -> None:
        self.assertEqual(
            font.TOWNWIND_SOURCE_IDENTITY,
            (
                24_524,
                "6FB2FF5B55DB92C4E7A28546EBD611C5452688A63164C7AFB78601A5238012AF",
            ),
        )
        self.assertEqual(
            font.TOWNWIND_OUTPUT_IDENTITY,
            (
                30_577,
                "BAF090734C8A8DDDA54DAB7BEBA23B95597A18A68034D9FC6FC9C953BD912F2C",
            ),
        )
        cost_targets = font.TOWNWIND_COST_TARGETS
        button_targets = font.TOWNWIND_BUTTON_TARGETS
        targets = (*cost_targets, *button_targets)
        target_keys = tuple(
            (str(target["resource"]), int(target["sprite"]))
            for target in targets
        )
        self.assertEqual(len(cost_targets), 1)
        self.assertEqual(len(button_targets), 4)
        self.assertEqual(len(target_keys), 5)
        self.assertEqual(len(set(target_keys)), len(target_keys))
        self.assertEqual(
            set(target_keys),
            {
                (font.TOWNWIND_RESOURCE_NAME, 3),
                (font.TOWNWIND_RESOURCE_NAME, 9),
                (font.TOWNWIND_RESOURCE_NAME, 10),
                (font.TOWNWIND_RESOURCE_NAME, 20),
                (font.TOWNWIND_RESOURCE_NAME, 21),
            },
        )
        self.assertEqual(
            cost_targets,
            (
                {
                    "resource": font.TOWNWIND_RESOURCE_NAME,
                    "sprite": 3,
                    "text": font.RECRUIT_COST_LABEL,
                    "state": "released",
                    "interface": "town_cost",
                    "roi": (20, 2, 92, 13),
                    "background": 0,
                    "clear_mode": "row_sample",
                    "background_sample_x": 14,
                    "skip_shadow": True,
                },
            ),
        )

        self.assertEqual(
            tuple((int(target["sprite"]), str(target["text"])) for target in button_targets),
            ((9, "최대"), (10, "최대"), (20, "모집"), (21, "모집")),
        )

    def test_townwind_uses_small_font_for_cost_and_normal_font_for_buttons(self) -> None:
        source_raw = bytes(font.TOWNWIND_SOURCE_IDENTITY[0])
        output_raw = bytes(font.TOWNWIND_OUTPUT_IDENTITY[0])
        cost_localized = mock.sentinel.cost_localized
        base = font.AggArchive(
            (
                font.AggEntry(
                    index=0,
                    name=font.TOWNWIND_RESOURCE_NAME,
                    name_slot=font.TOWNWIND_RESOURCE_NAME.encode("ascii").ljust(font.AGG_NAME_SIZE, b"\0"),
                    hash_word=font.agg_filename_hash(font.TOWNWIND_RESOURCE_NAME),
                    payload=source_raw,
                ),
            ),
            b"",
        )
        normal_font_sprites = (mock.sentinel.normal_font_sprite,)
        small_font_sprites = (mock.sentinel.small_font_sprite,)
        mapping = (mock.sentinel.mapping_row,)

        with (
            mock.patch.object(
                font,
                "_localize_image_ui_text_resource",
                side_effect=(cost_localized, output_raw),
            ) as localize,
            mock.patch.object(
                font,
                "sha256_bytes",
                side_effect=(font.TOWNWIND_SOURCE_IDENTITY[1], font.TOWNWIND_OUTPUT_IDENTITY[1]),
            ),
        ):
            result = font._localize_townwind_resource(
                base,
                normal_font_sprites,
                small_font_sprites,
                mapping,
                label="townwind-font-contract",
            )

        self.assertEqual(result, {font.TOWNWIND_RESOURCE_NAME: output_raw})
        self.assertEqual(
            localize.call_args_list,
            [
                mock.call(
                    source_raw,
                    font.TOWNWIND_COST_TARGETS,
                    small_font_sprites,
                    mapping,
                    {},
                    label=f"townwind-font-contract:{font.TOWNWIND_RESOURCE_NAME}:cost",
                ),
                mock.call(
                    cost_localized,
                    font.TOWNWIND_BUTTON_TARGETS,
                    normal_font_sprites,
                    mapping,
                    {},
                    label=f"townwind-font-contract:{font.TOWNWIND_RESOURCE_NAME}:buttons",
                ),
            ],
        )


class TextbarContractTests(unittest.TestCase):
    def test_textbar_resource_identity_targets_and_rendering_options_are_exact(self) -> None:
        self.assertEqual(font.TEXTBAR_RESOURCE_NAME, "TEXTBAR.ICN")
        self.assertEqual(
            font.TEXTBAR_SOURCE_IDENTITY,
            (
                18_213,
                "00710457495ED98772F4D6492B6E56189CA9E3277443E792E5F1EE1CC1678A5C",
            ),
        )
        self.assertEqual(
            font.TEXTBAR_OUTPUT_IDENTITY,
            (
                20_852,
                "A7C6D1AD5424FA086C73335A623B29FA3494CD777274017078220AC0422B6352",
            ),
        )
        self.assertEqual(
            tuple(
                (
                    int(target["sprite"]),
                    str(target["text"]),
                    str(target["state"]),
                    tuple(int(value) for value in target["roi"]),
                    int(target["background"]),
                )
                for target in font.TEXTBAR_TARGETS
            ),
            (
                (0, "넘기기", "released", (4, 11, 41, 14), 41),
                (1, "넘기기", "pressed", (4, 12, 41, 14), 45),
                (4, "자동", "released", (5, 2, 39, 13), 41),
                (5, "자동", "pressed", (5, 3, 39, 13), 45),
            ),
        )
        self.assertEqual(
            {str(target["resource"]) for target in font.TEXTBAR_TARGETS},
            {font.TEXTBAR_RESOURCE_NAME},
        )
        self.assertEqual(
            {str(target["interface"]) for target in font.TEXTBAR_TARGETS},
            {"good"},
        )

    def test_textbar_uses_small_font_and_pins_source_and_output(self) -> None:
        source_raw = bytes(font.TEXTBAR_SOURCE_IDENTITY[0])
        output_raw = bytes(font.TEXTBAR_OUTPUT_IDENTITY[0])
        base = font.AggArchive(
            (
                font.AggEntry(
                    index=0,
                    name=font.TEXTBAR_RESOURCE_NAME,
                    name_slot=font.TEXTBAR_RESOURCE_NAME.encode("ascii").ljust(font.AGG_NAME_SIZE, b"\0"),
                    hash_word=font.agg_filename_hash(font.TEXTBAR_RESOURCE_NAME),
                    payload=source_raw,
                ),
            ),
            b"",
        )
        small_font_sprites = (mock.sentinel.small_font_sprite,)
        mapping = (mock.sentinel.mapping_row,)

        with (
            mock.patch.object(
                font,
                "_localize_image_ui_text_resource",
                return_value=output_raw,
            ) as localize,
            mock.patch.object(
                font,
                "sha256_bytes",
                side_effect=(font.TEXTBAR_SOURCE_IDENTITY[1], font.TEXTBAR_OUTPUT_IDENTITY[1]),
            ),
        ):
            result = font._localize_textbar_resource(
                base,
                small_font_sprites,
                mapping,
                label="textbar-font-contract",
            )

        self.assertEqual(result, {font.TEXTBAR_RESOURCE_NAME: output_raw})
        localize.assert_called_once_with(
            source_raw,
            font.TEXTBAR_TARGETS,
            small_font_sprites,
            mapping,
            {},
            label=f"textbar-font-contract:{font.TEXTBAR_RESOURCE_NAME}",
        )

    def test_textbar_missing_from_expansion_is_an_exact_noop(self) -> None:
        base = font.AggArchive(
            (
                font.AggEntry(
                    index=0,
                    name="HEROES.ICN",
                    name_slot=b"HEROES.ICN\0\0\0\0\0",
                    hash_word=font.agg_filename_hash("HEROES.ICN"),
                    payload=b"expansion-main-menu",
                ),
            ),
            b"",
        )
        with mock.patch.object(font, "_localize_image_ui_text_resource") as localize:
            self.assertEqual(
                font._localize_textbar_resource(
                    base,
                    (),
                    (),
                    label="textbar-expansion-noop",
                ),
                {},
            )
        localize.assert_not_called()


class MainMenuPreservationContractTests(unittest.TestCase):
    def test_rebuild_preserves_main_menu_rasters_byte_exact(self) -> None:
        button_payload = b"pristine-BTNSHNGL-raster"
        heroes_payload = b"pristine-HEROES-raster"
        base_raw = make_agg(
            (
                ("FONT.ICN", legacy_icn(1)),
                ("SMALFONT.ICN", legacy_icn(101)),
                (font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME, button_payload),
                (font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME, heroes_payload),
            )
        )
        addition = make_sprite(font.FOREGROUND_PALETTE_INDEX)
        rendered = font.RenderedFont(
            normal=(addition,) * font.KOREAN_GLYPH_COUNT,
            small=(addition,) * font.KOREAN_GLYPH_COUNT,
            metadata={"fixture": True},
        )

        rebuilt_raw = font.rebuild_agg_fonts(
            base_raw,
            rendered,
            label="synthetic-main-menu-preservation",
        )
        rebuilt = font.parse_agg(rebuilt_raw, label="synthetic-main-menu-after")
        self.assertEqual(
            rebuilt.get(font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME).payload,
            button_payload,
        )
        self.assertEqual(
            rebuilt.get(font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).payload,
            heroes_payload,
        )


class FontLayoutTests(unittest.TestCase):
    def assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
        self,
        before: font.AggArchive,
        after: font.AggArchive,
        expected_resources: set[str],
        source_identities: dict[str, tuple[int, str]],
        output_identities: dict[str, tuple[int, str]] | None,
        text_targets: tuple[dict[str, object], ...],
        *,
        group_label: str,
    ) -> None:
        targets_by_resource: dict[str, dict[int, dict[str, object]]] = {}
        for target in text_targets:
            resource_name = str(target["resource"])
            if resource_name not in expected_resources:
                continue
            targets_by_resource.setdefault(resource_name, {})[int(target["sprite"])] = target
        self.assertEqual(set(targets_by_resource), expected_resources)

        for resource_name in expected_resources:
            before_payload = before.get(resource_name).payload
            after_payload = after.get(resource_name).payload
            self.assertEqual(
                (len(before_payload), font.sha256_bytes(before_payload)),
                source_identities[resource_name],
            )
            if output_identities is not None:
                self.assertEqual(
                    (len(after_payload), font.sha256_bytes(after_payload)),
                    output_identities[resource_name],
                )

            before_icn = font.parse_icn(
                before_payload,
                label=f"{group_label}-before:{resource_name}",
            )
            after_icn = font.parse_icn(
                after_payload,
                label=f"{group_label}-after:{resource_name}",
            )
            self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))
            targets_by_index = targets_by_resource[resource_name]
            for sprite_index, (before_sprite, after_sprite) in enumerate(
                zip(before_icn.sprites, after_icn.sprites)
            ):
                if sprite_index not in targets_by_index:
                    self.assertEqual(
                        after_sprite,
                        before_sprite,
                        f"{resource_name}:{sprite_index}",
                    )
                    continue

                target = targets_by_index[sprite_index]
                before_decoded = font._decode_sprite(
                    before_sprite,
                    label=f"{group_label}-before:{resource_name}:{sprite_index}",
                )
                after_decoded = font._decode_sprite(
                    after_sprite,
                    label=f"{group_label}-after:{resource_name}:{sprite_index}",
                )
                self.assertEqual(
                    (
                        after_decoded.offset_x,
                        after_decoded.offset_y,
                        after_decoded.width,
                        after_decoded.height,
                        after_decoded.animation,
                    ),
                    (
                        before_decoded.offset_x,
                        before_decoded.offset_y,
                        before_decoded.width,
                        before_decoded.height,
                        before_decoded.animation,
                    ),
                )
                x0, y0, width, height = (int(value) for value in target["roi"])
                for y in range(before_decoded.height):
                    for x in range(before_decoded.width):
                        if x0 <= x < x0 + width and y0 <= y < y0 + height:
                            continue
                        offset = y * before_decoded.width + x
                        self.assertEqual(
                            after_decoded.pixels[offset],
                            before_decoded.pixels[offset],
                        )
                        self.assertEqual(
                            after_decoded.transform[offset],
                            before_decoded.transform[offset],
                        )

    def assert_embedded_ui_resources_preserve_non_targets_and_roi_union_exterior(
        self,
        before: font.AggArchive,
        after: font.AggArchive,
        *,
        canonical_output_identities: bool = True,
    ) -> None:
        target_rois_by_resource: dict[str, dict[int, list[tuple[int, int, int, int]]]] = {}
        for mirror in font.EMBEDDED_UI_MIRRORS:
            resource_name = str(mirror["target_resource"])
            sprite_index = int(mirror["target_sprite"])
            roi = tuple(int(value) for value in mirror["target_roi"])
            target_rois_by_resource.setdefault(resource_name, {}).setdefault(sprite_index, []).append(roi)
        for target in font.EMBEDDED_UI_TEXT_TARGETS:
            resource_name = str(target["resource"])
            sprite_index = int(target["sprite"])
            roi = tuple(int(value) for value in target["roi"])
            target_rois_by_resource.setdefault(resource_name, {}).setdefault(sprite_index, []).append(roi)
        self.assertEqual(
            set(target_rois_by_resource),
            set(font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES),
        )

        for resource_name, source_identity in font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES.items():
            before_payload = before.get(resource_name).payload
            after_payload = after.get(resource_name).payload
            self.assertEqual(
                (len(before_payload), font.sha256_bytes(before_payload)),
                source_identity,
            )
            if canonical_output_identities:
                self.assertEqual(
                    (len(after_payload), font.sha256_bytes(after_payload)),
                    font.EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES[resource_name],
                )

            before_icn = font.parse_icn(
                before_payload,
                label=f"embedded-ui-before:{resource_name}",
            )
            after_icn = font.parse_icn(
                after_payload,
                label=f"embedded-ui-after:{resource_name}",
            )
            self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))
            target_rois_by_index = target_rois_by_resource[resource_name]
            for sprite_index, (before_sprite, after_sprite) in enumerate(
                zip(before_icn.sprites, after_icn.sprites)
            ):
                if sprite_index not in target_rois_by_index:
                    self.assertEqual(
                        after_sprite,
                        before_sprite,
                        f"{resource_name}:{sprite_index}",
                    )
                    continue

                before_decoded = font._decode_sprite(
                    before_sprite,
                    label=f"embedded-ui-before:{resource_name}:{sprite_index}",
                )
                after_decoded = font._decode_sprite(
                    after_sprite,
                    label=f"embedded-ui-after:{resource_name}:{sprite_index}",
                )
                self.assertEqual(
                    (
                        after_decoded.offset_x,
                        after_decoded.offset_y,
                        after_decoded.width,
                        after_decoded.height,
                        after_decoded.animation,
                    ),
                    (
                        before_decoded.offset_x,
                        before_decoded.offset_y,
                        before_decoded.width,
                        before_decoded.height,
                        before_decoded.animation,
                    ),
                )
                target_rois = target_rois_by_index[sprite_index]
                for y in range(before_decoded.height):
                    for x in range(before_decoded.width):
                        if any(
                            roi_x <= x < roi_x + roi_width
                            and roi_y <= y < roi_y + roi_height
                            for roi_x, roi_y, roi_width, roi_height in target_rois
                        ):
                            continue
                        offset = y * before_decoded.width + x
                        self.assertEqual(
                            after_decoded.pixels[offset],
                            before_decoded.pixels[offset],
                        )
                        self.assertEqual(
                            after_decoded.transform[offset],
                            before_decoded.transform[offset],
                        )

    def assert_camp_progress_preserves_geometry_transform_and_roi_union_exterior(
        self,
        before: font.AggArchive,
        after: font.AggArchive,
        expected_resources: set[str],
    ) -> None:
        self.assertIn(
            frozenset(expected_resources),
            font.CAMP_PROGRESS_ARCHIVE_RESOURCE_SETS,
        )
        for resource_name in expected_resources:
            before_payload = before.get(resource_name).payload
            after_payload = after.get(resource_name).payload
            self.assertEqual(
                (len(before_payload), font.sha256_bytes(before_payload)),
                font.CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES[resource_name],
            )
            self.assertEqual(
                (len(after_payload), font.sha256_bytes(after_payload)),
                font.CAMP_PROGRESS_RESOURCE_OUTPUT_IDENTITIES[resource_name],
            )
            before_icn = font.parse_icn(
                before_payload,
                label=f"camp-progress-before:{resource_name}",
            )
            after_icn = font.parse_icn(
                after_payload,
                label=f"camp-progress-after:{resource_name}",
            )
            self.assertEqual(len(before_icn.sprites), 1, resource_name)
            self.assertEqual(len(after_icn.sprites), 1, resource_name)
            before_decoded = font._decode_sprite(
                before_icn.sprites[0],
                label=f"camp-progress-before:{resource_name}:0",
            )
            after_decoded = font._decode_sprite(
                after_icn.sprites[0],
                label=f"camp-progress-after:{resource_name}:0",
            )
            before_geometry = (
                before_decoded.offset_x,
                before_decoded.offset_y,
                before_decoded.width,
                before_decoded.height,
                before_decoded.animation,
            )
            after_geometry = (
                after_decoded.offset_x,
                after_decoded.offset_y,
                after_decoded.width,
                after_decoded.height,
                after_decoded.animation,
            )
            self.assertEqual(before_geometry, (0, 0, 640, 480, 0), resource_name)
            self.assertEqual(after_geometry, before_geometry, resource_name)
            self.assertEqual(after_decoded.transform, before_decoded.transform, resource_name)
            self.assertFalse(any(after_decoded.transform), resource_name)

            editable_rois = [
                tuple(int(value) for value in spec[roi_name])
                for spec in font.CAMP_PROGRESS_SPECS[resource_name]["texts"]
                for roi_name in ("mask_roi", "layout_roi")
            ]
            changed_pixels = 0
            for y in range(before_decoded.height):
                for x in range(before_decoded.width):
                    offset = y * before_decoded.width + x
                    changed = after_decoded.pixels[offset] != before_decoded.pixels[offset]
                    changed_pixels += int(changed)
                    if any(
                        roi_x <= x < roi_x + roi_width
                        and roi_y <= y < roi_y + roi_height
                        for roi_x, roi_y, roi_width, roi_height in editable_rois
                    ):
                        continue
                    self.assertFalse(changed, f"{resource_name}:{x},{y}")
            self.assertGreater(changed_pixels, 0, resource_name)

    def assert_fancy_main_menu_buttons_preserve_geometry_and_roi_exteriors(
        self,
        before: font.AggArchive,
        after: font.AggArchive,
    ) -> font.FancyMainMenuDonors:
        resource_name = font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME
        before_payload = before.get(resource_name).payload
        after_payload = after.get(resource_name).payload
        self.assertEqual(
            (len(before_payload), font.sha256_bytes(before_payload)),
            font.FANCY_MAIN_MENU_BUTTON_SOURCE_IDENTITY,
        )
        self.assertEqual(
            (len(after_payload), font.sha256_bytes(after_payload)),
            font.FANCY_MAIN_MENU_BUTTON_OUTPUT_IDENTITY,
        )
        before_icn = font.parse_icn(before_payload, label="fancy-menu-buttons-before")
        after_icn = font.parse_icn(after_payload, label="fancy-menu-buttons-after")
        self.assertEqual(len(before_icn.sprites), 20)
        self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))

        specs_by_index = {
            int(sprite_index): spec
            for spec in font.FANCY_MAIN_MENU_SPECS
            for sprite_index in spec["sprites"]
        }
        for sprite_index, (before_sprite, after_sprite) in enumerate(
            zip(before_icn.sprites, after_icn.sprites)
        ):
            if sprite_index not in specs_by_index:
                self.assertEqual(after_sprite, before_sprite, sprite_index)
                continue
            before_decoded = font._decode_sprite(
                before_sprite,
                label=f"fancy-menu-button-before:{sprite_index}",
            )
            after_decoded = font._decode_sprite(
                after_sprite,
                label=f"fancy-menu-button-after:{sprite_index}",
            )
            self.assertEqual(
                (
                    after_decoded.offset_x,
                    after_decoded.offset_y,
                    after_decoded.width,
                    after_decoded.height,
                    after_decoded.animation,
                ),
                (
                    before_decoded.offset_x,
                    before_decoded.offset_y,
                    before_decoded.width,
                    before_decoded.height,
                    before_decoded.animation,
                ),
            )
            x0, y0, width, height = font._fancy_main_menu_editable_roi(
                specs_by_index[sprite_index]
            )
            for y in range(before_decoded.height):
                for x in range(before_decoded.width):
                    if x0 <= x < x0 + width and y0 <= y < y0 + height:
                        continue
                    offset = y * before_decoded.width + x
                    self.assertEqual(after_decoded.pixels[offset], before_decoded.pixels[offset])
                    self.assertEqual(after_decoded.transform[offset], before_decoded.transform[offset])
        return font._fancy_main_menu_donors_from_button_payload(
            after_payload,
            label="fancy-menu-test-donors",
        )

    def assert_fancy_main_menu_heroes_preserves_geometry_and_roi_union_exterior(
        self,
        before: font.AggArchive,
        after: font.AggArchive,
        donors: font.FancyMainMenuDonors,
        variant: str,
    ) -> None:
        resource_name = font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME
        before_payload = before.get(resource_name).payload
        after_payload = after.get(resource_name).payload
        self.assertEqual(
            (len(before_payload), font.sha256_bytes(before_payload)),
            font.FANCY_MAIN_MENU_HEROES_SOURCE_IDENTITIES[variant],
        )
        self.assertEqual(
            (len(after_payload), font.sha256_bytes(after_payload)),
            font.FANCY_MAIN_MENU_HEROES_OUTPUT_IDENTITIES[variant],
        )
        before_icn = font.parse_icn(before_payload, label=f"fancy-heroes-{variant}-before")
        after_icn = font.parse_icn(after_payload, label=f"fancy-heroes-{variant}-after")
        self.assertEqual(len(before_icn.sprites), 1)
        self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))
        before_decoded = font._decode_sprite(before_icn.sprites[0], label=f"heroes-{variant}-before")
        after_decoded = font._decode_sprite(after_icn.sprites[0], label=f"heroes-{variant}-after")
        self.assertEqual(
            (
                after_decoded.offset_x,
                after_decoded.offset_y,
                after_decoded.width,
                after_decoded.height,
                after_decoded.animation,
            ),
            (
                before_decoded.offset_x,
                before_decoded.offset_y,
                before_decoded.width,
                before_decoded.height,
                before_decoded.animation,
            ),
        )
        rois = []
        for spec, donor_sprite in zip(font.FANCY_MAIN_MENU_SPECS, donors.sprites):
            x0, y0, width, height = font._fancy_main_menu_editable_roi(spec)
            rois.append((donor_sprite.offset_x + x0, donor_sprite.offset_y + y0, width, height))
        for y in range(before_decoded.height):
            for x in range(before_decoded.width):
                if any(
                    x0 <= x < x0 + width and y0 <= y < y0 + height
                    for x0, y0, width, height in rois
                ):
                    continue
                offset = y * before_decoded.width + x
                self.assertEqual(after_decoded.pixels[offset], before_decoded.pixels[offset])
                self.assertEqual(after_decoded.transform[offset], before_decoded.transform[offset])

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
                ("CAMPBKGG.ICN", b"partial-campaign-progress-set"),
            )
        )
        addition = make_sprite(font.FOREGROUND_PALETTE_INDEX)
        for mode in ("default", "custom"):
            rendered = font.RenderedFont(
                normal=(addition,) * font.KOREAN_GLYPH_COUNT,
                small=(addition,) * font.KOREAN_GLYPH_COUNT,
                metadata={"mode": mode},
            )
            with self.subTest(mode=mode), self.assertRaises(font.FontBuildError):
                font.rebuild_agg_fonts(
                    base_raw,
                    rendered,
                    label=f"synthetic-recruit-wrong-source:{mode}",
                )

    def test_rebuild_rejects_an_incomplete_image_ui_resource_set(self) -> None:
        base_raw = make_agg(
            (
                ("FONT.ICN", legacy_icn(1)),
                ("SMALFONT.ICN", legacy_icn(101)),
                ("REQUEST.ICN", b"incomplete-image-ui-resource-set"),
            )
        )
        addition = make_sprite(font.FOREGROUND_PALETTE_INDEX)
        for mode in ("default", "custom"):
            rendered = font.RenderedFont(
                normal=(addition,) * font.KOREAN_GLYPH_COUNT,
                small=(addition,) * font.KOREAN_GLYPH_COUNT,
                metadata={"mode": mode},
            )
            with self.subTest(mode=mode), self.assertRaises(font.FontBuildError):
                font.rebuild_agg_fonts(
                    base_raw,
                    rendered,
                    label=f"synthetic-incomplete-image-ui:{mode}",
                )

    def test_local_gog_custom_font_rebuilds_buttons_deterministically_and_preserves_pristine_regions(
        self,
    ) -> None:
        fixture_value = os.environ.get(LOCAL_GOG_ORIGINAL_AGG_ENV)
        if not fixture_value:
            self.skipTest(f"set {LOCAL_GOG_ORIGINAL_AGG_ENV} to a pristine GOG HEROES2.AGG")
        fixture = Path(fixture_value)
        if not fixture.is_file():
            self.skipTest(f"configured pristine GOG HEROES2.AGG is unavailable: {fixture}")

        selected_value = os.environ.get(LOCAL_CUSTOM_FONT_ENV)
        selected = Path(selected_value) if selected_value else WINDOWS_MALGUN_FONT
        if not selected.is_file():
            self.skipTest(
                f"set {LOCAL_CUSTOM_FONT_ENV} to a Korean OpenType font; "
                f"default candidate is unavailable: {selected}"
            )

        default_plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        custom_plan = font.make_font_plan(
            MAPPING,
            selected,
            fallback_path=DEFAULT_FONT,
            mode="custom",
        )
        if custom_plan.primary.sha256 == default_plan.primary.sha256:
            self.skipTest("custom font fixture is byte-identical to the canonical Nanum font")
        default_rendered = font.render_font(default_plan)
        custom_rendered = font.render_font(custom_plan)
        self.assertEqual(custom_rendered.metadata["mode"], "custom")
        self.assertGreater(len(custom_plan.primary_codepoints), 0)
        self.assertNotEqual(custom_rendered.normal, default_rendered.normal)
        self.assertNotEqual(custom_rendered.small, default_rendered.small)

        base_raw = fixture.read_bytes()
        custom_raw = font.rebuild_agg_fonts(
            base_raw,
            custom_rendered,
            label="local-gog-main-custom",
        )
        self.assertEqual(
            font.rebuild_agg_fonts(
                base_raw,
                custom_rendered,
                label="local-gog-main-custom-determinism",
            ),
            custom_raw,
        )
        before = font.parse_agg(base_raw, label="local-gog-main-custom-before")
        after = font.parse_agg(custom_raw, label="local-gog-main-custom-after")
        expected_main_changes = {
            *font.FONT_RESOURCE_NAMES,
            *font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
            *font.MENU132_RESOURCE_SOURCE_IDENTITIES,
            *font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            *font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES,
            font.RECRUIT_COST_RESOURCE_NAME,
            font.TOWNWIND_RESOURCE_NAME,
            font.TEXTBAR_RESOURCE_NAME,
            "CAMPXTRG.ICN",
            "CAMPXTRE.ICN",
        }
        self.assertEqual(
            set(font.changed_agg_resources(base_raw, custom_raw, label="local-gog-main-custom-diff")),
            expected_main_changes,
        )

        canonical_outputs: dict[str, tuple[int, str]] = {}
        for identities in (
            font.IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES,
            font.MENU132_RESOURCE_OUTPUT_IDENTITIES,
            font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
            font.GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
            font.EMBEDDED_UI_RESOURCE_OUTPUT_IDENTITIES,
        ):
            canonical_outputs.update(identities)
        available = {entry.name.upper() for entry in before.entries}
        for resource_name, canonical_identity in canonical_outputs.items():
            if resource_name not in available:
                continue
            payload = after.get(resource_name).payload
            self.assertNotEqual(
                (len(payload), font.sha256_bytes(payload)),
                canonical_identity,
                resource_name,
            )
        for resource_name, canonical_identity in (
            (
                font.RECRUIT_COST_RESOURCE_NAME,
                (font.RECRUIT_COST_OUTPUT_SIZE, font.RECRUIT_COST_OUTPUT_SHA256),
            ),
            (font.TOWNWIND_RESOURCE_NAME, font.TOWNWIND_OUTPUT_IDENTITY),
            (font.TEXTBAR_RESOURCE_NAME, font.TEXTBAR_OUTPUT_IDENTITY),
        ):
            payload = after.get(resource_name).payload
            self.assertNotEqual(
                (len(payload), font.sha256_bytes(payload)),
                canonical_identity,
                resource_name,
            )

        image_targets = (
            *font.IMAGE_UI_TEXT_TARGETS,
            {
                "resource": str(font.IMAGE_UI_WELL_MIRROR["target_resource"]),
                "sprite": int(font.IMAGE_UI_WELL_MIRROR["target_sprite"]),
                "roi": tuple(font.IMAGE_UI_WELL_MIRROR["target_roi"]),
            },
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            set(font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES),
            font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
            None,
            image_targets,
            group_label="custom-image-ui",
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            set(font.MENU132_RESOURCE_SOURCE_IDENTITIES),
            font.MENU132_RESOURCE_SOURCE_IDENTITIES,
            None,
            font.MENU132_TEXT_TARGETS,
            group_label="custom-menu132",
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {"CAMPXTRG.ICN", "CAMPXTRE.ICN"},
            font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            None,
            font.CAMPAIGN_BUTTON_TEXT_TARGETS,
            group_label="custom-campaign",
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            set(font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES),
            font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            None,
            font.GAME_BUTTON_TEXT_TARGETS,
            group_label="custom-game-button",
        )
        self.assert_embedded_ui_resources_preserve_non_targets_and_roi_union_exterior(
            before,
            after,
            canonical_output_identities=False,
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {font.TOWNWIND_RESOURCE_NAME},
            {font.TOWNWIND_RESOURCE_NAME: font.TOWNWIND_SOURCE_IDENTITY},
            None,
            (*font.TOWNWIND_COST_TARGETS, *font.TOWNWIND_BUTTON_TARGETS),
            group_label="custom-townwind",
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {font.TEXTBAR_RESOURCE_NAME},
            {font.TEXTBAR_RESOURCE_NAME: font.TEXTBAR_SOURCE_IDENTITY},
            None,
            font.TEXTBAR_TARGETS,
            group_label="custom-textbar",
        )

        before_cost = font.parse_icn(
            before.get(font.RECRUIT_COST_RESOURCE_NAME).payload,
            label="custom-cost-before",
        )
        after_cost = font.parse_icn(
            after.get(font.RECRUIT_COST_RESOURCE_NAME).payload,
            label="custom-cost-after",
        )
        self.assertEqual(after_cost.sprites[1:], before_cost.sprites[1:])
        cost_before = font._decode_sprite(before_cost.sprites[0], label="custom-cost-before:0")
        cost_after = font._decode_sprite(after_cost.sprites[0], label="custom-cost-after:0")
        self.assertEqual(
            (
                cost_after.offset_x,
                cost_after.offset_y,
                cost_after.width,
                cost_after.height,
                cost_after.animation,
            ),
            (
                cost_before.offset_x,
                cost_before.offset_y,
                cost_before.width,
                cost_before.height,
                cost_before.animation,
            ),
        )
        x0, y0, width, height = font.RECRUIT_COST_ROI
        for y in range(cost_before.height):
            for x in range(cost_before.width):
                if x0 <= x < x0 + width and y0 <= y < y0 + height:
                    continue
                offset = y * cost_before.width + x
                self.assertEqual(cost_after.pixels[offset], cost_before.pixels[offset])
                self.assertEqual(cost_after.transform[offset], cost_before.transform[offset])

        for resource_name in (
            font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME,
            font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME,
            "CAMPBKGG.ICN",
            "CAMPBKGE.ICN",
            "HSBTNS.ICN",
        ):
            self.assertEqual(after.get(resource_name).payload, before.get(resource_name).payload, resource_name)

        expansion_fixture = fixture.with_name("HEROES2X.AGG")
        if not expansion_fixture.is_file():
            self.skipTest(f"configured pristine GOG HEROES2X.AGG is unavailable: {expansion_fixture}")
        expansion_base_raw = expansion_fixture.read_bytes()
        expansion_custom_raw = font.rebuild_agg_fonts(
            expansion_base_raw,
            custom_rendered,
            label="local-gog-expansion-custom",
        )
        self.assertEqual(
            font.rebuild_agg_fonts(
                expansion_base_raw,
                custom_rendered,
                label="local-gog-expansion-custom-determinism",
            ),
            expansion_custom_raw,
        )
        expansion_before = font.parse_agg(
            expansion_base_raw,
            label="local-gog-expansion-custom-before",
        )
        expansion_after = font.parse_agg(
            expansion_custom_raw,
            label="local-gog-expansion-custom-after",
        )
        expected_expansion_changes = {
            *font.FONT_RESOURCE_NAMES,
            "X_CMPBTN.ICN",
            *font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES,
        }
        self.assertEqual(
            set(
                font.changed_agg_resources(
                    expansion_base_raw,
                    expansion_custom_raw,
                    label="local-gog-expansion-custom-diff",
                )
            ),
            expected_expansion_changes,
        )
        for resource_name in {"X_CMPBTN.ICN", *font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES}:
            payload = expansion_after.get(resource_name).payload
            canonical_identity = (
                font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES[resource_name]
                if resource_name == "X_CMPBTN.ICN"
                else font.EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES[resource_name]
            )
            self.assertNotEqual(
                (len(payload), font.sha256_bytes(payload)),
                canonical_identity,
                resource_name,
            )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            expansion_before,
            expansion_after,
            {"X_CMPBTN.ICN"},
            font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            None,
            font.CAMPAIGN_BUTTON_TEXT_TARGETS,
            group_label="custom-expansion-campaign",
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            expansion_before,
            expansion_after,
            set(font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES),
            font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES,
            None,
            font.EXPANSION_MENU_TEXT_TARGETS,
            group_label="custom-expansion-menu",
        )
        for resource_name in (
            font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME,
            "X_CMPBKG.ICN",
        ):
            self.assertEqual(
                expansion_after.get(resource_name).payload,
                expansion_before.get(resource_name).payload,
                resource_name,
            )

    def test_local_gog_iropke_default_matches_the_same_font_in_custom_mode(self) -> None:
        fixture_value = os.environ.get(LOCAL_GOG_ORIGINAL_AGG_ENV)
        if not fixture_value:
            self.skipTest(f"set {LOCAL_GOG_ORIGINAL_AGG_ENV} to a pristine GOG HEROES2.AGG")
        fixture = Path(fixture_value)
        if not fixture.is_file():
            self.skipTest(f"configured pristine GOG HEROES2.AGG is unavailable: {fixture}")

        iropke_value = os.environ.get(LOCAL_IROPKE_FONT_ENV)
        if not iropke_value:
            self.skipTest(f"set {LOCAL_IROPKE_FONT_ENV} to a locally owned IropkeBatangM.ttf fixture")
        iropke = Path(iropke_value)
        if not iropke.is_file():
            self.skipTest(f"configured IropkeBatangM.ttf is unavailable: {iropke}")

        default_plan = font.make_font_plan(
            MAPPING,
            iropke,
            fallback_path=DEFAULT_FONT,
            mode="default",
        )
        custom_plan = font.make_font_plan(
            MAPPING,
            iropke,
            fallback_path=DEFAULT_FONT,
            mode="custom",
        )
        self.assertEqual(default_plan.primary.sha256, IROPKE_FONT_SHA256)
        self.assertEqual(default_plan.fallback_codepoints, frozenset())

        default_rendered = font.render_font(default_plan)
        custom_rendered = font.render_font(custom_plan)
        self.assertEqual(default_rendered.normal, custom_rendered.normal)
        self.assertEqual(default_rendered.small, custom_rendered.small)

        base_raw = fixture.read_bytes()
        default_raw = font.rebuild_agg_fonts(
            base_raw,
            default_rendered,
            label="local-gog-main-iropke-default",
        )
        custom_raw = font.rebuild_agg_fonts(
            base_raw,
            custom_rendered,
            label="local-gog-main-iropke-custom",
        )
        self.assertEqual(default_raw, custom_raw)

    def test_local_gog_main_agg_rebuilds_button_ui_and_recruit_cost_rasters(self) -> None:
        fixture_value = os.environ.get(LOCAL_GOG_ORIGINAL_AGG_ENV)
        if not fixture_value:
            self.skipTest(f"set {LOCAL_GOG_ORIGINAL_AGG_ENV} to a pristine GOG HEROES2.AGG")
        fixture = Path(fixture_value)
        if not fixture.is_file():
            self.skipTest(f"configured pristine GOG HEROES2.AGG is unavailable: {fixture}")

        base_raw = fixture.read_bytes()
        plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        rendered = font.render_font(plan)
        rebuilt_raw = font.rebuild_agg_fonts(base_raw, rendered, label="local-gog-main")
        before = font.parse_agg(base_raw, label="local-gog-main-before")
        after = font.parse_agg(rebuilt_raw, label="local-gog-main-after")

        self.assertTrue(
            {entry.name.upper() for entry in before.entries}.isdisjoint(
                font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES
            )
        )
        self.assertEqual(
            font.rebuild_agg_fonts(base_raw, rendered, label="local-gog-main-determinism"),
            rebuilt_raw,
        )
        self.assertEqual(len(after.entries), len(before.entries))
        for before_entry, after_entry in zip(before.entries, after.entries):
            self.assertEqual(
                (after_entry.index, after_entry.name, after_entry.name_slot, after_entry.hash_word),
                (before_entry.index, before_entry.name, before_entry.name_slot, before_entry.hash_word),
            )

        for resource_name in {
            *font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
            *font.MENU132_RESOURCE_SOURCE_IDENTITIES,
            *font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            *font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES,
            "CAMPBKGG.ICN",
            "CAMPBKGE.ICN",
            font.TOWNWIND_RESOURCE_NAME,
            font.TEXTBAR_RESOURCE_NAME,
            font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME,
            font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME,
            "CAMPXTRG.ICN",
            "CAMPXTRE.ICN",
            font.RECRUIT_COST_RESOURCE_NAME,
            "HSBTNS.ICN",
        }:
            source_payload = before.get(resource_name).payload
            source_icn = font.parse_icn(source_payload, label=f"local-gog-noop:{resource_name}")
            self.assertEqual(font.pack_icn(source_icn.sprites), source_payload, resource_name)

        self.assertEqual(
            set(font.changed_agg_resources(base_raw, rebuilt_raw, label="local-gog-main-diff")),
            {
                *font.FONT_RESOURCE_NAMES,
                *font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES,
                *font.MENU132_RESOURCE_SOURCE_IDENTITIES,
                *font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
                *font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES,
                font.RECRUIT_COST_RESOURCE_NAME,
                font.TOWNWIND_RESOURCE_NAME,
                font.TEXTBAR_RESOURCE_NAME,
                "CAMPXTRG.ICN",
                "CAMPXTRE.ICN",
            },
        )
        before_cost = before.get(font.RECRUIT_COST_RESOURCE_NAME)
        after_cost = after.get(font.RECRUIT_COST_RESOURCE_NAME)
        self.assertEqual(len(before_cost.payload), font.RECRUIT_COST_SOURCE_SIZE)
        self.assertEqual(font.sha256_bytes(before_cost.payload), font.RECRUIT_COST_SOURCE_SHA256)
        self.assertEqual(len(after_cost.payload), font.RECRUIT_COST_OUTPUT_SIZE)
        self.assertEqual(font.sha256_bytes(after_cost.payload), font.RECRUIT_COST_OUTPUT_SHA256)

        targets_by_resource: dict[str, list[dict[str, object]]] = {}
        for target in font.IMAGE_UI_TEXT_TARGETS:
            targets_by_resource.setdefault(str(target["resource"]), []).append(target)
        for resource_name, source_identity in font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES.items():
            before_payload = before.get(resource_name).payload
            after_payload = after.get(resource_name).payload
            self.assertEqual((len(before_payload), font.sha256_bytes(before_payload)), source_identity)
            self.assertEqual(
                (len(after_payload), font.sha256_bytes(after_payload)),
                font.IMAGE_UI_RESOURCE_OUTPUT_IDENTITIES[resource_name],
            )

            before_icn = font.parse_icn(before_payload, label=f"local-gog-image-before:{resource_name}")
            after_icn = font.parse_icn(after_payload, label=f"local-gog-image-after:{resource_name}")
            self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))
            resource_targets = targets_by_resource.get(resource_name, [])
            if resource_name == font.IMAGE_UI_WELL_MIRROR["target_resource"]:
                resource_targets = [
                    {
                        "sprite": font.IMAGE_UI_WELL_MIRROR["target_sprite"],
                        "roi": font.IMAGE_UI_WELL_MIRROR["target_roi"],
                    }
                ]
            target_indices = {int(target["sprite"]) for target in resource_targets}
            for sprite_index, (before_sprite, after_sprite) in enumerate(zip(before_icn.sprites, after_icn.sprites)):
                if sprite_index not in target_indices:
                    self.assertEqual(after_sprite, before_sprite, f"{resource_name}:{sprite_index}")
                    continue
                target = next(target for target in resource_targets if int(target["sprite"]) == sprite_index)
                roi = tuple(int(value) for value in target["roi"])
                before_decoded = font._decode_sprite(before_sprite, label=f"before:{resource_name}:{sprite_index}")
                after_decoded = font._decode_sprite(after_sprite, label=f"after:{resource_name}:{sprite_index}")
                self.assertEqual(
                    (
                        after_decoded.offset_x,
                        after_decoded.offset_y,
                        after_decoded.width,
                        after_decoded.height,
                        after_decoded.animation,
                    ),
                    (
                        before_decoded.offset_x,
                        before_decoded.offset_y,
                        before_decoded.width,
                        before_decoded.height,
                        before_decoded.animation,
                    ),
                )
                x0, y0, width, height = roi
                for y in range(before_decoded.height):
                    for x in range(before_decoded.width):
                        if x0 <= x < x0 + width and y0 <= y < y0 + height:
                            continue
                        offset = y * before_decoded.width + x
                        self.assertEqual(after_decoded.pixels[offset], before_decoded.pixels[offset])
                        self.assertEqual(after_decoded.transform[offset], before_decoded.transform[offset])

        menu_targets_by_resource: dict[str, list[dict[str, object]]] = {}
        for target in font.MENU132_TEXT_TARGETS:
            menu_targets_by_resource.setdefault(str(target["resource"]), []).append(target)
        for resource_name, source_identity in font.MENU132_RESOURCE_SOURCE_IDENTITIES.items():
            before_payload = before.get(resource_name).payload
            after_payload = after.get(resource_name).payload
            self.assertEqual((len(before_payload), font.sha256_bytes(before_payload)), source_identity)
            self.assertEqual(
                (len(after_payload), font.sha256_bytes(after_payload)),
                font.MENU132_RESOURCE_OUTPUT_IDENTITIES[resource_name],
            )

            before_icn = font.parse_icn(before_payload, label=f"local-gog-menu132-before:{resource_name}")
            after_icn = font.parse_icn(after_payload, label=f"local-gog-menu132-after:{resource_name}")
            self.assertEqual(len(after_icn.sprites), len(before_icn.sprites))
            resource_targets = menu_targets_by_resource[resource_name]
            targets_by_index = {
                int(target["sprite"]): target
                for target in resource_targets
            }
            for sprite_index, (before_sprite, after_sprite) in enumerate(zip(before_icn.sprites, after_icn.sprites)):
                if sprite_index not in targets_by_index:
                    self.assertEqual(after_sprite, before_sprite, f"{resource_name}:{sprite_index}")
                    continue

                target = targets_by_index[sprite_index]
                before_decoded = font._decode_sprite(
                    before_sprite,
                    label=f"menu132-before:{resource_name}:{sprite_index}",
                )
                after_decoded = font._decode_sprite(
                    after_sprite,
                    label=f"menu132-after:{resource_name}:{sprite_index}",
                )
                self.assertEqual(
                    (
                        after_decoded.offset_x,
                        after_decoded.offset_y,
                        after_decoded.width,
                        after_decoded.height,
                        after_decoded.animation,
                    ),
                    (
                        before_decoded.offset_x,
                        before_decoded.offset_y,
                        before_decoded.width,
                        before_decoded.height,
                        before_decoded.animation,
                    ),
                )
                x0, y0, width, height = (int(value) for value in target["roi"])
                for y in range(before_decoded.height):
                    for x in range(before_decoded.width):
                        if x0 <= x < x0 + width and y0 <= y < y0 + height:
                            continue
                        offset = y * before_decoded.width + x
                        self.assertEqual(after_decoded.pixels[offset], before_decoded.pixels[offset])
                        self.assertEqual(after_decoded.transform[offset], before_decoded.transform[offset])

        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {"CAMPXTRG.ICN", "CAMPXTRE.ICN"},
            font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
            font.CAMPAIGN_BUTTON_TEXT_TARGETS,
            group_label="campaign",
        )
        for resource_name in ("CAMPBKGG.ICN", "CAMPBKGE.ICN"):
            self.assertEqual(
                after.get(resource_name).payload,
                before.get(resource_name).payload,
                resource_name,
            )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            set(font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES),
            font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            font.GAME_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
            font.GAME_BUTTON_TEXT_TARGETS,
            group_label="game-button",
        )
        self.assert_embedded_ui_resources_preserve_non_targets_and_roi_union_exterior(
            before,
            after,
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {font.TOWNWIND_RESOURCE_NAME},
            {font.TOWNWIND_RESOURCE_NAME: font.TOWNWIND_SOURCE_IDENTITY},
            {font.TOWNWIND_RESOURCE_NAME: font.TOWNWIND_OUTPUT_IDENTITY},
            (*font.TOWNWIND_COST_TARGETS, *font.TOWNWIND_BUTTON_TARGETS),
            group_label="townwind",
        )
        townwind_before = font.parse_icn(
            before.get(font.TOWNWIND_RESOURCE_NAME).payload,
            label="townwind-before-exact",
        )
        townwind_after = font.parse_icn(
            after.get(font.TOWNWIND_RESOURCE_NAME).payload,
            label="townwind-after-exact",
        )
        self.assertEqual(
            {
                sprite_index
                for sprite_index, (before_sprite, after_sprite) in enumerate(
                    zip(townwind_before.sprites, townwind_after.sprites)
                )
                if before_sprite != after_sprite
            },
            {3, 9, 10, 20, 21},
        )
        for sprite_index, (before_sprite, after_sprite) in enumerate(
            zip(townwind_before.sprites, townwind_after.sprites)
        ):
            self.assertEqual(
                font._decode_sprite(
                    after_sprite,
                    label=f"townwind-after-transform:{sprite_index}",
                ).transform,
                font._decode_sprite(
                    before_sprite,
                    label=f"townwind-before-transform:{sprite_index}",
                ).transform,
                f"TOWNWIND.ICN:{sprite_index}:transform",
            )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {font.TEXTBAR_RESOURCE_NAME},
            {font.TEXTBAR_RESOURCE_NAME: font.TEXTBAR_SOURCE_IDENTITY},
            {font.TEXTBAR_RESOURCE_NAME: font.TEXTBAR_OUTPUT_IDENTITY},
            font.TEXTBAR_TARGETS,
            group_label="textbar",
        )
        for resource_name in (
            font.FANCY_MAIN_MENU_BUTTON_RESOURCE_NAME,
            font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME,
        ):
            self.assertEqual(
                after.get(resource_name).payload,
                before.get(resource_name).payload,
                resource_name,
            )

        mirror = font.IMAGE_UI_WELL_MIRROR
        wellxtra = font.parse_icn(after.get(str(mirror["source_resource"])).payload, label="wellxtra-after")
        wellbkg = font.parse_icn(after.get(str(mirror["target_resource"])).payload, label="wellbkg-after")
        donor = font._decode_sprite(wellxtra.sprites[int(mirror["source_sprite"])], label="wellxtra-donor")
        recipient = font._decode_sprite(wellbkg.sprites[int(mirror["target_sprite"])], label="wellbkg-recipient")
        sx, sy, sw, sh = (int(value) for value in mirror["source_roi"])
        tx, ty, tw, th = (int(value) for value in mirror["target_roi"])
        self.assertEqual((sw, sh), (tw, th))
        for row in range(sh):
            donor_start = (sy + row) * donor.width + sx
            recipient_start = (ty + row) * recipient.width + tx
            self.assertEqual(
                recipient.pixels[recipient_start : recipient_start + tw],
                donor.pixels[donor_start : donor_start + sw],
            )
            self.assertEqual(
                recipient.transform[recipient_start : recipient_start + tw],
                donor.transform[donor_start : donor_start + sw],
            )

        self.assertEqual(after.get("HSBTNS.ICN").payload, before.get("HSBTNS.ICN").payload)

        for before_entry, after_entry in zip(before.entries, after.entries):
            if before_entry.name.upper() in {
                *(name.upper() for name in font.FONT_RESOURCE_NAMES),
                *(name.upper() for name in font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES),
                *(name.upper() for name in font.MENU132_RESOURCE_SOURCE_IDENTITIES),
                *(name.upper() for name in font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES),
                *(name.upper() for name in font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES),
                *(name.upper() for name in font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES),
                font.RECRUIT_COST_RESOURCE_NAME,
                font.TOWNWIND_RESOURCE_NAME,
                font.TEXTBAR_RESOURCE_NAME,
            }:
                continue
            self.assertEqual(after_entry.payload, before_entry.payload, before_entry.name)

    def test_local_gog_expansion_agg_rebuilds_only_fonts(self) -> None:
        fixture_value = os.environ.get(LOCAL_GOG_ORIGINAL_AGG_ENV)
        if not fixture_value:
            self.skipTest(f"set {LOCAL_GOG_ORIGINAL_AGG_ENV} to a pristine GOG HEROES2.AGG")
        fixture = Path(fixture_value).with_name("HEROES2X.AGG")
        if not fixture.is_file():
            self.skipTest(f"configured pristine GOG HEROES2X.AGG is unavailable: {fixture}")

        base_raw = fixture.read_bytes()
        plan = font.make_font_plan(MAPPING, DEFAULT_FONT, mode="default")
        rendered = font.render_font(plan)
        rebuilt_raw = font.rebuild_agg_fonts(
            base_raw,
            rendered,
            label="local-gog-expansion",
        )
        before = font.parse_agg(base_raw, label="local-gog-expansion-before")
        after = font.parse_agg(rebuilt_raw, label="local-gog-expansion-after")

        self.assertEqual(
            font.rebuild_agg_fonts(
                base_raw,
                rendered,
                label="local-gog-expansion-determinism",
            ),
            rebuilt_raw,
        )

        self.assertEqual(
            after.get(font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).payload,
            before.get(font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).payload,
        )

        self.assertTrue(
            {entry.name.upper() for entry in before.entries}.isdisjoint(font.IMAGE_UI_RESOURCE_SOURCE_IDENTITIES)
        )
        self.assertTrue(
            {entry.name.upper() for entry in before.entries}.isdisjoint(font.MENU132_RESOURCE_SOURCE_IDENTITIES)
        )
        self.assertTrue(
            {entry.name.upper() for entry in before.entries}.isdisjoint(
                font.GAME_BUTTON_RESOURCE_SOURCE_IDENTITIES
            )
        )
        self.assertTrue(
            {entry.name.upper() for entry in before.entries}.isdisjoint(
                font.EMBEDDED_UI_RESOURCE_SOURCE_IDENTITIES
            )
        )
        self.assertNotIn(
            font.TOWNWIND_RESOURCE_NAME,
            {entry.name.upper() for entry in before.entries},
        )
        self.assertNotIn(
            font.TEXTBAR_RESOURCE_NAME,
            {entry.name.upper() for entry in before.entries},
        )
        self.assertEqual(
            {entry.name.upper() for entry in before.entries}
            & set(font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES),
            {"X_CMPBTN.ICN"},
        )
        self.assertEqual(
            {entry.name.upper() for entry in before.entries}
            & set(font.CAMP_PROGRESS_RESOURCE_SOURCE_IDENTITIES),
            {"X_CMPBKG.ICN"},
        )
        source_campaign_payload = before.get("X_CMPBTN.ICN").payload
        source_campaign_icn = font.parse_icn(
            source_campaign_payload,
            label="local-gog-expansion-noop:X_CMPBTN.ICN",
        )
        self.assertEqual(
            font.pack_icn(source_campaign_icn.sprites),
            source_campaign_payload,
        )
        source_progress_payload = before.get("X_CMPBKG.ICN").payload
        source_progress_icn = font.parse_icn(
            source_progress_payload,
            label="local-gog-expansion-noop:X_CMPBKG.ICN",
        )
        self.assertEqual(
            font.pack_icn(source_progress_icn.sprites),
            source_progress_payload,
        )
        for resource_name in font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES:
            source_payload = before.get(resource_name).payload
            source_icn = font.parse_icn(
                source_payload,
                label=f"local-gog-expansion-noop:{resource_name}",
            )
            self.assertEqual(font.pack_icn(source_icn.sprites), source_payload, resource_name)
        source_heroes_payload = before.get(font.FANCY_MAIN_MENU_HEROES_RESOURCE_NAME).payload
        source_heroes_icn = font.parse_icn(
            source_heroes_payload,
            label="local-gog-expansion-noop:HEROES.ICN",
        )
        self.assertEqual(font.pack_icn(source_heroes_icn.sprites), source_heroes_payload)
        self.assertEqual(
            set(font.changed_agg_resources(base_raw, rebuilt_raw, label="local-gog-expansion-diff")),
            {
                *font.FONT_RESOURCE_NAMES,
                "X_CMPBTN.ICN",
                *font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES,
            },
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            {"X_CMPBTN.ICN"},
            font.CAMPAIGN_BUTTON_RESOURCE_SOURCE_IDENTITIES,
            font.CAMPAIGN_BUTTON_RESOURCE_OUTPUT_IDENTITIES,
            font.CAMPAIGN_BUTTON_TEXT_TARGETS,
            group_label="campaign",
        )
        self.assertEqual(
            after.get("X_CMPBKG.ICN").payload,
            before.get("X_CMPBKG.ICN").payload,
        )
        self.assert_text_button_resources_preserve_non_targets_and_roi_exteriors(
            before,
            after,
            set(font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES),
            font.EXPANSION_MENU_RESOURCE_SOURCE_IDENTITIES,
            font.EXPANSION_MENU_RESOURCE_OUTPUT_IDENTITIES,
            font.EXPANSION_MENU_TEXT_TARGETS,
            group_label="expansion-menu",
        )

        before_new_campaign = font.parse_icn(
            before.get("X_NEWCMP.ICN").payload,
            label="expansion-menu-blank-before:X_NEWCMP.ICN",
        )
        after_new_campaign = font.parse_icn(
            after.get("X_NEWCMP.ICN").payload,
            label="expansion-menu-blank-after:X_NEWCMP.ICN",
        )
        for sprite_index in (1, 3, 5, 7, 9):
            self.assertEqual(
                after_new_campaign.sprites[sprite_index],
                before_new_campaign.sprites[sprite_index],
                f"X_NEWCMP.ICN:{sprite_index}",
            )

        self.assertEqual(len(rebuilt_raw), 2_981_224)
        self.assertEqual(
            font.sha256_bytes(rebuilt_raw),
            "4FC7AAA812434ADCF6CCA4B19D5861C478D1E77BAA6761853A705E8A7A056EDD",
        )


if __name__ == "__main__":
    unittest.main()
