#!/usr/bin/env python3
"""リプレイから「実際に通ったダメージ」を測る。

観測にはポケモンの `hp`(現在値)と `maxHp` が入っているので、
攻撃の直前と直後で相手バトル場の hp を引けば**実効打点**が出る。
弱点2倍・抵抗力・軽減効果(フルメタルラボ等)がすべて入った値になるので、
カードテキストからの推定ではなく実測で確かめられる。

  python3 meas_attack_damage.py --dir <replays> [--my-card 401]
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

import replay_diff as R  # noqa: E402


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


def active_of(obs, q):
    cur = obs.get("current") or {}
    pl = (cur.get("players") or [None, None])[q] or {}
    a = pl.get("active") or []
    return a[0] if a and a[0] else None


def board_heads(obs, q):
    cur = obs.get("current") or {}
    pl = (cur.get("players") or [None, None])[q] or {}
    return len(pl.get("active") or []) + len(pl.get("bench") or [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--my-card", type=int, default=401)
    ap.add_argument("--opponent-side", action="store_true",
                    help="相手が撃ったワザの実効打点を測る(何で殴られているか)")
    args = ap.parse_args()
    names = jp_names()
    try:
        from cg.api import all_attack
        atk = {a.attackId: a.name for a in all_attack()}
    except Exception:
        atk = {}

    # (ワザ, 相手のポケモン) -> [実効打点のリスト, 頭数のリスト]
    rec = collections.defaultdict(lambda: ([], []))
    ko = collections.Counter()

    def hp_timeline(rep):
        """step番号 -> {serial: hp}。どちらの視点の観測でも拾う。

        ★攻撃した側の「次の選択」まで待つと相手のターンが丸ごと挟まるので、
          回復・入れ替え・進化が混ざって実効打点が測れない。
          **serial で追いかけて、攻撃の直後に現れる最初の観測**を使う。
        """
        tl = []
        for si, st in enumerate(rep.get("steps") or []):
            snap = {}
            for q in (0, 1):
                r = st[q] if q < len(st) else None
                # ★status != ACTIVE の側は前ターンの観測が残っているので混ぜない
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

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        rep = json.load(open(path))
        tl = hp_timeline(rep)
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            # --opponent-side なら「相手が撃った側」を見る
            pi = 1 - pi if args.opponent_side else pi
            for si, obs, act in R.iter_decisions(rep, pi):
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i >= len(opts) or opts[i].get("type") != 13:
                        continue
                    d = active_of(obs, 1 - pi)
                    if d is None:
                        continue
                    aid, did = opts[i].get("attackId"), d.get("id")
                    ser, hp0 = d.get("serial"), d.get("hp") or 0
                    heads = board_heads(obs, pi)
                    hp1 = None
                    for sj in range(si + 1, len(tl)):
                        if ser in tl[sj]:
                            hp1 = tl[sj][ser]
                            break
                    if hp1 is None:
                        # 盤面から消えた = きぜつ。打点は「残りHP以上」しか分からない
                        ko[(aid, did)] += 1
                        continue
                    dmg = hp0 - hp1
                    if dmg > 0:
                        rec[(aid, did)][0].append(dmg)
                        rec[(aid, did)][1].append(heads)

    print("%-22s %-20s %5s %8s %8s %8s %6s"
          % ("ワザ", "受け手", "回数", "実効打点", "最小", "最大", "KO"))
    print("-" * 86)
    # きぜつさせた分は打点が測れないが、**何で落とされたか**は重要なので行は出す
    keys = set(rec) | set(ko)
    def _n(k):
        return len(rec[k][0]) + ko.get(k, 0)
    for k in sorted(keys, key=lambda k: -_n(k)):
        aid, did = k
        dmgs, heads = rec.get(k, ([], []))
        if not dmgs:
            print("%-22s %-20s %5d %8s %8s %8s %6d"
                  % (str(atk.get(aid, aid))[:22], str(names.get(did, did))[:20],
                     0, "-", "-", "-", ko.get(k, 0)))
            continue
        print("%-22s %-20s %5d %8.0f %8d %8d %6d"
              % (str(atk.get(aid, aid))[:22], str(names.get(did, did))[:20],
                 len(dmgs), sum(dmgs) / len(dmgs), min(dmgs), max(dmgs),
                 ko.get((aid, did), 0)))
        if aid in atk and "Rocket Rush" in str(atk[aid]) and heads:
            print("%-22s %-20s        (そのときの自分の頭数 平均 %.2f → 素点 %.0f)"
                  % ("", "", sum(heads) / len(heads), 30.0 * sum(heads) / len(heads)))


if __name__ == "__main__":
    main()
