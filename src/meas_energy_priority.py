#!/usr/bin/env python3
"""ワナイダーの「エネルギーを育てる優先順位」をリプレイから測る。

うちの対オーロンゲの問題は「ベンチに撃てるワナイダーが居ない(84%)」で、
サカキが使えず マシマシラ を咎められない、というところまで分かっている。
**上位勢は2体目を育てているのか**を、同じ指標で突き合わせる。

出す指標(すべて1試合あたり / 自分の番あたり):
  ・手張りの行き先(バトル場のワナイダー / ベンチのワナイダー / ミュウツー / たね)
  ・チャージアップ(特性)の使用回数と、その対象(バトル場かベンチか)
  ・「ベンチに撃てるワナイダーが居る番」の割合
  ・場のワナイダーの数、トラッシュの基本エネ枚数
  ・サカキの使用回数

  python3 meas_energy_priority.py --dir <replays> [--team <名前>]
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

SPIDOPS, TAROUNTULA, MEWTWO_EX = 401, 400, 431
GIOVANNI = 1218
BASIC_ENERGY = {1, 3, 5, 2, 4, 6, 7, 8}    # 基本エネのカードID(草1/水3/超5 など)
AREA_ACTIVE, AREA_BENCH = 4, 5


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


def _dest(obs, opt, pi):
    cur = obs.get("current") or {}
    p = (cur.get("players") or [None, None])[pi] or {}
    a, i = opt.get("inPlayArea"), opt.get("inPlayIndex") or 0
    src = (p.get("active") if a == AREA_ACTIVE
           else p.get("bench") if a == AREA_BENCH else None) or []
    z = src[i] if i < len(src) else None
    return (z, a) if isinstance(z, dict) else (None, a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--team", default=None)
    ap.add_argument("--only", default="", help="この相手アーキタイプだけ")
    args = ap.parse_args()
    AM.ARCH = AM.build_arch()
    names = jp_names()
    only = {s for s in args.only.split(",") if s}

    games = turns = 0
    attach = collections.Counter()
    chargeup = collections.Counter()
    bench_ready_turns = 0
    n_spidops = collections.Counter()
    discard0 = 0
    gio = 0
    labels = collections.Counter()

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        teams = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or SPIDOPS not in deck:
                continue
            if args.team and teams[pi] != args.team:
                continue
            arc = AM.archetype(R.deck_of(rep, 1 - pi) or [])
            if only and arc not in only:
                continue
            games += 1
            labels[teams[pi]] += 1
            seen = set()
            for si, obs, act in R.iter_decisions(rep, pi):
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                t = cur.get("turn")
                if t not in seen:
                    seen.add(t)
                    turns += 1
                    bench = [z for z in (me.get("bench") or []) if z]
                    ready = [z for z in bench if z.get("id") == SPIDOPS
                             and len(z.get("energies") or []) >= 2]
                    if ready:
                        bench_ready_turns += 1
                    n_spidops[min(len([z for z in bench
                                       if z.get("id") == SPIDOPS]), 3)] += 1
                    nde = sum(1 for c in (me.get("discard") or [])
                              if isinstance(c, dict) and c.get("id") in BASIC_ENERGY)
                    if nde == 0:
                        discard0 += 1
                opts = (obs.get("select") or {}).get("option") or []
                hand = me.get("hand") or []
                for i in act:
                    if i >= len(opts):
                        continue
                    o = opts[i]
                    if o.get("type") == 8:      # ATTACH
                        z, a = _dest(obs, o, pi)
                        if z is None:
                            continue
                        where = "バトル場" if a == AREA_ACTIVE else "ベンチ"
                        attach["%s の %s" % (where, names.get(z.get("id"), "?"))] += 1
                    elif o.get("type") == 10:   # ABILITY
                        z, a = _dest(obs, o, pi)
                        if z is None:
                            src = (me.get("active") if o.get("area") == AREA_ACTIVE
                                   else me.get("bench") if o.get("area") == AREA_BENCH
                                   else None) or []
                            idx = o.get("index") or 0
                            z = src[idx] if idx < len(src) else None
                            a = o.get("area")
                        if isinstance(z, dict) and z.get("id") == SPIDOPS:
                            chargeup["バトル場" if a == AREA_ACTIVE else "ベンチ"] += 1
                    elif o.get("type") == 7:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict) and c.get("id") == GIOVANNI:
                            gio += 1

    g = max(games, 1)
    tn = max(turns, 1)
    print("=" * 64)
    print("%d試合 / 自分の番 %d回   %s" % (games, turns, dict(labels.most_common(4))))
    print("=" * 64)
    print("手張りの行き先(1試合あたり):")
    for k, c in attach.most_common(8):
        print("   %-30s %5.2f" % (k, c / g))
    print("\nチャージアップ(特性)の使用(1試合あたり): 計 %.2f"
          % (sum(chargeup.values()) / g))
    for k, c in chargeup.most_common():
        print("   %-10s %5.2f" % (k, c / g))
    print("\n★ベンチに『撃てるワナイダー』が居た番   %.0f%%" % (100.0 * bench_ready_turns / tn))
    print("  場(ベンチ)のワナイダー数の分布:")
    for k in sorted(n_spidops):
        print("     %d体 : %.0f%%" % (k, 100.0 * n_spidops[k] / tn))
    print("  トラッシュに基本エネ0の番              %.0f%%" % (100.0 * discard0 / tn))
    print("  サカキの使用                          %.2f/試合" % (gio / g))


if __name__ == "__main__":
    main()
