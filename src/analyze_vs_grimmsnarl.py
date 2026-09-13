#!/usr/bin/env python3
"""対オーロンゲ(自分の帯で24%・勝率29%)の敗因を実戦リプレイから切り分ける。

オーロンゲ系は**3種とも草弱点**なのでロケットラッシュは2倍。
ただし マリィのオーロンゲex は HP320 で、
  30 × 頭数 × 2 ≧ 320 → **頭数6が必要**(頭数5なら300で1点足りない)。
本当に「頭数6に届いていない」のが原因かを数える。

  python3 analyze_vs_grimmsnarl.py --dir <replays>
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

GRIMMSNARL_EX, MORGREM, IMPIDIMP = 648, 647, 646
SPIDOPS, MEWTWO_EX = 401, 431


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
    args = ap.parse_args()
    AM.ARCH = AM.build_arch()
    names = jp_names()
    from cg.api import all_attack
    atk = {a.attackId: a.name for a in all_attack()}

    games = wins = 0
    heads_vs_ex = collections.Counter()   # オーロンゲexが前にいるときの攻撃の頭数
    heads_all = []
    ohko_chance = ohko_done = 0
    target_of_attack = collections.Counter()
    op_attacks = collections.Counter()
    my_ko_victim = collections.Counter()  # 相手の何を倒したか
    lost_mewtwo = 0

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
            if AM.archetype(R.deck_of(rep, 1 - pi) or []) != "オーロンゲex":
                continue
            games += 1
            wins += 1 if rw[pi] == 1 else 0
            prev_op = {}
            for si, obs, act in R.iter_decisions(rep, pi):
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                op = (cur.get("players") or [None, None])[1 - pi] or {}
                heads = (len([z for z in (me.get("active") or []) if z])
                         + len([z for z in (me.get("bench") or []) if z]))
                oa = (op.get("active") or [None])[0]
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i < len(opts) and opts[i].get("type") == 13:
                        heads_all.append(heads)
                        if oa:
                            target_of_attack[oa.get("id")] += 1
                            if oa.get("id") == GRIMMSNARL_EX:
                                heads_vs_ex[heads] += 1
                                ohko_chance += 1
                                if heads >= 6:
                                    ohko_done += 1
                # 相手の場から消えた = 倒した
                cur_op = {z.get("serial"): z.get("id")
                          for z in ((op.get("active") or []) + (op.get("bench") or []))
                          if z}
                for ser, cid in prev_op.items():
                    if ser not in cur_op:
                        my_ko_victim[cid] += 1
                prev_op = cur_op
            for si, obs, act in R.iter_decisions(rep, 1 - pi):
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i < len(opts) and opts[i].get("type") == 13:
                        op_attacks[opts[i].get("attackId")] += 1

    n = max(games, 1)
    print("=" * 64)
    print("対オーロンゲ %d試合 勝率 %.0f%%" % (games, 100.0 * wins / n))
    print("=" * 64)
    print("攻撃時の頭数 平均 %.2f"
          % (sum(heads_all) / max(len(heads_all), 1)))
    print("\nオーロンゲex(HP320)に攻撃した %d 回の頭数分布:" % ohko_chance)
    for h in sorted(heads_vs_ex):
        mark = "  ← 2倍で360、1発で落ちる" if h >= 6 else "  (2倍でも%d、届かない)" % (30 * h * 2)
        print("   頭数%d : %3d 回%s" % (h, heads_vs_ex[h], mark))
    print("   → **頭数6で殴れた割合 %.0f%%**" % (100.0 * ohko_done / max(ohko_chance, 1)))
    print("\n自分が殴った相手(1試合あたり):")
    for cid, c in target_of_attack.most_common(6):
        print("   %-22s %.2f" % (names.get(cid, cid), c / n))
    print("\n自分が倒した相手(1試合あたり):")
    for cid, c in my_ko_victim.most_common(6):
        print("   %-22s %.2f" % (names.get(cid, cid), c / n))
    print("\n相手のワザ(1試合あたり):")
    for aid, c in op_attacks.most_common(5):
        print("   %-22s %.2f" % (atk.get(aid, aid), c / n))


if __name__ == "__main__":
    main()
