#!/usr/bin/env python3
"""リーリエの決心とサカキの使い方を機序で測る。

ユーザー報告(2026-07-28):
 (1) エネを付けられる場面でエネを付けず先にリーリエを使い、手札のエネが流れた。
     リーリエは「手札を山札に戻して引き直す」ので、手札は全部消える。
 (2) サカキは相手のベンチから1体を引きずり出すので、
     今のバトル場を倒せる状況で使うと的を逃がしてしまう。
"""
import collections
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from cg.game import battle_start, battle_select, battle_finish   # noqa: E402
from cg.api import to_observation_class, OptionType, AreaType    # noqa: E402
import generic_heuristic as gh          # noqa: E402
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
            fn.label = mod
            opps.append(fn)
        except Exception:
            pass
    return opps


def inspect(obs_dict, pick, c):
    obs = to_observation_class(obs_dict)
    sel = obs.select
    if sel.context != 0 or not sel.option or not pick:
        return
    i = pick[0]
    if not (0 <= i < len(sel.option)):
        return
    o = sel.option[i]
    st = obs.current
    me = st.players[st.yourIndex]
    op = st.players[1 - st.yourIndex]
    wh._update_turn_state(st)
    p = wh._build_plan(obs, st, me, op)

    # サカキを使えた局面で「前が撃てず・ベンチで倒せる的がいる」のに
    # 使わなかったケース(機会損失)
    gio_available = False
    for oo in sel.option:
        if oo.type != OptionType.PLAY:
            continue
        hc3 = gh._hand_card(obs, oo.index, me)
        if hc3 is not None and hc3.id == wh.GIOVANNI:
            gio_available = True
    if gio_available:
        dmg0 = wh._our_active_damage(p, me)
        swap0 = wh._best_attacker_damage(p, me)
        if dmg0 <= 0 and wh._best_killable_bench(op, swap0) is not None:
            c["サカキの好機(前が撃てず・ベンチで倒せる)"] += 1
            picked = sel.option[i]
            hcp = (gh._hand_card(obs, picked.index, me)
                   if picked.type == OptionType.PLAY else None)
            if hcp is None or hcp.id != wh.GIOVANNI:
                c["★好機を逃した"] += 1

    if o.type == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return
        if card.id == wh.LILLIE:
            c["リーリエ使用"] += 1
            # 手札に残っていたエネ・ポケモンは山札に戻って消える
            lost_e = sum(p.hand_counts.get(e, 0) for e in
                         (wh.GRASS_ENERGY, wh.ROCKET_ENERGY, wh.PSYCHIC_ENERGY))
            # エネを付けられたのに付けずに使ったか
            # 「付けられた」だけでなく **付ける価値があったか** を見る。
            # 付け先が既に足りているエネや、殴らない駒への手張りは無駄なので
            # それを見送ってリーリエを使うのは正しい。
            useful_attach = False
            for oo in sel.option:
                if oo.type != OptionType.ATTACH or oo.area != AreaType.HAND:
                    continue
                hc2 = gh._hand_card(obs, oo.index, me)
                d2 = gh._CARD.get(hc2.id) if hc2 is not None else None
                if d2 is None or d2.cardType not in (5, 6):
                    continue
                dest = None
                try:
                    if oo.inPlayArea == AreaType.ACTIVE and me.active:
                        dest = me.active[oo.inPlayIndex or 0]
                    elif oo.inPlayArea == AreaType.BENCH and me.bench:
                        dest = me.bench[oo.inPlayIndex or 0]
                except (IndexError, TypeError):
                    dest = None
                if dest is None:
                    continue
                nd = wh._energy_need(dest)
                if nd > 0 and len(dest.energies or []) < nd:
                    useful_attach = True
            if useful_attach:
                c["★有益な手張りを逃してリーリエ"] += 1
            if lost_e:
                c["  手札のエネを流した枚数"] += lost_e
            if any(oo.type == OptionType.EVOLVE for oo in sel.option):
                c["★進化できたのにリーリエ"] += 1
        elif card.id == wh.GIOVANNI:
            c["サカキ使用"] += 1
            dmg = wh._our_active_damage(p, me)
            swap = wh._best_attacker_damage(p, me)
            best = wh._best_killable_bench(op, swap)
            if dmg > 0 and p.op_active is not None and p.op_active_hp <= dmg:
                c["★倒せる相手がいるのにサカキ"] += 1
            elif best is not None:
                c["  倒せる的を引きずり出した"] += 1
                if dmg <= 0:
                    c["  うち前が撃てない状態(ベンチの駒で倒す)"] += 1


def run(n_games=80):
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
            res = to_observation_class(obs).current.result
            c["_win"] += (res == ms)
        finally:
            battle_finish()
        c["_games"] += 1
    return c


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    c = run(n)
    g = max(c["_games"], 1)
    print("%d試合 (勝率 %.0f%%)" % (c["_games"], 100 * c["_win"] / g))
    for k in ("リーリエ使用", "★有益な手張りを逃してリーリエ",
              "★進化できたのにリーリエ", "  手札のエネを流した枚数",
              "サカキ使用", "★倒せる相手がいるのにサカキ",
              "  倒せる的を引きずり出した",
              "  うち前が撃てない状態(ベンチの駒で倒す)",
              "サカキの好機(前が撃てず・ベンチで倒せる)", "★好機を逃した"):
        print("  %-34s %4d  (%.2f/試合)" % (k, c[k], c[k] / g))
    if c["_inspect_error"]:
        print("  検査エラー", c["_inspect_error"])
