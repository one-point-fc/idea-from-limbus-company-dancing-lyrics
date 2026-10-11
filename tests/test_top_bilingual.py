import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtWidgets import QApplication
from animation import build_layout, display_regions, _glyph_layout
from glyph_motion import word_emphasis
from lrc import LyricDocument, LyricLine, TimedWord, display_document
from settings import Preferences, normalize_preferences
from overlay import LyricsOverlay
from netease import NeteasePlayer

APP = QApplication.instance() or QApplication([])


class TopBilingualTests(unittest.TestCase):
    def test_bilingual_order_fallback_and_original_word_emphasis(self):
        words = (TimedWord(1000, 2000, 0, 5),)
        document = LyricDocument([LyricLine(1000, "Hello", words, "你好"),
                                 LyricLine(3000, "No translation"),
                                 LyricLine(5000, "相同", (), "相同")], [])
        lines = display_document(document, True).lines
        self.assertEqual([line.text for line in lines], ["Hello\n你好", "No translation", "相同"])
        glyphs, _, _ = _glyph_layout(lines[0].text, 32, 700, translation_start=6)
        original = [g for g in glyphs if g.text_start < 5]
        translated = [g for g in glyphs if g.text_start > 5]
        self.assertLess(max(g.baseline for g in original), min(g.baseline for g in translated))
        self.assertTrue(any(word_emphasis(g, lines[0].words, 1500) > 0 for g in original))
        self.assertTrue(all(word_emphasis(g, lines[0].words, 1500) == 0 for g in translated))

    def test_alternates_at_top_and_fits_small_and_large_screens(self):
        for width, height in ((1024, 720), (1536, 960), (2560, 1440)):
            for style in ("classic", "ripple_wave", "fall_shake"):
                prefs = normalize_preferences(Preferences(region="top_alternate", animation_style=style,
                                                          singing_sync=True))
                for index in range(4):
                    regions = display_regions(width, height, prefs.region, index)
                    layout = build_layout("This is the original lyric\n这是对应的中文歌词翻译", 17,
                                          regions, [], prefs, translation_start=len("This is the original lyric") + 1)
                    self.assertIsNotNone(layout)
                    self.assertTrue(regions[0].adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(layout.bounds))
                    self.assertLessEqual(layout.bounds.bottom(), height * .32 + 0.01)
                    self.assertNotEqual(layout.angle, 0)
                    self.assertLessEqual(abs(layout.angle), prefs.angle)
                    self.assertEqual(layout.center.x() < width / 2, index % 2 == 0)

    def test_top_bilingual_uses_original_tilt_control(self):
        for maximum in (0, 5, 15, 25):
            prefs = Preferences(region="top_alternate", angle=maximum, font_size=20, jump=20)
            angles = []
            for seed in range(6):
                regions = display_regions(1536, 960, prefs.region, seed)
                layout = build_layout("Original lyric\n中文翻译", seed, regions, [], prefs, translation_start=15)
                self.assertIsNotNone(layout)
                self.assertLessEqual(abs(layout.angle), maximum)
                self.assertTrue(regions[0].adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(layout.bounds))
                angles.append(layout.angle)
            if maximum:
                self.assertLess(min(angles), 0)
                self.assertGreater(max(angles), 0)
            else:
                self.assertEqual(angles, [0] * 6)

    def test_translation_is_smaller_and_multiline_original_keeps_its_size(self):
        glyphs, _, _ = _glyph_layout("中\n中\n中", 32, 700, translation_start=4)
        self.assertEqual(glyphs[0].path.boundingRect().height(), glyphs[1].path.boundingRect().height())
        ratio = glyphs[2].path.boundingRect().height() / glyphs[0].path.boundingRect().height()
        self.assertAlmostEqual(ratio, .75, delta=.03)
        self.assertGreater(glyphs[2].baseline, glyphs[1].baseline)
        self.assertEqual((glyphs[2].text_start, glyphs[2].text_end), (4, 5))
        self.assertEqual([g.index for g in glyphs], [0, 1, 2])

    def test_overlay_skips_blank_markers_and_seek_keeps_side(self):
        player = NeteasePlayer()
        player.position = lambda: 4500
        player.energy_at = lambda _: 0
        player.duration = 20000
        prefs = Preferences(region="top_alternate", prefer_translation=True)
        overlay = LyricsOverlay(player, prefs)
        try:
            overlay.resize(1536, 960)
            overlay.set_document(LyricDocument([LyricLine(0, ""), LyricLine(1000, "First", (), "第一句"),
                                               LyricLine(3000, ""), LyricLine(4000, "Second", (), "第二句")], []))
            overlay.grab()
            self.assertGreater(overlay.layouts[3].center.x(), overlay.width() / 2)
            player.position = lambda: 1500
            overlay.clear_layouts()
            overlay.grab()
            self.assertLess(overlay.layouts[1].center.x(), overlay.width() / 2)
        finally:
            overlay.close()
            overlay.deleteLater()
