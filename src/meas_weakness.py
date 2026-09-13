#!/usr/bin/env python3
"""シミュレータ上で「実際に通った打点」を測る。弱点倍率・抵抗力の確認用。

リプレイだときぜつして盤面から消えた分が測れないので、
ローカル対戦で **相手バトル場のHPの増減** を直接見る。
攻撃を選んだ瞬間の (serial, hp) を覚えて、次に同じ serial が観測に出たときの
hp と引き算する。

  python3 meas_weakness.py --opp deck_mega_lucario_real.csv --games 30
"""
import argparse
import collections
import csv
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import arena  # noqa: E402
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402


def jp_names():
    out = {}
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            out[int(r["カード ID"])] = r["カード名"]
        except (KeyError, TypeError, ValueError):
            pass
    return out


def actives(obs):
    """{serial: (id, hp)} を両者ぶん。"""
    out = {}
    for pl in (obs["current"].get("players") or []):
        if not pl:
            continue
        for z in (pl.get("active") or []) + (pl.get("bench") or []):
            if isinstance(z, dict) and z.get("serial") is not None:
                out[z["serial"]] = (z.get("id"), z.get("hp"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--deck", default="deck_wanaider_top2.csv")
    ap.add_argument("--opp", required=True)
    ap.add_argument("--games", type=int, default=30)
    args = ap.parse_args()

    import importlib
    my_mod = importlib.import_module(args.agent)
    names = jp_names()
    from cg.api import all_attack
    atk = {a.attackId: a.name for a in all_attack()}

    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    key = args.opp[5:-4] if args.opp.startswith("deck_") else args.opp
    opp = pool[key]
    my_deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    rec = collections.defaultdict(list)
    used = collections.Counter()   # きぜつさせた分も含む「撃った回数」
    att_to = collections.Counter()  # エネ/どうぐの付け先
    endhand = []                    # ターンを終えた瞬間の手札枚数
    for g in range(args.games):
        first = g % 2
        my_mod.reset_state()
        opp["reset"]()
        d0, d1 = (my_deck, opp["deck"]) if first == 0 else (opp["deck"], my_deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        pend = None
        try:
            steps = 0
            while obs["current"]["result"] == -1 and steps < 3000:
                pl = obs["current"]["yourIndex"]
                snap = actives(obs)
                if pend is not None and pend[0] in snap:
                    aid, hp0, did = pend[1], pend[2], pend[3]
                    hp1 = snap[pend[0]][1]
                    if hp0 - hp1 > 0:
                        # (実効打点, そのときの自分の頭数) で持つ。
                        # ロケットラッシュは 30×頭数 が素点なので、
                        # 素点と実効値の差がそのまま抵抗力・軽減の量になる。
                        rec[(aid, did)].append((hp0 - hp1, pend[4]))
                    pend = None
                if pl == first:
                    act = my_mod.agent(obs)
                    sel = obs.get("select") or {}
                    opts = sel.get("option") or []
                    for i in act:
                        if i < len(opts) and opts[i].get("type") in (13, 14):
                            me = obs["current"]["players"][pl]
                            endhand.append(len(me.get("hand") or []))
                        if i < len(opts) and opts[i].get("type") == 8:
                            me = obs["current"]["players"][pl]
                            a2, i2 = (opts[i].get("inPlayArea"),
                                      opts[i].get("inPlayIndex") or 0)
                            src = (me.get("active") if a2 == 4
                                   else me.get("bench") if a2 == 5 else None)
                            if src and i2 < len(src) and src[i2]:
                                att_to[src[i2].get("id")] += 1
                        if i < len(opts) and opts[i].get("type") == 13:
                            op = obs["current"]["players"][1 - pl]
                            a = (op.get("active") or [None])[0]
                            if a:
                                me = obs["current"]["players"][pl]
                                # ★bench には空きスロットの null が入る。
                                #   そのまま len を取ると頭数を水増しする。
                                heads = len([e for e in (me.get("active") or [])
                                             if e]) + len(
                                    [e for e in (me.get("bench") or []) if e])
                                used[opts[i].get("attackId")] += 1
                                pend = (a.get("serial"), opts[i].get("attackId"),
                                        a.get("hp"), a.get("id"), heads)
                    obs = battle_select(act)
                else:
                    obs = battle_select(opp["agent"](obs))
                steps += 1
        finally:
            battle_finish()

    tot = sum(used.values())
    print("=== 撃ったワザ(きぜつ込み, %d試合) ===" % args.games)
    for aid, n in used.most_common():
        print("  %-22s %4d回  %5.2f/試合  %4.0f%%"
              % (str(atk.get(aid, aid))[:22], n, n / max(args.games, 1),
                 100.0 * n / max(tot, 1)))
    if endhand:
        print("=== ターンを終えた瞬間の手札 平均 %.2f 枚 (最大 %d, %d回) ==="
              % (sum(endhand) / len(endhand), max(endhand), len(endhand)))
    print("=== エネ/どうぐの付け先 ===")
    for cid, n in att_to.most_common(6):
        print("  %-22s %4d回  %5.2f/試合" % (str(names.get(cid, cid))[:22], n,
                                          n / max(args.games, 1)))
    print()
    print("%-22s %-18s %5s %8s %8s %8s"
          % ("ワザ", "受け手", "回数", "平均", "最小", "最大"))
    print("-" * 74)
    for (aid, did), v in sorted(rec.items(), key=lambda kv: -len(kv[1])):
        d = [x for x, _ in v]
        h = [y for _, y in v]
        print("%-22s %-18s %5d %8.0f %8d %8d   頭数%.2f (素点%.0f)"
              % (str(atk.get(aid, aid))[:22], str(names.get(did, did))[:18],
                 len(d), sum(d) / len(d), min(d), max(d),
                 sum(h) / len(h), 30.0 * sum(h) / len(h)))
        if "Rocket Rush" in str(atk.get(aid, "")):
            gap = collections.Counter(30 * y - x for x, y in v)
            print("      素点-実効 の分布: %s"
                  % sorted(gap.items(), key=lambda kv: kv[0]))


if __name__ == "__main__":
    main()
