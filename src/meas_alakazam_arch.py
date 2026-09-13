"""シェイミ(対ベンチ狙撃)とボス積極性(アーキタイプ別)の効果測定。

対オーロンゲ(ベンチ狙撃・ex主体=両方が効くはず)と、対プール全体で測る。
機序指標(シェイミ出場率・ボス使用回数)も出して、狙った挙動が動いたか確認する。
"""
import os
import statistics
import sys

from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class, OptionType

import generic_heuristic as gh
import alakazam_heuristic as ah

POOL = "../meta/top_decks"
MY_DECK = "../meta/opponents/alakazam/deck.csv"
SHAYMIN = 343
BOSS = 1182


def read_deck(p):
    return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]


def play(my_deck, op_deck, my_side):
    """1試合。(勝ち?, シェイミ出した?, ボス使用回数)"""
    d0, d1 = (my_deck, op_deck) if my_side == 0 else (op_deck, my_deck)
    a0, a1 = (ah.agent, gh.agent) if my_side == 0 else (gh.agent, ah.agent)
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


def run(label, opp_files, n_per, reps):
    my = read_deck(MY_DECK)
    rates, shays, bosses = [], [], []
    for r in range(reps):
        w = g = s = b = 0
        for fn in opp_files:
            opp = read_deck(os.path.join(POOL, fn))
            for i in range(n_per):
                ah.reset_state()
                win, sh, bo = play(my, opp, i % 2)
                if win is None:
                    continue
                g += 1; w += win; s += sh; b += bo
        rates.append(w / g * 100); shays.append(s / g * 100); bosses.append(b / g)
    m = statistics.mean(rates)
    se = statistics.pstdev(rates) / (len(rates) ** 0.5) if len(rates) > 1 else 0
    print(f"  {label:22s} 勝率 {m:5.1f}% ±{se:.1f}  "
          f"シェイミ出場 {statistics.mean(shays):4.0f}%  ボス {statistics.mean(bosses):.2f}回/試合")
    return m


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    grimm = [f for f in sorted(os.listdir(POOL)) if "grimmsnarl" in f]
    allp = [f for f in sorted(os.listdir(POOL))
            if f.startswith("deck_") and f.endswith(".csv")]

    print(f"=== 対オーロンゲ({len(grimm)}デッキ) ===")
    ah.USE_SHAYMIN_VS_SNIPER = False; ah.USE_ARCHETYPE_BOSS = False
    run("OFF(現行)", grimm, n, reps)
    ah.USE_SHAYMIN_VS_SNIPER = True; ah.USE_ARCHETYPE_BOSS = False
    run("シェイミのみ", grimm, n, reps)
    ah.USE_SHAYMIN_VS_SNIPER = True; ah.USE_ARCHETYPE_BOSS = True
    run("シェイミ+ボス", grimm, n, reps)

    print(f"=== 対プール全体({len(allp)}デッキ) ===")
    ah.USE_SHAYMIN_VS_SNIPER = False; ah.USE_ARCHETYPE_BOSS = False
    run("OFF(現行)", allp, max(2, n // 4), reps)
    ah.USE_SHAYMIN_VS_SNIPER = True; ah.USE_ARCHETYPE_BOSS = True
    run("シェイミ+ボス", allp, max(2, n // 4), reps)
