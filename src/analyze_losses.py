#!/usr/bin/env python3
"""自分のリプレイから「どのデッキに、どう負けているか」を機序で出す。

ラダーのリプレイは自分の実戦そのものなので、ローカル対戦と違って
**相手が本物の上位エージェント**。負け方の分類はここからしか取れない。

出力:
  - 相手デッキのアーキタイプ別 勝率(=環境の分布と苦手マッチ)
  - 負けたときの終局状態(サイド差 / 盤面の頭数 / ターン数 / 山札)
  - 敗因の分類(山札切れ / 場切れ / 打点不足で押し切られ)
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

SPIDOPS, TAROUNTULA, MEWTWO_EX = 401, 400, 431

# ★アーキタイプ判定は harvest_replays に一本化する(2026-07-31)。
#   ここのIDは手書きで、メガルカリオex=80 / メガスターミーex=56 と**間違って**おり
#   (正しくは 678 / 1031)、イワパレスも 345 だけで **533 を取りこぼして**いた。
#   同名別IDの罠は [[ptcg-band700-meta]] 参照。
import harvest_replays as HR      # noqa: E402


def archetype(deck, names):
    if not deck:
        return "不明"
    if HR.ARCH is None:
        HR.ARCH = HR.build_arch()
    nm = HR.archetype(deck)
    if nm != "?":
        return nm
    # 代表カードで当たらなければ、最も特徴的な進化ポケモン名で代用
    from collections import Counter
    import generic_heuristic as gh
    poke = [c for c in deck if gh._CARD.get(c) is not None
            and gh._CARD[c].cardType == 0 and not gh._CARD[c].basic]
    if poke:
        return names.get(Counter(poke).most_common(1)[0][0], "不明")
    return "不明"


def final_state(rep, pi):
    """最後に観測できた自分側の状態。"""
    last = None
    for _, obs, _ in R.iter_decisions(rep, pi):
        last = obs
    if last is None:
        return {}
    cur = last.get("current") or {}
    me = (cur.get("players") or [{}])[cur.get("yourIndex", 0)] or {}
    op = (cur.get("players") or [{}, {}])[1 - cur.get("yourIndex", 0)] or {}
    bench = [e for e in (me.get("bench") or []) if isinstance(e, dict)]
    return dict(
        turn=cur.get("turn") or 0,
        my_prize=len(me.get("prize") or []),
        op_prize=len(op.get("prize") or []),
        deck=me.get("deckCount") or 0,
        board=1 + len(bench),
        hand=len(me.get("hand") or []),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--my-card", type=int, default=SPIDOPS,
                    help="自分のデッキを見分けるカードID")
    args = ap.parse_args()
    names = R.load_card_names()
    import generic_heuristic  # noqa: F401  (archetype 内で使う)

    per = collections.defaultdict(lambda: [0, 0])   # 相手archetype -> [試合, 勝ち]
    lose_state = []
    win_state = []
    cause = collections.Counter()
    n_games = 0

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        with open(path) as f:
            rep = json.load(f)
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            opp_deck = R.deck_of(rep, 1 - pi)
            arc = archetype(opp_deck, names)
            won = rw[pi] == 1
            per[arc][0] += 1
            per[arc][1] += 1 if won else 0
            n_games += 1
            st = final_state(rep, pi)
            (win_state if won else lose_state).append(st)
            if not won:
                if st.get("deck", 0) <= 1:
                    cause["山札切れ"] += 1
                elif st.get("board", 9) <= 1:
                    cause["場切れ(ベンチが空)"] += 1
                else:
                    cause["サイドを取り切られた"] += 1

    print("=" * 66)
    print("自分のラダー実戦 %d試合 (勝率 %.1f%%)"
          % (n_games, 100.0 * sum(v[1] for v in per.values()) / max(n_games, 1)))
    print("=" * 66)
    print("\n--- 相手アーキタイプ別(=環境の分布と苦手マッチ) ---")
    print("%-22s %6s %6s %8s" % ("相手", "試合", "勝ち", "勝率"))
    for arc, (g, w) in sorted(per.items(), key=lambda kv: -kv[1][0]):
        print("%-22s %6d %6d %7.0f%%" % (arc[:22], g, w, 100.0 * w / max(g, 1)))

    def avg(rows, k):
        v = [r.get(k, 0) for r in rows if r]
        return sum(v) / len(v) if v else 0

    print("\n--- 終局時の状態 ---")
    print("%-22s %10s %10s" % ("", "勝った試合", "負けた試合"))
    for k, lab in (("turn", "ターン数"), ("my_prize", "自分の残りサイド"),
                   ("op_prize", "相手の残りサイド"), ("board", "自分の頭数"),
                   ("deck", "自分の山札"), ("hand", "自分の手札")):
        print("%-22s %10.1f %10.1f" % (lab, avg(win_state, k), avg(lose_state, k)))

    print("\n--- 敗因の分類 ---")
    tot = max(sum(cause.values()), 1)
    for k, v in cause.most_common():
        print("  %-22s %4d (%.0f%%)" % (k, v, 100.0 * v / tot))


if __name__ == "__main__":
    main()
