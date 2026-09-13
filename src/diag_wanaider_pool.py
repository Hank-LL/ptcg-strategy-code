"""ワナイダーを対弱プール(11デッキ、汎用操縦)で評価。
専用/汎用/薄い上書き の3者を同条件で比較する。
"""
import os
import sys

from cg.game import battle_start, battle_select, battle_finish

import generic_heuristic as gh
import wanaider_heuristic as wh
from diag_wanaider_setup import (read_deck, minimal_overlay_agent,
                                 routed_agent, WANAIDER_DECK)

POOL_DIR = os.path.join(os.path.dirname(WANAIDER_DECK))
POOL = [f for f in sorted(os.listdir(POOL_DIR))
        if f.startswith("deck_") and f.endswith(".csv")
        and f not in ("deck_wanaider_top.csv", "deck_wanaider.csv")]


def one(a0, a1, d0, d1):
    obs, sd = battle_start(d0, d1)
    if obs is None:
        return -1
    agents = [a0, a1]
    steps = 0
    try:
        while obs["current"]["result"] == -1 and steps < 3000:
            pl = obs["current"]["yourIndex"]
            obs = battle_select(agents[pl](obs))
            steps += 1
        return obs["current"]["result"]
    finally:
        battle_finish()


def run(name, pilot, n_per_deck):
    my = read_deck(WANAIDER_DECK)
    wins = games = 0
    for fn in POOL:
        opp = read_deck(os.path.join(POOL_DIR, fn))
        for i in range(n_per_deck):
            wh.reset_state()
            # 先後を交互に
            if i % 2 == 0:
                r = one(pilot, gh.agent, my, opp)
                win = (r == 0)
            else:
                r = one(gh.agent, pilot, opp, my)
                win = (r == 1)
            if r >= 0:
                games += 1
                wins += win
    print(f"{name:28s}: {wins}/{games} = {wins/games*100:.1f}% (対{len(POOL)}デッキ)")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run("専用 wanaider", wh.agent, n)
    run("汎用 generic", gh.agent, n)
    run("薄い上書き(攻撃規律)", minimal_overlay_agent, n)
    run("汎用展開+エネ配分(C)", routed_agent, n)
