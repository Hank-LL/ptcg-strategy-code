#!/usr/bin/env python3
"""環境を代表する相手プールで評価するローカルアリーナ。

## なぜ作ったか
従来のローカル評価は相手が **フーディン/オーロンゲ/イワパレスの3種だけ**だった。
ところが自分のラダー実戦22試合を数えると、実際に当たった相手は
  メガルカリオex 4 / ドラパルト 3 / イワパレス 3 / ワナイダー 2 /
  Archaludon ex 2 / Cinderace 2 / メガガルーラex 2 / …
と**11種以上**で、ローカルに存在しないデッキが過半だった。
これでは「環境で勝てるか」を測れない。

## このアリーナの方針
1. `meta/top_decks/` の全デッキを相手にする(専用ヒューリスティックがあればそれ、
   無ければ generic が操縦する)。
2. **ラダーで実際に当たった頻度で重み付け**できる(`--weights`)。
3. 反復して平均±SEを出す。単発の勝率では判断しない(同設定で±3〜10pp振れる)。
4. 勝率だけでなく**機序**(終局の頭数・ターン数・敗因)も出す。

## 限界(承知の上で使う)
generic が操縦する相手はラダーの本物より弱い。**絶対値は過大に出る**ので、
使い方は「A/B比較」と「苦手マッチの発見」に限る。絶対値はラダーで確かめる。
"""
import argparse
import collections
import importlib
import os
import statistics
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from cg.game import battle_start, battle_select, battle_finish   # noqa: E402
from cg.api import to_observation_class                          # noqa: E402
import generic_heuristic as gh                                   # noqa: E402

POOL = os.path.join(os.path.dirname(BASE), "meta", "top_decks")

# デッキ -> 専用ヒューリスティック(無ければ generic)
DECK_AGENTS = {
    "deck_fuudin_top.csv": "alakazam_heuristic",
    "deck_fuudin_nokocchi.csv": "alakazam_heuristic",
    "deck_iwaparesu.csv": "crustle_heuristic",
    "deck_grimmsnarl.csv": "grimmsnarl_heuristic",
    "deck_grimmsnarl_top.csv": "grimmsnarl_heuristic",
    "deck_marnie_grimmsnarl.csv": "grimmsnarl_heuristic",
    "deck_wanaider_top2.csv": "wanaider_heuristic",
    "deck_wanaider_top.csv": "wanaider_heuristic",
    "deck_dragapult_real.csv": "dragapult_heuristic",
    "deck_archaludon_real.csv": "archaludon_heuristic",
    "deck_mega_starmie_real.csv": "mega_starmie_heuristic",
    "deck_mega_starmie_top.csv": "mega_starmie_heuristic",
    "deck_mega_lucario.csv": "mega_lucario_heuristic",
    "deck_mega_lucario_real.csv": "mega_lucario_heuristic",
    "deck_ogerpon_maco.csv": "ogerpon_heuristic",
}

# ラダー実戦(22試合)で当たった頻度。0のものも環境にはいるので最低1は与える。
# ラダーの相手分布。**maco-macoo(71位/1020.6)の98試合の観測**に合わせた
# (2026-08-12)。上を目指す帯のメタに寄せる。
#   オーロンゲex 37% / フーディン 16% / オーガポンex 10% /
#   メガルカリオex 9% / ドラパルトex 8% / その他 20%
# ★以前の LADDER_WEIGHTS は **一度も使われていなかった**。build_pool が
#   dict に weight を入れるだけで、返すリストは1デッキ1件だったため、
#   呼び出し側の `pool[i % len(pool)]` は常に均等サンプリングだった。
#   ここでは重みのぶんだけ**エントリを複製**して、均等に回すだけで
#   分布どおりに当たるようにする。
LADDER_WEIGHTS = {
    # オーロンゲ系 37%
    "deck_grimmsnarl_top.csv": 20,
    "deck_grimmsnarl.csv": 9,
    "deck_marnie_grimmsnarl.csv": 8,
    # フーディン 16%
    "deck_fuudin_top.csv": 10,
    "deck_fuudin_nokocchi.csv": 6,
    # オーガポン(ミラー) 10%
    "deck_ogerpon_maco.csv": 10,
    # メガルカリオ 9% / ドラパルト 8%
    "deck_mega_lucario_real.csv": 9,
    "deck_dragapult_real.csv": 8,
    # その他 20%
    "deck_archaludon_real.csv": 4,
    "deck_iwaparesu.csv": 3,
    "deck_wanaider_top2.csv": 3,
    "deck_mega_garura_real.csv": 3,
    "deck_mega_starmie_top.csv": 3,
    "deck_wanaider_top.csv": 2,
    "deck_mega_garura.csv": 1,
    "deck_mega_starmie_real.csv": 1,
    "deck_garchomp.csv": 1,
}

EXCLUDE = {"deck_mega_lucario.csv", "deck_dragapult.csv", "deck_brijuras.csv", "deck_mega_starmie.csv", "deck_wanaider_hypno.csv", "deck_wanaider.csv", "deck_sample_yukinooh.csv",
           "deck_wanaider_lance4.csv",
           "deck_comfey_mill.csv",
           "deck_comfey_colosseum.csv",
           "deck_comfey_ogerpon.csv",
           "deck_chandelure.csv",
           "deck_tusk.csv",
           "deck_tusk_energy.csv",
           "deck_tusk_trimmer.csv",
           "deck_comfey_hitmontop.csv",
           "deck_comfey_colosseum2.csv",
           "deck_comfey_boss.csv",
           "deck_ogerpon.csv",
           "deck_comfey_dizzy.csv",
           "deck_ogerpon_ac_nplot.csv",
           "deck_ogerpon_ac_briar.csv",
           "deck_ogerpon_ac_ice.csv",
           "deck_ogerpon_ac_crown.csv",
           "deck_ogerpon_ours.csv"}


def read_deck(path):
    return [int(x) for x in open(path).read().split("\n") if x.strip()][:60]


def build_pool(weighted=True):
    """[(名前, deck, agent_fn, reset_fn, 重み)] を返す。"""
    out = []
    for fn in sorted(os.listdir(POOL)):
        if not fn.endswith(".csv") or fn in EXCLUDE:
            continue
        path = os.path.join(POOL, fn)
        try:
            deck = read_deck(path)
        except Exception:
            continue
        if len(deck) != 60:
            continue
        mod_name = DECK_AGENTS.get(fn)
        agent, reset = gh.agent, (lambda: None)
        if mod_name:
            try:
                m = importlib.import_module(mod_name)
                agent = (lambda mm: (lambda o: mm.agent(o)))(m)
                reset = (lambda mm: (lambda: getattr(mm, "reset_state", lambda: None)()))(m)
            except Exception:
                pass
        w = LADDER_WEIGHTS.get(fn, 1) if weighted else 1
        e = dict(name=fn[5:-4], deck=deck, agent=agent, reset=reset, weight=w)
        # ★重みのぶん複製する。呼び出し側は pool を均等に回すだけでよい
        out.extend([e] * max(int(w), 1))
    return out


def play(my_mod, my_deck, opp, first):
    """1試合。first=0 なら自分が先攻側。戻り値 (勝ち, 終局状態)。"""
    my_mod.reset_state()
    opp["reset"]()
    d0, d1 = (my_deck, opp["deck"]) if first == 0 else (opp["deck"], my_deck)
    obs, _ = battle_start(d0, d1)
    if obs is None:
        return None, {}
    last = None
    steps = 0
    try:
        while obs["current"]["result"] == -1 and steps < 3000:
            pl = obs["current"]["yourIndex"]
            if pl == first:
                last = obs
                obs = battle_select(my_mod.agent(obs))
            else:
                obs = battle_select(opp["agent"](obs))
            steps += 1
        res = to_observation_class(obs).current.result
        won = (res == first)
    finally:
        battle_finish()
    st = {}
    if last is not None:
        cur = last["current"]
        me = cur["players"][cur["yourIndex"]]
        st = dict(turn=cur.get("turn") or 0,
                  board=1 + len([e for e in (me.get("bench") or []) if e]),
                  deck=me.get("deckCount") or 0)
    return won, st


def run(my_mod, my_deck_path, reps, games, weighted=True, quiet=False):
    my_deck = read_deck(my_deck_path)
    pool = build_pool(weighted)
    # 重みに応じて対戦相手の並びを作る
    seq = []
    for p in pool:
        seq += [p] * p["weight"]
    rates = []
    per = collections.defaultdict(lambda: [0, 0])
    win_board, lose_board, win_turn, lose_turn = [], [], [], []
    for r in range(reps):
        w = g = 0
        for i in range(games):
            opp = seq[i % len(seq)]
            won, st = play(my_mod, my_deck, opp, i % 2)
            if won is None:
                continue
            g += 1
            w += won
            per[opp["name"]][0] += 1
            per[opp["name"]][1] += won
            (win_board if won else lose_board).append(st.get("board", 0))
            (win_turn if won else lose_turn).append(st.get("turn", 0))
        if g:
            rates.append(100.0 * w / g)
    mean = statistics.mean(rates) if rates else 0
    se = statistics.pstdev(rates) / (len(rates) ** 0.5) if len(rates) > 1 else 0
    if not quiet:
        print("=" * 62)
        print("環境代表アリーナ  %d反復 × %d試合  (重み付け %s)"
              % (reps, games, "あり=ラダー頻度" if weighted else "なし=均等"))
        print("=" * 62)
        print("  総合 %.1f%% ±%.1f   各回 %s"
              % (mean, se, [round(x) for x in rates]))
        m = lambda a: (sum(a) / len(a)) if a else 0
        print("  終局の頭数  勝ち %.2f / 負け %.2f" % (m(win_board), m(lose_board)))
        print("  ターン数    勝ち %.1f / 負け %.1f" % (m(win_turn), m(lose_turn)))
        print("\n--- 相手別 ---")
        print("%-24s %6s %8s" % ("相手デッキ", "試合", "勝率"))
        for nm, (g, w) in sorted(per.items(), key=lambda kv: 100.0 * kv[1][1] / max(kv[1][0], 1)):
            print("%-24s %6d %7.0f%%" % (nm[:24], g, 100.0 * w / max(g, 1)))
    return mean, se, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="wanaider_heuristic")
    ap.add_argument("--deck", default="../meta/top_decks/deck_wanaider_top2.csv")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--games", type=int, default=48)
    ap.add_argument("--even", action="store_true", help="重み付けせず均等に当たる")
    args = ap.parse_args()
    mod = importlib.import_module(args.agent)
    run(mod, args.deck, args.reps, args.games, not args.even)


if __name__ == "__main__":
    main()
