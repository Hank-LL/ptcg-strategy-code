#!/usr/bin/env python3
"""守りの札(アセロラ / ニュートラルセンター / シェイミ)の**使い時**を逆算する。

どれも1〜2枚しかなく、切ってしまうと戻らない。
「提示されたのに温存した局面」と「実際に切った局面」を並べて条件を出す。

  python3 analyze_defense_timing.py --dir <replays> --team hikarimaru
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

ACEROLA, NEUTRAL_CENTER, SHAYMIN = 1228, 1247, 343
CARDS = {ACEROLA: "アセロラのいたずら", NEUTRAL_CENTER: "ニュートラルセンター",
         SHAYMIN: "シェイミ"}


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
    args = ap.parse_args()
    names = jp_names()
    import generic_heuristic as gh

    used = collections.defaultdict(list)
    held = collections.defaultdict(list)
    protected = collections.Counter()
    games = 0

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
            pending = None
            for si, obs, act in R.iter_decisions(rep, pi):
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                op = (cur.get("players") or [None, None])[1 - pi] or {}
                hand = me.get("hand") or []
                opts = (obs.get("select") or {}).get("option") or []
                # アセロラの直後の選択 = 守る対象
                if pending is not None:
                    for i in act:
                        if i < len(opts):
                            o = opts[i]
                            src = (me.get("active") if o.get("area") == 4
                                   else me.get("bench") if o.get("area") == 5
                                   else None) or []
                            j = o.get("index") or 0
                            z = src[j] if j < len(src) else None
                            if isinstance(z, dict):
                                protected["%s(%s)" % (
                                    names.get(z.get("id"), "?"),
                                    "前" if o.get("area") == 4 else "ベンチ")] += 1
                    pending = None
                st_id = None
                try:
                    stad = cur.get("stadium") or []
                    st_id = stad[0].get("id") if stad and stad[0] else None
                except Exception:
                    st_id = None
                # 相手が ex/V を場に出しているか(ニュートラルセンターの価値)
                op_field = [z for z in ((op.get("active") or [])
                                        + (op.get("bench") or [])) if z]
                op_has_ex = any((gh._CARD.get(z.get("id")) is not None
                                 and (gh._CARD[z["id"]].ex
                                      or gh._CARD[z["id"]].megaEx))
                                for z in op_field)
                a0 = (me.get("active") or [None])[0]
                snap = dict(
                    turn=cur.get("turn") or 0,
                    myprize=len(me.get("prize") or []),
                    opprize=len(op.get("prize") or []),
                    stadium=("自分" if st_id == NEUTRAL_CENTER else
                             "相手/他" if st_id else "無し"),
                    op_ex=op_has_ex,
                    act_hp=(a0.get("hp") if a0 else 0),
                    bench=len([z for z in (me.get("bench") or []) if z]),
                )
                offered = set()
                for o in opts:
                    if o.get("type") == 7:
                        idx = o.get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict) and c.get("id") in CARDS:
                            offered.add(c["id"])
                taken = set()
                for i in act:
                    if i < len(opts) and opts[i].get("type") == 7:
                        idx = opts[i].get("index")
                        c = hand[idx] if (isinstance(idx, int)
                                          and idx < len(hand)) else None
                        if isinstance(c, dict) and c.get("id") in CARDS:
                            taken.add(c["id"])
                            if c["id"] == ACEROLA:
                                pending = True
                for cid in offered:
                    (used if cid in taken else held)[cid].append(snap)

    print("=" * 70)
    print("%s : %d試合" % (args.team, games))
    print("=" * 70)
    for cid, nm in CARDS.items():
        u, h = used[cid], held[cid]
        tot = len(u) + len(h)
        print("\n--- %s : 提示%d回 / 使用%d回 (%.0f%%) ---"
              % (nm, tot, len(u), 100.0 * len(u) / max(tot, 1)))
        if not u:
            continue

        def dist(rows, key):
            c = collections.Counter(r[key] for r in rows)
            return " / ".join("%s:%d" % (k, v) for k, v in
                              sorted(c.items(), key=lambda kv: str(kv[0])))

        def med(rows, key):
            v = sorted(r[key] for r in rows)
            return v[len(v) // 2] if v else 0
        print("   使った  : ターン中央値%d 相手サイド中央値%d 自分ベンチ中央値%d"
              % (med(u, "turn"), med(u, "opprize"), med(u, "bench")))
        print("             スタジアム %s" % dist(u, "stadium"))
        print("             相手にex/Vが居た %.0f%%"
              % (100.0 * sum(1 for r in u if r["op_ex"]) / len(u)))
        if h:
            print("   温存した: ターン中央値%d 相手サイド中央値%d"
                  % (med(h, "turn"), med(h, "opprize")))
            print("             スタジアム %s" % dist(h, "stadium"))
            print("             相手にex/Vが居た %.0f%%"
                  % (100.0 * sum(1 for r in h if r["op_ex"]) / len(h)))
    if protected:
        print("\n--- アセロラで守った対象 ---")
        for k, c in protected.most_common(8):
            print("   %-24s %3d" % (k, c))


if __name__ == "__main__":
    main()
