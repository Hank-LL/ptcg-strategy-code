#!/usr/bin/env python3
"""1つの相手デッキに絞って、フラグの on/off を反復測定で比べる。

ローカル勝率は単発だと10pp振れるので、**反復して平均とSEで見る**
([[ptcg-local-eval-noise]] の方針)。

  python3 ab_matchup.py --opp deck_archaludon_real.csv \
      --flags USE_MEWTWO_VS_ARCHALUDON,USE_RESISTANCE_AWARE --reps 6 --games 60
"""
import argparse
import importlib
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import arena  # noqa: E402


def run_cell(my_mod, my_deck, opp, reps, games):
    rates = []
    for r in range(reps):
        w = n = 0
        for g in range(games):
            won, _ = arena.play(my_mod, my_deck, opp, g % 2)
            if won is None:
                continue
            n += 1
            w += 1 if won else 0
        if n:
            rates.append(100.0 * w / n)
    mean = sum(rates) / max(len(rates), 1)
    var = sum((x - mean) ** 2 for x in rates) / max(len(rates) - 1, 1)
    se = (var / max(len(rates), 1)) ** 0.5
    return mean, se, rates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--deck", default="deck_wanaider_top2.csv")
    ap.add_argument("--opp", required=True)
    ap.add_argument("--flags", required=True, help="カンマ区切り。全部 True/False で比較")
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--games", type=int, default=60)
    args = ap.parse_args()

    my_mod = importlib.import_module(args.agent)
    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    key = args.opp[5:-4] if args.opp.startswith("deck_") else args.opp
    opp = pool[key]
    my_deck = arena.read_deck(os.path.join(arena.POOL, args.deck))
    flags = [f for f in args.flags.split(",") if f]

    for on in (False, True):
        for f in flags:
            setattr(my_mod, f, on)
        mean, se, rates = run_cell(my_mod, my_deck, opp, args.reps, args.games)
        print("%-5s %s: %.1f%% ± %.1f   %s"
              % ("ON" if on else "OFF", ",".join(flags), mean, se,
                 " ".join("%.0f" % x for x in rates)), flush=True)


if __name__ == "__main__":
    main()
