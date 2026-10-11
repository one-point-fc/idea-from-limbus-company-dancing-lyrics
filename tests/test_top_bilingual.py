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
        glyphs, _, _ = _glyph_layout(lines[0].text, 32, 700)
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
                                          regions, [], prefs)
                    self.assertIsNotNone(layout)
                    self.assertTrue(regions[0].adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(layout.bounds))
                    self.assertLessEqual(layout.bounds.bottom(), height * .32 + 0.01)
                    self.assertEqual(layout.angle, 0)
                    self.assertEqual(layout.center.x() < width / 2, index % 2 == 0)

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
