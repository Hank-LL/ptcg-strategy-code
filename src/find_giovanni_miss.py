#!/usr/bin/env python3
"""実戦リプレイから「倒せるのにサカキを使った」場面を探す。

ローカル対戦では0件だったので、**実戦の観測**で同じことが起きているかを確かめる。
サカキは自分のバトル場を強制的にベンチと入れ替えるので、
撃墜できる番に使うとその的を逃す。

  python3 find_giovanni_miss.py --dir <replays>
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
import wanaider_heuristic as W   # noqa: E402
from cg.api import to_observation_class, OptionType  # noqa: E402

GIOVANNI = 1218


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

    lethal = played = 0
    cases = []
    per_arc = collections.Counter()
    errors = 0
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
            for si, obs, act in R.iter_decisions(rep, pi):
                opts_raw = (obs.get("select") or {}).get("option") or []
                if not any(o.get("type") == OptionType.PLAY for o in opts_raw):
                    continue
                try:
                    o2 = to_observation_class(obs)
                    st = o2.current
                    me = st.players[pi]
                    op = st.players[1 - pi]
                    plan = W._build_plan(o2, st, me, op)
                    dmg = W._our_active_damage(plan, me)
                except Exception:
                    errors += 1
                    continue
                if not (dmg > 0 and plan.op_active is not None
                        and plan.op_active_hp <= dmg):
                    continue
                lethal += 1
                opts = o2.select.option or []
                for i in act:
                    if i < len(opts) and opts[i].type == OptionType.PLAY:
                        c = W.gh._hand_card(o2, opts[i].index, me)
                        if c is not None and c.id == GIOVANNI:
                            played += 1
                            per_arc[arc] += 1
                            cases.append((os.path.basename(path), si, arc,
                                          dmg, plan.op_active_hp,
                                          names.get(plan.op_active.id, "?")))

    print("=" * 66)
    print("実戦: 「バトル場で相手を倒せる」局面 %d / うち**サカキを選んだ** %d"
          % (lethal, played))
    print("=" * 66)
    if per_arc:
        print("相手別: %s" % dict(per_arc.most_common()))
    for c in cases[:12]:
        print("  %s step=%s 相手=%s 打点%d vs %s(HP%d)"
              % (c[0], c[1], c[2], c[3], c[5], c[4]))
    if errors:
        print("(観測を読めなかった局面 %d)" % errors)


if __name__ == "__main__":
    main()
