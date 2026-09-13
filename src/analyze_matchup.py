#!/usr/bin/env python3
"""特定マッチアップで上位者が実際に何をしているかを数える。

「対ブリジュラス/ルカリオ/スターミーにどう対応しているか」を答えるための道具。
リプレイから **自分のデッキ(--my-card を含む側)** の行動だけを取り出し、
相手アーキタイプ別に

  勝率 / 使ったワザ / 場に出したポケモン / 特性・グッズ・サポートの使用回数
  盤面の頭数の推移 / 終局時の状態

を1試合あたりに直して出す。勝率でなく**機序**を見るための集計。

  python3 analyze_matchup.py --dir <replays> [--my-card 401] [--per-game]
"""
import argparse
import collections
import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import replay_diff as R  # noqa: E402

SPIDOPS = 401

ARCH_KEYS = [
    ("メガルカリオex", "メガルカリオex"),
    ("Archaludon", "ブリジュラスex"),
    ("メガスターミーex", "メガスターミーex"),
    ("ドラパルトex", "ドラパルトex"),
    ("ワナイダー", "ロケット団のワナイダー"),
    ("オーロンゲex", "マリィのオーロンゲex"),
    ("フーディン", "フーディン"),
    ("イワパレス", "イワパレス"),
    ("メガガルーラex", "メガガルーラex"),
    ("メガリザードンex", "メガリザードンex"),
    ("Cinderace", "エースバーン"),
    # ★2026-08-01 に台頭した新顔(ユーザー報告)。判定に無いと "?" に落ちる。
    ("メガミミロップex", "メガミミロップex"),
    ("オーガポンex", "オーガポン みどりのめんex"),
    ("オーガポン", "オーガポン みどりのめん"),
    ("ノココッチ", "ノココッチ"),
]


def build_arch():
    import csv
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    # ★同名別IDがある(イワパレス = 345 と 533)。集合で持たないと取りこぼす。
    jp = collections.defaultdict(set)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                jp[r["カード名"]].add(int(r["カード ID"]))
            except (KeyError, TypeError, ValueError):
                pass
    return [(lab, jp[nm]) for lab, nm in ARCH_KEYS if nm in jp]


ARCH = None


def archetype(deck):
    s = set(deck or [])
    for lab, ids in ARCH:
        if s & ids:
            return lab
    return "?"


ACTION_NAME = {7: "PLAY", 8: "ATTACH", 9: "EVOLVE", 10: "ABILITY",
               12: "RETREAT", 13: "ATTACK", 14: "END"}


def _cid(obs, opt):
    cid = R._card_id_at(obs, opt)
    while isinstance(cid, (list, tuple)) and cid:
        cid = cid[0]
    if isinstance(cid, dict):
        cid = cid.get("id") or cid.get("cardId")
    return cid if isinstance(cid, int) else None


AREA_ACTIVE, AREA_BENCH = 4, 5


def _attach_dest(obs, opt, pi):
    """ATTACH の付け先のカードID。"""
    cur = obs.get("current") or {}
    p = (cur.get("players") or [None, None])[pi] or {}
    a, i = opt.get("inPlayArea"), opt.get("inPlayIndex") or 0
    z = None
    if a == AREA_ACTIVE:
        act = p.get("active") or []
        z = act[i] if i < len(act) else None
    elif a == AREA_BENCH:
        bn = p.get("bench") or []
        z = bn[i] if i < len(bn) else None
    while isinstance(z, (list, tuple)) and z:
        z = z[0]
    if isinstance(z, dict):
        return z.get("id") or z.get("cardId")
    return None


def board_of(obs, pi):
    cur = obs.get("current") or {}
    p = (cur.get("players") or [None, None])[pi] or {}
    return len(p.get("active") or []) + len(p.get("bench") or [])


def main():
    global ARCH
    ARCH = build_arch()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--my-card", type=int, default=SPIDOPS)
    ap.add_argument("--only", default="", help="この相手アーキタイプだけ(カンマ区切り)")
    ap.add_argument("--min-games", type=int, default=3)
    ap.add_argument("--top", type=int, default=18)
    args = ap.parse_args()

    names = R.load_card_names()
    # 表示は日本語名のほうが読みやすい(英名は アテナ=Ariana 等でずれる)
    import csv as _csv
    for _r in _csv.DictReader(open(os.path.join(
            os.path.dirname(BASE), "data", "pokemon-tcg-ai-battle",
            "JP_Card_Data.csv"), encoding="utf-8")):
        try:
            names[int(_r["カード ID"])] = _r["カード名"]
        except (KeyError, TypeError, ValueError):
            pass
    try:
        from cg.api import all_attack
        atk_names = {a.attackId: a.name for a in all_attack()}
    except Exception:
        atk_names = {}
    only = {s for s in args.only.split(",") if s}

    # 相手arch -> 集計
    games = collections.defaultdict(lambda: [0, 0])           # [試合, 勝ち]
    usage = collections.defaultdict(collections.Counter)      # arch -> (act,card) -> 回数
    attacks = collections.defaultdict(collections.Counter)    # arch -> attackId -> 回数
    op_attacks = collections.defaultdict(collections.Counter)
    board_end = collections.defaultdict(list)
    board_mid = collections.defaultdict(list)
    turns = collections.defaultdict(list)
    prize_end = collections.defaultdict(list)
    articuno = collections.defaultdict(lambda: [0, 0])        # [試合, フリーザーを場に出した]
    per_deck = collections.Counter()
    attach_to = collections.defaultdict(collections.Counter)
    # ターンを終えた瞬間の手札枚数。メガユキメノコexの「うらみのハミング」は
    # **相手の手札1枚につき50ダメージ** なので、この値がそのまま被弾になる。
    end_hand = collections.defaultdict(list)

    for path in sorted(glob.glob(os.path.join(args.dir, "*.json"))):
        try:
            with open(path) as f:
                rep = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        rw = rep.get("rewards") or [0, 0]
        for pi in (0, 1):
            deck = R.deck_of(rep, pi)
            if not deck or args.my_card not in deck:
                continue
            arc = archetype(R.deck_of(rep, 1 - pi))
            if only and arc not in only:
                continue
            per_deck[tuple(sorted(deck))] += 1
            games[arc][0] += 1
            games[arc][1] += 1 if rw[pi] == 1 else 0
            articuno[arc][0] += 1
            saw_articuno = False
            last_obs = None
            b_seq = []
            for si, obs, act in R.iter_decisions(rep, pi):
                sel = obs.get("select") or {}
                opts = sel.get("option") or []
                last_obs = obs
                for i in act:
                    if i >= len(opts):
                        continue
                    o = opts[i]
                    t = o.get("type")
                    if t in (13, 14):
                        # ワザを撃ってもターンは終わるので ATTACK も数える
                        cur0 = obs.get("current") or {}
                        me0 = (cur0.get("players") or [None, None])[pi] or {}
                        end_hand[arc].append(len(me0.get("hand") or []))
                    if t == 13:
                        attacks[arc][o.get("attackId")] += 1
                    elif t in ACTION_NAME and t != 14:
                        c = _cid(obs, o)
                        if c:
                            usage[arc][(ACTION_NAME[t], c)] += 1
                        if t == 8:
                            # ATTACH は **付け先** が本質(エネをどのポケモンに
                            # 寄せているか)。inPlayArea/inPlayIndex で引く。
                            d = _attach_dest(obs, o, pi)
                            if d:
                                attach_to[arc][d] += 1
                cur = obs.get("current") or {}
                me = (cur.get("players") or [None, None])[pi] or {}
                for z in (me.get("bench") or []) + (me.get("active") or []):
                    zz = z
                    while isinstance(zz, (list, tuple)) and zz:
                        zz = zz[0]
                    if isinstance(zz, dict):
                        zz = zz.get("id") or zz.get("cardId")
                    if zz == 414:
                        saw_articuno = True
                b_seq.append(board_of(obs, pi))
            # 相手のワザ
            for si, obs, act in R.iter_decisions(rep, 1 - pi):
                opts = (obs.get("select") or {}).get("option") or []
                for i in act:
                    if i < len(opts) and opts[i].get("type") == 13:
                        op_attacks[arc][opts[i].get("attackId")] += 1
            if saw_articuno:
                articuno[arc][1] += 1
            if b_seq:
                board_end[arc].append(b_seq[-1])
                board_mid[arc].append(sum(b_seq) / len(b_seq))
            if last_obs:
                cur = last_obs.get("current") or {}
                turns[arc].append(cur.get("turn") or 0)
                me = (cur.get("players") or [None, None])[pi] or {}
                prize_end[arc].append(len(me.get("prize") or []))

    print("=" * 70)
    tot_g = sum(v[0] for v in games.values())
    tot_w = sum(v[1] for v in games.values())
    print("対象: デッキに %d を含む側  %d試合 (勝率 %.1f%%)"
          % (args.my_card, tot_g, 100.0 * tot_w / max(tot_g, 1)))
    print("構築の種類: %d 通り (最多 %d試合)"
          % (len(per_deck), per_deck.most_common(1)[0][1] if per_deck else 0))
    print("=" * 70)
    print("\n%-18s %5s %5s %7s %7s %7s %7s %7s"
          % ("相手", "試合", "勝ち", "勝率", "頭数(平均)", "頭数(終)", "ターン", "フリーザー"))
    for arc, (g, w) in sorted(games.items(), key=lambda kv: -kv[1][0]):
        bm = board_mid[arc]
        be = board_end[arc]
        tn = turns[arc]
        print("%-18s %5d %5d %6.0f%% %9.2f %8.2f %7.1f %8.0f%%"
              % (arc[:18], g, w, 100.0 * w / max(g, 1),
                 sum(bm) / max(len(bm), 1), sum(be) / max(len(be), 1),
                 sum(tn) / max(len(tn), 1),
                 100.0 * articuno[arc][1] / max(articuno[arc][0], 1)))

    for arc, (g, w) in sorted(games.items(), key=lambda kv: -kv[1][0]):
        if g < args.min_games:
            continue
        print("\n" + "-" * 70)
        print("【対 %s】 %d試合 %d勝 (%.0f%%)" % (arc, g, w, 100.0 * w / g))
        print("-" * 70)
        print("  ワザ(1試合あたり):")
        for aid, n in attacks[arc].most_common(8):
            print("    %-26s %5.2f" % (atk_names.get(aid, aid), n / g))
        print("  相手のワザ(1試合あたり):")
        for aid, n in op_attacks[arc].most_common(8):
            print("    %-26s %5.2f" % (atk_names.get(aid, aid), n / g))
        eh = end_hand[arc]
        if eh:
            print("  ターンを終えた瞬間の手札: 平均 %.2f 枚 (最大 %d, %d回)"
                  % (sum(eh) / len(eh), max(eh), len(eh)))
        print("  エネ/どうぐの付け先(1試合あたり):")
        for cid, n in attach_to[arc].most_common(6):
            print("    %-26s %5.2f" % (str(names.get(cid, cid))[:26], n / g))
        print("  カード×行動(1試合あたり, 上位%d):" % args.top)
        for (a, c), n in usage[arc].most_common(args.top):
            print("    %-8s %-26s %5.2f" % (a, str(names.get(c, c))[:26], n / g))


if __name__ == "__main__":
    main()
