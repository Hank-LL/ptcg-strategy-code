#!/usr/bin/env python3
"""メガスターミーex 専用ヒューリスティック(**相手役として使う**)。

## 教材
自分のラダー実戦7試合(相手6勝1敗)。上位帯には5試合しか無い([[ptcg-meta-stratification]])。

## 実戦の構築(5試合4勝の最多構築。deck_mega_starmie_real.csv)
  ポケモン10: エースバーン4 / ヒトデマン3 / メガスターミーex3
  グッズ19 : なかよしポフィン4 / クラッシュハンマー4 / ポケギア3.0 4 /
              メガシグナル4 / 夜のタンカ2 / ハイパーボール1
  どうぐ1  : ヒーローマント
  サポート12: セイジ4 / リーリエの決心4 / ミツルの思いやり4 ※+クラウン2/トウコ2/ボス1
  エネ13   : 基本水9 / イグニッションエネルギー4

## このデッキの正体: 速い1進化 + ベンチ狙撃
  メガスターミーex(1031) HP330 ※ヒトデマンからの**1進化**
    **ジェッティングブロー [水] = 120 + 相手ベンチ1体に50** ← 主力(実戦3.14回/試合)
    ネビュラビーム [無,無,無] = 210(弱点・抵抗力・効果の影響を受けない)
  エースバーン(666) 特性 = 手札にあれば**裏向きでバトル場に置ける**(初手要員)
    ターボフレア[無] = 50 + 山札から基本エネ3枚まで**ベンチに**付ける ← 加速
  セイジ(1189) = **山札から「特性を持たない進化ポケモン」を直接場に乗せて進化**
                 → ヒトデマン→メガスターミーex を1枚で完結できる展開の要
  メガシグナル(1145) = 山札からメガシンカexをサーチ
  ミツルの思いやり(1229) = メガシンカexを全回復しエネを移す
  イグニッションエネルギー(17) = ターン終了時にトラッシュされるが強力

## 実戦の頻度(1試合あたり) — 実装の目標
  ジェッティングブロー **3.14** / ネビュラビーム 1.14 / ターボフレア 0.57
  主砲が場に出た試合 100%(初出ターン中央値**3** = 非常に速い)

ワナイダー視点では **ベンチに50を毎ターン飛ばしてくる**のが厄介
(頭数が打点なので削られると弱くなる)。相手役として価値が高い。
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, to_observation_class)
import generic_heuristic as gh

STARYU, MEGA_STARMIE_EX = 1030, 1031
# ★上位帯の実際の構築は **メガスターミーex3 + メガユキメノコex3** の2枚看板
#   (2026-07-29、リプレイ1784試合の索引で最多構築2種とも採用)。
#   ユキメノコを実装していなかったため、この相手役は本物より大幅に弱かった。
SNORUNT, MEGA_FROSLASS_EX = 860, 861
CINDERACE = 666
SURFING_BEACH = 1262        # スタジアム: 各プレイヤー1回、水どうしで入れ替え
HAND_TRIMMER = 1087         # 両者手札5枚まで捨てる(相手が先)
XEROSIC = 1197              # 相手の手札を3枚まで捨てさせる
CHEREN = 1224               # 3枚ドロー
WATER_ENERGY, IGNITION_ENERGY = 3, 17
E_WATER = 3
POFFIN = 1086
CRUSH_HAMMER = 1120
POKEGEAR = 1122
MEGA_SIGNAL = 1145          # メガシンカexをサーチ
NIGHT_STRETCHER = 1097
ULTRA_BALL = 1121
HERO_CLOAK = 1159
SAGE = 1189                 # 山札から進化ポケモンを直接乗せる
LILLIE = 1227
WALLACE_CARE = 1229         # メガexを全回復
HARLEQUIN = 1223
HILDA = 1225                # 進化ポケモン+エネをサーチ
BOSS_ORDERS = 1182

ATK_JETTING_BLOW = None
ATK_NEBULA_BEAM = None
ATK_TURBO_FLARE = None
ATK_RESENTFUL_REFRAIN = None    # メガユキメノコex [水] = 相手の手札1枚につき50
ATK_ABSOLUTE_SNOW = None        # メガユキメノコex [水,無,無] = 150 + ねむり

USE_GENERIC_BASE = True
USE_EVOLVE_RUSH = True
USE_ENERGY_ROUTING = True
USE_SEARCH_TARGET = True       # サーチ先は進化ラインを優先
USE_ACT_BEFORE_ATTACK = True   # 攻撃はターンを終えるのでタダの行動を先に
USE_HEAL_WHEN_HURT = True
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
    global ATK_JETTING_BLOW, ATK_NEBULA_BEAM, ATK_TURBO_FLARE
    global ATK_RESENTFUL_REFRAIN, ATK_ABSOLUTE_SNOW
    if ATK_JETTING_BLOW is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Jetting Blow":
            ATK_JETTING_BLOW = a.attackId
        elif a.name == "Nebula Beam":
            ATK_NEBULA_BEAM = a.attackId
        elif a.name == "Turbo Flare":
            ATK_TURBO_FLARE = a.attackId
        elif a.name == "Resentful Refrain":
            ATK_RESENTFUL_REFRAIN = a.attackId
        elif a.name == "Absolute Snow":
            ATK_ABSOLUTE_SNOW = a.attackId


def _atk_damage(aid, p) -> float:
    """そのワザで相手のバトル場に入る打点。

    ★うらみのハミングは **相手の手札1枚につき50**(ダメージは0固定なので
      API の damage からは分からない)。相手の手札枚数を見ないと
      「今なら倒せる」が判定できず、この相手役は本物の動きにならない。
    """
    if aid == ATK_JETTING_BLOW:
        return 120.0
    if aid == ATK_NEBULA_BEAM:
        return 210.0
    if aid == ATK_RESENTFUL_REFRAIN:
        return 50.0 * p.op_hand
    if aid == ATK_ABSOLUTE_SNOW:
        return 150.0
    if aid == ATK_TURBO_FLARE:
        return 50.0
    return 0.0


class Plan:
    __slots__ = ("hand_counts", "field_counts", "bench_free", "active",
                 "starmie_in_play", "active_energy", "op_active", "hurt_starmie",
                 "froslass_in_play", "op_hand", "mega_on_bench")

    def __init__(self):
        self.hand_counts = {}
        self.field_counts = {}
        self.bench_free = 0
        self.active = None
        self.starmie_in_play = 0
        self.active_energy = 0
        self.op_active = None
        self.hurt_starmie = None
        self.froslass_in_play = 0
        self.op_hand = 0
        self.mega_on_bench = False


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
    p.starmie_in_play = p.field_counts.get(MEGA_STARMIE_EX, 0)
    p.froslass_in_play = p.field_counts.get(MEGA_FROSLASS_EX, 0)
    # ★相手の手札枚数(うらみのハミングの打点そのもの)。
    #   相手の手札は見えないので handCount を使う。
    p.op_hand = (len(op.hand) if getattr(op, "hand", None) is not None
                 else (op.handCount or 0))
    p.mega_on_bench = any(x is not None and x.id in (MEGA_STARMIE_EX,
                                                     MEGA_FROSLASS_EX)
                          for x in (me.bench or []))
    p.active_energy = len(_energy_units(p.active)) if p.active is not None else 0
    p.op_active = (op.active or [None])[0]
    for c in field:
        if c.id in (MEGA_STARMIE_EX, MEGA_FROSLASS_EX):
            mx = getattr(c, "maxHp", None) or c.hp or 1
            if (c.hp or 0) <= mx * 0.5:
                p.hurt_starmie = c
    return p


def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type

    # ---- 進化 ----
    if t == OptionType.EVOLVE and USE_EVOLVE_RUSH:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is not None and card.id in (MEGA_STARMIE_EX, MEGA_FROSLASS_EX):
            return 6500.0
        return 800.0

    # ---- サーチ先(進化ラインを優先) ----
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
            if card.id == MEGA_STARMIE_EX:
                return 4200.0 if p.field_counts.get(STARYU) else 2000.0
            if card.id == MEGA_FROSLASS_EX:
                return 4200.0 if p.field_counts.get(SNORUNT) else 2000.0
            if card.id == STARYU:
                return 3600.0 if p.field_counts.get(STARYU, 0) < 2 else 1500.0
            if card.id == SNORUNT:
                return 3600.0 if p.field_counts.get(SNORUNT, 0) < 2 else 1500.0
            if card.id == CINDERACE:
                return 1600.0
            if card.id in (WATER_ENERGY, IGNITION_ENERGY):
                return 2000.0
            return 500.0

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
            return 2000.0 if dest.id in (MEGA_STARMIE_EX,
                                         MEGA_FROSLASS_EX) else -1000.0
        if cid not in (WATER_ENERGY, IGNITION_ENERGY):
            return 0.0
        n = len(_energy_units(dest))
        if dest.id == MEGA_STARMIE_EX:
            # ジェッティングブローは水1個。ネビュラビームは無3個。
            if n == 0:
                return 5200.0
            if n < 3:
                return 3000.0
            return -600.0
        if dest.id == MEGA_FROSLASS_EX:
            # ★うらみのハミングは **水1個だけ** で撃てる。まず1個載せるのが最優先。
            if n == 0:
                return 5300.0
            if n < 3:
                return 1800.0        # アブソリュートスノー(150+ねむり)用
            return -600.0
        if dest.id in (STARYU, SNORUNT):
            return 2500.0 if n < 2 else -400.0   # 進化で引き継ぐ
        return 200.0

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        _resolve_attacks()
        dmg = _atk_damage(o.attackId, p)
        hp = (p.op_active.hp or 0) if p.op_active is not None else 9999
        # ★倒せるワザが最優先。うらみのハミングは相手の手札次第で
        #   300打点にも50打点にもなるので、固定スコアでは選べない。
        if dmg >= hp:
            return 9500.0 + dmg
        if o.attackId == ATK_JETTING_BLOW:
            # 120 + **相手ベンチ1体に50**。ベンチを削る価値があるので
            # 素の打点以上に強い(実戦の最頻出ワザ)。
            return 8000.0
        if o.attackId == ATK_RESENTFUL_REFRAIN:
            # 倒せなくても打点に比例して価値がある
            return 3000.0 + dmg * 8.0
        if o.attackId == ATK_NEBULA_BEAM:
            return 6000.0        # 210(効果の影響を受けない)
        if o.attackId == ATK_ABSOLUTE_SNOW:
            return 5000.0        # 150 + ねむり
        if o.attackId == ATK_TURBO_FLARE:
            return 3000.0        # 50 + 山札から基本エネ3枚をベンチに
        return 600.0

    # ---- なみのりビーチ(スタジアム): 水どうしで入れ替え ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.STADIUM:
            try:
                card = (state.stadium or [None])[0]
            except (AttributeError, IndexError, TypeError):
                card = None
        if card is not None and card.id == SURFING_BEACH:
            # ★メガexが前にいないなら引っ張り出す。ユキメノコとスターミーを
            #   状況で使い分けられるのがこのデッキの強み。
            act_is_mega = (p.active is not None
                           and p.active.id in (MEGA_STARMIE_EX, MEGA_FROSLASS_EX))
            if not act_is_mega and p.mega_on_bench:
                return 4000.0
            # ★-500 では ABILITY のベース(700)を打ち消せず合計200で残り、
            #   1ターン1回の入れ替えを無駄撃ちしうる(audit_suppression.py で検出)。
            return -3000.0
        return 0.0

    # ---- ベンチ狙撃の対象(ジェッティングブローの50) ----
    if ctx in (SelectContext.DAMAGE, SelectContext.DAMAGE_COUNTER) \
            and t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        if o.playerIndex is not None and o.playerIndex == state.yourIndex:
            return -2000.0
        hp = card.hp or 0
        d = gh._CARD.get(card.id)
        pz = 3 if (d and d.megaEx) else 2 if (d and d.ex) else 1
        if hp <= 50:
            return 4000.0 + pz * 500.0    # 50で落とせる
        mx = getattr(card, "maxHp", None) or hp or 1
        return 1000.0 + 1200.0 * min(50, hp) / mx + pz * 200.0

    # ---- 場に出す / グッズ・サポート ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id
        if cid in (STARYU, SNORUNT):
            return 4600.0 if p.bench_free > 0 else 100.0
        if cid == CHEREN:
            return 1500.0
        if cid == CINDERACE:
            return 2000.0 if p.bench_free > 0 else 100.0
        if cid == SAGE:
            # ★山札から進化ポケモンを直接乗せる。ヒトデマン/ユキワラシが
            #   場にいれば1枚でメガexが完成する展開の要。
            if p.field_counts.get(STARYU) or p.field_counts.get(SNORUNT):
                return 5200.0
            return 600.0
        if cid == MEGA_SIGNAL:
            return 3400.0 if (p.starmie_in_play + p.froslass_in_play) == 0 else 900.0
        if cid == POFFIN:
            # HP70以下のたね2体をベンチに(ヒトデマン/ユキワラシとも HP70)
            n_basic = p.field_counts.get(STARYU, 0) + p.field_counts.get(SNORUNT, 0)
            if p.bench_free >= 2 and n_basic < 3:
                return 4400.0
            return 400.0
        if cid in (HAND_TRIMMER, XEROSIC):
            # ★手札干渉。**うらみのハミングの打点を自分で下げてしまう**ので、
            #   ユキメノコで殴れる状況では使わない(2026-07-29)。
            #   相手の手札が厚く、こちらがハミングを撃てないときだけ価値がある。
            can_refrain = (p.active is not None
                           and p.active.id == MEGA_FROSLASS_EX
                           and len(_energy_units(p.active)) >= 1)
            if can_refrain:
                return -1500.0
            return 1600.0 if p.op_hand >= 6 else 300.0
        if cid == HILDA:
            return 3000.0 if (p.starmie_in_play + p.froslass_in_play) == 0 else 1200.0
        if cid == WALLACE_CARE and USE_HEAL_WHEN_HURT:
            return 3600.0 if p.hurt_starmie is not None else -800.0
        if cid == POKEGEAR:
            return 2200.0
        if cid == ULTRA_BALL:
            hand = len(me.hand) if me.hand is not None else me.handCount
            no_mega = (p.starmie_in_play + p.froslass_in_play) == 0
            return 2400.0 if (no_mega and hand >= 4) else 600.0
        if cid == NIGHT_STRETCHER:
            return 1600.0
        if cid == CRUSH_HAMMER:
            return 1500.0
        if cid == BOSS_ORDERS:
            return 1800.0
        if cid == HARLEQUIN:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1400.0 if hand <= 3 else -700.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            my_prize = len(me.prize) if me.prize is not None else 6
            if my_prize >= 6 and hand <= 7:
                return 2400.0
            return 1800.0 if hand <= 6 else -900.0
    return 0.0


def _placement_bonus(o, obs, state, me, p):
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id in (MEGA_STARMIE_EX, MEGA_FROSLASS_EX):
        return 3000.0
    if card.id in (STARYU, SNORUNT):
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
        # ターボフレアのエネ3枚など「N枚まで」は上限まで取る
        if ctx in (SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO,
                   SelectContext.TO_HAND, SelectContext.TO_FIELD) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
