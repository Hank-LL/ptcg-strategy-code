#!/usr/bin/env python3
"""あるプレイヤーの「打ち方の規則」をリプレイから逆算する。

新しいデッキのヒューリスティックを書く前に、
  ・バトル場に誰を置くか(初手/入れ替え後)
  ・各ポケモンの役割(バトル場に立つ時間・攻撃回数)
  ・各カードを**どういう状態のときに**使うか(自分/相手の手札・山札・サイド・ターン)
  ・エネルギーの付け先
  ・にげる/進化の頻度
を数える。閾値はここから決める。

  python3 analyze_play_rules.py --dir <replays> --team hikarimaru
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

import replay_diff as R  # noqa: E402

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


def _stat(obs, pi):
    cur = obs.get("current") or {}
    me = (cur.get("players") or [None, None])[pi] or {}
    op = (cur.get("players") or [None, None])[1 - pi] or {}
    return dict(
        hand=len(me.get("hand") or []),
        ophand=(len(op.get("hand") or []) if op.get("hand") is not None
                else (op.get("handCount") or 0)),
        deck=me.get("deckCount") or 0,
        opdeck=op.get("deckCount") or 0,
        prize=len(me.get("prize") or []),
        opprize=len(op.get("prize") or []),
        turn=cur.get("turn") or 0,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--team", required=True)
    args = ap.parse_args()
    names = jp_names()
    try:
        from cg.api import all_attack
        atk = {a.attackId: a.name for a in all_attack()}
    except Exception:
        atk = {}

    games = 0
    active_time = collections.Counter()
    setup_active = collections.Counter()
    bench_time = collections.Counter()
    attacks_by = collections.Counter()
    retreat = collections.Counter()
    evolve = collections.Counter()
    attach_to = collections.Counter()
    # カード -> 使ったときの状態のリスト
    when = collections.defaultdict(list)
    offered = collections.Counter()
    used = collections.Counter()
    obs_n = 0

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        teams = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            if teams[pi] != args.team:
                continue
            games += 1
            first_active = None
            for si, obs, act in R.iter_decisions(rep, pi):
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                hand = me.get("hand") or []
                a0 = (me.get("active") or [None])[0]
                if a0:
                    active_time[a0.get("id")] += 1
                    if first_active is None:
                        first_active = a0.get("id")
                for z in (me.get("bench") or []):
                    if z:
                        bench_time[z.get("id")] += 1
                obs_n += 1
                st = _stat(obs, pi)
                opts = (obs.get("select") or {}).get("option") or []
                for o in opts:
                    if o.get("type") == 7:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict):
                            offered[c.get("id")] += 1
                for i in act:
                    if i >= len(opts):
                        continue
                    o = opts[i]
                    t = o.get("type")
                    if t == 13:
                        attacks_by[(a0.get("id") if a0 else None,
                                    o.get("attackId"))] += 1
                    elif t == 12:
                        retreat[a0.get("id") if a0 else None] += 1
                    elif t == 9:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict):
                            evolve[c.get("id")] += 1
                    elif t == 8:
                        a, j = o.get("inPlayArea"), o.get("inPlayIndex") or 0
                        src = (me.get("active") if a == AREA_ACTIVE
                               else me.get("bench") if a == AREA_BENCH else None) or []
                        z = src[j] if j < len(src) else None
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(z, dict) and isinstance(c, dict):
                            attach_to[(c.get("id"), z.get("id"),
                                       "前" if a == AREA_ACTIVE else "ベ")] += 1
                    elif t == 7:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict):
                            used[c.get("id")] += 1
                            when[c.get("id")].append(st)
            if first_active:
                setup_active[first_active] += 1

    g = max(games, 1)
    print("=" * 74)
    print("%s : %d試合 / 観測 %d" % (args.team, games, obs_n))
    print("=" * 74)
    print("\n--- 初手のバトル場 ---")
    for cid, c in setup_active.most_common():
        print("   %-16s %3d (%.0f%%)" % (names.get(cid, cid), c, 100.0 * c / g))
    print("\n--- バトル場に立っていた割合 / ベンチにいた割合 ---")
    ta = max(sum(active_time.values()), 1)
    tb = max(sum(bench_time.values()), 1)
    for cid in sorted(set(active_time) | set(bench_time),
                      key=lambda k: -active_time.get(k, 0)):
        print("   %-16s 前 %5.1f%%   ベンチ %5.1f%%"
              % (names.get(cid, cid), 100.0 * active_time.get(cid, 0) / ta,
                 100.0 * bench_time.get(cid, 0) / tb))
    print("\n--- 誰がどのワザを撃ったか(1試合あたり) ---")
    for (cid, aid), c in attacks_by.most_common(8):
        print("   %-14s %-20s %.2f" % (names.get(cid, cid), atk.get(aid, aid), c / g))
    print("\n--- にげる / 進化(1試合あたり) ---")
    for cid, c in retreat.most_common(5):
        print("   にげる: %-14s %.2f" % (names.get(cid, cid), c / g))
    for cid, c in evolve.most_common(5):
        print("   進化  : %-14s %.2f" % (names.get(cid, cid), c / g))
    print("\n--- エネルギーの付け先(1試合あたり) ---")
    for (e, z, w), c in attach_to.most_common(8):
        print("   %-18s → %-12s(%s) %.2f" % (names.get(e, e), names.get(z, z), w, c / g))
    print("\n--- カードを使ったときの状態(中央値) ---")
    print("%-20s %6s %6s %7s %7s %7s %7s %7s"
          % ("カード", "使用/試", "採用率", "自手札", "相手手札", "自山", "相手山", "ターン"))
    for cid, c in used.most_common(18):
        rows = when[cid]
        if not rows:
            continue
        def med(k):
            v = sorted(r[k] for r in rows)
            return v[len(v) // 2]
        print("%-20s %6.2f %5.0f%% %7d %7d %7d %7d %7d"
              % (str(names.get(cid, cid))[:20], c / g,
                 100.0 * c / max(offered.get(cid, 0), 1),
                 med("hand"), med("ophand"), med("deck"), med("opdeck"), med("turn")))


if __name__ == "__main__":
    main()
