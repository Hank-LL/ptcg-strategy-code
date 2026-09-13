#!/usr/bin/env python3
"""上位オーロンゲ勢のマシマシラ運用とサポート運用を調べる。

ユーザーの仮説(2026-07-28):
  マシマシラのアドレナブレイン(自分のポケモン1体からダメカンを最大3個、
  相手のポケモン1体に移す)は、**移す量は移動元が誰でも同じ**なので
  移動元の選択は自分側の延命問題。だから
    - バトル場のオーロンゲexが「移した結果 HP180超」になるなら優先して移す
    - ベンチも「移した結果 HP30超」になるなら優先して移す
  という「生存閾値をまたぐか」で決めるべき。

閾値の根拠(シャドーバレット): バトル場に180 + 相手ベンチ1体に30。
  → 残りHPが180以下だとバトル場は次の一撃で落ちる
  → 残りHPが30以下だとベンチは狙撃で落ちる
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

GRIMMSNARL_EX, MORGREM, IMPIDIMP = 648, 647, 646
MUNKIDORI, FROSLASS, SNORUNT = 112, 104, 860
ACTIVE_LETHAL = 180      # シャドーバレットのバトル場打点
BENCH_LETHAL = 30        # 同・ベンチ狙撃
CTX_DAMAGE_COUNTER, CTX_REMOVE = 13, 16   # 移し先 / 移動元


def _id(e):
    return e.get("id") if isinstance(e, dict) else None


def field_of(obs, who):
    cur = obs.get("current") or {}
    me_i = cur.get("yourIndex", 0)
    p = (cur.get("players") or [{}])[me_i if who == "me" else 1 - me_i] or {}
    act = (p.get("active") or [None])[0]
    return act, [e for e in (p.get("bench") or []) if isinstance(e, dict)]


def max_hp(e):
    return e.get("maxHp") or e.get("hp") or 0


def analyze(files, is_mirror_only=False):
    st = collections.Counter()
    src_choice = collections.Counter()
    dst_choice = collections.Counter()
    supporters = collections.Counter()
    games = wins = 0
    names = R.load_card_names()

    for path in sorted(files):
        with open(path) as f:
            rep = json.load(f)
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            opp_deck = R.deck_of(rep, 1 - pi)
            if not deck or GRIMMSNARL_EX not in deck:
                continue
            mirror = bool(opp_deck) and GRIMMSNARL_EX in opp_deck
            if is_mirror_only and not mirror:
                continue
            games += 1
            wins += 1 if rw[pi] == 1 else 0

            for _, obs, act in R.iter_decisions(rep, pi):
                ctx = obs["select"].get("context")
                opts = obs["select"]["option"]

                # ---- アドレナブレインの移動元 (自分の場から) ----
                if ctx == CTX_REMOVE:
                    my_act, my_bench = field_of(obs, "me")
                    for i in act:
                        if not (0 <= i < len(opts)):
                            continue
                        o = opts[i]
                        area, idx = o.get("area"), o.get("index")
                        e = None
                        if area == 4:
                            e = my_act
                        elif area == 5 and isinstance(idx, int) and idx < len(my_bench):
                            e = my_bench[idx]
                        if e is None:
                            continue
                        hp = e.get("hp") or 0
                        dmg = max(0, max_hp(e) - hp)
                        moved = min(dmg, 30)
                        after = hp + moved
                        where = "バトル場" if area == 4 else "ベンチ"
                        thr = ACTIVE_LETHAL if area == 4 else BENCH_LETHAL
                        src_choice["%s:%s" % (where, names.get(_id(e), _id(e)))] += 1
                        st["移動元 計"] += 1
                        # 生存閾値をまたいだか
                        if hp <= thr < after:
                            st["  ★閾値をまたいで救った"] += 1
                        elif after <= thr:
                            st["  まだ閾値以下(救えていない)"] += 1
                        else:
                            st["  もともと閾値超"] += 1

                # ---- アドレナブレインの移し先 (相手の場へ) ----
                elif ctx == CTX_DAMAGE_COUNTER:
                    op_act, op_bench = field_of(obs, "op")
                    for i in act:
                        if not (0 <= i < len(opts)):
                            continue
                        cid = C.option_card_id(obs, opts[i])
                        area = opts[i].get("area")
                        where = "バトル場" if area == 4 else "ベンチ"
                        dst_choice["%s:%s" % (where, names.get(cid, cid))] += 1
                        st["移し先 計"] += 1

                # ---- サポートの使用条件 ----
                elif ctx == 0:
                    cur = obs["current"]
                    mep = cur["players"][cur["yourIndex"]]
                    hand = mep.get("hand") or []
                    for i in act:
                        if not (0 <= i < len(opts)) or opts[i].get("type") != 7:
                            continue
                        cid = C.option_card_id(obs, opts[i])
                        import generic_heuristic as gh
                        d = gh._CARD.get(cid)
                        if d is None or d.cardType != 3:
                            continue
                        supporters["%s (手札%d枚)" % (names.get(cid, cid), len(hand))] += 1
                        supporters["_%s" % names.get(cid, cid)] += 1
                        st["_hand_sum_%s" % names.get(cid, cid)] += len(hand)
    st["_games"] = games
    st["_wins"] = wins
    return st, src_choice, dst_choice, supporters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--mirror", action="store_true", help="ミラー戦だけ")
    args = ap.parse_args()
    st, src, dst, sup = analyze(glob.glob(os.path.join(args.dir, "*.json")),
                                args.mirror)
    g = max(st["_games"], 1)
    print("=" * 64)
    print("上位オーロンゲ勢 %d試合 (勝率%.0f%%)%s"
          % (st["_games"], 100.0 * st["_wins"] / g, " ※ミラーのみ" if args.mirror else ""))
    print("=" * 64)
    print("\n--- アドレナブレインの移動元(自分の場のどこから剥がすか) ---")
    for k, v in src.most_common(8):
        print("  %-34s %4d (%.2f/試合)" % (k, v, v / g))
    print("  [生存閾値との関係] バトル場180 / ベンチ30")
    for k in ("移動元 計", "  ★閾値をまたいで救った", "  まだ閾値以下(救えていない)",
              "  もともと閾値超"):
        if k in st:
            tot = max(st["移動元 計"], 1)
            print("    %-30s %4d (%.0f%%)" % (k, st[k], 100 * st[k] / tot))
    print("\n--- アドレナブレインの移し先(相手のどこへ) ---")
    for k, v in dst.most_common(8):
        print("  %-34s %4d (%.2f/試合)" % (k, v, v / g))
    print("\n--- サポートの使用(カード別 / 使ったときの手札枚数) ---")
    for k, v in sorted([(k, v) for k, v in sup.items() if k.startswith("_")],
                       key=lambda x: -x[1]):
        nm = k[1:]
        avg = st["_hand_sum_%s" % nm] / max(v, 1)
        print("  %-30s %4d回 (%.2f/試合)  使用時の手札平均 %.1f枚" % (nm, v, v / g, avg))


if __name__ == "__main__":
    main()
