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
    QComboBox,
    QFileDialog,
    QFormLayout,
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


DEFAULT_MANUAL_CHARSET = """ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789
!?:;.,+-*/()[]<>{}=_~"'
アイウエオカキクケコサシスセソ
タチツテトナニヌネノハヒフヘホ
マミムメモヤユヨラリルレロワヲンー
ぁぃぅぇぉゃゅょっ
あいうえおかきくけこさしすせそ
たちつてとなにぬねのはひふへほ
まみむめもやゆよらりるれろわをん
がぎぐげござじずぜぞだぢづでど
ばびぶべぼぱぴぷぺぽ
、。！？「」ー・
"""


def build_basic_latin() -> str:
    chars = []
    for code in range(0x20, 0x7F):
        chars.append(chr(code))
    return "".join(chars)


def build_hiragana() -> str:
    chars = []
    for code in range(0x3041, 0x3097):
        chars.append(chr(code))
    chars.extend(["゛", "゜", "ー", "、", "。", "「", "」", "・"])
    return "".join(chars)


def build_katakana() -> str:
    chars = []
    for code in range(0x30A1, 0x30FB):
        chars.append(chr(code))
    chars.extend(["ー", "、", "。", "「", "」", "・"])
    return "".join(chars)


def build_jis_level_1_like() -> str:
    # CP932 first-byte/second-byte sweep approximates JIS first level coverage
    chars = []
    seen = set()
    for b1 in range(0x81, 0x9F + 1):
        for b2 in list(range(0x40, 0x7E + 1)) + list(range(0x80, 0xFC + 1)):
            if b2 == 0x7F:
                continue
            try:
                ch = bytes([b1, b2]).decode("cp932")
            except Exception:
                continue
            if len(ch) != 1:
                continue
            if ch not in seen:
                seen.add(ch)
                chars.append(ch)
    return "".join(chars)


def build_jis_level_2_like() -> str:
    chars = []
    seen = set()
    for b1 in range(0xE0, 0xEA + 1):
        for b2 in list(range(0x40, 0x7E + 1)) + list(range(0x80, 0xFC + 1)):
            if b2 == 0x7F:
                continue
            try:
                ch = bytes([b1, b2]).decode("cp932")
            except Exception:
                continue
            if len(ch) != 1:
                continue
            if ch not in seen:
                seen.add(ch)
                chars.append(ch)
    return "".join(chars)


def dedupe_chars(text: str) -> str:
    chars: list[str] = []
    seen: set[str] = set()
    for ch in text:
        if ch in ("\r", "\n"):
            continue
        if ch not in seen:
            seen.add(ch)
            chars.append(ch)
    return "".join(chars)


PRESET_BUILDERS = {
    "Basic Latin": build_basic_latin,
    "Hiragana": build_hiragana,
    "Katakana": build_katakana,
    "Kana + Latin": lambda: dedupe_chars(build_basic_latin() + build_hiragana() + build_katakana()),
    "JIS Level 1": lambda: dedupe_chars(build_basic_latin() + build_hiragana() + build_katakana() + build_jis_level_1_like()),
    "JIS Level 1 + 2": lambda: dedupe_chars(
        build_basic_latin() + build_hiragana() + build_katakana() + build_jis_level_1_like() + build_jis_level_2_like()
    ),
}


class BitmapFontToolV2(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ビットマップフォントツール V2")
        self.resize(1320, 820)

        self.font_path_edit = QLineEdit()
        self.output_dir_edit = QLineEdit(str(Path.cwd()))
        self.output_name_edit = QLineEdit("bitmap_font_jis")

        self.charset_source_combo = QComboBox()
        self.charset_source_combo.addItems(["手入力", "プリセット", "テキストファイル"])

        self.charset_preset_combo = QComboBox()
        self.charset_preset_combo.addItems(list(PRESET_BUILDERS.keys()))

        self.charset_file_edit = QLineEdit()
        self.charset_file_edit.setPlaceholderText("テキストファイルのパス")

        self.point_size_spin = QSpinBox()
        self.point_size_spin.setRange(4, 256)
        self.point_size_spin.setValue(16)

        self.glyph_w_spin = QSpinBox()
        self.glyph_w_spin.setRange(4, 256)
        self.glyph_w_spin.setValue(16)

        self.glyph_h_spin = QSpinBox()
        self.glyph_h_spin.setRange(4, 256)
        self.glyph_h_spin.setValue(16)

        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 256)
        self.columns_spin.setValue(32)

        self.rows_per_page_spin = QSpinBox()
        self.rows_per_page_spin.setRange(1, 256)
        self.rows_per_page_spin.setValue(32)

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

        self.antialias_check = QCheckBox("アンチエイリアス")
        self.antialias_check.setChecked(False)

        self.skip_missing_check = QCheckBox("欠損グリフをスキップ")
        self.skip_missing_check.setChecked(False)

        self.charset_edit = QPlainTextEdit()
        self.charset_edit.setPlainText(DEFAULT_MANUAL_CHARSET)

        self.preview_label = QLabel("プレビュー")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(480, 480)
        self.preview_label.setStyleSheet("background:#202020; border:1px solid #555;")

        self.info_label = QLabel("")
        self.sample_text_edit = QPlainTextEdit()
        self.sample_text_edit.setPlainText(
            "辰巳旅館\n"
            "浅虫温泉へようこそ\n"
            "HP 120/120\n"
            "宿\n"
            "露天風呂"
        )
        self.sample_text_edit.setMaximumHeight(120)

        self._build_ui()
        self._connect_signals()
        self._update_charset_source_ui()
        self.refresh_preview()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        file_box = QGroupBox("ファイル")
        file_form = QFormLayout(file_box)

        browse_font_btn = QPushButton("参照...")
        browse_out_btn = QPushButton("参照...")
        browse_charset_btn = QPushButton("参照...")

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

        charset_file_row = QWidget()
        charset_file_row_layout = QHBoxLayout(charset_file_row)
        charset_file_row_layout.setContentsMargins(0, 0, 0, 0)
        charset_file_row_layout.addWidget(self.charset_file_edit)
        charset_file_row_layout.addWidget(browse_charset_btn)

        file_form.addRow("フォントファイル", font_row)
        file_form.addRow("出力先フォルダ", out_row)
        file_form.addRow("出力名", self.output_name_edit)
        file_form.addRow("文字セット取得元", self.charset_source_combo)
        file_form.addRow("プリセット", self.charset_preset_combo)
        file_form.addRow("文字セットファイル", charset_file_row)

        settings_box = QGroupBox("設定")
        settings_form = QFormLayout(settings_box)
        settings_form.addRow("文字サイズ", self.point_size_spin)
        settings_form.addRow("グリフ幅", self.glyph_w_spin)
        settings_form.addRow("グリフ高さ", self.glyph_h_spin)
        settings_form.addRow("列数", self.columns_spin)
        settings_form.addRow("1ページの行数", self.rows_per_page_spin)
        settings_form.addRow("Xオフセット", self.offset_x_spin)
        settings_form.addRow("Yオフセット", self.offset_y_spin)
        settings_form.addRow("余白", self.padding_spin)
        settings_form.addRow("しきい値", self.threshold_spin)
        settings_form.addRow("", self.antialias_check)
        settings_form.addRow("", self.skip_missing_check)

        charset_box = QGroupBox("手入力文字")
        charset_layout = QVBoxLayout(charset_box)
        charset_layout.addWidget(self.charset_edit)

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_btn = QPushButton("プレビュー更新")
        self.generate_btn = QPushButton("PNG + JSON を生成")
        actions_layout.addWidget(self.preview_btn)
        actions_layout.addWidget(self.generate_btn)

        left_layout.addWidget(file_box)
        left_layout.addWidget(settings_box)
        left_layout.addWidget(charset_box)
        left_layout.addWidget(actions_row)
        left_layout.addWidget(self.info_label)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        preview_box = QGroupBox("1ページ目プレビュー")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.preview_label)

        sample_box = QGroupBox("サンプル文字列")
        sample_layout = QVBoxLayout(sample_box)
        sample_layout.addWidget(self.sample_text_edit)

        right_layout.addWidget(preview_box)
        right_layout.addWidget(sample_box)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([560, 700])

        browse_font_btn.clicked.connect(self.browse_font_file)
        browse_out_btn.clicked.connect(self.browse_output_dir)
        browse_charset_btn.clicked.connect(self.browse_charset_file)

    def _connect_signals(self) -> None:
        self.preview_btn.clicked.connect(self.refresh_preview)
        self.generate_btn.clicked.connect(self.generate_files)

        self.charset_source_combo.currentTextChanged.connect(self._update_charset_source_ui)

        for widget in [
            self.font_path_edit,
            self.output_name_edit,
            self.charset_file_edit,
        ]:
            widget.textChanged.connect(self.refresh_preview)

        for widget in [self.charset_edit, self.sample_text_edit]:
            widget.textChanged.connect(self.refresh_preview)

        for combo in [self.charset_preset_combo]:
            combo.currentTextChanged.connect(self.refresh_preview)

        for spin in [
            self.point_size_spin,
            self.glyph_w_spin,
            self.glyph_h_spin,
            self.columns_spin,
            self.rows_per_page_spin,
            self.offset_x_spin,
            self.offset_y_spin,
            self.padding_spin,
            self.threshold_spin,
        ]:
            spin.valueChanged.connect(self.refresh_preview)

        self.antialias_check.toggled.connect(self.refresh_preview)
        self.skip_missing_check.toggled.connect(self.refresh_preview)

    def _update_charset_source_ui(self) -> None:
        source = self.charset_source_combo.currentText()
        self.charset_edit.setEnabled(source == "手入力")
        self.charset_preset_combo.setEnabled(source == "プリセット")
        self.charset_file_edit.setEnabled(source == "テキストファイル")
        self.refresh_preview()

    def browse_font_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "フォントファイルを選択", "", "Font Files (*.ttf *.otf)")
        if path:
            self.font_path_edit.setText(path)

    def browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "出力先フォルダを選択", self.output_dir_edit.text() or str(Path.cwd()))
        if path:
            self.output_dir_edit.setText(path)

    def browse_charset_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "文字セット用テキストを選択", "", "Text Files (*.txt);;All Files (*)")
        if path:
            self.charset_file_edit.setText(path)

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

    def _load_draw_font(self, size: int) -> Optional[ImageFont.FreeTypeFont]:
        font_path = self.font_path_edit.text().strip()
        if not font_path:
            return None
        path = Path(font_path)
        if not path.exists():
            return None
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            return None

    def _current_charset(self) -> tuple[str, str]:
        source = self.charset_source_combo.currentText()

        if source == "手入力":
            return dedupe_chars(self.charset_edit.toPlainText()), "manual"

        if source == "プリセット":
            preset_name = self.charset_preset_combo.currentText()
            chars = PRESET_BUILDERS[preset_name]()
            return dedupe_chars(chars), f"preset:{preset_name}"

        path = Path(self.charset_file_edit.text().strip())
        if not path.exists():
            return "", "file:not found"
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return "", "file:read error"
        return dedupe_chars(text), f"file:{path.name}"

    def _glyph_has_visible_pixels(self, img: Image.Image) -> bool:
        alpha = img.getchannel("A")
        bbox = alpha.getbbox()
        return bbox is not None

    def _render_glyph_cell(
        self,
        ch: str,
        glyph_w: int,
        glyph_h: int,
        offset_x: int,
        offset_y: int,
        padding: int,
        antialias: bool,
        threshold: int,
    ) -> tuple[Image.Image, bool]:
        scale = 4 if antialias else 1
        work_w = glyph_w * scale
        work_h = glyph_h * scale

        draw_font = self._load_draw_font(self.point_size_spin.value() * scale if antialias else self.point_size_spin.value())
        if draw_font is None:
            rgba = Image.new("RGBA", (glyph_w, glyph_h), (0, 0, 0, 0))
            return rgba, False

        img = Image.new("L", (work_w, work_h), 0)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), ch, font=draw_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        base_x = ((glyph_w - text_w // scale) // 2) + offset_x + padding
        base_y = ((glyph_h - text_h // scale) // 2) + offset_y + padding

        if antialias:
            draw.text(
                (base_x * scale - bbox[0], base_y * scale - bbox[1]),
                ch,
                fill=255,
                font=draw_font,
            )
            img = img.resize((glyph_w, glyph_h), Image.Resampling.LANCZOS)
        else:
            draw.text(
                (base_x - bbox[0], base_y - bbox[1]),
                ch,
                fill=255,
                font=draw_font,
            )

        px = img.load()
        for y in range(glyph_h):
            for x in range(glyph_w):
                px[x, y] = 255 if px[x, y] >= threshold else 0

        rgba = Image.new("RGBA", (glyph_w, glyph_h), (0, 0, 0, 0))
        rgba_px = rgba.load()
        visible = False
        for y in range(glyph_h):
            for x in range(glyph_w):
                a = px[x, y]
                if a > 0:
                    rgba_px[x, y] = (255, 255, 255, 255)
                    visible = True

        return rgba, visible

    def _render_pages(self) -> tuple[Optional[list[Image.Image]], Optional[dict], str]:
        if self._load_font() is None:
            return None, None, "フォントファイルを選んでください。"

        characters, source_desc = self._current_charset()
        if not characters:
            return None, None, "文字セットが空です。"

        glyph_w = self.glyph_w_spin.value()
        glyph_h = self.glyph_h_spin.value()
        columns = self.columns_spin.value()
        rows_per_page = self.rows_per_page_spin.value()
        offset_x = self.offset_x_spin.value()
        offset_y = self.offset_y_spin.value()
        padding = self.padding_spin.value()
        threshold = self.threshold_spin.value()
        antialias = self.antialias_check.isChecked()
        skip_missing = self.skip_missing_check.isChecked()

        page_capacity = columns * rows_per_page

        glyph_entries: list[tuple[str, Image.Image]] = []
        missing: list[str] = []

        for ch in characters:
            cell, visible = self._render_glyph_cell(
                ch=ch,
                glyph_w=glyph_w,
                glyph_h=glyph_h,
                offset_x=offset_x,
                offset_y=offset_y,
                padding=padding,
                antialias=antialias,
                threshold=threshold,
            )
            if not visible:
                missing.append(ch)
                if skip_missing:
                    continue
            glyph_entries.append((ch, cell))

        if not glyph_entries:
            return None, None, "有効なグリフが1つも生成できませんでした。"

        total_glyphs = len(glyph_entries)
        page_count = math.ceil(total_glyphs / page_capacity)
        pages: list[Image.Image] = []

        pages_meta: list[str] = []
        glyph_map: dict[str, dict] = {}

        for page_index in range(page_count):
            sheet_w = columns * glyph_w
            sheet_h = rows_per_page * glyph_h
            sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

            start = page_index * page_capacity
            end = min(start + page_capacity, total_glyphs)
            part = glyph_entries[start:end]

            for local_index, (ch, cell) in enumerate(part):
                col = local_index % columns
                row = local_index // columns
                x = col * glyph_w
                y = row * glyph_h
                sheet.alpha_composite(cell, (x, y))
                glyph_map[ch] = {
                    "page": page_index,
                    "col": col,
                    "row": row,
                    "x": x,
                    "y": y,
                }

            pages.append(sheet)
            pages_meta.append(f"{self.output_name_edit.text().strip() or 'bitmap_font'}_{page_index:02d}.png")

        meta = {
            "pages": pages_meta,
            "glyph_width": glyph_w,
            "glyph_height": glyph_h,
            "columns": columns,
            "rows_per_page": rows_per_page,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "padding": padding,
            "antialias": antialias,
            "threshold": threshold,
            "charset_source": source_desc,
            "glyph_count": total_glyphs,
            "missing_count": len(missing),
            "glyphs": glyph_map,
            "missing": missing,
        }

        info = (
            f"glyphs={total_glyphs} / missing={len(missing)} / "
            f"pages={page_count} / page={columns}x{rows_per_page}"
        )
        return pages, meta, info

    def refresh_preview(self) -> None:
        pages, meta, info = self._render_pages()
        if pages is None or meta is None:
            self.preview_label.setText(info)
            self.info_label.setText(info)
            return

        self.info_label.setText(info)

        first_page = pages[0]
        qimage = self._pil_to_qimage(first_page)
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
        pages, meta, info = self._render_pages()
        if pages is None or meta is None:
            QMessageBox.warning(self, "生成エラー", info)
            return

        output_dir = Path(self.output_dir_edit.text().strip() or ".")
        output_name = self.output_name_edit.text().strip() or "bitmap_font"

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "出力先エラー", f"出力先を作成できません。\n{e}")
            return

        json_path = output_dir / f"{output_name}.json"
        missing_txt_path = output_dir / f"{output_name}_missing.txt"

        try:
            for i, page in enumerate(pages):
                png_path = output_dir / f"{output_name}_{i:02d}.png"
                page.save(png_path)

            json_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            missing_txt_path.write_text(
                "".join(meta.get("missing", [])),
                encoding="utf-8",
            )
        except Exception as e:
            QMessageBox.critical(self, "書込エラー", f"書き出しに失敗しました。\n{e}")
            return

        QMessageBox.information(
            self,
            "完了",
            f"生成しました。\n\n"
            f"JSON: {json_path}\n"
            f"Pages: {len(pages)}\n"
            f"Missing: {meta.get('missing_count', 0)}",
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
    window = BitmapFontToolV2()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
