import sys
import os
import csv
import shutil
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QFormLayout, QTextEdit,
    QMessageBox, QFileDialog,
    QComboBox, QMenuBar, QDialog, QCheckBox, QDialogButtonBox, QGroupBox,
    QTabWidget, QSplitter
)

from db import (
    init_db, upsert_employee, insert_employee_with_id, change_employee_id,
    list_employees, get_employee, delete_employee
)
from pdf_simple import build_simple_pdf


# ========= バージョン情報（確定） =========
APP_NAME = "労働者名簿"
APP_VERSION = "1.4.0"
COMPANY_NAME = "辰巳旅館株式会社内製"
RELEASE_DATE = "2026.02.22"

# ========= 初期DBとフォント =========
DEFAULT_DB_PATH = "roster.db"
FONT_PATH = "fonts/BIZ-UDGOTHICB.TTC"

FIELDS = [
    ("name", "氏名*", "text"),
    ("name_kana", "ふりがな", "text"),
    ("sex", "性別", "combo"),

    ("birth_date", "生年月日", "text"),   # 例: 1980-01-31
    ("address", "住所", "text"),
    ("phone", "電話番号", "text"),

    ("job_type", "従事する業務の種類", "text"),
    ("hire_date", "雇入れ年月日", "text"),  # 例: 2026-01-28
    ("hire_story", "雇入れの経緯", "memo"),

    ("history", "履歴", "memo"),
    ("license", "免許資格", "memo"),

    ("my_number", "個人番号", "text"),
    ("health_ins", "健康保険番号", "text"),
    ("pension_base", "基礎年金番号", "text"),
    ("welfare_pension", "厚生年金番号", "text"),
    ("employment_ins", "雇用保険番号", "text"),

    ("leave_date", "退職日", "text"),       # 例: 2026-12-31
    ("leave_reason", "退職の事由", "memo"),
    ("remarks", "備考", "memo"),
]


# タブ分割：個人番号から2ページ目
TAB1_KEYS = [
    "name", "name_kana", "sex",
    "birth_date", "address", "phone",
    "job_type", "hire_date", "hire_story",
    "history", "license",
]
TAB2_KEYS = [
    "my_number",
    "health_ins", "pension_base", "welfare_pension", "employment_ins",
    "leave_date", "leave_reason", "remarks",
]


def resource_path(rel_path: str) -> str:
    """PyInstaller(onefile)でも通常実行でも動くように、リソース実体パスを解決"""
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)


def abs_path(p: str) -> str:
    return os.path.abspath(p) if p else p


def db_filename(p: str) -> str:
    return os.path.basename(p) if p else ""


class ColumnSelectDialog(QDialog):
    """
    CSV出力の列選択ダイアログ
    - 初期はIDと氏名のみチェック
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CSV出力：列を選択")
        self.resize(520, 520)

        layout = QVBoxLayout(self)

        gb = QGroupBox("出力する列（初期：ID と 氏名）")
        gb_layout = QVBoxLayout(gb)

        self.checks = []

        # id
        self.chk_id = QCheckBox("ID")
        self.chk_id.setChecked(True)
        gb_layout.addWidget(self.chk_id)
        self.checks.append(("id", "ID", self.chk_id))

        # fields
        for key, label, _ in FIELDS:
            chk = QCheckBox(label)
            chk.setChecked(key == "name")  # 氏名だけ初期ON
            gb_layout.addWidget(chk)
            self.checks.append((key, label, chk))

        layout.addWidget(gb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        cols = self.selected_columns()
        if not cols:
            QMessageBox.warning(self, "未選択", "最低1つは列を選択してください")
            return
        self.accept()

    def selected_columns(self) -> list[str]:
        return [key for key, _, chk in self.checks if chk.isChecked()]

    def selected_headers(self) -> list[str]:
        return [label for _, label, chk in self.checks if chk.isChecked()]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1160, 740)

        # 現在開いているDB（動的切替）
        self.db_path = abs_path(DEFAULT_DB_PATH)
        init_db(self.db_path)

        self.current_id = None
        self.widgets = {}

        # ステータスバー
        self.statusBar()

        # メニューバー
        self._build_menu()

        # ===== 中央UI（左右スプリッター）=====
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        # 左：一覧エリア
        leftw = QWidget()
        left = QVBoxLayout(leftw)

        self.search = QLineEdit()
        self.search.setPlaceholderText("検索（ID・氏名・電話番号）")

        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "ID 古い順",
            "ID 新しい順",
            "業務種類 昇順",
            "業務種類 降順",
        ])
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.currentIndexChanged.connect(self.reload_list)

        btn_search = QPushButton("検索")
        btn_search.clicked.connect(self.reload_list)

        sr = QHBoxLayout()
        sr.addWidget(self.search)
        sr.addWidget(btn_search)

        left.addLayout(sr)
        left.addWidget(self.sort_combo)

        self.listw = QListWidget()
        self.listw.itemSelectionChanged.connect(self.on_select)
        left.addWidget(self.listw)

        # 右：フォームエリア
        rightw = QWidget()
        right = QVBoxLayout(rightw)

        # レコード操作ボタン（そのまま）
        btns = QHBoxLayout()
        btn_new = QPushButton("新規")
        btn_save = QPushButton("保存")
        btn_del = QPushButton("削除")
        btn_new.clicked.connect(self.new_record)
        btn_save.clicked.connect(self.save_record)
        btn_del.clicked.connect(self.delete_record)

        btns.addWidget(btn_new)
        btns.addWidget(btn_save)
        btns.addWidget(btn_del)
        btns.addStretch(1)
        right.addLayout(btns)

        # ID編集欄
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("空欄なら自動採番（例: 1, 2, 3 ...）")

        self.lbl_current = QLabel("現在のID: （新規）")
        self.lbl_current.setStyleSheet("font-weight:bold;")
        right.addWidget(self.lbl_current)

        # タブ（2ページ）
        self.tabs = QTabWidget()
        tab1 = QWidget()
        tab2 = QWidget()
        self.tabs.addTab(tab1, "基本情報")
        self.tabs.addTab(tab2, "労務情報")

        # タブ1フォーム
        form1 = QFormLayout(tab1)
        form1.setLabelAlignment(Qt.AlignRight)
        form1.addRow("ID（編集可）", self.id_edit)

        # タブ2フォーム
        form2 = QFormLayout(tab2)
        form2.setLabelAlignment(Qt.AlignRight)

        # 入力欄生成（widgetsは共通で保持）
        for key, label, typ in FIELDS:
            if typ == "text":
                w = QLineEdit()
                if key in ("birth_date", "hire_date", "leave_date"):
                    w.setPlaceholderText("YYYY-MM-DD（未入力OK）")
            elif typ == "memo":
                w = QTextEdit()
                w.setFixedHeight(70)
            elif typ == "combo":
                w = QComboBox()
                w.addItems(["未記入", "男", "女", "その他"])
            else:
                raise ValueError(f"unknown field type: {typ}")

            self.widgets[key] = w

            # タブ振り分け
            if key in TAB1_KEYS:
                form1.addRow(label, w)
            else:
                form2.addRow(label, w)

        right.addWidget(self.tabs)

        # splitterへ追加
        splitter.addWidget(leftw)
        splitter.addWidget(rightw)

        # 最小幅（崩れ防止）
        leftw.setMinimumWidth(260)
        rightw.setMinimumWidth(600)

        # 初期比率（左:右 ≒ 35:65）
        splitter.setSizes([380, 780])

        self.setCentralWidget(splitter)

        # タイトルバー＆ステータスバー更新
        self.update_db_status()

        # 初期表示
        self.reload_list()
        self.new_record()

    # ===== タイトル/ステータス表示 =====
    def update_db_status(self):
        # タイトルバー：DBファイル名
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}  |  データ: {db_filename(self.db_path)}")
        # ステータスバー：フルパス
        self.statusBar().showMessage(f"データ: {self.db_path}")

    # ===== メニュー =====
    def _build_menu(self):
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        # ファイル
        menu_file = menubar.addMenu("ファイル")

        # 名簿データベース（DBファイル操作）
        menu_db = menu_file.addMenu("名簿データベース")

        act_db_new = QAction("新規…", self)
        act_db_new.triggered.connect(self.db_new)

        act_db_open = QAction("開く…", self)
        act_db_open.triggered.connect(self.db_open)

        act_db_backup = QAction("バックアップ作成…", self)
        act_db_backup.triggered.connect(self.db_backup)

        menu_db.addAction(act_db_new)
        menu_db.addAction(act_db_open)
        menu_db.addSeparator()
        menu_db.addAction(act_db_backup)

        menu_file.addSeparator()

        # 出力
        menu_pdf = menu_file.addMenu("PDF出力")
        act_pdf_submit = QAction("提出用（個人番号なし）", self)
        act_pdf_submit.triggered.connect(lambda: self.export_pdf(submit_mode=True))
        act_pdf_internal = QAction("社内用（個人番号あり）", self)
        act_pdf_internal.triggered.connect(lambda: self.export_pdf(submit_mode=False))
        menu_pdf.addAction(act_pdf_submit)
        menu_pdf.addAction(act_pdf_internal)

        act_csv = QAction("一覧をCSV出力…", self)
        act_csv.triggered.connect(self.export_csv)
        menu_file.addAction(act_csv)

        menu_file.addSeparator()

        act_exit = QAction("終了", self)
        act_exit.setShortcut("Alt+F4")
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # ヘルプ
        menu_help = menubar.addMenu("ヘルプ")
        act_about = QAction("バージョン情報…", self)
        act_about.triggered.connect(self.show_about)
        menu_help.addAction(act_about)

    def show_about(self):
        text = (
            f"{APP_NAME}\n"
            f"Version {APP_VERSION}\n\n"
            f"{COMPANY_NAME}\n"
            f"{RELEASE_DATE}"
        )
        QMessageBox.information(self, "バージョン情報", text)

    # ===== DB操作 =====
    def _switch_db(self, new_path: str):
        new_path = abs_path(new_path)
        init_db(new_path)  # テーブル作成＋不足列追加
        self.db_path = new_path
        self.update_db_status()
        self.current_id = None
        self.reload_list()
        self.new_record()
        QMessageBox.information(self, "データ切り替え", f"データベースを切り替えました:\n{self.db_path}")

    def db_new(self):
        path, _ = QFileDialog.getSaveFileName(self, "新しい名簿データベースを作成", "roster_new.db", "DB Files (*.db)")
        if not path:
            return

        # 既存ファイルがあるなら確認して削除してから作る（init_dbが作る）
        if os.path.exists(path):
            if QMessageBox.question(self, "確認", "同名のファイルが存在します。上書きしますか？") != QMessageBox.Yes:
                return
            try:
                os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"既存ファイルを削除できません:\n{e}")
                return

        try:
            self._switch_db(path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"新規DB作成に失敗しました:\n{e}")

    def db_open(self):
        path, _ = QFileDialog.getOpenFileName(self, "名簿データベースを開く", "", "DB Files (*.db)")
        if not path:
            return
        try:
            self._switch_db(path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"DBを開けません:\n{e}")

    def db_backup(self):
        """現在DBを backup フォルダへコピー（切り替えない）"""
        try:
            base_dir = os.path.dirname(abs_path(self.db_path))
            backup_dir = os.path.join(base_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)

            stem = os.path.splitext(os.path.basename(self.db_path))[0] or "roster"
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            backup_path = os.path.join(backup_dir, f"{stem}_{ts}.db")

            shutil.copy2(self.db_path, backup_path)
            QMessageBox.information(self, "バックアップ完了", f"バックアップを作成しました:\n{backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "バックアップ失敗", str(e))

    # ===== ソート =====
    def _sort_spec(self) -> tuple[str, str]:
        idx = self.sort_combo.currentIndex()
        if idx == 0:
            return ("id", "ASC")
        if idx == 1:
            return ("id", "DESC")
        if idx == 2:
            return ("job_type", "ASC")
        if idx == 3:
            return ("job_type", "DESC")
        return ("id", "ASC")

    # ===== 一覧 =====
    def reload_list(self):
        """
        保存後に別人へズレる対策：
        - 再描画中に selectionChanged が暴れるのを blockSignals で抑止
        - 再描画後に current_id を再選択
        """
        keep_id = self.current_id
        q = self.search.text().strip()
        sort_key, sort_dir = self._sort_spec()

        self.listw.blockSignals(True)
        try:
            self.listw.clear()

            rows = list_employees(
                self.db_path,
                q=q,
                sort_key=sort_key,
                sort_dir=sort_dir,
                columns=["id", "name"],  # 一覧はID+氏名だけ
            )

            target_item = None
            for r in rows:
                emp_id = r["id"]
                name = r.get("name", "") or ""
                text = f'[{emp_id}] {name}'
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, emp_id)
                self.listw.addItem(item)

                if keep_id is not None and emp_id == keep_id:
                    target_item = item

            if target_item is not None:
                self.listw.setCurrentItem(target_item)
                self.listw.scrollToItem(target_item)
            else:
                self.listw.setCurrentRow(-1)

        finally:
            self.listw.blockSignals(False)

    def on_select(self):
        item = self.listw.currentItem()
        if not item:
            return
        self.load_record(int(item.data(Qt.UserRole)))

    # ===== 新規 =====
    def new_record(self):
        self.current_id = None
        self.lbl_current.setText("現在のID: （新規）")
        self.id_edit.setText("")
        self.tabs.setCurrentIndex(0)  # 基本情報タブに戻す

        for key, _, typ in FIELDS:
            w = self.widgets[key]
            if typ == "text":
                w.setText("")
            elif typ == "memo":
                w.setPlainText("")
            elif typ == "combo":
                w.setCurrentIndex(0)

    # ===== 読み込み =====
    def load_record(self, emp_id: int):
        emp = get_employee(self.db_path, emp_id)
        if not emp:
            return

        self.current_id = emp_id
        self.lbl_current.setText(f"現在のID: {emp_id}")
        self.id_edit.setText(str(emp_id))

        for key, _, typ in FIELDS:
            val = emp.get(key, "") or ""
            w = self.widgets[key]
            if typ == "text":
                w.setText(val)
            elif typ == "memo":
                w.setPlainText(val)
            elif typ == "combo":
                idx = w.findText(val)
                w.setCurrentIndex(idx if idx >= 0 else 0)

    # ===== 値取得 =====
    def _get(self, key: str) -> str:
        w = self.widgets[key]
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QComboBox):
            return w.currentText()
        return ""

    def _get_desired_id(self):
        s = (self.id_edit.text() or "").strip()
        if not s:
            return None
        try:
            v = int(s)
            if v <= 0:
                raise ValueError()
            return v
        except Exception:
            QMessageBox.warning(self, "IDエラー", "IDは正の整数で入力してください（空欄なら自動採番）")
            return "INVALID"

    # ===== 保存 =====
    def save_record(self):
        if not self._get("name"):
            QMessageBox.warning(self, "未入力", "氏名は必須です")
            return

        desired_id = self._get_desired_id()
        if desired_id == "INVALID":
            return

        payload = {key: self._get(key) for key, _, _ in FIELDS}

        try:
            # 新規
            if self.current_id is None:
                if desired_id is None:
                    new_id = upsert_employee(self.db_path, payload)
                else:
                    new_id = insert_employee_with_id(self.db_path, desired_id, payload)

            # 既存
            else:
                old_id = int(self.current_id)

                # まずID変更があるなら先に反映
                if desired_id is not None and desired_id != old_id:
                    change_employee_id(self.db_path, old_id, desired_id)
                    old_id = desired_id

                payload["id"] = old_id
                new_id = upsert_employee(self.db_path, payload)

        except Exception as e:
            QMessageBox.critical(self, "保存失敗", str(e))
            return

        self.current_id = int(new_id)
        self.lbl_current.setText(f"現在のID: {self.current_id}")
        self.id_edit.setText(str(self.current_id))

        self.reload_list()
        QMessageBox.information(self, "保存", "保存しました")

    # ===== 削除 =====
    def delete_record(self):
        if not self.current_id:
            return

        if QMessageBox.question(self, "確認", "削除しますか？") != QMessageBox.Yes:
            return

        delete_employee(self.db_path, int(self.current_id))
        self.reload_list()
        self.new_record()

    # ===== PDF =====
    def export_pdf(self, submit_mode: bool):
        if not self.current_id:
            QMessageBox.warning(self, "未選択", "保存後に出力してください")
            return

        emp = get_employee(self.db_path, int(self.current_id))
        if not emp:
            QMessageBox.warning(self, "エラー", "データが見つかりません")
            return

        font_path = resource_path(FONT_PATH)
        pdf_bytes = build_simple_pdf(emp, font_path, submit_mode=submit_mode)

        suffix = "submit" if submit_mode else "internal"
        default_name = f"worker_{suffix}_{self.current_id}.pdf"
        title = "PDF保存（提出用：個人番号なし）" if submit_mode else "PDF保存（社内用：個人番号あり）"

        path, _ = QFileDialog.getSaveFileName(self, title, default_name, "PDF Files (*.pdf)")
        if not path:
            return

        with open(path, "wb") as f:
            f.write(pdf_bytes)

        QMessageBox.information(self, "完了", f"PDFを書き出しました:\n{path}")

    # ===== CSV =====
    def export_csv(self):
        dlg = ColumnSelectDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        cols = dlg.selected_columns()
        headers = dlg.selected_headers()

        q = self.search.text().strip()
        sort_key, sort_dir = self._sort_spec()

        rows = list_employees(
            self.db_path,
            q=q,
            sort_key=sort_key,
            sort_dir=sort_dir,
            columns=cols
        )

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        default_name = f"employees_{ts}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "CSV保存", default_name, "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in rows:
                    w.writerow([r.get(c, "") or "" for c in cols])
        except Exception as e:
            QMessageBox.critical(self, "CSV出力失敗", str(e))
            return

        QMessageBox.information(self, "完了", f"CSVを書き出しました:\n{path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())