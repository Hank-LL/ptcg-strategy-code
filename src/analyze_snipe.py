#!/usr/bin/env python3
"""キチキギスex の Cruel Arrow(任意の1体に100)によるベンチ狙撃への対応を調べる。

Cruel Arrow は「相手のポケモン1体に100ダメージ」。100で1発で落ちるのは
  タマンチュラ HP50 / ミミッキュ HP60 / ヤミカラス HP80
ワナイダー(130)・フリーザー(120)・ソーナンス(110)は1発耐える。
ロケットラッシュは 30×場のロケット団数 なので、ベンチを削られると打点も落ちる。

フリーザーのレジストヴェールは「ワザの**効果**」を防ぐが
「ダメージは効果ではない」と明記されているので、狙撃ダメージは通るはず。
→ ここでは**実データで確認する**(フリーザーが場にいる状態で
   たねが削られているかを数える)。
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
ARTICUNO, MIMIKYU, MURKROW, WOBBUFFET = 414, 434, 463, 432
HERO_CLOAK, BRAVE_BANGLE = 1159, 1175
FEZANDIPITI_EX = 140
FRAGILE = {TAROUNTULA: 50, MIMIKYU: 60, MURKROW: 80}


def _id(e):
    return e.get("id") if isinstance(e, dict) else None


def board_snapshot(obs):
    """(自分の場のリスト, フリーザーが場にいるか)"""
    cur = obs.get("current") or {}
    me = (cur.get("players") or [{}])[cur.get("yourIndex", 0)] or {}
    field = [(me.get("active") or [None])[0]] + list(me.get("bench") or [])
    field = [e for e in field if isinstance(e, dict)]
    art = any(_id(e) == ARTICUNO for e in field)
    return field, art


def analyze(files, require_fez=True):
    st = collections.Counter()
    games = 0
    wins = 0
    board_at_attack = []
    fragile_on_bench = []
    for path in sorted(files):
        with open(path) as f:
            rep = json.load(f)
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            opp_deck = R.deck_of(rep, 1 - pi)
            if not deck or SPIDOPS not in deck:
                continue
            if require_fez and (not opp_deck or FEZANDIPITI_EX not in opp_deck):
                continue
            games += 1
            wins += 1 if rw[pi] == 1 else 0

            prev_opp_prize = None
            for _, obs, act in R.iter_decisions(rep, pi):
                field, art = board_snapshot(obs)
                cur = obs.get("current") or {}
                players = cur.get("players") or []
                opp = players[1 - cur.get("yourIndex", 0)] or {}
                # ★KOの判定は**相手のサイド枚数の減少**で見る。
                #   盤面のidを追うと「タマンチュラ→ワナイダー」の進化まで
                #   「失った」と数えてしまう(実測で3.33/試合のうち大半が進化だった)。
                opp_prize = len(opp.get("prize") or [])
                if prev_opp_prize is not None and opp_prize < prev_opp_prize:
                    st["ポケモンを倒された(サイドを取られた)"] += prev_opp_prize - opp_prize
                prev_opp_prize = opp_prize

                n_frag = sum(1 for e in field if _id(e) in FRAGILE)
                fragile_on_bench.append(n_frag)
                st["_taro"] += sum(1 for e in field if _id(e) == TAROUNTULA)
                st["_spid"] += sum(1 for e in field if _id(e) == SPIDOPS)
                st["_snap"] += 1
                if art:
                    st["フリーザーが場にいる局面"] += 1

                if obs["select"].get("context") != 0:
                    continue
                opts = obs["select"]["option"]
                for i in act:
                    if not (0 <= i < len(opts)):
                        continue
                    o = opts[i]
                    if o.get("type") == 13:
                        board_at_attack.append(len(field))
                    elif o.get("type") == 8:
                        # どうぐの装着先
                        idx = o.get("index")
                        cur = obs["current"]
                        mep = cur["players"][cur["yourIndex"]]
                        hand = mep.get("hand") or []
                        hid = _id(hand[idx]) if isinstance(idx, int) and idx < len(hand) else None
                        if hid == HERO_CLOAK:
                            st["ヒーローマントを付けた"] += 1
                        elif hid == BRAVE_BANGLE:
                            st["ブレイブバングルを付けた"] += 1
    st["_games"] = games
    st["_wins"] = wins
    st["_board"] = (sum(board_at_attack) / len(board_at_attack)) if board_at_attack else 0
    st["_frag"] = (sum(fragile_on_bench) / len(fragile_on_bench)) if fragile_on_bench else 0
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--all", action="store_true", help="キチキギス不在の試合も含める")
    args = ap.parse_args()
    st = analyze(glob.glob(os.path.join(args.dir, "*.json")), not args.all)
    g = max(st["_games"], 1)
    print("=" * 60)
    print("上位ワナイダー勢 vs キチキギスex入りデッキ: %d試合 (勝率%.0f%%)"
          % (st["_games"], 100.0 * st["_wins"] / g))
    print("=" * 60)
    print("  攻撃時の盤面        %.2f 体" % st["_board"])
    print("  場に置いている脆い駒 %.2f 体 (100で落ちるタマンチュラ/ミミッキュ/ヤミカラス)"
          % st["_frag"])
    snap = max(st["_snap"], 1)
    print("  盤面の内訳: タマンチュラ %.2f 体 / ワナイダー %.2f 体"
          % (st["_taro"] / snap, st["_spid"] / snap))
    for k in sorted(st, key=lambda k: -st[k]):
        if k.startswith("_"):
            continue
        print("  %-34s %5d  (%.2f/試合)" % (k, st[k], st[k] / g))


if __name__ == "__main__":
    main()
