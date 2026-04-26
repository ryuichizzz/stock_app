import json
import math
import os
import random
import sys
from dataclasses import dataclass

import pygame

# =========================
# Direction bits
# =========================
N, E, S, W = 1, 2, 4, 8
DIRS = {N: (0, -1), E: (1, 0), S: (0, 1), W: (-1, 0)}
OPPOSITE = {N: S, E: W, S: N, W: E}
TURN_LEFT = {N: W, W: S, S: E, E: N}
TURN_RIGHT = {N: E, E: S, S: W, W: N}
FACING_TO_ANGLE = {N: -math.pi / 2, E: 0.0, S: math.pi / 2, W: math.pi}

# =========================
# Screen / Camera
# =========================
SCREEN_W = 960
SCREEN_H = 640
HALF_H = SCREEN_H // 2

FOV = math.radians(80)
HALF_FOV = FOV / 2
NUM_RAYS = 240
MAX_DEPTH = 32.0
PROJ_PLANE = (SCREEN_W * 0.5) / math.tan(HALF_FOV)

MID_FRAME_MS = 35

CAMERA_HEIGHT = 0.5
CAMERA_BACK_OFFSET = 0.10

TEX_SIZE = 64
NUM_SHADES = 16

MINIMAP_CELL = 8
MINIMAP_MARGIN = 12

FLOOR_SCALE = 3
FLOOR_SHADE_DISTANCE = 0.22
FLOOR_MIN_SHADE = 0.10
CEIL_SHADE_MULTIPLIER = 0.72
CEIL_MIN_SHADE = 0.08

JOYSTICK_DEADZONE = 0.35
MOVE_REPEAT_MS = 170
TURN_REPEAT_MS = 140
AXIS_LEFT_X = 0
AXIS_LEFT_Y = 1
BTN_A = 0
BTN_Y = 3
BTN_BACK = 6
BTN_START = 7

BILLBOARD_WORLD_WIDTH = 0.78
BILLBOARD_WORLD_HEIGHT = 1.15

IDLE_REDRAW_FPS = 10
IDLE_REDRAW_MS = 1000 // IDLE_REDRAW_FPS

TOON_PRESETS = [
    ("標準", 16, 0.00, 0.00),
    ("ややトゥーン", 6, 0.22, 0.35),
    ("トゥーン", 4, 0.45, 0.65),
    ("強めトゥーン", 3, 0.72, 0.90),
]


# =========================
# Helpers
# =========================
def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def in_bounds(x, y, w, h):
    return 0 <= x < w and 0 <= y < h


def opposite_dir(d):
    return {N: S, S: N, E: W, W: E}[d]


def canonical_edge(x, y, d, w, h):
    dx, dy = DIRS[d]
    nx, ny = x + dx, y + dy
    if not in_bounds(nx, ny, w, h):
        return (x, y, d)
    if (nx, ny) < (x, y):
        return (nx, ny, opposite_dir(d))
    return (x, y, d)


def noisy_color(base, spread, rng):
    return (
        clamp(base[0] + rng.randint(-spread, spread)),
        clamp(base[1] + rng.randint(-spread, spread)),
        clamp(base[2] + rng.randint(-spread, spread)),
    )


def shade_surface(src, shade):
    shade = max(0.0, min(1.0, shade))
    out = src.copy()
    darkness = int(255 * (1.0 - shade))
    if darkness > 0:
        overlay = pygame.Surface(out.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, darkness))
        out.blit(overlay, (0, 0))
    return out


def quantize_unit(value, steps):
    value = max(0.0, min(1.0, value))
    steps = max(1, int(steps))
    if steps <= 1:
        return 0.0
    return round(value * (steps - 1)) / (steps - 1)


def build_texture_columns(tex, num_shades=16):
    tex = pygame.transform.scale(tex, (TEX_SIZE, TEX_SIZE))
    columns = []
    for sx in range(TEX_SIZE):
        col = tex.subsurface((sx, 0, 1, TEX_SIZE)).copy()
        shade_list = []
        for i in range(num_shades):
            shade = i / (num_shades - 1)
            shade = 0.18 + shade * 0.82
            shade_list.append(shade_surface(col, shade))
        columns.append(shade_list)
    return columns


def load_texture_or(path, fallback, alpha=False):
    try:
        if os.path.exists(path):
            if alpha:
                return pygame.image.load(path).convert_alpha()
            return pygame.image.load(path).convert()
    except Exception:
        pass
    return fallback


def normalize_catalog_entries(entries, prefix):
    out = []
    if not isinstance(entries, list):
        entries = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            item = {}
        out.append({
            "id": idx,
            "name": str(item.get("name", f"{prefix}_{idx:02d}") or f"{prefix}_{idx:02d}"),
            "file": str(item.get("file", f"{prefix}_{idx:02d}.png") or f"{prefix}_{idx:02d}.png"),
        })
    if not out:
        out.append({"id": 0, "name": f"{prefix}_00", "file": f"{prefix}_00.png"})
    return out


# =========================
# Texture builders
# =========================
def make_stone_texture(size=64, seed=1):
    rng = random.Random(seed)
    surf = pygame.Surface((size, size)).convert()
    for y in range(size):
        for x in range(size):
            surf.set_at((x, y), noisy_color((105, 100, 92), 18, rng))

    brick_h = size // 8
    rows = size // brick_h
    for row in range(rows):
        y0 = row * brick_h
        offset = 0 if row % 2 == 0 else size // 4
        x = -offset
        while x < size:
            bw = rng.randint(size // 5, size // 3)
            bh = brick_h - 2
            rect = pygame.Rect(x, y0, bw, bh)
            stone = noisy_color((125, 118, 108), 20, rng)
            for yy in range(max(0, rect.top), min(size, rect.bottom)):
                for xx in range(max(0, rect.left), min(size, rect.right)):
                    dx = min(xx - rect.left, rect.right - 1 - xx)
                    dy = min(yy - rect.top, rect.bottom - 1 - yy)
                    edge_dark = 18 if min(dx, dy) < 2 else 0
                    grain = rng.randint(-12, 12)
                    surf.set_at((xx, yy), (
                        clamp(stone[0] + grain - edge_dark),
                        clamp(stone[1] + grain - edge_dark),
                        clamp(stone[2] + grain - edge_dark),
                    ))
            x += bw + 2
    return surf


def make_floor_texture(size=64, seed=2):
    rng = random.Random(seed)
    surf = pygame.Surface((size, size)).convert()
    tile = size // 4
    for y in range(size):
        for x in range(size):
            base = 60 + ((x // tile + y // tile) % 2) * 10
            n = rng.randint(-12, 12)
            surf.set_at((x, y), (clamp(base + n), clamp(base + n), clamp(base + n + 4)))
    for y in range(0, size, tile):
        pygame.draw.line(surf, (38, 38, 42), (0, y), (size, y), 1)
    for x in range(0, size, tile):
        pygame.draw.line(surf, (38, 38, 42), (x, 0), (x, size), 1)
    return surf


def make_ceiling_texture(size=64, seed=3):
    rng = random.Random(seed)
    surf = pygame.Surface((size, size)).convert()
    for y in range(size):
        for x in range(size):
            n = rng.randint(-10, 10)
            shade = 48 + n + int(12 * math.sin(x * 0.18))
            surf.set_at((x, y), (clamp(shade), clamp(shade), clamp(shade + 6)))
    for y in range(0, size, 8):
        pygame.draw.line(surf, (40, 40, 50), (0, y), (size, y), 1)
    return surf


def make_door_texture(size=64, seed=4):
    rng = random.Random(seed)
    surf = pygame.Surface((size, size)).convert()
    surf.fill((52, 32, 18))
    plank_w = size // 6
    for i in range(6):
        x0 = i * plank_w
        wood = noisy_color((126, 82, 42), 12, rng)
        for y in range(size):
            for x in range(x0, min(size, x0 + plank_w - 1)):
                grain = int(16 * math.sin((y + i * 7) * 0.18)) + rng.randint(-8, 8)
                surf.set_at((x, y), (
                    clamp(wood[0] + grain),
                    clamp(wood[1] + grain),
                    clamp(wood[2] + grain),
                ))
    pygame.draw.rect(surf, (55, 55, 58), (0, size // 4 - 3, size, 6))
    pygame.draw.rect(surf, (55, 55, 58), (0, size * 3 // 4 - 3, size, 6))
    return surf


def make_corner_texture(size=64, seed=5):
    rng = random.Random(seed)
    surf = pygame.Surface((size, size)).convert()
    surf.fill((86, 80, 74))
    for y in range(size):
        for x in range(size):
            n = rng.randint(-10, 10)
            base = 95 + n
            surf.set_at((x, y), (clamp(base), clamp(base - 4), clamp(base - 8)))
    for x in range(0, size, 8):
        pygame.draw.line(surf, (70, 65, 60), (x, 0), (x, size), 1)
    pygame.draw.rect(surf, (125, 118, 110), (4, 4, size - 8, size - 8), 2)
    return surf


def make_billboard_texture(size_w=128, size_h=192, label="B"):
    surf = pygame.Surface((size_w, size_h), pygame.SRCALPHA)
    pygame.draw.rect(
        surf,
        (60, 48, 36, 220),
        pygame.Rect(int(size_w * 0.15), int(size_h * 0.16), int(size_w * 0.70), int(size_h * 0.55)),
        border_radius=12,
    )
    pygame.draw.rect(
        surf,
        (170, 130, 80, 220),
        pygame.Rect(int(size_w * 0.15), int(size_h * 0.16), int(size_w * 0.70), int(size_h * 0.55)),
        width=4,
        border_radius=12,
    )
    pygame.draw.rect(
        surf,
        (80, 70, 56, 220),
        pygame.Rect(size_w // 2 - 4, int(size_h * 0.70), 8, int(size_h * 0.14)),
    )
    font = pygame.font.SysFont(None, 64, bold=True)
    txt = font.render(label[:2], True, (180, 240, 255))
    surf.blit(txt, txt.get_rect(center=(size_w // 2, int(size_h * 0.38))))
    return surf


# =========================
# Structs
# =========================
@dataclass
class WallPiece:
    x1: float
    y1: float
    x2: float
    y2: float
    tex_kind: str
    prefer_side: int | None = None
    edge_key: tuple | None = None
    sample_cell: tuple | None = None


# =========================
# Mesh
# =========================
def build_wall_mesh(walls, doors_set, width, height, wall_thickness, door_thickness, corner_size):
    pieces = []
    used_v = set()
    used_h = set()

    def is_door(x, y, d):
        return canonical_edge(x, y, d, width, height) in doors_set

    def edge_kind(x, y, d):
        if is_door(x, y, d):
            return "door"
        if (walls[y][x] & d) != 0:
            return "wall"
        return None

    for y in range(height):
        for x in range(width):
            if (walls[y][x] & E) == 0 and not is_door(x, y, E):
                continue
            key = (x, y, E)
            if key in used_v:
                continue

            kind = edge_kind(x, y, E)
            y0 = y
            while y0 > 0 and edge_kind(x, y0 - 1, E) == kind and (x, y0 - 1, E) not in used_v:
                y0 -= 1
            y1 = y
            while y1 < height - 1 and edge_kind(x, y1 + 1, E) == kind and (x, y1 + 1, E) not in used_v:
                y1 += 1

            for yy in range(y0, y1 + 1):
                used_v.add((x, yy, E))

            half = (door_thickness if kind == "door" else wall_thickness) * 0.5
            bx = x + 1.0
            pieces.append(WallPiece(
                bx - half, y0 + 0.0, bx + half, y1 + 1.0,
                kind, prefer_side=0,
                edge_key=canonical_edge(x, y, E, width, height),
                sample_cell=(x, y),
            ))

    for y in range(height):
        for x in range(width):
            if (walls[y][x] & S) == 0 and not is_door(x, y, S):
                continue
            key = (x, y, S)
            if key in used_h:
                continue

            kind = edge_kind(x, y, S)
            x0 = x
            while x0 > 0 and edge_kind(x0 - 1, y, S) == kind and (x0 - 1, y, S) not in used_h:
                x0 -= 1
            x1 = x
            while x1 < width - 1 and edge_kind(x1 + 1, y, S) == kind and (x1 + 1, y, S) not in used_h:
                x1 += 1

            for xx in range(x0, x1 + 1):
                used_h.add((xx, y, S))

            half = (door_thickness if kind == "door" else wall_thickness) * 0.5
            by = y + 1.0
            pieces.append(WallPiece(
                x0 + 0.0, by - half, x1 + 1.0, by + half,
                kind, prefer_side=1,
                edge_key=canonical_edge(x, y, S, width, height),
                sample_cell=(x, y),
            ))

    corner_half = corner_size * 0.5
    for gy in range(height + 1):
        for gx in range(width + 1):
            v_count = 0
            h_count = 0

            if gx - 1 >= 0 and gy < height:
                if edge_kind(gx - 1, gy, E) is not None:
                    v_count += 1
            if gx - 1 >= 0 and gy - 1 >= 0:
                if edge_kind(gx - 1, gy - 1, E) is not None:
                    v_count += 1

            if gx < width and gy - 1 >= 0:
                if edge_kind(gx, gy - 1, S) is not None:
                    h_count += 1
            if gx - 1 >= 0 and gy - 1 >= 0:
                if edge_kind(gx - 1, gy - 1, S) is not None:
                    h_count += 1

            total_connections = v_count + h_count
            is_corner_joint = v_count > 0 and h_count > 0
            is_end_cap = total_connections == 1

            if is_corner_joint or is_end_cap:
                sx = max(0, min(width - 1, gx - 1))
                sy = max(0, min(height - 1, gy - 1))
                pieces.append(WallPiece(
                    gx - corner_half,
                    gy - corner_half,
                    gx + corner_half,
                    gy + corner_half,
                    "corner",
                    prefer_side=None,
                    edge_key=None,
                    sample_cell=(sx, sy),
                ))

    return pieces


def build_spatial_index(pieces, width, height):
    grid = {}
    for idx, p in enumerate(pieces):
        min_cx = max(0, int(math.floor(p.x1)) - 1)
        max_cx = min(width - 1, int(math.floor(max(p.x1, p.x2) - 1e-6)) + 1)
        min_cy = max(0, int(math.floor(p.y1)) - 1)
        max_cy = min(height - 1, int(math.floor(max(p.y1, p.y2) - 1e-6)) + 1)
        for cy in range(min_cy, max_cy + 1):
            for cx in range(min_cx, max_cx + 1):
                grid.setdefault((cx, cy), []).append(idx)
    return grid


def ray_aabb_intersection(ox, oy, dx, dy, x1, y1, x2, y2, max_depth):
    eps = 1e-9

    if abs(dx) < eps:
        if not (x1 <= ox <= x2):
            return None
        tx_min, tx_max = -1e30, 1e30
    else:
        tx1 = (x1 - ox) / dx
        tx2 = (x2 - ox) / dx
        tx_min = min(tx1, tx2)
        tx_max = max(tx1, tx2)

    if abs(dy) < eps:
        if not (y1 <= oy <= y2):
            return None
        ty_min, ty_max = -1e30, 1e30
    else:
        ty1 = (y1 - oy) / dy
        ty2 = (y2 - oy) / dy
        ty_min = min(ty1, ty2)
        ty_max = max(ty1, ty2)

    t_enter = max(tx_min, ty_min)
    t_exit = min(tx_max, ty_max)

    if t_exit < 0.0 or t_enter > t_exit:
        return None

    t = t_enter if t_enter >= 0.0 else t_exit
    if t < 0.0 or t > max_depth:
        return None

    hx = ox + dx * t
    hy = oy + dy * t
    hit_side = 0 if tx_min > ty_min else 1
    return t, hit_side, hx, hy


def visible_face_key(edge_key, ray_dx, ray_dy, width, height):
    if edge_key is None:
        return None

    x, y, d = edge_key

    if d == E:
        if ray_dx < 0:
            return (x, y, E)
        nx = x + 1
        if nx < width:
            return (nx, y, W)
        return (x, y, E)

    if d == S:
        if ray_dy < 0:
            return (x, y, S)
        ny = y + 1
        if ny < height:
            return (x, ny, N)
        return (x, y, S)

    return edge_key


# =========================
# Project paths
# =========================
def project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    if os.path.basename(script_dir).lower() == "editor":
        return parent_dir
    return script_dir


def textures_dir():
    return os.path.join(project_root(), "textures")


def billboards_dir():
    return os.path.join(project_root(), "billboards")


def maps_dir():
    return os.path.join(project_root(), "maps")


def resolve_map_path(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        raw_path = argv[0]
        if not os.path.isabs(raw_path):
            raw_path = os.path.join(os.getcwd(), raw_path)
        return os.path.abspath(raw_path)
    return pick_map_path()


def init_first_joystick():
    if pygame.joystick.get_count() <= 0:
        return None
    js = pygame.joystick.Joystick(0)
    js.init()
    return js


def refresh_joystick(current):
    if current is not None and current.get_init():
        return current
    return init_first_joystick()


def axis_to_digital(value, deadzone=JOYSTICK_DEADZONE):
    if value <= -deadzone:
        return -1
    if value >= deadzone:
        return 1
    return 0


# =========================
# Game
# =========================
class Game:
    def __init__(self, map_path):
        self.map_path = map_path

        self.W = 0
        self.H = 0

        self.meta = {}
        self.texture_set = "stone"
        self.render_cfg = {
            "wall_thickness": 0.18,
            "door_thickness": 0.18,
            "corner_filler_size": 0.16,
        }

        self.texture_catalog = {
            "name": "stone",
            "wall": [{"id": 0, "name": "wall_00", "file": "wall_00.png"}],
            "floor": [{"id": 0, "name": "floor_00", "file": "floor_00.png"}],
            "ceiling": [{"id": 0, "name": "ceiling_00", "file": "ceiling_00.png"}],
            "door": [{"id": 0, "name": "door_00", "file": "door_00.png"}],
            "corner": [{"id": 0, "name": "corner_00", "file": "corner_00.png"}],
        }
        self.billboard_catalog = {
            "name": "default_billboards",
            "billboards": [{"id": 0, "name": "billboard_00", "file": "billboard_00.png"}],
        }

        self.cell_textures = {}
        self.wall_face_textures = {}

        self.walls = []
        self.doors = []
        self.doors_by_edge = {}
        self.doors_set = set()

        self.billboards = []

        self.wall_pieces = []
        self.piece_grid = {}

        self.px = 0
        self.py = 0
        self.facing = N

        self.show_map = False
        self._temp_view = None

        self.inventory = {"bronze_key": 1}
        self.flags = {"boss_room_opened": False}

        self.effect_kind = None
        self.effect_end_ms = 0

        self.toon_preset_index = 1
        self.toon_steps = NUM_SHADES
        self.toon_outline_strength = 0.0
        self.toon_flatness = 0.0

        self.wall_tex_bank = []
        self.floor_tex_bank = []
        self.ceil_tex_bank = []
        self.door_tex_bank = []
        self.corner_tex_bank = []

        self.wall_cols_banks = []
        self.door_cols_banks = []
        self.corner_cols_banks = []

        self.billboard_tex = []

        self.load_map()
        self.load_texture_catalog()
        self.load_billboard_catalog()
        self.load_textures()
        self.apply_toon_preset(self.toon_preset_index)

    # -------------------------
    # Catalog loading
    # -------------------------
    def load_texture_catalog(self):
        path = os.path.join(textures_dir(), self.texture_set, "textureset.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.texture_catalog = {
                    "name": str(data.get("name", self.texture_set) or self.texture_set),
                    "wall": normalize_catalog_entries(data.get("wall", []), "wall"),
                    "floor": normalize_catalog_entries(data.get("floor", []), "floor"),
                    "ceiling": normalize_catalog_entries(data.get("ceiling", []), "ceiling"),
                    "door": normalize_catalog_entries(data.get("door", []), "door"),
                    "corner": normalize_catalog_entries(data.get("corner", []), "corner"),
                }
                return
            except Exception as exc:
                print(f"[WARN] failed to load textureset.json: {exc}")

        self.texture_catalog = {
            "name": self.texture_set,
            "wall": [{"id": 0, "name": "wall_00", "file": "wall_00.png"}],
            "floor": [{"id": 0, "name": "floor_00", "file": "floor_00.png"}],
            "ceiling": [{"id": 0, "name": "ceiling_00", "file": "ceiling_00.png"}],
            "door": [{"id": 0, "name": "door_00", "file": "door_00.png"}],
            "corner": [{"id": 0, "name": "corner_00", "file": "corner_00.png"}],
        }

    def load_billboard_catalog(self):
        path = os.path.join(billboards_dir(), "billboardset.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.billboard_catalog = {
                    "name": str(data.get("name", "default_billboards") or "default_billboards"),
                    "billboards": normalize_catalog_entries(data.get("billboards", []), "billboard"),
                }
                return
            except Exception as exc:
                print(f"[WARN] failed to load billboardset.json: {exc}")

        self.billboard_catalog = {
            "name": "default_billboards",
            "billboards": [{"id": 0, "name": "billboard_00", "file": "billboard_00.png"}],
        }

    # -------------------------
    # Map loading
    # -------------------------
    def load_map(self):
        with open(self.map_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.meta = data.get("meta", {})
        self.texture_set = data.get("texture_set", "stone")
        self.render_cfg.update(data.get("render", {}))

        self.W = int(data["size"]["w"])
        self.H = int(data["size"]["h"])

        self.walls = data.get("walls", [[0 for _ in range(self.W)] for __ in range(self.H)])

        st = data.get("start", {"x": 0, "y": 0, "f": N})
        self.px = int(st.get("x", 0))
        self.py = int(st.get("y", 0))
        self.facing = int(st.get("f", N))

        cell_tex = data.get("cell_textures", {})
        self.cell_textures = {
            "floor": cell_tex.get("floor", [[0 for _ in range(self.W)] for __ in range(self.H)]),
            "ceiling": cell_tex.get("ceiling", [[0 for _ in range(self.W)] for __ in range(self.H)]),
        }

        wall_face = data.get("wall_face_textures", {})
        self.wall_face_textures = {
            "n": wall_face.get("n", [[0 for _ in range(self.W)] for __ in range(self.H)]),
            "e": wall_face.get("e", [[0 for _ in range(self.W)] for __ in range(self.H)]),
            "s": wall_face.get("s", [[0 for _ in range(self.W)] for __ in range(self.H)]),
            "w": wall_face.get("w", [[0 for _ in range(self.W)] for __ in range(self.H)]),
        }

        self.doors = data.get("doors", [])
        self.doors_by_edge = {}
        self.doors_set = set()
        for door in self.doors:
            edge = canonical_edge(
                int(door["x"]),
                int(door["y"]),
                int(door["d"]),
                self.W,
                self.H,
            )
            self.doors_set.add(edge)
            self.doors_by_edge[edge] = door

        self.billboards = []
        for item in data.get("billboards", []):
            mode = item.get("mode", "face_camera")
            if mode not in ("face_camera", "fixed"):
                mode = "face_camera"

            f = int(item.get("f", N))
            if f not in (N, E, S, W):
                f = N

            self.billboards.append({
                "x": int(item["x"]),
                "y": int(item["y"]),
                "tex": int(item.get("tex", 0)),
                "offset_x": float(item.get("offset_x", 0.5)),
                "offset_y": float(item.get("offset_y", 0.5)),
                "width": float(item.get("width", 0.78)),
                "height": float(item.get("height", 1.15)),
                "mode": mode,
                "f": f,
            })

        self.wall_pieces = build_wall_mesh(
            self.walls,
            self.doors_set,
            self.W,
            self.H,
            wall_thickness=float(self.render_cfg.get("wall_thickness", 0.18)),
            door_thickness=float(self.render_cfg.get("door_thickness", 0.18)),
            corner_size=float(self.render_cfg.get("corner_filler_size", 0.16)),
        )
        self.piece_grid = build_spatial_index(self.wall_pieces, self.W, self.H)

    # -------------------------
    # Texture loading
    # -------------------------
    def _catalog_len(self, key):
        return max(1, len(self.texture_catalog.get(key, [])))

    def _catalog_file(self, key, tex_id):
        entries = self.texture_catalog.get(key, [])
        if not entries:
            return None
        tex_id = max(0, min(len(entries) - 1, tex_id))
        return entries[tex_id]["file"]

    def _billboard_file(self, tex_id):
        entries = self.billboard_catalog.get("billboards", [])
        if not entries:
            return None
        tex_id = max(0, min(len(entries) - 1, tex_id))
        return entries[tex_id]["file"]

    def load_textures(self):
        tex_dir = os.path.join(textures_dir(), self.texture_set)
        bb_dir = billboards_dir()

        self.wall_tex_bank = []
        for i in range(self._catalog_len("wall")):
            file_name = self._catalog_file("wall", i)
            path = os.path.join(tex_dir, file_name) if file_name else ""
            self.wall_tex_bank.append(load_texture_or(path, make_stone_texture(TEX_SIZE, 10 + i)))

        self.floor_tex_bank = []
        for i in range(self._catalog_len("floor")):
            file_name = self._catalog_file("floor", i)
            path = os.path.join(tex_dir, file_name) if file_name else ""
            self.floor_tex_bank.append(load_texture_or(path, make_floor_texture(TEX_SIZE, 20 + i)))

        self.ceil_tex_bank = []
        for i in range(self._catalog_len("ceiling")):
            file_name = self._catalog_file("ceiling", i)
            path = os.path.join(tex_dir, file_name) if file_name else ""
            self.ceil_tex_bank.append(load_texture_or(path, make_ceiling_texture(TEX_SIZE, 30 + i)))

        self.door_tex_bank = []
        for i in range(self._catalog_len("door")):
            file_name = self._catalog_file("door", i)
            path = os.path.join(tex_dir, file_name) if file_name else ""
            self.door_tex_bank.append(load_texture_or(path, make_door_texture(TEX_SIZE, 40 + i)))

        self.corner_tex_bank = []
        for i in range(self._catalog_len("corner")):
            file_name = self._catalog_file("corner", i)
            path = os.path.join(tex_dir, file_name) if file_name else ""
            self.corner_tex_bank.append(load_texture_or(path, make_corner_texture(TEX_SIZE, 50 + i)))

        self.wall_cols_banks = [build_texture_columns(t, NUM_SHADES) for t in self.wall_tex_bank]
        self.door_cols_banks = [build_texture_columns(t, NUM_SHADES) for t in self.door_tex_bank]
        self.corner_cols_banks = [build_texture_columns(t, NUM_SHADES) for t in self.corner_tex_bank]

        max_bb_tex = 0
        for item in self.billboards:
            max_bb_tex = max(max_bb_tex, int(item.get("tex", 0)))
        max_bb_tex = max(max_bb_tex, len(self.billboard_catalog.get("billboards", [])) - 1)

        self.billboard_tex = []
        for i in range(max_bb_tex + 1):
            file_name = self._billboard_file(i)
            path = os.path.join(bb_dir, file_name) if file_name else ""
            self.billboard_tex.append(load_texture_or(path, make_billboard_texture(label=f"B{i}"), alpha=True))

    # -------------------------
    # Accessors
    # -------------------------
    def get_floor_tex_id(self, x, y):
        if not in_bounds(x, y, self.W, self.H):
            return 0
        v = int(self.cell_textures["floor"][y][x])
        return max(0, min(len(self.floor_tex_bank) - 1, v))

    def get_ceil_tex_id(self, x, y):
        if not in_bounds(x, y, self.W, self.H):
            return 0
        v = int(self.cell_textures["ceiling"][y][x])
        return max(0, min(len(self.ceil_tex_bank) - 1, v))

    def get_wall_face_tex_id(self, x, y, d):
        if not in_bounds(x, y, self.W, self.H):
            return 0
        key = {N: "n", E: "e", S: "s", W: "w"}[d]
        v = int(self.wall_face_textures[key][y][x])
        return max(0, min(len(self.wall_tex_bank) - 1, v))

    def get_corner_tex_id(self):
        return 0

    def get_door_tex_id(self, edge_key=None):
        if edge_key is not None and edge_key in self.doors_by_edge:
            v = int(self.doors_by_edge[edge_key].get("tex", 0))
            return max(0, min(len(self.door_tex_bank) - 1, v))
        return 0

    def get_wall_tex_id(self, face_key=None, sample_cell=None):
        if face_key is not None:
            x, y, d = face_key
            return self.get_wall_face_tex_id(x, y, d)

        sx, sy = sample_cell if sample_cell else (0, 0)
        return self.get_wall_face_tex_id(sx, sy, N)

    # -------------------------
    # Effects
    # -------------------------
    def trigger_effect(self, kind, duration_ms=160):
        self.effect_kind = kind
        self.effect_end_ms = pygame.time.get_ticks() + duration_ms

    # -------------------------
    # Toon controls
    # -------------------------
    def apply_toon_preset(self, index):
        index %= len(TOON_PRESETS)
        self.toon_preset_index = index
        _, steps, outline, flatness = TOON_PRESETS[index]
        self.toon_steps = steps
        self.toon_outline_strength = outline
        self.toon_flatness = flatness

    def cycle_toon_preset(self):
        self.apply_toon_preset(self.toon_preset_index + 1)

    def adjust_toon_steps(self, delta):
        self.toon_steps = max(2, min(NUM_SHADES, self.toon_steps + delta))

    def adjust_toon_outline(self, delta):
        self.toon_outline_strength = max(0.0, min(1.0, self.toon_outline_strength + delta))

    def adjust_toon_flatness(self, delta):
        self.toon_flatness = max(0.0, min(1.0, self.toon_flatness + delta))

    def stylized_shade(self, shade):
        shade = max(0.0, min(1.0, shade))
        if self.toon_flatness <= 0.0:
            return shade

        boosted = 0.5 + (shade - 0.5) * (1.0 + self.toon_flatness * 1.35)
        boosted = max(0.0, min(1.0, boosted))
        quantized = quantize_unit(boosted, self.toon_steps)
        mix = self.toon_flatness
        return boosted * (1.0 - mix) + quantized * mix

    def current_effect_alpha(self):
        if not self.effect_kind:
            return 0
        now = pygame.time.get_ticks()
        if now >= self.effect_end_ms:
            self.effect_kind = None
            return 0
        remain = self.effect_end_ms - now
        return max(0, min(140, int(remain * 140 / 160)))

    # -------------------------
    # Movement / collision
    # -------------------------
    def wall_blocks_from(self, x, y, d):
        return (self.walls[y][x] & d) != 0

    def door_blocks_from(self, x, y, d):
        return canonical_edge(x, y, d, self.W, self.H) in self.doors_set

    def can_pass_door(self, x, y, d):
        edge = canonical_edge(x, y, d, self.W, self.H)
        door = self.doors_by_edge.get(edge)
        if door is None:
            return False

        if "event" in door:
            return True

        rule = door.get("pass", {"type": "always"})
        kind = rule.get("type", "always")

        if kind == "always":
            return True

        if kind == "key":
            key_id = rule.get("key_id", "")
            if self.inventory.get(key_id, 0) > 0:
                if rule.get("consume", False):
                    self.inventory[key_id] = max(0, self.inventory.get(key_id, 0) - 1)
                self.trigger_effect("flash_cyan")
                return True
            self.trigger_effect("flash_red")
            return False

        if kind == "flag":
            flag = rule.get("flag", "")
            wanted = bool(rule.get("value", True))
            if self.flags.get(flag, False) == wanted:
                self.trigger_effect("flash_magenta")
                return True
            self.trigger_effect("flash_red")
            return False

        return False

    def can_step_from(self, x, y, d):
        if self.wall_blocks_from(x, y, d):
            return False
        if self.door_blocks_from(x, y, d):
            return self.can_pass_door(x, y, d)
        dx, dy = DIRS[d]
        nx, ny = x + dx, y + dy
        return in_bounds(nx, ny, self.W, self.H)

    def current_angle(self):
        if self._temp_view is not None:
            return self._temp_view[2]
        return FACING_TO_ANGLE[self.facing]

    def current_pos(self):
        if self._temp_view is not None:
            x, y, ang = self._temp_view
            x -= math.cos(ang) * CAMERA_BACK_OFFSET
            y -= math.sin(ang) * CAMERA_BACK_OFFSET
            return x, y

        x = self.px + 0.5
        y = self.py + 0.5
        ang = self.current_angle()
        x -= math.cos(ang) * CAMERA_BACK_OFFSET
        y -= math.sin(ang) * CAMERA_BACK_OFFSET
        return x, y

    def draw_intermediate_frame(self, screen, font, mid_x, mid_y, mid_angle):
        self._temp_view = (mid_x, mid_y, mid_angle)
        self.draw(screen, font)
        pygame.display.flip()
        pygame.time.delay(MID_FRAME_MS)
        self._temp_view = None

    def try_forward(self, screen=None, font=None):
        if self.can_step_from(self.px, self.py, self.facing):
            dx, dy = DIRS[self.facing]
            if screen is not None and font is not None:
                self.draw_intermediate_frame(
                    screen, font,
                    self.px + 0.5 + dx * 0.5,
                    self.py + 0.5 + dy * 0.5,
                    self.current_angle(),
                )
            self.px += dx
            self.py += dy
            return True
        return False

    def try_backward(self, screen=None, font=None):
        back = OPPOSITE[self.facing]
        if self.can_step_from(self.px, self.py, back):
            dx, dy = DIRS[back]
            if screen is not None and font is not None:
                self.draw_intermediate_frame(
                    screen, font,
                    self.px + 0.5 + dx * 0.5,
                    self.py + 0.5 + dy * 0.5,
                    self.current_angle(),
                )
            self.px += dx
            self.py += dy
            return True
        return False

    def try_turn_left(self, screen=None, font=None):
        new_facing = TURN_LEFT[self.facing]
        if screen is not None and font is not None:
            a0 = FACING_TO_ANGLE[self.facing]
            a1 = FACING_TO_ANGLE[new_facing]
            diff = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            self.draw_intermediate_frame(screen, font, self.px + 0.5, self.py + 0.5, a0 + diff * 0.5)
        self.facing = new_facing
        return True

    def try_turn_right(self, screen=None, font=None):
        new_facing = TURN_RIGHT[self.facing]
        if screen is not None and font is not None:
            a0 = FACING_TO_ANGLE[self.facing]
            a1 = FACING_TO_ANGLE[new_facing]
            diff = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            self.draw_intermediate_frame(screen, font, self.px + 0.5, self.py + 0.5, a0 + diff * 0.5)
        self.facing = new_facing
        return True

    def try_space_action(self, screen=None, font=None):
        if self.door_blocks_from(self.px, self.py, self.facing):
            if not self.can_pass_door(self.px, self.py, self.facing):
                return False
            dx, dy = DIRS[self.facing]
            if screen is not None and font is not None:
                self.draw_intermediate_frame(
                    screen, font,
                    self.px + 0.5 + dx * 0.5,
                    self.py + 0.5 + dy * 0.5,
                    self.current_angle(),
                )
            self.px += dx
            self.py += dy
            return True
        return False

    # -------------------------
    # Raycast
    # -------------------------
    def raycast(self, ox, oy, angle):
        dx = math.cos(angle)
        dy = math.sin(angle)

        cell_x = int(ox)
        cell_y = int(oy)
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        eps = 1e-9

        if abs(dx) < eps:
            t_delta_x = 1e30
            t_max_x = 1e30
        else:
            next_vert = (cell_x + 1.0) if dx > 0 else cell_x * 1.0
            t_max_x = (next_vert - ox) / dx
            if t_max_x < 0:
                t_max_x = 0.0
            t_delta_x = abs(1.0 / dx)

        if abs(dy) < eps:
            t_delta_y = 1e30
            t_max_y = 1e30
        else:
            next_horz = (cell_y + 1.0) if dy > 0 else cell_y * 1.0
            t_max_y = (next_horz - oy) / dy
            if t_max_y < 0:
                t_max_y = 0.0
            t_delta_y = abs(1.0 / dy)

        best = None
        tested = set()

        for _ in range(int(MAX_DEPTH * 3) + 8):
            if in_bounds(cell_x, cell_y, self.W, self.H):
                for idx in self.piece_grid.get((cell_x, cell_y), ()):
                    if idx in tested:
                        continue
                    tested.add(idx)

                    piece = self.wall_pieces[idx]
                    hit = ray_aabb_intersection(
                        ox, oy, dx, dy,
                        piece.x1, piece.y1, piece.x2, piece.y2,
                        MAX_DEPTH
                    )
                    if hit is None:
                        continue

                    dist, hit_side, hx, hy = hit
                    if hit_side == 0:
                        tex_u = hy % 1.0
                        if dx > 0:
                            tex_u = 1.0 - tex_u
                    else:
                        tex_u = hx % 1.0
                        if dy < 0:
                            tex_u = 1.0 - tex_u

                    tex_u = max(0.0, min(0.999999, tex_u))
                    face_key = visible_face_key(piece.edge_key, dx, dy, self.W, self.H)
                    cand = (dist, hit_side, piece.tex_kind, tex_u, face_key, piece.edge_key, piece.sample_cell)
                    if best is None or dist < best[0]:
                        best = cand

            next_cell_t = min(t_max_x, t_max_y)
            if best is not None and next_cell_t > best[0]:
                break
            if next_cell_t > MAX_DEPTH:
                break

            if t_max_x < t_max_y:
                cell_x += step_x
                t_max_x += t_delta_x
            else:
                cell_y += step_y
                t_max_y += t_delta_y

            if cell_x < -1 or cell_x > self.W or cell_y < -1 or cell_y > self.H:
                if best is not None:
                    break

        if best is None:
            return MAX_DEPTH, 0, "wall", 0.0, None, None, None
        return best

    # -------------------------
    # Sampling
    # -------------------------
    def texture_sample(self, tex, u, v):
        tw = tex.get_width()
        th = tex.get_height()
        tx = int((u % 1.0) * tw) % tw
        ty = int((v % 1.0) * th) % th
        return tex.get_at((tx, ty))

    def floor_sample(self, wx, wy):
        cx = int(wx)
        cy = int(wy)
        tex_id = self.get_floor_tex_id(cx, cy)
        tex = self.floor_tex_bank[tex_id % len(self.floor_tex_bank)]
        col = self.texture_sample(tex, wx, wy)
        return (col.r, col.g, col.b)

    def ceil_sample(self, wx, wy):
        cx = int(wx)
        cy = int(wy)
        tex_id = self.get_ceil_tex_id(cx, cy)
        tex = self.ceil_tex_bank[tex_id % len(self.ceil_tex_bank)]
        col = self.texture_sample(tex, wx, wy)
        return (col.r, col.g, col.b)

    def wall_column_surface(self, tex_kind, src_x, shade_idx, face_key=None, edge_key=None, sample_cell=None):
        if tex_kind == "door":
            tex_id = self.get_door_tex_id(edge_key)
            return self.door_cols_banks[tex_id % len(self.door_cols_banks)][src_x][shade_idx]

        if tex_kind == "corner":
            tex_id = self.get_corner_tex_id()
            return self.corner_cols_banks[tex_id % len(self.corner_cols_banks)][src_x][shade_idx]

        tex_id = self.get_wall_tex_id(face_key=face_key, sample_cell=sample_cell)
        return self.wall_cols_banks[tex_id % len(self.wall_cols_banks)][src_x][shade_idx]

    # -------------------------
    # Projection / billboards
    # -------------------------
    def draw_billboard_sprite(self, screen, tex, center_x, center_y, width, height, depth_buffer):
        ox, oy = self.current_pos()
        ang = self.current_angle()

        dx = center_x - ox
        dy = center_y - oy

        cos_a = math.cos(ang)
        sin_a = math.sin(ang)

        cam_x = dx * (-sin_a) + dy * cos_a
        cam_z = dx * cos_a + dy * sin_a

        if cam_z <= 0.0001:
            return

        screen_x = SCREEN_W * 0.5 + (cam_x / cam_z) * PROJ_PLANE
        screen_h = max(1, int((height / cam_z) * PROJ_PLANE))
        screen_w = max(1, int((width / cam_z) * PROJ_PLANE))
        top_y = int(HALF_H - ((1.0 - CAMERA_HEIGHT) / cam_z) * PROJ_PLANE - screen_h * 0.15)

        left_x = int(screen_x - screen_w * 0.5)
        right_x = left_x + screen_w

        tex_w = tex.get_width()
        tex_h = tex.get_height()

        ix0 = max(0, left_x)
        ix1 = min(SCREEN_W - 1, right_x - 1)
        if ix1 < ix0:
            return

        for sx in range(ix0, ix1 + 1):
            if depth_buffer[sx] < cam_z:
                continue
            u = (sx - left_x) / max(1, screen_w)
            tx = max(0, min(tex_w - 1, int(u * tex_w)))
            col = tex.subsurface((tx, 0, 1, tex_h)).copy()
            scaled = pygame.transform.scale(col, (1, screen_h))
            screen.blit(scaled, (sx, top_y))

    def draw_billboards(self, screen, depth_buffer):
        if not self.billboards:
            return

        ox, oy = self.current_pos()
        ordered = sorted(
            self.billboards,
            key=lambda b: (b["x"] + b["offset_x"] - ox) ** 2 + (b["y"] + b["offset_y"] - oy) ** 2,
            reverse=True,
        )

        for b in ordered:
            tex_id = int(b.get("tex", 0))
            if tex_id < 0 or tex_id >= len(self.billboard_tex):
                continue
            tex = self.billboard_tex[tex_id]

            wx = b["x"] + float(b.get("offset_x", 0.5))
            wy = b["y"] + float(b.get("offset_y", 0.5))
            ww = float(b.get("width", BILLBOARD_WORLD_WIDTH))
            wh = float(b.get("height", BILLBOARD_WORLD_HEIGHT))

            # 第5段階で face_camera / fixed の差を本格対応
            self.draw_billboard_sprite(screen, tex, wx, wy, ww, wh, depth_buffer)

    # -------------------------
    # Drawing
    # -------------------------
    def draw_floor_and_ceiling(self, screen):
        low_w = SCREEN_W // FLOOR_SCALE
        low_h = SCREEN_H // FLOOR_SCALE
        low_half_h = low_h // 2

        temp = pygame.Surface((low_w, low_h)).convert()

        ox, oy = self.current_pos()
        base_angle = self.current_angle()

        left_dx = math.cos(base_angle - HALF_FOV)
        left_dy = math.sin(base_angle - HALF_FOV)
        right_dx = math.cos(base_angle + HALF_FOV)
        right_dy = math.sin(base_angle + HALF_FOV)

        for y in range(low_half_h, low_h):
            p = y - low_half_h + 0.0001
            row_distance = (CAMERA_HEIGHT * (PROJ_PLANE / FLOOR_SCALE)) / p

            step_x = row_distance * (right_dx - left_dx) / low_w
            step_y = row_distance * (right_dy - left_dy) / low_w

            floor_x = ox + row_distance * left_dx
            floor_y = oy + row_distance * left_dy

            for x in range(low_w):
                fr, fg, fb = self.floor_sample(floor_x, floor_y)
                cr, cg, cb = self.ceil_sample(floor_x, floor_y)

                shade = 1.0 / (1.0 + row_distance * FLOOR_SHADE_DISTANCE)
                shade = max(FLOOR_MIN_SHADE, min(1.0, shade))
                ceil_shade = max(CEIL_MIN_SHADE, min(1.0, shade * CEIL_SHADE_MULTIPLIER))
                shade = self.stylized_shade(shade)
                ceil_shade = self.stylized_shade(ceil_shade)

                fc = (clamp(fr * shade), clamp(fg * shade), clamp(fb * shade))
                cc = (clamp(cr * ceil_shade), clamp(cg * ceil_shade), clamp(cb * ceil_shade))

                temp.set_at((x, y), fc)
                cy = low_h - 1 - y
                if 0 <= cy < low_h:
                    temp.set_at((x, cy), cc)

                floor_x += step_x
                floor_y += step_y

        scaled = pygame.transform.scale(temp, (SCREEN_W, SCREEN_H))
        screen.blit(scaled, (0, 0))

    def draw_3d(self, screen):
        screen.fill((0, 0, 0))
        self.draw_floor_and_ceiling(screen)

        ox, oy = self.current_pos()
        base_angle = self.current_angle()

        ray_step = FOV / NUM_RAYS
        col_w = SCREEN_W / NUM_RAYS
        depth_buffer = [MAX_DEPTH] * SCREEN_W

        ray_depths = []

        for i in range(NUM_RAYS):
            ray_angle = base_angle - HALF_FOV + (i + 0.5) * ray_step
            dist, side, tex_kind, tex_u, face_key, edge_key, sample_cell = self.raycast(ox, oy, ray_angle)

            corrected = dist * math.cos(ray_angle - base_angle)
            corrected = max(0.0001, corrected)

            wall_h = min(SCREEN_H * 1.6, (PROJ_PLANE / corrected))
            top = HALF_H - wall_h / 2

            src_x = int(tex_u * TEX_SIZE)
            src_x = max(0, min(TEX_SIZE - 1, src_x))

            shade = 1.0 / (1.0 + corrected * 0.16)
            if side == 1:
                shade *= 0.78

            shade = max(0.18, min(1.0, shade))
            shade = self.stylized_shade(shade)
            shade_idx = int((shade - 0.18) / 0.82 * (NUM_SHADES - 1))
            shade_idx = max(0, min(NUM_SHADES - 1, shade_idx))

            column = self.wall_column_surface(
                tex_kind,
                src_x,
                shade_idx,
                face_key=face_key,
                edge_key=edge_key,
                sample_cell=sample_cell,
            )

            x = int(i * col_w)
            w = max(1, int(col_w) + 1)
            scaled = pygame.transform.scale(column, (w, int(wall_h)))
            screen.blit(scaled, (x, int(top)))

            for sx in range(x, min(SCREEN_W, x + w)):
                depth_buffer[sx] = min(depth_buffer[sx], corrected)
            ray_depths.append((x, w, corrected, top, wall_h))

        if self.toon_outline_strength > 0.0:
            self.draw_toon_outlines(screen, ray_depths)

        self.draw_billboards(screen, depth_buffer)

    def draw_toon_outlines(self, screen, ray_depths):
        if not ray_depths:
            return

        outline_alpha = int(120 + 135 * self.toon_outline_strength)
        color = (0, 0, 0, outline_alpha)
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        line_w = max(1, int(1 + self.toon_outline_strength * 2.5))
        prev = None

        for x, w, depth, top, wall_h in ray_depths:
            y0 = max(0, int(top))
            y1 = min(SCREEN_H - 1, int(top + wall_h))
            h = max(1, y1 - y0)

            # Top and bottom silhouette lines make the wall read as inked shapes.
            pygame.draw.rect(overlay, color, (x, y0, w, line_w))
            pygame.draw.rect(overlay, color, (x, max(y0, y1 - line_w), w, line_w))

            # Strong vertical seam between visibly different depths.
            if prev is not None:
                prev_x, prev_w, prev_depth, prev_top, prev_wall_h = prev
                edge_strength = abs(depth - prev_depth)
                threshold = 0.08 + (1.0 - self.toon_outline_strength) * 0.22
                if edge_strength > threshold:
                    seam_x = max(0, x - line_w)
                    seam_top = max(0, min(int(prev_top), y0))
                    seam_bottom = min(SCREEN_H - 1, max(int(prev_top + prev_wall_h), y1))
                    pygame.draw.rect(
                        overlay,
                        color,
                        (seam_x, seam_top, line_w, max(1, seam_bottom - seam_top)),
                    )

            prev = (x, w, depth, top, wall_h)

        # Outer frame helps the whole view feel more inked.
        rim_alpha = int(80 + 100 * self.toon_outline_strength)
        rim_color = (0, 0, 0, rim_alpha)
        pygame.draw.rect(overlay, rim_color, (0, 0, SCREEN_W, 2))
        pygame.draw.rect(overlay, rim_color, (0, SCREEN_H - 2, SCREEN_W, 2))

        screen.blit(overlay, (0, 0))

    def draw_effect_overlay(self, screen):
        alpha = self.current_effect_alpha()
        if alpha <= 0:
            return

        color = (255, 255, 255)
        if self.effect_kind == "flash_red":
            color = (255, 80, 80)
        elif self.effect_kind == "flash_cyan":
            color = (100, 220, 255)
        elif self.effect_kind == "flash_magenta":
            color = (220, 100, 255)

        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill((color[0], color[1], color[2], alpha))
        screen.blit(ov, (0, 0))

    def draw_minimap(self, screen):
        if not self.show_map:
            return

        cell = MINIMAP_CELL
        ox = MINIMAP_MARGIN
        oy = MINIMAP_MARGIN

        pygame.draw.rect(
            screen,
            (0, 0, 0),
            (ox - 6, oy - 6, self.W * cell + 12, self.H * cell + 12),
        )

        pal = [(16, 16, 18), (18, 28, 36), (18, 32, 24), (34, 18, 18), (20, 24, 42), (36, 24, 16)]

        for y in range(self.H):
            for x in range(self.W):
                rect = pygame.Rect(ox + x * cell, oy + y * cell, cell, cell)
                floor_id = self.get_floor_tex_id(x, y)
                pygame.draw.rect(screen, pal[floor_id % len(pal)], rect)

                v = self.walls[y][x]
                if v & N:
                    pygame.draw.line(screen, (255, 255, 255), rect.topleft, rect.topright, 1)
                if v & E:
                    pygame.draw.line(screen, (255, 255, 255), rect.topright, rect.bottomright, 1)
                if v & S:
                    pygame.draw.line(screen, (255, 255, 255), rect.bottomleft, rect.bottomright, 1)
                if v & W:
                    pygame.draw.line(screen, (255, 255, 255), rect.topleft, rect.bottomleft, 1)

        for edge, door in self.doors_by_edge.items():
            x, y, d = edge
            color = (240, 200, 70)
            if "event" in door:
                color = (255, 120, 180)
            else:
                p = door.get("pass", {"type": "always"}).get("type", "always")
                if p == "key":
                    color = (120, 240, 255)
                elif p == "flag":
                    color = (255, 120, 180)

            x0 = ox + x * cell
            y0 = oy + y * cell
            x1 = x0 + cell
            y1 = y0 + cell
            pad = max(2, cell // 4)

            if d == N:
                pygame.draw.line(screen, color, ((x0 + x1) // 2 - pad, y0), ((x0 + x1) // 2 + pad, y0), 2)
            elif d == S:
                pygame.draw.line(screen, color, ((x0 + x1) // 2 - pad, y1), ((x0 + x1) // 2 + pad, y1), 2)
            elif d == W:
                pygame.draw.line(screen, color, (x0, (y0 + y1) // 2 - pad), (x0, (y0 + y1) // 2 + pad), 2)
            elif d == E:
                pygame.draw.line(screen, color, (x1, (y0 + y1) // 2 - pad), (x1, (y0 + y1) // 2 + pad), 2)

        for b in self.billboards:
            bx = ox + int((b["x"] + 0.5) * cell)
            by = oy + int((b["y"] + 0.5) * cell)
            color = (120, 180, 255) if b.get("mode") == "face_camera" else (255, 180, 120)
            pygame.draw.circle(screen, color, (bx, by), 2)

        px = ox + int(self.current_pos()[0] * cell)
        py = oy + int(self.current_pos()[1] * cell)
        pygame.draw.circle(screen, (0, 255, 255), (px, py), max(2, cell // 3))

        ang = self.current_angle()
        lx = px + int(math.cos(ang) * cell * 0.8)
        ly = py + int(math.sin(ang) * cell * 0.8)
        pygame.draw.line(screen, (0, 255, 255), (px, py), (lx, ly), 2)

    def draw_hud(self, screen, font):
        inv_txt = ", ".join(f"{k}:{v}" for k, v in self.inventory.items()) or "-"
        lines = [
            "W/UP: forward  S/DOWN: back  A/LEFT: turn left  D/RIGHT: turn right",
            "SPACE: pass door  M: minimap  ESC: quit",
            "T: toon preset  Z/X: shade steps  C/V: outline  B/N: flatness",
            "PAD: LS/D-pad move-turn  A: action  Y: minimap  Start/Back: quit",
            (
                f"toon: {TOON_PRESETS[self.toon_preset_index][0]}  "
                f"steps:{self.toon_steps}  outline:{self.toon_outline_strength:.2f}  flat:{self.toon_flatness:.2f}"
            ),
            f"map: {self.meta.get('id', '')} {self.meta.get('name', '')}  keys: {inv_txt}",
        ]
        y = SCREEN_H - 78
        for line in lines:
            img = font.render(line, True, (230, 230, 230))
            shadow = font.render(line, True, (0, 0, 0))
            screen.blit(shadow, (13, y + 1))
            screen.blit(img, (12, y))
            y += 18

    def draw(self, screen, font):
        self.draw_3d(screen)
        self.draw_minimap(screen)
        self.draw_hud(screen, font)
        self.draw_effect_overlay(screen)


# =========================
# Bootstrap
# =========================
def pick_map_path():
    candidates = [
        os.path.join(maps_dir(), "map01.json"),
        os.path.join(maps_dir(), "test_map.json"),
        os.path.join(project_root(), "map.json"),
        os.path.join(project_root(), "test_map.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("maps/map01.json か maps/test_map.json を置いてください。")


def create_game(map_path):
    return Game(map_path)


def run(map_path):
    pygame.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Map Player Stage2")
    font = pygame.font.SysFont(None, 22)

    game = create_game(map_path)

    needs_redraw = True
    last_idle_redraw = 0
    last_move_ms = 0
    last_turn_ms = 0
    joystick = init_first_joystick()
    running = True
    clock = pygame.time.Clock()

    def handle_action(action):
        nonlocal running
        changed = False
        if action == "quit":
            running = False
        elif action == "forward":
            changed = game.try_forward(screen, font)
        elif action == "backward":
            changed = game.try_backward(screen, font)
        elif action == "turn_left":
            changed = game.try_turn_left(screen, font)
        elif action == "turn_right":
            changed = game.try_turn_right(screen, font)
        elif action == "action":
            changed = game.try_space_action(screen, font)
        elif action == "toggle_map":
            game.show_map = not game.show_map
            changed = True
        return changed

    def handle_keydown(key):
        if key == pygame.K_ESCAPE:
            return handle_action("quit")
        if key in (pygame.K_UP, pygame.K_w):
            return handle_action("forward")
        if key in (pygame.K_DOWN, pygame.K_s):
            return handle_action("backward")
        if key in (pygame.K_LEFT, pygame.K_a):
            return handle_action("turn_left")
        if key in (pygame.K_RIGHT, pygame.K_d):
            return handle_action("turn_right")
        if key == pygame.K_SPACE:
            return handle_action("action")
        if key == pygame.K_m:
            return handle_action("toggle_map")
        if key == pygame.K_t:
            game.cycle_toon_preset()
            return True
        if key == pygame.K_z:
            game.adjust_toon_steps(-1)
            return True
        if key == pygame.K_x:
            game.adjust_toon_steps(1)
            return True
        if key == pygame.K_c:
            game.adjust_toon_outline(-0.08)
            return True
        if key == pygame.K_v:
            game.adjust_toon_outline(0.08)
            return True
        if key == pygame.K_b:
            game.adjust_toon_flatness(-0.08)
            return True
        if key == pygame.K_n:
            game.adjust_toon_flatness(0.08)
            return True
        return False

    while running:
        now = pygame.time.get_ticks()
        joystick = refresh_joystick(joystick)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if handle_keydown(event.key):
                    needs_redraw = True
            elif event.type == pygame.JOYDEVICEADDED:
                joystick = refresh_joystick(None)
            elif event.type == pygame.JOYDEVICEREMOVED:
                joystick = refresh_joystick(None)
            elif event.type == pygame.JOYBUTTONDOWN:
                changed = False
                if event.button == BTN_A:
                    changed = handle_action("action")
                elif event.button == BTN_Y:
                    changed = handle_action("toggle_map")
                elif event.button in (BTN_BACK, BTN_START):
                    changed = handle_action("quit")
                if changed:
                    needs_redraw = True
            elif event.type == pygame.JOYHATMOTION:
                hx, hy = event.value
                changed = False
                if hy > 0:
                    changed = handle_action("forward")
                    last_move_ms = now
                elif hy < 0:
                    changed = handle_action("backward")
                    last_move_ms = now
                elif hx < 0:
                    changed = handle_action("turn_left")
                    last_turn_ms = now
                elif hx > 0:
                    changed = handle_action("turn_right")
                    last_turn_ms = now
                if changed:
                    needs_redraw = True

        if joystick is not None and joystick.get_init():
            axis_x = axis_to_digital(joystick.get_axis(AXIS_LEFT_X))
            axis_y = axis_to_digital(joystick.get_axis(AXIS_LEFT_Y))

            if axis_y < 0 and now - last_move_ms >= MOVE_REPEAT_MS:
                if handle_action("forward"):
                    needs_redraw = True
                last_move_ms = now
            elif axis_y > 0 and now - last_move_ms >= MOVE_REPEAT_MS:
                if handle_action("backward"):
                    needs_redraw = True
                last_move_ms = now

            if axis_x < 0 and now - last_turn_ms >= TURN_REPEAT_MS:
                if handle_action("turn_left"):
                    needs_redraw = True
                last_turn_ms = now
            elif axis_x > 0 and now - last_turn_ms >= TURN_REPEAT_MS:
                if handle_action("turn_right"):
                    needs_redraw = True
                last_turn_ms = now

        if game.effect_kind:
            needs_redraw = True
        elif now - last_idle_redraw >= IDLE_REDRAW_MS:
            last_idle_redraw = now
            needs_redraw = True

        if needs_redraw:
            game.draw(screen, font)
            pygame.display.flip()
            needs_redraw = False

        clock.tick(120)

    pygame.quit()


def main(argv=None):
    map_path = resolve_map_path(argv)
    run(map_path)


if __name__ == "__main__":
    main()

