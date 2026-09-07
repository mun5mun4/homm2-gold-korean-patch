"""Native button relief regressions using generated, redistributable fixtures."""

from dataclasses import replace
from pathlib import Path
import unittest

from tools.release import homm2_font as font


ROOT = Path(__file__).resolve().parents[1]


def encode(sprite: font._DecodedSprite) -> font.Sprite:
    return font.Sprite(
        sprite.offset_x, sprite.offset_y, sprite.width, sprite.height, sprite.animation,
        font._encode_sprite_data(sprite.width, sprite.height, sprite.pixels, sprite.transform),
    )


class SculptedButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        plan = font.make_font_plan(
            ROOT / "translations/font/mapping874.fixed-interface-font.txt",
            ROOT / "packaging/release_assets/fonts/IropkeBatangM.ttf",
            fallback_path=ROOT / "packaging/release_assets/fonts/NanumGothicCoding-Regular.ttf",
            mode="default",
        )
        rendered = font.render_font(plan)
        blank = font.Sprite(0, 0, 1, 1, 0, b"\x81\x00\x80")
        cls.normal = (blank,) * font.KOREAN_FIRST_INDEX + rendered.normal
        cls.small = (blank,) * font.KOREAN_FIRST_INDEX + rendered.small
        cls.mapping = rendered.mapping

    def fixture(self, target, width=96, height=25, original_marks=None):
        target = {key: value for key, value in target.items() if not key.startswith("donor_")}
        pixels = bytearray([target["background"]]) * (width * height)
        for (x, y), value in (original_marks or {}).items():
            pixels[y * width + x] = value
        original = font._DecodedSprite(7, -3, width, height, 0, bytes(pixels), bytes(width * height))
        sprite = encode(original)
        source = font.pack_icn((sprite,) * (target["sprite"] + 1))
        localized = font._localize_image_ui_text_resource(
            source, (target,), self.normal, self.mapping, {}, label="synthetic-relief",
        )
        current = font._decode_sprite(
            font.parse_icn(localized, label="synthetic-localized").sprites[target["sprite"]],
            label="synthetic-current",
        )
        return original, current, target

    def render(self, original, current, target):
        return font._sculpted_button_sprite(
            original, current, target, self.normal, self.small, self.mapping,
        )

    def test_dark_strokes_and_lower_left_bevel_preserve_glyphs_and_transparency(self):
        for interface, state, background, dark_tones in (
            ("good", "released", 41, {56, 51}),
            ("good", "pressed", 45, {59, 54}),
            ("evil", "released", 17, {32, 28}),
            ("evil", "pressed", 21, {33, 30}),
            ("town", "released", 120, {129, 126}),
            ("town", "pressed", 122, {61, 128}),
        ):
            with self.subTest(interface=interface, state=state):
                target = dict(font.IMAGE_UI_TEXT_TARGETS[0], interface=interface, state=state, background=background)
                original, current, target = self.fixture(target)
                after, metrics = self.render(original, current, target)
                foreground, shadow = font._sculpted_button_masks(target, self.normal, self.small, self.mapping)
                self.assertTrue(foreground)
                self.assertTrue(all(after.pixels[y * after.width + x] in dark_tones for x, y in foreground))
                bevel = {(x - 1, y + 1) for x, y in foreground} - foreground
                bevel = {point for point in bevel if font._sculpted_inside(*point, target["roi"])}
                self.assertEqual(metrics["bevel_pixels"], len(bevel))
                self.assertTrue(all(after.pixels[y * after.width + x] in set(metrics["palette_tones"][2:]) for x, y in bevel))
                # The previous lower-right shadow must not survive beside the new relief.
                self.assertTrue(all(after.pixels[y * after.width + x] == background for x, y in shadow - bevel))
                self.assertEqual(after.transform, current.transform)
                font._require_outside_roi_exact(current, after, tuple(target["roi"]), label="synthetic-relief-ROI")
                self.assertEqual(font._decode_sprite(encode(after), label="synthetic-roundtrip"), after)

    def test_corner_glints_are_restored_without_restoring_white_english_letters(self):
        target = dict(font.IMAGE_UI_TEXT_TARGETS[0], roi=(6, 4, 83, 17))
        # A diagonal corner glint and the white highlight of a letter T. The
        # previous broad color/bounding-box rule incorrectly restored this T.
        glint = {(14, 4), (13, 5), (12, 6)}
        english_t = {(x, 8) for x in range(69, 74)} | {(71, y) for y in range(9, 15)}
        original, current, target = self.fixture(target, original_marks={pt: 10 for pt in glint | english_t})
        after, metrics = self.render(original, current, target)
        self.assertEqual(metrics["restored_glint_pixels"], len(glint))
        self.assertTrue(all(after.pixels[y * after.width + x] == 10 for x, y in glint))
        self.assertTrue(all(after.pixels[y * after.width + x] == target["background"] for x, y in english_t))

    def test_flat_campaign_captions_remain_flat(self):
        target = dict(font.EXPANSION_MENU_TEXT_TARGETS[0])
        original, current, target = self.fixture(target, 132, 62)
        after, metrics = self.render(original, current, target)
        self.assertEqual(after, current)
        self.assertEqual(metrics["changed_pixels"], 0)
        self.assertTrue(metrics["preserved_style"])

    def test_original_english_top_fragment_cleanup_does_not_touch_the_frame(self):
        target = next(t for t in font.SCULPTED_BUTTON_TEXT_TARGETS if t["resource"] == "BTNNEWGM.ICN" and t["sprite"] == 4)
        marks = {(37, 6): 43, (36, 7): 46, (45, 7): 39, (128, 7): 40}
        original, current, target = self.fixture(target, 132, 62, marks)
        after, metrics = self.render(original, current, target)
        self.assertEqual(metrics["additional_rois"], [[36, 6, 64, 2]])
        self.assertEqual(metrics["removed_original_english_fragment_pixels"], 3)
        self.assertEqual(after.pixels[7 * after.width + 128], 40)
        for x, y in ((37, 6), (36, 7), (45, 7)):
            self.assertEqual(after.pixels[y * after.width + x], 41)
        font._require_outside_rois_exact(
            current, after, [tuple(target["roi"]), (36, 6, 64, 2)], label="synthetic-fragment-ROI",
        )

    def test_unexpected_generated_glyph_pixels_fail_before_restyling(self):
        original, current, target = self.fixture(font.IMAGE_UI_TEXT_TARGETS[0])
        foreground, _ = font._sculpted_button_masks(target, self.normal, self.small, self.mapping)
        x, y = next(iter(foreground))
        pixels = bytearray(current.pixels)
        pixels[y * current.width + x] = 36
        with self.assertRaisesRegex(font.FontBuildError, "glyph identity mismatch"):
            self.render(original, replace(current, pixels=bytes(pixels)), target)


if __name__ == "__main__":
    unittest.main()
