#!/usr/bin/env python3
"""「この手を選ばせない」意図の負スコアが、本当に効いているかを機械的に洗う。

専用ヒューリスティックの総合点は
    gh._score_option()(=ベース) + 自分の _bonus()(=加点)
なので、**負の加点はベースを打ち消せる大きさでないと効かない**。
イワパレス相手にミュウツーで撃ち続けていたのは、ATTACK のベースが3300前後ある
のに加点が -2000 しかなかったため([[ptcg-suppression-vs-generic-base]])。

この道具は各ファイルの `return <負の値>` を拾い、
  ・その return がどの OptionType の分岐にあるか
  ・ベース + 加点 が END(10) を上回っていないか
を出す。上回っていれば「抑制したつもりで効いていない」候補。

  python3 audit_suppression.py [--files wanaider_heuristic.py ...]
"""
import argparse
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# generic_heuristic._score_option のベース点(最大値)
#   ATTACK は 1000 + 打点×2、倒せるとさらに +2000 + サイド×500。
#   打点160・メガex(サイド3)で最大 1000+320+2000+1500 = 4820。
BASE_MAX = {
    "ATTACK": 1320.0,          # 1000 + 打点×2(打点160想定)。倒せるときは下の加算がつく
    "EVOLVE": 800.0,
    "ABILITY": 700.0,
    "PLAY": 400.0,        # PLAY_POKEMON_SCORE。トレーナーも 400
    "ATTACH": 350.0,      # バトル場。ベンチは 300
    "RETREAT": 50.0,
    "CARD": 150.0,
    "YES": 60.0,
    "NO": 40.0,
    "END": 10.0,
    "TOOL_CARD": 150.0,
    "ENERGY_CARD": 150.0,
    "ENERGY": 150.0,
    "DISCARD": 150.0,
    "SKILL": 20.0,
    "NUMBER": 20.0,
    "SPECIAL_CONDITION": 20.0,
}
END_BASE = 10.0

OPT_RE = re.compile(r"OptionType\.([A-Z_]+)")
# ★`-1e9` を「-1」と読んでしまう regex にしないこと(実測でここを踏んだ)。
#   `-1120.0 + 200.0` のような式も拾って合算する。
RET_RE = re.compile(r"^(\s*)return\s+(-[\d.]+(?:[eE][+-]?\d+)?"
                    r"(?:\s*[+-]\s*[\d.]+(?:[eE][+-]?\d+)?)*)\s*(?:#.*)?$")
# `return CRUSTLE_ATTACK_SCORE` のような**定数名**も見る(数値リテラルだけでは
# 取りこぼす。実際にイワパレスの抑制値は定数に切り出してあった)。
RET_NAME_RE = re.compile(r"^(\s*)return\s+([A-Z][A-Z0-9_]+)\s*(?:#.*)?$")
CONST_RE = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=\s*(-?[\d.]+(?:[eE][+-]?\d+)?)\s*(?:#.*)?$")


def _eval_num(expr):
    try:
        v = eval(expr, {"__builtins__": {}}, {})   # 数値リテラルのみ
        return float(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None
# 「そもそも選ばせたくない」意図を示す語(コメント/近傍)
VETO_WORDS = ("使わない", "置かない", "撃たない", "無駄", "禁止", "選ばない",
              "出さない", "付けない", "捨てない", "しない", "譲る", "候補外")


def branch_of(lines, i):
    """i 行目を含む `if t == OptionType.X` 分岐の名前。見つからなければ None。"""
    for j in range(i, -1, -1):
        s = lines[j]
        if re.match(r"\s*(el)?if\s+t\s*(==|in)\s", s) or "o.type" in s:
            m = OPT_RE.findall(s)
            if m:
                return m[0] if len(m) == 1 else "/".join(m)
    return None


def func_of(lines, i):
    for j in range(i, -1, -1):
        m = re.match(r"def (\w+)\(", lines[j])
        if m:
            return m.group(1)
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=None)
    ap.add_argument("--all", action="store_true", help="負の値すべてを出す")
    args = ap.parse_args()
    files = args.files or [os.path.basename(p) for p in
                           sorted(glob.glob(os.path.join(BASE, "*_heuristic.py")))
                           if "generic" not in p]

    total = flagged = 0
    for fn in files:
        path = os.path.join(BASE, fn)
        if not os.path.exists(path):
            continue
        lines = open(path, encoding="utf-8").read().splitlines()
        consts = {}
        for ln in lines:
            mc = CONST_RE.match(ln)
            if mc:
                consts[mc.group(1)] = _eval_num(mc.group(2))
        rows = []
        for i, s in enumerate(lines):
            m = RET_RE.match(s)
            if m:
                val = _eval_num(m.group(2))
            else:
                m2 = RET_NAME_RE.match(s)
                if not m2:
                    continue
                val = consts.get(m2.group(2))
            if val is None or val >= 0:
                continue
            br = branch_of(lines, i)
            if br is None:
                continue
            base = BASE_MAX.get(br.split("/")[0], 400.0)
            tot = base + val
            # ATTACK は「倒せる」ときベースに +2000 +サイド×500 が乗る。
            # ただし**倒せるなら撃つのが正しい**ので、判定は非致死のベースで行う。
            # ★ATTACK の抑制は「genericが**倒せると思っている**」最悪ケースで
            #   判定しないと意味がない。イワパレスは特性で実際は0ダメージだが
            #   generic は damage=160 を見て `+2000 +サイド×500` を足すため、
            #   非致死ベースだけで見ると -2000 でも足りているように見えてしまう。
            lethal_extra = 3500.0 if br.startswith("ATTACK") else 0.0
            tot = base + lethal_extra + val
            # 直前5行のコメントに「選ばせたくない」語があるか
            ctx = "\n".join(lines[max(0, i - 6):i + 1])
            veto = any(w in ctx for w in VETO_WORDS)
            ok = tot < END_BASE
            total += 1
            if args.all or not ok:
                # 同じ分岐内で、この行より前にある return の数(=順序で飛ばされる危険)
                bstart = i
                for j in range(i, -1, -1):
                    if re.match(r"\s*(el)?if\s+t\s*(==|in)\s", lines[j]):
                        bstart = j
                        break
                earlier = sum(1 for k in range(bstart, i)
                              if re.match(r"\s*return\s", lines[k]))
                rows.append((i + 1, func_of(lines, i), br, val, base, tot,
                             veto, ok, earlier, lethal_extra))
                if not ok:
                    flagged += 1
        if rows:
            print("=" * 92)
            print(fn)
            print("=" * 92)
            print("%-6s %-20s %-11s %8s %7s %8s %5s %6s"
                  % ("行", "関数", "分岐", "加点", "ベース", "合計", "END超", "先行return"))
            for ln, fnc, br, val, base, tot, veto, ok, earlier, lx in rows:
                mark = "  ← 効いていない可能性" if not ok else ""
                if veto:
                    mark += "(コメントに抑制意図あり)"
                if earlier and not ok:
                    mark += "  ← 先に return があり飛ばされる恐れ"
                print("%-6d %-20s %-11s %8.0f %7.0f %8.0f %5s %6d%s"
                      % (ln, fnc[:20], br[:11], val, base, tot,
                         "" if ok else "YES", earlier, mark))
    print("\n負のreturn %d件を検査 / **合計がENDを上回る**(抑制が効いていない候補) = %d件"
          % (total, flagged))
    print("※ 未カバー: min()/max()や変数式でのreturn、`sc = ...` の代入による抑制。")
    print("※ ATTACK は「generic が倒せると思っている」最悪ケース(+3500)で判定するため、")
    print("   **打点0のワザ**(かくせい等)や実際に倒せる場面は過検出になる。")
    print("   本当に危ないのは『genericが打点を読み違えるカード』"
          "(イワパレスの特性・抵抗力・軽減)が絡む抑制。")


if __name__ == "__main__":
    main()
