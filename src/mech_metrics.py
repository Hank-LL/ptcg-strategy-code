#!/usr/bin/env python3
"""「1試合あたり何回やったか」を上位者とうちで比べる(順序に依存しない指標)。

1手ごとの採用率は「ターン内のどこでやるか」に左右されるので、
「準備を先に済ませる」ように変えると比率がずれる。ここでは
**1試合あたりの実行回数**という順序非依存の量で比べる。

  --mode replay : リプレイから上位者の実測値を出す
  --mode local  : うちのエージェントで実際に対戦して同じ量を出す
"""
import argparse
import collections
import glob
import json
import os
import statistics
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import replay_diff as R          # noqa: E402
import card_usage_diff as C      # noqa: E402

# 追跡する行動: (ラベル, OptionType, カードID or None=全部)
TYPE_PLAY, TYPE_ATTACH, TYPE_EVOLVE, TYPE_ABILITY = 7, 8, 9, 10
TYPE_ATTACK, TYPE_RETREAT = 13, 12


def blank():
    return collections.Counter()


def count_game(iter_decisions_result, card_names, watch_cards):
    """1試合ぶんの行動回数。"""
    c = collections.Counter()
    turns = set()
    attack_board = []
    energy_turns = set()
    for obs, picks in iter_decisions_result:
        cur = obs.get("current") or {}
        turn = cur.get("turn")
        turns.add(turn)
        opts = obs["select"]["option"]
        if obs["select"].get("context") != 0:
            continue
        for i in picks:
            if not (0 <= i < len(opts)):
                continue
            o = opts[i]
            t = o.get("type")
            cid = C.option_card_id(obs, o)
            if t == TYPE_ATTACK:
                me = (cur.get("players") or [{}])[cur.get("yourIndex", 0)] or {}
                attack_board.append(1 + len(me.get("bench") or []))
                c["攻撃"] += 1
            elif t == TYPE_RETREAT:
                c["にげる"] += 1
            elif t in (TYPE_PLAY, TYPE_ATTACH, TYPE_EVOLVE, TYPE_ABILITY):
                label = {TYPE_PLAY: "出す", TYPE_ATTACH: "つける",
                         TYPE_EVOLVE: "進化", TYPE_ABILITY: "特性"}[t]
                c[label] += 1
                if t == TYPE_ATTACH:
                    energy_turns.add(turn)
                if cid in watch_cards:
                    c["%s(%s)" % (card_names.get(cid, cid), label)] += 1
    c["_turns"] = len([t for t in turns if t is not None])
    c["_attack_board_sum"] = sum(attack_board)
    c["_attack_board_n"] = len(attack_board)
    c["_energy_turns"] = len(energy_turns)
    return c


def from_replays(dirn, team, require_card, card_names, watch):
    games = []
    for path in sorted(glob.glob(os.path.join(dirn, "*.json"))):
        with open(path) as f:
            replay = json.load(f)
        tn = (replay.get("info") or {}).get("TeamNames") or ["?", "?"]
        for pi in (0, 1):
            if team and tn[pi] != team:
                continue
            deck = R.deck_of(replay, pi)
            if require_card is not None and (not deck or require_card not in deck):
                continue
            seq = [(obs, act) for _, obs, act in R.iter_decisions(replay, pi)]
            if seq:
                games.append(count_game(seq, card_names, watch))
    return games


def from_local(n_games, card_names, watch, deck_path):
    """うちのエージェントで実際に対戦し、同じ量を数える。"""
    from cg.game import battle_start, battle_select, battle_finish
    import generic_heuristic as gh          # noqa: F401
    import wanaider_heuristic as wh
    import importlib

    def read_deck(p):
        return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]

    pool = os.path.join(os.path.dirname(BASE), "meta", "top_decks")
    opps = []
    for mod, dk in [("alakazam_heuristic", "deck_fuudin_top.csv"),
                    ("grimmsnarl_heuristic", "deck_grimmsnarl.csv"),
                    ("crustle_heuristic", "deck_iwaparesu.csv")]:
        try:
            m = importlib.import_module(mod)
            fn = (lambda mm: (lambda o: mm.agent(o)))(m)
            fn.deck = read_deck(os.path.join(pool, dk))
            fn.reset = getattr(m, "reset_state", lambda: None)
            opps.append(fn)
        except Exception:
            pass
    deck = read_deck(deck_path)
    games = []
    for i in range(n_games):
        opp = opps[i % len(opps)]
        wh.reset_state()
        opp.reset()
        ms = i % 2
        d0, d1 = (deck, opp.deck) if ms == 0 else (opp.deck, deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        seq = []
        steps = 0
        try:
            while obs["current"]["result"] == -1 and steps < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == ms:
                    a = wh.agent(obs)
                    seq.append((obs, a))
                    obs = battle_select(a)
                else:
                    obs = battle_select(opp(obs))
                steps += 1
        finally:
            battle_finish()
        if seq:
            games.append(count_game(seq, card_names, watch))
    return games


def report(label, games):
    if not games:
        print("  %s: 試合0" % label)
        return {}
    out = {}
    keys = set()
    for g in games:
        keys |= {k for k in g if not k.startswith("_")}
    for k in keys:
        out[k] = statistics.mean(g.get(k, 0) for g in games)
    out["ターン数"] = statistics.mean(g["_turns"] for g in games)
    bn = sum(g["_attack_board_n"] for g in games)
    out["攻撃時の盤面"] = (sum(g["_attack_board_sum"] for g in games) / bn) if bn else 0.0
    out["エネを付けたターン数"] = statistics.mean(g["_energy_turns"] for g in games)
    print("  %s: %d試合" % (label, len(games)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["replay", "local", "both"], default="both")
    ap.add_argument("--dir")
    ap.add_argument("--team")
    ap.add_argument("--require-card", type=int)
    ap.add_argument("--deck")
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--watch", default="")
    args = ap.parse_args()

    names = R.load_card_names()
    watch = {int(x) for x in args.watch.split(",") if x.strip()}

    a = b = {}
    if args.mode in ("replay", "both"):
        a = report("上位者(リプレイ)",
                   from_replays(args.dir, args.team, args.require_card, names, watch))
    if args.mode in ("local", "both"):
        b = report("うち(ローカル対戦)",
                   from_local(args.games, names, watch, args.deck))

    print()
    # ★試合の長さと相手が違うので、**1ターンあたりに正規化**して比べる。
    #   正規化しないと「試合が長い=よく行動している」ように見えてしまう。
    ta, tb = a.get("ターン数", 1.0) or 1.0, b.get("ターン数", 1.0) or 1.0
    print("%-30s %9s %9s %9s %8s"
          % ("1ターンあたり", "上位者", "うち", "比(うち/上位)", "元の差"))
    rows = []
    for k in set(a) | set(b):
        if k in ("ターン数", "攻撃時の盤面"):
            continue
        x, y = a.get(k, 0.0) / ta, b.get(k, 0.0) / tb
        if max(x, y) < 0.02:
            continue
        ratio = (y / x) if x else float("inf")
        rows.append((abs(ratio - 1.0) * max(x, y), k, x, y, ratio))
    for _, k, x, y, ratio in sorted(rows, reverse=True):
        mark = ""
        if ratio < 0.7:
            mark = "  <<< 足りない"
        elif ratio > 1.4:
            mark = "  <<< 多すぎ"
        print("%-30s %9.3f %9.3f %11.2f%s" % (str(k)[:30], x, y, ratio, mark))
    print()
    for k in ("ターン数", "攻撃時の盤面"):
        print("%-30s %9.2f %9.2f" % (k, a.get(k, 0), b.get(k, 0)))


if __name__ == "__main__":
    main()
