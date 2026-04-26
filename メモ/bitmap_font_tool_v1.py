from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


DEFAULT_CHARSET = """ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789
!?:;.,+-*/()[]<>{}=_~"'
アイウエオカキクケコサシスセソ
タチツテトナニヌネノハヒフヘホ
マミムメモヤユヨラリルレロワヲンー
"""


class BitmapFontToolWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bitmap Font Tool V1")
        self.resize(1200, 760)

        self.font_path_edit = QLineEdit()
        self.output_dir_edit = QLineEdit(str(Path.cwd()))
        self.output_name_edit = QLineEdit("bitmap_font")

        self.point_size_spin = QSpinBox()
        self.point_size_spin.setRange(4, 256)
        self.point_size_spin.setValue(16)

        self.glyph_w_spin = QSpinBox()
        self.glyph_w_spin.setRange(4, 256)
        self.glyph_w_spin.setValue(8)

        self.glyph_h_spin = QSpinBox()
        self.glyph_h_spin.setRange(4, 256)
        self.glyph_h_spin.setValue(16)

        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 128)
        self.columns_spin.setValue(16)

        self.offset_x_spin = QSpinBox()
        self.offset_x_spin.setRange(-128, 128)
        self.offset_x_spin.setValue(0)

        self.offset_y_spin = QSpinBox()
        self.offset_y_spin.setRange(-128, 128)
        self.offset_y_spin.setValue(0)

        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 32)
        self.padding_spin.setValue(0)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 255)
        self.threshold_spin.setValue(128)

        self.antialias_check = QCheckBox("Antialias")
        self.antialias_check.setChecked(False)

        self.charset_edit = QPlainTextEdit()
        self.charset_edit.setPlainText(DEFAULT_CHARSET)

        self.preview_label = QLabel("Preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(420, 420)
        self.preview_label.setStyleSheet("background:#202020; border:1px solid #555;")

        self.info_label = QLabel("")

        self.sample_text_edit = QPlainTextEdit()
        self.sample_text_edit.setPlainText(
            "HP 120/120\n"
            "コマンド\n"
            "たたかう\n"
            "スライムがあらわれた！"
        )
        self.sample_text_edit.setMaximumHeight(120)

        self._build_ui()
        self._connect_signals()
        self.refresh_preview()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)

        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        file_box = QGroupBox("Files")
        file_form = QFormLayout(file_box)

        browse_font_btn = QPushButton("Browse...")
        browse_out_btn = QPushButton("Browse...")

        font_row = QWidget()
        font_row_layout = QHBoxLayout(font_row)
        font_row_layout.setContentsMargins(0, 0, 0, 0)
        font_row_layout.addWidget(self.font_path_edit)
        font_row_layout.addWidget(browse_font_btn)

        out_row = QWidget()
        out_row_layout = QHBoxLayout(out_row)
        out_row_layout.setContentsMargins(0, 0, 0, 0)
        out_row_layout.addWidget(self.output_dir_edit)
        out_row_layout.addWidget(browse_out_btn)

        file_form.addRow("Font File", font_row)
        file_form.addRow("Output Dir", out_row)
        file_form.addRow("Output Name", self.output_name_edit)

        settings_box = QGroupBox("Settings")
        settings_form = QFormLayout(settings_box)
        settings_form.addRow("Point Size", self.point_size_spin)
        settings_form.addRow("Glyph Width", self.glyph_w_spin)
        settings_form.addRow("Glyph Height", self.glyph_h_spin)
        settings_form.addRow("Columns", self.columns_spin)
        settings_form.addRow("Offset X", self.offset_x_spin)
        settings_form.addRow("Offset Y", self.offset_y_spin)
        settings_form.addRow("Padding", self.padding_spin)
        settings_form.addRow("Threshold", self.threshold_spin)
        settings_form.addRow("", self.antialias_check)

        charset_box = QGroupBox("Characters")
        charset_layout = QVBoxLayout(charset_box)
        charset_layout.addWidget(self.charset_edit)

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_btn = QPushButton("Refresh Preview")
        self.generate_btn = QPushButton("Generate PNG + JSON")
        actions_layout.addWidget(self.preview_btn)
        actions_layout.addWidget(self.generate_btn)

        left_layout.addWidget(file_box)
        left_layout.addWidget(settings_box)
        left_layout.addWidget(charset_box)
        left_layout.addWidget(actions_row)
        left_layout.addWidget(self.info_label)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        preview_box = QGroupBox("Sheet Preview")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.preview_label)

        sample_box = QGroupBox("Sample Text")
        sample_layout = QVBoxLayout(sample_box)
        sample_layout.addWidget(self.sample_text_edit)

        right_layout.addWidget(preview_box)
        right_layout.addWidget(sample_box)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 640])

        browse_font_btn.clicked.connect(self.browse_font_file)
        browse_out_btn.clicked.connect(self.browse_output_dir)

    def _connect_signals(self) -> None:
        self.preview_btn.clicked.connect(self.refresh_preview)
        self.generate_btn.clicked.connect(self.generate_files)

        watched = [
            self.font_path_edit,
            self.output_name_edit,
            self.charset_edit,
            self.sample_text_edit,
        ]
        for widget in watched:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.refresh_preview)
            else:
                widget.textChanged.connect(self.refresh_preview)

        spins = [
            self.point_size_spin,
            self.glyph_w_spin,
            self.glyph_h_spin,
            self.columns_spin,
            self.offset_x_spin,
            self.offset_y_spin,
            self.padding_spin,
            self.threshold_spin,
        ]
        for spin in spins:
            spin.valueChanged.connect(self.refresh_preview)

        self.antialias_check.toggled.connect(self.refresh_preview)

    def browse_font_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Font File",
            "",
            "Font Files (*.ttf *.otf)",
        )
        if path:
            self.font_path_edit.setText(path)

    def browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose Output Directory",
            self.output_dir_edit.text() or str(Path.cwd()),
        )
        if path:
            self.output_dir_edit.setText(path)

    def _normalized_charset(self) -> str:
        raw = self.charset_edit.toPlainText()
        chars: list[str] = []
        seen: set[str] = set()

        for ch in raw:
            if ch in ("\r",):
                continue
            if ch == "\n":
                continue
            if ch not in seen:
                seen.add(ch)
                chars.append(ch)

        return "".join(chars)

    def _load_font(self) -> Optional[ImageFont.FreeTypeFont]:
        font_path = self.font_path_edit.text().strip()
        if not font_path:
            return None

        path = Path(font_path)
        if not path.exists():
            return None

        try:
            return ImageFont.truetype(str(path), self.point_size_spin.value())
        except Exception:
            return None

    def _render_sheet(self) -> tuple[Optional[Image.Image], Optional[dict], str]:
        font = self._load_font()
        if font is None:
            return None, None, "フォントファイルを選んでください。"

        characters = self._normalized_charset()
        if not characters:
            return None, None, "文字セットが空です。"

        glyph_w = self.glyph_w_spin.value()
        glyph_h = self.glyph_h_spin.value()
        columns = self.columns_spin.value()
        offset_x = self.offset_x_spin.value()
        offset_y = self.offset_y_spin.value()
        padding = self.padding_spin.value()
        threshold = self.threshold_spin.value()
        antialias = self.antialias_check.isChecked()

        count = len(characters)
        rows = math.ceil(count / columns)

        sheet_w = columns * glyph_w
        sheet_h = rows * glyph_h

        sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

        for i, ch in enumerate(characters):
            col = i % columns
            row = i // columns
            x = col * glyph_w
            y = row * glyph_h

            cell = self._render_glyph_cell(
                font=font,
                ch=ch,
                glyph_w=glyph_w,
                glyph_h=glyph_h,
                offset_x=offset_x,
                offset_y=offset_y,
                padding=padding,
                antialias=antialias,
                threshold=threshold,
            )
            sheet.alpha_composite(cell, (x, y))

        meta = {
            "image": f"{self.output_name_edit.text().strip() or 'bitmap_font'}.png",
            "glyph_width": glyph_w,
            "glyph_height": glyph_h,
            "columns": columns,
            "rows": rows,
            "characters": characters,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "padding": padding,
            "antialias": antialias,
            "threshold": threshold,
        }

        info = (
            f"{len(characters)} glyphs / "
            f"{columns} cols / {rows} rows / "
            f"{sheet_w}x{sheet_h}px"
        )
        return sheet, meta, info

    def _render_glyph_cell(
        self,
        font: ImageFont.FreeTypeFont,
        ch: str,
        glyph_w: int,
        glyph_h: int,
        offset_x: int,
        offset_y: int,
        padding: int,
        antialias: bool,
        threshold: int,
    ) -> Image.Image:
        scale = 4 if antialias else 1
        work_w = glyph_w * scale
        work_h = glyph_h * scale

        img = Image.new("L", (work_w, work_h), 0)
        draw = ImageDraw.Draw(img)

        # textbbox gives reliable placement for many fonts
        bbox = draw.textbbox((0, 0), ch, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        base_x = ((glyph_w - text_w) // 2) + offset_x + padding
        base_y = ((glyph_h - text_h) // 2) + offset_y + padding

        if antialias:
            draw.text(
                (base_x * scale - bbox[0] * scale, base_y * scale - bbox[1] * scale),
                ch,
                fill=255,
                font=font.font_variant(size=self.point_size_spin.value() * scale),
            )
            img = img.resize((glyph_w, glyph_h), Image.Resampling.LANCZOS)
        else:
            draw.text(
                (base_x - bbox[0], base_y - bbox[1]),
                ch,
                fill=255,
                font=font,
            )

        # Threshold to crisp white/transparent
        px = img.load()
        for y in range(glyph_h):
            for x in range(glyph_w):
                px[x, y] = 255 if px[x, y] >= threshold else 0

        rgba = Image.new("RGBA", (glyph_w, glyph_h), (0, 0, 0, 0))
        rgba_px = rgba.load()
        for y in range(glyph_h):
            for x in range(glyph_w):
                a = px[x, y]
                if a > 0:
                    rgba_px[x, y] = (255, 255, 255, 255)

        return rgba

    def refresh_preview(self) -> None:
        sheet, meta, info = self._render_sheet()
        if sheet is None or meta is None:
            self.preview_label.setText(info)
            self.info_label.setText(info)
            return

        self.info_label.setText(info)

        qimage = self._pil_to_qimage(sheet)
        pixmap = QPixmap.fromImage(qimage)

        shown = pixmap.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.FastTransformation,
        )
        self.preview_label.setPixmap(shown)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.refresh_preview()

    def generate_files(self) -> None:
        sheet, meta, info = self._render_sheet()
        if sheet is None or meta is None:
            QMessageBox.warning(self, "Generate Error", info)
            return

        output_dir = Path(self.output_dir_edit.text().strip() or ".")
        output_name = self.output_name_edit.text().strip() or "bitmap_font"

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Output Error", f"出力先を作成できません。\n{e}")
            return

        png_path = output_dir / f"{output_name}.png"
        json_path = output_dir / f"{output_name}.json"

        try:
            sheet.save(png_path)
            json_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            QMessageBox.critical(self, "Write Error", f"書き出しに失敗しました。\n{e}")
            return

        QMessageBox.information(
            self,
            "Done",
            f"生成しました。\n\nPNG: {png_path}\nJSON: {json_path}",
        )

    @staticmethod
    def _pil_to_qimage(img: Image.Image) -> QImage:
        rgba = img.convert("RGBA")
        data = rgba.tobytes("raw", "RGBA")
        return QImage(
            data,
            rgba.width,
            rgba.height,
            QImage.Format_RGBA8888,
        ).copy()


def main() -> None:
    app = QApplication(sys.argv)
    window = BitmapFontToolWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()