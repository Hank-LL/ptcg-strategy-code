#!/usr/bin/env python3
"""「盤面の頭数」がなぜ足りないのかを実戦リプレイから切り分ける。

ロケットラッシュは 30×頭数 なので、頭数はそのまま打点。
実測で勝ち5.5 / 負け4.5 と差が出ているが、**原因が
「出せるのに出していない」なのか「手札にたねが無い」なのか**で
打ち手がまったく違う。攻撃した瞬間の状態で切り分ける。

  python3 meas_board_width.py --dir <replays> [--only オーロンゲex,Archaludon]
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
import analyze_matchup as AM     # noqa: E402

SPIDOPS, TAROUNTULA = 401, 400
ROCKET_BASICS = {400, 414, 431, 434, 463, 432}


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
    ap.add_argument("--dir", required=True)
    ap.add_argument("--my-card", type=int, default=SPIDOPS)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    AM.ARCH = AM.build_arch()
    names = jp_names()
    only = {s for s in args.only.split(",") if s}
    import generic_heuristic as gh

    n_games = 0
    atk_heads = []            # 攻撃した瞬間の頭数
    atk_bench_free = []       # そのときのベンチの空き
    could_play = 0            # 空きがあり、手札にたねもあった攻撃
    atk_n = 0
    basics_played = []        # 1試合に出したたねの数
    basics_lost = []          # ベンチで落とされた数
    hand_basic_when_gap = collections.Counter()   # 空きがあるとき手札のたね枚数
    per_arc = collections.defaultdict(lambda: [0, 0.0])

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            arc = AM.archetype(R.deck_of(rep, 1 - pi) or [])
            if only and arc not in only:
                continue
            n_games += 1
            played = lost = 0
            prev_serials = set()
            for si, obs, act in R.iter_decisions(rep, pi):
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                bench = [z for z in (me.get("bench") or []) if z]
                active = [z for z in (me.get("active") or []) if z]
                heads = len(bench) + len(active)
                free = (me.get("benchMax") or 5) - len(bench)
                hand = me.get("hand") or []
                n_basic_hand = sum(1 for c in hand
                                   if isinstance(c, dict) and c.get("id") in ROCKET_BASICS)
                cur_serials = {z.get("serial") for z in bench}
                lost += len(prev_serials - cur_serials)
                prev_serials = cur_serials
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i >= len(opts):
                        continue
                    o = opts[i]
                    if o.get("type") == 7:
                        c = hand[o.get("index")] if (
                            isinstance(o.get("index"), int)
                            and o.get("index") < len(hand)) else None
                        if isinstance(c, dict) and c.get("id") in ROCKET_BASICS:
                            played += 1
                    if o.get("type") == 13:
                        atk_n += 1
                        atk_heads.append(heads)
                        atk_bench_free.append(free)
                        if free > 0:
                            hand_basic_when_gap[min(n_basic_hand, 3)] += 1
                            if n_basic_hand > 0:
                                could_play += 1
                        per_arc[arc][0] += 1
                        per_arc[arc][1] += heads
            basics_played.append(played)
            basics_lost.append(lost)

    def avg(a):
        return sum(a) / len(a) if a else 0.0

    print("=" * 68)
    print("%d試合 / 攻撃 %d回" % (n_games, atk_n))
    print("=" * 68)
    print("攻撃した瞬間の頭数        平均 %.2f" % avg(atk_heads))
    print("そのときのベンチの空き    平均 %.2f" % avg(atk_bench_free))
    gaps = sum(1 for x in atk_bench_free if x > 0)
    print("ベンチに空きがある攻撃    %d / %d (%.0f%%)"
          % (gaps, atk_n, 100.0 * gaps / max(atk_n, 1)))
    print("  └ そのうち**手札にたねがあった**(=出せたのに出していない) %d (%.0f%%)"
          % (could_play, 100.0 * could_play / max(gaps, 1)))
    print("  └ 空きがあるときの手札のたね枚数の分布: %s"
          % dict(sorted(hand_basic_when_gap.items())))
    print("\n1試合あたり たねを出した数 %.2f / ベンチで失った数 %.2f"
          % (avg(basics_played), avg(basics_lost)))
    print("\n--- 相手別の「攻撃時の頭数」 ---")
    for arc, (c, tot) in sorted(per_arc.items(), key=lambda kv: -kv[1][0]):
        if c >= 10:
            print("  %-18s %4d回  %.2f" % (arc, c, tot / c))


if __name__ == "__main__":
    main()
