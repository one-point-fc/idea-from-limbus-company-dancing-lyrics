import json
from PySide6.QtCore import Qt, QRectF, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QCheckBox, QComboBox, QLabel, QDoubleSpinBox, QDialogButtonBox, QPushButton)
from regions import REGION_NAMES, DEFAULT_BOXES_JSON, region_boxes, selected_regions


class RegionCanvas(QWidget):
    changed = Signal()
    selected = Signal(str)

    def __init__(self, boxes, enabled, parent=None):
        super().__init__(parent)
        self.boxes, self.enabled = boxes, enabled
        self.current = next(iter(REGION_NAMES))
        self.drag = None
        self.setMinimumSize(460, 250)
        self.setAccessibleName("歌词出现范围预览；也可使用下方数字输入调整")

    def screen_rect(self):
        available = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        ratio = self.screen().availableGeometry().width() / self.screen().availableGeometry().height()
        width = min(available.width(), available.height() * ratio)
        height = width / ratio
        return QRectF(available.center().x()-width/2, available.center().y()-height/2, width, height)

    def box_rect(self, key):
        screen = self.screen_rect()
        x, y, w, h = self.boxes[key]
        return QRectF(screen.x()+screen.width()*x/100, screen.y()+screen.height()*y/100,
                      screen.width()*w/100, screen.height()*h/100)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.screen_rect(), QColor("#18202b"))
        for key in REGION_NAMES:
            rect = self.box_rect(key)
            color = QColor("#52c7ea" if key == self.current else "#8497aa")
            color.setAlpha(65 if key in self.enabled else 15)
            painter.fillRect(rect, color)
            painter.setPen(QPen(QColor("#52c7ea" if key == self.current else "#8497aa"),
                                2 if key == self.current else 1,
                                Qt.PenStyle.SolidLine if key in self.enabled else Qt.PenStyle.DashLine))
            painter.drawRect(rect)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, REGION_NAMES[key])
            if key == self.current:
                painter.fillRect(QRectF(rect.right()-9, rect.bottom()-9, 9, 9), QColor("#52c7ea"))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        keys = [self.current] + [key for key in REGION_NAMES if key != self.current]
        for key in keys:
            rect = self.box_rect(key)
            if rect.contains(event.position()):
                self.current = key
                resize = event.position().x() >= rect.right()-14 and event.position().y() >= rect.bottom()-14
                self.drag = (event.position(), list(self.boxes[key]), resize)
                self.selected.emit(key)
                self.update()
                return

    def mouseMoveEvent(self, event):
        if self.drag is None:
            return
        start, box, resize = self.drag
        screen = self.screen_rect()
        dx = (event.position().x()-start.x()) * 100 / screen.width()
        dy = (event.position().y()-start.y()) * 100 / screen.height()
        x, y, w, h = box
        if resize:
            w, h = max(5, min(100-x, w+dx)), max(5, min(100-y, h+dy))
        else:
            x, y = max(0, min(100-w, x+dx)), max(0, min(100-h, y+dy))
        self.boxes[self.current] = [round(n, 2) for n in (x, y, w, h)]
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag = None


class RegionEditor(QDialog):
    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择歌词位置与范围")
        self.resize(660, 590)
        self.boxes = region_boxes(prefs.region_boxes)
        self.enabled = set(selected_regions(prefs.selected_regions))
        layout = QVBoxLayout(self)
        hint = QLabel("勾选可出现的位置，歌词按勾选位置轮流出现。\n拖动画框移动范围，拖右下角缩放；也可在下方输入百分比。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        grid = QGridLayout()
        self.checkboxes = {}
        for index, (key, title) in enumerate(REGION_NAMES.items()):
            checkbox = QCheckBox(title)
            checkbox.setChecked(key in self.enabled)
            checkbox.toggled.connect(lambda checked, key=key: self.toggle(key, checked))
            self.checkboxes[key] = checkbox
            grid.addWidget(checkbox, index//2, index%2)
        layout.addLayout(grid)
        self.canvas = RegionCanvas(self.boxes, self.enabled)
        layout.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        self.selector = QComboBox()
        for key, name in REGION_NAMES.items():
            self.selector.addItem(name + "的范围", key)
        self.selector.currentIndexChanged.connect(self.select)
        row.addWidget(self.selector)
        self.spins = []
        for name in ("左边距", "上边距", "宽度", "高度"):
            column = QVBoxLayout()
            column.addWidget(QLabel(name))
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setDecimals(1)
            spin.setSuffix("%")
            spin.setAccessibleName(name)
            spin.valueChanged.connect(self.edit_box)
            self.spins.append(spin)
            column.addWidget(spin)
            row.addLayout(column)
        layout.addLayout(row)
        self.canvas.selected.connect(lambda key: self.selector.setCurrentIndex(self.selector.findData(key)))
        self.canvas.changed.connect(self.sync_spins)
        self.error = QLabel()
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存并应用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        reset = QPushButton("恢复默认范围")
        reset.clicked.connect(self.reset_boxes)
        buttons.addButton(reset, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.select()

    def toggle(self, key, checked):
        self.enabled.add(key) if checked else self.enabled.discard(key)
        self.save_button.setEnabled(bool(self.enabled))
        self.error.setText("" if self.enabled else "请至少选择一个出现位置。")
        self.canvas.update()

    def select(self, *_):
        self.canvas.current = self.selector.currentData()
        self.sync_spins()
        self.canvas.update()

    def sync_spins(self):
        blockers = [QSignalBlocker(spin) for spin in self.spins]
        x, y, w, h = self.boxes[self.canvas.current]
        for spin, minimum, maximum, value in zip(self.spins, (0, 0, 5, 5),
                                                  (100-w, 100-h, 100-x, 100-y), (x, y, w, h)):
            spin.setRange(minimum, maximum)
            spin.setValue(value)

    def edit_box(self):
        self.boxes[self.canvas.current] = [spin.value() for spin in self.spins]
        self.sync_spins()
        self.canvas.update()

    def reset_boxes(self):
        self.boxes.clear()
        self.boxes.update(region_boxes(DEFAULT_BOXES_JSON))
        self.sync_spins()
        self.canvas.update()

    def values(self):
        return ",".join(key for key in REGION_NAMES if key in self.enabled), json.dumps(self.boxes)
