"""強い相手だけでフーディンの改良を測る。

汎用ヒューリスティック操縦の相手では、ベンチ狙撃も育成もまともに行われないため
シェイミ/妨害ボスの価値が測れない([[ptcg-weak-opponent-overestimate]])。
そこで相手役に「本物レベル」だけを使う:
  - 公開フーディンAI (meta/opponents/alakazam, 唯一の外部の本物)
  - 自作の専用ヒューリスティック: オーロンゲ(ベンチ狙撃+ex主体) / イワパレス / ワナイダー

各改良フラグの on/off を反復測定して平均±SEで比較する。
"""
import importlib
import os
import statistics
import sys

from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class, OptionType

import generic_heuristic as gh
import alakazam_heuristic as ah
import opponent_agents as oa

POOL = "../meta/top_decks"
MY_DECK = "../meta/opponents/alakazam/deck.csv"
SHAYMIN = 343
BOSS = 1182


def read_deck(p):
    return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]


def _mk_specialist(module_name, deck_path):
    """自作の専用ヒューリスティックを相手役として使う。"""
    m = importlib.import_module(module_name)
    deck = read_deck(deck_path)

    def fn(obs):
        return m.agent(obs)

    def reset():
        if hasattr(m, "reset_state"):
            m.reset_state()
    fn.reset_state = reset
    fn.deck = deck
    fn.name = module_name
    return fn


def build_opponents():
    opps = []
    ext = oa.load_opponents(gh.agent)
    fu = next((o for o in ext if "alakazam" in o.name.lower()), None)
    if fu is not None:
        opps.append(fu)
    for mod, deck in [
        ("grimmsnarl_heuristic", f"{POOL}/deck_grimmsnarl.csv"),
        ("crustle_heuristic", f"{POOL}/deck_iwaparesu.csv"),
        ("wanaider_heuristic", f"{POOL}/deck_wanaider_top.csv"),
    ]:
        try:
            opps.append(_mk_specialist(mod, deck))
        except Exception as e:
            print(f"  [skip] {mod}: {e}")
    return opps


def play(my_deck, opp, my_side):
    d0, d1 = (my_deck, opp.deck) if my_side == 0 else (opp.deck, my_deck)
    a0, a1 = (ah.agent, opp) if my_side == 0 else (opp, ah.agent)
    obs, sd = battle_start(d0, d1)
    if obs is None:
        return None, False, 0
    ag = [a0, a1]
    steps = 0
    shay = False
    boss = 0
    try:
        while obs["current"]["result"] == -1 and steps < 3000:
            pl = obs["current"]["yourIndex"]
            if pl == my_side:
                sel = obs["select"]
                act = ah.agent(obs)
                try:
                    o = to_observation_class(obs)
                    me = o.current.players[my_side]
                    for c in list(me.active or []) + list(me.bench or []):
                        if c is not None and c.id == SHAYMIN:
                            shay = True
                    if sel.get("option") and act:
                        opt = sel["option"][act[0]]
                        if opt.get("type") == OptionType.PLAY:
                            c = gh._hand_card(o, opt.get("index"), me)
                            if c is not None and c.id == BOSS:
                                boss += 1
                except Exception:
                    pass
                obs = battle_select(act)
            else:
                obs = battle_select(ag[pl](obs))
            steps += 1
        return (obs["current"]["result"] == my_side), shay, boss
    finally:
        battle_finish()


def run(label, opps, n_per, reps, per_opp=False):
    my = read_deck(MY_DECK)
    rates, shays, bosses = [], [], []
    detail = {o.name: [0, 0] for o in opps}
    for r in range(reps):
        w = g = s = b = 0
        for opp in opps:
            for i in range(n_per):
                ah.reset_state()
                if hasattr(opp, "reset_state"):
                    opp.reset_state()
                win, sh, bo = play(my, opp, i % 2)
                if win is None:
                    continue
                g += 1; w += win; s += sh; b += bo
                detail[opp.name][0] += win; detail[opp.name][1] += 1
        rates.append(w / g * 100); shays.append(s / g * 100); bosses.append(b / g)
    m = statistics.mean(rates)
    se = statistics.pstdev(rates) / (len(rates) ** 0.5) if len(rates) > 1 else 0
    print(f"  {label:20s} 勝率 {m:5.1f}% ±{se:.1f}  "
          f"シェイミ {statistics.mean(shays):3.0f}%  ボス {statistics.mean(bosses):.2f}回")
    if per_opp:
        for k, (w2, g2) in detail.items():
            if g2:
                print(f"      vs {k:24s} {w2}/{g2} = {w2/g2*100:.0f}%")
    return m


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    opps = build_opponents()
    print(f"相手({len(opps)}種, 全て本物レベル): {[o.name for o in opps]}")

    print("=== 改良の効果(強い相手のみ) ===")
    ah.USE_SHAYMIN_VS_SNIPER = False; ah.USE_ARCHETYPE_BOSS = False
    run("OFF(現行)", opps, n, reps, per_opp=True)
    ah.USE_SHAYMIN_VS_SNIPER = True; ah.USE_ARCHETYPE_BOSS = False
    run("シェイミのみ", opps, n, reps)
    ah.USE_SHAYMIN_VS_SNIPER = False; ah.USE_ARCHETYPE_BOSS = True
    run("妨害ボスのみ", opps, n, reps)
    ah.USE_SHAYMIN_VS_SNIPER = True; ah.USE_ARCHETYPE_BOSS = True
    run("両方ON", opps, n, reps, per_opp=True)
