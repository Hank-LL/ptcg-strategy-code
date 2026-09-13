#!/usr/bin/env python3
"""リプレイから「どのチームがどのデッキを使っているか」を索引する。

相手役ヒューリスティックを作るとき、まず**そのデッキの上位使用者**を見つけて
リプレイをまとめて落とす必要がある。リーダーボードにはデッキ情報が無いので、
リプレイの `steps[1][player]["action"]`(=提出した60枚)から判定する。
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

# 代表カードでアーキタイプを判定(先に一致した方を採る)
ARCHETYPES = [
    ("メガルカリオex", {678}),
    ("ブリジュラスex", {1003}),      # 実行時にIDを解決
    ("メガスターミーex", {56}),
    ("ドラパルトex", {121}),
    ("ワナイダー", {401}),
    ("オーロンゲex", {648}),
    ("フーディン", {743}),
    ("イワパレス", {345}),
    ("メガガルーラex", {66}),
]


def resolve_archetypes():
    """日本語名からIDを引き直して ARCHETYPES を確定する。"""
    import csv
    jp = {}
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                jp[r["カード名"]] = int(r["カード ID"])
            except (KeyError, TypeError, ValueError):
                pass
    fix = {
        "メガルカリオex": "メガルカリオex",
        "ブリジュラスex": "ブリジュラスex",
        "メガスターミーex": "メガスターミーex",
        "ドラパルトex": "ドラパルトex",
        "ワナイダー": "ロケット団のワナイダー",
        "オーロンゲex": "マリィのオーロンゲex",
        "フーディン": "フーディン",
        "イワパレス": "イワパレス",
        "メガガルーラex": "メガガルーラex",
    }
    out = []
    for nm, key in fix.items():
        cid = jp.get(key)
        if cid:
            out.append((nm, {cid}))
    return out or ARCHETYPES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    arcs = resolve_archetypes()
    # チーム -> アーキタイプ -> [試合, 勝ち]
    per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    by_arc = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            with open(path) as f:
                rep = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        tn = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck:
                continue
            s = set(deck)
            nm = next((a for a, ids in arcs if s & ids), None)
            if nm is None:
                continue
            per[tn[pi]][nm][0] += 1
            per[tn[pi]][nm][1] += 1 if rw[pi] == 1 else 0
            by_arc[nm][tn[pi]][0] += 1
            by_arc[nm][tn[pi]][1] += 1 if rw[pi] == 1 else 0

    print("=" * 64)
    print("アーキタイプ別の使用チーム(試合数順)")
    print("=" * 64)
    for nm in sorted(by_arc, key=lambda k: -sum(v[0] for v in by_arc[k].values())):
        tot = sum(v[0] for v in by_arc[nm].values())
        print("\n【%s】 計%d試合" % (nm, tot))
        for team, (g, w) in sorted(by_arc[nm].items(), key=lambda kv: -kv[1][0])[:6]:
            print("   %-34s %3d戦 %3d勝 (%.0f%%)"
                  % (str(team)[:34], g, w, 100.0 * w / max(g, 1)))


if __name__ == "__main__":
    main()
