"""Preserve Hangul ink while correcting measured low-resolution Iropke drift."""
from dataclasses import replace
from pathlib import Path
import unittest

from tools.release import homm2_font as font


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "translations/font/mapping874.fixed-interface-font.txt"
IROPKE = ROOT / "packaging/release_assets/fonts/IropkeBatangM.ttf"
EXPECTED_RAISED = {
    14: set("술쓴숙승쓸쏩슬솟쏟웅용유우은속습솔올울운웁율온숨음순손움옥읍욕옮육솜숲옵옷웃송숫슨"),
    11: set("을울율웅용유우술은늘올운웁온음움옥쓸읍놀욕옮육놓늙슬옵옷웃"),
}


def foreground(sprite):
    decoded = font._decode_sprite(sprite, label="alignment-test")
    return {
        (decoded.offset_x + index % decoded.width, decoded.offset_y + index // decoded.width)
        for index, (pixel, flag) in enumerate(zip(decoded.pixels, decoded.transform))
        if flag == 0 and pixel == font.FOREGROUND_PALETTE_INDEX
    }


class IropkeOpticalAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = font.make_font_plan(MAPPING, IROPKE, mode="default")
        cls.characters = {row.codepoint: row.character for row in cls.plan.mapping}
        cls.layouts = {}
        for size, width, height in ((14, 13, 14), (11, 11, 12)):
            cls.layouts[size] = font._build_face_layout(
                cls.plan.primary, cls.characters, requested_pixel_size=size,
                cell_width=width, cell_height=height,
            )

    def test_only_independently_measured_downward_outliers_move_one_pixel(self):
        for size, layout in self.layouts.items():
            self.assertEqual({chr(cp) for cp in layout.optical_offsets}, EXPECTED_RAISED[size])
            self.assertEqual(set(layout.optical_offsets.values()), {-1})
            self.assertEqual(len(layout.optical_offsets), 41 if size == 14 else 29)
            # Shorter horizontal forms and naturally high ㅎ/ㅊ remain native.
            for ch in "주조소가고구그기간곤군근긴각곡국극과괴궤귀의초호효흐츠영병력":
                self.assertNotIn(ord(ch), layout.optical_offsets)

    def test_all_874_masks_are_exact_translations_without_reshaping_or_clipping(self):
        for size, layout in self.layouts.items():
            native_layout = replace(layout, optical_offsets={})
            for cp, glyph in layout.glyphs.items():
                before = font._render_sprite(native_layout, cp)
                after = font._render_sprite(layout, cp)
                dy = layout.optical_offsets.get(cp, 0)
                self.assertEqual(foreground(after), {(x, y + dy) for x, y in foreground(before)}, chr(cp))
                self.assertEqual(after.offset_x, before.offset_x)
                self.assertEqual(after.width, before.width)
                self.assertEqual(after.offset_y + after.height, layout.cell_height)
                self.assertTrue(all(0 <= y < layout.cell_height for x, y in foreground(after)))
                self.assertEqual(font.parse_icn(font.pack_icn((after,)), label="roundtrip").sprites, (after,))
                if dy == 0:
                    self.assertEqual(after, before, chr(cp))

    def test_yeong_ung_center_gap_drops_from_one_and_half_to_half_a_pixel(self):
        for size, layout in self.layouts.items():
            bounds = {}
            for ch in "영웅":
                points = foreground(font._render_sprite(layout, ord(ch)))
                bounds[ch] = (min(y for x, y in points), max(y for x, y in points))
            self.assertEqual(bounds["영"], (0, 12) if size == 14 else (0, 10))
            self.assertEqual(bounds["웅"], (1, 12) if size == 14 else (1, 10))
            self.assertEqual((sum(bounds["웅"]) - sum(bounds["영"])) / 2, 0.5)

    def test_same_iropke_in_custom_mode_has_the_same_glyphs(self):
        default = font.render_font(self.plan)
        custom = font.render_font(font.make_font_plan(MAPPING, IROPKE, mode="custom"))
        self.assertEqual(default.normal, custom.normal)
        self.assertEqual(default.small, custom.small)

    def test_policy_is_pinned_to_exact_face_and_measured_pixel_sizes(self):
        layout = self.layouts[14]
        for face, size in (
            (replace(self.plan.primary, sha256="0" * 64), 14),
            (replace(self.plan.primary, face_index=1), 14),
            (self.plan.primary, 12),
            (self.plan.primary, 13),
        ):
            self.assertEqual(font._iropke_optical_offsets(face, size, layout.glyphs), {})


if __name__ == "__main__":
    unittest.main()
