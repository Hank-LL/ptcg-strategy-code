"""ワナイダーの「準備プロセス」を機序として計測する診断。

勝率ではなく、盤面がどのターンでどこまで広がるか(go-wideの速さ)を測る。
専用(wanaider_heuristic)と汎用(generic_heuristic)を、同じワナイダーデッキで、
本物のフーディンAIを相手に走らせて比較する。

指標(自分=player0):
- max_width      : そのゲームで到達した最大ロケット団盤面数
- turn_reach4    : 盤面が初めて4に到達した自分のターン番号(未到達は None)
- charge_turns   : チャージアップ特性を使ったターン数
- attach_count   : エネルギーを付けた回数
- attack_count   : 攻撃した回数(MAIN)
- width_at_attack: 攻撃したときの盤面数(平均)
- result         : 勝敗
"""
import importlib.util
import os
import statistics
import sys

from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class, OptionType

import generic_heuristic as gh
import wanaider_heuristic as wh
import opponent_agents as oa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WANAIDER_DECK = os.path.join(ROOT, "meta", "top_decks", "deck_wanaider_top.csv")


def read_deck(path):
    with open(path) as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


def rocket_width(obs_dict, my_index):
    """自分の場のロケット団ポケモン数。"""
    try:
        obs = to_observation_class(obs_dict)
        me = obs.current.players[my_index]
        n = 0
        for c in (me.active or []):
            if c is not None and c.id in wh.ROCKET_POKEMON:
                n += 1
        for c in (me.bench or []):
            if c is not None and c.id in wh.ROCKET_POKEMON:
                n += 1
        return n, obs.current.turn
    except Exception:
        return -1, -1


class Recorder:
    """自分のagentを包んで、毎ターンの盤面幅と行動を記録する。"""

    def __init__(self, inner, my_index):
        self.inner = inner
        self.my_index = my_index
        self.max_width = 0
        self.turn_reach4 = None
        self.charge_turns = set()
        self.attach_count = 0
        self.attack_count = 0
        self.width_at_attack = []
        self.action_types = {}
        # ターン別(1..5)の行動内訳: {turn: {kind: count}}
        self.early = {t: {} for t in range(1, 6)}

    def __call__(self, obs_dict):
        w, turn = rocket_width(obs_dict, self.my_index)
        if w >= 0:
            if w > self.max_width:
                self.max_width = w
            if w >= 4 and self.turn_reach4 is None:
                self.turn_reach4 = turn
        action = self.inner(obs_dict)
        # 選んだ選択肢の種類を記録
        try:
            opts = obs_dict["select"]["option"]
            if action:
                chosen = opts[action[0]]
                ot = chosen["type"] if isinstance(chosen, dict) else chosen.type
                self.action_types[ot] = self.action_types.get(ot, 0) + 1
                # 種類ラベル(PLAYはポケ/トレーナーを分ける)
                kind = {OptionType.ATTACK: "ATK", OptionType.ATTACH: "ATT",
                        OptionType.ABILITY: "ABL", OptionType.EVOLVE: "EVO",
                        OptionType.CARD: "SRC", OptionType.RETREAT: "RET",
                        OptionType.END: "END"}.get(ot)
                if ot == OptionType.PLAY:
                    idx = chosen["index"] if isinstance(chosen, dict) else chosen.index
                    c = gh._hand_card(to_observation_class(obs_dict), idx,
                                      to_observation_class(obs_dict).current.players[self.my_index])
                    d = gh._CARD.get(c.id) if c else None
                    kind = "Pkm" if (d is not None and d.cardType == 0) else "Trn"
                if kind and 1 <= turn <= 5:
                    self.early[turn][kind] = self.early[turn].get(kind, 0) + 1
                if ot == OptionType.ATTACK:
                    self.attack_count += 1
                    self.width_at_attack.append(w)
                elif ot == OptionType.ATTACH:
                    self.attach_count += 1
                elif ot == OptionType.ABILITY:
                    self.charge_turns.add(turn)
        except Exception:
            pass
        return action


def run(pilot_name, inner_agent, n_games):
    opps = oa.load_opponents(gh.agent)
    fuudin = next((o for o in opps if "alakazam" in o.name.lower()), None)
    if fuudin is None:
        print("フーディンAIが見つからない")
        return
    deck0 = read_deck(WANAIDER_DECK)
    deck1 = fuudin.deck

    stats = {"max_width": [], "turn_reach4": [], "reached4": 0,
             "charge_turns": [], "attach_count": [], "attack_count": [],
             "width_at_attack": [], "wins": 0, "games": 0,
             "early": {t: {} for t in range(1, 6)}}

    for i in range(n_games):
        rec = Recorder(inner_agent, 0)
        wh.reset_state()
        fuudin.reset_state()
        obs, sd = battle_start(deck0, deck1)
        if obs is None:
            continue
        agents = [rec, fuudin]
        steps = 0
        try:
            while obs["current"]["result"] == -1 and steps < 3000:
                pl = obs["current"]["yourIndex"]
                obs = battle_select(agents[pl](obs))
                steps += 1
            result = obs["current"]["result"]
        finally:
            battle_finish()

        stats["games"] += 1
        if result == 0:
            stats["wins"] += 1
        stats["max_width"].append(rec.max_width)
        if rec.turn_reach4 is not None:
            stats["reached4"] += 1
            stats["turn_reach4"].append(rec.turn_reach4)
        stats["charge_turns"].append(len(rec.charge_turns))
        stats["attach_count"].append(rec.attach_count)
        stats["attack_count"].append(rec.attack_count)
        stats["width_at_attack"].extend(rec.width_at_attack)
        for t in range(1, 6):
            for k, v in rec.early[t].items():
                stats["early"][t][k] = stats["early"][t].get(k, 0) + v

    g = stats["games"]
    print(f"\n=== {pilot_name} ({g}試合, 対フーディンAI) ===")
    print(f"勝率           : {stats['wins']/g*100:.1f}%")
    print(f"最大盤面幅 平均 : {statistics.mean(stats['max_width']):.2f} "
          f"(中央{statistics.median(stats['max_width']):.0f})")
    print(f"盤面4到達率     : {stats['reached4']/g*100:.1f}%")
    if stats["turn_reach4"]:
        print(f"盤面4到達ターン : {statistics.mean(stats['turn_reach4']):.1f}")
    print(f"チャージ使用ターン数/試合: {statistics.mean(stats['charge_turns']):.2f}")
    print(f"エネ付け回数/試合: {statistics.mean(stats['attach_count']):.2f}")
    print(f"攻撃回数/試合   : {statistics.mean(stats['attack_count']):.2f}")
    if stats["width_at_attack"]:
        print(f"攻撃時の盤面幅 平均: {statistics.mean(stats['width_at_attack']):.2f}")
    print("ターン別 行動内訳/試合 (Pkm=ポケ展開 Trn=トレーナー ATT=エネ SRC=サーチ選択):")
    for t in range(1, 6):
        parts = " ".join(f"{k}{v/g:.2f}" for k, v in
                         sorted(stats["early"][t].items(), key=lambda x: -x[1]))
        print(f"  T{t}: {parts}")
    return stats


# ---- 実験: 展開は汎用に完全委譲し、攻撃規律だけ専用で上書きする ----
def minimal_overlay_agent(obs_dict):
    """generic の展開順をそのまま使い、ATTACK のときだけ
    「盤面が広がるまで非致死のロケットラッシュを我慢」する薄い上書き。"""
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]
        p = wh._build_plan(obs, state, me, op)

        scores = []
        for o in select.option:
            base = gh._score_option(o, obs, me, op)
            extra = 0.0
            if o.type == OptionType.ATTACK:
                aid = o.attackId
                rush = p.rocket_count * 30
                if aid == wh.ATK_ROCKET_RUSH:
                    lethal = p.op_active is not None and p.op_active_hp <= rush
                    wide = p.rocket_count >= wh.WIDE_ENOUGH
                    if not (lethal and wide):
                        # 展開を優先(generic の PLAY/EVOLVE より下げる)
                        extra = -1500.0
            scores.append(base + extra)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)


# ---- 実験C: 汎用の速い展開 + 専用のエネ・ルーティング/チャージ、攻撃我慢なし ----
def routed_agent(obs_dict):
    """展開順は generic に任せ、ATTACH(エネ配分)と ABILITY(チャージ)だけ
    専用ロジックを上乗せする。攻撃は generic のまま(致死で殴る)。"""
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]
        wh._update_turn_state(state)
        p = wh._build_plan(obs, state, me, op)

        scores = []
        for o in select.option:
            base = gh._score_option(o, obs, me, op)
            extra = 0.0
            # エネ配分とチャージだけ専用の判断を足す(展開・攻撃は generic のまま)
            if o.type in (OptionType.ATTACH, OptionType.ABILITY):
                extra = wh._bonus(o, obs, state, me, op, p)
                base = 0.0   # これらは専用スコアで順位付け
            scores.append(base + extra)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                c = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if c is not None and c.id == wh.SPIDOPS:
                    wh._used_chargeup = True
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    if mode == "routed":
        run("汎用展開+エネ配分(C)", routed_agent, n)
        sys.exit(0)
    if mode in ("all", "spec"):
        run("専用 wanaider_heuristic", wh.agent, n)
    if mode in ("all", "gen"):
        run("汎用 generic_heuristic", gh.agent, n)
    if mode in ("all", "min"):
        run("薄い上書き(汎用展開+攻撃規律)", minimal_overlay_agent, n)
