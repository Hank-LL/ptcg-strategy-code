#!/usr/bin/env python3
"""実戦の山札切れ負けで「今の規則なら止められたか」を反実仮想で確かめる。

ローカル対戦では山札切れが1%しか起きず(相手が弱くて試合が短い)、
ラダーの13%を再現できない。そこで**実戦の観測をそのまま**エージェントに流し、
山札が薄い局面でドロー札を選ぶかどうかを規則ON/OFFで比べる。
同一観測なので分散ゼロで比較できる。

  python3 counterfactual_deckout.py --dir <replays>
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import replay_diff as R          # noqa: E402

DRAW_CARDS = {1216: "アテナ", 1227: "リーリエ", 1220: "ランス",
              1086: "ポフィン", 1094: "むしとりセット", 1152: "ポケパッド",
              1134: "レシーバー", 1121: "ハイパーボール", 1097: "夜のタンカ"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--my-card", type=int, default=401)
    args = ap.parse_args()
    import importlib
    mod = importlib.import_module(args.agent)

    games = deckout_games = 0
    # (規則の状態) -> 「山札が薄いのにドロー札を選んだ」回数
    picked = {True: collections.Counter(), False: collections.Counter()}
    chances = 0
    errors = 0

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            games += 1
            decisions = list(R.iter_decisions(rep, pi))
            last = decisions[-1][1] if decisions else None
            dc_end = 0
            if last:
                me = ((last.get("current") or {}).get("players")
                      or [None, None])[pi] or {}
                dc_end = me.get("deckCount") or 0
            lost = rw[pi] != 1
            if not (lost and dc_end <= 1):
                continue          # 山札切れ負けの試合だけ見る
            deckout_games += 1
            for si, obs, act in decisions:
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                dc = me.get("deckCount") or 0
                if dc > 8:
                    continue      # 「薄い」局面だけ
                opts = (obs.get("select") or {}).get("option") or []
                hand = me.get("hand") or []
                has_draw = False
                for o in opts:
                    if o.get("type") == 7 and isinstance(o.get("index"), int) \
                            and o.get("index") < len(hand):
                        c = hand[o["index"]]
                        if isinstance(c, dict) and c.get("id") in DRAW_CARDS:
                            has_draw = True
                if not has_draw:
                    continue
                chances += 1
                for on in (False, True):
                    mod.HARD_DECK_FLOOR = 4 if on else 0
                    mod.DRAW_WHEN_STUCK_MIN_DECK = 6 if on else 0
                    try:
                        mod.reset_state()
                        a = mod.agent(obs)
                    except Exception:
                        errors += 1
                        continue
                    for i in a:
                        if i < len(opts) and opts[i].get("type") == 7:
                            idx = opts[i].get("index")
                            c = hand[idx] if (isinstance(idx, int)
                                              and idx < len(hand)) else None
                            if isinstance(c, dict) and c.get("id") in DRAW_CARDS:
                                picked[on][c["id"]] += 1

    print("=" * 62)
    print("%d試合中 山札切れ負け %d試合 / 山札8枚以下でドロー札を持っていた局面 %d"
          % (games, deckout_games, chances))
    print("=" * 62)
    print("%-16s %10s %10s" % ("カード", "規則OFF", "規則ON"))
    for cid, nm in DRAW_CARDS.items():
        a, b = picked[False].get(cid, 0), picked[True].get(cid, 0)
        if a or b:
            print("%-16s %10d %10d" % (nm, a, b))
    print("%-16s %10d %10d" % ("合計", sum(picked[False].values()),
                               sum(picked[True].values())))
    if errors:
        print("(例外 %d 件)" % errors)


if __name__ == "__main__":
    main()
