#!/usr/bin/env python3
"""たねの供給(手札にたねがある番の割合・ランスの採用率・攻撃時の頭数)を測る。

ラダー実戦154試合で「自分の番の63%が手札にたね0」「ランスは提示5.62回に対し
使用0.88回(16%)」と出たので、その改善をローカルで確認するための道具。

  python3 meas_basic_supply.py --opp grimmsnarl_top --games 24
"""
import argparse
import collections
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import arena  # noqa: E402
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402

ROCKET_BASICS = {400, 414, 431, 434, 463, 432}
LANCE = 1220


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--deck", default="deck_wanaider_top2.csv")
    ap.add_argument("--opp", default="grimmsnarl_top")
    ap.add_argument("--games", type=int, default=24)
    args = ap.parse_args()

    import importlib
    my = importlib.import_module(args.agent)
    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    opp = pool[args.opp]
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    turns = zero_basic = 0
    lance_offer = lance_use = 0
    atk_heads = []
    played = 0
    win = n = 0
    for g in range(args.games):
        first = g % 2
        my.reset_state()
        opp["reset"]()
        d0, d1 = (deck, opp["deck"]) if first == 0 else (opp["deck"], deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        seen_turn = set()
        try:
            s = 0
            while obs["current"]["result"] == -1 and s < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == first:
                    cur = obs["current"]
                    me = cur["players"][pl]
                    hand = me.get("hand") or []
                    t = cur.get("turn")
                    if t not in seen_turn:
                        seen_turn.add(t)
                        turns += 1
                        if not any(c and c.get("id") in ROCKET_BASICS for c in hand):
                            zero_basic += 1
                    bench = [z for z in (me.get("bench") or []) if z]
                    act = [z for z in (me.get("active") or []) if z]
                    opts = (obs.get("select") or {}).get("option") or []
                    for o in opts:
                        if o.get("type") == 7:
                            c = hand[o.get("index")] if (
                                isinstance(o.get("index"), int)
                                and o.get("index") < len(hand)) else None
                            if c and c.get("id") == LANCE:
                                lance_offer += 1
                    a = my.agent(obs)
                    for i in a:
                        if i >= len(opts):
                            continue
                        o = opts[i]
                        if o.get("type") == 7:
                            c = hand[o.get("index")] if (
                                isinstance(o.get("index"), int)
                                and o.get("index") < len(hand)) else None
                            if c and c.get("id") == LANCE:
                                lance_use += 1
                            if c and c.get("id") in ROCKET_BASICS:
                                played += 1
                        if o.get("type") == 13:
                            atk_heads.append(len(bench) + len(act))
                    obs = battle_select(a)
                else:
                    obs = battle_select(opp["agent"](obs))
                s += 1
            n += 1
            win += 1 if obs["current"]["result"] == first else 0
        finally:
            battle_finish()

    print("対 %s  %d試合  勝率 %.0f%%" % (args.opp, n, 100.0 * win / max(n, 1)))
    print("  手札にたね0の番      %d / %d (%.0f%%)   [実戦63%%]"
          % (zero_basic, turns, 100.0 * zero_basic / max(turns, 1)))
    print("  ランス 提示%.2f / 使用%.2f (採用率 %.0f%%)   [実戦 5.62 / 0.88 = 16%%]"
          % (lance_offer / max(n, 1), lance_use / max(n, 1),
             100.0 * lance_use / max(lance_offer, 1)))
    print("  たねを出した数 %.2f/試合   攻撃時の頭数 %.2f   [実戦 5.64 / 5.27]"
          % (played / max(n, 1),
             sum(atk_heads) / max(len(atk_heads), 1)))


if __name__ == "__main__":
    main()
