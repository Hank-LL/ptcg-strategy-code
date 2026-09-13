#!/usr/bin/env python3
"""対メガスターミー(+メガユキメノコ)の1試合ごとの内訳を出す。

集計だけだと「誰が使ったワナイダーか」「何で落とされたか」が消えるので、
**1試合1行**で並べる。ユキメノコexの うらみのハミング は
「相手の手札1枚につき50ダメージ」なので、ターン終了時の手札を併記する。

  python3 report_vs_starmie.py --dir <replays> [--idx <mine_*.jsonl のあるDIR>]
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

import replay_diff as R          # noqa: E402
import analyze_matchup as AM     # noqa: E402

FROSLASS = 861
STARMIE = 1031


def _hp_timeline(rep):
    tl = []
    for st in (rep.get("steps") or []):
        snap = {}
        for q in (0, 1):
            r = st[q] if q < len(st) else None
            # ★status != ACTIVE の側は **前ターンの観測が残っている**。
            #   混ぜるときぜつしたポケモンが生きたまま見えて、
            #   ダメージ0・KO0 に化ける(2026-07-29 実測でここに嵌った)。
            if not r or r.get("status") != "ACTIVE":
                continue
            cur = (r.get("observation") or {}).get("current") or {}
            for pl in (cur.get("players") or []):
                if not pl:
                    continue
                for z in (pl.get("active") or []) + (pl.get("bench") or []):
                    if isinstance(z, dict) and z.get("serial") is not None:
                        snap[z["serial"]] = z.get("hp")
        tl.append(snap)
    return tl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--lb", default=None, help="lb_all.csv(レート表示用)")
    ap.add_argument("--my-card", type=int, default=401)
    args = ap.parse_args()

    AM.ARCH = AM.build_arch()
    names = {}
    for _r in csv.DictReader(open(os.path.join(
            os.path.dirname(BASE), "data", "pokemon-tcg-ai-battle",
            "JP_Card_Data.csv"), encoding="utf-8")):
        try:
            names[int(_r["カード ID"])] = _r["カード名"]
        except (KeyError, TypeError, ValueError):
            pass
    try:
        from cg.api import all_attack
        atk = {a.attackId: a.name for a in all_attack()}
    except Exception:
        atk = {}
    score = {}
    if args.lb and os.path.exists(args.lb):
        for r in csv.DictReader(open(args.lb)):
            score[r["teamName"]] = r["score"]

    rows = []
    tot = collections.Counter()
    op_tot = collections.Counter()
    op_ko = collections.Counter()      # 相手のワザ別「こちらをきぜつさせた回数」
    op_dmg = collections.defaultdict(list)
    op_victim = collections.defaultdict(collections.Counter)  # ワザ -> やられた側
    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            rep = json.load(open(path))
        except (OSError, json.JSONDecodeError):
            continue
        rw = rep.get("rewards") or [0, 0]
        teams = ((rep.get("info") or {}).get("TeamNames") or ["?", "?"])
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            od = R.deck_of(rep, 1 - pi) or []
            if AM.archetype(od) != "メガスターミーex":
                continue
            mine, theirs = collections.Counter(), collections.Counter()
            hands = []
            turns = 0
            for si, obs, act in R.iter_decisions(rep, pi):
                opts = (obs.get("select") or {}).get("option") or []
                cur = obs.get("current") or {}
                turns = max(turns, cur.get("turn") or 0)
                me = (cur.get("players") or [None, None])[pi] or {}
                for i in act:
                    if i < len(opts) and opts[i].get("type") in (13, 14):
                        hands.append(len(me.get("hand") or []))
                    if i < len(opts) and opts[i].get("type") == 13:
                        mine[opts[i].get("attackId")] += 1
            tl = _hp_timeline(rep)
            for si, obs, act in R.iter_decisions(rep, 1 - pi):
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i >= len(opts) or opts[i].get("type") != 13:
                        continue
                    aid = opts[i].get("attackId")
                    theirs[aid] += 1
                    # 殴られた側(=こちら)のバトル場を serial で追う
                    cur = obs.get("current") or {}
                    mep = (cur.get("players") or [None, None])[pi] or {}
                    a = (mep.get("active") or [None])[0]
                    if not a:
                        continue
                    ser, hp0 = a.get("serial"), a.get("hp") or 0
                    hp1 = None
                    for sj in range(si + 1, len(tl)):
                        if ser in tl[sj]:
                            hp1 = tl[sj][ser]
                            break
                    if hp1 is None:
                        op_ko[aid] += 1
                        op_victim[aid][a.get("id")] += 1
                    elif hp0 - hp1 > 0:
                        op_dmg[aid].append(hp0 - hp1)
            tot.update(mine)
            op_tot.update(theirs)
            rows.append(dict(
                ep=os.path.basename(path).split(".")[0],
                me=teams[pi], op=teams[1 - pi],
                won=rw[pi] == 1, turns=turns,
                hand=sum(hands) / len(hands) if hands else 0,
                froslass=FROSLASS in od,
                mine=mine, theirs=theirs))

    print("=" * 100)
    print("対メガスターミー %d試合  ワナイダー側の勝ち %d"
          % (len(rows), sum(1 for r in rows if r["won"])))
    print("=" * 100)
    print("%-9s %-24s %-8s %-22s %-8s %4s %6s %5s"
          % ("episode", "ワナイダー側", "レート", "相手", "レート", "結果", "終了時手札", "ターン"))
    for r in sorted(rows, key=lambda r: (not r["won"], r["me"])):
        print("%-9s %-24s %-8s %-22s %-8s %4s %6.1f %5d%s"
              % (r["ep"], r["me"][:24], score.get(r["me"], "?"),
                 r["op"][:22], score.get(r["op"], "?"),
                 "勝ち" if r["won"] else "負け", r["hand"], r["turns"],
                 "" if r["froslass"] else "  (ユキメノコ無し)"))

    n = max(len(rows), 1)
    print("\n--- ワナイダー側のワザ(1試合あたり) ---")
    for aid, c in tot.most_common(6):
        print("   %-24s %5.2f" % (atk.get(aid, aid), c / n))
    print("--- 相手のワザ(1試合あたり / うちをきぜつさせた回数 / 生き残ったときの実効打点) ---")
    for aid, c in op_tot.most_common(8):
        d = op_dmg.get(aid) or []
        print("   %-24s %5.2f   KO %3d   打点 %s"
              % (atk.get(aid, aid), c / n, op_ko.get(aid, 0),
                 ("%.0f (n=%d)" % (sum(d) / len(d), len(d))) if d else "-"))
        if op_victim.get(aid):
            print("        きぜつしたのは: %s"
                  % ", ".join("%s×%d" % (names.get(k, k), v)
                              for k, v in op_victim[aid].most_common()))


if __name__ == "__main__":
    main()
