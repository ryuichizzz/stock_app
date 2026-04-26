import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox

# =========================
# Constants
# =========================
N, E, S, W = 1, 2, 4, 8
DIRS = {
    N: (0, -1),
    E: (1, 0),
    S: (0, 1),
    W: (-1, 0),
}
DIR_LABEL = {N: "N", E: "E", S: "S", W: "W"}
ARROW = {N: "↑", E: "→", S: "↓", W: "←"}
FACING_VALUES = [N, E, S, W]
FACING_LABELS = ["N", "E", "S", "W"]

TOOL_WALL = "wall"
TOOL_DOOR = "door"
TOOL_START = "start"
TOOL_TEX_WALL = "tex_wall"
TOOL_TEX_FLOOR = "tex_floor"
TOOL_TEX_CEIL = "tex_ceil"
TOOL_BILLBOARD = "billboard"

STATUS_BG = "#111111"
STATUS_FG = "#dddddd"
STATUS_CLICK_BG = "#2f4f8f"
STATUS_CLICK_FG = "#ffffff"
PANEL_BG = "#16161b"
BTN_BG = "#1f1f27"
BTN_ACTIVE = "#333344"
BTN_SELECTED = "#2a2a40"

WALL_TEX_PALETTE = [
    "#4aa3ff",
    "#5fd65f",
    "#ff6b6b",
    "#d38cff",
    "#ffd24a",
    "#4ae0d2",
    "#ff9f40",
    "#ff66cc",
]

TEXTURE_ROOT_DIR = "textures"
BILLBOARD_ROOT_DIR = "billboards"
TEXTURE_SET_FILENAME = "textureset.json"
BILLBOARD_SET_FILENAME = "billboardset.json"


# =========================
# Helpers
# =========================
def in_bounds(x, y, w, h):
    return 0 <= x < w and 0 <= y < h


def opposite_dir(d):
    return {N: S, S: N, E: W, W: E}[d]


def dir_to_key(d):
    return {N: "n", E: "e", S: "s", W: "w"}[d]


def key_to_dir(k):
    return {"n": N, "e": E, "s": S, "w": W}[k]


def deep_grid(h, w, value=0):
    return [[value for _ in range(w)] for __ in range(h)]


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def format_bool(v):
    return "true" if v else "false"


def parent_dir_of(filepath):
    if filepath:
        return os.path.dirname(os.path.abspath(filepath))
    return os.getcwd()


def join_if(root, *parts):
    return os.path.normpath(os.path.join(root, *parts))


# =========================
# Catalog helpers
# =========================
def default_texture_catalog(texture_set_name):
    return {
        "name": texture_set_name,
        "wall": [{"id": 0, "name": "wall_00", "file": "wall_00.png"}],
        "floor": [{"id": 0, "name": "floor_00", "file": "floor_00.png"}],
        "ceiling": [{"id": 0, "name": "ceiling_00", "file": "ceiling_00.png"}],
        "door": [{"id": 0, "name": "door_00", "file": "door_00.png"}],
        "corner": [{"id": 0, "name": "corner_00", "file": "corner_00.png"}],
    }


def default_billboard_catalog():
    return {
        "name": "default_billboards",
        "billboards": [{"id": 0, "name": "billboard_00", "file": "billboard_00.png"}],
    }


def normalize_catalog_entries(entries, default_prefix):
    out = []
    if not isinstance(entries, list):
        entries = []

    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            item = {}
        name = str(item.get("name", f"{default_prefix}_{idx:02d}") or f"{default_prefix}_{idx:02d}").strip()
        file_name = str(item.get("file", f"{default_prefix}_{idx:02d}.png") or f"{default_prefix}_{idx:02d}.png").strip()
        out.append({"id": idx, "name": name, "file": file_name})

    if not out:
        out.append({"id": 0, "name": f"{default_prefix}_00", "file": f"{default_prefix}_00.png"})

    return out


def ensure_category_has_zero(entries, default_prefix):
    entries = normalize_catalog_entries(entries, default_prefix)
    if not entries:
        entries = [{"id": 0, "name": f"{default_prefix}_00", "file": f"{default_prefix}_00.png"}]
    for idx, item in enumerate(entries):
        item["id"] = idx
    return entries


# =========================
# Model
# =========================
class MapData:
    def __init__(self, w, h):
        self.meta = {
            "id": "map01",
            "name": "New Map",
            "version": 2,
            "author": "ryuichi",
        }
        self.texture_set = "stone"
        self.render = {
            "wall_thickness": 0.18,
            "door_thickness": 0.18,
            "corner_filler_size": 0.16,
        }
        self.w = w
        self.h = h
        self.walls = deep_grid(h, w, 0)
        self.start = {"x": 0, "y": 0, "f": N}
        self.doors = []
        self.cell_textures = {
            "floor": deep_grid(h, w, 0),
            "ceiling": deep_grid(h, w, 0),
        }
        self.wall_face_textures = {
            "n": deep_grid(h, w, 0),
            "e": deep_grid(h, w, 0),
            "s": deep_grid(h, w, 0),
            "w": deep_grid(h, w, 0),
        }
        self.billboards = []

    def to_json(self):
        return {
            "meta": self.meta,
            "size": {"w": self.w, "h": self.h},
            "start": self.start,
            "texture_set": self.texture_set,
            "render": self.render,
            "walls": self.walls,
            "doors": self.doors,
            "cell_textures": self.cell_textures,
            "wall_face_textures": self.wall_face_textures,
            "billboards": self.billboards,
        }

    @staticmethod
    def from_json(data):
        w = max(1, safe_int(data.get("size", {}).get("w", 20), 20))
        h = max(1, safe_int(data.get("size", {}).get("h", 20), 20))
        m = MapData(w, h)

        meta = data.get("meta", {})
        if isinstance(meta, dict):
            m.meta.update(meta)

        m.texture_set = str(data.get("texture_set", "stone") or "stone")

        render = data.get("render", {})
        if isinstance(render, dict):
            m.render["wall_thickness"] = safe_float(render.get("wall_thickness", m.render["wall_thickness"]), m.render["wall_thickness"])
            m.render["door_thickness"] = safe_float(render.get("door_thickness", m.render["door_thickness"]), m.render["door_thickness"])
            m.render["corner_filler_size"] = safe_float(render.get("corner_filler_size", m.render["corner_filler_size"]), m.render["corner_filler_size"])

        m.walls = MapData._validate_wall_grid(data.get("walls"), w, h)
        m.start = MapData._validate_start(data.get("start", {}), w, h)
        m.doors = MapData._validate_doors(data.get("doors", []), w, h)

        cell_textures = data.get("cell_textures", {})
        if isinstance(cell_textures, dict):
            m.cell_textures["floor"] = MapData._validate_tex_grid(cell_textures.get("floor"), w, h, 0)
            m.cell_textures["ceiling"] = MapData._validate_tex_grid(cell_textures.get("ceiling"), w, h, 0)

        face_textures = data.get("wall_face_textures", {})
        if isinstance(face_textures, dict):
            for key in ("n", "e", "s", "w"):
                m.wall_face_textures[key] = MapData._validate_tex_grid(face_textures.get(key), w, h, 0)

        m.billboards = MapData._validate_billboards(data.get("billboards", []), w, h)
        return m

    @staticmethod
    def _validate_wall_grid(grid, w, h):
        out = deep_grid(h, w, 0)
        if not isinstance(grid, list):
            return out
        for y in range(min(h, len(grid))):
            if not isinstance(grid[y], list):
                continue
            for x in range(min(w, len(grid[y]))):
                out[y][x] = safe_int(grid[y][x], 0) & (N | E | S | W)
        return out

    @staticmethod
    def _validate_tex_grid(grid, w, h, default_value):
        out = deep_grid(h, w, default_value)
        if not isinstance(grid, list):
            return out
        for y in range(min(h, len(grid))):
            if not isinstance(grid[y], list):
                continue
            for x in range(min(w, len(grid[y]))):
                out[y][x] = max(0, safe_int(grid[y][x], default_value))
        return out

    @staticmethod
    def _validate_start(st, w, h):
        if not isinstance(st, dict):
            st = {}
        x = max(0, min(w - 1, safe_int(st.get("x", 0), 0)))
        y = max(0, min(h - 1, safe_int(st.get("y", 0), 0)))
        f = safe_int(st.get("f", N), N)
        if f not in FACING_VALUES:
            f = N
        return {"x": x, "y": y, "f": f}

    @staticmethod
    def _validate_doors(items, w, h):
        out = []
        seen = set()
        if not isinstance(items, list):
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            x = safe_int(item.get("x", 0), 0)
            y = safe_int(item.get("y", 0), 0)
            d = safe_int(item.get("d", N), N)
            tex = max(0, safe_int(item.get("tex", 0), 0))
            if not in_bounds(x, y, w, h):
                continue
            if d not in FACING_VALUES:
                continue
            key = (x, y, d)
            if key in seen:
                continue
            seen.add(key)
            door = {"x": x, "y": y, "d": d, "tex": tex}
            event_id = str(item.get("event", "") or "").strip()
            if event_id:
                door["event"] = event_id
            else:
                p = item.get("pass", {"type": "always"})
                if not isinstance(p, dict):
                    p = {"type": "always"}
                ptype = str(p.get("type", "always") or "always")
                if ptype not in ("always", "key", "flag"):
                    ptype = "always"
                if ptype == "key":
                    door["pass"] = {
                        "type": "key",
                        "key_id": str(p.get("key_id", "bronze_key") or "bronze_key"),
                        "consume": bool(p.get("consume", False)),
                    }
                elif ptype == "flag":
                    door["pass"] = {
                        "type": "flag",
                        "flag": str(p.get("flag", "boss_room_opened") or "boss_room_opened"),
                        "value": bool(p.get("value", True)),
                    }
                else:
                    door["pass"] = {"type": "always"}
            out.append(door)
        return out

    @staticmethod
    def _validate_billboards(items, w, h):
        out = []
        if not isinstance(items, list):
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            x = safe_int(item.get("x", 0), 0)
            y = safe_int(item.get("y", 0), 0)
            if not in_bounds(x, y, w, h):
                continue
            tex = max(0, safe_int(item.get("tex", 0), 0))
            offset_x = safe_float(item.get("offset_x", 0.5), 0.5)
            offset_y = safe_float(item.get("offset_y", 0.5), 0.5)
            width = max(0.01, safe_float(item.get("width", 0.78), 0.78))
            height = max(0.01, safe_float(item.get("height", 1.15), 1.15))
            mode = str(item.get("mode", "face_camera") or "face_camera")
            if mode not in ("face_camera", "fixed"):
                mode = "face_camera"
            f = safe_int(item.get("f", N), N)
            if f not in FACING_VALUES:
                f = N
            out.append({
                "x": x,
                "y": y,
                "tex": tex,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "width": width,
                "height": height,
                "mode": mode,
                "f": f,
            })
        return out


# =========================
# Catalog editors
# =========================
class TextureCatalogDialog(tk.Toplevel):
    CATEGORY_SPECS = {
        "wall": "wall",
        "floor": "floor",
        "ceiling": "ceiling",
        "door": "door",
        "corner": "corner",
    }

    def __init__(self, parent, textureset_path):
        super().__init__(parent)
        self.title("テクスチャセット管理")
        self.transient(parent)
        self.grab_set()
        self.configure(bg=PANEL_BG)
        self.geometry("820x520")

        self.textureset_path = textureset_path
        self.texture_dir = os.path.dirname(textureset_path)
        self.catalog = self.load_catalog()
        self.current_category = "wall"
        self.selected_index = None

        self._build_ui()
        self.refresh_category_list()
        self.refresh_tree()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def load_catalog(self):
        if os.path.exists(self.textureset_path):
            try:
                with open(self.textureset_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = str(data.get("name", os.path.basename(self.texture_dir)) or os.path.basename(self.texture_dir))
                out = {"name": name}
                for key, prefix in self.CATEGORY_SPECS.items():
                    out[key] = ensure_category_has_zero(data.get(key, []), prefix)
                return out
            except Exception as exc:
                messagebox.showwarning("Catalog Load", f"textureset.json の読み込みに失敗しました。\n{exc}")
        out = default_texture_catalog(os.path.basename(self.texture_dir))
        for key, prefix in self.CATEGORY_SPECS.items():
            out[key] = ensure_category_has_zero(out.get(key, []), prefix)
        return out

    def save_catalog(self):
        os.makedirs(self.texture_dir, exist_ok=True)
        with open(self.textureset_path, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, ensure_ascii=False, indent=2)

    def _build_ui(self):
        main = tk.Frame(self, bg=PANEL_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.Frame(main, bg=PANEL_BG, width=140)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        right = tk.Frame(main, bg=PANEL_BG)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(left, text="カテゴリ", bg=PANEL_BG, fg="#dddddd", anchor="w").pack(fill=tk.X, pady=(0, 6))
        self.category_listbox = tk.Listbox(left, exportselection=False)
        self.category_listbox.pack(fill=tk.BOTH, expand=True)
        self.category_listbox.bind("<<ListboxSelect>>", self.on_category_change)

        self.tree = ttk.Treeview(right, columns=("id", "name", "file"), show="headings", height=10)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="名前")
        self.tree.heading("file", text="ファイル")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("file", width=280, anchor="w")
        self.tree.pack(fill=tk.X)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        form = tk.Frame(right, bg=PANEL_BG)
        form.pack(fill=tk.X, pady=(12, 0))

        self.id_var = tk.StringVar(value="(auto)")
        self.name_var = tk.StringVar()
        self.file_var = tk.StringVar()

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="ID", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.id_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="名前", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.name_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="ファイル", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.file_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(row, text="参照...", command=self.browse_texture_file).pack(side=tk.LEFT, padx=(6, 0))

        btns = tk.Frame(right, bg=PANEL_BG)
        btns.pack(fill=tk.X, pady=(12, 0))
        tk.Button(btns, text="クリア", command=self.clear_form).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="追加", command=self.add_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="更新", command=self.update_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="削除", command=self.remove_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="閉じる", command=self.destroy).pack(side=tk.RIGHT)

        tk.Label(
            right,
            text="ID 0 は必須で削除不可です。新規追加時は自動採番されます。",
            bg=PANEL_BG,
            fg="#bbbbbb",
            anchor="w",
            justify="left",
        ).pack(fill=tk.X, pady=(10, 0))

    def refresh_category_list(self):
        self.category_listbox.delete(0, tk.END)
        for key in self.CATEGORY_SPECS:
            self.category_listbox.insert(tk.END, key)
        idx = list(self.CATEGORY_SPECS.keys()).index(self.current_category)
        self.category_listbox.selection_set(idx)

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for entry in self.catalog[self.current_category]:
            self.tree.insert("", tk.END, values=(entry["id"], entry["name"], entry["file"]))
        self.clear_form()

    def current_entries(self):
        return self.catalog[self.current_category]

    def on_category_change(self, _event=None):
        sel = self.category_listbox.curselection()
        if not sel:
            return
        self.current_category = list(self.CATEGORY_SPECS.keys())[sel[0]]
        self.selected_index = None
        self.refresh_tree()

    def on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        index = self.tree.index(sel[0])
        self.selected_index = index
        entry = self.current_entries()[index]
        self.id_var.set(str(entry["id"]))
        self.name_var.set(entry["name"])
        self.file_var.set(entry["file"])

    def clear_form(self):
        self.selected_index = None
        self.id_var.set("(auto)")
        self.name_var.set("")
        self.file_var.set("")
        for item in self.tree.selection():
            self.tree.selection_remove(item)

    def browse_texture_file(self):
        path = filedialog.askopenfilename(
            title="テクスチャファイルを選択",
            initialdir=self.texture_dir,
            filetypes=[("PNG", "*.png"), ("すべてのファイル", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            rel = os.path.relpath(path, self.texture_dir)
        except Exception:
            rel = os.path.basename(path)
        self.file_var.set(rel.replace("\\", "/"))

    def validate_form(self):
        name = self.name_var.get().strip()
        file_name = self.file_var.get().strip()
        if not name:
            messagebox.showwarning("カタログ", "名前を入力してください。", parent=self)
            return None, None
        if not file_name:
            messagebox.showwarning("カタログ", "ファイルを入力してください。", parent=self)
            return None, None
        names = [e["name"] for e in self.current_entries()]
        if self.selected_index is None:
            if name in names:
                messagebox.showwarning("カタログ", "同じ名前が既に存在します。", parent=self)
                return None, None
        else:
            current_name = self.current_entries()[self.selected_index]["name"]
            if name != current_name and name in names:
                messagebox.showwarning("カタログ", "同じ名前が既に存在します。", parent=self)
                return None, None
        return name, file_name

    def add_entry(self):
        name, file_name = self.validate_form()
        if name is None:
            return
        entries = self.current_entries()
        entries.append({"id": len(entries), "name": name, "file": file_name})
        self.save_catalog()
        self.refresh_tree()

    def update_entry(self):
        if self.selected_index is None:
            messagebox.showwarning("カタログ", "更新する項目を選択してください。", parent=self)
            return
        name, file_name = self.validate_form()
        if name is None:
            return
        self.current_entries()[self.selected_index]["name"] = name
        self.current_entries()[self.selected_index]["file"] = file_name
        self.save_catalog()
        self.refresh_tree()

    def remove_entry(self):
        if self.selected_index is None:
            messagebox.showwarning("カタログ", "削除する項目を選択してください。", parent=self)
            return
        if self.selected_index == 0:
            messagebox.showwarning("カタログ", "ID 0 は削除できません。", parent=self)
            return
        if not messagebox.askyesno("カタログ", "この項目を削除しますか？", parent=self):
            return
        entries = self.current_entries()
        entries.pop(self.selected_index)
        for idx, item in enumerate(entries):
            item["id"] = idx
        self.save_catalog()
        self.refresh_tree()


class BillboardCatalogDialog(tk.Toplevel):
    def __init__(self, parent, billboardset_path):
        super().__init__(parent)
        self.title("ビルボード管理")
        self.transient(parent)
        self.grab_set()
        self.configure(bg=PANEL_BG)
        self.geometry("700x480")

        self.billboardset_path = billboardset_path
        self.billboard_dir = os.path.dirname(billboardset_path)
        self.catalog = self.load_catalog()
        self.selected_index = None

        self._build_ui()
        self.refresh_tree()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def load_catalog(self):
        if os.path.exists(self.billboardset_path):
            try:
                with open(self.billboardset_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "name": str(data.get("name", "default_billboards") or "default_billboards"),
                    "billboards": ensure_category_has_zero(data.get("billboards", []), "billboard"),
                }
            except Exception as exc:
                messagebox.showwarning("Catalog Load", f"billboardset.json の読み込みに失敗しました。\n{exc}")
        return default_billboard_catalog()

    def save_catalog(self):
        os.makedirs(self.billboard_dir, exist_ok=True)
        with open(self.billboardset_path, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, ensure_ascii=False, indent=2)

    def _build_ui(self):
        main = tk.Frame(self, bg=PANEL_BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(main, columns=("id", "name", "file"), show="headings", height=10)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="名前")
        self.tree.heading("file", text="ファイル")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("file", width=320, anchor="w")
        self.tree.pack(fill=tk.X)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        form = tk.Frame(main, bg=PANEL_BG)
        form.pack(fill=tk.X, pady=(12, 0))

        self.id_var = tk.StringVar(value="(auto)")
        self.name_var = tk.StringVar()
        self.file_var = tk.StringVar()

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="ID", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.id_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="名前", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.name_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        row = tk.Frame(form, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="ファイル", width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        tk.Entry(row, textvariable=self.file_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(row, text="参照...", command=self.browse_file).pack(side=tk.LEFT, padx=(6, 0))

        btns = tk.Frame(main, bg=PANEL_BG)
        btns.pack(fill=tk.X, pady=(12, 0))
        tk.Button(btns, text="クリア", command=self.clear_form).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="追加", command=self.add_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="更新", command=self.update_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="削除", command=self.remove_entry).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btns, text="閉じる", command=self.destroy).pack(side=tk.RIGHT)

        tk.Label(
            main,
            text="ID 0 は必須で削除不可です。新規追加時は自動採番されます。",
            bg=PANEL_BG,
            fg="#bbbbbb",
            anchor="w",
            justify="left",
        ).pack(fill=tk.X, pady=(10, 0))

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for entry in self.catalog["billboards"]:
            self.tree.insert("", tk.END, values=(entry["id"], entry["name"], entry["file"]))
        self.clear_form()

    def clear_form(self):
        self.selected_index = None
        self.id_var.set("(auto)")
        self.name_var.set("")
        self.file_var.set("")
        for item in self.tree.selection():
            self.tree.selection_remove(item)

    def on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.selected_index = self.tree.index(sel[0])
        entry = self.catalog["billboards"][self.selected_index]
        self.id_var.set(str(entry["id"]))
        self.name_var.set(entry["name"])
        self.file_var.set(entry["file"])

    def browse_file(self):
        path = filedialog.askopenfilename(
            title="ビルボード画像を選択",
            initialdir=self.billboard_dir,
            filetypes=[("PNG", "*.png"), ("すべてのファイル", "*.*")],
            parent=self,
        )
        if not path:
            return
        try:
            rel = os.path.relpath(path, self.billboard_dir)
        except Exception:
            rel = os.path.basename(path)
        self.file_var.set(rel.replace("\\", "/"))

    def validate_form(self):
        name = self.name_var.get().strip()
        file_name = self.file_var.get().strip()
        if not name:
            messagebox.showwarning("カタログ", "名前を入力してください。", parent=self)
            return None, None
        if not file_name:
            messagebox.showwarning("カタログ", "ファイルを入力してください。", parent=self)
            return None, None
        names = [e["name"] for e in self.catalog["billboards"]]
        if self.selected_index is None:
            if name in names:
                messagebox.showwarning("カタログ", "同じ名前が既に存在します。", parent=self)
                return None, None
        else:
            current_name = self.catalog["billboards"][self.selected_index]["name"]
            if name != current_name and name in names:
                messagebox.showwarning("カタログ", "同じ名前が既に存在します。", parent=self)
                return None, None
        return name, file_name

    def add_entry(self):
        name, file_name = self.validate_form()
        if name is None:
            return
        entries = self.catalog["billboards"]
        entries.append({"id": len(entries), "name": name, "file": file_name})
        self.save_catalog()
        self.refresh_tree()

    def update_entry(self):
        if self.selected_index is None:
            messagebox.showwarning("カタログ", "更新する項目を選択してください。", parent=self)
            return
        name, file_name = self.validate_form()
        if name is None:
            return
        self.catalog["billboards"][self.selected_index]["name"] = name
        self.catalog["billboards"][self.selected_index]["file"] = file_name
        self.save_catalog()
        self.refresh_tree()

    def remove_entry(self):
        if self.selected_index is None:
            messagebox.showwarning("カタログ", "削除する項目を選択してください。", parent=self)
            return
        if self.selected_index == 0:
            messagebox.showwarning("カタログ", "ID 0 は削除できません。", parent=self)
            return
        if not messagebox.askyesno("カタログ", "この項目を削除しますか？", parent=self):
            return
        entries = self.catalog["billboards"]
        entries.pop(self.selected_index)
        for idx, item in enumerate(entries):
            item["id"] = idx
        self.save_catalog()
        self.refresh_tree()


# =========================
# Editor
# =========================
class MapEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Dungeon Map Editor v2")

        self.cell = 32
        self.margin = 12
        self.edge_snap = 8
        self.wall_width = 3
        self.wall_tex_line_width = 2
        self.right_panel_width = 360

        self.map = MapData(20, 20)
        self.current_path = None
        self.dirty = False

        self.current_tool = TOOL_WALL
        self.hover_cell = None
        self.hover_edge = None

        self.texture_catalog = default_texture_catalog(self.map.texture_set)
        self.billboard_catalog = default_billboard_catalog()

        self.wall_tex_paint = 0
        self.floor_tex_paint = 0
        self.ceil_tex_paint = 0
        self.door_settings = {
            "tex": 0,
            "event": "",
            "pass_type": "always",
            "key_id": "bronze_key",
            "consume": False,
            "flag": "boss_room_opened",
            "flag_value": True,
        }
        self.billboard_settings = {
            "tex": 0,
            "offset_x": 0.5,
            "offset_y": 0.5,
            "width": 0.78,
            "height": 1.15,
            "mode": "face_camera",
            "f": N,
        }

        self._build_ui()
        self._build_menubar()
        self._bind_keys()
        self._reload_catalogs()
        self._resize_canvas()
        self.refresh_tool_options()
        self.update_title()
        self.update_status()
        self.draw()

    # -------------------------
    # Paths / catalogs
    # -------------------------
    def project_base_dir(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def textures_dir(self):
        return join_if(self.project_base_dir(), TEXTURE_ROOT_DIR)

    def billboards_dir(self):
        return join_if(self.project_base_dir(), BILLBOARD_ROOT_DIR)

    def player_script_path(self):
        return join_if(os.path.dirname(os.path.abspath(__file__)), "map_player v2.py")

    def textureset_path(self):
        return join_if(self.textures_dir(), self.map.texture_set, TEXTURE_SET_FILENAME)

    def billboardset_path(self):
        return join_if(self.billboards_dir(), BILLBOARD_SET_FILENAME)

    def _reload_catalogs(self):
        self.texture_catalog = self.load_texture_catalog(self.map.texture_set)
        self.billboard_catalog = self.load_billboard_catalog()
        self._clamp_texture_indices()

    def load_texture_catalog(self, texture_set_name):
        path = join_if(self.textures_dir(), texture_set_name, TEXTURE_SET_FILENAME)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                out = {"name": str(data.get("name", texture_set_name) or texture_set_name)}
                out["wall"] = ensure_category_has_zero(data.get("wall", []), "wall")
                out["floor"] = ensure_category_has_zero(data.get("floor", []), "floor")
                out["ceiling"] = ensure_category_has_zero(data.get("ceiling", []), "ceiling")
                out["door"] = ensure_category_has_zero(data.get("door", []), "door")
                out["corner"] = ensure_category_has_zero(data.get("corner", []), "corner")
                return out
            except Exception as exc:
                messagebox.showwarning("Catalog", f"textureset.json の読み込みに失敗しました。\n{exc}")
        return default_texture_catalog(texture_set_name)

    def load_billboard_catalog(self):
        path = self.billboardset_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "name": str(data.get("name", "default_billboards") or "default_billboards"),
                    "billboards": ensure_category_has_zero(data.get("billboards", []), "billboard"),
                }
            except Exception as exc:
                messagebox.showwarning("Catalog", f"billboardset.json の読み込みに失敗しました。\n{exc}")
        return default_billboard_catalog()

    def _clamp_index_to_catalog(self, value, category):
        entries = self.texture_catalog.get(category, [])
        max_id = max(0, len(entries) - 1)
        return max(0, min(max_id, value))

    def _clamp_billboard_index(self, value):
        entries = self.billboard_catalog.get("billboards", [])
        max_id = max(0, len(entries) - 1)
        return max(0, min(max_id, value))

    def _clamp_texture_indices(self):
        for y in range(self.map.h):
            for x in range(self.map.w):
                self.map.cell_textures["floor"][y][x] = self._clamp_index_to_catalog(self.map.cell_textures["floor"][y][x], "floor")
                self.map.cell_textures["ceiling"][y][x] = self._clamp_index_to_catalog(self.map.cell_textures["ceiling"][y][x], "ceiling")
                for key in ("n", "e", "s", "w"):
                    self.map.wall_face_textures[key][y][x] = self._clamp_index_to_catalog(self.map.wall_face_textures[key][y][x], "wall")
        for door in self.map.doors:
            door["tex"] = self._clamp_index_to_catalog(door.get("tex", 0), "door")
        for b in self.map.billboards:
            b["tex"] = self._clamp_billboard_index(b.get("tex", 0))

        self.wall_tex_paint = self._clamp_index_to_catalog(self.wall_tex_paint, "wall")
        self.floor_tex_paint = self._clamp_index_to_catalog(self.floor_tex_paint, "floor")
        self.ceil_tex_paint = self._clamp_index_to_catalog(self.ceil_tex_paint, "ceiling")
        self.door_settings["tex"] = self._clamp_index_to_catalog(self.door_settings["tex"], "door")
        self.billboard_settings["tex"] = self._clamp_billboard_index(self.billboard_settings["tex"])

    def texture_choice_values(self, category):
        return [f"{item['id']}: {item['name']}" for item in self.texture_catalog.get(category, [])]

    def billboard_choice_values(self):
        return [f"{item['id']}: {item['name']}" for item in self.billboard_catalog.get("billboards", [])]

    def choice_from_id(self, category, tex_id):
        entries = self.texture_catalog.get(category, [])
        tex_id = self._clamp_index_to_catalog(tex_id, category)
        if not entries:
            return "0: (none)"
        return f"{tex_id}: {entries[tex_id]['name']}"

    def billboard_choice_from_id(self, tex_id):
        entries = self.billboard_catalog.get("billboards", [])
        tex_id = self._clamp_billboard_index(tex_id)
        if not entries:
            return "0: (none)"
        return f"{tex_id}: {entries[tex_id]['name']}"

    def id_from_choice(self, value, default=0):
        if not value:
            return default
        try:
            return max(0, int(str(value).split(":", 1)[0].strip()))
        except Exception:
            return default

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self):
        self.root.configure(bg=STATUS_BG)

        main = tk.Frame(self.root, bg=STATUS_BG)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main, bg="black", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.right_panel = tk.Frame(main, bg=PANEL_BG, width=self.right_panel_width)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_panel.pack_propagate(False)

        self._section_label(self.right_panel, "ツール")
        self.tool_buttons = {}
        for label, tool in [
            ("壁 (1)", TOOL_WALL),
            ("扉 (2)", TOOL_DOOR),
            ("開始地点 (3)", TOOL_START),
            ("壁テクスチャ (4)", TOOL_TEX_WALL),
            ("床テクスチャ (5)", TOOL_TEX_FLOOR),
            ("天井テクスチャ (6)", TOOL_TEX_CEIL),
            ("ビルボード (7)", TOOL_BILLBOARD),
        ]:
            self._add_tool_button(self.right_panel, label, tool)

        self._section_label(self.right_panel, "ツール設定")
        self.tool_options_frame = tk.Frame(self.right_panel, bg=PANEL_BG)
        self.tool_options_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        self._section_label(self.right_panel, "ヒント")
        self.hint_label = tk.Label(
            self.right_panel,
            text="",
            justify="left",
            anchor="w",
            bg=PANEL_BG,
            fg="#bbbbbb",
        )
        self.hint_label.pack(fill=tk.X, padx=10, pady=6)

        self.status_frame = tk.Frame(self.root, bg=STATUS_BG)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_main_label = tk.Label(
            self.status_frame,
            text="",
            anchor="w",
            bg=STATUS_BG,
            fg=STATUS_FG,
            padx=8,
            pady=6,
        )
        self.status_main_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_click_label = tk.Label(
            self.status_frame,
            text="マップ情報 | 描画設定",
            anchor="e",
            bg=STATUS_CLICK_BG,
            fg=STATUS_CLICK_FG,
            padx=8,
            pady=6,
            cursor="hand2",
        )
        self.status_click_label.pack(side=tk.RIGHT)
        self.status_click_label.bind("<Button-1>", self.on_status_click)

        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

    def _build_menubar(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="新規作成", command=self.new_map)
        file_menu.add_command(label="開く", command=self.load_map)
        file_menu.add_command(label="保存", command=self.save_map)
        file_menu.add_command(label="名前を付けて保存", command=self.save_map_as)
        file_menu.add_separator()
        file_menu.add_command(label="プレビュー", command=self.open_preview)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.on_exit)
        menubar.add_cascade(label="ファイル", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="マップ情報...", command=self.open_meta_dialog)
        edit_menu.add_command(label="描画設定...", command=self.open_render_dialog)
        edit_menu.add_separator()
        edit_menu.add_command(label="テクスチャセット管理...", command=self.open_texture_catalog_dialog)
        edit_menu.add_command(label="ビルボード管理...", command=self.open_billboard_catalog_dialog)
        menubar.add_cascade(label="編集", menu=edit_menu)

        self.root.config(menu=menubar)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg=PANEL_BG, fg="#aaaaaa", anchor="w").pack(
            fill=tk.X, padx=10, pady=(10, 4)
        )

    def _add_tool_button(self, parent, text, tool_name):
        btn = tk.Button(
            parent,
            text=text,
            command=lambda t=tool_name: self.set_tool(t),
            relief="flat",
            bg=BTN_BG,
            fg="white",
            activebackground=BTN_ACTIVE,
            activeforeground="white",
        )
        btn.pack(fill=tk.X, padx=10, pady=2)
        self.tool_buttons[tool_name] = btn

    def _entry_row(self, parent, label, var, width=16):
        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        entry = tk.Entry(row, textvariable=var, width=width)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _combo_row(self, parent, label, var, values):
        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        combo = ttk.Combobox(row, state="readonly", textvariable=var, values=values)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return combo

    def _checkbox_row(self, parent, label, var):
        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=label, width=12, anchor="w", bg=PANEL_BG, fg="#dddddd").pack(side=tk.LEFT)
        chk = tk.Checkbutton(
            row,
            variable=var,
            bg=PANEL_BG,
            fg="white",
            selectcolor="#303040",
            activebackground=PANEL_BG,
        )
        chk.pack(side=tk.LEFT)
        return chk

    def _bind_keys(self):
        self.root.bind("1", lambda e: self.set_tool(TOOL_WALL))
        self.root.bind("2", lambda e: self.set_tool(TOOL_DOOR))
        self.root.bind("3", lambda e: self.set_tool(TOOL_START))
        self.root.bind("4", lambda e: self.set_tool(TOOL_TEX_WALL))
        self.root.bind("5", lambda e: self.set_tool(TOOL_TEX_FLOOR))
        self.root.bind("6", lambda e: self.set_tool(TOOL_TEX_CEIL))
        self.root.bind("7", lambda e: self.set_tool(TOOL_BILLBOARD))
        self.root.bind("q", lambda e: self.rotate_start(-1))
        self.root.bind("Q", lambda e: self.rotate_start(-1))
        self.root.bind("e", lambda e: self.rotate_start(1))
        self.root.bind("E", lambda e: self.rotate_start(1))
        self.root.bind("<Control-n>", lambda e: self.new_map())
        self.root.bind("<Control-o>", lambda e: self.load_map())
        self.root.bind("<Control-s>", lambda e: self.save_map())
        self.root.bind("<Control-S>", lambda e: self.save_map_as())
        self.root.bind("<Control-p>", lambda e: self.open_preview())
        self.root.bind("<Control-P>", lambda e: self.open_preview())

    # -------------------------
    # Tool options
    # -------------------------
    def _clear_tool_options(self):
        for child in self.tool_options_frame.winfo_children():
            child.destroy()

    def refresh_tool_options(self):
        self._clear_tool_options()
        hint = ""

        if self.current_tool == TOOL_WALL:
            hint = "辺をクリック: 壁を配置\n右クリック: 壁を削除"
            tk.Label(self.tool_options_frame, text="このツールに追加設定はありません", anchor="w", bg=PANEL_BG, fg="#bbbbbb").pack(fill=tk.X)

        elif self.current_tool == TOOL_DOOR:
            hint = "辺をクリック: 扉を配置\n右クリック: 扉を削除"
            self.door_tex_var = tk.StringVar(value=self.choice_from_id("door", self.door_settings["tex"]))
            self.door_event_var = tk.StringVar(value=self.door_settings["event"])
            self.door_pass_type_var = tk.StringVar(value=self.door_settings["pass_type"])
            self.door_key_id_var = tk.StringVar(value=self.door_settings["key_id"])
            self.door_consume_var = tk.BooleanVar(value=self.door_settings["consume"])
            self.door_flag_var = tk.StringVar(value=self.door_settings["flag"])
            self.door_flag_value_var = tk.StringVar(value=format_bool(self.door_settings["flag_value"]))

            combo = self._combo_row(self.tool_options_frame, "扉テクスチャ", self.door_tex_var, self.texture_choice_values("door"))
            combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_door_options())
            e1 = self._entry_row(self.tool_options_frame, "イベントID", self.door_event_var)
            e2 = self._entry_row(self.tool_options_frame, "鍵ID", self.door_key_id_var)
            e3 = self._entry_row(self.tool_options_frame, "フラグ名", self.door_flag_var)
            pass_combo = self._combo_row(self.tool_options_frame, "通行条件", self.door_pass_type_var, ["always", "key", "flag"])
            pass_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_door_options())
            chk = self._checkbox_row(self.tool_options_frame, "鍵を消費", self.door_consume_var)
            chk.configure(command=self.apply_door_options)
            flag_combo = self._combo_row(self.tool_options_frame, "フラグ値", self.door_flag_value_var, ["true", "false"])
            flag_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_door_options())
            for entry in (e1, e2, e3):
                self._bind_entry_apply(entry, self.apply_door_options)
            tk.Label(
                self.tool_options_frame,
                text="Event ID がある場合、Pass設定は無視されます。",
                anchor="w",
                justify="left",
                bg=PANEL_BG,
                fg="#bbbbbb",
            ).pack(fill=tk.X, pady=(4, 0))

        elif self.current_tool == TOOL_START:
            hint = "セルをクリック: 開始地点を配置\nQ / E: 向きを回転"
            tk.Label(self.tool_options_frame, text="このツールに追加設定はありません", anchor="w", bg=PANEL_BG, fg="#bbbbbb").pack(fill=tk.X)

        elif self.current_tool == TOOL_TEX_WALL:
            hint = "辺をクリック: 壁面テクスチャを設定\n右クリック: 0に戻す"
            self.wall_tex_var = tk.StringVar(value=self.choice_from_id("wall", self.wall_tex_paint))
            combo = self._combo_row(self.tool_options_frame, "壁テクスチャ", self.wall_tex_var, self.texture_choice_values("wall"))
            combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_wall_tex_option())

        elif self.current_tool == TOOL_TEX_FLOOR:
            hint = "セルをクリック: 床テクスチャを設定\n右クリック: 0に戻す"
            self.floor_tex_var = tk.StringVar(value=self.choice_from_id("floor", self.floor_tex_paint))
            combo = self._combo_row(self.tool_options_frame, "床テクスチャ", self.floor_tex_var, self.texture_choice_values("floor"))
            combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_floor_tex_option())

        elif self.current_tool == TOOL_TEX_CEIL:
            hint = "セルをクリック: 天井テクスチャを設定\n右クリック: 0に戻す"
            self.ceil_tex_var = tk.StringVar(value=self.choice_from_id("ceiling", self.ceil_tex_paint))
            combo = self._combo_row(self.tool_options_frame, "天井テクスチャ", self.ceil_tex_var, self.texture_choice_values("ceiling"))
            combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_ceil_tex_option())

        elif self.current_tool == TOOL_BILLBOARD:
            hint = "セルをクリック: ビルボードを配置 / 上書き\n右クリック: ビルボードを削除"
            self.bb_tex_var = tk.StringVar(value=self.billboard_choice_from_id(self.billboard_settings["tex"]))
            self.bb_offset_x_var = tk.StringVar(value=str(self.billboard_settings["offset_x"]))
            self.bb_offset_y_var = tk.StringVar(value=str(self.billboard_settings["offset_y"]))
            self.bb_width_var = tk.StringVar(value=str(self.billboard_settings["width"]))
            self.bb_height_var = tk.StringVar(value=str(self.billboard_settings["height"]))
            self.bb_mode_var = tk.StringVar(value=self.billboard_settings["mode"])
            self.bb_facing_var = tk.StringVar(value=DIR_LABEL[self.billboard_settings["f"]])

            tex_combo = self._combo_row(self.tool_options_frame, "ビルボード", self.bb_tex_var, self.billboard_choice_values())
            tex_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_billboard_options())
            ex = self._entry_row(self.tool_options_frame, "Xオフセット", self.bb_offset_x_var)
            ey = self._entry_row(self.tool_options_frame, "Yオフセット", self.bb_offset_y_var)
            ew = self._entry_row(self.tool_options_frame, "幅", self.bb_width_var)
            eh = self._entry_row(self.tool_options_frame, "高さ", self.bb_height_var)
            for entry in (ex, ey, ew, eh):
                self._bind_entry_apply(entry, self.apply_billboard_options)
            mode_combo = self._combo_row(self.tool_options_frame, "表示モード", self.bb_mode_var, ["face_camera", "fixed"])
            facing_combo = self._combo_row(self.tool_options_frame, "向き", self.bb_facing_var, FACING_LABELS)
            mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_billboard_options())
            facing_combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_billboard_options())

        self.hint_label.config(text=hint)
        self.update_tool_button_states()

    def _bind_entry_apply(self, entry, callback):
        entry.bind("<Return>", lambda _e: callback())
        entry.bind("<FocusOut>", lambda _e: callback())

    def apply_wall_tex_option(self):
        self.wall_tex_paint = self._clamp_index_to_catalog(self.id_from_choice(self.wall_tex_var.get(), self.wall_tex_paint), "wall")
        self.wall_tex_var.set(self.choice_from_id("wall", self.wall_tex_paint))
        self.update_status()
        self.draw()

    def apply_floor_tex_option(self):
        self.floor_tex_paint = self._clamp_index_to_catalog(self.id_from_choice(self.floor_tex_var.get(), self.floor_tex_paint), "floor")
        self.floor_tex_var.set(self.choice_from_id("floor", self.floor_tex_paint))
        self.update_status()
        self.draw()

    def apply_ceil_tex_option(self):
        self.ceil_tex_paint = self._clamp_index_to_catalog(self.id_from_choice(self.ceil_tex_var.get(), self.ceil_tex_paint), "ceiling")
        self.ceil_tex_var.set(self.choice_from_id("ceiling", self.ceil_tex_paint))
        self.update_status()
        self.draw()

    def apply_door_options(self):
        ptype = self.door_pass_type_var.get().strip()
        if ptype not in ("always", "key", "flag"):
            ptype = "always"
        self.door_settings.update({
            "tex": self._clamp_index_to_catalog(self.id_from_choice(self.door_tex_var.get(), self.door_settings["tex"]), "door"),
            "event": self.door_event_var.get().strip(),
            "pass_type": ptype,
            "key_id": self.door_key_id_var.get().strip() or "bronze_key",
            "consume": bool(self.door_consume_var.get()),
            "flag": self.door_flag_var.get().strip() or "boss_room_opened",
            "flag_value": self.door_flag_value_var.get().strip().lower() != "false",
        })
        self.door_tex_var.set(self.choice_from_id("door", self.door_settings["tex"]))
        self.update_status()

    def apply_billboard_options(self):
        tex = self._clamp_billboard_index(self.id_from_choice(self.bb_tex_var.get(), self.billboard_settings["tex"]))
        ox = safe_float(self.bb_offset_x_var.get(), self.billboard_settings["offset_x"])
        oy = safe_float(self.bb_offset_y_var.get(), self.billboard_settings["offset_y"])
        width = safe_float(self.bb_width_var.get(), self.billboard_settings["width"])
        height = safe_float(self.bb_height_var.get(), self.billboard_settings["height"])
        if not (0.0 <= ox <= 1.0 and 0.0 <= oy <= 1.0 and width > 0.0 and height > 0.0):
            messagebox.showwarning("Invalid Value", "Offset は 0.0〜1.0、Width/Height は正の数値にしてください。")
            self.bb_offset_x_var.set(str(self.billboard_settings["offset_x"]))
            self.bb_offset_y_var.set(str(self.billboard_settings["offset_y"]))
            self.bb_width_var.set(str(self.billboard_settings["width"]))
            self.bb_height_var.set(str(self.billboard_settings["height"]))
            return
        mode = self.bb_mode_var.get().strip()
        if mode not in ("face_camera", "fixed"):
            mode = "face_camera"
        f = key_to_dir(self.bb_facing_var.get().strip().lower()) if self.bb_facing_var.get().strip().lower() in ("n", "e", "s", "w") else N
        self.billboard_settings.update({
            "tex": tex,
            "offset_x": ox,
            "offset_y": oy,
            "width": width,
            "height": height,
            "mode": mode,
            "f": f,
        })
        self.bb_tex_var.set(self.billboard_choice_from_id(self.billboard_settings["tex"]))
        self.update_status()

    # -------------------------
    # Lifecycle / file ops
    # -------------------------
    def update_title(self):
        suffix = " *" if self.dirty else ""
        name = self.current_path if self.current_path else "(未保存)"
        self.root.title(f"ダンジョンマップエディタ v2 - {name}{suffix}")

    def mark_dirty(self, value=True):
        self.dirty = value
        self.update_title()
        self.update_status()

    def confirm_discard_if_dirty(self):
        if not self.dirty:
            return True
        return messagebox.askyesno("未保存の変更", "未保存の変更があります。破棄して続行しますか？")

    def on_exit(self):
        if self.confirm_discard_if_dirty():
            self.root.destroy()

    def new_map(self):
        if not self.confirm_discard_if_dirty():
            return
        w = simpledialog.askinteger("新規マップ", "マップの横幅", initialvalue=20, minvalue=1)
        if w is None:
            return
        h = simpledialog.askinteger("新規マップ", "マップの高さ", initialvalue=20, minvalue=1)
        if h is None:
            return
        self.map = MapData(w, h)
        self.current_path = None
        self.hover_cell = None
        self.hover_edge = None
        self._reload_catalogs()
        self.refresh_tool_options()
        self.mark_dirty(False)
        self._resize_canvas()
        self.draw()

    def _write_map_file(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.map.to_json(), f, ensure_ascii=False, indent=2)

    def _save_current_map(self, show_message=True):
        if not self.current_path:
            return self.save_map_as(show_message=show_message)
        self._write_map_file(self.current_path)
        self.mark_dirty(False)
        if show_message:
            messagebox.showinfo("保存", "保存しました。")
        return True

    def save_map(self, show_message=True):
        return self._save_current_map(show_message=show_message)

    def save_map_as(self, show_message=True):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return False
        self.current_path = path
        self._reload_catalogs()
        self.refresh_tool_options()
        self._write_map_file(self.current_path)
        self.mark_dirty(False)
        if show_message:
            messagebox.showinfo("保存", "保存しました。")
        return True

    def open_preview(self):
        if not self.save_map(show_message=False):
            return False

        player_script = self.player_script_path()
        if not os.path.exists(player_script):
            messagebox.showerror("プレビュー", f"プレビュープレイヤーが見つかりません。\n{player_script}")
            return False

        try:
            subprocess.Popen(
                [sys.executable, player_script, self.current_path],
                cwd=self.project_base_dir(),
            )
        except Exception as exc:
            messagebox.showerror("プレビュー", f"プレビューの起動に失敗しました。\n{exc}")
            return False

        self.update_status()
        return True

    def load_map(self):
        if not self.confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.current_path = path
        self.map = MapData.from_json(data)
        self.hover_cell = None
        self.hover_edge = None
        self._reload_catalogs()
        self.refresh_tool_options()
        self.mark_dirty(False)
        self._resize_canvas()
        self.draw()

    # -------------------------
    # Geometry / hit test
    # -------------------------
    def _resize_canvas(self):
        w_px = self.margin * 2 + self.map.w * self.cell
        h_px = self.margin * 2 + self.map.h * self.cell
        self.canvas.config(width=w_px, height=h_px)

    def cell_rect(self, x, y):
        x0 = self.margin + x * self.cell
        y0 = self.margin + y * self.cell
        return x0, y0, x0 + self.cell, y0 + self.cell

    def screen_to_cell(self, px, py):
        x = int((px - self.margin) // self.cell)
        y = int((py - self.margin) // self.cell)
        if not in_bounds(x, y, self.map.w, self.map.h):
            return None
        return x, y

    def hit_test(self, px, py):
        cell = self.screen_to_cell(px, py)
        if cell is None:
            return None, None
        x, y = cell
        x0, y0, _, _ = self.cell_rect(x, y)
        lx = px - x0
        ly = py - y0
        dist = [
            (ly, N),
            (self.cell - lx, E),
            (self.cell - ly, S),
            (lx, W),
        ]
        dist.sort(key=lambda t: t[0])
        if dist[0][0] <= self.edge_snap:
            return "edge", (x, y, dist[0][1])
        return "cell", (x, y)

    # -------------------------
    # Input
    # -------------------------
    def set_tool(self, tool_name):
        self.current_tool = tool_name
        self.refresh_tool_options()
        self.update_status()
        self.draw()

    def update_tool_button_states(self):
        for tool_name, btn in self.tool_buttons.items():
            btn.config(bg=BTN_SELECTED if tool_name == self.current_tool else BTN_BG)

    def rotate_start(self, sign):
        if self.current_tool != TOOL_START:
            return
        f = self.map.start["f"]
        self.map.start["f"] = {N: E, E: S, S: W, W: N}[f] if sign > 0 else {N: W, W: S, S: E, E: N}[f]
        self.mark_dirty(True)
        self.draw()

    def on_mouse_move(self, event):
        kind, target = self.hit_test(event.x, event.y)
        self.hover_cell = target if kind == "cell" else None
        self.hover_edge = target if kind == "edge" else None
        self.update_status()
        self.draw()

    def on_mouse_leave(self, _event):
        self.hover_cell = None
        self.hover_edge = None
        self.update_status()
        self.draw()

    def on_left_click(self, event):
        self.apply_click(event.x, event.y, erase=False)

    def on_right_click(self, event):
        self.apply_click(event.x, event.y, erase=True)

    def on_status_click(self, event):
        width = self.status_click_label.winfo_width()
        if width <= 0:
            return
        if event.x < width * 0.5:
            self.open_meta_dialog()
        else:
            self.open_render_dialog()

    # -------------------------
    # Editing
    # -------------------------
    def apply_click(self, px, py, erase=False):
        kind, target = self.hit_test(px, py)
        if target is None:
            return

        changed = False
        if self.current_tool == TOOL_WALL and kind == "edge":
            changed = self.edit_wall(target, erase)
        elif self.current_tool == TOOL_DOOR and kind == "edge":
            changed = self.edit_door(target, erase)
        elif self.current_tool == TOOL_START and kind == "cell" and not erase:
            self.map.start["x"], self.map.start["y"] = target
            changed = True
        elif self.current_tool == TOOL_TEX_WALL and kind == "edge":
            changed = self.edit_wall_face_texture(target, erase)
        elif self.current_tool == TOOL_TEX_FLOOR and kind == "cell":
            changed = self.edit_cell_texture("floor", target, erase)
        elif self.current_tool == TOOL_TEX_CEIL and kind == "cell":
            changed = self.edit_cell_texture("ceiling", target, erase)
        elif self.current_tool == TOOL_BILLBOARD and kind == "cell":
            changed = self.edit_billboard(target, erase)

        if changed:
            self.mark_dirty(True)
            self.draw()

    def set_wall_edge(self, x, y, d, value):
        if not in_bounds(x, y, self.map.w, self.map.h):
            return
        if value:
            self.map.walls[y][x] |= d
        else:
            self.map.walls[y][x] &= ~d
        dx, dy = DIRS[d]
        nx, ny = x + dx, y + dy
        od = opposite_dir(d)
        if in_bounds(nx, ny, self.map.w, self.map.h):
            if value:
                self.map.walls[ny][nx] |= od
            else:
                self.map.walls[ny][nx] &= ~od

    def edge_matches_door(self, door, x, y, d):
        if (door["x"], door["y"], door["d"]) == (x, y, d):
            return True
        dx, dy = DIRS[d]
        nx, ny = x + dx, y + dy
        if in_bounds(nx, ny, self.map.w, self.map.h):
            return (door["x"], door["y"], door["d"]) == (nx, ny, opposite_dir(d))
        return False

    def find_door_at_edge(self, x, y, d):
        for i, door in enumerate(self.map.doors):
            if self.edge_matches_door(door, x, y, d):
                return i
        return None

    def edit_wall(self, edge, erase=False):
        x, y, d = edge
        before = self.map.walls[y][x]
        self.set_wall_edge(x, y, d, not erase)
        changed = before != self.map.walls[y][x]
        if not erase:
            idx = self.find_door_at_edge(x, y, d)
            if idx is not None:
                self.map.doors.pop(idx)
                changed = True
        return changed

    def build_current_pass(self):
        ptype = self.door_settings["pass_type"]
        if ptype == "key":
            return {
                "type": "key",
                "key_id": self.door_settings["key_id"].strip() or "bronze_key",
                "consume": bool(self.door_settings["consume"]),
            }
        if ptype == "flag":
            return {
                "type": "flag",
                "flag": self.door_settings["flag"].strip() or "boss_room_opened",
                "value": bool(self.door_settings["flag_value"]),
            }
        return {"type": "always"}

    def edit_door(self, edge, erase=False):
        x, y, d = edge
        idx = self.find_door_at_edge(x, y, d)
        if erase:
            if idx is not None:
                self.map.doors.pop(idx)
                return True
            return False
        self.set_wall_edge(x, y, d, False)
        door = {"x": x, "y": y, "d": d, "tex": int(self.door_settings["tex"])}
        event_id = self.door_settings["event"].strip()
        if event_id:
            door["event"] = event_id
        else:
            door["pass"] = self.build_current_pass()
        if idx is None:
            self.map.doors.append(door)
        else:
            self.map.doors[idx] = door
        return True

    def edit_cell_texture(self, kind, cell, erase=False):
        x, y = cell
        current = self.map.cell_textures[kind][y][x]
        if erase:
            self.map.cell_textures[kind][y][x] = 0
        else:
            self.map.cell_textures[kind][y][x] = int(self.floor_tex_paint if kind == "floor" else self.ceil_tex_paint)
        return current != self.map.cell_textures[kind][y][x]

    def edit_wall_face_texture(self, edge, erase=False):
        x, y, d = edge
        key = dir_to_key(d)
        current = self.map.wall_face_textures[key][y][x]
        self.map.wall_face_textures[key][y][x] = 0 if erase else int(self.wall_tex_paint)
        return current != self.map.wall_face_textures[key][y][x]

    def find_billboard_in_cell(self, x, y):
        for i, item in enumerate(self.map.billboards):
            if item["x"] == x and item["y"] == y:
                return i
        return None

    def edit_billboard(self, cell, erase=False):
        x, y = cell
        idx = self.find_billboard_in_cell(x, y)
        if erase:
            if idx is not None:
                self.map.billboards.pop(idx)
                return True
            return False
        item = {
            "x": x,
            "y": y,
            "tex": int(self.billboard_settings["tex"]),
            "offset_x": float(self.billboard_settings["offset_x"]),
            "offset_y": float(self.billboard_settings["offset_y"]),
            "width": float(self.billboard_settings["width"]),
            "height": float(self.billboard_settings["height"]),
            "mode": self.billboard_settings["mode"],
            "f": int(self.billboard_settings["f"]),
        }
        if idx is None:
            self.map.billboards.append(item)
        else:
            self.map.billboards[idx] = item
        return True

    # -------------------------
    # Meta / render dialogs
    # -------------------------
    def open_meta_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Map Meta")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=PANEL_BG)

        map_id_var = tk.StringVar(value=self.map.meta["id"])
        map_name_var = tk.StringVar(value=self.map.meta["name"])
        author_var = tk.StringVar(value=self.map.meta.get("author", ""))
        texture_set_var = tk.StringVar(value=self.map.texture_set)

        self._entry_row(win, "Map ID", map_id_var)
        self._entry_row(win, "Map Name", map_name_var)
        self._entry_row(win, "Author", author_var)
        self._entry_row(win, "Texture Set", texture_set_var)

        def apply_and_close():
            old_set = self.map.texture_set
            self.map.meta["id"] = map_id_var.get().strip() or "map01"
            self.map.meta["name"] = map_name_var.get().strip() or "New Map"
            self.map.meta["author"] = author_var.get().strip() or "ryuichi"
            self.map.texture_set = texture_set_var.get().strip() or "stone"
            if self.map.texture_set != old_set:
                self._reload_catalogs()
                self.refresh_tool_options()
            self.mark_dirty(True)
            self.draw()
            win.destroy()

        tk.Button(win, text="OK", command=apply_and_close).pack(pady=(8, 10))

    def open_render_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Render Settings")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=PANEL_BG)

        wall_var = tk.StringVar(value=str(self.map.render["wall_thickness"]))
        door_var = tk.StringVar(value=str(self.map.render["door_thickness"]))
        corner_var = tk.StringVar(value=str(self.map.render["corner_filler_size"]))

        self._entry_row(win, "Wall Thick", wall_var)
        self._entry_row(win, "Door Thick", door_var)
        self._entry_row(win, "Corner Size", corner_var)

        def apply_and_close():
            wall = safe_float(wall_var.get(), self.map.render["wall_thickness"])
            door = safe_float(door_var.get(), self.map.render["door_thickness"])
            corner = safe_float(corner_var.get(), self.map.render["corner_filler_size"])
            if not (0.01 <= wall <= 1.0 and 0.01 <= door <= 1.0 and 0.01 <= corner <= 1.0):
                messagebox.showwarning("Invalid Value", "Render値は 0.01〜1.0 の数値にしてください。")
                return
            self.map.render["wall_thickness"] = wall
            self.map.render["door_thickness"] = door
            self.map.render["corner_filler_size"] = corner
            self.mark_dirty(True)
            win.destroy()

        tk.Button(win, text="OK", command=apply_and_close).pack(pady=(8, 10))

    def open_texture_catalog_dialog(self):
        dlg = TextureCatalogDialog(self.root, self.textureset_path())
        self.root.wait_window(dlg)
        self._reload_catalogs()
        self.refresh_tool_options()
        self.update_status()
        self.draw()

    def open_billboard_catalog_dialog(self):
        dlg = BillboardCatalogDialog(self.root, self.billboardset_path())
        self.root.wait_window(dlg)
        self._reload_catalogs()
        self.refresh_tool_options()
        self.update_status()
        self.draw()

    # -------------------------
    # Drawing
    # -------------------------
    def draw(self):
        self.canvas.delete("all")
        base_palette = ["#0b0b0e", "#10161c", "#122014", "#1d0f0f", "#111826", "#241b12"]

        for y in range(self.map.h):
            for x in range(self.map.w):
                x0, y0, x1, y1 = self.cell_rect(x, y)
                floor_id = self.map.cell_textures["floor"][y][x]
                fill = base_palette[floor_id % len(base_palette)]
                self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#1a1a22")

        for y in range(self.map.h):
            for x in range(self.map.w):
                x0, y0, _, _ = self.cell_rect(x, y)
                floor_id = self.map.cell_textures["floor"][y][x]
                ceil_id = self.map.cell_textures["ceiling"][y][x]
                self.canvas.create_text(x0 + 5, y0 + 4, anchor="nw", text=f"F{floor_id}", fill="#6ea0ff", font=("Consolas", 8))
                self.canvas.create_text(x0 + 5, y0 + 13, anchor="nw", text=f"C{ceil_id}", fill="#bbbbbb", font=("Consolas", 8))

        if self.current_tool == TOOL_TEX_WALL:
            self.draw_wall_face_overlay()

        for y in range(self.map.h):
            for x in range(self.map.w):
                x0, y0, x1, y1 = self.cell_rect(x, y)
                v = self.map.walls[y][x]
                if v & N:
                    self.canvas.create_line(x0, y0, x1, y0, fill="white", width=self.wall_width)
                if v & E:
                    self.canvas.create_line(x1, y0, x1, y1, fill="white", width=self.wall_width)
                if v & S:
                    self.canvas.create_line(x0, y1, x1, y1, fill="white", width=self.wall_width)
                if v & W:
                    self.canvas.create_line(x0, y0, x0, y1, fill="white", width=self.wall_width)

        for door in self.map.doors:
            color = "#f6d04d"
            if "event" in door:
                color = "#ff88cc"
            else:
                ptype = door.get("pass", {"type": "always"}).get("type", "always")
                if ptype == "key":
                    color = "#6cf0ff"
                elif ptype == "flag":
                    color = "#ff88aa"
            self.draw_edge_marker(door["x"], door["y"], door["d"], color, 3)

        for item in self.map.billboards:
            self.draw_billboard_icon(item)

        sx = self.map.start["x"]
        sy = self.map.start["y"]
        sf = self.map.start["f"]
        if in_bounds(sx, sy, self.map.w, self.map.h):
            x0, y0, x1, y1 = self.cell_rect(sx, sy)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            r = self.cell * 0.17
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="cyan", outline="")
            self.canvas.create_text(cx, y0 + self.cell * 0.16, text=ARROW[sf], fill="cyan", font=("Consolas", max(8, int(self.cell * 0.20)), "bold"))

        if self.hover_edge and self.current_tool in (TOOL_WALL, TOOL_DOOR, TOOL_TEX_WALL):
            x, y, d = self.hover_edge
            self.draw_edge_marker(x, y, d, "#66aaff", 2)

        if self.hover_cell and self.current_tool in (TOOL_START, TOOL_TEX_FLOOR, TOOL_TEX_CEIL, TOOL_BILLBOARD):
            x, y = self.hover_cell
            x0, y0, x1, y1 = self.cell_rect(x, y)
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#66aaff", width=2)

    def draw_wall_face_overlay(self):
        for y in range(self.map.h):
            for x in range(self.map.w):
                for d in FACING_VALUES:
                    tex_id = self.map.wall_face_textures[dir_to_key(d)][y][x]
                    if tex_id == 0:
                        continue
                    color = WALL_TEX_PALETTE[tex_id % len(WALL_TEX_PALETTE)]
                    self.draw_inner_edge_line(x, y, d, color, self.wall_tex_line_width)

    def draw_inner_edge_line(self, x, y, d, color, width=2):
        x0, y0, x1, y1 = self.cell_rect(x, y)
        inset = 4
        if d == N:
            self.canvas.create_line(x0 + 4, y0 + inset, x1 - 4, y0 + inset, fill=color, width=width)
        elif d == E:
            self.canvas.create_line(x1 - inset, y0 + 4, x1 - inset, y1 - 4, fill=color, width=width)
        elif d == S:
            self.canvas.create_line(x0 + 4, y1 - inset, x1 - 4, y1 - inset, fill=color, width=width)
        elif d == W:
            self.canvas.create_line(x0 + inset, y0 + 4, x0 + inset, y1 - 4, fill=color, width=width)

    def draw_edge_marker(self, x, y, d, color, width=3):
        x0, y0, x1, y1 = self.cell_rect(x, y)
        pad = max(5, int(self.cell * 0.18))
        if d == N:
            mx, my = (x0 + x1) / 2, y0
            self.canvas.create_line(mx - pad, my, mx + pad, my, fill=color, width=width)
        elif d == S:
            mx, my = (x0 + x1) / 2, y1
            self.canvas.create_line(mx - pad, my, mx + pad, my, fill=color, width=width)
        elif d == W:
            mx, my = x0, (y0 + y1) / 2
            self.canvas.create_line(mx, my - pad, mx, my + pad, fill=color, width=width)
        elif d == E:
            mx, my = x1, (y0 + y1) / 2
            self.canvas.create_line(mx, my - pad, mx, my + pad, fill=color, width=width)

    def draw_billboard_icon(self, item):
        x0, y0, _, _ = self.cell_rect(item["x"], item["y"])
        cx = x0 + item.get("offset_x", 0.5) * self.cell
        cy = y0 + item.get("offset_y", 0.5) * self.cell
        color = "#8fe0ff" if item.get("mode", "face_camera") == "face_camera" else "#ffb870"
        self.canvas.create_rectangle(
            cx - self.cell * 0.14,
            cy - self.cell * 0.20,
            cx + self.cell * 0.14,
            cy + self.cell * 0.06,
            fill="#3a3028",
            outline="#b08c60",
        )
        self.canvas.create_line(
            cx,
            cy + self.cell * 0.06,
            cx,
            cy + self.cell * 0.16,
            fill="#6c5848",
            width=max(1, int(self.cell * 0.05)),
        )
        self.canvas.create_text(
            cx,
            cy - self.cell * 0.06,
            text=f"B{item['tex']}",
            fill=color,
            font=("Consolas", max(8, int(self.cell * 0.20)), "bold"),
        )
        if item.get("mode") == "fixed":
            self.canvas.create_text(
                cx,
                cy + self.cell * 0.24,
                text=ARROW[item.get("f", N)],
                fill="#ffcc88",
                font=("Consolas", max(8, int(self.cell * 0.16)), "bold"),
            )

    # -------------------------
    # Status
    # -------------------------
    def get_hover_detail(self):
        if self.hover_edge:
            x, y, d = self.hover_edge
            idx = self.find_door_at_edge(x, y, d)
            if idx is not None:
                door = self.map.doors[idx]
                if "event" in door:
                    return f"Door: tex={door['tex']} event={door['event']}"
                p = door.get("pass", {"type": "always"})
                if p.get("type") == "always":
                    return f"Door: tex={door['tex']} pass=always"
                if p.get("type") == "key":
                    return f"Door: tex={door['tex']} pass=key key_id={p.get('key_id', '')} consume={format_bool(bool(p.get('consume', False)))}"
                return f"Door: tex={door['tex']} pass=flag flag={p.get('flag', '')} value={format_bool(bool(p.get('value', True)))}"
        if self.hover_cell:
            x, y = self.hover_cell
            idx = self.find_billboard_in_cell(x, y)
            if idx is not None:
                b = self.map.billboards[idx]
                extra = f" f={DIR_LABEL[b['f']]}" if b.get("mode") == "fixed" else ""
                return (
                    f"Billboard: tex={b['tex']} mode={b['mode']}{extra} "
                    f"off=({b.get('offset_x', 0.5):.2f},{b.get('offset_y', 0.5):.2f}) "
                    f"size=({b.get('width', 0.78):.2f},{b.get('height', 1.15):.2f})"
                )
        return ""

    def update_status(self):
        hover_text = ""
        if self.hover_edge:
            x, y, d = self.hover_edge
            hover_text = f" | edge=({x},{y},{DIR_LABEL[d]})"
        elif self.hover_cell:
            x, y = self.hover_cell
            hover_text = f" | cell=({x},{y})"

        hover_detail = self.get_hover_detail()
        if hover_detail:
            hover_text += f" | {hover_detail}"

        self.status_main_label.config(
            text=(
                f"{self.map.meta['id']} ({self.map.meta['name']}) | "
                f"{self.map.w}x{self.map.h} | texset={self.map.texture_set}{hover_text}"
            )
        )
        self.update_tool_button_states()


def main():
    root = tk.Tk()
    app = MapEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()

