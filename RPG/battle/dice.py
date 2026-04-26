import tkinter as tk
from tkinter import ttk
import random
import json
import re
from collections import defaultdict

UNIT_FILE = "unit_presets.json"
TEST_FILE = "saved_tests.json"

dice_pattern = re.compile(r'(\d+)d(\d+)')

# -------------------------
# ダイス処理
# -------------------------

def roll_dice(expr: str) -> str:
    while True:
        m = dice_pattern.search(expr)
        if not m:
            break

        n = int(m.group(1))
        d = int(m.group(2))
        total = sum(random.randint(1, d) for _ in range(n))
        expr = expr[:m.start()] + str(total) + expr[m.end():]

    return expr


# -------------------------
# 能力値評価
# -------------------------

def evaluate_stats(raw_stats: dict) -> dict:
    stats = dict(raw_stats)

    # 数値文字列は先に int / float 化
    for k, v in list(stats.items()):
        if isinstance(v, (int, float)):
            continue
        s = str(v).strip()
        try:
            if "." in s:
                stats[k] = float(s)
            else:
                stats[k] = int(s)
        except:
            pass

    # 式を最大10回再評価（循環参照対策）
    for _ in range(10):
        changed = False

        for k, v in list(stats.items()):
            if isinstance(v, (int, float)):
                continue

            expr = str(v)
            expr = roll_dice(expr)

            for k2 in sorted(stats.keys(), key=len, reverse=True):
                if k2 == k:
                    continue
                expr = expr.replace(k2, str(stats[k2]))

            try:
                value = eval(expr)
                if stats[k] != value:
                    stats[k] = value
                    changed = True
            except:
                pass

        if not changed:
            break

    return stats


# -------------------------
# 式評価
# -------------------------

def eval_expr(expr: str, stats: dict):
    expr = roll_dice(expr)

    for k in sorted(stats.keys(), key=len, reverse=True):
        expr = expr.replace(k, str(stats[k]))

    try:
        return eval(expr)
    except:
        return 0


# -------------------------
# JSON保存
# -------------------------

def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf8") as f:
            return json.load(f)
    except:
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


units = load_json(UNIT_FILE, {})
saved_tests = load_json(TEST_FILE, [])

# -------------------------
# UI
# -------------------------

root = tk.Tk()
root.title("戦闘式テストツール")
root.geometry("1280x860")

main = ttk.Frame(root, padding=10)
main.pack(fill="x")

content = ttk.Frame(root, padding=10)
content.pack(fill="both", expand=True)

content.columnconfigure(0, weight=3)
content.columnconfigure(1, weight=2)
content.rowconfigure(0, weight=1)
content.rowconfigure(1, weight=1)

# -------------------------
# A/Bキャラ
# -------------------------

ttk.Label(main, text="Aキャラ").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)

unitA = tk.StringVar()
unitA_box = ttk.Combobox(main, textvariable=unitA, width=25, state="readonly")
unitA_box.grid(row=0, column=1, sticky="w")

ttk.Label(main, text="Bキャラ").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)

unitB = tk.StringVar()
unitB_box = ttk.Combobox(main, textvariable=unitB, width=25, state="readonly")
unitB_box.grid(row=1, column=1, sticky="w")


def refresh_units():
    names = sorted(units.keys())
    unitA_box["values"] = names
    unitB_box["values"] = names


refresh_units()

# -------------------------
# 式
# -------------------------

ttk.Label(main, text="式A").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)

exprA = tk.Entry(main, width=64)
exprA.grid(row=2, column=1, columnspan=4, sticky="w")

ttk.Label(main, text="式B").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)

exprB = tk.Entry(main, width=64)
exprB.grid(row=3, column=1, columnspan=4, sticky="w")

# -------------------------
# 試行回数
# -------------------------

ttk.Label(main, text="試行回数").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)

trials = tk.Entry(main, width=10)
trials.insert(0, "1000")
trials.grid(row=4, column=1, sticky="w")

# -------------------------
# 保存名
# -------------------------

ttk.Label(main, text="保存名").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)

save_name = tk.Entry(main, width=40)
save_name.grid(row=5, column=1, sticky="w", columnspan=2)

# -------------------------
# 操作
# -------------------------

def swap_units():
    a = unitA.get()
    b = unitB.get()
    unitA.set(b)
    unitB.set(a)
    update_unit_views()


def copy_A_to_B():
    exprB.delete(0, tk.END)
    exprB.insert(0, exprA.get())


def copy_B_to_A():
    exprA.delete(0, tk.END)
    exprA.insert(0, exprB.get())


def copy_both_formulas():
    text = f"式A: {exprA.get()}\n式B: {exprB.get()}"
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()


btn_frame = ttk.Frame(main)
btn_frame.grid(row=6, column=0, columnspan=5, sticky="w", pady=(8, 0))

ttk.Button(btn_frame, text="A⇄B", command=swap_units).grid(row=0, column=0, padx=4)
ttk.Button(btn_frame, text="A→B", command=copy_A_to_B).grid(row=0, column=1, padx=4)
ttk.Button(btn_frame, text="B→A", command=copy_B_to_A).grid(row=0, column=2, padx=4)
ttk.Button(btn_frame, text="式コピー", command=copy_both_formulas).grid(row=0, column=3, padx=4)

tool = ttk.Frame(main)
tool.grid(row=7, column=0, columnspan=5, sticky="w", pady=(10, 0))

# -------------------------
# 左上：結果 + 保存済みテスト
# -------------------------

left_top = ttk.Frame(content)
left_top.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
left_top.columnconfigure(0, weight=2)
left_top.columnconfigure(1, weight=1)
left_top.rowconfigure(0, weight=1)

# 結果
result_frame = ttk.LabelFrame(left_top, text="結果")
result_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
result_frame.rowconfigure(0, weight=1)
result_frame.columnconfigure(0, weight=1)

result_box = tk.Text(result_frame, bg="white", wrap="word")
result_box.grid(row=0, column=0, sticky="nsew")
result_box.tag_config("left", justify="left")

# 保存済みテスト
history_frame = ttk.LabelFrame(left_top, text="保存済みテスト")
history_frame.grid(row=0, column=1, sticky="nsew")
history_frame.rowconfigure(0, weight=1)
history_frame.columnconfigure(0, weight=1)

history_listbox = tk.Listbox(history_frame, bg="white")
history_listbox.grid(row=0, column=0, sticky="nsew")

history_scroll = ttk.Scrollbar(history_frame, orient="vertical", command=history_listbox.yview)
history_scroll.grid(row=0, column=1, sticky="ns")
history_listbox.config(yscrollcommand=history_scroll.set)

history_btns = ttk.Frame(history_frame)
history_btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

# -------------------------
# 右上：能力値表示
# -------------------------

unit_view_frame = ttk.LabelFrame(content, text="能力値")
unit_view_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
unit_view_frame.columnconfigure(0, weight=1)
unit_view_frame.columnconfigure(1, weight=1)
unit_view_frame.rowconfigure(0, weight=1)

unitA_view = tk.Text(unit_view_frame, width=34, bg="white", wrap="word")
unitA_view.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
unitA_view.tag_config("left", justify="left")

unitB_view = tk.Text(unit_view_frame, width=34, bg="white", wrap="word")
unitB_view.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
unitB_view.tag_config("left", justify="left")

# -------------------------
# 下段：グラフ
# -------------------------

graph_frame = ttk.LabelFrame(content, text="差分分布")
graph_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
graph_frame.columnconfigure(0, weight=1)
graph_frame.rowconfigure(0, weight=1)

canvas = tk.Canvas(graph_frame, bg="white", highlightthickness=1, highlightbackground="#cccccc")
canvas.grid(row=0, column=0, sticky="nsew")

# -------------------------
# 能力値表示
# -------------------------

def format_unit(name):
    if name not in units:
        return "（未選択）"

    raw = units[name]
    evaluated = evaluate_stats(raw)

    lines = [f"【{name}】", ""]
    for k in raw:
        rv = raw[k]
        ev = evaluated.get(k, rv)
        if str(rv) != str(ev):
            lines.append(f"{k}: {rv}  →  {ev}")
        else:
            lines.append(f"{k}: {rv}")

    return "\n".join(lines)


def update_unit_views(event=None):
    for box in (unitA_view, unitB_view):
        box.config(state="normal")
        box.delete("1.0", tk.END)

    unitA_view.insert(tk.END, format_unit(unitA.get()))
    unitA_view.insert(tk.END, "\n", "left")
    unitA_view.tag_add("left", "1.0", "end")

    unitB_view.insert(tk.END, format_unit(unitB.get()))
    unitB_view.insert(tk.END, "\n", "left")
    unitB_view.tag_add("left", "1.0", "end")

    unitA_view.config(state="disabled")
    unitB_view.config(state="disabled")


unitA_box.bind("<<ComboboxSelected>>", update_unit_views)
unitB_box.bind("<<ComboboxSelected>>", update_unit_views)

# -------------------------
# 保存済みテスト一覧
# -------------------------

def refresh_history():
    history_listbox.delete(0, tk.END)
    for item in saved_tests:
        history_listbox.insert(tk.END, item["name"])


def restore_history(event=None):
    sel = history_listbox.curselection()
    if not sel:
        return

    item = saved_tests[sel[0]]

    unitA.set(item["Aキャラ"])
    unitB.set(item["Bキャラ"])

    exprA.delete(0, tk.END)
    exprA.insert(0, item["式A"])

    exprB.delete(0, tk.END)
    exprB.insert(0, item["式B"])

    trials.delete(0, tk.END)
    trials.insert(0, str(item["試行回数"]))

    save_name.delete(0, tk.END)
    save_name.insert(0, item["name"])

    update_unit_views()


def delete_history():
    sel = history_listbox.curselection()
    if not sel:
        return

    idx = sel[0]
    if 0 <= idx < len(saved_tests):
        saved_tests.pop(idx)
        save_json(TEST_FILE, saved_tests)
        refresh_history()


def clear_history():
    saved_tests.clear()
    save_json(TEST_FILE, saved_tests)
    refresh_history()


history_listbox.bind("<<ListboxSelect>>", restore_history)

ttk.Button(history_btns, text="復元", command=restore_history).grid(row=0, column=0, padx=4)
ttk.Button(history_btns, text="削除", command=delete_history).grid(row=0, column=1, padx=4)
ttk.Button(history_btns, text="全消去", command=clear_history).grid(row=0, column=2, padx=4)

# -------------------------
# 保存
# -------------------------

def save_current_test():
    name = save_name.get().strip()
    if not name:
        result_box.config(state="normal")
        result_box.delete("1.0", tk.END)
        result_box.insert(tk.END, "保存名を入力してください。", "left")
        result_box.tag_add("left", "1.0", "end")
        result_box.config(state="disabled")
        return

    item = {
        "name": name,
        "Aキャラ": unitA.get(),
        "Bキャラ": unitB.get(),
        "式A": exprA.get(),
        "式B": exprB.get(),
        "試行回数": int(trials.get()) if trials.get().isdigit() else 1000
    }

    for i, old in enumerate(saved_tests):
        if old["name"] == name:
            saved_tests[i] = item
            break
    else:
        saved_tests.append(item)

    save_json(TEST_FILE, saved_tests)
    refresh_history()

# -------------------------
# 実行
# -------------------------

def run_test():
    canvas.delete("all")
    result_box.config(state="normal")
    result_box.delete("1.0", tk.END)

    a_name = unitA.get()
    b_name = unitB.get()

    if a_name not in units or b_name not in units:
        result_box.insert(tk.END, "AキャラとBキャラを選択してください。", "left")
        result_box.tag_add("left", "1.0", "end")
        result_box.config(state="disabled")
        return

    statsA = evaluate_stats(units[a_name])
    statsB = evaluate_stats(units[b_name])

    eA = exprA.get().strip()
    eB = exprB.get().strip()

    if not eA or not eB:
        result_box.insert(tk.END, "式Aと式Bを入力してください。", "left")
        result_box.tag_add("left", "1.0", "end")
        result_box.config(state="disabled")
        return

    try:
        t = int(trials.get())
        if t <= 0:
            raise ValueError
    except:
        result_box.insert(tk.END, "試行回数は1以上の整数にしてください。", "left")
        result_box.tag_add("left", "1.0", "end")
        result_box.config(state="disabled")
        return

    gt = eq = lt = 0
    diffs = []
    dist = defaultdict(int)

    maxA = float("-inf")
    minA = float("inf")
    maxB = float("-inf")
    minB = float("inf")

    for _ in range(t):
        A = eval_expr(eA, statsA)
        B = eval_expr(eB, statsB)

        maxA = max(maxA, A)
        minA = min(minA, A)
        maxB = max(maxB, B)
        minB = min(minB, B)

        diff = A - B
        diffs.append(diff)
        dist[diff] += 1

        if A > B:
            gt += 1
        elif A < B:
            lt += 1
        else:
            eq += 1

    avg = sum(diffs) / len(diffs)

    text = []
    text.append(f"試行回数   {t}")
    text.append("")
    text.append(f"A > B      {gt}   ({gt/t*100:.2f}%)")
    text.append(f"A = B      {eq}   ({eq/t*100:.2f}%)")
    text.append(f"A < B      {lt}   ({lt/t*100:.2f}%)")
    text.append("")
    text.append(f"平均差      {avg:.2f}")
    text.append(f"最大差      {max(diffs)}")
    text.append(f"最小差      {min(diffs)}")
    text.append("")
    text.append(f"A最大       {maxA}")
    text.append(f"A最小       {minA}")
    text.append(f"B最大       {maxB}")
    text.append(f"B最小       {minB}")

    result_box.insert(tk.END, "\n".join(text), "left")
    result_box.tag_add("left", "1.0", "end")
    result_box.config(state="disabled")

    draw_graph(dist)

# -------------------------
# グラフ描画
# -------------------------

def draw_graph(dist):
    canvas.delete("all")

    width = max(1000, canvas.winfo_width())
    height = max(260, canvas.winfo_height())

    keys = sorted(dist.keys())
    if not keys:
        return

    left_margin = 45
    right_margin = 10
    bottom_margin = 28
    top_margin = 20

    usable_w = width - left_margin - right_margin
    usable_h = height - top_margin - bottom_margin

    max_v = max(dist.values())
    bar_w = max(4, usable_w / len(keys))

    canvas.create_line(left_margin, height - bottom_margin, width - right_margin, height - bottom_margin, fill="#888888")
    canvas.create_line(left_margin, top_margin, left_margin, height - bottom_margin, fill="#888888")

    for i, k in enumerate(keys):
        v = dist[k]
        h = (v / max_v) * usable_h
        x0 = left_margin + i * bar_w
        y0 = height - bottom_margin - h
        x1 = x0 + bar_w - 1
        y1 = height - bottom_margin

        canvas.create_rectangle(x0, y0, x1, y1, fill="#4caf50", outline="")

        if len(keys) <= 45:
            canvas.create_text(
                x0 + bar_w / 2,
                height - 10,
                text=str(k),
                fill="black",
                font=("Arial", 8)
            )

# -------------------------
# ユニット編集
# -------------------------

def open_editor():
    win = tk.Toplevel()
    win.title("ユニット編集")
    win.geometry("800x680")

    fields = [
        "筋力",
        "敏捷性",
        "器用度",
        "体力",
        "知力",
        "精神力",
        "武器A攻撃力",
        "武器A防御力",
        "武器A重さ",
        "武器Aスキル",
        "武器Aクリ率",
        "武器B攻撃力",
        "武器B防御力",
        "武器B重さ",
        "武器Bスキル",
        "武器Bクリ率",
        "防具防御力",
        "防具重さ",
        "防具スキル",
        "回避スキル"
    ]

    selected_original_name = {"value": None}

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=0)
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(0, weight=1)

    left = ttk.LabelFrame(outer, text="ユニット一覧")
    left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))

    right = ttk.LabelFrame(outer, text="ユニット編集")
    right.grid(row=0, column=1, sticky="nsew")

    list_frame = ttk.Frame(left, padding=6)
    list_frame.pack(fill="both", expand=True)

    unit_listbox = tk.Listbox(list_frame, width=24, height=28)
    unit_listbox.pack(side="left", fill="both", expand=True)

    list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=unit_listbox.yview)
    list_scroll.pack(side="right", fill="y")
    unit_listbox.config(yscrollcommand=list_scroll.set)

    left_btns = ttk.Frame(left, padding=(6, 0, 6, 6))
    left_btns.pack(fill="x")

    form = ttk.Frame(right, padding=10)
    form.pack(fill="both", expand=True)
    form.columnconfigure(1, weight=1)

    ttk.Label(form, text="名前").grid(row=0, column=0, sticky="w", padx=4, pady=3)
    name_entry = tk.Entry(form, width=28)
    name_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=3)

    entries = {}

    for i, f in enumerate(fields, start=1):
        ttk.Label(form, text=f).grid(row=i, column=0, sticky="w", padx=4, pady=3)
        e = tk.Entry(form, width=20)
        e.insert(0, "0")
        e.grid(row=i, column=1, sticky="w", padx=4, pady=3)
        entries[f] = e

    status_var = tk.StringVar(value="新規作成モード")
    ttk.Label(form, textvariable=status_var, foreground="#555").grid(
        row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 4)
    )

    btns = ttk.Frame(form)
    btns.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def refresh_listbox(select_name=None):
        unit_listbox.delete(0, tk.END)
        names = sorted(units.keys())
        for n in names:
            unit_listbox.insert(tk.END, n)

        if select_name and select_name in names:
            idx = names.index(select_name)
            unit_listbox.selection_clear(0, tk.END)
            unit_listbox.selection_set(idx)
            unit_listbox.see(idx)

    def clear_form():
        selected_original_name["value"] = None
        name_entry.delete(0, tk.END)
        for f in fields:
            entries[f].delete(0, tk.END)
            entries[f].insert(0, "0")
        status_var.set("新規作成モード")

    def load_unit_to_form(name):
        if name not in units:
            return

        data = units[name]
        selected_original_name["value"] = name

        name_entry.delete(0, tk.END)
        name_entry.insert(0, name)

        for f in fields:
            entries[f].delete(0, tk.END)
            entries[f].insert(0, str(data.get(f, 0)))

        status_var.set(f"編集中: {name}")

    def get_form_data():
        name = name_entry.get().strip()
        if not name:
            return None, None

        data = {}
        for f in fields:
            raw = entries[f].get().strip()
            data[f] = raw if raw else "0"

        return name, data

    def save_current():
        new_name, data = get_form_data()
        if not new_name:
            return

        original_name = selected_original_name["value"]
        units[new_name] = data
        save_json(UNIT_FILE, units)
        refresh_units()
        refresh_listbox(select_name=new_name)

        if original_name == new_name:
            status_var.set(f"上書き保存: {new_name}")
        else:
            status_var.set(f"別ユニットとして保存: {new_name}")

        selected_original_name["value"] = new_name
        update_unit_views()

    def save_as_new_copy():
        new_name, data = get_form_data()
        if not new_name:
            return

        units[new_name] = data
        save_json(UNIT_FILE, units)
        refresh_units()
        refresh_listbox(select_name=new_name)
        selected_original_name["value"] = new_name
        status_var.set(f"新規保存: {new_name}")
        update_unit_views()

    def delete_selected():
        sel = unit_listbox.curselection()
        if not sel:
            return

        name = unit_listbox.get(sel[0])
        if name in units:
            del units[name]
            save_json(UNIT_FILE, units)
            refresh_units()
            refresh_listbox()
            clear_form()
            status_var.set(f"削除: {name}")
            update_unit_views()

    def duplicate_selected():
        sel = unit_listbox.curselection()
        if not sel:
            return

        name = unit_listbox.get(sel[0])
        if name not in units:
            return

        base = f"{name}_copy"
        new_name = base
        i = 2
        while new_name in units:
            new_name = f"{base}{i}"
            i += 1

        units[new_name] = dict(units[name])
        save_json(UNIT_FILE, units)
        refresh_units()
        refresh_listbox(select_name=new_name)
        load_unit_to_form(new_name)
        status_var.set(f"複製作成: {new_name}")
        update_unit_views()

    def on_select(event=None):
        sel = unit_listbox.curselection()
        if not sel:
            return
        name = unit_listbox.get(sel[0])
        load_unit_to_form(name)

    ttk.Button(left_btns, text="新規", command=clear_form).pack(side="left", padx=2)
    ttk.Button(left_btns, text="複製", command=duplicate_selected).pack(side="left", padx=2)
    ttk.Button(left_btns, text="削除", command=delete_selected).pack(side="left", padx=2)

    ttk.Button(btns, text="保存", command=save_current).pack(side="left", padx=4)
    ttk.Button(btns, text="別名で保存", command=save_as_new_copy).pack(side="left", padx=4)
    ttk.Button(btns, text="フォーム初期化", command=clear_form).pack(side="left", padx=4)

    unit_listbox.bind("<<ListboxSelect>>", on_select)
    refresh_listbox()

# -------------------------
# ボタン
# -------------------------

ttk.Button(tool, text="実行", command=run_test).grid(row=0, column=0, padx=6)
ttk.Button(tool, text="保存", command=save_current_test).grid(row=0, column=1, padx=6)
ttk.Button(tool, text="ユニット編集", command=open_editor).grid(row=0, column=2, padx=6)

# 初期更新
refresh_history()
update_unit_views()

root.mainloop()