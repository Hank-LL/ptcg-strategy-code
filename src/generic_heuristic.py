"""汎用ルールベース エージェント (デッキ非依存) — 可変ダメージ対応版

設計方針:
- カード固有のハードコードは避け、all_card_data()/all_attack() の構造化データ
  (HP, 弱点, 進化前, コスト, ダメージ, ex/mega, 特性有無)を中心に意思決定する。
- 可変ダメージ技(damage=0)については、効果テキストから事前抽出した
  「ベース値 × 盤面から数える量」のパターン(_VARIABLE_DMG)を使い、
  現在の盤面から実ダメージを概算する。ワナイダーのロケットラッシュ
  (30×自分の場のロケット団数)のような技を正しく評価できる。
- パターン外・確率技(コイン)は期待値や安全側の概算にフォールバックする。

用途:
- RL 環境での「非MAIN選択の委譲先」および「相手役」
- 単体でも提出可能な、そこそこ強いベースライン

公開関数:
- agent(obs_dict) -> list[int]     : メインのエージェント関数
- read_deck_csv() -> list[int]     : deck.csv を読む(提出時のデッキ返却用)
"""

import os

from cg.api import (
    AreaType, EnergyType, OptionType, SelectContext,
    Observation, Pokemon, Card,
    all_card_data, all_attack, to_observation_class,
)

# ---------------------------------------------------------------- マスタ
_CARD = {c.cardId: c for c in all_card_data()}
_ATTACK = {a.attackId: a for a in all_attack()}

# CardData.cardType の実測値: 0=ポケモン(1056枚), 1=グッズ, 2=どうぐ,
# 3=サポート, 4=スタジアム, 5=基本エネルギー(8枚), 6=特殊エネルギー。
# 以前ここを 5 と書いていたため「ポケモンなら優先」の判定が基本エネルギー
# 8枚にしか一致せず、ベンチ展開の優先付けが機能していなかった。
# A/B比較のため定数にしてある(5 に戻せば旧挙動を再現できる)。
CARDTYPE_POKEMON = 0

# ポケモンを手札から出すときのスコア。述語が壊れていた間はここが一度も効かず、
# 全ての PLAY が 400 で並んでいた(= 400 は旧挙動と完全に同一)。
#
# 2026-07-22の実測(述語修正版 vs 旧挙動、11デッキ×30試合=330試合):
#   300 → 43.0% / 400 → 47.3% / 500 → 49.1% / 600 → 50.9%
# 400 は定義上 50% になるはずが 47.3% で、これが測定ノイズの大きさを示す。
# 別途660試合で測った 600 相当は 46.2%。合算 473/990 = 47.8%(SE 1.6pp)。
# つまり**どの値も旧挙動と区別できない**。述語だけ正しく直し、挙動は
# 変えない 400 に据え置く。上げるなら5pp以上の差を確認してから。
PLAY_POKEMON_SCORE = 400.0

# 可変ダメージ技テーブル: card_id -> [[base, pattern, coin_n], ...]
# 効果テキストから事前抽出(EN_Card_Data.csv)。pattern は盤面から数える量の種別。
_VARIABLE_DMG = {24: [[30, 'coin', 4]], 35: [[20, 'other_foreach', 0]], 51: [[90, 'coin', 2]], 53: [[10, 'coin', 2]], 62: [[30, 'own_pokemon', 0]], 63: [[70, 'discard_choice', 0]], 69: [[30, 'coin', 3]], 84: [[120, 'discard_choice', 0]], 93: [[20, 'own_bench', 0]], 94: [[70, 'discard_choice', 0]], 98: [[30, 'opp_hand', 0]], 99: [[20, 'self_damage', 0]], 110: [[90, 'coin', 2]], 118: [[50, 'discard_choice', 0]], 128: [[20, 'other_foreach', 0]], 136: [[20, 'coin', 2]], 137: [[60, 'opp_ex', 0]], 141: [[60, 'opp_prize_taken', 0]], 147: [[100, 'other_foreach', 0]], 154: [[40, 'own_energy_self', 0]], 172: [[10, 'coin', 3]], 176: [[30, 'own_bench', 0]], 212: [[20, 'opp_energy', 0]], 236: [[60, 'opp_energy', 0]], 237: [[10, 'coin', 3]], 242: [[10, 'self_damage', 0]], 254: [[60, 'coin', 4]], 258: [[30, 'other_foreach', 0]], 294: [[10, 'coin', 2]], 296: [[120, 'coin', 3]], 303: [[20, 'self_damage', 0]], 306: [[60, 'opp_ex', 0]], 350: [[10, 'coin', 2]], 356: [[70, 'discard_choice', 0]], 363: [[70, 'other_foreach', 0]], 376: [[30, 'other_foreach', 0]], 382: [[40, 'coin', 2]], 387: [[10, 'other_foreach', 0]], 396: [[30, 'other_foreach', 0]], 401: [[30, 'own_rocket', 0]], 411: [[40, 'coin', 2]], 413: [[30, 'other_foreach', 0]], 417: [[30, 'own_energy_self', 0]], 420: [[30, 'other_foreach', 0]], 430: [[80, 'coin', 1]], 460: [[100, 'other_foreach', 0]], 462: [[40, 'other_foreach', 0]], 465: [[80, 'coin', 4]], 470: [[20, 'coin', 3]], 472: [[90, 'coin', 2]], 474: [[20, 'other_foreach', 0]], 475: [[20, 'other_foreach', 0]], 500: [[20, 'own_pokemon', 0]], 501: [[40, 'own_pokemon', 0]], 502: [[70, 'own_pokemon', 0]], 503: [[30, 'other_foreach', 0]], 507: [[50, 'coin', 2]], 513: [[100, 'coin', 4]], 524: [[80, 'coin', 2]], 532: [[10, 'self_damage', 0]], 555: [[20, 'coin', 2]], 561: [[50, 'other_foreach', 0]], 575: [[30, 'own_energy_self', 0]], 582: [[90, 'coin', 2]], 587: [[50, 'discard_choice', 0]], 601: [[20, 'other_foreach', 0]], 611: [[60, 'coin', 1]], 615: [[30, 'other_foreach', 0]], 617: [[40, 'coin', 2]], 695: [[80, 'other_foreach', 0]], 702: [[30, 'coin', 5]], 721: [[20, 'other_foreach', 0]], 723: [[100, 'other_foreach', 0]], 727: [[30, 'coin', 2]], 739: [[10, 'coin', 2]], 747: [[50, 'other_foreach', 0]], 748: [[20, 'other_foreach', 0]], 749: [[10, 'coin', 3]], 766: [[120, 'discard_choice', 0]], 769: [[20, 'own_pokemon', 0]], 786: [[10, 'coin', 3]], 790: [[90, 'discard_choice', 0]], 799: [[70, 'coin', 2]], 819: [[40, 'own_pokemon', 0]], 822: [[10, 'coin', 2]], 837: [[40, 'other_foreach', 0]], 841: [[20, 'coin', 2]], 842: [[40, 'own_pokemon', 0]], 852: [[80, 'other_foreach', 0]], 861: [[50, 'opp_hand', 0]], 871: [[70, 'coin', 1]], 877: [[30, 'other_foreach', 0]], 891: [[60, 'discard_choice', 0]], 894: [[70, 'other_foreach', 0]], 914: [[40, 'own_pokemon', 0]], 922: [[10, 'coin', 3]], 940: [[20, 'other_foreach', 0]], 964: [[20, 'own_pokemon', 0]], 970: [[30, 'own_energy_self', 0]], 978: [[20, 'own_pokemon', 0]], 997: [[80, 'coin', 1]], 1001: [[40, 'opp_energy', 0]], 1016: [[20, 'own_pokemon', 0]], 1034: [[90, 'coin', 1]], 1035: [[10, 'coin', 2]], 1037: [[70, 'other_foreach', 0]], 1041: [[60, 'discard_choice', 0]], 1053: [[20, 'self_damage', 0]], 1066: [[60, 'other_foreach', 0]], 1070: [[40, 'other_foreach', 0]]}

# card_id が持つ attackId のうち、可変技のインデックスを引くためのマップ。
# _CARD[cid].attacks は attackId のリスト。_VARIABLE_DMG[cid] は
# 「そのカードの可変技」を出現順に並べたもの。両者を突き合わせて、
# attackId -> (base, pattern, coin_n) を作る。
_ATK_VARIABLE = {}
for _cid, _vlist in _VARIABLE_DMG.items():
    _cd = _CARD.get(_cid)
    if _cd is None:
        continue
    # そのカードの技のうち damage<=0(=可変)のものに、順に割り当てる
    _var_attack_ids = [aid for aid in _cd.attacks
                       if (_ATTACK.get(aid) and _ATTACK[aid].damage <= 0)]
    for _aid, _v in zip(_var_attack_ids, _vlist):
        _ATK_VARIABLE[_aid] = _v


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


def _can_pay(cost_energies: list, have: list) -> bool:
    """技コスト(タイプ番号リスト)を、持っているエネルギーで払えるか。"""
    have_pool = list(have)
    colored = [e for e in cost_energies if e != EnergyType.COLORLESS]
    colorless = [e for e in cost_energies if e == EnergyType.COLORLESS]
    for need in colored:
        idx = next((i for i, e in enumerate(have_pool)
                    if e == need or e == EnergyType.RAINBOW), None)
        if idx is None:
            return False
        have_pool.pop(idx)
    return len(have_pool) >= len(colorless)


def _is_rocket(pk: Pokemon) -> bool:
    """ロケット団のポケモンか(名前で判定)。"""
    d = _CARD.get(pk.id)
    return bool(d and d.name and d.name.startswith("Team Rocket's"))


def _count_field_pokemon(ps) -> int:
    """場のポケモン数(バトル+ベンチ)。"""
    n = len(ps.active) if ps.active else 0
    n += len(ps.bench) if ps.bench else 0
    return n


def _variable_damage(base: int, pattern: str, coin_n: int,
                     attacker: Pokemon, me, op) -> int:
    """可変ダメージ技の推定ダメージを盤面から概算する。"""
    def field(ps):
        pk = []
        if ps.active:
            pk += list(ps.active)
        if ps.bench:
            pk += list(ps.bench)
        return pk

    if pattern == "own_rocket":
        # 自分の場のロケット団ポケモン数(ロケットラッシュ)
        n = sum(1 for pk in field(me) if _is_rocket(pk))
        return base * n
    if pattern == "own_pokemon":
        return base * _count_field_pokemon(me)
    if pattern == "own_bench":
        return base * (len(me.bench) if me.bench else 0)
    if pattern == "opp_hand":
        return base * (op.handCount or 0)
    if pattern == "own_hand":
        return base * (me.handCount or 0)
    if pattern == "own_energy_self":
        return base * (len(attacker.energies) if attacker.energies else 0)
    if pattern == "opp_energy":
        tgt = op.active[0] if op.active else None
        return base * (len(tgt.energies) if tgt and tgt.energies else 0)
    if pattern == "discard_choice":
        # 攻撃時に自分のエネを捨てて増やす系: 手元エネ(最大2〜3程度)で概算
        e = len(attacker.energies) if attacker.energies else 0
        return base * min(e, 3)
    if pattern == "self_damage":
        # 自分のダメカン数 = (maxHp - hp)/10
        dc = max(0, (attacker.maxHp - attacker.hp)) // 10
        return base * dc
    if pattern == "opp_ex":
        n = sum(1 for pk in field(op)
                if _CARD.get(pk.id) and (_CARD[pk.id].ex or _CARD[pk.id].megaEx))
        return base * n
    if pattern == "opp_prize_taken":
        # 相手が取ったサイド = 6 - 相手の残りサイド
        taken = 6 - (len(op.prize) if op.prize else 6)
        return base * taken
    if pattern == "coin":
        # コイン: 期待値(表の数 = coin_n / 2)
        return int(base * coin_n / 2)
    # other_foreach 等: 安全側に「ベース値1個分」で概算(最低評価よりは上)
    return base


def _attack_damage(attack_id: int, attacker: Pokemon, defender: Pokemon,
                   me=None, op=None) -> int:
    """弱点・抵抗を加味した推定ダメージ。可変技は盤面から概算する。"""
    at = _ATTACK.get(attack_id)
    if at is None:
        return 0
    base = at.damage
    if base <= 0:
        # 可変ダメージ技: テーブルがあれば盤面から概算
        v = _ATK_VARIABLE.get(attack_id)
        if v is not None and me is not None and op is not None:
            b, pat, cn = v
            dmg = _variable_damage(b, pat, cn, attacker, me, op)
        else:
            dmg = 1  # 不明な可変技は最低限の価値
    else:
        dmg = base
    # 弱点・抵抗(固定・可変とも適用)
    dd = _CARD.get(defender.id)
    ad = _CARD.get(attacker.id)
    if dd is not None and ad is not None and dmg > 0:
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
        if d.skills:
            score += 30
    return score


# ---------------------------------------------------------------- 選択肢スコアリング
def _score_option(o, obs: Observation, me, op) -> float:
    """1つの選択肢に汎用ルールで点数を付ける。高いほど選ばれやすい。"""
    t = o.type

    if t == OptionType.ATTACK:
        active = me.active[0] if me.active else None
        target = op.active[0] if op.active else None
        if active is None or target is None:
            return 500.0
        dmg = _attack_damage(o.attackId, active, target, me, op)
        s = 1000.0 + dmg * 2
        if dmg >= target.hp:
            s += 2000 + _prize_value(target) * 500
        return s

    if t == OptionType.EVOLVE:
        return 800.0

    if t == OptionType.ABILITY:
        return 700.0

    if t == OptionType.PLAY:
        card = _hand_card(obs, o.index, me)
        d = _CARD.get(card.id) if card else None
        if d is not None and d.cardType == CARDTYPE_POKEMON:
            return PLAY_POKEMON_SCORE
        return 400.0

    if t == OptionType.ATTACH:
        if o.inPlayArea == AreaType.ACTIVE:
            return 350.0
        return 300.0

    if t == OptionType.RETREAT:
        return 50.0

    if t == OptionType.END:
        return 10.0

    if t == OptionType.CARD:
        card = _get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 100.0
        d = _CARD.get(card.id)
        s = 100.0
        if d is not None:
            if d.ex or d.megaEx:
                s += 30
            if d.basic and d.cardType == CARDTYPE_POKEMON:
                s += 20
        return s

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
    if obs_dict.get("select") is None:
        return read_deck_csv()

    try:
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]

        scores = [_score_option(o, obs, me, op) for o in select.option]

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = max(lo, 1)
        k = min(k, hi, len(order))
        return order[:k]
    except Exception:
        select = obs_dict["select"]
        n = len(select["option"])
        lo = select.get("minCount") or 1
        return list(range(min(max(lo, 1), n)))