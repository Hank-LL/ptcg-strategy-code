#!/usr/bin/env python3
"""走査済みインデックスから「帯ごとのメタ」と「特定カードの採用率」を出す。

`harvest_replays.py scan` が吐いた jsonl には 60枚デッキがそのまま入っているので、
アーキタイプは**後から付け直せる**(判定を直したら再集計するだけでよい)。

  python3 meta_by_band.py --idx '<dir>/band700_*.jsonl' --lb lb_all.csv \\
      --cards 861,666
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

import harvest_replays as H  # noqa: E402


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
    ap.add_argument("--idx", required=True, help="jsonl の glob")
    ap.add_argument("--lb", default=None)
    ap.add_argument("--cards", default="", help="採用率を見たいカードID(カンマ区切り)")
    ap.add_argument("--by-team", action="store_true",
                    help="1チーム1票にする(同じ人の試合数で歪めない)")
    args = ap.parse_args()

    H.ARCH = H.build_arch()
    names = jp_names()
    score = {}
    if args.lb and os.path.exists(args.lb):
        for r in csv.DictReader(open(args.lb)):
            score[r["teamName"]] = float(r["score"])
    cards = [int(x) for x in args.cards.split(",") if x.strip().isdigit()]

    seen = set()
    rows = []
    for fn in glob.glob(args.idx):
        for line in open(fn):
            d = json.loads(line)
            if d["episode"] in seen:
                continue
            seen.add(d["episode"])
            for pi in (0, 1):
                if d["decks"][pi]:
                    rows.append((d["teams"][pi], d["decks"][pi]))

    if args.by_team:
        # チームごとに最多構築を1票にする
        per = collections.defaultdict(collections.Counter)
        for t, dk in rows:
            per[t][tuple(sorted(dk))] += 1
        rows = [(t, list(c.most_common(1)[0][0])) for t, c in per.items()]

    arc = collections.Counter()
    card_n = collections.Counter()
    arc_of_card = collections.defaultdict(collections.Counter)
    for t, dk in rows:
        a = H.archetype(dk)
        arc[a] += 1
        for cid in cards:
            if cid in dk:
                card_n[cid] += 1
                arc_of_card[cid][a] += 1

    n = max(len(rows), 1)
    sc = [score[t] for t, _ in rows if t in score]
    print("=" * 62)
    print("対象 %d %s   レート判明 %d / 中央値 %.0f"
          % (n, "チーム" if args.by_team else "デッキ(視点)", len(sc),
             sorted(sc)[len(sc) // 2] if sc else 0))
    print("=" * 62)
    print("\n--- アーキタイプ分布 ---")
    for a, c in arc.most_common():
        print("  %-16s %4d (%4.1f%%)" % (a, c, 100.0 * c / n))
    if cards:
        print("\n--- 指定カードの採用率 ---")
        for cid in cards:
            c = card_n.get(cid, 0)
            print("  %-18s(%d) %4d (%4.1f%%)"
                  % (names.get(cid, cid), cid, c, 100.0 * c / n))
            for a, k in arc_of_card[cid].most_common(5):
                print("        └ %-14s %3d" % (a, k))


if __name__ == "__main__":
    main()
