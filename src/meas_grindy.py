"""長期戦相手(イワパレス/ワナイダー)への引き控えの効果測定。
勝率と、機序である「山札切れ負け率」を相手別に出す。
"""
import collections
import statistics
import sys

from cg.game import battle_start, battle_select, battle_finish
from cg.api import to_observation_class

import alakazam_heuristic as ah
import meas_alakazam_strong as M


def run(label, opps, n, reps):
    my = M.read_deck(M.MY_DECK)
    per = collections.defaultdict(lambda: [0, 0, 0])  # win, games, deckout
    rates = []
    for r in range(reps):
        w = g = 0
        for opp in opps:
            for i in range(n):
                ah.reset_state()
                if hasattr(opp, "reset_state"):
                    opp.reset_state()
                ms = i % 2
                d0, d1 = (my, opp.deck) if ms == 0 else (opp.deck, my)
                a0, a1 = (ah.agent, opp) if ms == 0 else (opp, ah.agent)
                obs, sd = battle_start(d0, d1)
                if obs is None:
                    continue
                ag = [a0, a1]
                steps = 0
                try:
                    while obs["current"]["result"] == -1 and steps < 3000:
                        pl = obs["current"]["yourIndex"]
                        obs = battle_select(ag[pl](obs))
                        steps += 1
                    o = to_observation_class(obs)
                    st = o.current
                    me = st.players[ms]
                    win = st.result == ms
                    dko = (not win) and (me.deckCount or 0) == 0
                    per[opp.name][0] += win
                    per[opp.name][1] += 1
                    per[opp.name][2] += dko
                    w += win; g += 1
                finally:
                    battle_finish()
        rates.append(w / g * 100)
    m = statistics.mean(rates)
    se = statistics.pstdev(rates) / (len(rates) ** 0.5) if len(rates) > 1 else 0
    print(f"  {label:22s} 総合 {m:5.1f}% ±{se:.1f}")
    for k, (w2, g2, d2) in per.items():
        print(f"      {k:24s} {w2/g2*100:5.1f}%  山札切れ負け {d2/g2*100:4.1f}%")
    return m


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    opps = M.build_opponents()
    ah.USE_SHAYMIN_VS_SNIPER = True
    ah.USE_ARCHETYPE_BOSS = False

    print("=== 長期戦相手への引き控え ===")
    ah.USE_GRINDY_SAFETY = False
    run("OFF(buffer=6一律)", opps, n, reps)
    ah.USE_GRINDY_SAFETY = True
    for b in (12, 18):
        ah.GRINDY_SAFETY_BUFFER = b
        run(f"ON(長期戦buffer={b})", opps, n, reps)
