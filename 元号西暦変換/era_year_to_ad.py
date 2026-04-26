import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, timedelta

# =========================
# 元号データ（開始日）
# =========================
ERAS = [
    ("令和", date(2019, 5, 1)),
    ("平成", date(1989, 1, 8)),
    ("昭和", date(1926, 12, 25)),
    ("大正", date(1912, 7, 30)),
    ("明治", date(1868, 1, 25)),
]
ERAS_DESC = ERAS[:]                 # 新しい順
ERAS_ASC = list(reversed(ERAS_DESC))  # 古い順


# =========================
# 日付ユーティリティ
# =========================
def today_local() -> date:
    # 依存なし：OSのローカル日付（日本なら実質JST）
    return date.today()


def is_leap(y: int) -> bool:
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def last_day_of_month(y: int, m: int) -> int:
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def validate_ymd(y: int, m: int, d: int) -> date:
    if not (1 <= m <= 12):
        raise ValueError("月は1〜12で入力してください")
    ld = last_day_of_month(y, m)
    if not (1 <= d <= ld):
        raise ValueError(f"日は1〜{ld}で入力してください")
    return date(y, m, d)


def ymd_diff(start: date, end: date):
    """
    カレンダー差分：start→end の (years, months, days, sign)
    end >= start の場合 sign=1、それ以外 sign=-1 で絶対値差分を返す
    """
    sign = 1
    if end < start:
        start, end = end, start
        sign = -1

    y = end.year - start.year
    m = end.month - start.month
    d = end.day - start.day

    if d < 0:
        prev_month = end.month - 1
        prev_year = end.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        d += last_day_of_month(prev_year, prev_month)
        m -= 1

    if m < 0:
        m += 12
        y -= 1

    return y, m, d, sign


def format_elapsed(start: date, end: date) -> str:
    total_days = (end - start).days
    y, m, d, sign = ymd_diff(start, end)
    if sign < 0:
        return f"あと {y}年{m}ヶ月{d}日（合計{abs(total_days):,}日）"
    return f"{y}年{m}ヶ月{d}日（合計{total_days:,}日）"


# =========================
# 1欄入力パース
# =========================
def parse_flexible_ymd(s: str):
    """
    西暦入力:
      YYYY / YYYY-MM / YYYY-MM-DD
      YYYY/MM/DD もOK
    戻り: (precision, y, m, d)  ※Y/YMは1日補完
    """
    t = s.strip().replace("/", "-")
    if not t:
        raise ValueError("入力してください")

    parts = t.split("-")
    if len(parts) == 1:
        y = int(parts[0])
        return ("Y", y, 1, 1)
    if len(parts) == 2:
        y = int(parts[0])
        m = int(parts[1])
        return ("YM", y, m, 1)
    if len(parts) == 3:
        y = int(parts[0])
        m = int(parts[1])
        d = int(parts[2])
        validate_ymd(y, m, d)
        return ("YMD", y, m, d)

    raise ValueError("形式が不正です（例：2024 / 2024-06 / 2024-06-15）")


def parse_era_flexible_ymd(s: str):
    """
    元号入力:
      6 / 元 / 6-4 / 6-4-1 （/もOK）
    戻り: (precision, year_in_era, m, d) ※Y/YMは1日補完
    """
    t = s.strip().replace("/", "-")
    if not t:
        raise ValueError("入力してください")

    parts = t.split("-")
    if len(parts) == 1:
        y_str = parts[0]
        y = 1 if y_str == "元" else int(y_str)
        if y <= 0:
            raise ValueError("年は1以上で入力してください（元年=1）")
        return ("Y", y, 1, 1)

    if len(parts) == 2:
        y_str, m_str = parts
        y = 1 if y_str == "元" else int(y_str)
        m = int(m_str)
        if y <= 0:
            raise ValueError("年は1以上で入力してください（元年=1）")
        if not (1 <= m <= 12):
            raise ValueError("月は1〜12で入力してください")
        return ("YM", y, m, 1)

    if len(parts) == 3:
        y_str, m_str, d_str = parts
        y = 1 if y_str == "元" else int(y_str)
        m = int(m_str)
        d = int(d_str)
        if y <= 0:
            raise ValueError("年は1以上で入力してください（元年=1）")
        validate_ymd(2000, m, d)  # 年は後で確定するので月日だけ先チェック
        return ("YMD", y, m, d)

    raise ValueError("形式が不正です（例：6 / 元 / 6-4 / 6-4-1）")


# =========================
# 変換
# =========================
def ad_date_to_era_parts(d: date):
    """
    西暦date → (era_name, year_in_era, month, day)
    """
    if d < ERAS_ASC[0][1]:
        raise ValueError("1868年（明治）より前は未対応です")

    for era, start in ERAS_DESC:
        if d >= start:
            year_in_era = d.year - start.year + 1
            return era, year_in_era, d.month, d.day
    raise ValueError("変換できませんでした")


def format_era_year(era: str, y_in_era: int) -> str:
    y_disp = "元" if y_in_era == 1 else str(y_in_era)
    return f"{era}{y_disp}年"


def format_era_date(era: str, y_in_era: int, m: int, d: int) -> str:
    # 指定どおり：昭和yy年mm月dd日（mm/ddは0埋め）
    y_disp = "元" if y_in_era == 1 else f"{y_in_era:02d}"
    return f"{era}{y_disp}年{m:02d}月{d:02d}日"


def ad_year_to_era_years_with_boundary(ad_year: int) -> str:
    """
    西暦「年だけ」→ 同年に存在する元号を全部表示（境界がある年は2つ）
    """
    if ad_year < 1868:
        raise ValueError("1868年（明治）より前は未対応です")

    year_start = date(ad_year, 1, 1)
    year_end = date(ad_year, 12, 31)

    spans = []
    for i, (era, start) in enumerate(ERAS_DESC):
        if i == 0:
            end = date.max
        else:
            _, newer_start = ERAS_DESC[i - 1]
            end = newer_start - timedelta(days=1)

        overlap_start = max(year_start, start)
        overlap_end = min(year_end, end)
        if overlap_start <= overlap_end:
            y_in_era = ad_year - start.year + 1
            name = format_era_year(era, y_in_era)

            if overlap_start == year_start and overlap_end == year_end:
                note = ""
            elif overlap_start == year_start:
                note = f"（〜{overlap_end.month}/{overlap_end.day}）"
            elif overlap_end == year_end:
                note = f"（{overlap_start.month}/{overlap_start.day}〜）"
            else:
                note = f"（{overlap_start.month}/{overlap_start.day}〜{overlap_end.month}/{overlap_end.day}）"

            spans.append(f"{name}{note}")

    if not spans:
        raise ValueError("変換できませんでした")

    return " / ".join(spans)


def era_input_to_ad_date(era: str, precision: str, y_in_era: int, m: int, d: int) -> date:
    start = None
    idx = None
    for i, (name, s) in enumerate(ERAS_DESC):
        if name == era:
            start = s
            idx = i
            break
    if start is None:
        raise ValueError("元号が未選択です")

    ad_year = start.year + (y_in_era - 1)

    if precision == "Y":
        m, d = 1, 1
    elif precision == "YM":
        d = 1

    dd = validate_ymd(ad_year, m, d)

    if idx == 0:
        end = date.max
    else:
        _, newer_start = ERAS_DESC[idx - 1]
        end = newer_start - timedelta(days=1)

    if not (start <= dd <= end):
        raise ValueError(f"{era}の期間外の日付です（改元境界をまたいでいる可能性）")

    return dd


# =========================
# クリップボード
# =========================
def copy_to_clipboard(widget, text: str):
    widget.clipboard_clear()
    widget.clipboard_append(text)
    widget.update()


# =========================
# 出力組み立て
# =========================
def build_output(mode: str, raw: str):
    """
    戻り:
      display_text: 結果欄に出す文字（経過など含む）
      copy_text:    クリップボードに入れる文字（変換結果だけ）
    """
    today = today_local()
    today_str = f"{today.year:04d}-{today.month:02d}-{today.day:02d}"

    lines = [f"今日：{today_str}"]

    if mode == "西暦":
        precision, y, m, d = parse_flexible_ymd(raw)
        input_date = validate_ymd(y, m, d)

        if precision == "Y":
            # 年だけ：2元号年は両方表示
            era_years = ad_year_to_era_years_with_boundary(y)
            lines.append(f"元号：{era_years}")

            start_date = date(y, 1, 1)
            lines.append(f"経過：{format_elapsed(start_date, today)}（{y}-01-01→{today_str}）")
            lines.append("※ 年だけ入力は 1/1 扱い")

            copy_text = era_years  # 年だけは年表示をコピー
            return "\n".join(lines), copy_text

        # 年月/年月日：日が未入力なら1日扱い
        era, y_in_era, mm, dd = ad_date_to_era_parts(input_date)
        if precision == "YM":
            era_text = format_era_date(era, y_in_era, mm, dd) + "（※日=1扱い）"
        else:
            era_text = format_era_date(era, y_in_era, mm, dd)

        lines.append(f"元号：{era_text}")
        lines.append(f"経過：{format_elapsed(input_date, today)}（{input_date.isoformat()}→{today_str}）")

        # コピーは元号を指定形式で（注釈なし）
        copy_text = format_era_date(era, y_in_era, mm, dd)
        return "\n".join(lines), copy_text

    # 元号 → 西暦
    precision, y_in_era, m, d = parse_era_flexible_ymd(raw)
    ad_d = era_input_to_ad_date(mode, precision, y_in_era, m, d)

    # 表示（西暦は状況に応じて見やすく）
    if precision == "Y":
        lines.append(f"西暦：{ad_d.year}")
        # この年が境界年なら注釈
        era_years = ad_year_to_era_years_with_boundary(ad_d.year)
        if " / " in era_years:
            lines.append(f"※ {ad_d.year}年は：{era_years}")

        start_date = date(ad_d.year, 1, 1)
        lines.append(f"経過：{format_elapsed(start_date, today)}（{ad_d.year}-01-01→{today_str}）")
        lines.append("※ 年だけ入力は 1/1 扱い")
    elif precision == "YM":
        lines.append(f"西暦：{ad_d.year}-{ad_d.month:02d}（※日=1扱い）")
        lines.append(f"経過：{format_elapsed(ad_d, today)}（{ad_d.isoformat()}→{today_str}）")
    else:
        lines.append(f"西暦：{ad_d.isoformat()}")
        lines.append(f"経過：{format_elapsed(ad_d, today)}（{ad_d.isoformat()}→{today_str}）")

    # コピー仕様：西暦は「年の数字のみ」
    copy_text = str(ad_d.year)
    return "\n".join(lines), copy_text


# =========================
# UIイベント（Enterだけ）
# =========================
def on_mode_change(event=None):
    mode = mode_var.get()
    if mode == "西暦":
        hint_var.set("（例：2024 / 2024-06 / 2024-06-15）")
    else:
        hint_var.set("（例：6 / 元 / 6-4 / 6-4-1）")
    entry.focus_set()


def on_convert(event=None):
    try:
        mode = mode_var.get()
        raw = entry.get().strip()
        if not raw:
            raise ValueError("入力してください")

        display_text, copy_text = build_output(mode, raw)
        result_var.set(display_text)
        copy_to_clipboard(root, copy_text)

        entry.delete(0, tk.END)
        entry.focus_set()

    except Exception as e:
        messagebox.showerror("変換エラー", str(e))


# =========================
# UI構築
# =========================
root = tk.Tk()
root.title("元号 ⇄ 西暦（年/年月日）＋経過（年月日/合計日数）")
root.geometry("660x320")

frm = ttk.Frame(root, padding=12)
frm.pack(fill="both", expand=True)

row1 = ttk.Frame(frm)
row1.pack(fill="x", pady=(0, 10))

ttk.Label(row1, text="モード").pack(side="left")

mode_var = tk.StringVar(value="令和")
mode_combo = ttk.Combobox(
    row1,
    textvariable=mode_var,
    values=["西暦"] + [e for e, _ in ERAS_DESC],
    state="readonly",
    width=10
)
mode_combo.pack(side="left", padx=(8, 16))
mode_combo.bind("<<ComboboxSelected>>", on_mode_change)

ttk.Label(row1, text="入力").pack(side="left")

entry = ttk.Entry(row1, width=24)
entry.pack(side="left", padx=(8, 0))

hint_var = tk.StringVar(value="")
ttk.Label(row1, textvariable=hint_var).pack(side="left", padx=(10, 0))

# Enterで変換＋コピー＋クリア
entry.bind("<Return>", on_convert)

ttk.Label(frm, text="結果（Enterで変換→自動コピー→入力欄クリア）").pack(anchor="w")

result_var = tk.StringVar(value="")

result_box = tk.Text(frm, height=8, wrap="word")
result_box.pack(fill="both", expand=True, pady=(6, 0))

def sync_result_box(*args):
    result_box.config(state="normal")
    result_box.delete("1.0", tk.END)
    result_box.insert(tk.END, result_var.get())
    result_box.config(state="disabled")

result_var.trace_add("write", sync_result_box)

# クリックで全選択（見やすさ）
def select_all_text(event):
    result_box.tag_add("sel", "1.0", "end-1c")
    return "break"

result_box.bind("<Button-1>", select_all_text)

on_mode_change()
entry.focus_set()
root.mainloop()