"""マリィのオーロンゲex 専用ヒューリスティック。

設計は alakazam_heuristic.py / crustle_heuristic.py と同じで、
generic_heuristic のスコアを土台に、デッキ固有の判断を加算レイヤーで重ねる。

## このデッキの正体: 2進化への最速到達 + エネルギー爆発

マリィのオーロンゲex(648) HP320 / 2進化 / 弱点【草】/ 逃げ2。

  特性 **パンクアップ**:
    自分の番に、このカードを**手札から出して進化させたとき**、1回使える。
    自分の山札から**基本【悪】エネルギーを5枚まで**選び、
    自分の「マリィのポケモン」に好きなようにつける。
  ワザ **シャドーバレット [悪,悪] 180**:
    相手のベンチポケモン1匹にも30ダメージ(ベンチは弱点・抵抗力を計算しない)。

デッキの基本【悪】エネルギーは10枚。**その半分を進化1回で場に出せる**のが核。
理想は「ベロバーをベンチに置く → ふしぎなアメでオーロンゲexに飛ばす →
パンクアップで悪エネを撒く → 180+30 を毎ターン」。
ふしぎなアメも「手札から進化させる」のでパンクアップが乗る。

## 噛み合っている補助

- **スパイクタウンジム(1259)** … 場に出ている限り、毎ターン1回
  山札から「マリィのポケモン」をサーチできる常設エンジン。切らさない。
- **ヒカリ(1231)** … たね/1進化/2進化を1枚ずつ = ベロバー/ギモー/オーロンゲex 一式。
- **マシマシラ(112)** … 特性アドレナブレインで自分のダメカン3個を相手に移す。
  シャドーバレットのベンチ30と合わせて打点調整ができる。
  ただし**マリィのポケモンではない**のでパンクアップの対象外。悪エネは手張りする。
- **ヒーローマント(1159)** … オーロンゲexが HP420 になる。
- **スボミー(235)** … 「むずむずかふん」で次の相手の番グッズをロック。

## 弱点

弱点は【草】(weakness=1)。加えてオーロンゲexは**ex**なので、
イワパレスの特性「相手のポケモン【ex】からワザのダメージを受けない」で完封される。
実測でも対イワパレスは18%(汎用操縦)と最悪。

## 実測(汎用ヒューリスティック操縦での相性、各40試合)

ドラパルト90% / ブリジュラス88% / フーディン85% / サンプル82% / ワナイダー82%
メガルカリオ52% / ガブリアス50% / メガスターミー50% / メガガルーラ42% / イワパレス18%
合計 64.0%
"""

import generic_heuristic as gh

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)

# ---------------------------------------------------------------- カードID
GRIMMSNARL_EX = 648   # マリィのオーロンゲex HP320 2進化
MORGREM = 647         # マリィのギモー      HP100 1進化
IMPIDIMP = 646        # マリィのベロバー    HP70  たね
DUDUNSPARCE = 66      # ノココッチ          HP140 1進化(にげあしドロー)
DUNSPARCE = 305       # ノコッチ            HP70  たね
MUNKIDORI = 112       # マシマシラ          HP110 たね(アドレナブレイン)
YVELTAL = 689         # イベルタル          HP110 たね
FEZANDIPITI = 140     # キチキギスex        HP210 たね
BUDEW = 235           # スボミー            HP30  たね(グッズロック)

DARK_ENERGY = 7       # 基本【悪】エネルギー ×10

POFFIN = 1086         # なかよしポフィン(HP70以下のたね2枚)
RARE_CANDY = 1079     # ふしぎなアメ
POKE_PAD = 1152       # ポケパッド
LILLIE = 1227         # リーリエの決心
SPIKEMUTH_GYM = 1259  # スパイクタウンジム(毎ターン マリィのポケモンをサーチ)
DAWN = 1231           # ヒカリ
BOSS_ORDERS = 1182    # ボスの指令
XEROSIC = 1197        # クセロシキのたくらみ
TOOL_SCRAPPER = 1137  # ツールスクラッパー
HERO_CLOAK = 1159     # ヒーローマント(最大HP+100)
DANGEROUS_RUINS = 1260  # 危ない廃墟(悪以外のたねをベンチに出すとダメカン2個)

# ワザID
ATK_SHADOW_BULLET = 937    # オーロンゲex [悪,悪] 180 + ベンチ30
ATK_FILCH = 934            # ベロバー [無] 山札を1枚引く
ATK_CORKSCREW_IMP = 935    # ベロバー [悪] 10
ATK_CORKSCREW_MOR = 936    # ギモー   [悪,悪] 60
ATK_LAND_CRUSH = 76        # ノココッチ [無,無,無] 90
ATK_TRADING_PLACES = 423   # ノコッチ [無] 自分をベンチと入れ替え
ATK_RAM = 424              # ノコッチ [無,無] 20
ATK_MIND_BEND = 141        # マシマシラ [超,無] 60 + こんらん
ATK_CLUTCH = 997           # イベルタル [悪] 20 + にげられない
ATK_DARK_FEATHER = 998     # イベルタル [悪,悪,無] 110
ATK_CRUEL_ARROW = 183      # キチキギスex [無,無,無] 相手1匹に100
ATK_ITCHY_POLLEN = 323     # スボミー [なし] 10 + 次の相手の番グッズロック

MARNIE_LINE = {IMPIDIMP, MORGREM, GRIMMSNARL_EX}   # パンクアップの対象
GRASS = 1                  # オーロンゲexの弱点タイプ

# ---------------------------------------------------------------- 設定(A/B用)
USE_GENERIC_BASE = True     # 汎用ヒューリスティックを土台に敷く
USE_EVOLVE_RUSH = True      # ベロバー→(アメ)→オーロンゲex を最優先で通す
USE_ENERGY_ROUTING = True   # 悪エネの付け先を用途で振り分ける
USE_ADRENA = True           # マシマシラのアドレナブレインでダメカンを移す
USE_STADIUM_CARE = True     # スパイクタウンジムを維持する
USE_GRASS_AWARENESS = True  # 草(弱点)の相手を警戒する

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
    __slots__ = ("active", "active_id", "field_counts", "hand_counts",
                 "bench_free", "gx_in_play", "gx_ready", "damaged",
                 "op_active", "op_grass", "op_has_grass", "boss_target",
                 "stadium_ours", "can_candy")

    def __init__(self):
        self.active = None
        self.active_id = -1
        self.gx_in_play = 0
        self.gx_ready = False
        self.damaged = 0
        self.op_active = None
        self.op_grass = False
        self.op_has_grass = False
        self.boss_target = -1
        self.stadium_ours = False
        self.can_candy = False


def _counts(cards):
    d = {}
    for c in cards or []:
        if c is not None:
            d[c.id] = d.get(c.id, 0) + 1
    return d


def _is_grass(pk) -> bool:
    d = gh._CARD.get(pk.id) if pk else None
    return bool(d) and d.energyType == GRASS


def _dark_count(pk) -> int:
    """悪エネルギーとして機能している個数。"""
    if pk is None:
        return 0
    return sum(1 for e in (pk.energies or []) if e == DARK_ENERGY)


def _build_plan(obs: Observation, state, me, op) -> Plan:
    p = Plan()
    field = [c for c in (me.active or []) if c] + [c for c in (me.bench or []) if c]
    p.field_counts = _counts(field)
    p.hand_counts = _counts(me.hand)
    p.bench_free = (me.benchMax or 5) - len(me.bench or [])

    p.active = me.active[0] if me.active else None
    if p.active is not None:
        p.active_id = p.active.id
        p.damaged = max(0, p.active.maxHp - p.active.hp)
    p.gx_in_play = p.field_counts.get(GRIMMSNARL_EX, 0)
    # シャドーバレットは [悪,悪]
    p.gx_ready = (p.active_id == GRIMMSNARL_EX
                  and len(p.active.energies or []) >= 2)

    # ふしぎなアメを撃てる形か(手札にアメ + オーロンゲex、場にベロバー)
    p.can_candy = bool(p.hand_counts.get(RARE_CANDY)
                       and p.hand_counts.get(GRIMMSNARL_EX)
                       and p.field_counts.get(IMPIDIMP))

    op_all = [c for c in (op.active or []) if c] + [c for c in (op.bench or []) if c]
    p.op_active = op.active[0] if op.active else None
    p.op_grass = _is_grass(p.op_active)
    p.op_has_grass = any(_is_grass(c) for c in op_all)

    # スタジアムが自分のスパイクタウンジムか
    try:
        p.stadium_ours = bool(state.stadium) and state.stadium[0].id == SPIKEMUTH_GYM
    except (IndexError, AttributeError, TypeError):
        p.stadium_ours = False

    # ボスの指令の対象: 草(弱点)を最優先、次にサイドを多く取れて倒しやすい相手
    best = (-1, -1e9)
    for i, b in enumerate(op.bench or []):
        if b is None:
            continue
        d = gh._CARD.get(b.id)
        sc = 0.0
        if _is_grass(b):
            sc += 100.0
        if d is not None:
            sc += (3 if d.megaEx else 2 if d.ex else 1) * 20
        if b.hp <= 180:
            sc += 50.0          # シャドーバレットで倒しきれる
        sc -= b.hp / 40.0
        if sc > best[1]:
            best = (i + 1, sc)
    p.boss_target = best[0]
    return p


# ---------------------------------------------------------------- スコアリング
def _bonus(o, obs: Observation, state, me, op, p: Plan) -> float:
    t = o.type
    hc = p.hand_counts

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        aid = o.attackId
        if aid == ATK_SHADOW_BULLET:
            return 4000.0                 # 主砲 180 + ベンチ30
        if aid == ATK_CRUEL_ARROW:
            return 1800.0                 # 相手1匹に100(ベンチも狙える)
        if aid == ATK_DARK_FEATHER:
            return 1500.0                 # イベルタル110
        if aid == ATK_LAND_CRUSH:
            return 1200.0                 # ノココッチ90
        if aid == ATK_ITCHY_POLLEN:
            # グッズロック。オーロンゲexが立つ前の時間稼ぎとして価値がある。
            return 900.0 if p.gx_in_play == 0 else -1500.0
        if aid == ATK_CORKSCREW_MOR:
            return 700.0                  # ギモー60
        if aid == ATK_MIND_BEND:
            return 600.0                  # マシマシラ60 + こんらん
        if aid == ATK_FILCH:
            # ベロバーの「くすねる」は打点0だが1枚引ける。他に何もないときだけ。
            return 300.0 if p.gx_in_play == 0 else -2000.0
        if aid in (ATK_CORKSCREW_IMP, ATK_RAM, ATK_CLUTCH, ATK_TRADING_PLACES):
            return -1500.0                # 打点が低すぎる
        return 0.0

    # ---- 特性 ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        cid = card.id if card else None
        if cid == GRIMMSNARL_EX:
            return 5000.0                 # パンクアップ。最優先で必ず使う
        if cid == MUNKIDORI:
            if not USE_ADRENA or _used_adrena:
                return -2000.0
            # 自分が傷んでいるほど価値が高い。相手を削る手段にもなる。
            return 1900.0 if p.damaged >= 30 else 500.0
        if cid == DUDUNSPARCE:
            # にげあしドロー: 3枚引くが自身は山札に戻る
            return 1400.0
        if cid == FEZANDIPITI:
            return 1300.0
        return 0.0

    # ---- 進化 ----
    if t == OptionType.EVOLVE:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        cid = card.id if card else None
        if cid == GRIMMSNARL_EX:
            return 4500.0                 # 進化そのものがパンクアップの起動条件
        if cid == MORGREM:
            # ギモー経由は遅い。アメでオーロンゲexに飛べるなら、そちらを優先。
            if USE_EVOLVE_RUSH and p.can_candy:
                return -500.0
            return 1500.0
        if cid == DUDUNSPARCE:
            return 1300.0
        return 800.0

    # ---- エネルギー付け ----
    if t == OptionType.ATTACH:
        if not USE_ENERGY_ROUTING:
            return 500.0 if o.inPlayArea == AreaType.ACTIVE else 200.0
        dest = None
        try:
            if o.inPlayArea == AreaType.ACTIVE and me.active:
                dest = me.active[o.inPlayIndex or 0]
            elif o.inPlayArea == AreaType.BENCH and me.bench:
                dest = me.bench[o.inPlayIndex or 0]
        except (IndexError, TypeError):
            dest = None
        dest_id = dest.id if dest else -1
        n = len(dest.energies or []) if dest else 0

        # オーロンゲexは2個で撃てる。3個目以降は無駄。
        if dest_id == GRIMMSNARL_EX:
            return 2200.0 if n < 2 else 200.0
        # マシマシラはパンクアップの対象外なので、悪エネを手張りして
        # アドレナブレインを起動する。
        if dest_id == MUNKIDORI:
            return 1600.0 if n == 0 else 100.0
        if dest_id in (IMPIDIMP, MORGREM):
            return 900.0        # 進化後に引き継げる
        if dest_id == YVELTAL:
            return 500.0
        return 200.0

    # ---- 手札からのプレイ ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None

        if cid == RARE_CANDY:
            # ベロバー → オーロンゲex。このデッキの核。
            if USE_EVOLVE_RUSH and p.can_candy:
                return 3800.0
            return -1000.0
        if cid == GRIMMSNARL_EX:
            return 2500.0
        if cid == SPIKEMUTH_GYM:
            # 毎ターン マリィのポケモンをサーチできる常設エンジン。
            # 既に自分のジムが出ているなら張り替えない。
            if USE_STADIUM_CARE and p.stadium_ours:
                return -2000.0
            return 2000.0
        if cid == DAWN:
            return 2100.0       # たね/1進化/2進化を1枚ずつ = ライン一式
        if cid == POFFIN:
            # HP70以下のたね = ベロバー/ノコッチ/スボミー
            if p.bench_free >= 2 and p.field_counts.get(IMPIDIMP, 0) < 2:
                return 2000.0
            return 300.0
        if cid == POKE_PAD:
            return 1300.0       # ルール持ち以外 = ベロバー/ギモー/マシマシラ等
        if cid == HERO_CLOAK:
            return 1700.0 if p.gx_in_play else 200.0
        if cid == BOSS_ORDERS:
            return 1900.0 if p.boss_target > 0 else 300.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1600.0 if hand <= 3 else -900.0
        if cid == DANGEROUS_RUINS:
            # 悪以外のたねをベンチに出すとダメカン2個。こちらは悪主体なので
            # 相手の方が損をしやすいが、ノコッチ/マシマシラ/スボミーには当たる。
            if USE_STADIUM_CARE and p.stadium_ours:
                return -1500.0      # 自分のジムを潰さない
            return 400.0
        if cid == TOOL_SCRAPPER:
            return 600.0
        if cid == XEROSIC:
            return 500.0
        if cid == BUDEW:
            return 900.0 if p.gx_in_play == 0 else -800.0
        if cid == IMPIDIMP:
            return 1800.0       # 進化元。常に確保しておきたい
        if cid in (MUNKIDORI, DUNSPARCE, YVELTAL, FEZANDIPITI):
            return 1000.0
        return 0.0

    # ---- 選択(サーチ先・ボスの対象など) ----
    if t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        # 相手の場から選ぶ(ボスの指令の対象、シャドーバレットのベンチ30 など)
        if o.playerIndex is not None and o.playerIndex != state.yourIndex:
            if p.boss_target > 0 and o.index == p.boss_target - 1:
                return 1500.0
            return 0.0
        # 自分側: 進化ラインとエネルギーを優先して手札に加える
        if card.id == GRIMMSNARL_EX:
            return 1200.0
        if card.id == RARE_CANDY:
            return 1100.0
        if card.id == IMPIDIMP:
            return 1000.0
        if card.id == DARK_ENERGY:
            return 800.0
        if card.id == MORGREM:
            return 600.0
        return 0.0

    # ---- 逃げる ----
    if t == OptionType.RETREAT:
        if USE_GRASS_AWARENESS and p.op_grass and p.active_id == GRIMMSNARL_EX:
            return 700.0        # 草(弱点2倍)の前に立たせない
        if p.active_id == GRIMMSNARL_EX:
            return -1000.0
        return 100.0

    return 0.0


def _placement_bonus(o, obs, state, me, p: Plan) -> float:
    """誰をバトル場に置くか。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == GRIMMSNARL_EX:
        if USE_GRASS_AWARENESS and p.op_grass:
            return -400.0
        return 1600.0
    if card.id == IMPIDIMP:
        return 800.0            # 前で進化させる
    if card.id == MUNKIDORI:
        return 500.0
    if card.id == BUDEW:
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
