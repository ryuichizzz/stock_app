from __future__ import annotations

import json
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

CANVAS_WIDTH = 640
CANVAS_HEIGHT = 480
GRID_SIZE = 16
HANDLE_SIZE = 10
TEXT_CELL_WIDTH = 16
TEXT_CELL_HEIGHT = 16
PRESET_FILE = "frame_presets.json"


class BitmapFont:
    def __init__(self, json_path: str = ""):
        self.json_path = json_path
        self.base_dir = Path(json_path).parent if json_path else Path.cwd()
        self.pages: list[QPixmap] = []
        self.glyphs: dict[str, dict] = {}
        self.glyph_width = 8
        self.glyph_height = 16
        self.offset_x = 0
        self.offset_y = 0
        self.is_valid = False
        if json_path:
            self.load(json_path)

    def load(self, json_path: str) -> None:
        self.json_path = json_path
        self.base_dir = Path(json_path).parent
        self.pages = []
        self.glyphs = {}
        self.is_valid = False

        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        self.glyph_width = int(data.get("glyph_width", 8))
        self.glyph_height = int(data.get("glyph_height", 16))
        self.offset_x = int(data.get("offset_x", 0))
        self.offset_y = int(data.get("offset_y", 0))
        self.glyphs = data.get("glyphs", {})

        for page_name in data.get("pages", []):
            pix = QPixmap(str(self.base_dir / page_name))
            self.pages.append(pix)

        self.is_valid = bool(self.pages) and bool(self.glyphs)

    def draw_text(self, painter: QPainter, x: int, y: int, text: str) -> None:
        if not self.is_valid:
            return

        cx = x
        cy = y
        for ch in text:
            if ch == "\n":
                cx = x
                cy += self.glyph_height
                continue

            info = self.glyphs.get(ch)
            if info is None:
                cx += self.glyph_width
                continue

            page_index = int(info.get("page", 0))
            col = int(info.get("col", 0))
            row = int(info.get("row", 0))
            if not (0 <= page_index < len(self.pages)):
                cx += self.glyph_width
                continue

            src_x = col * self.glyph_width
            src_y = row * self.glyph_height
            page = self.pages[page_index]

            painter.drawPixmap(
                QRectF(cx, cy, self.glyph_width, self.glyph_height).toRect(),
                page,
                QRectF(src_x, src_y, self.glyph_width, self.glyph_height).toRect(),
            )
            cx += self.glyph_width


@dataclass
class LayoutObject:
    id: str
    name: str = ""
    type: str = ""
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    text: str = ""
    selected_index: int = 0
    lines: list[str] | None = None
    image_path: str = ""
    image_scale: int = 1
    cursor_image_path: str = ""
    frame_image_path: str = ""
    slice_left: int = 16
    slice_right: int = 16
    slice_top: int = 16
    slice_bottom: int = 16
    cursor_offset_x: int = 0
    cursor_offset_y: int = 0
    z_value: int = 0
    bitmap_font_json: str = ""


class BaseEditorItem:
    obj_id: str
    obj_name: str
    obj_type: str

    def to_layout_object(self) -> LayoutObject:
        raise NotImplementedError

    def apply_layout_object(self, obj: LayoutObject) -> None:
        raise NotImplementedError

    def display_name(self) -> str:
        raise NotImplementedError


class TextAreaItem(QGraphicsSimpleTextItem, BaseEditorItem):
    def __init__(self, obj: LayoutObject):
        super().__init__(obj.text)
        self.obj_id = obj.id
        self.obj_name = obj.name or "text_area"
        self.obj_type = obj.type
        self.bitmap_font_json = obj.bitmap_font_json
        self.bitmap_font = BitmapFont(obj.bitmap_font_json) if obj.bitmap_font_json else None

        self._w = max(GRID_SIZE, obj.w or 160)
        self._h = max(GRID_SIZE, obj.h or 48)

        self.setPos(obj.x, obj.y)
        self.setBrush(QBrush(QColor("#FFFFFF")))
        self.setZValue(obj.z_value)

        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.Monospace)
        font.setBold(True)
        self.setFont(font)

        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

    def display_name(self) -> str:
        return self.obj_name or "TextArea"

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def paint(self, painter: QPainter, option, widget=None):
        if self.bitmap_font and self.bitmap_font.is_valid:
            max_rows = max(1, self._h // self.bitmap_font.glyph_height)
            max_cols = max(1, self._w // self.bitmap_font.glyph_width)
            lines = self.text().splitlines()[:max_rows]
            clipped = [line[:max_cols] for line in lines]
            self.bitmap_font.draw_text(painter, 0, 0, "\n".join(clipped))
        else:
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(self.font())
            max_rows = max(1, self._h // TEXT_CELL_HEIGHT)
            max_cols = max(1, self._w // TEXT_CELL_WIDTH)
            lines = self.text().splitlines()[:max_rows]
            for i, line in enumerate(lines):
                y = (i + 1) * TEXT_CELL_HEIGHT - 4
                painter.drawText(QPointF(0, y), line[:max_cols])

        if self.isSelected():
            painter.setPen(QPen(QColor("#80C0FF"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            p = value
            return QPointF(
                round(p.x() / GRID_SIZE) * GRID_SIZE,
                round(p.y() / GRID_SIZE) * GRID_SIZE,
            )
        return super().itemChange(change, value)

    def to_layout_object(self) -> LayoutObject:
        return LayoutObject(
            id=self.obj_id,
            name=self.obj_name,
            type=self.obj_type,
            x=int(self.pos().x()),
            y=int(self.pos().y()),
            w=int(self._w),
            h=int(self._h),
            text=self.text(),
            z_value=int(self.zValue()),
            bitmap_font_json=self.bitmap_font_json,
        )

    def apply_layout_object(self, obj: LayoutObject) -> None:
        self.obj_name = obj.name or "text_area"
        self.bitmap_font_json = obj.bitmap_font_json
        self.bitmap_font = BitmapFont(obj.bitmap_font_json) if obj.bitmap_font_json else None
        self.prepareGeometryChange()
        self._w = max(GRID_SIZE, obj.w or 160)
        self._h = max(GRID_SIZE, obj.h or 48)
        self.setText(obj.text)
        self.setPos(obj.x, obj.y)
        self.setZValue(obj.z_value)
        self.update()


class ResizableFrameItem(QGraphicsItem, BaseEditorItem):
    def __init__(self, obj: LayoutObject):
        super().__init__()
        self.obj_id = obj.id
        self.obj_name = obj.name or obj.type or "item"
        self.obj_type = obj.type
        self._w = max(GRID_SIZE, obj.w)
        self._h = max(GRID_SIZE, obj.h)
        self.setPos(obj.x, obj.y)
        self.setZValue(obj.z_value)

        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        self._resizing = False
        self._start_rect = QRectF(0, 0, self._w, self._h)
        self._start_scene_pos = QPointF()

    def boundingRect(self) -> QRectF:
        pad = HANDLE_SIZE
        return QRectF(-pad, -pad, self._w + pad * 2, self._h + pad * 2)

    def content_rect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def handle_rect(self) -> QRectF:
        return QRectF(self._w - HANDLE_SIZE, self._h - HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None and not self._resizing:
            p = value
            return QPointF(
                round(p.x() / GRID_SIZE) * GRID_SIZE,
                round(p.y() / GRID_SIZE) * GRID_SIZE,
            )
        return super().itemChange(change, value)

    def compute_resized_size(self, delta: QPointF) -> tuple[int, int]:
        new_w = max(GRID_SIZE, int(self._start_rect.width() + delta.x()))
        new_h = max(GRID_SIZE, int(self._start_rect.height() + delta.y()))
        new_w = max(GRID_SIZE, round(new_w / GRID_SIZE) * GRID_SIZE)
        new_h = max(GRID_SIZE, round(new_h / GRID_SIZE) * GRID_SIZE)
        return new_w, new_h

    def mousePressEvent(self, event):
        if self.handle_rect().contains(event.pos()):
            self._resizing = True
            self._start_rect = QRectF(0, 0, self._w, self._h)
            self._start_scene_pos = event.scenePos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._start_scene_pos
            new_w, new_h = self.compute_resized_size(delta)
            self.prepareGeometryChange()
            self._w = new_w
            self._h = new_h
            self.update()
            sc = self.scene()
            if sc is not None and hasattr(sc, "selection_changed_for_ui"):
                sc.selection_changed_for_ui.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            sc = self.scene()
            if sc is not None and hasattr(sc, "item_list_changed"):
                sc.item_list_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def draw_selection_handle(self, painter: QPainter) -> None:
        if self.isSelected():
            painter.setBrush(QBrush(QColor("#FFD84D")))
            painter.setPen(QPen(QColor("#000000"), 1))
            painter.drawRect(self.handle_rect())


class WindowItem(ResizableFrameItem):
    def __init__(self, obj: LayoutObject):
        super().__init__(obj)
        self.frame_image_path = obj.frame_image_path
        self.slice_left = max(1, obj.slice_left)
        self.slice_right = max(1, obj.slice_right)
        self.slice_top = max(1, obj.slice_top)
        self.slice_bottom = max(1, obj.slice_bottom)
        self.bitmap_font_json = obj.bitmap_font_json
        self.bitmap_font = BitmapFont(obj.bitmap_font_json) if obj.bitmap_font_json else None
        self._frame_pixmap = QPixmap()
        self._load_frame_pixmap()

    def _load_frame_pixmap(self) -> None:
        self._frame_pixmap = QPixmap(self.frame_image_path) if self.frame_image_path else QPixmap()

    def display_name(self) -> str:
        return self.obj_name or "Window"

    def _draw_nine_slice(self, painter: QPainter, rect: QRectF, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return

        src_w = pixmap.width()
        src_h = pixmap.height()
        if src_w < 3 or src_h < 3:
            painter.drawPixmap(rect.toRect(), pixmap)
            return

        left = min(max(1, self.slice_left), max(1, src_w - 2))
        right = min(max(1, self.slice_right), max(1, src_w - left - 1))
        top = min(max(1, self.slice_top), max(1, src_h - 2))
        bottom = min(max(1, self.slice_bottom), max(1, src_h - top - 1))

        center_w = max(1, src_w - left - right)
        center_h = max(1, src_h - top - bottom)

        dst_x = int(rect.x())
        dst_y = int(rect.y())
        dst_w = max(1, int(rect.width()))
        dst_h = max(1, int(rect.height()))

        dst_left = min(left, max(1, dst_w // 2))
        dst_right = min(right, max(1, dst_w - dst_left - 1))
        dst_top = min(top, max(1, dst_h // 2))
        dst_bottom = min(bottom, max(1, dst_h - dst_top - 1))

        dst_center_w = max(1, dst_w - dst_left - dst_right)
        dst_center_h = max(1, dst_h - dst_top - dst_bottom)

        x0 = dst_x
        x1 = x0 + dst_left
        x2 = x1 + dst_center_w
        y0 = dst_y
        y1 = y0 + dst_top
        y2 = y1 + dst_center_h

        src_tl = QRectF(0, 0, left, top).toRect()
        src_t = QRectF(left, 0, center_w, top).toRect()
        src_tr = QRectF(src_w - right, 0, right, top).toRect()
        src_l = QRectF(0, top, left, center_h).toRect()
        src_c = QRectF(left, top, center_w, center_h).toRect()
        src_r = QRectF(src_w - right, top, right, center_h).toRect()
        src_bl = QRectF(0, src_h - bottom, left, bottom).toRect()
        src_b = QRectF(left, src_h - bottom, center_w, bottom).toRect()
        src_br = QRectF(src_w - right, src_h - bottom, right, bottom).toRect()

        dst_tl = QRectF(x0, y0, dst_left, dst_top).toRect()
        dst_t = QRectF(x1, y0, dst_center_w, dst_top).toRect()
        dst_tr = QRectF(x2, y0, dst_right, dst_top).toRect()
        dst_l = QRectF(x0, y1, dst_left, dst_center_h).toRect()
        dst_c = QRectF(x1, y1, dst_center_w, dst_center_h).toRect()
        dst_r = QRectF(x2, y1, dst_right, dst_center_h).toRect()
        dst_bl = QRectF(x0, y2, dst_left, dst_bottom).toRect()
        dst_b = QRectF(x1, y2, dst_center_w, dst_bottom).toRect()
        dst_br = QRectF(x2, y2, dst_right, dst_bottom).toRect()

        painter.drawPixmap(dst_tl, pixmap, src_tl)
        painter.drawPixmap(dst_t, pixmap, src_t)
        painter.drawPixmap(dst_tr, pixmap, src_tr)
        painter.drawPixmap(dst_l, pixmap, src_l)
        painter.drawPixmap(dst_c, pixmap, src_c)
        painter.drawPixmap(dst_r, pixmap, src_r)
        painter.drawPixmap(dst_bl, pixmap, src_bl)
        painter.drawPixmap(dst_b, pixmap, src_b)
        painter.drawPixmap(dst_br, pixmap, src_br)

    def paint(self, painter: QPainter, option, widget=None):
        r = self.content_rect()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        if not self._frame_pixmap.isNull():
            self._draw_nine_slice(painter, r, self._frame_pixmap)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#111633")))
            painter.drawRect(r)
            inner = r.adjusted(4, 4, -4, -4)
            painter.setBrush(QBrush(QColor("#1B2455")))
            painter.drawRect(inner)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#D8E6FF"), 2))
            painter.drawRect(r.adjusted(1, 1, -1, -1))
            painter.setPen(QPen(QColor("#5A77C8"), 1))
            painter.drawRect(r.adjusted(5, 5, -5, -5))

        self.draw_selection_handle(painter)

    def to_layout_object(self) -> LayoutObject:
        return LayoutObject(
            id=self.obj_id,
            name=self.obj_name,
            type=self.obj_type,
            x=int(self.pos().x()),
            y=int(self.pos().y()),
            w=int(self._w),
            h=int(self._h),
            frame_image_path=self.frame_image_path,
            slice_left=self.slice_left,
            slice_right=self.slice_right,
            slice_top=self.slice_top,
            slice_bottom=self.slice_bottom,
            z_value=int(self.zValue()),
            bitmap_font_json=self.bitmap_font_json,
        )

    def apply_layout_object(self, obj: LayoutObject) -> None:
        self.prepareGeometryChange()
        self.obj_name = obj.name or self.obj_type or "window"
        self._w = max(GRID_SIZE, obj.w)
        self._h = max(GRID_SIZE, obj.h)

        path_changed = self.frame_image_path != obj.frame_image_path
        self.frame_image_path = obj.frame_image_path
        self.slice_left = max(1, obj.slice_left)
        self.slice_right = max(1, obj.slice_right)
        self.slice_top = max(1, obj.slice_top)
        self.slice_bottom = max(1, obj.slice_bottom)

        self.bitmap_font_json = obj.bitmap_font_json
        self.bitmap_font = BitmapFont(obj.bitmap_font_json) if obj.bitmap_font_json else None

        self.setPos(obj.x, obj.y)
        self.setZValue(obj.z_value)

        if path_changed:
            self._load_frame_pixmap()

        self.update()


class MessageWindowItem(WindowItem):
    def __init__(self, obj: LayoutObject):
        super().__init__(obj)
        self.text = obj.text or "スライムがあらわれた！\nこうげきする？"

    def display_name(self) -> str:
        return self.obj_name or "Message"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)

        if self.bitmap_font and self.bitmap_font.is_valid:
            max_rows = max(1, (self._h - 32) // self.bitmap_font.glyph_height)
            max_cols = max(1, (self._w - 32) // self.bitmap_font.glyph_width)
            lines = self.text.splitlines()[:max_rows]
            clipped = [line[:max_cols] for line in lines]
            self.bitmap_font.draw_text(painter, 16, 16, "\n".join(clipped))
        else:
            font = QFont("Courier New", 10)
            font.setStyleHint(QFont.Monospace)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF"))

            text_area = QRectF(16, 16, self._w - 32, self._h - 32)
            max_rows = max(1, (self._h - 32) // TEXT_CELL_HEIGHT)
            max_cols = max(1, (self._w - 32) // TEXT_CELL_WIDTH)
            lines = self.text.splitlines()[:max_rows]

            for i, line in enumerate(lines):
                y = text_area.top() + i * TEXT_CELL_HEIGHT + 12
                painter.drawText(QPointF(text_area.left(), y), line[:max_cols])

    def to_layout_object(self) -> LayoutObject:
        obj = super().to_layout_object()
        obj.text = self.text
        return obj

    def apply_layout_object(self, obj: LayoutObject) -> None:
        super().apply_layout_object(obj)
        self.text = obj.text
        self.update()


class CommandMenuItem(WindowItem):
    def __init__(self, obj: LayoutObject):
        super().__init__(obj)
        self.lines = obj.lines or ["たたかう", "まほう", "どうぐ", "にげる"]
        self.selected_index = obj.selected_index
        self.cursor_image_path = obj.cursor_image_path
        self.cursor_offset_x = obj.cursor_offset_x
        self.cursor_offset_y = obj.cursor_offset_y
        self._cursor_pixmap = QPixmap()
        self._load_cursor_pixmap()

    def _load_cursor_pixmap(self) -> None:
        self._cursor_pixmap = QPixmap(self.cursor_image_path) if self.cursor_image_path else QPixmap()

    def display_name(self) -> str:
        return self.obj_name or "CommandMenu"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        glyph_w = self.bitmap_font.glyph_width if self.bitmap_font and self.bitmap_font.is_valid else TEXT_CELL_WIDTH
        glyph_h = self.bitmap_font.glyph_height if self.bitmap_font and self.bitmap_font.is_valid else TEXT_CELL_HEIGHT

        base_x = 16
        cursor_area_w = glyph_w * 2
        text_x = base_x + cursor_area_w

        for i, line in enumerate(self.lines):
            baseline_y = 16 + glyph_h + i * glyph_h
            selected = i == self.selected_index

            if selected and not self._cursor_pixmap.isNull():
                target_h = glyph_h
                src_w = max(1, self._cursor_pixmap.width())
                src_h = max(1, self._cursor_pixmap.height())
                target_w = max(8, round(src_w * (target_h / src_h)))
                cx = base_x + self.cursor_offset_x
                cy = baseline_y - glyph_h + self.cursor_offset_y
                painter.drawPixmap(QRectF(cx, cy, target_w, target_h).toRect(), self._cursor_pixmap)
            elif selected:
                if self.bitmap_font and self.bitmap_font.is_valid:
                    self.bitmap_font.draw_text(
                        painter,
                        base_x + self.cursor_offset_x,
                        baseline_y - glyph_h + self.cursor_offset_y,
                        "▶",
                    )
                else:
                    font = QFont("Courier New", 10)
                    font.setStyleHint(QFont.Monospace)
                    font.setBold(True)
                    painter.setFont(font)
                    painter.setPen(QColor("#FFE680"))
                    painter.drawText(QPointF(base_x + self.cursor_offset_x, baseline_y + self.cursor_offset_y), "▶")

            if self.bitmap_font and self.bitmap_font.is_valid:
                self.bitmap_font.draw_text(painter, text_x, baseline_y - glyph_h, line)
            else:
                font = QFont("Courier New", 10)
                font.setStyleHint(QFont.Monospace)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#FFE680") if selected else QColor("#FFFFFF"))
                painter.drawText(QPointF(text_x, baseline_y), line)

    def to_layout_object(self) -> LayoutObject:
        obj = super().to_layout_object()
        obj.lines = self.lines
        obj.selected_index = self.selected_index
        obj.cursor_image_path = self.cursor_image_path
        obj.cursor_offset_x = self.cursor_offset_x
        obj.cursor_offset_y = self.cursor_offset_y
        return obj

    def apply_layout_object(self, obj: LayoutObject) -> None:
        super().apply_layout_object(obj)
        self.lines = obj.lines or []
        self.selected_index = max(0, min(obj.selected_index, max(0, len(self.lines) - 1)))

        path_changed = self.cursor_image_path != obj.cursor_image_path
        self.cursor_image_path = obj.cursor_image_path
        self.cursor_offset_x = obj.cursor_offset_x
        self.cursor_offset_y = obj.cursor_offset_y

        if path_changed:
            self._load_cursor_pixmap()

        self.update()


class ImageItem(ResizableFrameItem):
    def __init__(self, obj: LayoutObject):
        super().__init__(obj)
        self.image_path = obj.image_path
        self.image_scale = max(1, obj.image_scale)
        self._pixmap = QPixmap()
        self._base_w = GRID_SIZE
        self._base_h = GRID_SIZE
        self._load_pixmap()
        self._sync_size_from_scale()
        self.setPos(obj.x, obj.y)

    def _load_pixmap(self) -> None:
        self._pixmap = QPixmap(self.image_path) if self.image_path else QPixmap()
        if not self._pixmap.isNull():
            self._base_w = max(1, self._pixmap.width())
            self._base_h = max(1, self._pixmap.height())
        else:
            self._base_w = GRID_SIZE
            self._base_h = GRID_SIZE

    def _sync_size_from_scale(self) -> None:
        self._w = max(GRID_SIZE, self._base_w * self.image_scale)
        self._h = max(GRID_SIZE, self._base_h * self.image_scale)

    def display_name(self) -> str:
        return self.obj_name or "Image"

    def compute_resized_size(self, delta: QPointF) -> tuple[int, int]:
        approx_w = max(1, int(self._start_rect.width() + delta.x()))
        approx_h = max(1, int(self._start_rect.height() + delta.y()))
        scale_x = max(1, round(approx_w / max(1, self._base_w)))
        scale_y = max(1, round(approx_h / max(1, self._base_h)))
        self.image_scale = max(1, max(scale_x, scale_y))
        return self._base_w * self.image_scale, self._base_h * self.image_scale

    def paint(self, painter: QPainter, option, widget=None):
        r = self.content_rect()
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        if not self._pixmap.isNull():
            painter.drawPixmap(r.toRect(), self._pixmap)
        else:
            painter.setPen(QPen(QColor("#FF8888"), 1, Qt.DashLine))
            painter.setBrush(QBrush(QColor(80, 20, 20, 80)))
            painter.drawRect(r)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(r.adjusted(8, 8, -8, -8), Qt.AlignCenter, "No Image")

        if self.isSelected():
            painter.setPen(QPen(QColor("#80C0FF"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(r)

        self.draw_selection_handle(painter)

    def to_layout_object(self) -> LayoutObject:
        return LayoutObject(
            id=self.obj_id,
            name=self.obj_name,
            type=self.obj_type,
            x=int(self.pos().x()),
            y=int(self.pos().y()),
            w=int(self._w),
            h=int(self._h),
            image_path=self.image_path,
            image_scale=self.image_scale,
            z_value=int(self.zValue()),
        )

    def apply_layout_object(self, obj: LayoutObject) -> None:
        self.prepareGeometryChange()
        self.obj_name = obj.name or "image"
        path_changed = self.image_path != obj.image_path
        self.image_path = obj.image_path

        if path_changed:
            self._load_pixmap()

        self.image_scale = max(1, obj.image_scale)
        if obj.w > 0 and obj.h > 0 and not path_changed:
            scale_x = max(1, round(obj.w / max(1, self._base_w)))
            scale_y = max(1, round(obj.h / max(1, self._base_h)))
            self.image_scale = max(1, max(scale_x, scale_y))

        self._sync_size_from_scale()
        self.setPos(obj.x, obj.y)
        self.setZValue(obj.z_value)
        self.update()


class EditorScene(QGraphicsScene):
    selection_changed_for_ui = Signal()
    item_list_changed = Signal()

    def __init__(self):
        super().__init__(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        self.setBackgroundBrush(QColor("#101018"))
        self._rebuilding = False
        self.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        if self._rebuilding:
            return
        self.selection_changed_for_ui.emit()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.save()
        painter.setPen(QPen(QColor(50, 50, 70), 1))
        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)

        for x in range(left, int(rect.right()) + GRID_SIZE, GRID_SIZE):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top, int(rect.bottom()) + GRID_SIZE, GRID_SIZE):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

        painter.setPen(QPen(QColor("#80C0FF"), 2))
        painter.drawRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        painter.restore()

    def selected_editor_item(self) -> Optional[BaseEditorItem]:
        items = self.selectedItems()
        return items[0] if items else None

    def all_editor_items(self) -> list[BaseEditorItem]:
        return [item for item in self.items() if isinstance(item, BaseEditorItem)]

    def find_item_by_id(self, obj_id: str) -> Optional[BaseEditorItem]:
        for item in self.all_editor_items():
            if getattr(item, "obj_id", None) == obj_id:
                return item
        return None

    def _max_z(self) -> int:
        items = self.all_editor_items()
        return int(max((item.zValue() for item in items), default=0))

    def _min_z(self) -> int:
        items = self.all_editor_items()
        return int(min((item.zValue() for item in items), default=0))

    def bring_selected_to_front(self) -> None:
        item = self.selected_editor_item()
        if item is None:
            return
        item.setZValue(self._max_z() + 1)
        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()

    def send_selected_to_back(self) -> None:
        item = self.selected_editor_item()
        if item is None:
            return
        item.setZValue(self._min_z() - 1)
        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()

    def _add_and_select(self, item: BaseEditorItem) -> None:
        item.setZValue(self._max_z() + 1)
        self.addItem(item)
        self.clearSelection()
        item.setSelected(True)
        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()

    def add_window_item(self) -> WindowItem:
        item = WindowItem(
            LayoutObject(
                id=str(uuid.uuid4()),
                name="window",
                type="window",
                x=0,
                y=CANVAS_HEIGHT - 128,
                w=CANVAS_WIDTH,
                h=128,
            )
        )
        self._add_and_select(item)
        return item

    def add_message_window_item(self) -> MessageWindowItem:
        item = MessageWindowItem(
            LayoutObject(
                id=str(uuid.uuid4()),
                name="message_window",
                type="message_window",
                x=0,
                y=CANVAS_HEIGHT - 128,
                w=CANVAS_WIDTH,
                h=128,
                text="スライムがあらわれた！\nなにをする？",
            )
        )
        self._add_and_select(item)
        return item

    def add_command_menu_item(self) -> CommandMenuItem:
        item = CommandMenuItem(
            LayoutObject(
                id=str(uuid.uuid4()),
                name="command_menu",
                type="command_menu",
                x=CANVAS_WIDTH - 160,
                y=CANVAS_HEIGHT - 176,
                w=160,
                h=112,
                lines=["たたかう", "まほう", "どうぐ", "にげる"],
                selected_index=0,
            )
        )
        self._add_and_select(item)
        return item

    def add_text_area_item(self) -> TextAreaItem:
        item = TextAreaItem(
            LayoutObject(
                id=str(uuid.uuid4()),
                name="text_area",
                type="text_area",
                x=16,
                y=16,
                w=160,
                h=48,
                text="HP 120/120",
            )
        )
        self._add_and_select(item)
        return item

    def add_image_item(self, image_path: str) -> Optional[ImageItem]:
        if not image_path:
            return None
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None
        item = ImageItem(
            LayoutObject(
                id=str(uuid.uuid4()),
                name=Path(image_path).stem or "image",
                type="image",
                x=16,
                y=16,
                image_path=image_path,
                image_scale=1,
            )
        )
        self._add_and_select(item)
        return item

    def to_dict(self) -> dict:
        objects = [asdict(item.to_layout_object()) for item in reversed(self.all_editor_items())]
        return {
            "meta": {
                "canvas_width": CANVAS_WIDTH,
                "canvas_height": CANVAS_HEIGHT,
                "grid_size": GRID_SIZE,
            },
            "objects": objects,
        }

    def load_dict(self, data: dict) -> None:
        self._rebuilding = True
        try:
            self.clearSelection()
            self.clear()

            for obj_data in data.get("objects", []):
                obj = LayoutObject(**obj_data)
                if obj.type == "window":
                    self.addItem(WindowItem(obj))
                elif obj.type == "message_window":
                    self.addItem(MessageWindowItem(obj))
                elif obj.type == "command_menu":
                    self.addItem(CommandMenuItem(obj))
                elif obj.type == "image":
                    self.addItem(ImageItem(obj))
                elif obj.type in {"label", "text_area"}:
                    if obj.type == "label":
                        obj.type = "text_area"
                        if not obj.name:
                            obj.name = "text_area"
                        if not obj.w:
                            obj.w = 160
                        if not obj.h:
                            obj.h = 48
                    self.addItem(TextAreaItem(obj))
        finally:
            self._rebuilding = False

        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()

    def delete_selected(self) -> None:
        self._rebuilding = True
        try:
            for item in list(self.selectedItems()):
                self.removeItem(item)
        finally:
            self._rebuilding = False

        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()

    def apply_template(self, template_name: str) -> None:
        self._rebuilding = True
        try:
            self.clearSelection()
            self.clear()

            def add_item(item: BaseEditorItem) -> None:
                item.setZValue(self._max_z() + 1)
                self.addItem(item)

            def make_text_area(x: int, y: int, text: str, name: str) -> None:
                add_item(
                    TextAreaItem(
                        LayoutObject(
                            id=str(uuid.uuid4()),
                            name=name,
                            type="text_area",
                            x=x,
                            y=y,
                            w=160,
                            h=48,
                            text=text,
                        )
                    )
                )

            selected_item: Optional[BaseEditorItem] = None

            if template_name == "battle":
                make_text_area(16, 16, "HP 120/120   MP 30/30", "battle_status_text")

                msg = MessageWindowItem(
                    LayoutObject(
                        id=str(uuid.uuid4()),
                        name="battle_message",
                        type="message_window",
                        x=0,
                        y=CANVAS_HEIGHT - 128,
                        w=CANVAS_WIDTH,
                        h=128,
                        text="スライムがあらわれた！\nなにをする？",
                    )
                )
                add_item(msg)

                cmd = CommandMenuItem(
                    LayoutObject(
                        id=str(uuid.uuid4()),
                        name="battle_command",
                        type="command_menu",
                        x=CANVAS_WIDTH - 160,
                        y=CANVAS_HEIGHT - 176,
                        w=160,
                        h=112,
                        lines=["たたかう", "まほう", "どうぐ", "にげる"],
                        selected_index=0,
                    )
                )
                add_item(cmd)
                selected_item = cmd

            elif template_name == "field":
                make_text_area(16, 16, "アサムシのまち", "field_title")

                msg = MessageWindowItem(
                    LayoutObject(
                        id=str(uuid.uuid4()),
                        name="field_message",
                        type="message_window",
                        x=0,
                        y=CANVAS_HEIGHT - 128,
                        w=CANVAS_WIDTH,
                        h=128,
                        text="ようこそ、アサムシのまちへ。",
                    )
                )
                add_item(msg)
                selected_item = msg

            elif template_name == "menu":
                add_item(
                    WindowItem(
                        LayoutObject(
                            id=str(uuid.uuid4()),
                            name="status_window",
                            type="window",
                            x=16,
                            y=16,
                            w=608,
                            h=144,
                        )
                    )
                )

                make_text_area(32, 40, "リュウイチ  Lv12  HP120/120  MP30/30", "menu_status_text")

                cmd = CommandMenuItem(
                    LayoutObject(
                        id=str(uuid.uuid4()),
                        name="menu_command",
                        type="command_menu",
                        x=432,
                        y=192,
                        w=160,
                        h=112,
                        lines=["どうぐ", "そうび", "じゅもん", "セーブ"],
                        selected_index=0,
                    )
                )
                add_item(cmd)
                selected_item = cmd

            else:
                msg = MessageWindowItem(
                    LayoutObject(
                        id=str(uuid.uuid4()),
                        name="message_window",
                        type="message_window",
                        x=0,
                        y=CANVAS_HEIGHT - 128,
                        w=CANVAS_WIDTH,
                        h=128,
                        text="メッセージ",
                    )
                )
                add_item(msg)
                selected_item = msg

            self.clearSelection()
            if selected_item is not None:
                selected_item.setSelected(True)
        finally:
            self._rebuilding = False

        self.item_list_changed.emit()
        self.selection_changed_for_ui.emit()


class EditorView(QGraphicsView):
    mouse_scene_pos_changed = Signal(int, int)

    def __init__(self, scene: EditorScene):
        super().__init__(scene)
        self.display_scale = 1
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.TextAntialiasing, False)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setAlignment(Qt.AlignCenter)
        self.setSceneRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        self.setMinimumSize(CANVAS_WIDTH + 40, CANVAS_HEIGHT + 40)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.set_display_scale(1)

    def set_display_scale(self, scale: int) -> None:
        self.display_scale = max(1, int(scale))
        self.resetTransform()
        self.scale(self.display_scale, self.display_scale)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_scene_pos_changed.emit(int(scene_pos.x()), int(scene_pos.y()))
        super().mouseMoveEvent(event)


class PropertyPanel(QWidget):
    changed = Signal()
    choose_image_requested = Signal()
    choose_cursor_requested = Signal()
    choose_frame_requested = Signal()
    choose_bitmap_font_requested = Signal()
    save_preset_requested = Signal(str)
    load_preset_requested = Signal(str)
    delete_preset_requested = Signal(str)

    def __init__(self, scene: EditorScene):
        super().__init__()
        self.scene = scene
        self._updating = False
        self.current_item_id: Optional[str] = None

        layout = QFormLayout(self)

        self.type_label = QLabel("-")
        self.id_label = QLabel("-")
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumWidth(220)

        self.x_spin = QSpinBox()
        self.y_spin = QSpinBox()
        self.w_spin = QSpinBox()
        self.h_spin = QSpinBox()
        self.z_spin = QSpinBox()

        self.text_edit = QPlainTextEdit()
        self.text_edit.setMinimumWidth(220)
        self.text_edit.setMinimumHeight(120)

        self.cursor_spin = QSpinBox()
        self.cursor_offset_x_spin = QSpinBox()
        self.cursor_offset_y_spin = QSpinBox()

        self.char_count_label = QLabel("0 / 0")

        self.font_path_edit = QLineEdit()
        self.font_path_edit.setReadOnly(True)

        self.image_path_edit = QLineEdit()
        self.image_path_edit.setReadOnly(True)

        self.cursor_path_edit = QLineEdit()
        self.cursor_path_edit.setReadOnly(True)

        self.frame_path_edit = QLineEdit()
        self.frame_path_edit.setReadOnly(True)

        self.slice_left_spin = QSpinBox()
        self.slice_right_spin = QSpinBox()
        self.slice_top_spin = QSpinBox()
        self.slice_bottom_spin = QSpinBox()

        self.choose_font_button = QPushButton("フォントを選択")
        self.clear_font_button = QPushButton("フォントを解除")
        self.choose_image_button = QPushButton("画像を選択")
        self.choose_cursor_button = QPushButton("カーソル画像を選択")
        self.choose_frame_button = QPushButton("フレーム画像を選択")

        self.preset_name_edit = QLineEdit()
        self.preset_combo = QComboBox()
        self.save_preset_button = QPushButton("プリセットを保存")
        self.load_preset_button = QPushButton("プリセットを適用")
        self.delete_preset_button = QPushButton("プリセットを削除")

        for spin in (
            self.x_spin,
            self.y_spin,
            self.w_spin,
            self.h_spin,
            self.z_spin,
            self.slice_left_spin,
            self.slice_right_spin,
            self.slice_top_spin,
            self.slice_bottom_spin,
            self.cursor_offset_x_spin,
            self.cursor_offset_y_spin,
        ):
            spin.setRange(-9999, 9999)
            spin.setSingleStep(GRID_SIZE)
            spin.valueChanged.connect(self.apply_changes)

        for spin in (self.slice_left_spin, self.slice_right_spin, self.slice_top_spin, self.slice_bottom_spin):
            spin.setRange(1, 9999)
            spin.setSingleStep(1)

        self.cursor_spin.setRange(0, 99)
        self.cursor_spin.valueChanged.connect(self.apply_changes)

        self.name_edit.textChanged.connect(self.apply_changes)
        self.text_edit.textChanged.connect(self.apply_changes)

        self.choose_image_button.clicked.connect(self.choose_image_requested.emit)
        self.choose_cursor_button.clicked.connect(self.choose_cursor_requested.emit)
        self.choose_frame_button.clicked.connect(self.choose_frame_requested.emit)
        self.choose_font_button.clicked.connect(self.choose_bitmap_font_requested.emit)
        self.clear_font_button.clicked.connect(self._clear_font)

        self.save_preset_button.clicked.connect(lambda: self.save_preset_requested.emit(self.preset_name_edit.text().strip()))
        self.load_preset_button.clicked.connect(lambda: self.load_preset_requested.emit(self.preset_combo.currentText().strip()))
        self.delete_preset_button.clicked.connect(lambda: self.delete_preset_requested.emit(self.preset_combo.currentText().strip()))

        layout.addRow("種類", self.type_label)
        layout.addRow("ID", self.id_label)
        layout.addRow("名前", self.name_edit)
        layout.addRow("X", self.x_spin)
        layout.addRow("Y", self.y_spin)
        layout.addRow("W", self.w_spin)
        layout.addRow("H", self.h_spin)
        layout.addRow("Z", self.z_spin)
        layout.addRow("テキスト", self.text_edit)
        layout.addRow("カーソル位置", self.cursor_spin)
        layout.addRow("カーソルX", self.cursor_offset_x_spin)
        layout.addRow("カーソルY", self.cursor_offset_y_spin)
        layout.addRow("文字数", self.char_count_label)
        layout.addRow("ビットマップフォント", self.font_path_edit)
        layout.addRow("", self.choose_font_button)
        layout.addRow("", self.clear_font_button)
        layout.addRow("画像", self.image_path_edit)
        layout.addRow("", self.choose_image_button)
        layout.addRow("カーソル画像", self.cursor_path_edit)
        layout.addRow("", self.choose_cursor_button)
        layout.addRow("フレーム画像", self.frame_path_edit)
        layout.addRow("左スライス", self.slice_left_spin)
        layout.addRow("右スライス", self.slice_right_spin)
        layout.addRow("上スライス", self.slice_top_spin)
        layout.addRow("下スライス", self.slice_bottom_spin)
        layout.addRow("", self.choose_frame_button)
        layout.addRow("プリセット名", self.preset_name_edit)
        layout.addRow("プリセット一覧", self.preset_combo)
        layout.addRow("", self.save_preset_button)
        layout.addRow("", self.load_preset_button)
        layout.addRow("", self.delete_preset_button)

    def _clear_font(self) -> None:
        self.font_path_edit.setText("")
        self.apply_changes()

    def set_presets(self, names: list[str]) -> None:
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(names)
        index = self.preset_combo.findText(current)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)

    def set_item(self, item: Optional[BaseEditorItem]) -> None:
        self._updating = True

        if item is None:
            self.current_item_id = None
            self.type_label.setText("-")
            self.id_label.setText("-")
            self.name_edit.setText("")
            self.x_spin.setValue(0)
            self.y_spin.setValue(0)
            self.w_spin.setValue(0)
            self.h_spin.setValue(0)
            self.z_spin.setValue(0)
            self.text_edit.setPlainText("")
            self.cursor_spin.setValue(0)
            self.cursor_offset_x_spin.setValue(0)
            self.cursor_offset_y_spin.setValue(0)
            self.char_count_label.setText("0 / 0")
            self.font_path_edit.setText("")
            self.image_path_edit.setText("")
            self.cursor_path_edit.setText("")
            self.frame_path_edit.setText("")
            self.slice_left_spin.setValue(16)
            self.slice_right_spin.setValue(16)
            self.slice_top_spin.setValue(16)
            self.slice_bottom_spin.setValue(16)
            self._set_enabled(False, False, False, False, False)
            self._updating = False
            return

        self.current_item_id = item.obj_id
        obj = item.to_layout_object()

        self.type_label.setText(obj.type)
        self.id_label.setText(obj.id)
        self.name_edit.setText(obj.name)
        self.x_spin.setValue(obj.x)
        self.y_spin.setValue(obj.y)
        self.w_spin.setValue(obj.w)
        self.h_spin.setValue(obj.h)
        self.z_spin.setValue(obj.z_value)
        self.text_edit.setPlainText(obj.text if obj.type != "command_menu" else "\n".join(obj.lines or []))
        self.cursor_spin.setValue(obj.selected_index)
        self.cursor_offset_x_spin.setValue(obj.cursor_offset_x)
        self.cursor_offset_y_spin.setValue(obj.cursor_offset_y)
        self.font_path_edit.setText(obj.bitmap_font_json)
        self.image_path_edit.setText(obj.image_path)
        self.cursor_path_edit.setText(obj.cursor_image_path)
        self.frame_path_edit.setText(obj.frame_image_path)
        self.slice_left_spin.setValue(max(1, obj.slice_left))
        self.slice_right_spin.setValue(max(1, obj.slice_right))
        self.slice_top_spin.setValue(max(1, obj.slice_top))
        self.slice_bottom_spin.setValue(max(1, obj.slice_bottom))

        is_sized = obj.type in {"window", "message_window", "command_menu", "image", "text_area"}
        has_text = obj.type in {"text_area", "message_window", "command_menu"}
        has_cursor = obj.type == "command_menu"
        has_image = obj.type == "image"
        has_frame = obj.type in {"window", "message_window", "command_menu"}

        self._set_enabled(is_sized, has_text, has_cursor, has_image, has_frame)
        self._refresh_char_count(obj)
        self._updating = False

    def _set_enabled(self, is_sized: bool, has_text: bool, has_cursor: bool, has_image: bool, has_frame: bool) -> None:
        self.w_spin.setEnabled(is_sized)
        self.h_spin.setEnabled(is_sized)
        self.z_spin.setEnabled(True)
        self.text_edit.setEnabled(has_text)
        self.cursor_spin.setEnabled(has_cursor)
        self.cursor_offset_x_spin.setEnabled(has_cursor)
        self.cursor_offset_y_spin.setEnabled(has_cursor)
        self.image_path_edit.setEnabled(has_image)
        self.choose_image_button.setEnabled(has_image)
        self.cursor_path_edit.setEnabled(has_cursor)
        self.choose_cursor_button.setEnabled(has_cursor)
        self.frame_path_edit.setEnabled(has_frame)
        self.choose_frame_button.setEnabled(has_frame)
        self.slice_left_spin.setEnabled(has_frame)
        self.slice_right_spin.setEnabled(has_frame)
        self.slice_top_spin.setEnabled(has_frame)
        self.slice_bottom_spin.setEnabled(has_frame)
        self.font_path_edit.setEnabled(has_text)
        self.choose_font_button.setEnabled(has_text)
        self.clear_font_button.setEnabled(has_text)
        self.preset_name_edit.setEnabled(has_frame)
        self.preset_combo.setEnabled(True)
        self.save_preset_button.setEnabled(has_frame)
        self.load_preset_button.setEnabled(True)
        self.delete_preset_button.setEnabled(True)

    def _refresh_char_count(self, obj: LayoutObject) -> None:
        if obj.type in {"text_area", "message_window"}:
            self.char_count_label.setText(f"{len(obj.text)} chars")
        elif obj.type == "command_menu":
            self.char_count_label.setText(f"{sum(len(line) for line in (obj.lines or []))} chars")
        elif obj.type == "image":
            self.char_count_label.setText("image")
        else:
            self.char_count_label.setText("-")

    def apply_changes(self) -> None:
        if self._updating or self.current_item_id is None:
            return

        item = self.scene.find_item_by_id(self.current_item_id)
        if item is None:
            self.set_item(None)
            return

        obj = item.to_layout_object()
        obj.x = (self.x_spin.value() // GRID_SIZE) * GRID_SIZE
        obj.y = (self.y_spin.value() // GRID_SIZE) * GRID_SIZE
        obj.name = self.name_edit.text().strip() or obj.type or "item"
        obj.z_value = self.z_spin.value()
        obj.bitmap_font_json = self.font_path_edit.text().strip()

        if obj.type in {"window", "message_window", "command_menu", "image", "text_area"}:
            obj.w = max(GRID_SIZE, (self.w_spin.value() // GRID_SIZE) * GRID_SIZE)
            obj.h = max(GRID_SIZE, (self.h_spin.value() // GRID_SIZE) * GRID_SIZE)

        obj.slice_left = max(1, self.slice_left_spin.value())
        obj.slice_right = max(1, self.slice_right_spin.value())
        obj.slice_top = max(1, self.slice_top_spin.value())
        obj.slice_bottom = max(1, self.slice_bottom_spin.value())
        obj.cursor_offset_x = self.cursor_offset_x_spin.value()
        obj.cursor_offset_y = self.cursor_offset_y_spin.value()

        if obj.type in {"text_area", "message_window"}:
            obj.text = self.text_edit.toPlainText()
        elif obj.type == "command_menu":
            obj.lines = [line for line in self.text_edit.toPlainText().splitlines() if line.strip()]
            if not obj.lines:
                obj.lines = ["たたかう"]
            obj.selected_index = max(0, min(self.cursor_spin.value(), len(obj.lines) - 1))

        item.apply_layout_object(obj)
        refreshed = item.to_layout_object()
        self.w_spin.setValue(refreshed.w)
        self.h_spin.setValue(refreshed.h)
        self._refresh_char_count(refreshed)
        self.changed.emit()


class ObjectListPanel(QWidget):
    def __init__(self, scene: EditorScene):
        super().__init__()
        self.scene = scene
        self.list_widget = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        self.list_widget.currentRowChanged.connect(self._select_scene_item)

    def refresh(self) -> None:
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        items = sorted(self.scene.all_editor_items(), key=lambda i: i.zValue())
        for scene_item in items:
            label = f"{scene_item.display_name()} (z={int(scene_item.zValue())})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, scene_item.obj_id)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

    def sync_to_scene_selection(self) -> None:
        selected = self.scene.selected_editor_item()
        selected_id = selected.obj_id if selected is not None else None

        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == selected_id:
                self.list_widget.setCurrentRow(i)
                break
        else:
            self.list_widget.setCurrentRow(-1)
        self.list_widget.blockSignals(False)

    def _select_scene_item(self, row: int) -> None:
        self.scene.clearSelection()
        if row < 0:
            return
        item = self.list_widget.item(row)
        obj_id = item.data(Qt.UserRole)
        scene_item = self.scene.find_item_by_id(obj_id)
        if scene_item is not None:
            scene_item.setSelected(True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("レトロRPG UIエディタ")
        self.resize(1360, 860)
        self.setMinimumWidth(1180)

        self.current_file: Optional[Path] = None
        self.scene = EditorScene()
        self.view = EditorView(self.scene)
        self.setCentralWidget(self.view)

        self.property_panel = PropertyPanel(self.scene)
        self.object_list_panel = ObjectListPanel(self.scene)
        self.frame_presets: dict[str, dict] = {}

        self._build_docks()
        self._build_toolbar()
        self._build_status()
        self._connect_signals()
        self._load_presets_from_disk()
        self.new_document()

    def _build_docks(self) -> None:
        left_dock = QDockWidget("オブジェクト", self)
        left_dock.setWidget(self.object_list_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        right_dock = QDockWidget("プロパティ", self)
        right_dock.setWidget(self.property_panel)
        right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        right_dock.setMinimumWidth(340)
        right_dock.setMaximumWidth(340)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

        tool_panel = QWidget()
        tool_layout = QVBoxLayout(tool_panel)

        btn_window = QPushButton("ウィンドウ追加")
        btn_message = QPushButton("メッセージ枠追加")
        btn_menu = QPushButton("コマンド枠追加")
        btn_text = QPushButton("テキスト追加")
        btn_image = QPushButton("画像追加")
        btn_front = QPushButton("最前面へ")
        btn_back = QPushButton("最背面へ")
        btn_delete = QPushButton("選択を削除")
        template_combo = QComboBox()
        template_combo.addItem("戦闘", "battle")
        template_combo.addItem("フィールド", "field")
        template_combo.addItem("メニュー", "menu")
        btn_apply_template = QPushButton("テンプレート適用")
        btn_scale_1x = QPushButton("表示 1x")
        btn_scale_2x = QPushButton("表示 2x")
        btn_export_png = QPushButton("PNGを書き出し")

        for w in (
            btn_window,
            btn_message,
            btn_menu,
            btn_text,
            btn_image,
            btn_front,
            btn_back,
            btn_delete,
            QLabel("テンプレート"),
            template_combo,
            btn_apply_template,
            btn_scale_1x,
            btn_scale_2x,
            btn_export_png,
        ):
            tool_layout.addWidget(w)
        tool_layout.addStretch()

        btn_window.clicked.connect(self.scene.add_window_item)
        btn_message.clicked.connect(self.scene.add_message_window_item)
        btn_menu.clicked.connect(self.scene.add_command_menu_item)
        btn_text.clicked.connect(self.scene.add_text_area_item)
        btn_image.clicked.connect(self.add_image_item)
        btn_front.clicked.connect(self.bring_selected_to_front)
        btn_back.clicked.connect(self.send_selected_to_back)
        btn_delete.clicked.connect(self.safe_delete_selected)
        btn_apply_template.clicked.connect(lambda: self.safe_apply_template(template_combo.currentData()))
        btn_scale_1x.clicked.connect(lambda: self.set_view_scale(1))
        btn_scale_2x.clicked.connect(lambda: self.set_view_scale(2))
        btn_export_png.clicked.connect(self.export_png)

        tool_dock = QDockWidget("ツール", self)
        tool_dock.setWidget(tool_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, tool_dock)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("メイン")

        act_new = QAction("新規", self)
        act_open = QAction("開く", self)
        act_save = QAction("保存", self)
        act_save_as = QAction("名前を付けて保存", self)
        act_export = QAction("PNGを書き出し", self)
        act_view_1x = QAction("表示 1x", self)
        act_view_2x = QAction("表示 2x", self)

        act_new.setShortcut(QKeySequence.New)
        act_open.setShortcut(QKeySequence.Open)
        act_save.setShortcut(QKeySequence.Save)

        act_new.triggered.connect(self.new_document)
        act_open.triggered.connect(self.open_document)
        act_save.triggered.connect(self.save_document)
        act_save_as.triggered.connect(self.save_document_as)
        act_export.triggered.connect(self.export_png)
        act_view_1x.triggered.connect(lambda: self.set_view_scale(1))
        act_view_2x.triggered.connect(lambda: self.set_view_scale(2))

        toolbar.addAction(act_new)
        toolbar.addAction(act_open)
        toolbar.addAction(act_save)
        toolbar.addAction(act_save_as)
        toolbar.addAction(act_view_1x)
        toolbar.addAction(act_view_2x)
        toolbar.addAction(act_export)

        menu_file = self.menuBar().addMenu("ファイル")
        menu_file.addAction(act_new)
        menu_file.addAction(act_open)
        menu_file.addAction(act_save)
        menu_file.addAction(act_save_as)
        menu_file.addSeparator()
        menu_file.addAction(act_export)

        menu_view = self.menuBar().addMenu("表示")
        menu_view.addAction(act_view_1x)
        menu_view.addAction(act_view_2x)

    def _build_status(self) -> None:
        self.coord_label = QLabel("x: -, y: -")
        self.statusBar().addPermanentWidget(self.coord_label)

    def _connect_signals(self) -> None:
        self.scene.selection_changed_for_ui.connect(self._sync_selection)
        self.scene.item_list_changed.connect(self.object_list_panel.refresh)
        self.scene.item_list_changed.connect(self._mark_dirty)
        self.property_panel.changed.connect(self.object_list_panel.refresh)
        self.property_panel.changed.connect(self._mark_dirty)
        self.property_panel.choose_image_requested.connect(self.choose_image_for_selected)
        self.property_panel.choose_cursor_requested.connect(self.choose_cursor_for_selected)
        self.property_panel.choose_frame_requested.connect(self.choose_frame_for_selected)
        self.property_panel.choose_bitmap_font_requested.connect(self.choose_bitmap_font_for_selected)
        self.property_panel.save_preset_requested.connect(self.save_frame_preset)
        self.property_panel.load_preset_requested.connect(self.load_frame_preset)
        self.property_panel.delete_preset_requested.connect(self.delete_frame_preset)
        self.view.mouse_scene_pos_changed.connect(self._update_mouse_coord)

    def _update_mouse_coord(self, x: int, y: int) -> None:
        self.coord_label.setText(f"x: {x}, y: {y} / view {self.view.display_scale}x")

    def set_view_scale(self, scale: int) -> None:
        self.view.set_display_scale(scale)
        self.statusBar().showMessage(f"表示倍率: {scale}x", 2000)

    def _sync_selection(self) -> None:
        item = self.scene.selected_editor_item()
        self.property_panel.set_item(item)
        self.object_list_panel.sync_to_scene_selection()

    def _mark_dirty(self) -> None:
        title = "レトロRPG UIエディタ"
        if self.current_file:
            title += f" - {self.current_file.name}"
        self.setWindowTitle(title)

    def _preset_file_path(self) -> Path:
        if self.current_file:
            return self.current_file.parent / PRESET_FILE
        return Path.cwd() / PRESET_FILE

    def _load_presets_from_disk(self) -> None:
        path = self._preset_file_path()
        if path.exists():
            try:
                self.frame_presets = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.frame_presets = {}
        else:
            self.frame_presets = {}
        self.property_panel.set_presets(sorted(self.frame_presets.keys()))

    def _save_presets_to_disk(self) -> None:
        path = self._preset_file_path()
        path.write_text(json.dumps(self.frame_presets, ensure_ascii=False, indent=2), encoding="utf-8")
        self.property_panel.set_presets(sorted(self.frame_presets.keys()))

    def new_document(self) -> None:
        self.current_file = None
        self.property_panel.set_item(None)
        self.scene.apply_template("battle")
        self.object_list_panel.refresh()
        self._sync_selection()
        self._mark_dirty()
        self._load_presets_from_disk()

    def safe_apply_template(self, template_name: str) -> None:
        self.property_panel.set_item(None)
        self.scene.apply_template(template_name)

    def safe_delete_selected(self) -> None:
        self.property_panel.set_item(None)
        self.scene.delete_selected()

    def bring_selected_to_front(self) -> None:
        self.scene.bring_selected_to_front()

    def send_selected_to_back(self) -> None:
        self.scene.send_selected_to_back()

    def add_image_item(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "画像を選択", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        item = self.scene.add_image_item(path)
        if item is None:
            QMessageBox.warning(self, "画像エラー", "画像を読み込めませんでした。")
            return
        self.object_list_panel.refresh()
        self._sync_selection()
        self._mark_dirty()

    def choose_bitmap_font_for_selected(self) -> None:
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") not in {"text_area", "message_window", "command_menu"}:
            return
        path, _ = QFileDialog.getOpenFileName(self, "ビットマップフォントJSONを選択", "", "JSON Files (*.json)")
        if not path:
            return
        obj = selected.to_layout_object()
        obj.bitmap_font_json = path
        selected.apply_layout_object(obj)
        self.property_panel.set_item(selected)
        self.object_list_panel.refresh()
        self._mark_dirty()

    def choose_image_for_selected(self) -> None:
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") != "image":
            return
        path, _ = QFileDialog.getOpenFileName(self, "画像を選択", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        obj = selected.to_layout_object()
        obj.image_path = path
        obj.image_scale = 1
        selected.apply_layout_object(obj)
        self.property_panel.set_item(selected)
        self.object_list_panel.refresh()
        self._mark_dirty()

    def choose_cursor_for_selected(self) -> None:
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") != "command_menu":
            return
        path, _ = QFileDialog.getOpenFileName(self, "カーソル画像を選択", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        obj = selected.to_layout_object()
        obj.cursor_image_path = path
        selected.apply_layout_object(obj)
        self.property_panel.set_item(selected)
        self.object_list_panel.refresh()
        self._mark_dirty()

    def choose_frame_for_selected(self) -> None:
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") not in {"window", "message_window", "command_menu"}:
            return
        path, _ = QFileDialog.getOpenFileName(self, "フレーム画像を選択", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        obj = selected.to_layout_object()
        obj.frame_image_path = path
        selected.apply_layout_object(obj)
        self.property_panel.set_item(selected)
        self.object_list_panel.refresh()
        self._mark_dirty()

    def save_frame_preset(self, name: str) -> None:
        if not name:
            QMessageBox.information(self, "プリセット", "プリセット名を入力してください。")
            return
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") not in {"window", "message_window", "command_menu"}:
            QMessageBox.information(self, "プリセット", "枠付きウィンドウを選択してください。")
            return

        obj = selected.to_layout_object()
        self.frame_presets[name] = {
            "frame_image_path": obj.frame_image_path,
            "slice_left": obj.slice_left,
            "slice_right": obj.slice_right,
            "slice_top": obj.slice_top,
            "slice_bottom": obj.slice_bottom,
        }
        self._save_presets_to_disk()
        self.property_panel.preset_name_edit.setText(name)

    def load_frame_preset(self, name: str) -> None:
        if not name or name not in self.frame_presets:
            return
        selected = self.scene.selected_editor_item()
        if selected is None or getattr(selected, "obj_type", "") not in {"window", "message_window", "command_menu"}:
            QMessageBox.information(self, "プリセット", "枠付きウィンドウを選択してください。")
            return

        preset = self.frame_presets[name]
        obj = selected.to_layout_object()
        obj.frame_image_path = preset.get("frame_image_path", "")
        obj.slice_left = int(preset.get("slice_left", 16))
        obj.slice_right = int(preset.get("slice_right", 16))
        obj.slice_top = int(preset.get("slice_top", 16))
        obj.slice_bottom = int(preset.get("slice_bottom", 16))
        selected.apply_layout_object(obj)
        self.property_panel.set_item(selected)
        self.object_list_panel.refresh()
        self._mark_dirty()

    def delete_frame_preset(self, name: str) -> None:
        if not name or name not in self.frame_presets:
            return
        del self.frame_presets[name]
        self._save_presets_to_disk()

    def export_png(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "PNGを書き出し", "ui_preview.png", "PNG Files (*.png)")
        if not path_str:
            return

        image = QImage(QSize(CANVAS_WIDTH, CANVAS_HEIGHT), QImage.Format_ARGB32)
        image.fill(QColor("#101018"))
        painter = QPainter(image)
        self.scene.render(
            painter,
            QRectF(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT),
            QRectF(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT),
        )
        painter.end()

        if not image.save(path_str):
            QMessageBox.warning(self, "書き出しエラー", "PNGを書き出せませんでした。")
            return

        self.statusBar().showMessage(f"PNGを書き出しました: {path_str}", 3000)

    def open_document(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "レイアウトを開く", "", "JSON Files (*.json)")
        if not path_str:
            return

        path = Path(path_str)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.property_panel.set_item(None)
            self.scene.load_dict(data)
            self.current_file = path
            self.object_list_panel.refresh()
            self._sync_selection()
            self._mark_dirty()
            self._load_presets_from_disk()
        except Exception as e:
            QMessageBox.critical(self, "読込エラー", f"ファイルを開けませんでした。\n{e}")

    def save_document(self) -> None:
        if self.current_file is None:
            self.save_document_as()
            return
        self._write_to_path(self.current_file)

    def save_document_as(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "レイアウトを保存", "layout.json", "JSON Files (*.json)")
        if not path_str:
            return
        path = Path(path_str)
        self.current_file = path
        self._write_to_path(path)
        self._save_presets_to_disk()

    def _write_to_path(self, path: Path) -> None:
        try:
            path.write_text(
                json.dumps(self.scene.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._mark_dirty()
            self.statusBar().showMessage(f"保存しました: {path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"保存に失敗しました。\n{e}")


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
