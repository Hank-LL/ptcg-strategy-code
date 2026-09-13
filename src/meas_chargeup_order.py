#!/usr/bin/env python3
"""「チャージアップで足りるのに手張りしてしまう」無駄を数える。

ユーザー報告(2026-07-28):
  バトル場のワナイダーに草エネ1個 → ロケット団エネを手張り → その後チャージアップで
  草エネを付けた。チャージアップだけで攻撃可能になったので手張りは不要だった。

チャージアップは「トラッシュから基本エネを1枚**自身に**付ける」(ターン1回・無料)。
手張りは1ターン1回しかない貴重な行動なので、**先にチャージアップを試して
それで足りるなら手張りを別の場所に回す**のが正しい。
"""
import collections
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from cg.game import battle_start, battle_select, battle_finish   # noqa: E402
from cg.api import to_observation_class, OptionType, AreaType    # noqa: E402
import generic_heuristic as gh          # noqa: E402,F401
import wanaider_heuristic as wh         # noqa: E402

POOL = os.path.join(os.path.dirname(BASE), "meta", "top_decks")


def read_deck(p):
    return [int(x) for x in open(p).read().split("\n") if x.strip()][:60]


def build_opponents():
    import importlib
    opps = []
    for mod, dk in [("alakazam_heuristic", "deck_fuudin_top.csv"),
                    ("grimmsnarl_heuristic", "deck_grimmsnarl.csv"),
                    ("crustle_heuristic", "deck_iwaparesu.csv")]:
        try:
            m = importlib.import_module(mod)
            fn = (lambda mm: (lambda o: mm.agent(o)))(m)
            fn.deck = read_deck(os.path.join(POOL, dk))
            fn.reset = getattr(m, "reset_state", lambda: None)
            opps.append(fn)
        except Exception:
            pass
    return opps


def inspect(obs_dict, pick, c):
    """1手ぶん見て、無駄な手張りかどうか判定する。"""
    obs = to_observation_class(obs_dict)
    sel = obs.select
    if sel.context != 0 or not sel.option or not pick:
        return
    i = pick[0]
    if not (0 <= i < len(sel.option)):
        return
    o = sel.option[i]
    if o.type != OptionType.ATTACH or o.area != AreaType.HAND:
        return
    st = obs.current
    me = st.players[st.yourIndex]
    card = gh._hand_card(obs, o.index, me)
    if card is None:
        return
    d = gh._CARD.get(card.id)
    if d is None or d.cardType not in (5, 6):     # 基本エネ/特殊エネ以外(どうぐ)は除く
        return
    # 付け先
    dest = None
    try:
        if o.inPlayArea == AreaType.ACTIVE and me.active:
            dest = me.active[o.inPlayIndex or 0]
        elif o.inPlayArea == AreaType.BENCH and me.bench:
            dest = me.bench[o.inPlayIndex or 0]
    except (IndexError, TypeError):
        dest = None
    if dest is None or dest.id != wh.SPIDOPS:
        return
    have = len(dest.energies or [])
    need = wh._energy_need(dest)
    c["ワナイダーへの手張り"] += 1
    if have >= need:
        return                                    # もう足りている(別の話)
    # 同じ個体のチャージアップが選択肢に出ているか
    chargeup_here = False
    for oo in sel.option:
        if oo.type != OptionType.ABILITY:
            continue
        src = None
        try:
            if oo.area == AreaType.ACTIVE and me.active:
                src = me.active[oo.index or 0]
            elif oo.area == AreaType.BENCH and me.bench:
                src = me.bench[oo.index or 0]
        except (IndexError, TypeError):
            src = None
        if src is not None and src.id == wh.SPIDOPS and src is dest:
            chargeup_here = True
    if not chargeup_here:
        return
    # チャージアップ1回で必要数に届くか
    if have + 1 >= need:
        c["★手張り不要(チャージアップで足りた)"] += 1
        if card.id == wh.ROCKET_ENERGY:
            c["  うちロケット団エネを浪費"] += 1
        else:
            c["  うち基本エネを浪費"] += 1


def run(n_games=60):
    opps = build_opponents()
    deck = read_deck(os.path.join(POOL, "deck_wanaider_top2.csv"))
    c = collections.Counter()
    for i in range(n_games):
        opp = opps[i % len(opps)]
        wh.reset_state()
        opp.reset()
        ms = i % 2
        d0, d1 = (deck, opp.deck) if ms == 0 else (opp.deck, deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        steps = 0
        try:
            while obs["current"]["result"] == -1 and steps < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == ms:
                    a = wh.agent(obs)
                    try:
                        inspect(obs, a, c)
                    except Exception:
                        c["_inspect_error"] += 1
                    obs = battle_select(a)
                else:
                    obs = battle_select(opp(obs))
                steps += 1
        finally:
            battle_finish()
        c["_games"] += 1
    return c


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    c = run(n)
    print("%d試合" % c["_games"])
    for k in ("ワナイダーへの手張り", "★手張り不要(チャージアップで足りた)",
              "  うちロケット団エネを浪費", "  うち基本エネを浪費"):
        print("  %-38s %4d  (%.2f/試合)" % (k, c[k], c[k] / max(c["_games"], 1)))
    if c["_inspect_error"]:
        print("  検査エラー", c["_inspect_error"])
