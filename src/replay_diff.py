#!/usr/bin/env python3
"""上位者のリプレイを自分のエージェントに流し込み、選択の差分を集計する。

リプレイには (observation, action) の対が全ステップぶん入っている。
同じ observation をうちのヒューリスティックに渡し、上位者と違う手を選んだ場面を
context / OptionType 別に集計する。勝率ではなく「どこで判断が分かれるか」を見る。

  python3 replay_diff.py --dir <replay_dir> --agent grimmsnarl [--deck <60枚>] [--limit N]
"""
import argparse
import collections
import csv
import glob
import importlib
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.dirname(BASE), "data", "pokemon-tcg-ai-battle"))

OPTION_TYPE_NAME = {
    0: "NUMBER", 1: "YES", 2: "NO", 3: "CARD", 4: "TOOL_CARD", 5: "ENERGY_CARD",
    6: "ENERGY", 7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY", 11: "DISCARD",
    12: "RETREAT", 13: "ATTACK", 14: "END", 15: "SKILL", 16: "SPECIAL_CONDITION",
}


def load_card_names():
    path = os.path.join(os.path.dirname(BASE), "data", "pokemon-tcg-ai-battle", "EN_Card_Data.csv")
    names = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kid = next(c for c in row if "id" in c.lower())
            knm = next(c for c in row if "name" in c.lower())
            try:
                names[int(row[kid])] = row[knm]
            except (TypeError, ValueError):
                pass
    return names


def deck_of(replay, pi):
    """そのプレイヤーが提出した60枚(step1のaction)。"""
    try:
        deck = replay["steps"][1][pi]["action"]
        return deck if deck and len(deck) == 60 else None
    except (IndexError, KeyError, TypeError):
        return None


def iter_decisions(replay, pi):
    """(step_index, observation, action) を、選択が発生したぶんだけ返す。

    Kaggleのリプレイでは step N の observation に対する行動は **step N+1 の
    action** に記録される。step N 自身の action は1つ前の観測への応答なので、
    そのまま突き合わせると選択肢数や minCount と矛盾する(実測で確認済み)。
    また INACTIVE 側は観測が前ターンのまま残っているので除外する。
    """
    steps = replay["steps"]
    for si in range(len(steps) - 1):
        step = steps[si]
        if pi >= len(step) or not step[pi]:
            continue
        rec = step[pi]
        if rec.get("status") != "ACTIVE":
            continue
        obs = rec.get("observation") or {}
        sel = obs.get("select")
        if not sel or not sel.get("option"):
            continue
        nxt = steps[si + 1]
        if pi >= len(nxt) or not nxt[pi]:
            continue
        act = nxt[pi].get("action")
        if not isinstance(act, list) or not act or len(act) == 60:
            continue
        # 選択肢の範囲に収まらないものは対応が取れていないので捨てる
        n_opt = len(sel["option"])
        if any(not isinstance(i, int) or i < 0 or i >= n_opt for i in act):
            continue
        lo, hi = sel.get("minCount") or 0, sel.get("maxCount") or 1
        if not (lo <= len(act) <= max(hi, lo)):
            continue
        yield si, obs, act


AREA_DECK, AREA_HAND, AREA_DISCARD = 1, 2, 3
AREA_ACTIVE, AREA_BENCH, AREA_STADIUM = 4, 5, 7


def _card_id_at(obs, opt):
    """選択肢の area/index から実際のカードIDを引く。

    option には cardId が入っていないので、観測の hand / active / bench /
    discard を area 番号で引き直す必要がある。
    """
    cur = obs.get("current") or {}
    me_i = cur.get("yourIndex")
    players = cur.get("players") or []
    pi = opt.get("playerIndex")
    if pi is None:
        pi = me_i
    if not isinstance(pi, int) or pi >= len(players):
        return None
    p = players[pi] or {}
    area, idx = opt.get("area"), opt.get("index")

    def _id(entry):
        if isinstance(entry, dict):
            return entry.get("id") or entry.get("cardId")
        return entry

    if area == AREA_DECK and isinstance(idx, int):
        # 山札サーチ系。中身は observation["select"]["deck"] にだけ入っている
        deck = (obs.get("select") or {}).get("deck") or []
        return _id(deck[idx]) if idx < len(deck) else None
    if area == AREA_HAND and isinstance(idx, int):
        hand = p.get("hand") or []
        return _id(hand[idx]) if idx < len(hand) else None
    if area == AREA_DISCARD and isinstance(idx, int):
        dis = p.get("discard") or []
        return _id(dis[idx]) if idx < len(dis) else None
    if area == AREA_ACTIVE:
        act = p.get("active") or []
        return _id(act[0]) if act else None
    if area == AREA_BENCH and isinstance(idx, int):
        bench = p.get("bench") or []
        return _id(bench[idx]) if idx < len(bench) else None
    if area == AREA_STADIUM:
        return _id(cur.get("stadium"))
    # PLAY/EVOLVE 等は area なしで手札 index を指す
    if area is None and isinstance(idx, int):
        hand = (players[me_i] or {}).get("hand") or []
        return _id(hand[idx]) if idx < len(hand) else None
    return None


def describe(opt, names, obs=None, attacks=None):
    """選択肢1つを人間が読める形にする。"""
    t = opt.get("type")
    tn = OPTION_TYPE_NAME.get(t, str(t))
    if t == 13 and opt.get("attackId") is not None:  # ATTACK
        aid = opt["attackId"]
        return "ATTACK:%s" % (attacks.get(aid, aid) if attacks else aid)
    if t == 0 and opt.get("number") is not None:  # NUMBER
        return "NUMBER:%s" % opt["number"]
    if obs is not None:
        cid = _card_id_at(obs, opt)
        if cid:
            return "%s:%s" % (tn, names.get(cid, cid))
    if opt.get("area") is not None:
        return "%s@a%s" % (tn, opt["area"])
    return tn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--agent", required=True,
                    help="grimmsnarl / wanaider / alakazam / generic")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--team", default=None,
                    help="この名前のプレイヤー側だけ見る(既定: 全員)")
    ap.add_argument("--deck-filter", action="store_true",
                    help="うちのデッキと一致する側だけ見る")
    ap.add_argument("--our-deck", default=None, help="deck.csv(--deck-filter用)")
    ap.add_argument("--require-card", type=int, default=None,
                    help="このカードIDを含むデッキの側だけ見る(構築が違っても比較したいとき)")
    ap.add_argument("--deck-report", action="store_true",
                    help="対象になった構築とうちのデッキの差分も出す")
    ap.add_argument("--show", type=int, default=25, help="代表例の表示件数")
    args = ap.parse_args()

    mod_name = {
        "grimmsnarl": "grimmsnarl_heuristic",
        "wanaider": "wanaider_heuristic",
        "alakazam": "alakazam_heuristic",
        "generic": "generic_heuristic",
    }[args.agent]
    agent_mod = importlib.import_module(mod_name)
    names = load_card_names()
    try:
        from cg.api import all_attack
        attacks = {a.attackId: a.name for a in all_attack()}
    except Exception:
        attacks = {}

    our_deck = None
    ref_deck = None
    if args.deck_filter or args.deck_report:
        path = args.our_deck or os.path.join(
            os.path.dirname(BASE), "meta", "top_decks", "deck_grimmsnarl.csv")
        with open(path) as f:
            ref_deck = collections.Counter(
                int(l.strip()) for l in f if l.strip().isdigit())
        if args.deck_filter:
            our_deck = ref_deck
    seen_decks = collections.Counter()

    files = sorted(glob.glob(os.path.join(args.dir, "*.json")))
    if args.limit:
        files = files[: args.limit]

    n_dec = n_match = n_err = 0
    n_games = 0
    by_ctx = collections.Counter()      # (context, type) -> 総数
    by_ctx_diff = collections.Counter()  # (context, type) -> 不一致数
    examples = collections.defaultdict(list)
    choice_pairs = collections.Counter()  # (相手が選んだ, うちが選んだ) -> 回数

    for path in files:
        try:
            with open(path) as f:
                replay = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        team_names = (replay.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            if args.team and team_names[pi] != args.team:
                continue
            deck = deck_of(replay, pi)
            if our_deck is not None:
                if deck is None or collections.Counter(deck) != our_deck:
                    continue
            if args.require_card is not None:
                if deck is None or args.require_card not in deck:
                    continue
            if deck is not None:
                seen_decks[tuple(sorted(collections.Counter(deck).items()))] += 1
            used = False
            for si, obs, act in iter_decisions(replay, pi):
                sel = obs["select"]
                ctx = sel.get("context")
                opts = sel["option"]
                # うちのエージェントに同じ観測を渡す
                try:
                    ours = agent_mod.agent(obs)
                except Exception:
                    n_err += 1
                    continue
                if not isinstance(ours, list):
                    n_err += 1
                    continue
                used = True
                n_dec += 1
                otype = opts[0].get("type") if opts else None
                key = (ctx, otype)
                by_ctx[key] += 1
                same = sorted(ours) == sorted(act)
                if same:
                    n_match += 1
                else:
                    by_ctx_diff[key] += 1
                    try:
                        theirs_s = "+".join(describe(opts[i], names, obs, attacks)
                                            for i in act if 0 <= i < len(opts))
                        ours_s = "+".join(describe(opts[i], names, obs, attacks)
                                          for i in ours if 0 <= i < len(opts))
                    except Exception:
                        theirs_s = str(act)
                        ours_s = str(ours)
                    choice_pairs[(ctx, theirs_s, ours_s)] += 1
                    if len(examples[key]) < 3:
                        examples[key].append((os.path.basename(path), si, theirs_s, ours_s))
            if used:
                n_games += 1

    if not n_dec:
        print("比較できた判断が0件。--deck-filter や --team の指定を確認。")
        return

    print("=" * 78)
    print("リプレイ %d ファイル / 対象プレイヤー視点 %d / 判断 %d 件 / エラー %d"
          % (len(files), n_games, n_dec, n_err))
    print("一致率: %.1f%%  (%d / %d)" % (100.0 * n_match / n_dec, n_match, n_dec))
    print("=" * 78)
    print()
    print("--- 不一致が多い場面 (context, OptionType) ---")
    print("%-8s %-14s %8s %8s %8s" % ("context", "type", "件数", "不一致", "不一致率"))
    rows = sorted(by_ctx_diff.items(), key=lambda kv: -kv[1])
    for (ctx, t), nd in rows[:20]:
        tot = by_ctx[(ctx, t)]
        print("%-8s %-14s %8d %8d %7.1f%%"
              % (ctx, OPTION_TYPE_NAME.get(t, t), tot, nd, 100.0 * nd / tot))
    print()
    print("--- 具体的な食い違い (上位%d) ---" % args.show)
    print("%6s  %-34s -> %-34s %s" % ("ctx", "上位者の選択", "うちの選択", "回数"))
    for (ctx, th, ou), c in choice_pairs.most_common(args.show):
        print("%6s  %-34s -> %-34s %4d" % (ctx, th[:34], ou[:34], c))

    if args.deck_report and ref_deck is not None and seen_decks:
        print()
        print("--- 対象になった構築 (上位%d) とうちのデッキとの差 ---" % 3)
        for dk, cnt in seen_decks.most_common(3):
            dc = collections.Counter(dict(dk))
            diff = [(cid, dc.get(cid, 0) - ref_deck.get(cid, 0))
                    for cid in set(dc) | set(ref_deck)]
            diff = sorted([d for d in diff if d[1]], key=lambda x: -x[1])
            print("  [%d試合] 差分 %d種:" % (cnt, len(diff)))
            for cid, dd in diff:
                print("      %-34s %+d" % (names.get(cid, cid), dd))


if __name__ == "__main__":
    main()
