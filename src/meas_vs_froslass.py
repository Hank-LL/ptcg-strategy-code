#!/usr/bin/env python3
"""対メガユキメノコexの機序を測る。

うらみのハミングは **相手(=こちら)の手札1枚につき50**。
つまりこちらの「ターンを終えた瞬間の手札枚数」がそのまま被弾になる。
どの駒が前にいるときに落とされているか(サイドを何枚渡したか)も併せて数える。

  python3 meas_vs_froslass.py --games 30
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

FROSLASS = 861


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
    ap.add_argument("--opp", default="mega_starmie_top")
    ap.add_argument("--games", type=int, default=30)
    args = ap.parse_args()

    import importlib
    my = importlib.import_module(args.agent)
    names = jp_names()
    from cg.api import all_attack
    atk = {a.attackId: a.name for a in all_attack()}
    refrain = next((k for k, v in atk.items() if v == "Resentful Refrain"), None)

    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    opp = pool[args.opp]
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    endhand = []
    victim = collections.Counter()
    prizes_given = 0
    refrain_n = 0
    win = n = 0
    for g in range(args.games):
        first = g % 2
        my.reset_state()
        opp["reset"]()
        d0, d1 = (deck, opp["deck"]) if first == 0 else (opp["deck"], deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        try:
            s = 0
            while obs["current"]["result"] == -1 and s < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == first:
                    act = my.agent(obs)
                    opts = (obs.get("select") or {}).get("option") or []
                    me = obs["current"]["players"][pl]
                    for i in act:
                        if i < len(opts) and opts[i].get("type") in (13, 14):
                            endhand.append(len(me.get("hand") or []))
                    obs = battle_select(act)
                else:
                    act = opp["agent"](obs)
                    opts = (obs.get("select") or {}).get("option") or []
                    for i in act:
                        if i < len(opts) and opts[i].get("attackId") == refrain:
                            refrain_n += 1
                            tgt = (obs["current"]["players"][first]
                                   .get("active") or [None])[0]
                            if tgt:
                                # そのとき前にいた駒(=落とされる駒)
                                victim[tgt.get("id")] += 1
                                d = None
                                try:
                                    import generic_heuristic as gh
                                    d = gh._CARD.get(tgt.get("id"))
                                except Exception:
                                    pass
                                nonlocal_p = 3 if (d and d.megaEx) else 2 if (d and d.ex) else 1
                                globals()["_pg"] = globals().get("_pg", 0) + nonlocal_p
                    obs = battle_select(act)
                s += 1
            r = obs["current"]["result"]
            n += 1
            win += 1 if r == first else 0
        finally:
            battle_finish()

    prizes_given = globals().get("_pg", 0)
    print("=" * 60)
    print("対 %s  %d試合  勝率 %.0f%%" % (args.opp, n, 100.0 * win / max(n, 1)))
    print("=" * 60)
    if endhand:
        big = sum(1 for x in endhand if x >= 6)
        print("ターンを終えた瞬間の手札: 平均 %.2f 枚 (最大 %d, %d回)"
              % (sum(endhand) / len(endhand), max(endhand), len(endhand)))
        print("  → うらみのハミング換算 平均 %.0f 打点"
              % (50.0 * sum(endhand) / len(endhand)))
        print("  6枚以上でターンを渡した割合: %.0f%% (ミュウツーexHP280が落ちる圏)"
              % (100.0 * big / len(endhand)))
    print("うらみのハミングを撃たれた回数: %.2f/試合" % (refrain_n / max(n, 1)))
    print("そのとき前にいた駒(=落とされる駒) / 渡したサイド計 %d:" % prizes_given)
    for cid, c in victim.most_common(8):
        print("   %-24s %3d" % (names.get(cid, cid), c))


if __name__ == "__main__":
    main()
