#!/usr/bin/env python3
"""ドラパルトex 専用ヒューリスティック(**相手役として使う**)。

## なぜ作るか
自分のラダー90試合で **対ドラパルトが6戦1勝(17%)** と最悪のマッチだった。
ところがローカルでは generic が操縦するせいで **100%勝てて**しまい、
シミュレータで検証できなかった([[ptcg-ladder-meta-and-arena]])。
まともに殴ってくる相手を用意しないと対策を検証できない。

## このデッキの正体
ドラパルトex(121) HP320
  ファントムダイブ [炎,超] = **2エネで 200 + 相手ベンチにダメカン6個を好きなように**
  ジェットヘッドバット [無] = 70
進化ライン: ドラメシヤ(119,HP70) → ドロンチ(120,HP90) → ドラパルトex
  ふしぎなアメ×2 で ドラメシヤ→ドラパルトex を飛ばせる
ドロンチの特性「偵察指令」= 山札の上2枚を見て1枚を手札に(毎ターン)
スボミー(235) の「かゆいポールン」= **相手は次の番グッズを使えない**
クラッシュハンマー×4 = コインで相手のエネを1個トラッシュ

## 相手役として最重要なのは「ダメカン6個をどこに置くか」
ここを適当にすると、こちらのベンチが削られず**対策の検証にならない**。
実装方針は「**倒せる相手から順に、6個(60ダメージ)で落とせるだけ落とす**」。
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)
import generic_heuristic as gh

DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
BUDEW = 235                 # スボミー(グッズロック)
FEZANDIPITI_EX = 140
LATIAS_EX = 184
MEOWTH_EX = 1071
CRISPIN = 1198              # アカマツ: 基本エネ2枚サーチ、1枚を手札に**1枚を場に付ける**
RARE_CANDY = 1079
BOSS_ORDERS = 1182
# ★サーチ札を一切扱っていなかったため部品が揃わず、主砲が46%しか立たなかった
#   (実戦は100%・初出ターン6)。以下を追加(2026-07-29)。
POFFIN = 1086        # HP70以下のたねを2体**直接ベンチに**(ドラメシヤHP70/スボミーHP30)
ULTRA_BALL = 1121    # 手札2枚を捨てて任意のポケモンをサーチ
POKE_PAD = 1152      # ルールを持たないポケモン(ドラメシヤ/ドロンチ)をサーチ
BROCK_SCOUT = 1210   # たね2枚 or 進化1枚をサーチ
NIGHT_STRETCHER = 1097
LILLIE = 1227
FIRE_ENERGY, PSYCHIC_ENERGY = 2, 5
E_FIRE, E_PSYCHIC = 2, 5

ATK_PHANTOM_DIVE = None     # 実行時に解決
ATK_JET_HEADBUTT = None

USE_GENERIC_BASE = True
USE_EVOLVE_RUSH = True      # 最短でドラパルトexを立てる
USE_ENERGY_ROUTING = True   # 炎+超をドラパルトexに集める
USE_SMART_COUNTERS = True   # ダメカン6個を「倒せる相手」に配る
USE_BUDEW_OPENER = True
# 攻撃はターンを終えるのでタダの行動を先にやる
USE_SEARCH_TARGET = True   # サーチ先は進化ラインを優先する
USE_ACT_BEFORE_ATTACK = True
PREP_MIN_SCORE = 1000.0     # 序盤はスボミーでグッズロック

_turn_seen = -1
_used_recon = set()


def reset_state():
    global _turn_seen, _used_recon
    _turn_seen = -1
    _used_recon = set()


def _update_turn_state(state):
    global _turn_seen, _used_recon
    t = state.turn
    if t != _turn_seen:
        _turn_seen = t
        _used_recon = set()


def _resolve_attacks():
    global ATK_PHANTOM_DIVE, ATK_JET_HEADBUTT
    if ATK_PHANTOM_DIVE is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Phantom Dive":
            ATK_PHANTOM_DIVE = a.attackId
        elif a.name == "Jet Headbutt":
            ATK_JET_HEADBUTT = a.attackId


class Plan:
    __slots__ = ("hand_counts", "field_counts", "bench_free", "gx_in_play",
                 "gx_ready", "active", "op_active", "op_bench")

    def __init__(self):
        self.hand_counts = {}
        self.field_counts = {}
        self.bench_free = 0
        self.gx_in_play = 0
        self.gx_ready = False
        self.active = None
        self.op_active = None
        self.op_bench = []


def _counts(cards):
    c = collections.Counter()
    for x in (cards or []):
        if x is not None:
            c[x.id] += 1
    return c


def _energy_units(c):
    return list(getattr(c, "energies", None) or [])


def _build_plan(obs, state, me, op):
    p = Plan()
    p.hand_counts = _counts(me.hand)
    field = [x for x in (me.active or []) if x] + [x for x in (me.bench or []) if x]
    p.field_counts = _counts(field)
    p.bench_free = (me.benchMax or 5) - len([x for x in (me.bench or []) if x])
    p.gx_in_play = p.field_counts.get(DRAGAPULT_EX, 0)
    p.active = (me.active or [None])[0]
    p.op_active = (op.active or [None])[0]
    p.op_bench = [x for x in (op.bench or []) if x]
    # ファントムダイブは [炎,超] の2個
    if p.active is not None and p.active.id == DRAGAPULT_EX:
        en = _energy_units(p.active)
        p.gx_ready = (sum(1 for e in en if e == E_FIRE) >= 1
                      and sum(1 for e in en if e == E_PSYCHIC) >= 1)
    return p


def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type

    # ---- ダメカン6個の配り先(ファントムダイブ) ----
    # ★ここが相手役として一番大事。倒せる相手から順に落とす。
    if USE_SMART_COUNTERS and ctx in (SelectContext.DAMAGE_COUNTER,
                                      SelectContext.DAMAGE_COUNTER_ANY,
                                      SelectContext.DAMAGE):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        if o.playerIndex is not None and o.playerIndex == state.yourIndex:
            return -2000.0            # 自分には置かない
        hp = card.hp or 0
        d = gh._CARD.get(card.id)
        pz = 3 if (d and d.megaEx) else 2 if (d and d.ex) else 1
        sc = 1000.0
        if hp <= 60:
            # 残り6個(60)で落とせる = サイドが進む。最優先。
            sc += 3000.0 + pz * 600.0 + (60 - hp) * 5.0
        else:
            # 落ちないなら「次に落としやすい」個体を削る
            sc += 800.0 * min(60, hp) / max(hp, 1) + pz * 200.0
        return sc

    # ---- 進化(最短でドラパルトexへ) ----
    if t == OptionType.EVOLVE and USE_EVOLVE_RUSH:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is not None:
            if card.id == DRAGAPULT_EX:
                return 6000.0
            if card.id == DRAKLOAK:
                return 3600.0
        return 800.0

    # ---- エネルギー(炎+超をドラパルトexに) ----
    if t == OptionType.ATTACH and USE_ENERGY_ROUTING:
        card = gh._hand_card(obs, o.index, me) if o.area == AreaType.HAND else None
        cid = card.id if card else None
        dest = None
        try:
            if o.inPlayArea == AreaType.ACTIVE and me.active:
                dest = me.active[o.inPlayIndex or 0]
            elif o.inPlayArea == AreaType.BENCH and me.bench:
                dest = me.bench[o.inPlayIndex or 0]
        except (IndexError, TypeError):
            dest = None
        if dest is None or cid not in (FIRE_ENERGY, PSYCHIC_ENERGY):
            return 0.0
        en = _energy_units(dest)
        want = E_FIRE if cid == FIRE_ENERGY else E_PSYCHIC
        have = sum(1 for e in en if e == want)
        if dest.id == DRAGAPULT_EX:
            # 足りていない色を優先。両方1個ずつで撃てる。
            return 4000.0 if have == 0 else 500.0
        if dest.id in (DRAKLOAK, DREEPY):
            # 進化で引き継ぐので、前借りしておくと立った瞬間に撃てる
            return 3000.0 if have == 0 else 400.0
        return 100.0

    # ---- 山札/トラッシュから何を取るか(サーチ先の選択) ----
    # ★これが未実装だったため、ハイパーボール/ポケパッド/ポフィン/ブロックで
    #   何を取るかが generic 任せになり、**進化ラインが伸びなかった**。
    #   実測(場のドラパルト系の数): 実戦は4ターン目以降2.5〜3.0体を維持するのに
    #   うちは1.5体で止まっていた。
    #   2進化デッキなので **ドラメシヤを並べ続ける**のが全ての前提。
    if USE_SEARCH_TARGET and t == OptionType.CARD and o.area in (
            AreaType.DECK, AreaType.DISCARD, AreaType.LOOKING, AreaType.PRIZE):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.LOOKING:
            try:
                lk = obs.current.looking or []
                card = lk[o.index] if isinstance(o.index, int) and o.index < len(lk) else None
            except (AttributeError, IndexError, TypeError):
                card = None
        if card is None and o.area == AreaType.DECK:
            try:
                dl = obs.select.deck or []
                card = dl[o.index] if isinstance(o.index, int) and o.index < len(dl) else None
            except (AttributeError, IndexError, TypeError):
                card = None
        if card is not None:
            n_line = (p.field_counts.get(DREEPY, 0)
                      + p.field_counts.get(DRAKLOAK, 0)
                      + p.field_counts.get(DRAGAPULT_EX, 0))
            if card.id == DREEPY:
                # 進化元。3体並ぶまでは最優先。
                return 4000.0 if n_line < 3 else 1500.0
            if card.id == DRAKLOAK:
                # 場のドラメシヤを進化させられるなら価値が高い
                return 3600.0 if p.field_counts.get(DREEPY) else 2000.0
            if card.id == DRAGAPULT_EX:
                # 進化先が場にいる/アメがあるなら取る
                if p.field_counts.get(DRAKLOAK) or p.hand_counts.get(RARE_CANDY):
                    return 3800.0
                return 1400.0
            if card.id == RARE_CANDY:
                return 2600.0 if p.field_counts.get(DREEPY) else 900.0
            if card.id in (FIRE_ENERGY, PSYCHIC_ENERGY):
                return 1800.0
            if card.id == BUDEW:
                return 1200.0 if n_line >= 2 else 300.0
            return 500.0

    # ---- アカマツ等で「どのポケモンに付けるか」を選ぶ場面 ----
    if ctx in (SelectContext.ATTACH_TO, SelectContext.TO_FIELD) \
            and t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            if card.id == DRAGAPULT_EX:
                return 4000.0
            if card.id in (DRAKLOAK, DREEPY):
                return 1500.0
            return 100.0

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        _resolve_attacks()
        if o.attackId == ATK_PHANTOM_DIVE:
            return 8000.0
        if o.attackId == ATK_JET_HEADBUTT:
            return 1200.0
        return 600.0

    # ---- 特性(ドロンチの偵察指令は毎ターン使う) ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    card = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    card = me.bench[o.index or 0]
            except (IndexError, TypeError):
                card = None
        if card is not None and card.id == DRAKLOAK:
            if (o.area, o.index) in _used_recon:
                return -2000.0
            return 2500.0
        return 500.0

    # ---- 場に出す ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id
        if cid == DREEPY:
            # ★進化元は何体でも欲しい。実戦はドロンチを3.09回/試合作っており、
            #   ドラメシヤを並べ続けているのが前提(うちは1.23回で止まっていた)。
            n_line = (p.field_counts.get(DREEPY, 0)
                      + p.field_counts.get(DRAKLOAK, 0))
            if p.bench_free <= 0:
                return 100.0
            return 4800.0 if n_line < 3 else 2200.0
        if cid == BUDEW and USE_BUDEW_OPENER:
            # 序盤のグッズロックは強力。盤面が出来る前だけ。
            return 2600.0 if (p.gx_in_play == 0 and p.bench_free > 0) else 300.0
        if cid in (FEZANDIPITI_EX, LATIAS_EX, MEOWTH_EX):
            return 1400.0 if p.bench_free > 0 else 100.0
        if cid == RARE_CANDY:
            # ドラメシヤが場にいて手札にドラパルトexがあるときだけ
            if p.field_counts.get(DREEPY) and p.hand_counts.get(DRAGAPULT_EX):
                return 5000.0
            return -500.0
        if cid == CRISPIN:
            # ★このデッキ唯一のエネ加速。ファントムダイブは[炎,超]の2個必要で、
            #   手張り1回だけでは間に合わない。**最優先で使う**。
            #   (これを入れ忘れていたためファントムダイブが0.50回/試合しか
            #    撃てていなかった)
            return 5200.0
        if cid == BOSS_ORDERS:
            return 1800.0
        # ---- サーチ札(主砲を立てるための部品集め) ----
        need_line = (p.gx_in_play == 0)
        if cid == POFFIN:
            # ドラメシヤ(HP70)を**直接ベンチに2体**。進化元の供給が最優先。
            if p.bench_free >= 2 and p.field_counts.get(DREEPY, 0) < 2:
                return 4600.0
            return 400.0
        if cid == BROCK_SCOUT:
            # たね2枚 or 進化1枚。欠けている方を取れる。
            return 3600.0 if need_line else 1200.0
        if cid == ULTRA_BALL:
            hand = len(me.hand) if me.hand is not None else me.handCount
            if need_line and hand >= 4:
                return 3400.0
            return 600.0
        if cid == POKE_PAD:
            # ドラメシヤ/ドロンチ(ルールなし)をサーチ
            return 3000.0 if need_line else 1200.0
        if cid == NIGHT_STRETCHER:
            return 1600.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            my_prize = len(me.prize) if me.prize is not None else 6
            # ★実戦は2.09回/試合。うちは1.07で足りなかったので条件を緩める。
            if my_prize >= 6 and hand <= 7:
                return 2400.0
            return 1800.0 if hand <= 6 else -900.0
    return 0.0


def _placement_bonus(o, obs, state, me, p):
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == DRAGAPULT_EX:
        return 3000.0
    if card.id == DRAKLOAK:
        return 1200.0
    if card.id == DREEPY:
        return 800.0
    return 300.0


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]
        _update_turn_state(state)
        plan = _build_plan(obs, state, me, op)
        ctx = select.context
        placement = (SelectContext.SWITCH, SelectContext.TO_ACTIVE,
                     SelectContext.SETUP_ACTIVE_POKEMON,
                     SelectContext.SETUP_BENCH_POKEMON)
        scores = []
        for o in select.option:
            base = gh._score_option(o, obs, me, op) if USE_GENERIC_BASE else 0.0
            opp_side = (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex)
            if ctx in placement and not opp_side:
                extra = _placement_bonus(o, obs, state, me, plan)
            else:
                extra = _bonus(o, obs, state, me, op, plan, ctx)
            scores.append(base + extra)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # ★攻撃はターンを終わらせるので、タダの行動(進化/エネ付け/特性/展開)を先に。
        #   実測: 実戦の使い手は**ファントムダイブ4.45回/試合**だが、
        #   この順序ルールが無い実装は0.62回/試合しか撃てていなかった。
        if (USE_ACT_BEFORE_ATTACK and ctx == SelectContext.MAIN
                and select.option
                and select.option[order[0]].type == OptionType.ATTACK):
            prep = [i for i in order
                    if select.option[i].type in (OptionType.ABILITY,
                                                 OptionType.EVOLVE,
                                                 OptionType.ATTACH,
                                                 OptionType.PLAY)
                    and scores[i] >= PREP_MIN_SCORE]
            if prep:
                order = [prep[0]] + [j for j in order if j != prep[0]]

        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                _used_recon.add((top.area, top.index))
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        # ★ダメカンは上限まで配る(6個をばら撒くのがこのデッキの主眼)
        if ctx in (SelectContext.DAMAGE_COUNTER, SelectContext.DAMAGE_COUNTER_ANY,
                   SelectContext.DAMAGE_COUNTER_COUNT) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
