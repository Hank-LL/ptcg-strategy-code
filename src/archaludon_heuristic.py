#!/usr/bin/env python3
"""ブリジュラスex(Archaludon ex) 専用ヒューリスティック(**相手役として使う**)。

## 教材
自分のラダー実戦17試合(相手10勝7敗)。上位帯にはこのデッキが無いので
([[ptcg-meta-stratification]])、教材は実際に自分が当たっている相手。

## 実戦の構築(9試合7勝=78%の最多構築。deck_archaludon_real.csv)
  ポケモン13: ブリジュラスex4 / ジュラルドン4 / エースバーン4 / ジーランス1
  グッズ19 : ポケパッド4 / ジャンボアイス4 / ポケギア3.0 4 /
              ハイパーボール4 / 夜のタンカ3
  どうぐ1  : ヒーローマント
  サポート12: リーリエの決心4 / 探検家の先導4 / ボスの指令3 / ジャッジマン1
  スタジアム4: フルメタルラボ
  基本鋼エネ11

## このデッキの正体: 硬い壁で殴り続ける
  ブリジュラスex(190) HP300 ※ジュラルドンからの1進化
    **メタルディフェンダー [鋼,鋼,鋼] = 220**(次の相手番は弱点なし)
    特性アセンブルアロイ = **手札から進化させたとき、トラッシュから
      基本鋼エネを2枚まで鋼ポケモンに好きなように付ける**(エネ加速の要)
  フルメタルラボ(1244) = 鋼ポケモンが相手のワザから**受けるダメージ-30**
  ジャンボアイス(1147) = エネ3個以上付いたバトル場を**80回復**
  エースバーン(666) 特性 = 手札にあるなら**裏向きでバトル場に置ける**(初手要員)
    ターボフレア[無] = 50 + 山札から基本エネ3枚まで付ける
  ジーランス(57) 特性メモリーダイブ = 進化ポケモンが進化前のワザを使える

## 実戦の頻度(1試合あたり) — 実装の目標
  メタルディフェンダー **4.18** / レイジングハンマー 0.65 / ハンマーイン 0.65
  ターボフレア 0.35
  主砲が場に出た試合 94%(初出ターン中央値4) / 平均15.3ターン

**要は「220を毎ターン撃ち続ける」デッキ**。硬さ(HP300 + ラボ-30 + 回復80)で
受け切りながら殴る。相手役としてはここを再現できれば十分。
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, to_observation_class)
import generic_heuristic as gh

DURALUDON, ARCHALUDON_EX = 169, 190
CINDERACE, RELICANTH = 666, 57
METAL_ENERGY = 8
E_METAL = 8
POKE_PAD = 1152
JUMBO_ICE = 1147            # エネ3個以上のバトル場を80回復
POKEGEAR = 1122             # 上7枚からサポート1枚
ULTRA_BALL = 1121
NIGHT_STRETCHER = 1097
HERO_CLOAK = 1159
LILLIE = 1227
EXPLORER_GUIDE = 1185       # 上6枚から2枚を手札、残りトラッシュ
BOSS_ORDERS = 1182
JUDGE = 1213
FULL_METAL_LAB = 1244       # 鋼ポケモンの被ダメ-30

ATK_METAL_DEFENDER = None
ATK_RAGING_HAMMER = None
ATK_HAMMER_IN = None
ATK_TURBO_FLARE = None

USE_GENERIC_BASE = True
USE_EVOLVE_RUSH = True         # ジュラルドン→ブリジュラスexを最短で
USE_ENERGY_ROUTING = True      # 鋼エネを主砲に集める(メタルディフェンダーは3個)
USE_ACT_BEFORE_ATTACK = True   # 攻撃はターンを終えるのでタダの行動を先に
USE_LAB_FIRST = True           # フルメタルラボは早めに張る(被ダメ-30)
USE_HEAL_WHEN_HURT = True      # ジャンボアイスで80回復
PREP_MIN_SCORE = 1000.0

_turn_seen = -1


def reset_state():
    global _turn_seen
    _turn_seen = -1


def _update_turn_state(state):
    global _turn_seen
    if state.turn != _turn_seen:
        _turn_seen = state.turn


def _resolve_attacks():
    global ATK_METAL_DEFENDER, ATK_RAGING_HAMMER, ATK_HAMMER_IN, ATK_TURBO_FLARE
    if ATK_METAL_DEFENDER is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Metal Defender":
            ATK_METAL_DEFENDER = a.attackId
        elif a.name == "Raging Hammer":
            ATK_RAGING_HAMMER = a.attackId
        elif a.name == "Hammer In":
            ATK_HAMMER_IN = a.attackId
        elif a.name == "Turbo Flare":
            ATK_TURBO_FLARE = a.attackId


class Plan:
    __slots__ = ("hand_counts", "field_counts", "bench_free", "active",
                 "arch_in_play", "active_energy", "op_active", "hurt_active",
                 "lab_up")

    def __init__(self):
        self.hand_counts = {}
        self.field_counts = {}
        self.bench_free = 0
        self.active = None
        self.arch_in_play = 0
        self.active_energy = 0
        self.op_active = None
        self.hurt_active = False
        self.lab_up = False


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
    p.active = (me.active or [None])[0]
    p.arch_in_play = p.field_counts.get(ARCHALUDON_EX, 0)
    p.active_energy = len(_energy_units(p.active)) if p.active is not None else 0
    p.op_active = (op.active or [None])[0]
    if p.active is not None:
        mx = getattr(p.active, "maxHp", None) or p.active.hp or 1
        p.hurt_active = (p.active.hp or 0) <= mx - 80
    try:
        p.lab_up = bool(state.stadium) and state.stadium[0].id == FULL_METAL_LAB
    except (IndexError, AttributeError, TypeError):
        p.lab_up = False
    return p


def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type

    # ---- 進化(アセンブルアロイでエネ2枚が付いてくるので最優先) ----
    if t == OptionType.EVOLVE and USE_EVOLVE_RUSH:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is not None and card.id == ARCHALUDON_EX:
            # ★手札から進化させたときだけ「トラッシュから基本鋼エネ2枚」が付く。
            #   メタルディフェンダーは鋼3個なので、これがエネ加速の要。
            return 6500.0
        return 800.0

    # ---- 進化時のエネ配分(アセンブルアロイ) ----
    if ctx in (SelectContext.ATTACH_TO, SelectContext.TO_FIELD) \
            and t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            if card.id == ARCHALUDON_EX:
                n = len(_energy_units(card))
                return 4000.0 if n < 3 else 500.0
            if card.id == DURALUDON:
                return 1500.0        # 進化で引き継ぐ
            return 100.0

    # ---- エネルギー ----
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
        if dest is None:
            return 0.0
        if cid == HERO_CLOAK:
            return 2000.0 if dest.id == ARCHALUDON_EX else -1000.0
        if cid != METAL_ENERGY:
            return 0.0
        n = len(_energy_units(dest))
        if dest.id == ARCHALUDON_EX:
            return 5000.0 if n < 3 else -600.0   # メタルディフェンダーは3個
        if dest.id == DURALUDON:
            return 2500.0 if n < 3 else -400.0   # 進化で引き継ぐ
        return 100.0

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        _resolve_attacks()
        if o.attackId == ATK_METAL_DEFENDER:
            return 9000.0            # 220。実戦4.18回/試合の主力
        if o.attackId == ATK_TURBO_FLARE:
            return 3000.0            # 50 + 山札から基本エネ3枚(序盤の加速)
        if o.attackId == ATK_RAGING_HAMMER:
            return 2000.0            # 80 + 自分のダメカン×10
        if o.attackId == ATK_HAMMER_IN:
            return 1200.0            # 30
        return 600.0

    # ---- 場に出す / グッズ・サポート ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id
        if cid == DURALUDON:
            return 4200.0 if p.bench_free > 0 else 100.0
        if cid == CINDERACE:
            # 初手要員。ターボフレアで加速もできる。
            return 2000.0 if p.bench_free > 0 else 100.0
        if cid == RELICANTH:
            return 900.0 if p.bench_free > 0 else 100.0
        if cid == FULL_METAL_LAB and USE_LAB_FIRST:
            # ★鋼ポケモンの被ダメ-30。HP300と噛み合って非常に硬くなる。
            #   既に自分のラボが出ているなら重ねない。
            if p.lab_up:
                return -1500.0
            return 3400.0
        if cid == JUMBO_ICE and USE_HEAL_WHEN_HURT:
            # エネ3個以上のバトル場を80回復。削れているときだけ。
            if p.hurt_active and p.active_energy >= 3:
                return 3600.0
            return -800.0
        if cid == EXPLORER_GUIDE:
            return 2600.0        # 上6枚から2枚(実戦の主要ドロー)
        if cid == POKEGEAR:
            return 2200.0
        if cid == ULTRA_BALL:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 2000.0 if (p.arch_in_play == 0 and hand >= 4) else 600.0
        if cid == POKE_PAD:
            return 1600.0
        if cid == NIGHT_STRETCHER:
            return 1400.0
        if cid == BOSS_ORDERS:
            return 1800.0
        if cid == JUDGE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1500.0 if hand <= 3 else -600.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            my_prize = len(me.prize) if me.prize is not None else 6
            if my_prize >= 6 and hand <= 6:
                return 2400.0
            return 1600.0 if hand <= 5 else -900.0
    return 0.0


def _placement_bonus(o, obs, state, me, p):
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == ARCHALUDON_EX:
        return 3000.0
    if card.id == DURALUDON:
        return 1800.0
    if card.id == CINDERACE:
        return 1200.0
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

        # ★攻撃はターンを終わらせるので、タダの行動を先に済ませる
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

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        # アセンブルアロイのエネ2枚など「N枚まで」は上限まで取る
        if ctx in (SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO,
                   SelectContext.TO_HAND, SelectContext.TO_FIELD) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
