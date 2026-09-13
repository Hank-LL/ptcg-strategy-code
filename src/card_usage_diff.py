#!/usr/bin/env python3
"""デッキの各カードを「上位者と同じように使えているか」をカード単位で突き合わせる。

replay_diff.py が (context, OptionType) 単位なのに対し、こちらは**カード単位**。
同じ観測で「そのカードを使う選択肢が出ていた回数(提示)」と
「実際に選んだ回数(採用)」を上位者とうちで並べる。

  提示に対する採用率が上位者より低い → そのカードを使いこなせていない
  採用率が高すぎる                   → 無駄撃ちしている疑い

  python3 card_usage_diff.py --dir <replays> --agent wanaider --team flg \
      --require-card 401 --our-deck ../meta/top_decks/deck_wanaider_top2.csv
"""
import argparse
import collections
import glob
import importlib
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import replay_diff as R  # noqa: E402

# 「カードを使う」行動だけを見る。ATTACK/END/RETREAT は別軸なので除く。
CARD_ACTION_TYPES = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY"}


def option_card_id(obs, opt):
    """MAIN の選択肢が指しているカードID。EVOLVE/PLAY は手札を引く。"""
    cid = R._card_id_at(obs, opt)
    # 場のポケモンは中身がリストのことがある(進化を重ねた山)。先頭が現在のカード。
    while isinstance(cid, (list, tuple)) and cid:
        cid = cid[0]
    if isinstance(cid, dict):
        cid = cid.get("id") or cid.get("cardId")
    return cid if isinstance(cid, int) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--team", default=None)
    ap.add_argument("--require-card", type=int, default=None)
    ap.add_argument("--our-deck", required=True)
    ap.add_argument("--min-offer", type=int, default=8,
                    help="提示回数がこれ未満のカードは表示しない")
    args = ap.parse_args()

    mod = importlib.import_module({
        "grimmsnarl": "grimmsnarl_heuristic",
        "wanaider": "wanaider_heuristic",
        "alakazam": "alakazam_heuristic",
        "generic": "generic_heuristic",
    }[args.agent])
    names = R.load_card_names()
    with open(args.our_deck) as f:
        deck_counts = collections.Counter(
            int(l.strip()) for l in f if l.strip().isdigit())

    offered = collections.Counter()   # カード -> 提示された局面数
    took_top = collections.Counter()  # 上位者が選んだ回数
    took_our = collections.Counter()  # うちが選んだ回数
    n_dec = 0

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        with open(path) as f:
            replay = json.load(f)
        team_names = (replay.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            if args.team and team_names[pi] != args.team:
                continue
            deck = R.deck_of(replay, pi)
            if args.require_card is not None:
                if not deck or args.require_card not in deck:
                    continue
            for si, obs, act in R.iter_decisions(replay, pi):
                if obs["select"].get("context") != 0:
                    continue
                opts = obs["select"]["option"]
                try:
                    ours = mod.agent(obs)
                except Exception:
                    continue
                n_dec += 1
                # この局面で「使える」カードを重複なく数える
                # ★キーは (カード, 行動種別)。カードだけで数えると、
                #   「場に出ているスタジアムを参照する特性の選択肢」まで
                #   そのカードの提示として数えてしまい、採用率が不当に下がる
                #   (ファクトリーで実測: 見かけ354提示のうち実際にプレイ可能
                #    だったのは一部だけだった)。
                seen = set()
                for o in opts:
                    if o.get("type") not in CARD_ACTION_TYPES:
                        continue
                    cid = option_card_id(obs, o)
                    if cid:
                        seen.add((cid, o.get("type")))
                for key in seen:
                    offered[key] += 1
                for i in act:
                    if 0 <= i < len(opts) and opts[i].get("type") in CARD_ACTION_TYPES:
                        cid = option_card_id(obs, opts[i])
                        if cid:
                            took_top[(cid, opts[i].get("type"))] += 1
                for i in ours:
                    if 0 <= i < len(opts) and opts[i].get("type") in CARD_ACTION_TYPES:
                        cid = option_card_id(obs, opts[i])
                        if cid:
                            took_our[(cid, opts[i].get("type"))] += 1

    print("=" * 84)
    print("カード単位の使い方 (MAIN文脈 %d局面 / 同じ観測での比較)" % n_dec)
    print("=" * 84)
    print("%-27s %-7s %4s %6s %9s %8s %7s"
          % ("カード", "行動", "枚", "提示", "上位者採用", "うち採用", "差"))
    rows = []
    for key, off in offered.items():
        if off < args.min_offer:
            continue
        a = 100.0 * took_top.get(key, 0) / off
        b = 100.0 * took_our.get(key, 0) / off
        rows.append((b - a, key, off, a, b))
    for d, (cid, ty), off, a, b in sorted(rows, key=lambda r: -abs(r[0])):
        mark = "  <<< 使えていない" if d < -8 else ("  <<< 使いすぎ" if d > 8 else "")
        print("%-27s %-7s %4d %6d %8.1f%% %8.1f%% %+6.1f%s"
              % (str(names.get(cid, cid))[:27], CARD_ACTION_TYPES.get(ty, ty),
                 deck_counts.get(cid, 0), off, a, b, d, mark))


if __name__ == "__main__":
    main()
