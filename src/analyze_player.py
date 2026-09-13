#!/usr/bin/env python3
"""あるプレイヤーの「デッキと戦略」をリプレイから丸ごと洗い出す。

新しいデッキを真似するときの入口。出すもの:
  ・使っている60枚(最多構築)と、そのバリエーション
  ・勝率と、**どうやって勝っているか**(サイド / 相手の山札切れ / 相手の場切れ)
  ・1試合あたりの ワザ / カード×行動 の頻度
  ・自分と相手の終局時の山札枚数

  python3 analyze_player.py --dir <replays> --team hikarimaru
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

ACTION_NAME = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY",
               12: "RETREAT", 13: "ATTACK", 14: "END"}


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
    ap.add_argument("--team", required=True)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    AM.ARCH = AM.build_arch()
    names = jp_names()
    try:
        from cg.api import all_attack
        atk = {a.attackId: a.name for a in all_attack()}
    except Exception:
        atk = {}

    decks = collections.Counter()
    games = wins = 0
    usage = collections.Counter()
    attacks = collections.Counter()
    end_deck_mine, end_deck_op = [], []
    how_won = collections.Counter()
    how_lost = collections.Counter()
    vs = collections.defaultdict(lambda: [0, 0])
    turns = []

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        teams = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            if teams[pi] != args.team:
                continue
            deck = R.deck_of(rep, pi)
            if not deck:
                continue
            games += 1
            won = rw[pi] == 1
            wins += 1 if won else 0
            decks[tuple(sorted(deck))] += 1
            vs[AM.archetype(R.deck_of(rep, 1 - pi) or [])][0] += 1
            vs[AM.archetype(R.deck_of(rep, 1 - pi) or [])][1] += 1 if won else 0
            last = None
            for si, obs, act in R.iter_decisions(rep, pi):
                last = obs
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                hand = me.get("hand") or []
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i >= len(opts):
                        continue
                    o = opts[i]
                    t = o.get("type")
                    if t == 13:
                        attacks[o.get("attackId")] += 1
                    elif t == 7:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict):
                            usage[("PLAY", c.get("id"))] += 1
                    elif t in (9, 10):
                        usage[(ACTION_NAME[t], None)] += 1
            if last:
                cur = last.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                op = (cur.get("players") or [None, None])[1 - pi] or {}
                dm, do = me.get("deckCount") or 0, op.get("deckCount") or 0
                end_deck_mine.append(dm)
                end_deck_op.append(do)
                turns.append(cur.get("turn") or 0)
                bench_op = len([z for z in (op.get("bench") or []) if z])
                tag = ("相手の山札切れ" if do <= 1 else
                       "相手の場切れ" if bench_op == 0 and not (op.get("active") or [None])[0]
                       else "サイドを取り切った")
                (how_won if won else how_lost)[
                    tag if won else ("自分の山札切れ" if dm <= 1 else "サイドを取られた")] += 1

    g = max(games, 1)
    print("=" * 66)
    print("%s : %d試合 勝率 %.0f%%  (構築 %d種)"
          % (args.team, games, 100.0 * wins / g, len(decks)))
    print("=" * 66)
    if decks:
        best, n = decks.most_common(1)[0]
        c = collections.Counter(best)
        print("\n--- 最多構築 (%d試合) ---" % n)
        line = ", ".join("%s×%d" % (names.get(x, x), y)
                         for x, y in sorted(c.items(), key=lambda kv: -kv[1]))
        print("  " + line)
    print("\n--- 相手別 ---")
    for a, (t, w) in sorted(vs.items(), key=lambda kv: -kv[1][0]):
        print("   %-16s %3d戦 %3d勝 (%.0f%%)" % (a, t, w, 100.0 * w / max(t, 1)))
    print("\n--- 勝ち方 / 負け方 ---")
    for k, v in how_won.most_common():
        print("   勝ち: %-16s %3d" % (k, v))
    for k, v in how_lost.most_common():
        print("   負け: %-16s %3d" % (k, v))
    print("\n終局時の山札  自分 %.1f / 相手 %.1f   平均 %.1f ターン"
          % (sum(end_deck_mine) / max(len(end_deck_mine), 1),
             sum(end_deck_op) / max(len(end_deck_op), 1),
             sum(turns) / max(len(turns), 1)))
    print("\n--- ワザ(1試合あたり) ---")
    for aid, c2 in attacks.most_common(8):
        print("   %-26s %.2f" % (atk.get(aid, aid), c2 / g))
    print("\n--- よく使うカード(1試合あたり) ---")
    for (t, cid), c2 in usage.most_common(args.top):
        if cid is None:
            continue
        print("   %-26s %.2f" % (names.get(cid, cid), c2 / g))


if __name__ == "__main__":
    main()
