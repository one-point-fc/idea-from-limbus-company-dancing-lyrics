import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QRect, QRectF
from PySide6.QtWidgets import QApplication
from animation import build_layout
from glyph_motion import glyph_states
from lrc import LyricDocument, LyricLine, LyricTimeline, display_document
from region_editor import RegionEditor
from settings import Preferences
from text_effects import TextEffects, pixels_view

APP = QApplication.instance() or QApplication([])


class CustomUpgradeTests(unittest.TestCase):
    def test_both_orders_preserve_original_size_in_normal_and_scrolling_regions(self):
        for mode in ('bilingual_original', 'bilingual_translation'):
            for width in (120, 900):
                prefs = Preferences(region='custom', font_size=40, lyric_display_mode=mode, jump=0)
                doc = display_document(LyricDocument([LyricLine(0, 'Original ' * 9, translation='中文翻译' * 9)], []), mode=mode)
                line = doc.lines[0]
                layout = build_layout(line.text, 42, [QRectF(0, 0, width, 240)], [], prefs,
                                      line.secondary_start, 'top_left')
                self.assertIsNotNone(layout)
                original_language = 1 if mode == 'bilingual_translation' else 0
                self.assertEqual({g.pixels for g in layout.glyphs if g.language == original_language}, {40})
                self.assertEqual({g.pixels for g in layout.glyphs if g.language != original_language}, {30})
                self.assertEqual(layout.font_size, 40)
                if width == 120:
                    self.assertIsNotNone(layout.clip_rect)

    def test_gradient_scramble_renders_inside_fixed_font_scrolling_viewport(self):
        prefs = Preferences(region='custom', font_size=32, text_style='gradient_fill', scramble_exit=True)
        doc = display_document(LyricDocument([LyricLine(0, 'Original ' * 8, translation='中文翻译' * 8), LyricLine(4000, 'Next')], []), True)
        timeline = LyricTimeline(doc, scramble_exit=True, align_boundaries=True)
        first = timeline.visible(0, 8000)[0]
        self.assertEqual(first.entry_end_ms, first.start_ms)
        line = doc.lines[0]
        layout = build_layout(line.text, 42, [QRectF(0, 0, 160, 160)], [], prefs, line.secondary_start, 'top_right')
        self.assertIsNotNone(layout.clip_rect)
        renderer = TextEffects()
        surface = renderer.prepare(layout.glyphs, layout.font_size, prefs, 1, viewport=layout.clip_rect)
        item = timeline.visible(4200, 8000)[0]
        states = layout.scroll_states(glyph_states(layout.glyphs, prefs, item, 4200, 0, 32), .5)
        self.assertTrue(any(s.replacement >= 0 for s in states))
        image = renderer.render(surface, prefs, states=states)
        self.assertTrue(pixels_view(image)[:, :, 3].any())
        self.assertLessEqual(image.width(), 162)
        self.assertLessEqual(renderer.cache_bytes, renderer.limit_bytes)

    def test_region_preview_uses_selected_monitor_aspect_ratio(self):
        screen = Mock()
        screen.availableGeometry.return_value = QRect(1920, 0, 1080, 1920)
        prefs = Preferences(display_screen='name:portrait')
        editor = RegionEditor(prefs)
        try:
            with patch('region_editor.select_screen', return_value=screen) as select:
                area = editor.canvas.screen_rect()
                self.assertAlmostEqual(area.width()/area.height(), 1080/1920)
                self.assertEqual(select.call_args.args[2], prefs.display_screen)
        finally:
            editor.close()
