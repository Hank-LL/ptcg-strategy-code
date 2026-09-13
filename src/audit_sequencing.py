#!/usr/bin/env python3
"""「手札を流す前に、使うべき札を先に使う」の順序ミスを洗い出す。

ジャッジマン/リーリエ/クラウンのように**手札を山に戻す**札を撃つと、
その時点で手札にあった札は全部消える。その中に「その番に使えて、
使う価値があった札」が混ざっていたら順序ミス。

サポートは1ターン1枚しか使えないので、流す札と同時には使えない(除外)。
対象は **グッズ / どうぐ / スタジアム / エネルギー**。

  python3 audit_sequencing.py --agent ogerpon_heuristic --deck deck_ogerpon.csv
"""
import argparse
import collections
import csv
import importlib
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import generic_heuristic as gh  # noqa: E402
from cg.api import OptionType, SelectContext, AreaType  # noqa: E402

# 手札を山に戻す札
# ★クセロシキは**相手の**手札を捨てさせる札。自分の手札は流れないので対象外
SHUFFLERS = {1213: "ジャッジマン", 1227: "リーリエの決心", 1223: "クラウン"}
# サポート(cardType=3)は同時に使えないので順序ミスに数えない
SKIP_TYPES = (3,)


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
    ap.add_argument("--agent", required=True)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--min-score", type=float, default=1000.0,
                    help="この点数以上なら『使う価値があった』とみなす")
    args = ap.parse_args()

    import arena
    jp = jp_names()
    mod = importlib.import_module(args.agent)
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))
    pool = arena.build_pool(weighted=True)

    lost = collections.Counter()
    plays = collections.Counter()
    scores = {}
    ob = mod._bonus
    a0 = mod.agent

    def bw(o, obs, state, me, op, p, ctx=None):
        v = ob(o, obs, state, me, op, p, ctx)
        if o.type in (OptionType.PLAY, OptionType.ATTACH,
                      OptionType.TOOL_CARD) and ctx == SelectContext.MAIN:
            c = gh._hand_card(obs, o.index, me)
            if c is not None:
                scores[(id(obs), o.index, int(o.type))] = (c.id, v)
        return v

    def wrapped(obs):
        sel = obs.get("select") or {}
        opts = sel.get("option") or []
        ci = (obs.get("current") or {}).get("yourIndex")
        me = (obs.get("current") or {}).get("players")[ci]
        hand = me.get("hand") or []
        scores.clear()
        act = a0(obs)
        # 流す札を撃ったか
        shuffled = None
        for i in act:
            if i < len(opts) and opts[i].get("type") == int(OptionType.PLAY):
                idx = opts[i].get("index")
                c = hand[idx] if isinstance(idx, int) and idx < len(hand) else None
                if isinstance(c, dict) and c.get("id") in SHUFFLERS:
                    shuffled = c["id"]
        if shuffled is None:
            return act
        plays[SHUFFLERS[shuffled]] += 1
        # そのとき手札にあって「使う価値があった」札
        seen = set()
        for (_, idx, ty), (cid, v) in scores.items():
            if cid == shuffled or cid in seen:
                continue
            cd = gh._CARD.get(cid)
            if cd is None or cd.cardType in SKIP_TYPES:
                continue
            if v >= args.min_score:
                seen.add(cid)
                lost[(SHUFFLERS[shuffled], jp.get(cid, "?"), round(v))] += 1
        return act

    mod._bonus = bw
    mod.agent = wrapped
    for g in range(args.games):
        arena.play(mod, deck, pool[g % len(pool)], g % 2)
    mod._bonus = ob
    mod.agent = a0

    print("=" * 74)
    print("%s / %s  %d試合" % (args.agent, args.deck, args.games))
    print("=" * 74)
    print("手札を流した回数: %s" % dict(plays))
    if not lost:
        print("\n順序ミス: なし(流す前に使うべき札は残っていなかった)")
        return
    print("\n流す札と一緒に消えた『使う価値があった札』(点数=そのときの評価)")
    print("%-14s %-22s %7s %6s"
          % ("流した札", "一緒に消えた札", "点数", "回数"))
    tot = 0
    for (sh, nm, v), n in lost.most_common(20):
        print("%-14s %-22s %7d %6d" % (sh, nm, v, n))
        tot += n
    print("\n合計 %d回 (%.2f回/試合)" % (tot, tot / args.games))


if __name__ == "__main__":
    main()
