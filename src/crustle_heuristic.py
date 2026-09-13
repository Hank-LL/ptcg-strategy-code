"""イワパレス専用ヒューリスティック。

設計は alakazam_heuristic.py と同じ「generic_heuristic のスコアを土台に、
デッキ固有の判断を加算レイヤーで重ねる」形。

## このデッキの正体: 壁で殴り勝つデッキ

イワパレス(345)の特性「しんぴのいしやど」=
**相手の「ポケモン【ex】」からワザのダメージを受けない**。
上位アーキタイプの大半がex主体なので、そこに対しては一方的に殴れる。

耐久を積み上げる手段:
  HP150 + グロウ【草】エネルギー(+20) + ヒーローマント(+100) = 最大270
  ジャンボアイスで80回復、スパイクエネルギーで殴り返し(ダメカン2個)
  ミストエネルギーで相手のワザの効果を無効化

## エネルギーの割り当てが最重要

デッキのエネルギー16枚は**すべて特殊エネルギー**(基本エネルギー0枚)。

- **グロウ【草】(18) ×4** … グレートシザーのコストは [草,無,無]。
  草を供給できるのは事実上これだけなので、**必ずイワパレスに付ける**。
  さらに草ポケモンの最大HPを+20する。
- **プリズム(16) ×4** … 「たねポケモンについているなら全タイプ扱い」。
  イワパレスは1進化なので無扱いにしかならないが、**たねのマシマシラに付けると
  【悪】エネルギー扱いになり、特性アドレナブレインが起動する**。
- **ミスト(11) / スパイク(14) ×4ずつ** … イワパレスの2個目以降の枠に。

## 天敵

弱点は【炎】(weakness=2)。**炎タイプの非exポケモン**だけが実質的な脅威で、
プール内ではメガスターミーデッキのエースバーン(50→弱点2倍で100)。
イワパレスHP150を2発で落とす。実測でもメガスターミー戦だけ勝率が落ちる。

## 実測(汎用ヒューリスティックで操縦した場合の相性)

vs サンプル92% / ワナイダー85% / ドラパルト82% / フーディン82% / メガガルーラ82%
vs ブリジュラス70% / オーロンゲ65% / メガルカリオ60% / ガブリアス55% / メガスターミー50%
合計 72.5%(400試合)
"""

import generic_heuristic as gh

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)

# ---------------------------------------------------------------- カードID
DWEBBLE = 344       # イシズマイ  HP70 たね 逃げ2
MUNKIDORI = 112     # マシマシラ  HP110 たね 逃げ1
CRUSTLE = 345       # イワパレス  HP150 1進化 逃げ3

POFFIN = 1086        # なかよしポフィン(HP70以下のたね2枚をベンチへ)
BOSS_ORDERS = 1182   # ボスの指令
POKEGEAR = 1122      # ポケギア3.0
LILLIE = 1227        # リーリエの決心
ROCKET_LAMBDA = 1219  # ロケット団のラムダ(トレーナーズをサーチ)
CRUSH_HAMMER = 1120  # クラッシュハンマー
JUMBO_ICE = 1147     # ジャンボアイス(エネ3個以上のバトル場を80回復)
HILDA = 1225         # トウコ
POKE_PAD = 1152      # ポケパッド
SACRED_CHARM = 1177  # せいなるおまもり(特性持ちからのダメージ-30)
XEROSIC = 1197       # クセロシキのたくらみ
HERO_CLOAK = 1159    # ヒーローマント(最大HP+100)

MIST_ENERGY = 11     # ミスト  (相手のワザの効果を受けない)
SPIKE_ENERGY = 14    # スパイク(殴られたら相手にダメカン2個)
PRISM_ENERGY = 16    # プリズム(たねなら全タイプ扱い)
GLOW_GRASS = 18      # グロウ【草】(草1個ぶん / 最大HP+20)

# ワザID
ATK_ASCENSION = 478       # イシズマイ「かくせい」 [無] 山札から進化先を持ってきて進化
ATK_SUPERB_SCISSORS = 479  # イワパレス「グレートシザー」 [草,無,無] 120
ATK_MIND_BEND = 141        # マシマシラ「サイコトリップ」 [超,無] 60 + こんらん

FIRE = 2                  # イワパレスの弱点タイプ
TOOLS = {SACRED_CHARM, HERO_CLOAK}

# ---------------------------------------------------------------- 設定(A/B用)
USE_GENERIC_BASE = True      # 汎用ヒューリスティックを土台に敷く
USE_ENERGY_ROUTING = True    # エネルギーの付け先をカード効果に合わせて振り分ける
# バトル場が攻撃可なら、殴る前にベンチの次アタッカーへエネを付ける案。
# 「攻撃できるターンの4割でエネ付けを捨てている」実測から試したが、
# **発動条件を絞りすぎてほぼ発動しなかった**(ベンチ付け率 24%→25%, 勝率83%→83%)。
# 条件 p.crustle_ready は「エネ3個以上+草付きのイワパレス」を要求するが、
# 取りこぼしの47%は「草はあるがまだ3個未満のイワパレス」で条件を満たさない。
# 最初に「逆効果(-5.5pp)」と報告したのはノイズだった(挙動が変わらないのに
# 勝率がそんなに動くはずがない)。既定オフ。広げれば発動するが、壁デッキで
# 2体目にエネを割く価値があるかは別途要検証。
USE_BENCH_PRELOAD = False
USE_ASCENSION_RUSH = True    # 序盤は「かくせい」で最速進化を狙う
USE_FIRE_AWARENESS = True    # 炎タイプ(弱点)の相手を警戒する
USE_SUSTAIN = True           # ジャンボアイス / どうぐ / アドレナブレイン

# ---------------------------------------------------------------- ターン内状態
_turn = -1
_used_adrena = False


def _update_turn_state(state):
    global _turn, _used_adrena
    if state.turn != _turn:
        _turn = state.turn
        _used_adrena = False


def reset_state():
    global _turn, _used_adrena
    _turn = -1
    _used_adrena = False


# ---------------------------------------------------------------- 盤面の把握
class Plan:
    __slots__ = ("active", "active_id", "active_energy", "active_hp",
                 "active_maxhp", "field_counts", "hand_counts", "bench_free",
                 "crustle_ready", "crustle_in_play", "op_active", "op_fire",
                 "op_has_fire", "op_all", "boss_target", "damaged")

    def __init__(self):
        self.active = None
        self.active_id = -1
        self.active_energy = 0
        self.active_hp = 0
        self.active_maxhp = 0
        self.crustle_ready = False
        self.crustle_in_play = 0
        self.op_active = None
        self.op_fire = False
        self.op_has_fire = False
        self.boss_target = -1
        self.damaged = 0


def _counts(cards):
    d = {}
    for c in cards or []:
        if c is not None:
            d[c.id] = d.get(c.id, 0) + 1
    return d


def _is_fire(pk) -> bool:
    d = gh._CARD.get(pk.id) if pk else None
    return bool(d) and d.energyType == FIRE


def _has_glow(pk) -> bool:
    return any(e.id == GLOW_GRASS for e in (pk.energyCards or [])) if pk else False


def _build_plan(obs: Observation, state, me, op) -> Plan:
    p = Plan()
    p.field_counts = _counts([c for c in (me.active or []) if c]
                             + [c for c in (me.bench or []) if c])
    p.hand_counts = _counts(me.hand)
    p.bench_free = (me.benchMax or 5) - len(me.bench or [])

    p.active = me.active[0] if me.active else None
    if p.active is not None:
        p.active_id = p.active.id
        p.active_energy = len(p.active.energies or [])
        p.active_hp = p.active.hp
        p.active_maxhp = p.active.maxHp
        p.damaged = max(0, p.active.maxHp - p.active.hp)
    p.crustle_in_play = p.field_counts.get(CRUSTLE, 0)
    # グレートシザーは [草,無,無]。草を供給できるのは実質グロウ草エネだけ。
    p.crustle_ready = (p.active_id == CRUSTLE and p.active_energy >= 3
                       and _has_glow(p.active))

    p.op_all = [c for c in (op.active or []) if c] + \
               [c for c in (op.bench or []) if c]
    p.op_active = op.active[0] if op.active else None
    p.op_fire = _is_fire(p.op_active)
    p.op_has_fire = any(_is_fire(c) for c in p.op_all)

    # ボスの指令で引っぱりたい相手: 炎(弱点)を優先的に処理し、
    # いなければサイドを多く取れる相手。
    best = (-1, -1.0)
    for i, b in enumerate(op.bench or []):
        if b is None:
            continue
        d = gh._CARD.get(b.id)
        score = 0.0
        if _is_fire(b):
            score += 100.0          # 天敵は場に出す前に潰す
        if d is not None:
            score += (3 if d.megaEx else 2 if d.ex else 1) * 10
            score -= b.hp / 50.0    # 倒しやすい方
        if score > best[1]:
            best = (i + 1, score)
    p.boss_target = best[0]
    return p


# ---------------------------------------------------------------- スコアリング
def _bonus(o, obs: Observation, state, me, op, p: Plan) -> float:
    t = o.type

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        aid = o.attackId
        if aid == ATK_SUPERB_SCISSORS:
            return 4000.0                     # 主砲。撃てるなら撃つ
        if aid == ATK_ASCENSION:
            # 「かくせい」は山札からイワパレスを持ってきて即進化する展開札。
            # 序盤はこれが最優先(打点0だが、盤面が一気に完成する)。
            if USE_ASCENSION_RUSH and p.crustle_in_play == 0:
                return 3500.0
            return -1000.0
        if aid == ATK_MIND_BEND:
            # マシマシラ60 + こんらん。イワパレスが立っていないときの繋ぎ、
            # および炎の相手にイワパレスを晒したくないとき。
            if p.crustle_in_play == 0 or (USE_FIRE_AWARENESS and p.op_fire):
                return 1500.0
            return 200.0
        return 0.0

    # ---- 特性(アドレナブレイン: 自分のダメカン3個を相手に移す) ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None and card.id == MUNKIDORI:
            if not USE_SUSTAIN:
                return 0.0
            if _used_adrena:
                return -2000.0
            # 自分が傷んでいるほど価値が高い
            return 1800.0 if p.damaged >= 30 else 400.0
        return 0.0

    # ---- 進化 ----
    if t == OptionType.EVOLVE:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None and card.id == CRUSTLE:
            return 3200.0
        return 1200.0

    # ---- エネルギー付け ----
    if t == OptionType.ATTACH:
        # 付けるエネルギーは手札にある。ATTACHの選択肢は playerIndex=None なので
        # _get_card では取得できず、必ず me.hand から取る。
        # (以前ここを _get_card に頼っていて全エネが判別できず、草の優先付けが
        #  効いていなかった。ユーザーがラダーで「草があるのに他を付ける」を観測)
        card = gh._hand_card(obs, o.index, me) if o.area == AreaType.HAND else None
        cid = card.id if card else None
        if not USE_ENERGY_ROUTING:
            return 600.0 if o.inPlayArea == AreaType.ACTIVE else 200.0

        dest = None
        try:
            if o.inPlayArea == AreaType.ACTIVE and me.active:
                dest = me.active[o.inPlayIndex or 0]
            elif o.inPlayArea == AreaType.BENCH and me.bench:
                dest = me.bench[o.inPlayIndex or 0]
        except (IndexError, TypeError):
            dest = None
        dest_id = dest.id if dest else -1
        dest_energy = len(dest.energies or []) if dest else 0
        is_bench = o.inPlayArea == AreaType.BENCH

        # ベンチ先付け(preload): バトル場が既に攻撃できる状態(p.crustle_ready)で、
        # このターンまだエネを付けていないなら、攻撃(4000)より先にベンチの
        # 次アタッカーへ付ける。エネ付けはターンを終えないので完全にタダで得。
        # (実測で、攻撃できるターンの多くでベンチに付けずに殴り、エネ付けを
        #  捨てていた。攻撃できるターンの取りこぼしが4割あった)
        preload = (USE_BENCH_PRELOAD and is_bench and not state.energyAttached
                   and p.crustle_ready)

        # グロウ草エネはイワパレス系の草コスト供給源。4枚しかないので他に回さない。
        # グレートシザーは [草,無,無] で、草を払えるのはこれだけ。草が付いていない
        # イワパレス/イシズマイには最優先で付ける(進化前でも進化後に引き継がれる)。
        if cid == GLOW_GRASS:
            if dest_id == CRUSTLE:
                if not _has_glow(dest):
                    return 4600.0 if preload else 2600.0
                return 250.0
            if dest_id == DWEBBLE:
                if not _has_glow(dest):
                    return 4500.0 if preload else 2400.0
                return 250.0
            return -1500.0
        # プリズムはたねに付けてこそ全タイプ扱い。マシマシラの悪エネ役。
        if cid == PRISM_ENERGY:
            if dest_id == MUNKIDORI:
                return 2000.0 if dest_energy == 0 else 200.0
            if dest_id == DWEBBLE:
                return 800.0
            return 100.0
        # ミスト/スパイクはイワパレスの2個目以降に(草を優先させるため低め)。
        # ベンチ先付け対象なら攻撃より優先(草の次に)。
        if cid in (MIST_ENERGY, SPIKE_ENERGY):
            if is_bench and preload and dest_id in (CRUSTLE, DWEBBLE):
                return 4200.0
            if dest_id == CRUSTLE:
                return 1500.0
            if dest_id == DWEBBLE:
                return 700.0
            return 100.0
        return 300.0

    # ---- 手札からのプレイ ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None

        if cid in TOOLS:
            if not USE_SUSTAIN:
                return 300.0
            # どうぐはイワパレスに載せて壁を厚くする
            return 1700.0 if p.crustle_in_play else 200.0
        if cid == JUMBO_ICE:
            # エネ3個以上のバトル場を80回復。傷んでいないと無駄。
            if USE_SUSTAIN and p.active_energy >= 3 and p.damaged >= 80:
                return 2200.0
            return -1500.0
        if cid == BOSS_ORDERS:
            if USE_FIRE_AWARENESS and p.boss_target > 0:
                return 1900.0
            return 400.0
        if cid == POFFIN:
            # HP70以下のたね = イシズマイのみ。展開の要。
            if p.bench_free >= 2 and p.field_counts.get(DWEBBLE, 0) < 2:
                return 2100.0
            return 300.0
        if cid == HILDA:
            return 1500.0       # 進化ポケモン+エネをサーチ(イワパレス+グロウ草)
        if cid == ROCKET_LAMBDA:
            return 1300.0
        if cid == POKE_PAD:
            return 1200.0       # ルール持ち以外 = イシズマイ/マシマシラ
        if cid == POKEGEAR:
            return 1000.0
        if cid == LILLIE:
            # 手札を全部戻して6枚(サイド6なら8枚)引く。手札が少ないときだけ。
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1600.0 if hand <= 3 else -800.0
        if cid == CRUSH_HAMMER:
            return 700.0
        if cid == XEROSIC:
            return 500.0
        if cid in (DWEBBLE, MUNKIDORI):
            return 1400.0
        return 0.0

    # ---- 逃げる ----
    if t == OptionType.RETREAT:
        # イワパレスの逃げエネは3と重い。炎の相手に晒されているときだけ。
        if USE_FIRE_AWARENESS and p.op_fire and p.active_id == CRUSTLE:
            return 800.0
        if p.active_id == CRUSTLE:
            return -1200.0
        return 100.0

    return 0.0


def _placement_bonus(o, obs, state, me, p: Plan) -> float:
    """SETUP / SWITCH / TO_ACTIVE 系: 誰をバトル場に置くか。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    # 炎の相手が前にいるならイワパレスを出さない(弱点2倍で2発)
    if card.id == CRUSTLE:
        if USE_FIRE_AWARENESS and p.op_fire:
            return -500.0
        return 1500.0
    if card.id == MUNKIDORI:
        return 900.0 if (USE_FIRE_AWARENESS and p.op_fire) else 400.0
    if card.id == DWEBBLE:
        return 300.0
    return 0.0


# ---------------------------------------------------------------- エージェント
def agent(obs_dict: dict) -> list[int]:
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
            if ctx in placement:
                extra = _placement_bonus(o, obs, state, me, plan)
            else:
                extra = _bonus(o, obs, state, me, op, plan)
            scores.append(base + extra)

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                c = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if c is not None and c.id == MUNKIDORI:
                    global _used_adrena
                    _used_adrena = True

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
