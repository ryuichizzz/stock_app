import json
import random
import tkinter as tk
from collections import Counter
from tkinter import ttk, filedialog, messagebox, simpledialog


DEFAULT_DATA = {
    "version": 1,
    "cultures": {
        "elf_female": {
            "label": "エルフ女性",
            "description": "柔らかく流れる響き",
            "syllableGroups": {
                "open_soft": [
                    {"text": "エ", "weight": 8},
                    {"text": "リ", "weight": 10},
                    {"text": "シェ", "weight": 5},
                    {"text": "ミ", "weight": 6}
                ],
                "mid_flow": [
                    {"text": "リ", "weight": 10},
                    {"text": "リア", "weight": 7},
                    {"text": "レ", "weight": 6},
                    {"text": "ネ", "weight": 5}
                ],
                "end_noble": [
                    {"text": "リア", "weight": 10},
                    {"text": "シア", "weight": 8},
                    {"text": "リエ", "weight": 5},
                    {"text": "ミア", "weight": 6}
                ]
            },
            "patterns": [
                {"id": "short", "slots": ["open_soft", "end_noble"], "weight": 15},
                {"id": "standard", "slots": ["open_soft", "mid_flow", "end_noble"], "weight": 60},
                {"id": "long", "slots": ["open_soft", "mid_flow", "mid_flow", "end_noble"], "weight": 25}
            ],
            "rules": {
                "minLength": 2,
                "maxLength": 10,
                "maxRepeat": 2,
                "forbiddenStart": ["ッ"],
                "forbiddenEnd": ["ッ", "ァ", "ィ", "ゥ", "ェ", "ォ"]
            }
        }
    }
}

SMALL_KANA = set("ァィゥェォャュョッ")


def deep_copy(data):
    return json.loads(json.dumps(data, ensure_ascii=False))


def normalize_item(item):
    if isinstance(item, dict):
        text = str(item.get("text", "")).strip()
        try:
            weight = int(item.get("weight", 1))
        except Exception:
            weight = 1
        return {"text": text, "weight": weight}
    else:
        return {"text": str(item).strip(), "weight": 1}


def normalize_item_list(items):
    out = []
    for item in items or []:
        norm = normalize_item(item)
        if norm["text"]:
            out.append(norm)
    return out


def upgrade_legacy_data(data):
    """
    旧形式を新形式へ一時変換する。
    対応対象:
      1) syllables.start/mid/end の固定3区分
      2) syllables.end が male/female/neutral を持つ形式
    """
    if "cultures" not in data or not isinstance(data["cultures"], dict):
        return data

    upgraded = deep_copy(data)

    for culture_id, culture in upgraded["cultures"].items():
        if "syllableGroups" in culture and isinstance(culture["syllableGroups"], dict):
            # すでに新形式
            for gname, items in list(culture["syllableGroups"].items()):
                culture["syllableGroups"][gname] = normalize_item_list(items)
            continue

        syllables = culture.get("syllables")
        if not isinstance(syllables, dict):
            culture["syllableGroups"] = {}
            continue

        groups = {}

        # 旧 start / mid
        if "start" in syllables:
            groups["start"] = normalize_item_list(syllables.get("start", []))
        if "mid" in syllables:
            groups["mid"] = normalize_item_list(syllables.get("mid", []))

        # 旧 end
        old_end = syllables.get("end", [])
        if isinstance(old_end, dict):
            # male/female/neutral 形式
            if "male" in old_end:
                groups["end_male"] = normalize_item_list(old_end.get("male", []))
            if "female" in old_end:
                groups["end_female"] = normalize_item_list(old_end.get("female", []))
            if "neutral" in old_end:
                groups["end_neutral"] = normalize_item_list(old_end.get("neutral", []))
        else:
            groups["end"] = normalize_item_list(old_end)

        culture["syllableGroups"] = groups

        # patterns の slots が旧 start/mid/end ならそのまま使える
        # end_male などは旧 gender 選択前提だったが、ここでは slots は変更しない
        # そのため、旧 gender 分岐型の end_male/end_female/end_neutral を使いたい場合は
        # 読込後に patterns を任意グループに直す想定。
        if "patterns" not in culture or not isinstance(culture["patterns"], list):
            culture["patterns"] = [
                {"id": "short", "slots": ["start", "end"], "weight": 20},
                {"id": "standard", "slots": ["start", "mid", "end"], "weight": 60},
            ]

        if "rules" not in culture or not isinstance(culture["rules"], dict):
            culture["rules"] = {
                "minLength": 2,
                "maxLength": 10,
                "maxRepeat": 2,
                "forbiddenStart": ["ッ"],
                "forbiddenEnd": ["ッ", "ァ", "ィ", "ゥ", "ェ", "ォ"]
            }

    upgraded["version"] = upgraded.get("version", 1)
    return upgraded


def weighted_pick(items):
    valid_items = []
    weights = []
    for item in items or []:
        try:
            weight = int(item.get("weight", 1))
        except Exception:
            weight = 1
        if weight <= 0:
            continue
        valid_items.append(item)
        weights.append(weight)
    if not valid_items:
        return None
    return random.choices(valid_items, weights=weights, k=1)[0]


def max_repeat_count(text):
    if not text:
        return 0
    best = 1
    run = 1
    for i in range(1, len(text)):
        if text[i] == text[i - 1]:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def is_valid_name(name, rules):
    if not name:
        return False

    min_length = int(rules.get("minLength", 2))
    max_length = int(rules.get("maxLength", 10))
    forbidden_start = set(rules.get("forbiddenStart", []))
    forbidden_end = set(rules.get("forbiddenEnd", []))
    max_repeat = int(rules.get("maxRepeat", 2))

    if len(name) < min_length or len(name) > max_length:
        return False
    if name[0] in forbidden_start:
        return False
    if name[-1] in forbidden_end:
        return False
    if name[0] in SMALL_KANA:
        return False
    if name[-1] in SMALL_KANA:
        return False
    if max_repeat_count(name) > max_repeat:
        return False
    return True


def generate_one(data, culture_id):
    culture = data["cultures"].get(culture_id)
    if not culture:
        return None

    groups = culture.get("syllableGroups", {})
    patterns = culture.get("patterns", [])
    rules = culture.get("rules", {})

    pattern = weighted_pick(patterns)
    if not pattern:
        return None

    out = []
    for group_name in pattern.get("slots", []):
        group_items = groups.get(group_name, [])
        picked = weighted_pick(group_items)
        if not picked:
            return None
        out.append(picked.get("text", ""))

    name = "".join(out)
    if is_valid_name(name, rules):
        return name
    return None


def generate_many(data, culture_id, count=10):
    results = []
    seen = set()
    guard = 0
    while len(results) < count and guard < count * 100:
        guard += 1
        name = generate_one(data, culture_id)
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        results.append(name)
    return results


def simulate_frequency(data, culture_id, trials=1000):
    counter = Counter()
    for _ in range(trials):
        name = generate_one(data, culture_id)
        if name:
            counter[name] += 1
    return counter


def concat_groups(item_lists):
    """合体は単純連結のみ。重複整理はしない。"""
    out = []
    for items in item_lists:
        for item in items:
            out.append(normalize_item(item))
    return out


def dedupe_group_items_sum(items):
    """選択中グループ内の重複だけを、text単位でweight合算して整理。"""
    merged = {}
    order = []

    for item in items:
        norm = normalize_item(item)
        text = norm["text"]
        weight = norm["weight"]
        if not text:
            continue

        if text not in merged:
            merged[text] = weight
            order.append(text)
        else:
            merged[text] += weight

    return [{"text": text, "weight": merged[text]} for text in order]


class NameEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ファンタジー名前エディタ groups互換版")
        self.root.geometry("1680x960")

        self.data = deep_copy(DEFAULT_DATA)
        self.current_culture_id = None
        self.current_file = None
        self.current_group_name = None

        self._build_ui()
        self.refresh_culture_list()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        top = ttk.Frame(main)
        top.pack(fill="x", pady=(0, 8))

        ttk.Button(top, text="新規", command=self.new_data).pack(side="left", padx=2)
        ttk.Button(top, text="開く", command=self.load_json).pack(side="left", padx=2)
        ttk.Button(top, text="保存", command=self.save_json).pack(side="left", padx=2)
        ttk.Button(top, text="名前を付けて保存", command=self.save_json_as).pack(side="left", padx=2)

        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        pane = ttk.PanedWindow(main, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane, padding=6)
        center = ttk.Frame(pane, padding=6)
        right = ttk.Frame(pane, padding=6)

        pane.add(left, weight=1)
        pane.add(center, weight=3)
        pane.add(right, weight=2)

        self._build_left_panel(left)
        self._build_center_panel(center)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        ttk.Label(parent, text="文化圏", font=("", 12, "bold")).pack(anchor="w")

        self.culture_listbox = tk.Listbox(parent, height=18)
        self.culture_listbox.pack(fill="both", expand=True, pady=6)
        self.culture_listbox.bind("<<ListboxSelect>>", self.on_select_culture)

        row1 = ttk.Frame(parent)
        row1.pack(fill="x", pady=(0, 6))
        ttk.Button(row1, text="複製", command=self.duplicate_culture).pack(side="left", padx=2)
        ttk.Button(row1, text="ID変更", command=self.rename_culture_id).pack(side="left", padx=2)

        form = ttk.LabelFrame(parent, text="文化圏追加")
        form.pack(fill="x", pady=6)

        ttk.Label(form, text="ID").pack(anchor="w")
        self.new_id_entry = ttk.Entry(form)
        self.new_id_entry.pack(fill="x", padx=4, pady=2)

        ttk.Label(form, text="表示名").pack(anchor="w")
        self.new_label_entry = ttk.Entry(form)
        self.new_label_entry.pack(fill="x", padx=4, pady=2)

        ttk.Label(form, text="説明").pack(anchor="w")
        self.new_desc_entry = ttk.Entry(form)
        self.new_desc_entry.pack(fill="x", padx=4, pady=2)

        row2 = ttk.Frame(form)
        row2.pack(fill="x", pady=4)
        ttk.Button(row2, text="追加", command=self.add_culture).pack(side="left", padx=2)
        ttk.Button(row2, text="削除", command=self.delete_culture).pack(side="left", padx=2)

    def _build_center_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)

        tab_basic = ttk.Frame(notebook, padding=6)
        tab_groups = ttk.Frame(notebook, padding=6)
        tab_patterns = ttk.Frame(notebook, padding=6)
        tab_rules = ttk.Frame(notebook, padding=6)
        tab_json = ttk.Frame(notebook, padding=6)

        notebook.add(tab_basic, text="基本")
        notebook.add(tab_groups, text="音節グループ")
        notebook.add(tab_patterns, text="パターン")
        notebook.add(tab_rules, text="ルール")
        notebook.add(tab_json, text="文化圏JSON")

        self._build_basic_tab(tab_basic)
        self._build_groups_tab(tab_groups)
        self._build_patterns_tab(tab_patterns)
        self._build_rules_tab(tab_rules)
        self._build_json_tab(tab_json)

    def _build_basic_tab(self, parent):
        ttk.Label(parent, text="表示名").grid(row=0, column=0, sticky="w")
        self.label_entry = ttk.Entry(parent)
        self.label_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(parent, text="説明").grid(row=1, column=0, sticky="w")
        self.desc_entry = ttk.Entry(parent)
        self.desc_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Button(parent, text="基本情報を保存", command=self.save_basic).grid(row=2, column=1, sticky="e", pady=6)
        parent.columnconfigure(1, weight=1)

    def _build_groups_tab(self, parent):
        outer = ttk.PanedWindow(parent, orient="horizontal")
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer, padding=4)
        right = ttk.Frame(outer, padding=4)
        outer.add(left, weight=1)
        outer.add(right, weight=3)

        ttk.Label(left, text="音節グループ", font=("", 11, "bold")).pack(anchor="w")
        self.group_listbox = tk.Listbox(left, height=18)
        self.group_listbox.pack(fill="both", expand=True, pady=6)
        self.group_listbox.bind("<<ListboxSelect>>", self.on_select_group)

        group_form = ttk.LabelFrame(left, text="グループ操作")
        group_form.pack(fill="x", pady=6)

        ttk.Label(group_form, text="グループ名").pack(anchor="w")
        self.group_name_entry = ttk.Entry(group_form)
        self.group_name_entry.pack(fill="x", padx=4, pady=2)

        row1 = ttk.Frame(group_form)
        row1.pack(fill="x", pady=4)
        ttk.Button(row1, text="追加", command=self.add_group).pack(side="left", padx=2)
        ttk.Button(row1, text="名前変更", command=self.rename_group).pack(side="left", padx=2)
        ttk.Button(row1, text="削除", command=self.delete_group).pack(side="left", padx=2)

        row2 = ttk.Frame(group_form)
        row2.pack(fill="x", pady=4)
        ttk.Button(row2, text="複製", command=self.duplicate_group).pack(side="left", padx=2)
        ttk.Button(row2, text="他文化へコピー", command=self.copy_group_to_other_culture).pack(side="left", padx=2)
        ttk.Button(row2, text="合体", command=self.merge_groups_dialog).pack(side="left", padx=2)

        top = ttk.Frame(right)
        top.pack(fill="x", pady=(0, 6))

        ttk.Label(top, text="選択グループ内の音節", font=("", 11, "bold")).pack(side="left")
        ttk.Button(top, text="文字順", command=self.sort_group_items_by_text).pack(side="right", padx=2)
        ttk.Button(top, text="重み順", command=self.sort_group_items_by_weight).pack(side="right", padx=2)
        ttk.Button(top, text="重複削除", command=self.dedupe_current_group).pack(side="right", padx=2)

        table_frame = ttk.Frame(right)
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.syllable_tree = ttk.Treeview(
            table_frame,
            columns=("text", "weight"),
            show="headings",
            selectmode="browse"
        )
        self.syllable_tree.heading("text", text="音節")
        self.syllable_tree.heading("weight", text="重み")
        self.syllable_tree.column("text", width=240, anchor="w")
        self.syllable_tree.column("weight", width=100, anchor="center")
        self.syllable_tree.grid(row=0, column=0, sticky="nsew")
        self.syllable_tree.bind("<<TreeviewSelect>>", self.on_select_syllable)

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.syllable_tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.syllable_tree.configure(yscrollcommand=yscroll.set)

        editor = ttk.LabelFrame(right, text="音節編集")
        editor.pack(fill="x", pady=8)
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="音節").grid(row=0, column=0, sticky="w")
        self.syllable_text_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.syllable_text_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(editor, text="重み").grid(row=1, column=0, sticky="w")
        self.syllable_weight_var = tk.StringVar(value="5")
        ttk.Entry(editor, textvariable=self.syllable_weight_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        btns = ttk.Frame(editor)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(btns, text="追加", command=self.add_syllable).pack(side="left", padx=2)
        ttk.Button(btns, text="更新", command=self.update_syllable).pack(side="left", padx=2)
        ttk.Button(btns, text="削除", command=self.delete_syllable).pack(side="left", padx=2)
        ttk.Button(btns, text="入力クリア", command=self.clear_syllable_editor).pack(side="left", padx=2)

    def _build_patterns_tab(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        table_frame = ttk.Frame(parent)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.pattern_tree = ttk.Treeview(
            table_frame,
            columns=("id", "slots", "weight"),
            show="headings",
            selectmode="browse"
        )
        self.pattern_tree.heading("id", text="ID")
        self.pattern_tree.heading("slots", text="slots")
        self.pattern_tree.heading("weight", text="重み")
        self.pattern_tree.column("id", width=160, anchor="w")
        self.pattern_tree.column("slots", width=360, anchor="w")
        self.pattern_tree.column("weight", width=80, anchor="center")
        self.pattern_tree.grid(row=0, column=0, sticky="nsew")
        self.pattern_tree.bind("<<TreeviewSelect>>", self.on_select_pattern)

        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.pattern_tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.pattern_tree.configure(yscrollcommand=yscroll.set)

        editor = ttk.LabelFrame(parent, text="パターン編集")
        editor.grid(row=2, column=0, sticky="ew", pady=8)
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="ID").grid(row=0, column=0, sticky="w")
        self.pattern_id_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.pattern_id_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(editor, text="slots").grid(row=1, column=0, sticky="w")
        self.pattern_slots_var = tk.StringVar()
        ttk.Entry(editor, textvariable=self.pattern_slots_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(editor, text="重み").grid(row=2, column=0, sticky="w")
        self.pattern_weight_var = tk.StringVar(value="20")
        ttk.Entry(editor, textvariable=self.pattern_weight_var).grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        hint = ttk.Label(editor, text="slots は グループ名をカンマ区切りで入力", foreground="gray")
        hint.grid(row=3, column=0, columnspan=2, sticky="w", padx=2, pady=(0, 4))

        btns = ttk.Frame(editor)
        btns.grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(btns, text="追加", command=self.add_pattern).pack(side="left", padx=2)
        ttk.Button(btns, text="更新", command=self.update_pattern).pack(side="left", padx=2)
        ttk.Button(btns, text="削除", command=self.delete_pattern).pack(side="left", padx=2)
        ttk.Button(btns, text="入力クリア", command=self.clear_pattern_editor).pack(side="left", padx=2)

    def _build_rules_tab(self, parent):
        form = ttk.LabelFrame(parent, text="ルール編集")
        form.pack(fill="x", pady=6)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="minLength").grid(row=0, column=0, sticky="w")
        self.rule_min_length_var = tk.StringVar(value="2")
        ttk.Entry(form, textvariable=self.rule_min_length_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="maxLength").grid(row=1, column=0, sticky="w")
        self.rule_max_length_var = tk.StringVar(value="10")
        ttk.Entry(form, textvariable=self.rule_max_length_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="maxRepeat").grid(row=2, column=0, sticky="w")
        self.rule_max_repeat_var = tk.StringVar(value="2")
        ttk.Entry(form, textvariable=self.rule_max_repeat_var).grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="forbiddenStart").grid(row=3, column=0, sticky="w")
        self.rule_forbidden_start_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.rule_forbidden_start_var).grid(row=3, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="forbiddenEnd").grid(row=4, column=0, sticky="w")
        self.rule_forbidden_end_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.rule_forbidden_end_var).grid(row=4, column=1, sticky="ew", padx=4, pady=4)

        hint = ttk.Label(form, text="禁止文字はカンマ区切り。例: ッ,ァ,ィ,ゥ,ェ,ォ", foreground="gray")
        hint.grid(row=5, column=0, columnspan=2, sticky="w", padx=2, pady=(0, 4))

        ttk.Button(form, text="ルールを保存", command=self.save_rules_form).grid(row=6, column=1, sticky="e", pady=6)

        json_frame = ttk.LabelFrame(parent, text="ルールJSON確認")
        json_frame.pack(fill="both", expand=True, pady=6)

        self.rules_text = tk.Text(json_frame, wrap="none", height=12)
        self.rules_text.pack(fill="both", expand=True, pady=4)
        ttk.Button(json_frame, text="JSONからルールを上書き", command=self.apply_rules_json).pack(anchor="e", pady=4)

    def _build_json_tab(self, parent):
        ttk.Label(parent, text="現在の文化圏JSON").pack(anchor="w")
        self.json_text = tk.Text(parent, wrap="none")
        self.json_text.pack(fill="both", expand=True, pady=4)

        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Button(row, text="文化圏をJSON表示", command=self.show_current_culture_json).pack(side="left", padx=2)
        ttk.Button(row, text="このJSONで上書き", command=self.apply_current_culture_json).pack(side="left", padx=2)

    def _build_right_panel(self, parent):
        ttk.Label(parent, text="生成テスト", font=("", 12, "bold")).pack(anchor="w")

        form = ttk.Frame(parent)
        form.pack(fill="x", pady=6)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="文化圏").grid(row=0, column=0, sticky="w")
        self.preview_culture_var = tk.StringVar()
        self.preview_culture_combo = ttk.Combobox(form, textvariable=self.preview_culture_var, state="readonly")
        self.preview_culture_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="生成数").grid(row=1, column=0, sticky="w")
        self.count_var = tk.StringVar(value="12")
        ttk.Entry(form, textvariable=self.count_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Button(parent, text="名前を生成", command=self.run_generate).pack(fill="x", pady=4)

        self.result_text = tk.Text(parent, height=14)
        self.result_text.pack(fill="both", expand=True, pady=4)

        stats_frame = ttk.LabelFrame(parent, text="出現回数テスト")
        stats_frame.pack(fill="both", expand=True, pady=6)

        stats_top = ttk.Frame(stats_frame)
        stats_top.pack(fill="x", pady=(0, 4))
        ttk.Label(stats_top, text="試行回数").pack(side="left")
        self.stats_trials_var = tk.StringVar(value="1000")
        ttk.Entry(stats_top, textvariable=self.stats_trials_var, width=10).pack(side="left", padx=4)
        ttk.Button(stats_top, text="集計実行", command=self.run_frequency_test).pack(side="left", padx=4)

        self.stats_text = tk.Text(stats_frame, height=14)
        self.stats_text.pack(fill="both", expand=True)

    # ---------- utility ----------

    def set_status(self, text):
        self.status_var.set(text)

    def set_text(self, widget, value):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)

    def get_text(self, widget):
        return widget.get("1.0", tk.END).strip()

    def culture_ids(self):
        return list(self.data.get("cultures", {}).keys())

    def current_culture(self):
        if not self.current_culture_id:
            return None
        return self.data["cultures"].get(self.current_culture_id)

    def current_groups(self):
        culture = self.current_culture()
        if not culture:
            return {}
        return culture.setdefault("syllableGroups", {})

    def current_group_items(self):
        groups = self.current_groups()
        if not self.current_group_name:
            return []
        return groups.setdefault(self.current_group_name, [])

    # ---------- culture ----------

    def refresh_culture_list(self):
        self.culture_listbox.delete(0, tk.END)
        culture_ids = self.culture_ids()

        for cid in culture_ids:
            culture = self.data["cultures"][cid]
            label = culture.get("label", cid)
            self.culture_listbox.insert(tk.END, f"{cid} | {label}")

        self.preview_culture_combo["values"] = culture_ids

        if culture_ids:
            if self.current_culture_id not in culture_ids:
                self.current_culture_id = culture_ids[0]
            self.preview_culture_var.set(self.current_culture_id)

            index = culture_ids.index(self.current_culture_id)
            self.culture_listbox.selection_clear(0, tk.END)
            self.culture_listbox.selection_set(index)
            self.culture_listbox.activate(index)
            self.load_current_culture_to_ui()
        else:
            self.current_culture_id = None

    def get_selected_culture_id_from_list(self):
        sel = self.culture_listbox.curselection()
        if not sel:
            return None
        index = sel[0]
        culture_ids = self.culture_ids()
        if index >= len(culture_ids):
            return None
        return culture_ids[index]

    def on_select_culture(self, event=None):
        cid = self.get_selected_culture_id_from_list()
        if cid:
            self.current_culture_id = cid
            self.preview_culture_var.set(cid)
            self.load_current_culture_to_ui()

    def load_current_culture_to_ui(self):
        culture = self.current_culture()
        if not culture:
            return

        self.label_entry.delete(0, tk.END)
        self.label_entry.insert(0, culture.get("label", ""))

        self.desc_entry.delete(0, tk.END)
        self.desc_entry.insert(0, culture.get("description", ""))

        self.refresh_group_list()
        self.refresh_pattern_tree()
        self.clear_pattern_editor()
        self.load_rules_to_form()
        self.show_current_culture_json()
        self.set_status(f"文化圏 {self.current_culture_id} を読み込みました")

    def save_basic(self):
        culture = self.current_culture()
        if not culture:
            return
        culture["label"] = self.label_entry.get().strip()
        culture["description"] = self.desc_entry.get().strip()
        self.refresh_culture_list()
        self.set_status("基本情報を保存しました")

    def add_culture(self):
        cid = self.new_id_entry.get().strip()
        label = self.new_label_entry.get().strip() or cid
        desc = self.new_desc_entry.get().strip()

        if not cid:
            messagebox.showwarning("入力不足", "文化圏IDを入れてください")
            return
        if cid in self.data["cultures"]:
            messagebox.showwarning("重複", "そのIDは既に存在します")
            return

        self.data["cultures"][cid] = {
            "label": label,
            "description": desc,
            "syllableGroups": {
                "group_main": [{"text": "ア", "weight": 5}]
            },
            "patterns": [
                {"id": "short", "slots": ["group_main"], "weight": 20},
                {"id": "standard", "slots": ["group_main", "group_main"], "weight": 60}
            ],
            "rules": {
                "minLength": 2,
                "maxLength": 10,
                "maxRepeat": 2,
                "forbiddenStart": ["ッ"],
                "forbiddenEnd": ["ッ", "ァ", "ィ", "ゥ", "ェ", "ォ"]
            }
        }

        self.current_culture_id = cid
        self.refresh_culture_list()
        self.set_status(f"文化圏 {cid} を追加しました")

    def delete_culture(self):
        cid = self.current_culture_id
        if not cid:
            return
        if len(self.data["cultures"]) <= 1:
            messagebox.showwarning("削除不可", "最後の1件は削除できません")
            return
        if not messagebox.askyesno("確認", f"{cid} を削除しますか？"):
            return

        del self.data["cultures"][cid]
        self.current_culture_id = None
        self.refresh_culture_list()
        self.set_status(f"文化圏 {cid} を削除しました")

    def duplicate_culture(self):
        cid = self.current_culture_id
        if not cid:
            return

        new_id = simpledialog.askstring("文化圏複製", "新しい文化圏ID", initialvalue=f"{cid}_copy")
        if not new_id:
            return
        new_id = new_id.strip()

        if new_id in self.data["cultures"]:
            messagebox.showwarning("重複", "そのIDは既に存在します")
            return

        copied = deep_copy(self.data["cultures"][cid])
        copied["label"] = f"{copied.get('label', cid)} コピー"
        self.data["cultures"][new_id] = copied
        self.current_culture_id = new_id
        self.refresh_culture_list()
        self.set_status(f"{cid} を {new_id} として複製しました")

    def rename_culture_id(self):
        cid = self.current_culture_id
        if not cid:
            return

        new_id = simpledialog.askstring("文化圏ID変更", "新しい文化圏ID", initialvalue=cid)
        if not new_id:
            return
        new_id = new_id.strip()

        if new_id == cid:
            return
        if new_id in self.data["cultures"]:
            messagebox.showwarning("重複", "そのIDは既に存在します")
            return

        items = list(self.data["cultures"].items())
        new_cultures = {}
        for key, value in items:
            if key == cid:
                new_cultures[new_id] = value
            else:
                new_cultures[key] = value

        self.data["cultures"] = new_cultures
        self.current_culture_id = new_id
        self.refresh_culture_list()
        self.set_status(f"文化圏IDを {cid} -> {new_id} に変更しました")

    # ---------- groups ----------

    def refresh_group_list(self):
        self.group_listbox.delete(0, tk.END)
        groups = self.current_groups()
        names = list(groups.keys())

        for name in names:
            self.group_listbox.insert(tk.END, name)

        if names:
            if self.current_group_name not in names:
                self.current_group_name = names[0]
            index = names.index(self.current_group_name)
            self.group_listbox.selection_clear(0, tk.END)
            self.group_listbox.selection_set(index)
            self.group_listbox.activate(index)
            self.group_name_entry.delete(0, tk.END)
            self.group_name_entry.insert(0, self.current_group_name)
            self.refresh_syllable_tree()
        else:
            self.current_group_name = None
            self.group_name_entry.delete(0, tk.END)
            self.refresh_syllable_tree()

    def get_selected_group_name(self):
        sel = self.group_listbox.curselection()
        if not sel:
            return None
        index = sel[0]
        names = list(self.current_groups().keys())
        if index >= len(names):
            return None
        return names[index]

    def on_select_group(self, event=None):
        name = self.get_selected_group_name()
        if name:
            self.current_group_name = name
            self.group_name_entry.delete(0, tk.END)
            self.group_name_entry.insert(0, name)
            self.refresh_syllable_tree()
            self.clear_syllable_editor()

    def add_group(self):
        groups = self.current_groups()
        name = self.group_name_entry.get().strip()
        if not name:
            messagebox.showwarning("入力不足", "グループ名を入れてください")
            return
        if name in groups:
            messagebox.showwarning("重複", "そのグループ名は既に存在します")
            return

        groups[name] = []
        self.current_group_name = name
        self.refresh_group_list()
        self.show_current_culture_json()
        self.set_status("グループを追加しました")

    def rename_group(self):
        groups = self.current_groups()
        old = self.current_group_name
        if not old:
            return

        new = self.group_name_entry.get().strip()
        if not new:
            messagebox.showwarning("入力不足", "新しいグループ名を入れてください")
            return
        if new == old:
            return
        if new in groups:
            messagebox.showwarning("重複", "そのグループ名は既に存在します")
            return

        items = list(groups.items())
        new_groups = {}
        for key, value in items:
            if key == old:
                new_groups[new] = value
            else:
                new_groups[key] = value

        self.current_culture()["syllableGroups"] = new_groups
        self.current_group_name = new

        for p in self.current_culture().get("patterns", []):
            p["slots"] = [new if slot == old else slot for slot in p.get("slots", [])]

        self.refresh_group_list()
        self.refresh_pattern_tree()
        self.show_current_culture_json()
        self.set_status(f"グループ名を {old} -> {new} に変更しました")

    def delete_group(self):
        groups = self.current_groups()
        name = self.current_group_name
        if not name:
            return
        if not messagebox.askyesno("確認", f"グループ {name} を削除しますか？"):
            return

        del groups[name]
        self.current_group_name = None
        self.refresh_group_list()
        self.show_current_culture_json()
        self.set_status("グループを削除しました")

    def duplicate_group(self):
        groups = self.current_groups()
        name = self.current_group_name
        if not name:
            return

        new_name = simpledialog.askstring("グループ複製", "新しいグループ名", initialvalue=f"{name}_copy")
        if not new_name:
            return
        new_name = new_name.strip()

        if new_name in groups:
            messagebox.showwarning("重複", "そのグループ名は既に存在します")
            return

        groups[new_name] = deep_copy(groups[name])
        self.current_group_name = new_name
        self.refresh_group_list()
        self.show_current_culture_json()
        self.set_status(f"グループ {name} を {new_name} として複製しました")

    def copy_group_to_other_culture(self):
        src_culture = self.current_culture_id
        src_group = self.current_group_name
        if not src_culture or not src_group:
            return

        target_culture = simpledialog.askstring("他文化へコピー", "コピー先文化圏ID", initialvalue=src_culture)
        if not target_culture:
            return
        target_culture = target_culture.strip()

        if target_culture not in self.data["cultures"]:
            messagebox.showwarning("未存在", "その文化圏IDは存在しません")
            return

        target_group = simpledialog.askstring("他文化へコピー", "コピー先グループ名", initialvalue=src_group)
        if not target_group:
            return
        target_group = target_group.strip()

        target_groups = self.data["cultures"][target_culture].setdefault("syllableGroups", {})
        if target_group in target_groups:
            if not messagebox.askyesno("確認", f"{target_culture}.{target_group} は既に存在します。上書きしますか？"):
                return

        target_groups[target_group] = deep_copy(self.current_groups()[src_group])
        self.show_current_culture_json()
        self.set_status(f"{src_culture}.{src_group} を {target_culture}.{target_group} にコピーしました")

    def merge_groups_dialog(self):
        culture = self.current_culture()
        if not culture:
            return
        groups = culture.get("syllableGroups", {})
        if len(groups) < 2:
            messagebox.showwarning("不足", "合体には少なくとも2グループ必要です")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("グループ合体")
        dialog.geometry("520x500")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="合体元グループを複数選択").pack(anchor="w", padx=8, pady=(8, 4))

        listbox = tk.Listbox(dialog, selectmode=tk.MULTIPLE)
        listbox.pack(fill="both", expand=True, padx=8, pady=4)
        group_names = list(groups.keys())
        for g in group_names:
            listbox.insert(tk.END, g)

        form = ttk.Frame(dialog, padding=8)
        form.pack(fill="x")

        ttk.Label(form, text="出力先文化圏ID").grid(row=0, column=0, sticky="w")
        culture_var = tk.StringVar(value=self.current_culture_id)
        ttk.Entry(form, textvariable=culture_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="出力先グループ名").grid(row=1, column=0, sticky="w")
        group_var = tk.StringVar(value="merged_group")
        ttk.Entry(form, textvariable=group_var).grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Label(form, text="合体は単純連結です").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))
        form.columnconfigure(1, weight=1)

        def do_merge():
            indices = listbox.curselection()
            if len(indices) < 2:
                messagebox.showwarning("不足", "合体元を2つ以上選んでください", parent=dialog)
                return

            target_culture = culture_var.get().strip()
            target_group = group_var.get().strip()

            if target_culture not in self.data["cultures"]:
                messagebox.showwarning("未存在", "出力先文化圏IDが存在しません", parent=dialog)
                return
            if not target_group:
                messagebox.showwarning("入力不足", "出力先グループ名を入れてください", parent=dialog)
                return

            source_items = []
            source_names = []
            for idx in indices:
                gname = group_names[idx]
                source_names.append(gname)
                source_items.append(groups[gname])

            merged = concat_groups(source_items)
            target_groups = self.data["cultures"][target_culture].setdefault("syllableGroups", {})
            target_groups[target_group] = merged

            dialog.destroy()
            if target_culture == self.current_culture_id:
                self.current_group_name = target_group
                self.refresh_group_list()
            self.show_current_culture_json()
            self.set_status(f"{', '.join(source_names)} を {target_culture}.{target_group} に合体しました")

        btns = ttk.Frame(dialog, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text="実行", command=do_merge).pack(side="right", padx=2)
        ttk.Button(btns, text="閉じる", command=dialog.destroy).pack(side="right", padx=2)

    # ---------- syllables ----------

    def refresh_syllable_tree(self):
        for item in self.syllable_tree.get_children():
            self.syllable_tree.delete(item)

        items = self.current_group_items()
        for idx, item in enumerate(items):
            self.syllable_tree.insert("", "end", iid=str(idx), values=(item.get("text", ""), item.get("weight", 1)))

    def clear_syllable_editor(self):
        self.syllable_text_var.set("")
        self.syllable_weight_var.set("5")
        for item in self.syllable_tree.selection():
            self.syllable_tree.selection_remove(item)

    def on_select_syllable(self, event=None):
        sel = self.syllable_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        items = self.current_group_items()
        if idx < 0 or idx >= len(items):
            return
        item = items[idx]
        self.syllable_text_var.set(item.get("text", ""))
        self.syllable_weight_var.set(str(item.get("weight", 1)))

    def add_syllable(self):
        items = self.current_group_items()
        if self.current_group_name is None:
            messagebox.showwarning("未選択", "先にグループを選んでください")
            return

        text = self.syllable_text_var.get().strip()
        if not text:
            messagebox.showwarning("入力不足", "音節を入れてください")
            return

        try:
            weight = int(self.syllable_weight_var.get().strip())
        except ValueError:
            messagebox.showwarning("入力エラー", "重みは整数で入れてください")
            return

        items.append({"text": text, "weight": weight})
        self.refresh_syllable_tree()
        self.show_current_culture_json()
        self.set_status("音節を追加しました")

    def update_syllable(self):
        sel = self.syllable_tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "更新する行を選んでください")
            return

        idx = int(sel[0])
        items = self.current_group_items()

        text = self.syllable_text_var.get().strip()
        if not text:
            messagebox.showwarning("入力不足", "音節を入れてください")
            return

        try:
            weight = int(self.syllable_weight_var.get().strip())
        except ValueError:
            messagebox.showwarning("入力エラー", "重みは整数で入れてください")
            return

        items[idx] = {"text": text, "weight": weight}
        self.refresh_syllable_tree()
        self.syllable_tree.selection_set(str(idx))
        self.show_current_culture_json()
        self.set_status("音節を更新しました")

    def delete_syllable(self):
        sel = self.syllable_tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "削除する行を選んでください")
            return

        idx = int(sel[0])
        items = self.current_group_items()
        if 0 <= idx < len(items):
            del items[idx]

        self.refresh_syllable_tree()
        self.clear_syllable_editor()
        self.show_current_culture_json()
        self.set_status("音節を削除しました")

    def sort_group_items_by_text(self):
        items = self.current_group_items()
        items.sort(key=lambda x: x.get("text", ""))
        self.refresh_syllable_tree()
        self.show_current_culture_json()
        self.set_status("音節を文字順でソートしました")

    def sort_group_items_by_weight(self):
        items = self.current_group_items()
        items.sort(key=lambda x: (-int(x.get("weight", 0)), x.get("text", "")))
        self.refresh_syllable_tree()
        self.show_current_culture_json()
        self.set_status("音節を重み順でソートしました")

    def dedupe_current_group(self):
        if not self.current_group_name:
            messagebox.showwarning("未選択", "先にグループを選んでください")
            return

        groups = self.current_groups()
        before = len(groups[self.current_group_name])
        groups[self.current_group_name] = dedupe_group_items_sum(groups[self.current_group_name])
        after = len(groups[self.current_group_name])

        self.refresh_syllable_tree()
        self.show_current_culture_json()
        self.set_status(f"重複削除を実行しました: {before}件 -> {after}件")

    # ---------- patterns ----------

    def current_patterns(self):
        culture = self.current_culture()
        if not culture:
            return []
        return culture.setdefault("patterns", [])

    def refresh_pattern_tree(self):
        for item in self.pattern_tree.get_children():
            self.pattern_tree.delete(item)

        patterns = self.current_patterns()
        for idx, item in enumerate(patterns):
            slots_text = ",".join(item.get("slots", []))
            self.pattern_tree.insert("", "end", iid=str(idx), values=(item.get("id", ""), slots_text, item.get("weight", 1)))

    def clear_pattern_editor(self):
        self.pattern_id_var.set("")
        self.pattern_slots_var.set("")
        self.pattern_weight_var.set("20")
        for item in self.pattern_tree.selection():
            self.pattern_tree.selection_remove(item)

    def on_select_pattern(self, event=None):
        sel = self.pattern_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        patterns = self.current_patterns()
        if idx < 0 or idx >= len(patterns):
            return
        item = patterns[idx]
        self.pattern_id_var.set(item.get("id", ""))
        self.pattern_slots_var.set(",".join(item.get("slots", [])))
        self.pattern_weight_var.set(str(item.get("weight", 1)))

    def _parse_pattern_slots(self, text):
        slots = [s.strip() for s in text.split(",") if s.strip()]
        if not slots:
            raise ValueError("slots を1つ以上入れてください")
        return slots

    def add_pattern(self):
        patterns = self.current_patterns()
        pattern_id = self.pattern_id_var.get().strip()
        if not pattern_id:
            messagebox.showwarning("入力不足", "IDを入れてください")
            return

        try:
            slots = self._parse_pattern_slots(self.pattern_slots_var.get().strip())
            weight = int(self.pattern_weight_var.get().strip())
        except ValueError as e:
            messagebox.showwarning("入力エラー", str(e))
            return

        patterns.append({"id": pattern_id, "slots": slots, "weight": weight})
        self.refresh_pattern_tree()
        self.show_current_culture_json()
        self.set_status("パターンを追加しました")

    def update_pattern(self):
        sel = self.pattern_tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "更新する行を選んでください")
            return

        idx = int(sel[0])
        patterns = self.current_patterns()

        pattern_id = self.pattern_id_var.get().strip()
        if not pattern_id:
            messagebox.showwarning("入力不足", "IDを入れてください")
            return

        try:
            slots = self._parse_pattern_slots(self.pattern_slots_var.get().strip())
            weight = int(self.pattern_weight_var.get().strip())
        except ValueError as e:
            messagebox.showwarning("入力エラー", str(e))
            return

        patterns[idx] = {"id": pattern_id, "slots": slots, "weight": weight}
        self.refresh_pattern_tree()
        self.pattern_tree.selection_set(str(idx))
        self.show_current_culture_json()
        self.set_status("パターンを更新しました")

    def delete_pattern(self):
        sel = self.pattern_tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "削除する行を選んでください")
            return
        idx = int(sel[0])
        patterns = self.current_patterns()
        if 0 <= idx < len(patterns):
            del patterns[idx]
        self.refresh_pattern_tree()
        self.clear_pattern_editor()
        self.show_current_culture_json()
        self.set_status("パターンを削除しました")

    # ---------- rules ----------

    def load_rules_to_form(self):
        culture = self.current_culture()
        if not culture:
            return
        rules = culture.setdefault("rules", {})

        self.rule_min_length_var.set(str(rules.get("minLength", 2)))
        self.rule_max_length_var.set(str(rules.get("maxLength", 10)))
        self.rule_max_repeat_var.set(str(rules.get("maxRepeat", 2)))
        self.rule_forbidden_start_var.set(",".join(rules.get("forbiddenStart", [])))
        self.rule_forbidden_end_var.set(",".join(rules.get("forbiddenEnd", [])))
        self.set_text(self.rules_text, json.dumps(rules, ensure_ascii=False, indent=2))

    def save_rules_form(self):
        culture = self.current_culture()
        if not culture:
            return

        try:
            min_length = int(self.rule_min_length_var.get().strip())
            max_length = int(self.rule_max_length_var.get().strip())
            max_repeat = int(self.rule_max_repeat_var.get().strip())
            if min_length < 1 or max_length < min_length or max_repeat < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("入力エラー", "minLength / maxLength / maxRepeat の値を見直してください")
            return

        forbidden_start = [x.strip() for x in self.rule_forbidden_start_var.get().split(",") if x.strip()]
        forbidden_end = [x.strip() for x in self.rule_forbidden_end_var.get().split(",") if x.strip()]

        rules = {
            "minLength": min_length,
            "maxLength": max_length,
            "maxRepeat": max_repeat,
            "forbiddenStart": forbidden_start,
            "forbiddenEnd": forbidden_end
        }

        culture["rules"] = rules
        self.set_text(self.rules_text, json.dumps(rules, ensure_ascii=False, indent=2))
        self.show_current_culture_json()
        self.set_status("ルールを保存しました")

    def apply_rules_json(self):
        culture = self.current_culture()
        if not culture:
            return
        try:
            rules = json.loads(self.get_text(self.rules_text))
        except Exception as e:
            messagebox.showerror("JSONエラー", f"rules JSONが壊れています\n\n{e}")
            return

        culture["rules"] = rules
        self.load_rules_to_form()
        self.show_current_culture_json()
        self.set_status("JSONからルールを上書きしました")

    # ---------- json ----------

    def show_current_culture_json(self):
        culture = self.current_culture()
        if not culture:
            return
        self.set_text(self.json_text, json.dumps(culture, ensure_ascii=False, indent=2))

    def apply_current_culture_json(self):
        if not self.current_culture_id:
            return
        try:
            culture = json.loads(self.get_text(self.json_text))
        except Exception as e:
            messagebox.showerror("JSONエラー", f"文化圏JSONが壊れています\n\n{e}")
            return

        upgraded_wrapper = upgrade_legacy_data({
            "version": self.data.get("version", 1),
            "cultures": {
                self.current_culture_id: culture
            }
        })
        self.data["cultures"][self.current_culture_id] = upgraded_wrapper["cultures"][self.current_culture_id]
        self.load_current_culture_to_ui()
        self.refresh_culture_list()
        self.set_status("JSONから文化圏を上書きしました")

    # ---------- test ----------

    def run_generate(self):
        cid = self.preview_culture_var.get().strip() or self.current_culture_id
        if not cid:
            return

        try:
            count = max(1, min(100, int(self.count_var.get())))
        except ValueError:
            messagebox.showwarning("入力エラー", "生成数は整数で入れてください")
            return

        names = generate_many(self.data, cid, count)
        self.result_text.delete("1.0", tk.END)
        for name in names:
            self.result_text.insert(tk.END, name + "\n")

        self.set_status(f"{len(names)}件生成しました")

    def run_frequency_test(self):
        cid = self.preview_culture_var.get().strip() or self.current_culture_id
        if not cid:
            return

        try:
            trials = max(1, min(100000, int(self.stats_trials_var.get())))
        except ValueError:
            messagebox.showwarning("入力エラー", "試行回数は整数で入れてください")
            return

        counter = simulate_frequency(self.data, cid, trials)
        self.stats_text.delete("1.0", tk.END)

        total = sum(counter.values())
        self.stats_text.insert(tk.END, f"文化圏: {cid}\n")
        self.stats_text.insert(tk.END, f"試行回数: {trials}\n")
        self.stats_text.insert(tk.END, f"有効生成数: {total}\n\n")

        for name, count in counter.most_common(50):
            rate = (count / total * 100) if total else 0.0
            self.stats_text.insert(tk.END, f"{name}\t{count}\t{rate:.2f}%\n")

        self.set_status(f"出現回数テストを実行しました ({trials}回)")

    # ---------- file ----------

    def new_data(self):
        if not messagebox.askyesno("確認", "現在の内容を捨てて新規作成しますか？"):
            return
        self.data = deep_copy(DEFAULT_DATA)
        self.current_file = None
        self.current_culture_id = None
        self.current_group_name = None
        self.refresh_culture_list()
        self.set_status("新規データを作成しました")

    def load_json(self):
        path = filedialog.askopenfilename(
            title="JSONを開く",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "cultures" not in data:
                raise ValueError("cultures がありません")

            data = upgrade_legacy_data(data)

        except Exception as e:
            messagebox.showerror("読込エラー", f"読み込みに失敗しました\n\n{e}")
            return

        self.data = data
        self.current_file = path
        self.current_culture_id = None
        self.current_group_name = None
        self.refresh_culture_list()
        self.set_status(f"読み込みました: {path}")

    def save_json(self):
        if not self.current_file:
            self.save_json_as()
            return

        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.set_status(f"保存しました: {self.current_file}")
        except Exception as e:
            messagebox.showerror("保存エラー", f"保存に失敗しました\n\n{e}")

    def save_json_as(self):
        path = filedialog.asksaveasfilename(
            title="JSONを保存",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        self.current_file = path
        self.save_json()


def main():
    root = tk.Tk()
    app = NameEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()