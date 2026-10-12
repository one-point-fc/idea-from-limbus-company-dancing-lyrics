import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from regions import REGION_NAMES, DEFAULT_BOXES_JSON, selected_regions, region_boxes
from region_editor import RegionEditor
from settings import Preferences, SettingsStore, normalize_preferences
from animation import display_regions, build_layout
from presets import EFFECT_KEYS
from lrc import LyricDocument, LyricLine, LyricTimeline
from netease import NeteasePlayer, validate_snapshot
from test_netease import packet

APP = QApplication.instance() or QApplication([])


class CustomRegionsTests(unittest.TestCase):
    def test_resizing_custom_regions_preserves_original_and_translation_font_sizes(self):
        from PySide6.QtCore import QRectF
        from dataclasses import replace
        prefs = Preferences(region="custom", font_size=32, angle=0, jump=0, text_style="solid")
        text = "Original lyric text\n中文翻译"
        layouts = [build_layout(text, 12, [QRectF(0, 0, width, 800)], [], prefs, text.index("\n")+1, "top_left")
                   for width in (800, 400, 240)]
        for layout in layouts:
            self.assertIsNotNone(layout)
            self.assertEqual(layout.font_size, prefs.font_size)
            self.assertEqual([glyph.path.boundingRect() for glyph in layout.glyphs],
                             [glyph.path.boundingRect() for glyph in layouts[0].glyphs])
        self.assertGreater(len({g.baseline for g in layouts[-1].glyphs}),
                           len({g.baseline for g in layouts[0].glyphs}))
        # A box that only fits after shrinking must no longer silently change the font.
        tiny = QRectF(0, 0, 100, 70)
        clipped = build_layout("字", 12, [tiny], [], prefs, anchor="top_left")
        self.assertEqual(clipped.font_size, prefs.font_size)
        self.assertTrue(tiny.contains(clipped.bounds))
        self.assertIsNotNone(build_layout("字", 12, [tiny], [], replace(prefs, region="edges")))

    def test_six_regions_roundtrip_clamping_and_preset_independence(self):
        prefs = Preferences(region="custom", selected_regions="bottom_left,top_right")
        prefs.region_boxes = json.dumps({"top_right": [88, 90, 30, 30]})
        prefs = normalize_preferences(prefs)
        self.assertEqual(selected_regions(prefs.selected_regions), ["top_right", "bottom_left"])
        self.assertEqual(region_boxes(prefs.region_boxes)["top_right"], [88, 90, 12, 10])
        self.assertEqual(len(region_boxes("bad")), 6)
        self.assertEqual(selected_regions(""), ["top_left", "top_right"])
        for key in ("selected_regions", "region_boxes", "native_line_sync"):
            self.assertNotIn(key, EFFECT_KEYS)
        with tempfile.TemporaryDirectory() as folder:
            store = SettingsStore(Path(folder)/"settings.ini")
            store.save(prefs)
            self.assertEqual(store.load(), prefs)

    def test_all_six_anchors_stay_in_custom_boxes_and_at_outer_edges(self):
        prefs = Preferences(region="custom", selected_regions=",".join(REGION_NAMES), font_size=20, angle=25)
        for index, key in enumerate(REGION_NAMES):
            box = display_regions(1536, 960, "custom", index, prefs)[0]
            layout = build_layout("Original\n翻译", 12+index, [box], [], prefs, 9, key)
            self.assertIsNotNone(layout)
            self.assertTrue(box.adjusted(-1e-6,-1e-6,1e-6,1e-6).contains(layout.bounds))
            edge = layout.bounds.left() if key.endswith("left") else layout.bounds.right()
            self.assertAlmostEqual(edge, box.left() if key.endswith("left") else box.right())
            if key.startswith("top"):
                self.assertAlmostEqual(layout.bounds.top(), box.top())
            elif key.startswith("bottom"):
                self.assertAlmostEqual(layout.bounds.bottom(), box.bottom())
            else:
                self.assertAlmostEqual(layout.bounds.center().y(), box.center().y())
            # Reusing one selected region must not push a short line toward screen center.
            repeated = build_layout("Original\n翻译", 12+index, [box], [layout.bounds], prefs, 9, key)
            self.assertEqual(repeated.bounds, layout.bounds)

    def test_editor_multi_selection_numeric_edit_drag_and_cancel_isolation(self):
        prefs = Preferences()
        dialog = RegionEditor(prefs)
        dialog.show()
        APP.processEvents()
        try:
            for checkbox in dialog.checkboxes.values():
                checkbox.setChecked(False)
            self.assertFalse(dialog.save_button.isEnabled())
            dialog.checkboxes["bottom_left"].setChecked(True)
            self.assertTrue(dialog.save_button.isEnabled())
            dialog.selector.setCurrentIndex(dialog.selector.findData("bottom_left"))
            dialog.spins[2].setValue(20)
            self.assertEqual(dialog.boxes["bottom_left"][2], 20)
            before = dialog.boxes["bottom_left"][:]
            center = dialog.canvas.box_rect("bottom_left").center().toPoint()
            QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=center)
            QTest.mouseMove(dialog.canvas, center+QPoint(12,-12))
            QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=center+QPoint(12,-12))
            self.assertNotEqual(dialog.boxes["bottom_left"], before)
            selected, boxes = dialog.values()
            self.assertEqual(selected, "bottom_left")
            self.assertEqual(len(region_boxes(boxes)), 6)
            self.assertEqual(prefs.region_boxes, DEFAULT_BOXES_JSON)
        finally:
            dialog.close()


class NativeAlignmentTests(unittest.TestCase):
    def test_original_playback_timestamp_prevents_repeated_stale_snapshot_lag(self):
        clock = [10.]
        player = NeteasePlayer(clock=lambda: clock[0])
        with patch("netease.time.time", return_value=100.2):
            player.apply(validate_snapshot(packet(position_ms=1000, position_at_ms=100000)))
        self.assertAlmostEqual(player.position(), 1200)
        with patch("netease.time.time", return_value=100.6):
            clock[0] += .4
            player.apply(validate_snapshot(packet(position_ms=1000, position_at_ms=100000)))
        self.assertAlmostEqual(player.position(), 1600)
        jumps = []
        player.discontinuity.connect(lambda: jumps.append(True))
        clock[0] += .5
        with patch("netease.time.time", return_value=101.1):
            player.apply(validate_snapshot(packet(position_ms=1000, position_at_ms=100000)))
        self.assertAlmostEqual(player.position(), 2100)
        self.assertEqual(jumps, [], "aged snapshots must not look like a seek")
        with patch("netease.time.time", return_value=101):
            player.apply(validate_snapshot(packet(position_ms=1600, position_at_ms=100600, playing=False)))
        clock[0] += 2
        self.assertEqual(player.position(), 1600)

    def test_aligned_line_is_visible_at_boundary_and_long_lines_do_not_expire_early(self):
        doc = LyricDocument([LyricLine(1000, "first"), LyricLine(15000, "next")], [])
        for style in ("classic", "ripple_wave", "fall_shake"):
            timeline = LyricTimeline(doc, animation_style=style, align_boundaries=True)
            item = timeline.visible(1000, 20000)[0]
            self.assertEqual(item.opacity, 1)
            if style != "classic":
                self.assertEqual(item.entry_end_ms, item.start_ms)
            self.assertEqual(timeline.visible(12000,20000)[0].text, "first")
            self.assertEqual(timeline.visible(15000,20000)[-1].text, "next")
        self.assertEqual(LyricTimeline(doc).visible(1000,20000)[0].opacity, 0)
