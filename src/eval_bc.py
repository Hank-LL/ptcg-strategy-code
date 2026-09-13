"""BC-Fuudin の棋力を実戦で測る。alakazam_heuristic と比較。

相手:
  - 本物フーディンAI(meta/opponents/alakazam, 公開5位)
  - 弱プール11デッキ(generic操縦)
"""
import os
import sys

from cg.game import battle_start, battle_select, battle_finish

import generic_heuristic as gh
import opponent_agents as oa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL_DIR = os.path.join(ROOT, "meta", "top_decks")
FUUDIN_DECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuudin_deck.csv")
ALA_DECK = os.path.join(ROOT, "meta", "opponents", "alakazam", "deck.csv")


def read_deck(p):
    lines = [x for x in open(p).read().split("\n") if x.strip()]
    return [int(x) for x in lines[:60]]


def one(a0, a1, d0, d1):
    obs, sd = battle_start(list(d0), list(d1))
    if obs is None:
        return -1
    ag = [a0, a1]
    steps = 0
    try:
        while obs["current"]["result"] == -1 and steps < 3000:
            pl = obs["current"]["yourIndex"]
            obs = battle_select(ag[pl](obs))
            steps += 1
        return obs["current"]["result"]
    finally:
        battle_finish()


def vs_fuudin(name, pilot, deck, n):
    opps = oa.load_opponents(gh.agent)
    fu = next(o for o in opps if "alakazam" in o.name.lower())
    wins = games = 0
    for i in range(n):
        fu.reset_state()
        if i % 2 == 0:
            r = one(pilot, fu, deck, fu.deck); win = (r == 0)
        else:
            r = one(fu, pilot, fu.deck, deck); win = (r == 1)
        if r >= 0:
            games += 1; wins += win
    print(f"  {name:26s} vs 本物フーディン: {wins}/{games} = {wins/games*100:.1f}%")


def vs_pool(name, pilot, deck, n_per):
    pool = [f for f in sorted(os.listdir(POOL_DIR))
            if f.startswith("deck_") and f.endswith(".csv")]
    wins = games = 0
    for fn in pool:
        opp = read_deck(os.path.join(POOL_DIR, fn))
        for i in range(n_per):
            if i % 2 == 0:
                r = one(pilot, gh.agent, deck, opp); win = (r == 0)
            else:
                r = one(gh.agent, pilot, opp, deck); win = (r == 1)
            if r >= 0:
                games += 1; wins += win
    print(f"  {name:26s} vs プール({len(pool)}): {wins}/{games} = {wins/games*100:.1f}%")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    import bc_agent
    import alakazam_heuristic as ah
    deck_bc = read_deck(FUUDIN_DECK)
    deck_ala = read_deck(ALA_DECK)

    print("=== 対 本物フーディン ===")
    vs_fuudin("BC-Fuudin", bc_agent.agent, deck_bc, n)
    vs_fuudin("alakazam_heuristic", ah.agent, deck_ala, n)
    print("=== 対 弱プール ===")
    vs_pool("BC-Fuudin", bc_agent.agent, deck_bc, max(4, n // 25))
    vs_pool("alakazam_heuristic", ah.agent, deck_ala, max(4, n // 25))
