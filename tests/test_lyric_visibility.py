import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from animation import build_layout
from settings import Preferences
from netease import NeteasePlayer, validate_snapshot
from test_netease import packet
from text_effects import TextEffects, pixels_view
from glyph_motion import GlyphState
from PySide6.QtWidgets import QSpinBox, QStyle, QStyleOptionFrame
from themes import theme_stylesheet
from overlay import LyricsOverlay
from lrc import LyricDocument, LyricLine

APP = QApplication.instance() or QApplication([])


class LyricVisibilityTests(unittest.TestCase):
    def test_overlay_paints_long_native_bilingual_line_throughout_its_interval(self):
        prefs = Preferences(region="custom", font_size=22, prefer_translation=True, animation_style="fall_wave")
        player = NeteasePlayer()
        player.apply(validate_snapshot(packet(duration_ms=20000, position_ms=1000, playing=False)))
        overlay = LyricsOverlay(player, prefs)
        overlay.resize(900, 600)
        overlay.set_document(LyricDocument([LyricLine(0, "Long native lyrics " * 30,
                                                     translation="中文原生译文" * 80),
                                            LyricLine(20000, "next")], []))
        try:
            for position in (1000, 10000, 19000):
                player.apply(validate_snapshot(packet(duration_ms=20000, position_ms=position,
                                                       playing=False, lyrics=None)))
                image = overlay.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
                self.assertGreater((pixels_view(image)[:, :, 3] > 0).sum(), 100)
                self.assertEqual(overlay.layouts[0].font_size, 22)
                self.assertIsNotNone(overlay.layouts[0].clip_rect)
            prefs.animation_style = "classic"
            overlay.refresh_preferences()
            image = overlay.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
            self.assertGreater((pixels_view(image)[:, :, 3] > 0).sum(), 100)
        finally:
            overlay.close()

    def test_long_bilingual_line_keeps_font_and_a_bounded_scroll_viewport(self):
        prefs = Preferences(region="custom", font_size=22, angle=15, animation_style="fall_wave", jump=20)
        original, translation = "这是不会在小区域消失的长句"*12, "中文译文"*40
        region = QRectF(0, 0, 318, 340)
        layout = build_layout(original+"\n"+translation, 12, [region], [], prefs,
                              len(original)+1, "top_left")
        self.assertIsNotNone(layout)
        self.assertEqual(layout.font_size, 22)
        self.assertIsNotNone(layout.clip_rect)
        self.assertTrue(region.adjusted(-.01,-.01,.01,.01).contains(layout.bounds))
        self.assertEqual(len(layout.scroll_spans), 2)
        self.assertTrue(all(value > 0 for value in layout.scroll_spans.values()))
        effects = TextEffects()
        surface = effects.prepare(layout.glyphs, layout.font_size, prefs, 1, prefs.jump,
                                  layout.angle, layout.clip_rect)
        self.assertLess(surface.image.sizeInBytes(), 318 * 340 * 4)
        poses = [GlyphState(g.x, g.baseline) for g in layout.glyphs]
        for progress in (0, .5, 1):
            image = effects.render(surface, prefs, states=layout.scroll_states(poses, progress))
            self.assertGreater((pixels_view(image)[:, :, 3] > 0).sum(), 100)

    def test_numeric_editor_has_room_for_digits_in_all_themes(self):
        for theme in ("light", "dark", "special"):
            spin = QSpinBox()
            spin.setStyleSheet(theme_stylesheet(theme))
            spin.setValue(20)
            spin.setSuffix(" px")
            spin.resize(420, spin.sizeHint().height())
            spin.show()
            APP.processEvents()
            edit = spin.lineEdit()
            option = QStyleOptionFrame()
            edit.initStyleOption(option)
            rect = edit.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, edit)
            self.assertGreaterEqual(rect.height(), edit.fontMetrics().height())
            self.assertEqual(edit.text(), "20 px")
            self.assertEqual(edit.font().families()[0], "Segoe UI")
            spin.close()

    def test_transient_lyric_refresh_keeps_same_song_but_switch_and_empty_clear(self):
        player = NeteasePlayer()
        documents = []
        player.document_changed.connect(documents.append)
        player.apply(validate_snapshot(packet()))
        self.assertIsNotNone(documents[-1])
        documents.clear()
        player.apply(validate_snapshot(packet(lyrics=None)))
        self.assertEqual(documents, [])
        player.apply(validate_snapshot(packet(lyrics=[], song={"id":"2","title":"next","artist":"test"})))
        self.assertIsNone(documents[-1])
