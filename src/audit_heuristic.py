#!/usr/bin/env python3
"""ヒューリスティック1本を機械的に監査する。

`audit_suppression.py` の後継。あちらは `return -500.0` のような**リテラル**しか
見なかったので、`return LETHAL_BLOCK` のように定数で書いた抑制を取りこぼしていた。
ここではモジュールを実際に import して定数を解決する。

見るもの:
  [1] 関数・定数の二重定義        (後ろの定義が前を黙って潰す)
  [2] 定義だけで呼ばれない関数/定数  (死にコード)
  [3] 抑制の負スコアが効いているか  (END / generic のベース / PREP_MIN の3つ)
  [4] デッキとコードの突き合わせ    (デッキに無いカードの分岐 / 扱っていないカード)
  [5] 実戦での例外・不正手・思考時間・generic へのフォールバック
  [6] 実戦で一度も通らない分岐      (提示されない = 死んでいる)

  python3 audit_heuristic.py --agent ogerpon_heuristic --deck deck_ogerpon.csv
"""
import argparse
import collections
import csv
import importlib
import os
import re
import sys
import time
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import generic_heuristic as gh  # noqa: E402

# generic の _score_option が返すベースの最大値(分岐ごと)
BASE_MAX = {
    "ATTACK": 4820.0,   # 1000 + 打点×2 + 倒せるとき 2000 + サイド×500
    "ABILITY": 700.0,
    "EVOLVE": 800.0,
    "PLAY": 400.0,
    "ATTACH": 350.0,
    "TOOL_CARD": 350.0,
    "ENERGY": 200.0,
    "CARD": 200.0,
    "RETREAT": 50.0,
    "END": 10.0,
}
END_SCORE = 10.0


def jp_names():
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            out[int(r["カード ID"])] = r["カード名"]
        except (KeyError, TypeError, ValueError):
            pass
    return out


def sibling_decks(agent):
    """その .py を使う build スクリプトから、デッキの和集合を集める。"""
    out = set()
    for f in os.listdir(BASE):
        if not (f.startswith("build_") and f.endswith(".py")):
            continue
        try:
            b = open(os.path.join(BASE, f)).read()
        except OSError:
            continue
        if agent + ".py" not in b:
            continue
        m = re.search(r'DECK_SRC = "(?:\.\./meta/top_decks/)?([^"]+)"', b)
        if m:
            out.add(os.path.basename(m.group(1)))
    return sorted(out)


def _is_opponent_side(src, name):
    """その定数が**相手のカード**として扱われているか。

    スタジアムは場に1枚の共有カードで、相手が張ったものをこちらが起動するか
    決める分岐がある(夜のアカデミー/ミステリーガーデン/公民館)。
    自分のデッキに入らないのが正常なので、デッキ突き合わせから外す。
    """
    for line in src.split("\n"):
        if not re.search(r'\b%s\b' % re.escape(name), line):
            continue
        if re.search(r'^\s*%s = ' % re.escape(name), line):
            continue
        if re.search(r'\b(sid|p\.stadium_id|op\.|p\.op_)', line):
            continue
        if re.search(r'^STADIUM_(KEEP|NEVER|ALWAYS)', line):
            continue
        return False        # 相手側でない使い方が1つでもあれば自分の札
    return True


def static_checks(path, mod, deck_ids, jp):
    src = open(path).read()
    issues = []

    # [1] 二重定義
    for kind, pat in (("関数", r'^def ([a-zA-Z_]\w*)\('),
                      ("定数", r'^([A-Z][A-Z0-9_]*) = ')):
        dup = [k for k, v in collections.Counter(
            re.findall(pat, src, re.M)).items() if v > 1]
        for d in dup:
            issues.append(("[1] 二重定義", "%s %s" % (kind, d)))

    # [2] 呼ばれない関数 / 参照されない定数
    for m in re.finditer(r'^def ([a-zA-Z_]\w*)\(', src, re.M):
        nm = m.group(1)
        if nm in ("agent", "reset_state"):
            continue
        if len(re.findall(r'\b%s\b' % re.escape(nm), src)) == 1:
            issues.append(("[2] 死にコード", "関数 %s は一度も呼ばれない" % nm))
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*) = ', src, re.M):
        nm = m.group(1)
        if len(re.findall(r'\b%s\b' % re.escape(nm), src)) == 1:
            issues.append(("[2] 死にコード", "定数 %s は一度も参照されない" % nm))

    # [3] 抑制スコアが3つの閾値を下回っているか
    prep = getattr(mod, "PREP_MIN_SCORE", 1000.0)
    branch = None
    for ln, line in enumerate(src.split("\n"), 1):
        m = re.search(r'OptionType\.([A-Z_]+)', line)
        if m and re.search(r'^\s*(el)?if\b', line):
            branch = m.group(1)
        m = re.search(r'^\s*return\s+(-?[A-Za-z_0-9.]+)\s*$', line)
        if not m or branch is None:
            continue
        tok = m.group(1)
        try:
            val = float(tok)
        except ValueError:
            val = getattr(mod, tok, None)
            if not isinstance(val, (int, float)):
                continue
        if val >= 0:
            continue
        b = BASE_MAX.get(branch, 400.0)
        total = b + val
        if total > END_SCORE:
            issues.append(("[3] 抑制不足",
                           "%d行 %s: %s(%.0f) + ベース%.0f = %.0f > END(10)"
                           % (ln, branch, tok, val, b, total)))
        elif total >= prep:
            issues.append(("[3] 抑制不足",
                           "%d行 %s: 合計%.0f >= PREP_MIN(%.0f)"
                           % (ln, branch, total, prep)))

    # [4] デッキとの突き合わせ
    #   ★誤検出が2種類あるので除外する(2026-08-12):
    #     ① 同じ .py を複数のデッキで共有している。渡した1つに無いだけで、
    #        兄弟デッキでは現役(ボスの指令/いしずえのめんex/カポエラー)。
    #        -> build_*.py から「このエージェントを使うデッキ」を集めて和集合で見る。
    #     ② **相手のカード**に反応する判定がある。スタジアムは場に1枚の共有カードで、
    #        相手が張ったものをこちらが起動するか決める(夜のアカデミー等)。
    #        自分のデッキに入らないのが正常。
    consts = {m.group(1): int(m.group(2)) for m in
              re.finditer(r'^([A-Z][A-Z0-9_]*) = (\d+)\s*(?:#.*)?$', src, re.M)}
    named = {}
    for nm, cid in consts.items():
        if cid in jp and len(re.findall(r'\b%s\b' % nm, src)) > 1:
            named[nm] = cid
    for nm, cid in sorted(named.items()):
        # そのIDが「カードとして」扱われているものだけ(閾値定数を除く)
        if not re.search(r'(==\s*%s\b|\bin\s*\([^)]*\b%s\b)' % (nm, nm), src):
            continue
        if _is_opponent_side(src, nm):
            continue
        if cid not in deck_ids:
            issues.append(("[4] デッキに無い",
                           "%s (%s) の分岐があるがデッキに入っていない"
                           % (nm, jp.get(cid, "?"))))
    known = set(named.values())
    for cid in sorted(set(deck_ids)):
        c = gh._CARD.get(cid)
        if c is None or c.cardType == 0 or cid in known:
            continue
        if c.cardType in (5, 6):
            continue
        issues.append(("[4] 扱いなし",
                       "%s (%d) をコードが個別に扱っていない"
                       % (jp.get(cid, "?"), cid)))
    return issues


def runtime_checks(mod, deck, games):
    import arena
    from cg.api import OptionType
    pool = arena.build_pool(weighted=True)
    bad = collections.Counter()
    seen = collections.Counter()
    zero = collections.Counter()
    mx = [0.0]
    fb = [0]
    g0 = gh.agent
    a0 = mod.agent
    ob = mod._bonus

    def spy(o):
        fb[0] += 1
        return g0(o)

    def bw(o, obs, state, me, op, p, ctx=None):
        v = ob(o, obs, state, me, op, p, ctx)
        seen[str(o.type).split(".")[-1]] += 1
        if v == 0.0:
            zero[str(o.type).split(".")[-1]] += 1
        return v

    def wrapped(obs):
        t = time.time()
        try:
            act = a0(obs)
        except Exception:
            bad["★例外"] += 1
            traceback.print_exc()
            raise
        mx[0] = max(mx[0], time.time() - t)
        n = len((obs.get("select") or {}).get("option") or [])
        if not isinstance(act, list) or not act:
            bad["★空/型不正"] += 1
        else:
            for i in act:
                if not isinstance(i, int) or i < 0 or i >= n:
                    bad["★範囲外index"] += 1
        return act

    mod._bonus = bw
    mod.agent = wrapped
    gh.agent = spy
    for g in range(games):
        arena.play(mod, deck, pool[g % len(pool)], g % 2)
    mod._bonus = ob
    mod.agent = a0
    gh.agent = g0
    return bad, seen, zero, mx[0], fb[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--games", type=int, default=60)
    args = ap.parse_args()

    import arena
    jp = jp_names()
    mod = importlib.import_module(args.agent)
    path = os.path.join(BASE, args.agent + ".py")
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))
    sibs = sibling_decks(args.agent) or [args.deck]
    deck_ids = set()
    for d in sibs:
        try:
            deck_ids |= set(arena.read_deck(os.path.join(arena.POOL, d)))
        except OSError:
            pass
    deck_ids |= set(deck)

    print("=" * 78)
    print("%s  /  %s" % (args.agent, args.deck))
    print("突き合わせるデッキ(このエージェントを使う全提出): %s"
          % ", ".join(sibs))
    print("=" * 78)
    issues = static_checks(path, mod, deck_ids, jp)
    if issues:
        cur = None
        for tag, msg in issues:
            if tag != cur:
                print("\n%s" % tag)
                cur = tag
            print("   %s" % msg)
    else:
        print("静的チェック: 問題なし")

    bad, seen, zero, mx, fb = runtime_checks(mod, deck, args.games)
    print("\n[5] 実戦 %d試合" % args.games)
    print("   例外・不正手 : %s" % (dict(bad) or "なし"))
    print("   generic フォールバック : %d" % fb)
    print("   最長思考時間 : %.1fms" % (mx * 1000))
    print("\n[6] 選択肢の種類別: 提示回数 / うち加点0(=判断していない)")
    for k, v in seen.most_common():
        z = zero[k]
        flag = "  ← 全部素通り" if z == v and v > 20 else ""
        print("   %-14s %6d / %6d (%3.0f%%)%s" % (k, v, z, 100.0 * z / v, flag))


if __name__ == "__main__":
    main()
