#!/usr/bin/env python3
"""ベンチ狙撃デッキ相手に、上位ワナイダー勢が何をしているかを見る。

## 背景
自分のラダー90試合で 対ドラパルト17% / 対メガルカリオ35% と負け越し、
敗因は「盤面の頭数」(勝ち5.8 / 負け4.3)だった。
削っているのは ファントムダイブ(200 + ベンチにダメカン6個)、
Jetting Blow(120 + ベンチ50)、シャドーバレット(180 + ベンチ30)。

相手AIを手書きして再現するのは失敗した([[ptcg-ladder-meta-and-arena]])ので、
**上位者が同じ相手にどう対処しているか**を直接観察する。

## 見るもの
1. 上位勢の対狙撃デッキ勝率(そもそも勝てているのか)
2. **ベンチの構成**: たね(フリーザーで守れる)と1進化(守れない)の比率
3. フリーザーの設置率
4. ダメカンが実際どこに置かれたか(相手視点の選択を読む)
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
import card_usage_diff as C      # noqa: E402

SPIDOPS, TAROUNTULA, MEWTWO_EX = 401, 400, 431
ARTICUNO, MIMIKYU, MURKROW, WOBBUFFET = 414, 434, 463, 432
BASIC_ROCKETS = {TAROUNTULA, MEWTWO_EX, ARTICUNO, MIMIKYU, MURKROW, WOBBUFFET}

SNIPERS = {
    "ドラパルト": {119, 120, 121},
    "オーロンゲex": {648},
    "メガルカリオex": {678},
    "キチキギスex入り": {140},
}


def _id(e):
    return e.get("id") if isinstance(e, dict) else None


def my_field(obs):
    cur = obs.get("current") or {}
    me = (cur.get("players") or [{}])[cur.get("yourIndex", 0)] or {}
    act = (me.get("active") or [None])[0]
    bench = [e for e in (me.get("bench") or []) if isinstance(e, dict)]
    return act, bench


def analyze(files, team=None, snipe_key=None):
    names = R.load_card_names()
    per = collections.defaultdict(lambda: [0, 0])
    comp = collections.Counter()
    snaps = 0
    art_on = 0
    basics = 0
    stage1 = 0
    board = []
    for path in sorted(files):
        with open(path) as f:
            rep = json.load(f)
        tn = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or SPIDOPS not in deck:
                continue
            if team and tn[pi] != team:
                continue
            od = R.deck_of(rep, 1 - pi)
            arcs = [nm for nm, ids in SNIPERS.items() if od and set(od) & ids]
            arc = arcs[0] if arcs else "狙撃なし"
            if snipe_key and arc != snipe_key:
                continue
            per[arc][0] += 1
            per[arc][1] += 1 if rw[pi] == 1 else 0
            for _, obs, act in R.iter_decisions(rep, pi):
                a, b = my_field(obs)
                fld = ([a] if isinstance(a, dict) else []) + b
                if not fld:
                    continue
                snaps += 1
                board.append(len(fld))
                if any(_id(e) == ARTICUNO for e in fld):
                    art_on += 1
                for e in fld:
                    cid = _id(e)
                    if cid in BASIC_ROCKETS:
                        basics += 1
                        comp[names.get(cid, cid)] += 1
                    elif cid == SPIDOPS:
                        stage1 += 1
                        comp["Spidops(1進化=守れない)"] += 1
    return per, comp, snaps, art_on, basics, stage1, board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--team")
    ap.add_argument("--snipe", help="ドラパルト等に絞る")
    args = ap.parse_args()
    per, comp, snaps, art, basics, st1, board = analyze(
        glob.glob(os.path.join(args.dir, "*.json")), args.team, args.snipe)
    print("=" * 62)
    print("上位ワナイダー勢 vs 狙撃デッキ%s" % (" (%s)" % args.team if args.team else ""))
    print("=" * 62)
    print("%-20s %6s %6s %8s" % ("相手", "試合", "勝ち", "勝率"))
    for arc, (g, w) in sorted(per.items(), key=lambda kv: -kv[1][0]):
        print("%-20s %6d %6d %7.0f%%" % (arc[:20], g, w, 100.0 * w / max(g, 1)))
    if not snaps:
        return
    print("\n--- 盤面の作り方 (%d局面) ---" % snaps)
    print("  平均の頭数          %.2f" % (sum(board) / len(board)))
    print("  フリーザーが場にいる率 %.0f%%" % (100.0 * art / snaps))
    tot = basics + st1
    print("  たね(守れる) %.0f%% / ワナイダー(1進化=守れない) %.0f%%"
          % (100.0 * basics / max(tot, 1), 100.0 * st1 / max(tot, 1)))
    print("\n  内訳:")
    for k, v in comp.most_common(8):
        print("    %-32s %5d (%.2f体/局面)" % (str(k)[:32], v, v / snaps))


if __name__ == "__main__":
    main()
