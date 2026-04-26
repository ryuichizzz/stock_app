from __future__ import annotations
import random
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# =============================
# Config（まずここだけ調整）
# =============================
START_CT_JITTER = 20

# 命中率（簡易）
BASE_HIT = 0.72
AGI_HIT_COEF = 0.02
MIN_HIT = 0.10
MAX_HIT = 0.95

# ダメージ
DMG_JITTER = 2

# CT（行動後の隙）
MELEE_RECOVERY_BASE = 110
RANGED_RECOVERY_BASE = 140
DISENGAGE_RECOVERY_BASE = 160
DEFEND_RECOVERY_BASE = 80

# wind-up（発動までの準備時間）
MELEE_WINDUP = 10
RANGED_WINDUP = 40
DISENGAGE_WINDUP = 35

# 体格/重量/敏捷による調整（シンプル版）
AGI_SPEED_COEF = 2       # AGIが高いほど wind-up / recovery が減る
WEIGHT_SLOW_COEF = 1     # 重量が高いほど wind-up / recovery が増える

MIN_TIME = 5
MAX_TIME = 220

# 中断された時の「立て直し時間」
INTERRUPT_PENALTY = 25


def clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


# =============================
# Model
# =============================
@dataclass
class Unit:
    name: str
    team: str  # "P" or "E"
    max_hp: int
    hp: int
    atk: int
    agi: int
    equip_w: int = 0

    ct: int = 0  # 次イベントまでの残り時間
    engaged: Set[str] = field(default_factory=set)

    state: str = "Idle"  # "Idle" or "Preparing"
    pending_action: Optional[str] = None  # "MELEE" "RANGED" "DISENGAGE"
    pending_target: Optional[str] = None
    interruptible: bool = False  # wind-up中に中断される行動か

    @property
    def alive(self) -> bool:
        return self.hp > 0


# =============================
# Battle Core
# =============================
class Battle:
    def __init__(self, units: List[Unit], seed: int = 1):
        random.seed(seed)
        self.units: Dict[str, Unit] = {u.name: u for u in units}
        for u in self.units.values():
            u.ct = random.randint(0, START_CT_JITTER)

        self.log: List[str] = []
        self.finished: bool = False
        self.result: str = ""

        self.active_actor: Optional[str] = None  # 入力待ちの味方
        self.pending_names: List[str] = []        # 同時刻イベント群の処理キュー

    # ---------- Helpers ----------
    def teams_alive(self) -> Tuple[bool, bool]:
        p = any(u.alive and u.team == "P" for u in self.units.values())
        e = any(u.alive and u.team == "E" for u in self.units.values())
        return p, e

    def cleanup_dead(self) -> None:
        dead = {u.name for u in self.units.values() if not u.alive}
        if not dead:
            return
        for u in self.units.values():
            u.engaged.difference_update(dead)
        # 死亡者が準備中なら当然キャンセル
        for name in dead:
            if name in self.units:
                self.units[name].state = "Idle"
                self.units[name].pending_action = None
                self.units[name].pending_target = None
                self.units[name].interruptible = False

    def add_engagement(self, a: Unit, b: Unit) -> None:
        a.engaged.add(b.name)
        b.engaged.add(a.name)

    def hit_chance(self, attacker: Unit, defender: Unit) -> float:
        p = BASE_HIT + (attacker.agi - defender.agi) * AGI_HIT_COEF
        return float(max(MIN_HIT, min(MAX_HIT, p)))

    def roll_hit(self, attacker: Unit, defender: Unit) -> bool:
        return random.random() < self.hit_chance(attacker, defender)

    def roll_damage(self, attacker: Unit) -> int:
        return max(1, attacker.atk + random.randint(-DMG_JITTER, DMG_JITTER))

    def time_cost(self, base: int, u: Unit) -> int:
        # 高AGIは短縮、重量は増加（超シンプル）
        t = base - u.agi * AGI_SPEED_COEF + u.equip_w * WEIGHT_SLOW_COEF
        return clamp(t, MIN_TIME, MAX_TIME)

    def list_alive(self, team: Optional[str] = None) -> List[Unit]:
        xs = [u for u in self.units.values() if u.alive]
        if team is not None:
            xs = [u for u in xs if u.team == team]
        return sorted(xs, key=lambda x: (x.team, x.name))

    def skirmish_list(self) -> List[Unit]:
        # 遊撃 = engagedが空
        return [u for u in self.units.values() if u.alive and len(u.engaged) == 0]

    def can_melee_targets(self, attacker: Unit) -> List[Unit]:
        if not attacker.alive:
            return []
        if attacker.engaged:
            return [self.units[n] for n in sorted(attacker.engaged) if n in self.units and self.units[n].alive]
        return [u for u in self.list_alive() if u.team != attacker.team]

    def can_ranged_targets(self, attacker: Unit) -> List[Unit]:
        if not attacker.alive:
            return []
        # 遠距離は基本どこでも狙える（調整は後）
        return [u for u in self.list_alive() if u.team != attacker.team]

    def is_engaged_with(self, a: Unit, b: Unit) -> bool:
        return b.name in a.engaged

    # ---------- Interrupt rule (B) ----------
    def try_interrupt(self, target: Unit, attacker: Unit, hit: bool) -> None:
        """
        中断ルールB：
          - targetがPreparingで interruptible な行動中
          - attackerが target の交戦相手
          - その攻撃が命中(hit=True)
        のとき中断。
        """
        if not hit:
            return
        if target.state != "Preparing":
            return
        if not target.interruptible:
            return
        if not self.is_engaged_with(target, attacker):
            return

        # 中断発生
        self.log.append(f"!! 中断: {target.name} の {target.pending_action} は {attacker.name} に止められた！")
        target.state = "Idle"
        target.pending_action = None
        target.pending_target = None
        target.interruptible = False
        # 立て直しのCT（完全に0だと即再試行できて軽すぎるので少し罰）
        target.ct += INTERRUPT_PENALTY

    # ---------- Time advance ----------
    def advance_until_player_input(self) -> None:
        """
        時間を進めてイベントを処理。
        プレイヤー（P）の Idle かつ ct==0 が発生したら入力待ちに止まる。
        Preparingの実行や敵AIは自動処理。
        """
        if self.finished:
            return

        self.active_actor = None

        while True:
            self.cleanup_dead()
            p_alive, e_alive = self.teams_alive()
            if not p_alive:
                self.finished = True
                self.result = "LOSE"
                self.log.append(">>> パーティは全滅した。")
                return
            if not e_alive:
                self.finished = True
                self.result = "WIN"
                self.log.append(">>> 敵を倒した。")
                return

            # 同時イベント群が空なら、時間を進めて ct==0 の群を作る
            if not self.pending_names:
                alive_units = [u for u in self.units.values() if u.alive]
                min_ct = min(u.ct for u in alive_units)
                for u in alive_units:
                    u.ct -= min_ct

                actors = [u for u in alive_units if u.ct == 0]
                # 同時刻の処理順：AGI高い→ランダム
                random.shuffle(actors)
                actors.sort(key=lambda x: x.agi, reverse=True)
                self.pending_names = [u.name for u in actors]

            if not self.pending_names:
                continue

            name = self.pending_names.pop(0)
            if name not in self.units:
                continue
            u = self.units[name]
            if not u.alive:
                continue

            # ct==0 のイベント処理
            if u.state == "Preparing":
                # 準備完了 → 発動
                self.execute_prepared_action(u)
                continue

            # Idle の場合：敵はAIで決めて即準備開始 or 即防御
            if u.team == "E":
                self.enemy_decide_and_start(u)
                continue

            # プレイヤー（味方）は入力待ちで止める
            self.active_actor = u.name
            return

    # ---------- Action start ----------
    def start_melee(self, attacker: Unit, target_name: str) -> None:
        attacker.state = "Preparing"
        attacker.pending_action = "MELEE"
        attacker.pending_target = target_name
        attacker.interruptible = False  # 近接は中断なし（まずは）
        attacker.ct += self.time_cost(MELEE_WINDUP, attacker)
        self.log.append(f"{attacker.name} は {target_name} に近接攻撃の構え。")

    def start_ranged(self, attacker: Unit, target_name: str) -> None:
        attacker.state = "Preparing"
        attacker.pending_action = "RANGED"
        attacker.pending_target = target_name
        attacker.interruptible = True   # 遠距離は中断される
        attacker.ct += self.time_cost(RANGED_WINDUP, attacker)
        self.log.append(f"{attacker.name} は {target_name} に遠距離攻撃の構え。")

    def start_disengage(self, attacker: Unit) -> None:
        attacker.state = "Preparing"
        attacker.pending_action = "DISENGAGE"
        attacker.pending_target = None
        attacker.interruptible = True  # 離脱は中断される
        attacker.ct += self.time_cost(DISENGAGE_WINDUP, attacker)
        self.log.append(f"{attacker.name} は離脱の構え。")

    def defend(self, attacker: Unit) -> None:
        self.log.append(f"{attacker.name} は防御した。")
        attacker.ct += self.time_cost(DEFEND_RECOVERY_BASE, attacker)

    # ---------- Execute prepared ----------
    def execute_prepared_action(self, attacker: Unit) -> None:
        act = attacker.pending_action
        tgt = attacker.pending_target

        # preparing解除（発動する／しないに関わらず）
        attacker.state = "Idle"
        attacker.pending_action = None
        attacker.pending_target = None
        attacker.interruptible = False

        if act == "MELEE":
            if tgt is None or tgt not in self.units or not self.units[tgt].alive:
                self.log.append(f"{attacker.name} の近接攻撃は不発。")
            else:
                self.resolve_melee(attacker, self.units[tgt])
            attacker.ct += self.time_cost(MELEE_RECOVERY_BASE, attacker)
            return

        if act == "RANGED":
            if tgt is None or tgt not in self.units or not self.units[tgt].alive:
                self.log.append(f"{attacker.name} の遠距離攻撃は不発。")
            else:
                self.resolve_ranged(attacker, self.units[tgt])
            attacker.ct += self.time_cost(RANGED_RECOVERY_BASE, attacker)
            return

        if act == "DISENGAGE":
            self.resolve_disengage(attacker)
            attacker.ct += self.time_cost(DISENGAGE_RECOVERY_BASE, attacker)
            return

        # 何もなければ軽く待機
        attacker.ct += 10

    # ---------- Resolve actions ----------
    def resolve_melee(self, attacker: Unit, target: Unit) -> None:
        # 命中判定
        hit = self.roll_hit(attacker, target)
        if hit:
            dmg = self.roll_damage(attacker)
            target.hp -= dmg
            self.log.append(f"{attacker.name} の近接攻撃 -> {target.name}: 命中 {dmg}ダメージ (HP {max(0,target.hp)})")
            if target.hp <= 0:
                self.log.append(f"*** {target.name} は倒れた！")
        else:
            self.log.append(f"{attacker.name} の近接攻撃 -> {target.name}: ミス")

        # 近接は「命中したら」交戦リンク生成（仕様）
        if hit and target.alive:
            if target.name not in attacker.engaged:
                self.add_engagement(attacker, target)
                self.log.append(f"{attacker.name} は {target.name} と交戦状態になった！")

        # 中断チェック（ターゲット側）
        self.try_interrupt(target, attacker, hit)

    def resolve_ranged(self, attacker: Unit, target: Unit) -> None:
        # 遠距離は交戦リンクを作らない
        hit = self.roll_hit(attacker, target)
        if hit:
            dmg = self.roll_damage(attacker)
            target.hp -= dmg
            self.log.append(f"{attacker.name} の遠距離攻撃 -> {target.name}: 命中 {dmg}ダメージ (HP {max(0,target.hp)})")
            if target.hp <= 0:
                self.log.append(f"*** {target.name} は倒れた！")
        else:
            self.log.append(f"{attacker.name} の遠距離攻撃 -> {target.name}: ミス")

        # 中断チェック（ターゲット側）
        self.try_interrupt(target, attacker, hit)

    def resolve_disengage(self, attacker: Unit) -> None:
        if not attacker.engaged:
            self.log.append(f"{attacker.name} はすでに遊撃状態。")
            return

        # wind-upが通った → 交戦解除
        for enemy_name in list(attacker.engaged):
            if enemy_name in self.units:
                self.units[enemy_name].engaged.discard(attacker.name)
        attacker.engaged.clear()
        self.log.append(f"{attacker.name} は離脱に成功し、遊撃状態になった。")

    # ---------- Enemy AI ----------
    def enemy_decide_and_start(self, enemy: Unit) -> None:
        # すでにPreparingなら来ない想定（ct==0でPreparingはexecute側に入る）
        if enemy.engaged:
            # 交戦相手からランダムで近接（交戦を維持したい）
            candidates = [self.units[n] for n in enemy.engaged if n in self.units and self.units[n].alive]
            if not candidates:
                self.defend(enemy)
                return
            target = random.choice(candidates)
            self.start_melee(enemy, target.name)
            return

        # 遊撃なら：近接で捕まえに行く or 遠距離準備
        party = [u for u in self.units.values() if u.alive and u.team == "P"]
        if not party:
            self.defend(enemy)
            return
        target = random.choice(party)

        if random.random() < 0.65:
            self.start_melee(enemy, target.name)
        else:
            self.start_ranged(enemy, target.name)

    # ---------- UI helpers ----------
    def engagement_groups_text(self) -> str:
        # 交戦リンクの連結成分（交戦が存在するもの）を表示
        alive = {n for n, u in self.units.items() if u.alive}
        seen: Set[str] = set()
        groups: List[Set[str]] = []

        for n in sorted(alive):
            if n in seen:
                continue
            stack = [n]
            comp: Set[str] = set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                comp.add(cur)
                for nxt in self.units[cur].engaged:
                    if nxt in alive and nxt not in seen:
                        stack.append(nxt)
            if any(self.units[x].engaged for x in comp):
                groups.append(comp)

        lines = []
        idx = 1
        for comp in groups:
            ps = [self.units[n] for n in comp if self.units[n].alive and self.units[n].team == "P"]
            es = [self.units[n] for n in comp if self.units[n].alive and self.units[n].team == "E"]
            if not ps or not es:
                continue

            def fmt(us: List[Unit]) -> str:
                return ", ".join(f"{u.name}(⚔{len(u.engaged)})" for u in sorted(us, key=lambda x: x.name))

            lines.append(f"({idx}) {fmt(ps)}  <->  {fmt(es)}")
            idx += 1

        return "\n".join(lines) if lines else "(none)"

    def skirmish_text(self) -> str:
        xs = [u for u in self.units.values() if u.alive and len(u.engaged) == 0]
        if not xs:
            return "(none)"
        xs = sorted(xs, key=lambda x: (x.team, x.name))
        def prep(u: Unit) -> str:
            if u.state == "Preparing":
                act = u.pending_action or "?"
                tgt = f"->{u.pending_target}" if u.pending_target else ""
                return f" [準備中:{act}{tgt}]"
            return ""
        return "\n".join(f"- {u.name} [{u.team}] HP:{u.hp}/{u.max_hp} CT:{u.ct}{prep(u)}" for u in xs)


# =============================
# GUI
# =============================
class BattleApp(tk.Tk):
    def __init__(self, battle: Battle):
        super().__init__()
        self.title("戦闘テストツール")
        self.geometry("1180x740")

        self.battle = battle

        self._build_ui()
        self.battle.advance_until_player_input()
        self.refresh()

    def _build_ui(self) -> None:
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=8, pady=8)

        ttk.Label(left, text="交戦", font=("Arial", 12, "bold")).pack(anchor="w")
        self.eng_txt = tk.Text(left, width=56, height=10, wrap="word")
        self.eng_txt.pack(fill=tk.X)
        self.eng_txt.configure(state="disabled")

        ttk.Label(left, text="遊撃", font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 0))
        self.skir_txt = tk.Text(left, width=56, height=8, wrap="word")
        self.skir_txt.pack(fill=tk.X)
        self.skir_txt.configure(state="disabled")

        ttk.Label(left, text="行動中の味方", font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 0))
        self.active_lbl = ttk.Label(left, text="(なし)")
        self.active_lbl.pack(anchor="w", pady=(2, 6))

        cmd = ttk.Frame(left)
        cmd.pack(fill=tk.X)

        ttk.Label(cmd, text="対象").grid(row=0, column=0, sticky="w")
        self.target_var = tk.StringVar(value="")
        self.target_combo = ttk.Combobox(cmd, textvariable=self.target_var, state="readonly", width=30)
        self.target_combo.grid(row=0, column=1, sticky="w", padx=(6, 0))

        self.melee_btn = ttk.Button(cmd, text="近接攻撃", command=self.on_melee)
        self.melee_btn.grid(row=1, column=0, sticky="we", pady=(8, 0))

        self.ranged_btn = ttk.Button(cmd, text="遠距離攻撃", command=self.on_ranged)
        self.ranged_btn.grid(row=1, column=1, sticky="we", padx=(6, 0), pady=(8, 0))

        self.dis_btn = ttk.Button(cmd, text="離脱", command=self.on_disengage)
        self.dis_btn.grid(row=2, column=0, sticky="we", pady=(6, 0))

        self.def_btn = ttk.Button(cmd, text="防御 / 待機", command=self.on_defend)
        self.def_btn.grid(row=2, column=1, sticky="we", padx=(6, 0), pady=(6, 0))

        self.adv_btn = ttk.Button(cmd, text="時間を進める", command=self.on_advance)
        self.adv_btn.grid(row=3, column=0, columnspan=2, sticky="we", pady=(10, 0))

        right = ttk.Frame(self)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        top_lists = ttk.Frame(right)
        top_lists.pack(fill=tk.BOTH, expand=False)

        party_frame = ttk.Frame(top_lists)
        party_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(party_frame, text="味方ステータス", font=("Arial", 12, "bold")).pack(anchor="w")
        self.party_list = tk.Listbox(party_frame, height=12, width=58)
        self.party_list.pack(fill=tk.BOTH, expand=True)

        enemy_frame = ttk.Frame(top_lists)
        enemy_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        ttk.Label(enemy_frame, text="敵ステータス", font=("Arial", 12, "bold")).pack(anchor="w")
        self.enemy_list = tk.Listbox(enemy_frame, height=12, width=58)
        self.enemy_list.pack(fill=tk.BOTH, expand=True)

        ttk.Label(right, text="ログ", font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 0))
        self.log_txt = tk.Text(right, height=20, wrap="word")
        self.log_txt.pack(fill=tk.BOTH, expand=True)
        self.log_txt.configure(state="disabled")

    def refresh(self) -> None:
        b = self.battle

        self.eng_txt.configure(state="normal")
        self.eng_txt.delete("1.0", tk.END)
        self.eng_txt.insert(tk.END, b.engagement_groups_text())
        self.eng_txt.configure(state="disabled")

        self.skir_txt.configure(state="normal")
        self.skir_txt.delete("1.0", tk.END)
        self.skir_txt.insert(tk.END, b.skirmish_text())
        self.skir_txt.configure(state="disabled")

        # status lists
        self.party_list.delete(0, tk.END)
        for u in b.list_alive(team="P"):
            eng = "遊撃" if not u.engaged else ",".join(sorted(u.engaged))
            prep = ""
            if u.state == "Preparing":
                act = u.pending_action or "?"
                tgt = f"->{u.pending_target}" if u.pending_target else ""
                prep = f"  [準備:{act}{tgt}]"
            self.party_list.insert(
                tk.END,
                f"{u.name:8s} HP:{u.hp:3d}/{u.max_hp:3d} AGI:{u.agi:2d} CT:{u.ct:3d}  {eng}{prep}"
            )
        for u in sorted([x for x in b.units.values() if x.team == "P" and not x.alive], key=lambda x: x.name):
            self.party_list.insert(tk.END, f"{u.name:8s} [戦闘不能]")

        self.enemy_list.delete(0, tk.END)
        for u in b.list_alive(team="E"):
            eng = "遊撃" if not u.engaged else ",".join(sorted(u.engaged))
            prep = ""
            if u.state == "Preparing":
                act = u.pending_action or "?"
                tgt = f"->{u.pending_target}" if u.pending_target else ""
                prep = f"  [準備:{act}{tgt}]"
            self.enemy_list.insert(
                tk.END,
                f"{u.name:8s} HP:{u.hp:3d}/{u.max_hp:3d} AGI:{u.agi:2d} CT:{u.ct:3d}  {eng}{prep}"
            )
        for u in sorted([x for x in b.units.values() if x.team == "E" and not x.alive], key=lambda x: x.name):
            self.enemy_list.insert(tk.END, f"{u.name:8s} [戦闘不能]")

        # log
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0", tk.END)
        self.log_txt.insert(tk.END, "\n".join(b.log))
        self.log_txt.see(tk.END)
        self.log_txt.configure(state="disabled")

        # active actor & controls
        if b.finished:
            self.active_lbl.configure(text=f"(戦闘終了) 結果: {b.result}")
            self._set_cmd_enabled(False)
            messagebox.showinfo("戦闘終了", f"結果: {b.result}")
            return

        if b.active_actor:
            u = b.units[b.active_actor]
            eng = "遊撃" if not u.engaged else ",".join(sorted(u.engaged))
            self.active_lbl.configure(text=f"{u.name}  HP {u.hp}/{u.max_hp}  CT {u.ct}  状態 {eng}")

            # デフォは近接ターゲットを入れておく（ボタン別で許可チェック）
            melee_targets = b.can_melee_targets(u)
            # コンボは汎用に「敵全員」を入れておく（近接/遠距離で検査する）
            all_enemies = b.can_ranged_targets(u)
            names = [t.name for t in all_enemies]
            self.target_combo["values"] = names
            if names:
                if self.target_var.get() not in names:
                    self.target_var.set(names[0])
            else:
                self.target_var.set("")
            self._set_cmd_enabled(True)
        else:
            self.active_lbl.configure(text="(なし) 時間を進めてください")
            self.target_combo["values"] = []
            self.target_var.set("")
            self._set_cmd_enabled(False)

    def _set_cmd_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.melee_btn.configure(state=state)
        self.ranged_btn.configure(state=state)
        self.dis_btn.configure(state=state)
        self.def_btn.configure(state=state)

    # --------- Button handlers ----------
    def on_melee(self) -> None:
        b = self.battle
        if not b.active_actor:
            return
        attacker = b.units[b.active_actor]
        target = self.target_var.get().strip()
        if not target or target not in b.units or not b.units[target].alive:
            return

        legal = {u.name for u in b.can_melee_targets(attacker)}
        if target not in legal:
            b.log.append(f"!! 無効な近接対象: {attacker.name} は {target} を攻撃できない")
            b.defend(attacker)
        else:
            b.start_melee(attacker, target)

        b.active_actor = None
        b.advance_until_player_input()
        self.refresh()

    def on_ranged(self) -> None:
        b = self.battle
        if not b.active_actor:
            return
        attacker = b.units[b.active_actor]
        target = self.target_var.get().strip()
        if not target or target not in b.units or not b.units[target].alive:
            return

        legal = {u.name for u in b.can_ranged_targets(attacker)}
        if target not in legal:
            b.log.append(f"!! 無効な遠距離対象: {attacker.name} は {target} を攻撃できない")
            b.defend(attacker)
        else:
            b.start_ranged(attacker, target)

        b.active_actor = None
        b.advance_until_player_input()
        self.refresh()

    def on_disengage(self) -> None:
        b = self.battle
        if not b.active_actor:
            return
        attacker = b.units[b.active_actor]
        b.start_disengage(attacker)

        b.active_actor = None
        b.advance_until_player_input()
        self.refresh()

    def on_defend(self) -> None:
        b = self.battle
        if not b.active_actor:
            return
        attacker = b.units[b.active_actor]
        b.defend(attacker)

        b.active_actor = None
        b.advance_until_player_input()
        self.refresh()

    def on_advance(self) -> None:
        self.battle.advance_until_player_input()
        self.refresh()


# =============================
# Sample setup
# =============================
def make_sample_battle(seed: int = 2) -> Battle:
    party = [
        Unit("キャラA", "P", max_hp=40, hp=40, atk=8, agi=30, equip_w=4),
        Unit("キャラB", "P", max_hp=35, hp=35, atk=9, agi=18, equip_w=8),
        Unit("キャラC", "P", max_hp=28, hp=28, atk=6, agi=25, equip_w=2),
        Unit("キャラD", "P", max_hp=50, hp=50, atk=10, agi=12, equip_w=12),
    ]
    enemies = [
        Unit("敵A", "E", max_hp=38, hp=38, atk=8, agi=22, equip_w=6),
        Unit("敵B", "E", max_hp=30, hp=30, atk=7, agi=28, equip_w=3),
        Unit("敵C", "E", max_hp=45, hp=45, atk=9, agi=15, equip_w=10),
        Unit("敵D", "E", max_hp=26, hp=26, atk=6, agi=26, equip_w=2),
    ]
    return Battle(party + enemies, seed=seed)


if __name__ == "__main__":
    b = make_sample_battle(seed=2)
    app = BattleApp(b)
    app.mainloop()
