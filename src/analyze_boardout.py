#!/usr/bin/env python3
"""場切れ(ベンチが空になって負け)の機序を実戦リプレイから測る。

ラダー154試合で敗因の10%が場切れ。バトル場がきぜつしたとき控えが無ければ
その場で負けるので、**負ける数ターン前に何をしていたか**を見る。

出力:
  ・場切れ負けの試合を特定し、終盤の頭数の推移
  ・「ベンチに空きがあり、手札にたねもあったのに出さなかった」回数
  ・そのとき代わりに何を選んでいたか
  ・手札にたねが無かったなら、サーチ札(ランス/ポフィン/夜のタンカ)を持っていたか

  python3 analyze_boardout.py --dir <replays>
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

ROCKET_BASICS = {400, 414, 431, 434, 463, 432}
FINDERS = {1220: "ランス", 1086: "ポフィン", 1097: "夜のタンカ",
           1121: "ハイパーボール", 1134: "レシーバー", 1227: "リーリエ",
           1216: "アテナ"}
OPT_NAME = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY",
            12: "RETREAT", 13: "ATTACK", 14: "END", 3: "CARD"}


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
    ap.add_argument("--my-card", type=int, default=401)
    args = ap.parse_args()
    AM.ARCH = AM.build_arch()
    names = jp_names()

    games = boardout = 0
    tail_heads = []          # 場切れ試合の終盤5決定の頭数
    gap_with_basic = 0       # 空きがあり手札にたねもあった
    gap_no_basic = 0
    had_finder = 0
    chosen_instead = collections.Counter()
    opp_arc = collections.Counter()
    other_tail_heads = []

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
            dec = list(R.iter_decisions(rep, pi))
            if not dec:
                continue
            last = dec[-1][1]
            cur = last.get("current") or {}
            me = (cur.get("players") or [None, None])[pi] or {}
            bench_n = len([z for z in (me.get("bench") or []) if z])
            lost = rw[pi] != 1
            heads_seq = []
            for si, obs, act in dec:
                c2 = obs.get("current") or {}
                m2 = (c2.get("players") or [None, None])[pi] or {}
                heads_seq.append(len([z for z in (m2.get("bench") or []) if z])
                                 + len([z for z in (m2.get("active") or []) if z]))
            if not (lost and bench_n == 0):
                other_tail_heads += heads_seq[-5:]
                continue
            boardout += 1
            opp_arc[AM.archetype(R.deck_of(rep, 1 - pi) or [])] += 1
            tail_heads += heads_seq[-5:]
            # 終盤(最後の12決定)で「出せたのに出さなかった」を数える
            for si, obs, act in dec[-12:]:
                c2 = obs.get("current") or {}
                m2 = (c2.get("players") or [None, None])[pi] or {}
                hand = m2.get("hand") or []
                free = (m2.get("benchMax") or 5) - len(
                    [z for z in (m2.get("bench") or []) if z])
                if free <= 0:
                    continue
                basics = [c for c in hand
                          if isinstance(c, dict) and c.get("id") in ROCKET_BASICS]
                opts = (obs.get("select") or {}).get("option") or []
                played_basic = False
                for i in act:
                    if i < len(opts) and opts[i].get("type") == 7:
                        idx = opts[i].get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict) and c.get("id") in ROCKET_BASICS:
                            played_basic = True
                if basics:
                    if not played_basic:
                        gap_with_basic += 1
                        for i in act:
                            if i < len(opts):
                                o = opts[i]
                                nm = OPT_NAME.get(o.get("type"), str(o.get("type")))
                                cid = None
                                if o.get("type") in (7, 8) and isinstance(
                                        o.get("index"), int) and o["index"] < len(hand):
                                    c = hand[o["index"]]
                                    cid = c.get("id") if isinstance(c, dict) else None
                                chosen_instead["%s:%s" % (nm, names.get(cid, ""))] += 1
                else:
                    gap_no_basic += 1
                    if any(isinstance(c, dict) and c.get("id") in FINDERS
                           for c in hand):
                        had_finder += 1

    def avg(a):
        return sum(a) / len(a) if a else 0.0

    print("=" * 66)
    print("%d試合中 **場切れ負け %d試合 (%.0f%%)**"
          % (games, boardout, 100.0 * boardout / max(games, 1)))
    print("=" * 66)
    print("終盤5決定の頭数  場切れ試合 %.2f / それ以外 %.2f"
          % (avg(tail_heads), avg(other_tail_heads)))
    print("相手: %s" % dict(opp_arc.most_common(6)))
    print("\n終盤12決定で「ベンチに空きがあった」局面の内訳:")
    print("  手札にたねがあったのに出さなかった  %d" % gap_with_basic)
    print("  手札にたねが無かった                %d" % gap_no_basic)
    print("    └ うちサーチ/ドロー札は持っていた %d (%.0f%%)"
          % (had_finder, 100.0 * had_finder / max(gap_no_basic, 1)))
    if chosen_instead:
        print("\n  たねを出さずに選んだ手(上位8):")
        for k, c in chosen_instead.most_common(8):
            print("    %-28s %3d" % (k, c))


if __name__ == "__main__":
    main()
