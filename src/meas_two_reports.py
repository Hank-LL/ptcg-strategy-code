#!/usr/bin/env python3
"""ユーザー報告2件の裏取り。

(1) 対オーロンゲ: **倒せるのにサカキを使って撃墜を逃す**場面があるか。
    ロケットラッシュは草、オーロンゲ系は3種とも草弱点なので打点は2倍のはず。
(2) 対フーディン: **まだ撃てないミュウツーにロケット団エネを付けて**
    改造ハンマー(フーディンデッキに4枚)で剥がされていないか。

どちらも「そのとき本当にそうなっていたか」を数えるだけの道具。

  python3 meas_two_reports.py --opp grimmsnarl_top --games 24
"""
import argparse
import collections
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import arena  # noqa: E402
import wanaider_heuristic as W  # noqa: E402
from cg.api import to_observation_class, OptionType, AreaType  # noqa: E402
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402

GIOVANNI, ROCKET_ENERGY, MEWTWO_EX = 1218, 15, 431


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", default="deck_wanaider_top2.csv")
    ap.add_argument("--opp", required=True)
    ap.add_argument("--games", type=int, default=24)
    args = ap.parse_args()

    pool = {p["name"]: p for p in arena.build_pool(weighted=False)}
    opp = pool[args.opp]
    deck = arena.read_deck(os.path.join(arena.POOL, args.deck))

    lethal_turns = 0          # 「今のバトル場で相手を倒せる」番
    lethal_but_giovanni = 0   # そのときサカキを選んだ
    dmg_samples = []          # そのときの打点(2倍が効いているかの確認)
    rocket_attach = collections.Counter()   # 付けた時点でミュウツーが撃てるか
    for g in range(args.games):
        first = g % 2
        W.reset_state()
        opp["reset"]()
        d0, d1 = (deck, opp["deck"]) if first == 0 else (opp["deck"], deck)
        obs, _ = battle_start(d0, d1)
        if obs is None:
            continue
        try:
            s = 0
            while obs["current"]["result"] == -1 and s < 3000:
                pl = obs["current"]["yourIndex"]
                if pl == first:
                    o2 = to_observation_class(obs)
                    st = o2.current
                    me = st.players[pl]
                    op = st.players[1 - pl]
                    plan = W._build_plan(o2, st, me, op)
                    dmg = W._our_active_damage(plan, me)
                    can_ko = (dmg > 0 and plan.op_active is not None
                              and plan.op_active_hp <= dmg)
                    act = W.agent(obs)
                    opts = o2.select.option or []
                    if can_ko:
                        lethal_turns += 1
                        dmg_samples.append((dmg, plan.op_active_hp))
                        for i in act:
                            if i < len(opts) and opts[i].type == OptionType.PLAY:
                                c = W.gh._hand_card(o2, opts[i].index, me)
                                if c is not None and c.id == GIOVANNI:
                                    lethal_but_giovanni += 1
                    for i in act:
                        if i >= len(opts) or opts[i].type != OptionType.ATTACH:
                            continue
                        c = W.gh._hand_card(o2, opts[i].index, me)
                        if c is None or c.id != ROCKET_ENERGY:
                            continue
                        dest = None
                        try:
                            if opts[i].inPlayArea == AreaType.ACTIVE and me.active:
                                dest = me.active[opts[i].inPlayIndex or 0]
                            elif opts[i].inPlayArea == AreaType.BENCH and me.bench:
                                dest = me.bench[opts[i].inPlayIndex or 0]
                        except (IndexError, TypeError):
                            dest = None
                        if dest is None or dest.id != MEWTWO_EX:
                            continue
                        # ロケット団エネは2個ぶん。付けた後の合計個数で判定する
                        after = len(W._energy_units(dest)) + 2
                        rocket_attach["撃てる形になる(3個以上)" if after >= 3
                                      else "まだ撃てない(%d個)" % after] += 1
                    obs = battle_select(act)
                else:
                    obs = battle_select(opp["agent"](obs))
                s += 1
        finally:
            battle_finish()

    print("=" * 64)
    print("対 %s  %d試合" % (args.opp, args.games))
    print("=" * 64)
    print("(1) 「今のバトル場で相手を倒せる」番 %d 回" % lethal_turns)
    print("     うち**サカキを選んだ** %d 回" % lethal_but_giovanni)
    if dmg_samples:
        print("     そのときの打点/相手HP の例: %s"
              % ", ".join("%d/%d" % x for x in dmg_samples[:8]))
    print("\n(2) ロケット団エネをミュウツーexに付けた内訳:")
    for k, v in rocket_attach.most_common():
        print("     %-24s %3d" % (k, v))
    if not rocket_attach:
        print("     (付けた場面なし)")


if __name__ == "__main__":
    main()
