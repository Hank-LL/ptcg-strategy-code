#!/usr/bin/env python3
"""上位ワナイダー勢が「対フーディン」で何をしているかを調べる。

背景(2026-07-28 ユーザー報告): ラダー740帯に上がると、フーディン側が
  - 改造ハンマー(Enhanced Hammer, id=1081)で**特殊エネ**を割ってくる
    → ロケット団エネルギー(id=15, cardType=6)が狙い撃ちされる。基本草は対象外。
  - キチキギスex(Fezandipiti ex, id=140)の Cruel Arrow(無3で任意の1体に100)で
    ベンチを狙撃してくる。
という対策を取ってくる。上位勢がどう対応しているかを実データで見る。
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
ARTICUNO, MIMIKYU = 414, 434
GRASS, ROCKET_E = 1, 15
ALAKAZAM_LINE = {741, 742, 743, 109, 245}
ENHANCED_HAMMER, FEZANDIPITI_EX = 1081, 140

TYPE_PLAY, TYPE_ATTACH, TYPE_EVOLVE, TYPE_ABILITY = 7, 8, 9, 10
TYPE_ATTACK = 13


def is_fuudin(deck):
    return bool(deck) and any(c in ALAKAZAM_LINE for c in deck)


def attach_dest(obs, opt):
    """ATTACH の付け先カードID。"""
    cur = obs.get("current") or {}
    me = (cur.get("players") or [{}])[cur.get("yourIndex", 0)] or {}
    area, idx = opt.get("inPlayArea"), opt.get("inPlayIndex")
    try:
        if area == 4:
            a = me.get("active") or []
            e = a[0] if a else None
        elif area == 5:
            b = me.get("bench") or []
            e = b[idx or 0]
        else:
            return None
    except (IndexError, TypeError):
        return None
    if isinstance(e, dict):
        return e.get("id")
    return None


def analyze(files, team=None):
    st = collections.Counter()
    games = 0
    wins = 0
    for path in sorted(files):
        with open(path) as f:
            rep = json.load(f)
        tn = (rep.get("info") or {}).get("TeamNames") or ["?", "?"]
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            opp_deck = R.deck_of(rep, 1 - pi)
            if not deck or SPIDOPS not in deck:
                continue          # ワナイダー側だけ見る
            if not is_fuudin(opp_deck):
                continue          # 相手がフーディンの試合だけ
            if team and tn[pi] != team:
                continue
            games += 1
            wins += 1 if rw[pi] == 1 else 0
            st["_hammer_in_opp_deck"] += (ENHANCED_HAMMER in (opp_deck or []))
            st["_fez_in_opp_deck"] += (FEZANDIPITI_EX in (opp_deck or []))
            for _, obs, act in R.iter_decisions(rep, pi):
                if obs["select"].get("context") != 0:
                    continue
                opts = obs["select"]["option"]
                for i in act:
                    if not (0 <= i < len(opts)):
                        continue
                    o = opts[i]
                    t = o.get("type")
                    cid = C.option_card_id(obs, o)
                    if t == TYPE_ATTACH:
                        dest = attach_dest(obs, o)
                        if cid == ROCKET_E:
                            st["ロケット団エネを付けた"] += 1
                            if dest == MEWTWO_EX:
                                st["  ロケ→ミュウツーex"] += 1
                                # ★そのロケット団エネで**そのターン撃てる形**に
                                #   なるか。ならないなら改造ハンマーの的を
                                #   先置きしているだけで危険。
                                cur = obs["current"]
                                mep = cur["players"][cur["yourIndex"]]
                                n_rk = 1 + len(mep.get("bench") or [])
                                tgt = None
                                for e in ([ (mep.get("active") or [None])[0] ]
                                          + list(mep.get("bench") or [])):
                                    if isinstance(e, dict) and e.get("id") == MEWTWO_EX:
                                        tgt = e
                                have = len(((tgt or {}).get("energyCards")
                                            or (tgt or {}).get("energies") or []))
                                # ロケ(2個ぶん)を足して3個以上、かつ場のロケット団4体以上
                                if have + 2 >= 3 and n_rk >= 4:
                                    st["    うち即撃てる形になる"] += 1
                                else:
                                    st["    うち先置き(ハンマーの的)"] += 1
                            elif dest in (SPIDOPS, TAROUNTULA):
                                st["  ロケ→ワナイダー系"] += 1
                            else:
                                st["  ロケ→その他"] += 1
                        elif cid == GRASS:
                            st["草エネを付けた"] += 1
                            if dest == MEWTWO_EX:
                                st["  草→ミュウツーex"] += 1
                    elif t == TYPE_PLAY:
                        if cid == MEWTWO_EX:
                            st["ミュウツーexを出した"] += 1
                        elif cid == ARTICUNO:
                            st["フリーザーを出した"] += 1
                        elif cid == MIMIKYU:
                            st["ミミッキュを出した"] += 1
                        elif cid == TAROUNTULA:
                            st["タマンチュラを出した"] += 1
                    elif t == TYPE_ATTACK:
                        cur = obs["current"]
                        mep = cur["players"][cur["yourIndex"]]
                        a = (mep.get("active") or [None])[0]
                        aid = (a or {}).get("id")
                        if aid == SPIDOPS:
                            st["ワナイダーで攻撃"] += 1
                        elif aid == MEWTWO_EX:
                            st["ミュウツーexで攻撃"] += 1
                        else:
                            st["その他で攻撃"] += 1
                        # フリーザーの居場所(たねを守る特性なので場にいれば効く)
                        bench_ids = [ (e or {}).get("id") for e in (mep.get("bench") or []) ]
                        if aid == ARTICUNO:
                            st["  攻撃時フリーザーがバトル場"] += 1
                        elif ARTICUNO in bench_ids:
                            st["  攻撃時フリーザーがベンチ"] += 1
                        else:
                            st["  攻撃時フリーザー不在"] += 1
    st["_games"] = games
    st["_wins"] = wins
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--team")
    args = ap.parse_args()
    files = glob.glob(os.path.join(args.dir, "*.json"))
    st = analyze(files, args.team)
    g = max(st["_games"], 1)
    print("=" * 62)
    print("上位ワナイダー勢の 対フーディン戦: %d試合 (勝率 %.0f%%)"
          % (st["_games"], 100.0 * st["_wins"] / g))
    print("  相手デッキに改造ハンマー %d / キチキギスex %d"
          % (st["_hammer_in_opp_deck"], st["_fez_in_opp_deck"]))
    print("=" * 62)
    order = ["ロケット団エネを付けた", "  ロケ→ミュウツーex",
             "    うち即撃てる形になる", "    うち先置き(ハンマーの的)",
             "  ロケ→ワナイダー系", "  ロケ→その他",
             "草エネを付けた", "  草→ミュウツーex",
             "ミュウツーexを出した", "タマンチュラを出した",
             "フリーザーを出した", "ミミッキュを出した",
             "ワナイダーで攻撃", "ミュウツーexで攻撃", "その他で攻撃",
             "  攻撃時フリーザーがバトル場", "  攻撃時フリーザーがベンチ",
             "  攻撃時フリーザー不在"]
    for k in order:
        if k in st:
            print("  %-24s %4d  (%.2f/試合)" % (k, st[k], st[k] / g))


if __name__ == "__main__":
    main()
