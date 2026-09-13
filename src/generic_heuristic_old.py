"""汎用ルールベース エージェント (デッキ非依存)

設計方針:
- カード固有のハードコードを一切せず、all_card_data()/all_attack() の
  構造化データ(HP, 弱点, 進化前, コスト, ダメージ, ex/mega, 特性有無)
  だけで意思決定する。どんなデッキを持たせても最低限「上手く」動く。
- 効果テキストは解釈しない(可変ダメージ damage=0 の技は最低評価)。
  デッキ固有のコンボの妙味は RL 側に委ねる、という役割分担。

用途:
- RL 環境での「非MAIN選択の委譲先」および「相手役」
- 単体でも提出可能なそこそこ強いベースライン

公開関数:
- agent(obs_dict) -> list[int]     : メインのエージェント関数
- read_deck_csv() -> list[int]     : deck.csv を読む(提出時のデッキ返却用)
"""

import os
from collections import defaultdict

from cg.api import (
    AreaType, EnergyType, OptionType, SelectContext,
    Observation, Pokemon, Card,
    all_card_data, all_attack, to_observation_class,
)

# ---------------------------------------------------------------- マスタ
_CARD = {c.cardId: c for c in all_card_data()}
_ATTACK = {a.attackId: a for a in all_attack()}


def read_deck_csv(path: str = "deck.csv") -> list[int]:
    if not os.path.exists(path):
        path = "/kaggle_simulations/agent/" + path
    with open(path) as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


# ---------------------------------------------------------------- カード評価ヘルパ
def _prize_value(pk: Pokemon) -> int:
    """このポケモンを倒すと相手に渡るサイド枚数(高いほど倒す価値/守る価値)。"""
    d = _CARD.get(pk.id)
    if d is None:
        return 1
    if d.megaEx:
        return 3
    if d.ex:
        return 2
    return 1


def _can_pay(cost_energies: list[int], have: list[int]) -> bool:
    """技コスト(タイプ番号リスト)を、持っているエネルギー(タイプ番号リスト)で払えるか。

    無色(0)は任意のエネルギーで代替可。色指定はまず同色で、足りなければ判定失敗。
    虹(10)は任意色として扱う。
    """
    have_pool = list(have)
    # 色指定を先に消費
    colored = [e for e in cost_energies if e != EnergyType.COLORLESS]
    colorless = [e for e in cost_energies if e == EnergyType.COLORLESS]
    for need in colored:
        # 同色 or 虹 で払う
        idx = next((i for i, e in enumerate(have_pool)
                    if e == need or e == EnergyType.RAINBOW), None)
        if idx is None:
            return False
        have_pool.pop(idx)
    # 無色は残りエネルギーの枚数で払う
    return len(have_pool) >= len(colorless)


def _attack_damage(attack_id: int, attacker: Pokemon, defender: Pokemon) -> int:
    """弱点・抵抗を加味した推定ダメージ。可変(damage=0)は最低評価の1点。"""
    at = _ATTACK.get(attack_id)
    if at is None:
        return 0
    base = at.damage
    if base <= 0:
        return 1  # 可変ダメージ技: 火力不明だが「撃てる技」として最低限の価値
    dd = _CARD.get(defender.id)
    ad = _CARD.get(attacker.id)
    dmg = base
    if dd is not None and ad is not None:
        if dd.weakness is not None and dd.weakness == ad.energyType:
            dmg *= 2
        elif dd.resistance is not None and dd.resistance == ad.energyType:
            dmg -= 30
    return max(0, dmg)


def _threat_score(pk: Pokemon) -> float:
    """相手ポケモンの脅威度(高いほど優先的に倒したい)。"""
    d = _CARD.get(pk.id)
    score = _prize_value(pk) * 100
    score += pk.hp * 0.5
    score += len(pk.energies) * 20
    if d is not None:
        if d.stage2:
            score += 40
        elif d.stage1:
            score += 20
        if d.skills:  # 特性持ちは厄介
            score += 30
    return score


# ---------------------------------------------------------------- 選択肢スコアリング
def _score_option(o, obs: Observation, me, op) -> float:
    """1つの選択肢に汎用ルールで点数を付ける。高いほど選ばれやすい。"""
    t = o.type

    # --- 攻撃: 最重要。倒せる/大ダメージ/弱点を優先 ---
    if t == OptionType.ATTACK:
        active = me.active[0] if me.active else None
        target = op.active[0] if op.active else None
        if active is None or target is None:
            return 500.0
        dmg = _attack_damage(o.attackId, active, target)
        s = 1000.0 + dmg * 2
        if dmg >= target.hp:           # 気絶させられる
            s += 2000 + _prize_value(target) * 500
        return s

    # --- 進化: 盤面を強くする。基本的に前向き ---
    if t == OptionType.EVOLVE:
        return 800.0

    # --- 特性: 使えるなら使う(ドロー/加速など有用なことが多い) ---
    if t == OptionType.ABILITY:
        return 700.0

    # --- ポケモンを場に出す/エネ加速サポート等のプレイ ---
    if t == OptionType.PLAY:
        card = _hand_card(obs, o.index, me)
        d = _CARD.get(card.id) if card else None
        if d is not None and d.cardType == 5:  # ポケモン(cardType 5 is POKEMON per sample)
            return 600.0                        # たね展開は積極的に
        return 400.0                            # トレーナーズ

    # --- エネルギー付け: アタッカーに寄せる ---
    if t == OptionType.ATTACH:
        # 手札からのエネルギー添付。バトル場優先。
        if o.inPlayArea == AreaType.ACTIVE:
            return 350.0
        return 300.0

    # --- リトリート: 不利なら下がる。基本は消極的 ---
    if t == OptionType.RETREAT:
        return 50.0

    # --- ターン終了: 他に良い手がなければ ---
    if t == OptionType.END:
        return 10.0

    # --- カード選択(サーチ対象・手札に加える等): 汎用的に価値付け ---
    if t == OptionType.CARD:
        card = _get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 100.0
        d = _CARD.get(card.id)
        s = 100.0
        if d is not None:
            # exや進化先など価値の高いカードをやや優先
            if d.ex or d.megaEx:
                s += 30
            if d.basic and d.cardType == 5:  # たねポケモンはサーチで欲しい
                s += 20
        return s

    # --- Yes/No/数値など: 無難なデフォルト ---
    if t == OptionType.YES:
        return 60.0
    if t == OptionType.NO:
        return 40.0
    if t == OptionType.NUMBER:
        return float(o.number or 0)

    return 20.0


# ---------------------------------------------------------------- obsアクセスヘルパ
def _hand_card(obs: Observation, index: int, me):
    if me.hand is None or index is None or index >= len(me.hand):
        return None
    return me.hand[index]


def _get_card(obs: Observation, area, index, player_index):
    if area is None or index is None:
        return None
    state = obs.current
    ps = state.players[player_index] if player_index is not None else None
    try:
        if area == AreaType.HAND and ps and ps.hand:
            return ps.hand[index]
        if area == AreaType.ACTIVE and ps and ps.active:
            return ps.active[index]
        if area == AreaType.BENCH and ps:
            return ps.bench[index]
        if area == AreaType.DISCARD and ps:
            return ps.discard[index]
        if area == AreaType.DECK and obs.select and obs.select.deck:
            return obs.select.deck[index]
        if area == AreaType.STADIUM:
            return state.stadium[index]
    except (IndexError, TypeError, AttributeError):
        return None
    return None


# ---------------------------------------------------------------- メイン
def agent(obs_dict: dict) -> list[int]:
    # 初回: デッキ返却
    if obs_dict.get("select") is None:
        return read_deck_csv()

    try:
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]

        scores = [_score_option(o, obs, me, op) for o in select.option]

        # 降順に並べ、必要数だけ選ぶ(重複なし)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = max(lo, 1)
        k = min(k, hi, len(order))
        return order[:k]
    except Exception:
        # フォールバック: 最小限の合法手
        select = obs_dict["select"]
        n = len(select["option"])
        lo = select.get("minCount") or 1
        return list(range(min(max(lo, 1), n)))