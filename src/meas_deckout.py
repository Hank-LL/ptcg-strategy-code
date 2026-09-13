#!/usr/bin/env python3
"""山札切れ負けの機序を測る。

ラダー154試合で敗因の13%が山札切れ。負けた試合ではドロー系の使用が
14.78回/試合(それ以外は10.77)と**倍近く**だった。
`USE_DECK_SAFETY` があるのにどこから漏れているのかを、
「山札が薄い(safe_draws<=N)ときに何を選んだか」で特定する。

  python3 meas_deckout.py --games 60
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

DECK_SAFETY_BUFFER = 10
# 山札を減らす行動(カードID -> 減る枚数の目安)
DRAWERS = {1216: 5, 1227: 5, 1220: 3, 1086: 2, 1094: 2,
           1152: 1, 1134: 1, 1121: 1, 1097: 1}
FACTORY = 1257


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
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--thin", type=int, default=0,
                    help="safe_draws がこれ以下を「山札が薄い」とみなす")
    args = ap.parse_args()

    import importlib
    my = importlib.import_module(args.agent)
    names = jp_names()
    pool = arena.build_pool(weighted=True)
    seq = []
    for q in pool:
        seq += [q] * q["weight"]
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    n = win = deckout = 0
    thin_use = collections.Counter()      # 山札が薄いときに選んだドロー系
    thin_turns = 0
    all_use = collections.Counter()
    last_deck = []
    for g in range(args.games):
        opp = seq[g % len(seq)]
        first = g % 2
        my.reset_state()
        opp["reset"]()
        d0, d1 = (deck, opp["deck"]) if first == 0 else (opp["deck"], deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        dc = 60
        try:
            s = 0
            while obs["current"]["result"] == -1 and s < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == first:
                    cur = obs["current"]
                    me = cur["players"][pl]
                    hand = me.get("hand") or []
                    dc = me.get("deckCount") or 0
                    prize = len(me.get("prize") or [])
                    safe = max(0, dc - prize - DECK_SAFETY_BUFFER)
                    thin = safe <= args.thin
                    if thin:
                        thin_turns += 1
                    act = my.agent(obs)
                    opts = (obs.get("select") or {}).get("option") or []
                    for i in act:
                        if i >= len(opts):
                            continue
                        o = opts[i]
                        cid = None
                        if o.get("type") == 7:
                            c = hand[o.get("index")] if (
                                isinstance(o.get("index"), int)
                                and o.get("index") < len(hand)) else None
                            cid = c.get("id") if isinstance(c, dict) else None
                        elif o.get("type") == 10 and o.get("area") == 7:
                            # ★area=STADIUM(7)のときだけファクトリーの特性。
                            #   これを見ないと**ワナイダーのチャージアップまで
                            #   ファクトリーとして数えてしまう**(最初これで
                            #   「58回漏れている」と誤検出した)。
                            st = cur.get("stadium") or []
                            if st and st[0] and st[0].get("id") == FACTORY:
                                cid = FACTORY
                        if cid in DRAWERS or cid == FACTORY:
                            all_use[cid] += 1
                            if thin:
                                thin_use[cid] += 1
                    obs = battle_select(act)
                else:
                    obs = battle_select(opp["agent"](obs))
                s += 1
            n += 1
            won = obs["current"]["result"] == first
            win += 1 if won else 0
            me = obs["current"]["players"][first]
            last_deck.append(me.get("deckCount") or 0)
            if not won and (me.get("deckCount") or 0) <= 1:
                deckout += 1
        finally:
            battle_finish()

    print("=" * 62)
    print("%d試合  勝率 %.0f%%  **山札切れ負け %d (%.0f%%)**"
          % (n, 100.0 * win / max(n, 1), deckout, 100.0 * deckout / max(n, 1)))
    print("終局の山札 平均 %.1f" % (sum(last_deck) / max(len(last_deck), 1)))
    print("=" * 62)
    print("山札が薄い番(safe_draws<=%d) %d回に選んだドロー系:" % (args.thin, thin_turns))
    for cid, c in thin_use.most_common():
        print("   %-22s %4d回  (全体では %d回)"
              % (str(names.get(cid, cid))[:22], c, all_use.get(cid, 0)))
    if not thin_use:
        print("   なし(=ゲートは効いている)")


if __name__ == "__main__":
    main()
