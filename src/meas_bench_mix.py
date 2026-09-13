#!/usr/bin/env python3
"""ベンチに何を並べているかを相手別に測る。

ベンチ狙撃(オーロンゲのシャドーバレット30 / メガスターミーのジェットブロー50 /
キチキギスexの100)は**頭数=打点**のワナイダーに直接効く。
「HPの低い駒(ミミッキュHP60)を並べていないか」「狙撃で実際に落ちているか」を数える。

  python3 meas_bench_mix.py --opp mega_starmie_top --games 30
"""
import argparse
import collections
import csv
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import arena  # noqa: E402
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402

# 進化後のHP(タマンチュラは進化するとHP130になる)
EVOLVED_HP = {400: 130}


def jp_names():
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            out[int(r["カード ID"])] = r["カード名"]
        except (KeyError, TypeError, ValueError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--deck", default="deck_wanaider_top2.csv")
    ap.add_argument("--opp", required=True)
    ap.add_argument("--games", type=int, default=30)
    args = ap.parse_args()

    import importlib
    my = importlib.import_module(args.agent)
    names = jp_names()
    import generic_heuristic as gh
    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    opp = pool[args.opp]
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    # ベンチに「いた回数」(観測ごと)と、置いた回数(PLAY)
    on_bench = collections.Counter()
    played = collections.Counter()
    ko_on_bench = collections.Counter()
    obs_n = 0
    win = n = 0
    for g in range(args.games):
        first = g % 2
        my.reset_state()
        opp["reset"]()
        d0, d1 = (deck, opp["deck"]) if first == 0 else (opp["deck"], deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        prev_bench = {}
        try:
            s = 0
            while obs["current"]["result"] == -1 and s < 3000:
                pl = obs["current"]["yourIndex"]
                mine_side = (pl == first)
                me = obs["current"]["players"][first]
                bench = [z for z in (me.get("bench") or []) if z]
                cur = {z.get("serial"): z.get("id") for z in bench}
                # 前の観測にいて今いない = きぜつ(ベンチで落ちた)
                for ser, cid in prev_bench.items():
                    if ser not in cur:
                        ko_on_bench[cid] += 1
                prev_bench = cur
                if mine_side:
                    obs_n += 1
                    for z in bench:
                        on_bench[z.get("id")] += 1
                    act = my.agent(obs)
                    opts = (obs.get("select") or {}).get("option") or []
                    for i in act:
                        if i < len(opts) and opts[i].get("type") == 7:
                            c = gh._hand_card(
                                __import__("cg.api", fromlist=["x"])
                                .to_observation_class(obs),
                                opts[i].get("index"),
                                __import__("cg.api", fromlist=["x"])
                                .to_observation_class(obs)
                                .current.players[pl])
                            if c is not None:
                                played[c.id] += 1
                    obs = battle_select(act)
                else:
                    obs = battle_select(opp["agent"](obs))
                s += 1
            r = obs["current"]["result"]
            n += 1
            win += 1 if r == first else 0
        finally:
            battle_finish()

    print("=" * 66)
    print("対 %s  %d試合  勝率 %.0f%%" % (args.opp, n, 100.0 * win / max(n, 1)))
    print("=" * 66)
    print("%-22s %6s %8s %8s %8s"
          % ("ベンチの駒", "HP", "在場率", "出した回数", "ベンチで落ちた"))
    for cid, c in on_bench.most_common():
        d = gh._CARD.get(cid)
        hp = (d.hp if d else 0) or 0
        ev = EVOLVED_HP.get(cid)
        hp_s = "%d→%d" % (hp, ev) if ev else str(hp)
        print("%-22s %6s %7.2f %8.2f %8.2f"
              % (str(names.get(cid, cid))[:22], hp_s,
                 c / max(obs_n, 1), played.get(cid, 0) / max(n, 1),
                 ko_on_bench.get(cid, 0) / max(n, 1)))
    tot_ko = sum(ko_on_bench.values())
    print("\nベンチで落ちた合計 %.2f/試合" % (tot_ko / max(n, 1)))


if __name__ == "__main__":
    main()
