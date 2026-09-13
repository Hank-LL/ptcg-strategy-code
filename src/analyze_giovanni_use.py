#!/usr/bin/env python3
"""上位勢が「どういう盤面でサカキを撃っているか」を条件別に洗い出す。

うちはサカキに `swap_dmg > 0`(ベンチに撃てる駒がいること)を必須にしているが、
上位勢は 0.80回/試合 使っていて、うちは 0.58回(対オーロンゲでは 0.09回)しかない。
**どの条件を緩めるべきか**をデータで決めるための道具。

サカキを出せた局面ごとに
  ・今のバトル場で相手を倒せるか (my_dmg >= 相手HP)
  ・ベンチに撃てる駒がいるか (swap_dmg > 0)
  ・引きずり出して倒せる的がいるか
を分類し、**上位勢が実際に撃った/撃たなかった**を並べる。
同じ観測をうちのエージェントにも流し、判断の差も出す。

  python3 analyze_giovanni_use.py --dir <replays> [--team kashiwashira]
"""
import argparse
import collections
import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import replay_diff as R          # noqa: E402
import wanaider_heuristic as W   # noqa: E402
from cg.api import to_observation_class, OptionType  # noqa: E402

GIOVANNI = 1218


def classify(plan, me, op):
    my = W._our_active_damage(plan, me)
    swap = W._best_bench_attacker_damage(plan, me)
    can_ko = (my > 0 and plan.op_active is not None
              and plan.op_active_hp <= my)
    best = W._best_killable_bench(op, swap) if swap > 0 else None
    # 「今の前が撃てるか」も分けて持つ(緩め方の候補になる)
    front_can_attack = my > 0
    return can_ko, front_can_attack, swap > 0, best is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--team", default=None)
    ap.add_argument("--my-card", type=int, default=401)
    args = ap.parse_args()

    used = collections.Counter()
    skipped = collections.Counter()
    ours_used = collections.Counter()
    n_chance = 0
    games = 0

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        teams = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            if args.team and teams[pi] != args.team:
                continue
            games += 1
            for si, obs, act in R.iter_decisions(rep, pi):
                raw = (obs.get("select") or {}).get("option") or []
                if not any(o.get("type") == 7 for o in raw):
                    continue
                try:
                    o2 = to_observation_class(obs)
                    st = o2.current
                    me = st.players[pi]
                    op = st.players[1 - pi]
                    opts = o2.select.option or []
                    gio_idx = [i for i, o in enumerate(opts)
                               if o.type == OptionType.PLAY
                               and (W.gh._hand_card(o2, o.index, me) or
                                    type("x", (), {"id": 0})).id == GIOVANNI]
                    if not gio_idx:
                        continue
                    plan = W._build_plan(o2, st, me, op)
                    key = classify(plan, me, op)
                except Exception:
                    continue
                n_chance += 1
                label = ("倒せる" if key[0] else
                         ("前は撃てる" if key[1] else "前は撃てない")) + \
                        (" / ベンチ○" if key[2] else " / ベンチ×") + \
                        (" / 的○" if key[3] else " / 的×")
                if any(i in gio_idx for i in act):
                    used[label] += 1
                else:
                    skipped[label] += 1
                try:
                    W.reset_state()
                    ours = W.agent(obs)
                    if any(i in gio_idx for i in ours):
                        ours_used[label] += 1
                except Exception:
                    pass

    print("=" * 78)
    print("%d試合 / サカキを出せた局面 %d" % (games, n_chance))
    print("=" * 78)
    print("%-34s %8s %8s %8s %8s"
          % ("盤面の条件", "撃った", "撃たない", "採用率", "うちなら"))
    keys = sorted(set(used) | set(skipped),
                  key=lambda k: -(used[k] + skipped[k]))
    for k in keys:
        u, s = used.get(k, 0), skipped.get(k, 0)
        print("%-34s %8d %8d %7.0f%% %8d"
              % (k, u, s, 100.0 * u / max(u + s, 1), ours_used.get(k, 0)))
    tu, ts = sum(used.values()), sum(skipped.values())
    print("%-34s %8d %8d %7.0f%% %8d"
          % ("合計", tu, ts, 100.0 * tu / max(tu + ts, 1), sum(ours_used.values())))


if __name__ == "__main__":
    main()
