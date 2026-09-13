"""alakazam_heuristic の USE_SETUP_V2(6ルール) を、公開フーディンAI相手に反復測定。
勝率(平均±SE)と、ルール1の機序=デッキ切れ負け率 を出す。
"""
import statistics
import sys

from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class

import generic_heuristic as gh
import alakazam_heuristic as ah
import opponent_agents as oa

PUB_DECK = "../meta/opponents/alakazam/deck.csv"


def read_deck(p):
    return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]


def play(a_me, a_op, d_me, d_op, my_side):
    """my_side=0/1 で自分の席を決めて対戦。(勝ち?, デッキ切れ負け?)を返す。"""
    d0, d1 = (d_me, d_op) if my_side == 0 else (d_op, d_me)
    a0, a1 = (a_me, a_op) if my_side == 0 else (a_op, a_me)
    obs, sd = battle_start(d0, d1)
    if obs is None:
        return None, False
    ag = [a0, a1]
    steps = 0
    try:
        while obs["current"]["result"] == -1 and steps < 3000:
            pl = obs["current"]["yourIndex"]
            obs = battle_select(ag[pl](obs))
            steps += 1
        result = obs["current"]["result"]
        # デッキ切れ判定: 自分が負け かつ 自分の山札0
        deckout = False
        try:
            o = to_observation_class(obs)
            me = o.current.players[my_side]
            if result != my_side and result != 2 and (me.deckCount or 0) == 0:
                deckout = True
        except Exception:
            pass
        return (result == my_side), deckout
    finally:
        battle_finish()


def run(label, n_games, reps):
    opps = oa.load_opponents(gh.agent)
    fu = next(o for o in opps if "alakazam" in o.name.lower())
    d_me = read_deck(PUB_DECK)
    rates, douts = [], []
    for r in range(reps):
        w = g = d = 0
        for i in range(n_games):
            ah.reset_state(); fu.reset_state()
            win, deckout = play(ah.agent, fu, d_me, fu.deck, i % 2)
            if win is None:
                continue
            g += 1; w += win; d += deckout
        rates.append(w / g * 100)
        douts.append(d / g * 100)
    m = statistics.mean(rates)
    se = statistics.pstdev(rates) / (len(rates) ** 0.5) if len(rates) > 1 else 0
    dm = statistics.mean(douts)
    print(f"{label:18s} 勝率 {m:.1f}% ±{se:.1f}  "
          f"デッキ切れ負け {dm:.1f}%   (各{n_games}×{reps}反復) {['%.0f'%x for x in rates]}")
    return m, se, dm


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print("=== USE_SETUP_V2 の効果(対 公開フーディンAI) ===")
    ah.USE_SETUP_V2 = False
    run("V2 OFF(現行)", n, reps)
    ah.USE_SETUP_V2 = True
    run("V2 ON(6ルール)", n, reps)
