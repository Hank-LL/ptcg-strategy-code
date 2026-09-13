#!/usr/bin/env python3
"""メガルカリオex 専用ヒューリスティック(**相手役として使う**)。

## 教材
自分のラダー実戦28試合(相手15勝13敗)から、実際の使い手の打ち回しを抽出した。
※ 上位帯(1100〜)にはこのデッキがほぼ存在しないので([[ptcg-meta-stratification]])、
   教材は中位帯=実際に自分が当たっている相手。

## 実戦の構築(12試合9勝=75%の最多構築。deck_mega_lucario_real.csv)
  ポケモン17: メガルカリオex4 / リオル4 / ソルロック3 / ルナトーン2 /
              ハリテヤマ2 / マクノシタ2
  グッズ16 : ファイトゴング4 / パワープロテイン4 / ダークボール4 /
              ポケパッド2 / ポケモンいれかえ2
  どうぐ1  : ヒーローマント
  サポート11: リーリエの決心4 / ゼイユ4 / ボスの指令3
  スタジアム1: グラビティーマウンテン
  基本闘エネ14

## カードの働き
  メガルカリオex(678) HP340 ※リオルからの**1進化**
    オーラジャブ [闘]     = 130 + **トラッシュから基本闘エネを3枚までベンチに**
    メガブレイブ [闘,闘]  = **270**(次の自分の番は使えない)
  ルナトーン(675) 特性ルナサイクル
    = ソルロックが場にいるなら、手札の基本闘エネを1枚トラッシュして**3枚ドロー**
      (1ターン1回。実戦で**3.50回/試合**使われている最頻出の行動)
  ハリテヤマ(674) 特性ヘヴィーホーキャッチャー
    = **手札から進化させたとき**、相手のベンチを1体バトル場に引きずり出す
  パワープロテイン(1141) = このターン闘ポケモンの打点+30 → メガブレイブ300
  グラビティーマウンテン = 2進化ポケモンのHP-30(相手にも効く)

## 実戦の頻度(1試合あたり) — これに寄せるのが目標
  基本闘エネを付ける 4.57 / ルナトーンの特性 3.50 / ファイトゴング 2.79
  ダークボール 2.75 / パワープロテイン 2.39 / メガルカリオexに進化 1.79
  リオルを出す 1.61 / **オーラジャブ 2.29 / メガブレイブ 0.96**
  メガルカリオが場に出た試合 96%(初出ターン中央値4)
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, to_observation_class)
import generic_heuristic as gh

RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE = 676, 675
MAKUHITA, HARIYAMA = 673, 674
FIGHT_ENERGY = 6
E_FIGHT = 6
POWER_PROTEIN = 1141        # 闘ポケモンの打点+30(このターン)
FIGHTING_GONG = 1142        # 闘エネ/たね闘ポケモンをサーチ
DARK_BALL = 1102            # 山札の下7枚からポケモン1枚
POKE_PAD = 1152
SWITCH_CARD = 1123
LILLIE = 1227
ZEIYU = 1192                # 手札を捨てて5枚ドロー(先攻1ターン目から可)
BOSS_ORDERS = 1182
HERO_CLOAK = 1159
GRAVITY_MOUNTAIN = 1252

ATK_MEGA_BRAVE = None
ATK_AURA_JAB = None
ATK_WILD_PRESS = None

USE_GENERIC_BASE = True
USE_EVOLVE_RUSH = True             # リオル→メガルカリオexを最短で
USE_ENERGY_ROUTING = True
USE_LUNAR_CYCLE = True             # ルナトーンのドロー(最頻出の行動)
USE_PROTEIN_BEFORE_ATTACK = True   # 殴る直前にパワープロテイン
USE_HARIYAMA_PULL = True           # ハリテヤマは引きずり出し目的で進化
USE_AURA_JAB_ENGINE = True
# 攻撃はターンを終えるので、タダの行動(特性/進化/エネ付け/展開)を先にやる
USE_ACT_BEFORE_ATTACK = True
PREP_MIN_SCORE = 1000.0         # オーラジャブを主軸に(実戦2.29 vs メガブレイブ0.96)

_turn_seen = -1
_protein_used = False
_lunar_used = False


def reset_state():
    global _turn_seen, _protein_used, _lunar_used
    _turn_seen = -1
    _protein_used = False
    _lunar_used = False


def _update_turn_state(state):
    global _turn_seen, _protein_used, _lunar_used
    if state.turn != _turn_seen:
        _turn_seen = state.turn
        _protein_used = False
        _lunar_used = False


def _resolve_attacks():
    global ATK_MEGA_BRAVE, ATK_AURA_JAB, ATK_WILD_PRESS
    if ATK_MEGA_BRAVE is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Mega Brave":
            ATK_MEGA_BRAVE = a.attackId
        elif a.name == "Aura Jab":
            ATK_AURA_JAB = a.attackId
        elif a.name == "Wild Press":
            ATK_WILD_PRESS = a.attackId


class Plan:
    __slots__ = ("hand_counts", "field_counts", "bench_free", "active",
                 "lucario_in_play", "solrock_in_play", "op_active", "hurt_lucario",
                 "active_energy")

    def __init__(self):
        self.hand_counts = {}
        self.field_counts = {}
        self.bench_free = 0
        self.active = None
        self.lucario_in_play = 0
        self.solrock_in_play = 0
        self.op_active = None
        self.hurt_lucario = None
        self.active_energy = 0


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
    p.lucario_in_play = p.field_counts.get(MEGA_LUCARIO_EX, 0)
    p.solrock_in_play = p.field_counts.get(SOLROCK, 0)
    p.op_active = (op.active or [None])[0]
    p.active_energy = len(_energy_units(p.active)) if p.active is not None else 0
    for c in field:
        if c.id == MEGA_LUCARIO_EX:
            mx = getattr(c, "maxHp", None) or c.hp or 1
            if (c.hp or 0) <= mx * 0.45:
                p.hurt_lucario = c
    return p


def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type

    # ---- 進化 ----
    if t == OptionType.EVOLVE and USE_EVOLVE_RUSH:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 800.0
        if card.id == MEGA_LUCARIO_EX:
            return 6000.0
        if card.id == HARIYAMA and USE_HARIYAMA_PULL:
            # ★手札から進化させた**そのとき**だけ、相手のベンチを引きずり出せる。
            #   実戦で0.79回/試合。倒せる的を引き出す手段として価値がある。
            return 3800.0
        return 800.0

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
            return 2000.0 if dest.id == MEGA_LUCARIO_EX else -1000.0
        if cid != FIGHT_ENERGY:
            return 0.0
        n = len(_energy_units(dest))
        if dest.id == MEGA_LUCARIO_EX:
            # オーラジャブは闘1個で撃てる。メガブレイブ用に2個目まで。
            if n == 0:
                return 5000.0     # まず1個 = オーラジャブが撃てる
            if n == 1:
                return 3000.0     # 2個目 = メガブレイブ圏
            return -600.0
        if dest.id == RIOLU:
            return 2500.0 if n < 2 else -400.0   # 進化で引き継ぐ
        if dest.id in (HARIYAMA, MAKUHITA):
            return 600.0 if n < 3 else -400.0
        return 100.0

    # ---- 特性 ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    card = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    card = me.bench[o.index or 0]
                elif o.area == AreaType.STADIUM and state.stadium:
                    card = state.stadium[0]
            except (IndexError, TypeError):
                card = None
        if card is not None and card.id == LUNATONE and USE_LUNAR_CYCLE:
            # ★ルナサイクル: ソルロックが場にあり、手札の基本闘エネを1枚捨てて3枚ドロー。
            #   場全体で1ターン1回。**実戦で3.50回/試合**と最頻出の行動。
            #   ただし闘エネを捨てるので、手札に2枚以上あるときだけ。
            if _lunar_used:
                return -2000.0
            if p.solrock_in_play == 0:
                return -1500.0
            # ★「手札に2枚以上」は厳しすぎた(2026-07-29 実測)。
            #   そもそもゲーム側は**手札に闘エネがあるときしか選択肢を出さない**ので、
            #   選択肢が出た局面は全体の9%しかない。実戦の使い手は3.50回/試合
            #   使っており、これは**出たらほぼ必ず使う**水準。
            #   うちは2枚条件で74%断って0.90回/試合まで落ちていた。
            #   3枚引けば闘エネ(デッキに14枚)も戻ってくるので、出し惜しみしない。
            if p.hand_counts.get(FIGHT_ENERGY, 0) < 1:
                return -800.0
            # ※「最後の1枚は付ける方に回す」ガードも入れてみたが、
            #   実測で 1.45回/試合 に留まり実戦(3.50)に遠かったので外した。
            #   3枚引けば闘エネ(14枚)が戻る確率が高く、出し惜しみは損。
            return 4200.0
        return 400.0

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        _resolve_attacks()
        if o.attackId == ATK_MEGA_BRAVE:
            # 270。撃てるなら強いが、次の番は使えない。
            # 実戦の比率は オーラジャブ2.29 : メガブレイブ0.96 で、
            # **オーラジャブが主軸**。倒せるときだけメガブレイブを優先する。
            # ★実戦比は オーラジャブ2.29 : メガブレイブ0.96。
            #   「オーラジャブで落ちる相手ならオーラジャブ」で十分だが、
            #   最初の実装は 4000 まで下げすぎて 0.30回/試合になった。
            #   オーラジャブ(5000)より僅かに上に置き、落とせない相手には最優先。
            if USE_AURA_JAB_ENGINE and p.op_active is not None:
                hp = p.op_active.hp or 0
                if hp > 130:
                    return 9000.0     # オーラジャブでは落ちない相手
                # ★オーラジャブは130の打点だけでなく
                #   **トラッシュから基本闘エネを3枚までベンチに付ける**エンジン。
                #   実戦比 2.29 : 0.96 でオーラジャブが主軸なのはこのため。
                #   落とせる相手にはオーラジャブを優先する。
                return 4500.0
            return 9000.0
        if o.attackId == ATK_AURA_JAB:
            return 5000.0             # 130 + トラッシュから闘エネ3枚をベンチに
        if o.attackId == ATK_WILD_PRESS:
            return 3000.0             # 210(自分にも70)
        return 600.0

    # ---- 場に出す / グッズ・サポート ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id
        if cid == RIOLU:
            return 4200.0 if p.bench_free > 0 else 100.0
        if cid == SOLROCK:
            # ルナトーンの特性の前提条件。早めに置きたい。
            if p.solrock_in_play == 0 and p.bench_free > 0:
                return 3000.0
            return 300.0 if p.bench_free > 0 else 100.0
        if cid == LUNATONE:
            return 2600.0 if (p.bench_free > 0
                              and p.field_counts.get(LUNATONE, 0) == 0) else 300.0
        if cid == MAKUHITA:
            return 1200.0 if p.bench_free > 0 else 100.0
        if cid == POWER_PROTEIN and USE_PROTEIN_BEFORE_ATTACK:
            # ★このターン殴れるときだけ。+30で 270→300 / 130→160。
            if _protein_used:
                return -2000.0
            act = p.active
            if act is not None and act.id == MEGA_LUCARIO_EX and p.active_energy >= 1:
                return 5500.0     # 攻撃(5000)より先に使う
            return -500.0
        if cid == FIGHTING_GONG:
            return 2800.0         # 闘エネ or たね闘ポケモンをサーチ(実戦2.79)
        if cid == DARK_BALL:
            return 2700.0 if p.lucario_in_play == 0 else 1800.0
        if cid == POKE_PAD:
            return 1600.0
        if cid == BOSS_ORDERS:
            return 1800.0
        if cid == ZEIYU:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 2000.0 if hand <= 4 else -600.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            my_prize = len(me.prize) if me.prize is not None else 6
            if my_prize >= 6 and hand <= 6:
                return 2400.0
            return 1600.0 if hand <= 5 else -900.0
        if cid == SWITCH_CARD:
            return 900.0
        if cid == GRAVITY_MOUNTAIN:
            return 1200.0
    return 0.0


def _placement_bonus(o, obs, state, me, p):
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == MEGA_LUCARIO_EX:
        return 3000.0
    if card.id == RIOLU:
        return 1800.0
    if card.id == HARIYAMA:
        return 1000.0
    return 300.0


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
        global _protein_used, _lunar_used
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

        # ★攻撃はターンを終わらせるので、**タダの行動は先に済ませる**。
        #   実測: ルナサイクルが選べた72局面のうち47%を取り逃がしており、
        #   その24件は攻撃を優先していた(ルナトーンの特性 1.46回/試合。
        #   実戦の使い手は3.50回/試合)。
        #   ドロー・進化・エネ付けは攻撃の前に全部やる。
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

        # 使用済みフラグ(1ターン1回のもの)
        if select.option and ctx == SelectContext.MAIN:
            top = select.option[order[0]]
            if top.type == OptionType.PLAY:
                c = gh._hand_card(obs, top.index, me)
                if c is not None and c.id == POWER_PROTEIN:
                    _protein_used = True
            elif top.type == OptionType.ABILITY:
                c = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if c is None:
                    try:
                        if top.area == AreaType.BENCH and me.bench:
                            c = me.bench[top.index or 0]
                        elif top.area == AreaType.ACTIVE and me.active:
                            c = me.active[top.index or 0]
                    except (IndexError, TypeError):
                        c = None
                if c is not None and c.id == LUNATONE:
                    _lunar_used = True

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        # オーラジャブのエネ加速など「N枚まで」は上限まで取る
        if ctx in (SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO,
                   SelectContext.TO_HAND, SelectContext.TO_FIELD) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
