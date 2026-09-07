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
        self.assertGreater(metrics["changed_pixels"], 0)
        self.assertEqual(set(after.pixels), set(current.pixels))
        ink = [i // after.width for i, pixel in enumerate(after.pixels) if pixel == 32]
        self.assertLessEqual(abs((min(ink) + max(ink)) / 2 - 27.5), 0.5)
        self.assertTrue(metrics["preserved_style"])

    def test_map_menu_text_is_centered_on_the_face_in_both_states(self):
        for index in range(6):
            target = next(t for t in font.SCULPTED_BUTTON_TEXT_TARGETS
                          if t["resource"] == "X_MAPMNU.ICN" and t["sprite"] == index)
            original, current, target = self.fixture(target, 132, 62)
            after, metrics = self.render(original, current, target)
            ink = [(i % after.width, i // after.width) for i, pixel in enumerate(after.pixels)
                   if pixel in set(metrics["palette_tones"])]
            with self.subTest(index=index):
                self.assertEqual(metrics["vertical_alignment_shift"], -3)
                self.assertEqual((min(y for x, y in ink) + max(y for x, y in ink)) / 2,
                                 27.5 + index % 2)
                self.assertEqual(after.transform, current.transform)
                self.assertEqual((after.offset_x, after.offset_y), (current.offset_x, current.offset_y))
                # The formerly painted lowest row is blank after moving upward.
                self.assertTrue(all(after.pixels[(37 + index % 2) * 132 + x] == target["background"]
                                    for x in range(8, 124)))

    def test_two_line_menu_label_is_centered_as_one_block(self):
        target = next(t for t in font.SCULPTED_BUTTON_TEXT_TARGETS
                      if t["resource"] == "BTNMODEM.ICN" and t["sprite"] == 0)
        original, current, target = self.fixture(target, 132, 62)
        after, metrics = self.render(original, current, target)
        ink_rows = [i // 132 for i, pixel in enumerate(after.pixels)
                    if pixel in set(metrics["palette_tones"])]
        self.assertLessEqual(abs((min(ink_rows) + max(ink_rows)) / 2 - 27.5), 0.5)
        font._require_outside_roi_exact(current, after, tuple(target["roi"]), label="centered-two-line")

    def test_recruit_maximum_text_uses_one_pressed_displacement(self):
        masks = []
        for index, expected_shift in ((4, -3), (5, -4)):
            target = next(t for t in font.SCULPTED_BUTTON_TEXT_TARGETS
                          if t["resource"] == "RECRUIT.ICN" and t["sprite"] == index)
            frame_top = 21 + index % 2
            marks = {(x, y): 45 + y - frame_top for y in range(frame_top, frame_top + 4)
                     for x in range(8, 60)}
            original, current, target = self.fixture(target, 66, 30, marks)
            after, metrics = self.render(original, current, target)
            ink = {(i % 66, i // 66) for i, pixel in enumerate(after.pixels)
                   if pixel in set(metrics["palette_tones"])}
            self.assertEqual(metrics["vertical_alignment_shift"], expected_shift)
            self.assertLessEqual(abs((min(y for x, y in ink) + max(y for x, y in ink)) / 2
                                     - (12 + index % 2)), 0.5)
            font._require_outside_roi_exact(current, after, tuple(target["roi"]), label="centered-maximum")
            for y in range(frame_top, frame_top + 4):
                self.assertEqual(after.pixels[y * 66 + 8:y * 66 + 60],
                                 original.pixels[y * 66 + 8:y * 66 + 60])
            masks.append(ink)
        self.assertEqual(masks[1], {(x + 1, y + 1) for x, y in masks[0]})

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
