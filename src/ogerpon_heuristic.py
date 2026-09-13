#!/usr/bin/env python3
"""オーガポン みどりのめんex 単デッキ用ヒューリスティック。

上位プレイヤー **cabbage patch**(1049.4 / 42位) と **maco-macoo**(951.1 / 194位)
のリプレイ120件を解析して組んだ(2026-08-11)。

## デッキの中身
ポケモンは **オーガポン みどりのめんex(96) 4枚だけ**。残りは草エネ18枚+
グロウ草2枚と、エネを探す/引く札。

    オーガポン みどりのめんex  HP210 逃げ1 テラスタル
      特性 Teal Dance   自分の番に1回、手札から**基本【草】**を
                        **このポケモンに**つけ、つけたなら1枚引く
      ワザ Myriad Leaf Shower [草][草][草] 30
           **おたがいのバトルポケモンについているエネの数 x30** を追加

打点は「自分のエネ + 相手のエネ」で伸びる。実測では
**自分5.1〜5.4個 / 相手1.2〜1.3個 → 打点220前後**で殴っていた。

## リプレイから読み取った打ち回し(実測値)
- **撃てるなら100%撃つ**。エネ3〜7個のどの段階でも、攻撃可能な番の
  攻撃率は **100%**(418番中418番)。溜める判断は存在しない。
- **オーガポンは並べる**。ベンチ0体なら83%、1体なら80%、2体でも68%で追加する。
- **特性は全個体で使う**。対象は 前422回 / ベンチ705回 で、ベンチの方が多い。
  ベンチのオーガポンにもエネを溜めておき、前が倒れたら次を出す。
- **手貼りはバトル場**(前4.37回 / ベンチ0.33回 per game)。
- **にげるはほぼ使わない**(0.10回/試合)。

## クラッシュハンマーを入れない理由
maco-macoo は4枚入れているが cabbage patch は0枚。
Myriad Leaf Shower は**相手のエネも自分の打点になる**ので、剥がすと
自分の打点が下がる。勝率も cabbage 60%(18-12) / maco 52%(31-29) と
入れていない側が上。ここでは cabbage patch の構築を採る。
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, to_observation_class)
import generic_heuristic as gh

# ---- カード ----
OGERPON = 96            # オーガポン みどりのめんex (たね/テラスタル)
GRASS_ENERGY = 1        # 基本【草】 … 特性で付けられるのはこれだけ
GROW_ENERGY = 18        # グロウ【草】(特殊エネ・+20HP)。特性の対象外
BUG_CATCHING = 1094     # むしとりセット: 山上7枚から 草ポケ/基本草 を2枚
ENERGY_RECOVER = 1118   # エネルギー回収: トラッシュから基本エネ2枚
ENERGY_SEARCH = 1119    # エネルギー転送: 山から基本エネ1枚
POKEGEAR = 1122         # ポケギア3.0: 山上7枚からサポート1枚
TERA_ORB = 1127         # テラスタルオーブ: 山からテラスタル1枚(=オーガポン)
TOOL_SCRAPPER = 1137    # ツールスクラッパー: どうぐを2枚トラッシュ
JUMBO_ICE = 1147        # ジャンボアイス: エネ3個以上の前を80回復
HERO_CAPE = 1159        # ヒーローマント(どうぐ): +100HP
BOSS_ORDERS = 1182      # ボスの指令
BRIAR = 1201            # ブライア: 相手のサイドが**ちょうど2枚**のときだけ
JUDGE = 1213            # ジャッジマン: 両者 手札を山に戻して4枚
N_PLOT = 1221           # Nの筋書き: ベンチ→バトル場へエネを2個まで移す
CRUSH_HAMMER = 1120     # クラッシュハンマー: コイン表なら相手のエネを1個トラッシュ
CROWN = 1223            # クラウン: 両者 手札を山に戻し、コインで5枚/3枚(現構築は不採用)
ACEROLA = 1228          # アセロラのいたずら: 相手サイド2枚以下。自分の1体が
                        #   **相手exのワザ**のダメージと効果を1ターン受けない
LILLIE = 1227           # リーリエの決心: 手札を山に戻して6枚(サイド6なら8枚)
EXCITE_STADIUM = 1251   # エキサイトスタジアム: 場のたね全員 +30HP

ANY_ENERGY = (GRASS_ENERGY, GROW_ENERGY)
# フーディンの進化ライン(ケーシィ/ユンゲラー/フーディン)。
# パワフルハンドは「相手の手札の枚数x2個のダメカン」なので、
# **この相手にだけ**手札を削る意味がある。
FUUDIN_LINE = (741, 742, 743)

# ---- 方針のつまみ ----
USE_GENERIC_BASE = True
# 番が終わるスタジアム特性(ミアレシティ)を、ベンチが居るときは使わない
USE_SKIP_TURN_ENDING_ABILITY = True
PREP_MIN_SCORE = 1000.0     # これ以上の準備行動は攻撃より先に回す
USE_ACT_BEFORE_ATTACK = True

# 実測: 攻撃可能な番の攻撃率は100%。溜める判断は入れない
ATTACK_SCORE = 9000.0
# 特性(Teal Dance)。エネが増えて1枚引ける。無条件で最優先
ABILITY_SCORE = 8000.0
ATTACK_ENERGY_COST = 3   # Myriad Leaf Shower は【草】x3
# 前が撃てるようになるまで、ベンチのTeal Danceに弾を渡さない
USE_ACTIVE_ENERGY_FIRST = True
BENCH_ABILITY_WAIT = 2000.0   # 手貼り(4000)より下・PREP_MIN(1000)より上
# ベンチに並べるオーガポンの数(実測: ベンチ2体でも68%で追加する)
OGERPON_BENCH_WANT = 3
PLAY_OGERPON_SCORE = 4500.0
# 手貼りはバトル場優先(実測 前4.37 / ベンチ0.33)
ATTACH_ACTIVE_SCORE = 4000.0
ATTACH_BENCH_SCORE = 2500.0
# にげるはほぼ使わない(実測 0.10回/試合)
RETREAT_SCORE = -3000.0
# ベンチの育った個体に交代すれば倒せる場面だけは逃げる
USE_RETREAT_FOR_LETHAL = True
# ★攻撃(9000)より**上**にする必要がある(2026-08-12 修正)。
#   7000 にしていたので「倒せない攻撃」に負け、52回の該当場面で
#   実際に逃げたのは9回だけだった。RETREAT は
#   「攻撃より先に回す準備行動」の一覧(ABILITY/ATTACH/PLAY)にも入っていない。
#   逃げても番は終わらないので、交代してから殴れる。
RETREAT_LETHAL_SCORE = 9500.0
RETREAT_MIN_PRIZE = 2
# 前が撃てない番は、撃てるベンチと入れ替える(2026-08-13 ユーザー指摘)
USE_RETREAT_TO_ATTACKER = True
# ★手札からできること(手貼り4000・スタジアム3600・流す札2800〜)を全部やった
#   あとの最後の手段にする。エネを付け足して前が3個に届くならその方が得
#   (にげるは前のエネを捨てる)。END(10)には勝つ必要がある。
RETREAT_ATTACKER_SCORE = 500.0
# 逃げエネ0の駒は、倒しきれないなら引きずり出さない
USE_BOSS_SKIP_FREE_RETREAT = True
BOSS_FREE_RETREAT_BLOCK = -9000.0   # 取れるサイドがこれ未満なら逃げない
# 倒せる盤面を自分から壊す行動を止める(ボスの指令/エキサイトスタジアム)
USE_KEEP_LETHAL = True
LETHAL_BLOCK = -4000.0
# 手札を流す札(2800〜3200)より上に置く
STADIUM_PLAY_SCORE = 3600.0
HERO_CAPE_SCORE = 3500.0   # 流す札より上
HERO_CAPE_HP = 100.0       # ヒーローマントが増やすHP
EXCITE_HP_UP = 30.0     # エキサイトスタジアムがたねに与えるHP
# ★このデッキで「相手が張っていても流さない」のは**エキサイトスタジアムだけ**
#   (2026-08-11 ユーザー指摘)。キュワワー系の除外リストをそのまま持ち込んでいた。
#     エキサイトスタジアム … 相手が張ってもこちらのオーガポン(たね)が+30HP。得
#     ニュートラルセンター … **流すべき**。守るのは「ルールを持たない」ポケモンで、
#                          オーガポン みどりのめんex は **ex** なので守られない。
#                          むしろ**相手の非exにこちらの攻撃が通らなくなる**
#     めまいの谷         … こんらんを使わないので無関係
#     公民館            … 回復10。残す理由がない
STADIUM_KEEP = (EXCITE_STADIUM,)
# ボスで安いサイドを取りに行かず、目の前の高サイドを削り倒す
USE_CHIP_THE_ACE = True
CHIP_TURNS = 2          # 「あと何回の攻撃で倒せるか」の許容
# ジャッジマンを撃つ手札の上限。
# ★4 は古い標本(2026-08-11時点の maco 0.80回/試合)に合わせた値。
#   maco-macoo が71位(1020.6)に上がった現行版を取り直すと **1.57回/試合**で、
#   こちらは0.38回/試合しか撃っていなかった。6 にすると1.83回/試合になり、
#   対応比較で **+5.1pp ±1.6**(16反復×32試合)。
# ★リーリエの条件を絞る案は**測定で不利**だった(-1.1pp ±1.8、20反復×640試合)。
#   「手札に草を抱えているなら流さない」は理屈が通るが、このデッキは
#   むしろ手札を回し続ける方が強いらしい。旧条件(手札4枚以下で3000、
#   それ以外1400)のままにする。
ENERGY_FETCHERS = (BUG_CATCHING, ENERGY_SEARCH, ENERGY_RECOVER)
# 手札を山に戻す札。この前に「盤面へ変換できる札」を使い切る
HAND_SHUFFLERS = (LILLIE, JUDGE, CROWN)
USE_BOARD_FETCH_FIRST = True
# ブライアの前にも道具(テラスタルオーブ/むしとりセット)を使い切る案。
# ★実装して測ったが**採用しない**(2026-08-13)。
#   狙いどおり「むしとりセットを抱えたままブライア」は 3回→0回 になったが、
#   本命の指標「倒せるのにブライアを撃たなかった」は改善せず
#   (800試合: ON 15/76 撃ち逃し vs OFF 13/57)、
#   対応のあるA/B(200試合x6回)の勝率は **-1.17pp ± 1.61** で下向きだった。
#   理由は、ブライアを1手待たせるとその番の他の判断が後ろにずれるため。
#   ブライアは _lethal_now を満たしたときだけ撃つので、
#   道具を先に使っても打点の判定材料は増えない(手貼りとTeal Danceは
#   どちらも点数が上で、既にブライアより先に処理されている)。
USE_BRIAR_WAIT_FETCH = False
SHUFFLE_WAIT_SCORE = -1500.0   # 1手待たせる(次の判断で撃ち直す)
# ★「手札にエネが無く、エネを呼ぶ札も無いときだけ撃つ」を実装したが、
#   測定では不利だった(サイド6優先あり -0.6pp / 厳守 -1.6pp、20反復×640試合)。
#   無駄撃ちは 115回 -> 35回 と大きく減るのに勝率が伸びない。
#   このデッキは草を18枚積んでいるので、抱えた1〜2枚を惜しむより
#   手札を回し切る方が期待値が高いらしい。旧条件のままにする。
USE_LILLIE_GATE = True   # 2026-08-12 ユーザー指定でON
# ジャッジは相手にも4枚渡すので、相手の手札が細いときは撃たない。
# 単独では +0.2pp ±1.5(誤差内)だが、無駄撃ち116回が0になり理屈も通る
USE_JUDGE_GATE = True
LILLIE_MAX_HAND = 4
JUDGE_MIN_OP_HAND = 4         # 相手の手札がこれ未満なら撃たない
# 相手の手札を削る目的で撃つ線(対フーディン等)
USE_HAND_DISRUPTION = True
CROWN_MIN_OP_HAND = 5         # クラウンは相手を3〜5枚にする
JUDGE_DISRUPT_OP_HAND = 6     # ジャッジマンは両者4枚にする
OGERPON_COPIES = 4      # デッキのオーガポン枚数
ACEROLA_SCORE = 3400.0
# 勝ちきれないのに次の番で倒される場面は、延命でなく敗北の回避
USE_ACEROLA_URGENT = True
ACEROLA_URGENT_SCORE = 5000.0   # ブライア(3600)/ボスの指令(3600)より上
ACEROLA_MAX_PRIZE = 2           # カードの条件「相手のサイド2枚以下」
# 負けが確定している番の「捨て身のボスの指令」(2026-08-13 ユーザー指摘)
USE_DESPERATION_BOSS = True
DESPERATION_BOSS_SCORE = 3600.0
DESPERATION_TARGET_SCORE = 6000.0
DESPERATION_TURNS = 2   # 引き出した番 + 次の番で倒し切れること
# 対フーディンだけ、バトル場に積むエネの上限(2026-08-13 ユーザー指摘)
# ★リプレイ 92626073 で、バトル場を6個まで育てる一方ベンチは1個ずつのままで、
#   前が倒れた瞬間に**次が撃てなくなった**(T9〜T12でエネ1→3、その間ずっと無抵抗)。
#   フーディンの Powerful Hand は**こちらのHPと無関係に**手札枚数x20の
#   ダメカンを乗せるので、前を厚くしても延命にならない。積むより配る。
USE_FUUDIN_ENERGY_CAP = True
FUUDIN_ACTIVE_ENERGY_CAP = 5
FUUDIN_CAP_ATTACH_SCORE = 2400.0   # ベンチ手貼り(2500)より下・END(10)より上
CRUSH_HAMMER_SCORE = 3400.0
# 相手のベンチにエネが無いなら撃たない(前を剥がすと自分の打点が下がる)
# ★False。ベンチ限定にすると標的は100%ベンチになるが、勝率は -1.4pp ±1.8。
#   前を剥がす自傷(打点-30)より、相手の攻撃を遅らせる効果の方が大きいらしい。
#   使用回数も 1.46 -> 2.32回/試合 と本家(2.70)に近くなる。
USE_HAMMER_BENCH_ONLY = False
# ハンマーの標的: ベンチ優先(バトル場を剥がすと自分の打点が30下がる)
HAMMER_ABILITY_BONUS = 2500.0  # エネで起動する特性を止められる標的
HAMMER_STAGE_PENALTY = 1.5   # 進化が残っているほど標的価値を割り引く
HAMMER_PREFER_ACTIVE = False   # True=バトル場の主力を優先
HAMMER_BENCH_SCORE = 3000.0
HAMMER_ACTIVE_SCORE = -800.0
# 倒しきれる番は、前を剥がす理由がすべて消える
USE_HAMMER_SKIP_WHEN_LETHAL = True
HAMMER_LETHAL_BLOCK = -3000.0
# ★「剥がすと相手が撃てなくなる」例外は**入れない方が強かった**(2026-08-12 実測)。
#   ハンマーはコイン表でしか成功しない(50%)のに、こちらの打点30減は確実。
#   さらに相手は次の番に貼り直せる。期待値でベンチ側が勝つ。
#     ハンマー不使用      81.2%±1.4
#     ベンチ厳守         85.3%±1.2  (+4.0pp ±2.1)  ← 採用
#     攻撃阻止を許す      81.9%±1.3  (+0.7pp ±2.1)
HAMMER_DENY_ATTACK = -900.0
# ボスの標的で「相手のエース(とその進化前)」を優先する重み
ACE_WEIGHT = 8.0
ACE_DAMAGE_CAP = 300.0

# 手札の基本草がこれを下回ったら、エネを探す札の優先度を上げる
ENERGY_THIN = 2
# ジャンボアイスを使う最低ダメージ(回復量80)
USE_HEAL_TO_SURVIVE = True
JUMBO_HEAL = 80.0       # ジャンボアイスの回復量
JUMBO_MIN_ENERGY = 3    # カードの条件(エネ3個以上)
HEAL_MIN_DAMAGE = 160   # 上の判定に当てはまらないときの保険
HEAL_MIN_ENERGY = 5     # 本家の中央値は6
# Nの筋書きを使う「前のエネが足りない」線
N_PLOT_MAX_ACTIVE = 3   # 旧条件用(USE_N_PLOT_FOR_LETHAL=False のときだけ効く)
USE_N_PLOT_FOR_LETHAL = True
N_PLOT_MAX_MOVE = 2     # このカードで移せるエネの上限
N_PLOT_SCORE = 3400.0
N_PLOT_TAKE_SCORE = 2000.0   # 取る元の基準点(エネが多いほど下がる)

ATK_MYRIAD = None


def _resolve_attacks():
    global ATK_MYRIAD
    if ATK_MYRIAD is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Myriad Leaf Shower":
            ATK_MYRIAD = a.attackId


_seen_fuudin = False


def reset_state():
    """1試合ごとに呼ぶ。"""
    global _seen_fuudin
    _seen_fuudin = False


class Plan:
    __slots__ = ("active", "active_id", "active_energy", "active_damage",
                 "op_active", "op_active_energy", "op_active_ex", "bench", "bench_free",
                 "bench_ogerpon", "hand_counts", "hand", "deck", "op_deck", "op_hand",
                 "grass_in_hand", "op_prize", "my_prize", "bench_energy",
                 "stadium_id", "tool_on_active", "op_is_fuudin", "op_bench")

    def __init__(self):
        self.active = None
        self.active_id = None
        self.active_energy = 0
        self.active_damage = 0
        self.op_active = None
        self.op_active_energy = 0
        self.op_active_ex = False
        self.bench = []
        self.bench_free = 0
        self.bench_ogerpon = 0
        self.hand_counts = {}
        self.hand = 0
        self.deck = 0
        self.op_deck = 0
        self.op_hand = 0
        self.grass_in_hand = 0
        self.op_prize = 6
        self.my_prize = 6
        self.bench_energy = 0
        self.stadium_id = None
        self.tool_on_active = False
        self.op_is_fuudin = False
        self.op_bench = []


def _energy_units(c):
    if c is None:
        return []
    return list(getattr(c, "energies", None) or getattr(c, "energyCards", None) or [])


def _counts(cards):
    out = collections.Counter()
    for c in (cards or []):
        if c is not None:
            out[c.id] += 1
    return out


def _damage_on(c):
    """そのポケモンが受けているダメージ。"""
    if c is None:
        return 0
    try:
        return max(0, (c.maxHp or 0) - (c.hp or 0))
    except (AttributeError, TypeError):
        return 0


def _build_plan(obs, state, me, op):
    p = Plan()
    p.active = (me.active or [None])[0]
    p.active_id = p.active.id if p.active is not None else None
    p.active_energy = len(_energy_units(p.active))
    p.active_damage = _damage_on(p.active)
    p.op_active = (op.active or [None])[0]
    p.op_active_energy = len(_energy_units(p.op_active))
    _oc = gh._CARD.get(p.op_active.id) if p.op_active is not None else None
    p.op_active_ex = bool(_oc is not None
                          and (getattr(_oc, "ex", False)
                               or getattr(_oc, "megaEx", False)))
    p.bench = [x for x in (me.bench or []) if x is not None]
    try:
        p.op_bench = [x for x in (op.bench or []) if x is not None]
    except (AttributeError, TypeError):
        p.op_bench = []
    p.bench_free = (me.benchMax or 5) - len(p.bench)
    p.bench_ogerpon = len([x for x in p.bench if x.id == OGERPON])
    p.bench_energy = sum(len(_energy_units(x)) for x in p.bench)
    p.hand_counts = _counts(me.hand)
    p.hand = len(me.hand) if me.hand is not None else (me.handCount or 0)
    p.deck = me.deckCount or 0
    p.op_deck = op.deckCount or 0
    p.op_hand = (len(op.hand) if op.hand is not None else (op.handCount or 0))
    p.grass_in_hand = p.hand_counts.get(GRASS_ENERGY, 0)
    p.op_prize = len(op.prize) if op.prize is not None else 6
    p.my_prize = len(me.prize) if me.prize is not None else 6
    try:
        p.stadium_id = state.stadium[0].id if state.stadium else None
    except (AttributeError, IndexError, TypeError):
        p.stadium_id = None
    p.tool_on_active = bool(getattr(p.active, "tools", None))
    # ★相手がフーディンか。一度見たらその試合はずっと覚えておく
    global _seen_fuudin
    try:
        _fld = ([x for x in (op.active or []) if x]
                + [x for x in (op.bench or []) if x])
        if any(x.id in FUUDIN_LINE for x in _fld):
            _seen_fuudin = True
    except (AttributeError, TypeError):
        pass
    p.op_is_fuudin = _seen_fuudin
    return p


GRASS_TYPE = 1          # オーガポンのタイプ。弱点2倍/抵抗-30 の判定に使う
RESISTANCE_CUT = 30.0


def _damage_to(p, defender):
    """Myriad Leaf Shower で defender に通る打点(弱点・抵抗こみ)。

    ★このワザは表記30の**可変ダメージ**で、追加ぶんはテキストにしか書いていない。
      generic の `_attack_damage` は表記30しか見ないので、
      「倒せるかどうか」をこちら側で計算しないと判断できない。
    """
    if defender is None:
        return 0.0
    # ★特性持ちのワザを完全に防ぐ相手には、こちらの打点は**0**。
    #   オーガポン みどりのめんex は Teal Dance を持っているので必ず引っかかる。
    if _we_have_ability(p) and _blocks_ability_attackers(defender.id):
        return 0.0
    d = 30.0 + 30.0 * (p.active_energy + len(_energy_units(defender)))
    cd = gh._CARD.get(defender.id)
    if cd is not None:
        if cd.weakness is not None and cd.weakness == GRASS_TYPE:
            d *= 2.0                      # オーロンゲexは草弱点。**2倍**
        elif cd.resistance is not None and cd.resistance == GRASS_TYPE:
            d -= RESISTANCE_CUT
    return d


_EVO_FWD = None
_ATK_MAX = {}
_ATK_DMG = {}      # attackId -> ダメージ(_max_damage_with 用)
_ATK_COST_TYPES = None   # attackId -> コストのタイプ列


def _evo_forward():
    global _EVO_FWD
    if _EVO_FWD is None:
        m = collections.defaultdict(list)
        for c in gh._CARD.values():
            ef = getattr(c, "evolvesFrom", None)
            if ef:
                m[ef].append(c)
        _EVO_FWD = m
    return _EVO_FWD


def _card_max_damage(cid):
    """そのカードのワザの最大打点(可変技はベース値で概算)。"""
    v = _ATK_MAX.get(cid)
    if v is None:
        from cg.api import all_attack
        if not _ATK_MAX:
            for a in all_attack():
                _ATK_MAX[-a.attackId] = a.damage or 0
        c = gh._CARD.get(cid)
        best = 0
        for aid in ((c.attacks if c is not None else None) or []):
            d = _ATK_MAX.get(-aid, 0)
            vv = gh._ATK_VARIABLE.get(aid)
            if vv:
                d = max(d, vv[0] * 3)
            best = max(best, d)
        _ATK_MAX[cid] = v = best
    return v


def _final_max_damage(cid):
    """進化しきった姿での最大打点。進化前の脅威度を測るのに使う。"""
    c = gh._CARD.get(cid)
    if c is None:
        return 0
    fwd = _evo_forward()
    seen, stack, best = set(), [c], 0
    while stack:
        x = stack.pop()
        if x.cardId in seen:
            continue
        seen.add(x.cardId)
        nxt = fwd.get(x.name) or []
        if nxt:
            stack.extend(nxt)
        else:
            best = max(best, _card_max_damage(x.cardId))
    return best


_BLOCK_CACHE = {}


def _blocks_ability_attackers(cid):
    """その相手が「特性持ちのワザのダメージを受けない」特性を持つか。

    ★オーガポン いしずえのめんex(117) がこれ。こちらのオーガポン みどりのめんexは
      **Teal Dance という特性を持っている**ので、ワザのダメージが丸ごと0になる。
      ボスの指令でわざわざ引きずり出して殴っていた(2026-08-11 ユーザー指摘)。
      カード名ではなくテキストで判定するので、同じ効果の新カードにも効く。
    """
    v = _BLOCK_CACHE.get(cid)
    if v is None:
        c = gh._CARD.get(cid)
        v = False
        for sk in (getattr(c, "skills", None) or []):
            t = (getattr(sk, "text", "") or "").replace("\u2019", "'").lower()
            if "prevent all damage" in t and "have an ability" in t:
                v = True
        _BLOCK_CACHE[cid] = v
    return v


def _we_have_ability(p):
    cd = gh._CARD.get(p.active_id) if p.active_id is not None else None
    return bool(cd is not None and getattr(cd, "skills", None))


def _remaining_hp(c):
    try:
        return max(0, c.hp or 0)          # 観測の hp は**残りHP**
    except (AttributeError, TypeError):
        return 0


def _prize_value(c):
    """倒したときに取れるサイドの枚数。"""
    cd = gh._CARD.get(c.id) if c is not None else None
    if cd is None:
        return 1
    if getattr(cd, "megaEx", False):
        return 3
    return 2 if getattr(cd, "ex", False) else 1


def _damage_with(p, energy, defender):
    """自分のエネ数を差し替えて打点を計算する(交代後の見積り用)。"""
    if defender is None:
        return 0.0
    if _we_have_ability(p) and _blocks_ability_attackers(defender.id):
        return 0.0
    d = 30.0 + 30.0 * (energy + len(_energy_units(defender)))
    cd = gh._CARD.get(defender.id)
    if cd is not None:
        if cd.weakness is not None and cd.weakness == GRASS_TYPE:
            d *= 2.0
        elif cd.resistance is not None and cd.resistance == GRASS_TYPE:
            d -= RESISTANCE_CUT
    return d


def _board_fetch_in_hand(p, me):
    """手札に「その番のうちに盤面へ変換できる」サーチ札があるか。

    テラスタルオーブはテラスタル(=オーガポン)を手札に加えるだけだが、
    ベンチに空きがあればそのまま出せる。盤面に出れば手札を流しても残る。

    ★判定は「オーブを**実際に撃つ**条件」と完全に一致させること。
      ずれると、撃たないオーブを抱えたまま流す札だけが止まり続ける。
        ・ベンチが埋まっている         → 出せない
        ・山札にオーガポンが残っていない → オーブは -1500 で撃たない
        ・すでにオーガポンが足りている   → オーブは 600 (PREP_MIN未満) で撃たない
    """
    if not p.hand_counts.get(TERA_ORB):
        return False
    if p.bench_free <= 0:
        return False
    if _ogerpon_left(p, me) <= 0:
        return False
    have = p.hand_counts.get(OGERPON, 0) + p.bench_ogerpon
    return have < OGERPON_BENCH_WANT


def _grass_fetch_worth_it(p):
    """むしとりセットを、この番に**実際に撃つ**状況か。

    条件は BUG_CATCHING の 3400 側の分岐と同じにしてある(草が細いとき)。
    1800 側(草が足りている)は PREP_MIN_SCORE を超えるが優先度が低く、
    ここで待たせる価値がないので対象にしない。
    """
    if not p.hand_counts.get(BUG_CATCHING):
        return False
    return p.grass_in_hand < ENERGY_THIN + 1


def _energy_fetch_in_hand(p):
    """手札に「エネを持ってこられる札」があるか。

    むしとりセット(山上7枚から基本草)/エネルギー転送(山から基本エネ)/
    エネルギー回収(トラッシュから基本エネ2枚)。
    これらがあるなら、手札を丸ごと山に戻すより先にこちらを使う。
    """
    return any(p.hand_counts.get(x) for x in ENERGY_FETCHERS)


def _attachable_energy_in_hand(p):
    """手札に、この番まだ付けられるエネがあるか。

    基本草は特性(Teal Dance)でも手貼りでも付けられる。グロウ草は手貼りのみ。
    どちらも無ければ「その番のエネ付与は終わっている」とみなす。
    """
    return (p.hand_counts.get(GRASS_ENERGY, 0)
            + p.hand_counts.get(GROW_ENERGY, 0)) > 0


def _n_plot_makes_lethal(p):
    """Nの筋書きでベンチからエネを移せば、相手のバトル場を倒しきれるか。

    条件は3つ:
      ・その番の**エネ付与が終わっている**(手札に付けられるエネが無い)。
        まだ付けられるなら、先に付ける方が得(移す枚数を温存できる)
      ・**今のままでは倒せない**
      ・ベンチから1〜2個移せば**届く**
    打点は `30 + 30 x (自分 + 相手のバトル場のエネ)` なので、
    相手側のエネもそのまま数に入る。
    """
    o = p.op_active
    if o is None:
        return False
    if _attachable_energy_in_hand(p):
        return False
    hp = _remaining_hp(o)
    if hp <= 0 or _damage_to(p, o) >= hp:
        return False                      # 倒せないときに使う札
    movable = min(p.bench_energy, N_PLOT_MAX_MOVE)
    for k in range(1, int(movable) + 1):
        if _damage_with(p, p.active_energy + k, o) >= hp:
            return True
    return False


def _retreat_makes_lethal(p):
    """今は倒せないが、ベンチの個体に交代すれば倒せるか。

    ★このワザの打点は**バトル場のエネ数**で決まるので、ベンチで育った個体に
      入れ替えるだけで届くことがある(2026-08-11 ユーザー指摘)。
      実例(リプレイ 91996609 turn12): 前がエネ1で打点90、相手HP140。
      ベンチにエネ7の個体が居て打点270。交代すれば倒せた。
      逃げエネ1は**交代する側**から払うので、出てくる個体の打点は減らない。
    """
    o = p.op_active
    if o is None:
        return False
    hp = _remaining_hp(o)
    if hp <= 0 or _damage_to(p, o) >= hp:
        return False                    # 今のままで倒せるなら交代不要
    if _prize_value(o) < RETREAT_MIN_PRIZE and p.my_prize > _prize_value(o):
        # ★逃げると**エネを一番積んだ個体**が前に出る。倒されればサイド2枚。
        #   取れるのが1枚なら割に合わない(2026-08-12 実測で -3.3pp)。
        #   ただしそのKOで**サイドを取り切れる**ならこの理屈は成立しない。
        #   返しの番は来ないので、後で2枚取られる心配がない。
        return False
    for b in p.bench:
        if _damage_with(p, len(_energy_units(b)), o) >= hp:
            return True
    return False


def _retreat_enables_attack(p):
    """前が撃てない番に、交代すれば撃てるベンチが居るか。

    ★2026-08-13 ユーザー指摘・リプレイ 92586036 step133。
      ボスの指令でエネ0のオーガポンを引きずり出され、Nの筋書きで前に2個まで
      戻したところで番を終えていた(ワザは草3個)。ベンチにはエネ9の個体が
      居たので、逃げて交代すれば相手のバトル場(HP100)を倒してサイドを
      取り切れた。**撃てないまま番を終えるくらいなら交代して殴る**。
      逃げエネは**下がる側**から払うので、出てくる個体のエネは減らない。
    """
    if _can_attack_now(p):
        return False
    for b in p.bench:
        if len(_energy_units(b)) >= ATTACK_ENERGY_COST:
            return True
    return False


def _incoming_damage(p):
    """相手のバトル場がこちらに通せる最大打点(弱点・抵抗こみ)。"""
    o = p.op_active
    if o is None:
        return 0.0
    d = float(_card_max_damage(o.id))
    oc = gh._CARD.get(o.id)
    mc = gh._CARD.get(p.active_id) if p.active_id is not None else None
    if oc is not None and mc is not None and d > 0:
        if mc.weakness is not None and mc.weakness == oc.energyType:
            d *= 2.0
        elif mc.resistance is not None and mc.resistance == oc.energyType:
            d -= RESISTANCE_CUT
    return d


def _heal_saves_us(p):
    """ジャンボアイスで回復すると、相手の次の攻撃を耐えられるようになるか。

    カードの条件は「エネ3個以上のバトルポケモンを80回復」。
    回復量は受けているダメージが上限(HPは最大値を超えない)。
    """
    if p.active is None or p.active_energy < JUMBO_MIN_ENERGY:
        return False
    if p.active_damage <= 0:
        return False
    heal = min(JUMBO_HEAL, p.active_damage)
    hp = _remaining_hp(p.active)
    incoming = _incoming_damage(p)
    if incoming <= 0:
        return False
    return hp <= incoming < hp + heal


def _briar_closes_game(p):
    """ブライアを使えば、**その番でサイドを取り切って勝てる**か。

    ブライアは「この番、テラスタルのワザで相手のバトル場が【きぜつ】したなら、
    サイドを1枚多くとる」。KOで取れる枚数 +1 が、こちらの残りサイド以上なら
    その番で勝負が決まる。決まらないなら、相手のサイドは2枚しかないので
    次の番にこちらのex(サイド2枚)が倒されて負ける。
    """
    if not _lethal_now(p):
        return False
    return p.my_prize <= _prize_value(p.op_active) + 1


def _op_can_ko_us(p):
    """相手のバトル場のワザで、こちらのバトル場が倒されるか(弱点こみ)。"""
    if p.active is None:
        return False
    hp = _remaining_hp(p.active)
    return hp > 0 and _incoming_damage(p) >= hp


RAINBOW = 10            # どのタイプにもなるエネルギー


def _can_pay(cost, have):
    """コストのタイプ列 cost を、付いているエネ have で払えるか。

    ★**個数だけでは足りない**(2026-08-13 実測)。メガルカリオexの
      Mega Brave は【闘】x2。エネが3個あっても闘でなければ撃てない。
      個数だけで見ていたので「270打点で必ず倒される」と誤判定していた。
    """
    pool = list(have or [])
    colorless = 0
    for t in (cost or []):
        if t == 0:
            colorless += 1
            continue
        for i, e in enumerate(pool):
            if e == t or e == RAINBOW:
                pool.pop(i)
                break
        else:
            return False
    return len(pool) >= colorless


def _max_damage_with(cid, energies):
    """今ついているエネで**実際に撃てる**ワザの最大打点。"""
    global _ATK_COST_TYPES
    c = gh._CARD.get(cid)
    if c is None:
        return 0
    from cg.api import all_attack
    if not _ATK_DMG:
        for a in all_attack():
            _ATK_DMG[a.attackId] = a.damage or 0
    if _ATK_COST_TYPES is None:
        _ATK_COST_TYPES = {a.attackId: list(a.energies or [])
                           for a in all_attack()}
    best = 0
    for aid in (c.attacks or []):
        cost = _ATK_COST_TYPES.get(aid)
        if cost is not None and not _can_pay(cost, energies):
            continue
        d = _ATK_DMG.get(aid, 0)
        vv = gh._ATK_VARIABLE.get(aid)
        if vv:
            d = max(d, vv[0] * 3)
        best = max(best, d)
    return best


def _incoming_damage_soon(p):
    """相手が**今ついているエネで**通せる最大打点。

    ★`_incoming_damage` はエネを見ずにカードの最大打点を返すので、
      「負け確」の判定に使うと過大になる(実測: エネ3のメガルカリオexに
      270打点=【闘】x2 を見込んでいたが、エネの**タイプ**が合っていなかった)。
      賭けに出る判断はこちらで行う。手貼り1回ぶんは**見込まない**。
      確実に倒されるときだけ賭けに出る。
    """
    o = p.op_active
    if o is None:
        return 0.0
    d = float(_max_damage_with(o.id, _energy_units(o)))
    oc = gh._CARD.get(o.id)
    mc = gh._CARD.get(p.active_id) if p.active_id is not None else None
    if oc is not None and mc is not None and d > 0:
        if mc.weakness is not None and mc.weakness == oc.energyType:
            d *= 2.0
        elif mc.resistance is not None and mc.resistance == oc.energyType:
            d -= RESISTANCE_CUT
    return d


def _retreat_cost(cid):
    cd = gh._CARD.get(cid)
    try:
        return (cd.retreatCost or 0) if cd is not None else 0
    except (AttributeError, TypeError):
        return 0


def _has_survival_out(p):
    """「次の番に倒される」を覆す手が手札か盤面にあるか。

    ★これを見ないと、耐える札を持ったまま賭けに出てしまう
      (2026-08-13 実測: 発動15試合で ON 5勝 / OFF 11勝。
       ジャンボアイス・ヒーローマント・元気なベンチを無視していた)。
    """
    if _heal_saves_us(p):
        return True
    if p.active is None:
        return False
    inc = _incoming_damage_soon(p)
    if inc <= 0:
        return True
    if (p.hand_counts.get(HERO_CAPE) and not p.tool_on_active
            and _remaining_hp(p.active) + HERO_CAPE_HP > inc):
        return True
    if p.active_energy >= _retreat_cost(p.active_id):
        for b in p.bench:
            if _remaining_hp(b) > inc:
                return True                # 逃げれば耐える駒が居る
    return False


def _can_attack_now(p):
    """この番、実際にワザを撃てるか。Myriad Leaf Shower は【草】3個。"""
    return p.active_energy >= ATTACK_ENERGY_COST


def _bench_ability_steals_energy(p, o):
    """ベンチの Teal Dance が、前が撃つのに要る草を奪ってしまうか。"""
    if o.area != AreaType.BENCH:
        return False
    if _can_attack_now(p):
        return False                      # 前は足りている。ベンチに回してよい
    need = ATTACK_ENERGY_COST - p.active_energy
    return p.hand_counts.get(GRASS_ENERGY, 0) <= need


def _cap_active_energy(p):
    """対フーディンで、これ以上バトル場にエネを積まない番か。

    ★2026-08-13 ユーザー指摘・リプレイ 92626073。
      このワザの打点は**バトル場のエネ数**で伸びるので、放っておくと
      前1体に全部乗る。相手がフーディンのときは前がまとめて落ちるため、
      交代した個体が3個に届かず何番も殴れなくなる。
      ただし**あと1個で倒し切れる**ならその方が得なので、そこは例外。
    """
    if not (USE_FUUDIN_ENERGY_CAP and p.op_is_fuudin):
        return False
    if p.active_energy < FUUDIN_ACTIVE_ENERGY_CAP:
        return False
    o = p.op_active
    if o is not None:
        hp = _remaining_hp(o)
        if hp > 0 and _damage_to(p, o) < hp <= _damage_with(p, p.active_energy + 1, o):
            return False
    return True


def _lethal_now(p):
    """今のバトル場を、このターンそのまま倒せるか。"""
    if p.op_active is None or p.active_energy < 3:
        return False
    return _damage_to(p, p.op_active) >= _remaining_hp(p.op_active)


_END_TURN_CACHE = {}


def _ability_ends_turn(cid):
    """その特性/スタジアムを使うと**番が終わる**か。

    ★ミアレシティ(1267)がこれ。「山札からたねを1枚ベンチに出す。
      この方法で山札を見たなら、そのプレイヤーの番は終わる」。
      相手が張ったスタジアムでも起動できてしまうので、
      無条件に使うと**攻撃せずに番を終える**(2026-08-11 ユーザー指摘)。
      カード名ではなくテキストで判定する。
    """
    v = _END_TURN_CACHE.get(cid)
    if v is None:
        c = gh._CARD.get(cid)
        v = False
        for sk in (getattr(c, "skills", None) or []):
            t = (getattr(sk, "text", "") or "").replace("\u2019", "'").lower()
            if "turn ends" in t or "end your turn" in t:
                v = True
        _END_TURN_CACHE[cid] = v
    return v


# ---- スタジアムの起動型特性をどう扱うか(2026-08-11 ユーザー指定) ----
MYSTERY_GARDEN = 1263   # 手札のエネを捨てて引く。使わない
NIGHT_ACADEMY = 1248    # 手札1枚を山の上へ。**山札が相手より少ないときだけ**
COMMUNITY_CENTER = 1242 # サポートを使った番なら全員10回復。積極的に使う
STADIUM_NEVER = (MYSTERY_GARDEN,)
STADIUM_ALWAYS = (COMMUNITY_CENTER,)
STADIUM_BLOCK = -4000.0
STADIUM_USE = 1200.0


def _stadium_ability_score(o, p):
    """スタジアムの起動型特性の点数。None なら通常どおり扱う。

    相手が張った札でも起動できてしまうので、**中身を見て**決める必要がある。
    ミアレシティを毎ターン起動して攻撃を捨てていたのが発端(オーガポンで
    攻撃できる番の70%を失っていた)。
    """
    if not USE_SKIP_TURN_ENDING_ABILITY:
        return None
    if o.area != AreaType.STADIUM or p.stadium_id is None:
        return None
    sid = p.stadium_id
    if sid in STADIUM_NEVER:
        return STADIUM_BLOCK
    if _ability_ends_turn(sid):
        # ベンチが空なら「たねをベンチに出す」効果自体に価値がある
        return None if not p.bench else STADIUM_BLOCK
    if sid == NIGHT_ACADEMY:
        # 手札1枚を山に戻す = 自分の山が1枚増える。
        # 山札レースで負けているときだけ得
        return STADIUM_USE if p.deck < p.op_deck else STADIUM_BLOCK
    if sid in STADIUM_ALWAYS:
        return STADIUM_USE
    return None

def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type

    # ---- ワザ: 撃てるなら撃つ(実測 100%) ----
    if t == OptionType.ATTACK:
        return ATTACK_SCORE

    # ---- 特性 Teal Dance: 手札の基本草を自分につけて1枚引く ----
    if t == OptionType.ABILITY:
        _sc = _stadium_ability_score(o, p)
        if _sc is not None:
            return _sc
        # 実測では前(422回)よりベンチ(705回)で使う方が多い。
        # ベンチのオーガポンにも溜めておき、前が倒れたら次が即戦力になる。
        # ★ただし**前が撃てるようになるまでは、ベンチに弾を渡さない**
        #   (2026-08-13 ユーザー指摘・リプレイ33)。Teal Dance は手札の
        #   基本【草】を**自分に**つけるので、ベンチの個体が使うとエネはベンチに乗る。
        #   実例: 前エネ2・手札の草1枚の場面でベンチのTeal Danceが草を奪い、
        #   前は2のまま。Myriad Leaf Shower(草3)もジャンボアイス(エネ3)も
        #   撃てなくなって負けた。
        #   点数を手貼り(4000)より下に落とすだけでよい。手貼りが先に処理されて
        #   前が3個に届けば、次の判断でベンチのTeal Danceが通常どおり通る。
        if USE_ACTIVE_ENERGY_FIRST and _bench_ability_steals_energy(p, o):
            return BENCH_ABILITY_WAIT
        # ★対フーディンで前が上限に達したら、Teal Dance も**ベンチから**回す。
        #   点数を下げるだけなので、ベンチのオーガポンが居ない番は
        #   これまでどおり前が使う(引く1枚を捨てる必要はない)。
        if o.area == AreaType.ACTIVE and _cap_active_energy(p):
            return BENCH_ABILITY_WAIT
        return ABILITY_SCORE

    # ---- にげる: ほぼ使わない。ただし交代で倒せるようになるなら別 ----
    if t == OptionType.RETREAT:
        if USE_RETREAT_FOR_LETHAL and _retreat_makes_lethal(p):
            return RETREAT_LETHAL_SCORE
        if USE_RETREAT_TO_ATTACKER and _retreat_enables_attack(p):
            return RETREAT_ATTACKER_SCORE
        return RETREAT_SCORE

    # ---- エネ/どうぐを付ける ----
    if t == OptionType.ATTACH:
        card = gh._hand_card(obs, o.index, me) if o.area == AreaType.HAND else None
        cid = card.id if card else None
        if cid is None:
            return 0.0
        if cid == HERO_CAPE:
            # +100HP。殴られるバトル場に付ける。
            # ★これも「付ければポケモンに残る」札なので、手札を流す前に付ける
            return HERO_CAPE_SCORE if o.inPlayArea == AreaType.ACTIVE else -1000.0
        if cid in ANY_ENERGY:
            if o.inPlayArea == AreaType.ACTIVE:
                if _cap_active_energy(p):
                    return FUUDIN_CAP_ATTACH_SCORE
                return ATTACH_ACTIVE_SCORE
            return ATTACH_BENCH_SCORE
        return 100.0

    # ---- 場に出す / グッズ・サポート ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id

        if cid == OGERPON:
            # 実測: ベンチ0体83% / 1体80% / 2体68% で追加する
            if p.bench_free <= 0:
                return 100.0
            return (PLAY_OGERPON_SCORE if p.bench_ogerpon < OGERPON_BENCH_WANT
                    else 1500.0)

        # -- エネを供給する札(この構築の生命線) --
        if cid == ENERGY_SEARCH:
            return 3600.0 if p.grass_in_hand < ENERGY_THIN else 1200.0
        if cid == BUG_CATCHING:
            # 草ポケモンと基本草の両方を拾える。常に価値がある
            return 3400.0 if p.grass_in_hand < ENERGY_THIN + 1 else 1800.0
        if cid == ENERGY_RECOVER:
            return 3000.0 if p.grass_in_hand < ENERGY_THIN else 900.0
        if cid == TERA_ORB:
            # オーガポンを探す。手札と場に足りないときだけ。
            # ★山札に残っていないなら空振り(2026-08-11 ユーザー指摘)。
            #   場+手札+トラッシュで4枚見えていたら山には居ない。
            if _ogerpon_left(p, me) <= 0:
                return -1500.0
            have = p.hand_counts.get(OGERPON, 0) + p.bench_ogerpon
            return 3200.0 if have < OGERPON_BENCH_WANT else 600.0

        # -- 回復 / 耐久 --
        if cid == JUMBO_ICE:
            # ★maco-macoo の実測(44試合): 使ったときの被ダメ中央値 **180**、
            #   温存したとき 80。前のエネも 6 対 4。
            #   80回復なので、80しか食らっていない段階で切ると
            #   「削り直されて終わり」。**倒される寸前まで引きつける**のが
            #   本家の打ち回し。こちらは 80/エネ3 で撃っていた。
            # エネ3個以上の前を80回復。削られていないと無駄
            # ★本命は「**回復すれば相手の次の攻撃を耐えられる**」場面
            #   (2026-08-13 ユーザー指摘。リプレイ 92354260 turn11)。
            #   被ダメ70(HP140/210)でエネ3。固定閾値(被ダメ160/エネ5)では
            #   拾えなかったが、70回復してHP210になれば
            #   ドラパルトexの200を受けても10残って生き残れた。
            if USE_HEAL_TO_SURVIVE and _heal_saves_us(p):
                return 3800.0
            if (p.active_energy >= HEAL_MIN_ENERGY
                    and p.active_damage >= HEAL_MIN_DAMAGE):
                return 3800.0
            return -2000.0
        if cid == EXCITE_STADIUM:
            # ★相手の**たね**も+30されるので、倒せる盤面を壊すことがある。
            #   バトル場だけでなく、**ボスで引き出して倒す予定の駒**まで見る
            #   (2026-08-11 ユーザー指定)。オーロンゲのベロバー(70→100)や
            #   ギモー(100→130)が、+30で射程から外れる。
            if USE_KEEP_LETHAL and _breaks_any_lethal(p, op, EXCITE_HP_UP):
                return LETHAL_BLOCK
            # 場のたね全員 +30HP。相手のたねも上がるが、こちらは
            # **オーガポンしか居ない**ので取り分が大きい
            # ★相手が張っていても流さない札(ユーザー指定)。どれもこちらに
            #   利があるか害が無い。エキサイトは相手が張ってもこちらのたねが
            #   +30されるので、自分の札を切る必要がない。
            if p.stadium_id in STADIUM_KEEP:
                return -1500.0
            # ★手札を山に戻す札(ジャッジマン/リーリエ/クラウン)より**先に**張る
            #   (2026-08-13 ユーザー指摘)。張らずに流すと、相手のスタジアムを
            #   消す機会ごと捨てることになる。実測で 0.3回/試合 起きていた。
            #   特に夜の鉱山はテラスタルのワザのコストを+1するので放置できない。
            return STADIUM_PLAY_SCORE

        # -- 引く札 --
        # ★手札を山に戻す札の前に、**盤面へ変換できるサーチ札**を先に使う
        #   (2026-08-13 ユーザー指摘)。テラスタルオーブはオーガポンを手札に
        #   加えるだけだが、ベンチに空きがあればそのまま出せる。出してしまえば
        #   手札を流しても盤面に残るので、丸損にならない。
        #   実測: リーリエ314回中59回(18.8%)でオーブを抱えたまま流していた。
        #   うち7回は「ベンチが空だから撃つ」分岐で、オーブを使えばベンチを
        #   埋められた場面だった。
        #   むしとりセット/エネルギー転送/エネルギー回収は ENERGY_FETCHERS 側の
        #   ガード(_energy_fetch_in_hand)で既に止めている。
        #   ポケギア3.0は**ここに入れない**。持ってこられるのはサポートだけで、
        #   流す札を撃つ番はサポートをもう1枚使えないため、先に撃っても
        #   そのターン使えないまま山に戻る(=二重に損)。
        if (USE_BOARD_FETCH_FIRST and cid in HAND_SHUFFLERS
                and _board_fetch_in_hand(p, me)):
            return SHUFFLE_WAIT_SCORE

        if cid == LILLIE:
            # 手札を山に戻して6枚。**サイドちょうど6枚なら8枚**。
            # ★else を 1400 にしていたので PREP_MIN(1000) を超え、
            #   手札が厚くても撃っていた(手札5枚以上での使用が449回中217回)。
            #   手札の基本草は Teal Dance の弾なので、抱えたまま流すのは損。
            if not USE_LILLIE_GATE:
                return 3000.0 if p.hand <= 4 else 1400.0
            # ★条件は「手札にエネが無く、**エネを呼ぶ札も無い**とき」
            #   (2026-08-12 ユーザーが maco の挙動から指摘)。
            #   むしとりセット/エネルギー転送/エネルギー回収が手札にあるなら、
            #   そちらの方が安く弾を取れる。手札を丸ごと流す必要はない。
            # ★「サイド6なら無条件で撃つ」は外した(2026-08-12 ユーザー指摘)。
            #   8枚引けるのは確かだが、それ自体は撃つ理由にならない。
            #   撃つのは**手詰まりのとき**だけ:
            #     ・エネが無く、エネを呼ぶ札も無い(Teal Dance の弾切れ)
            #     ・ベンチが空(前が倒れたら負け)
            #     ・手札が細い
            # ★「エネが無い」は**グロウ草も含めて**判定する
            #   (2026-08-12 ユーザー指摘)。グロウ草は特性(Teal Dance)では
            #   付けられないが、**手貼りなら付けられる**。持っているのに
            #   山に流すのは損。`_attachable_energy_in_hand` が両方を見る。
            if (not _attachable_energy_in_hand(p)
                    and not _energy_fetch_in_hand(p)):
                return 3000.0
            if not p.bench:
                return 3200.0
            if p.hand <= LILLIE_MAX_HAND:
                return 2600.0
            return -1500.0
        if cid == JUDGE:
            # 両者4枚。**手札が細いときだけ**。
            # ★else を 1000 にしていたが、これは PREP_MIN_SCORE ちょうどで
            #   「攻撃より先に回す準備行動」として毎ターン繰り上がっていた。
            #   実測 1.58回/試合(本家0.80)、うち183/316回が手札6枚以上。
            #   手札の草エネは Teal Dance の弾なので、厚い手札を流すのは損。
            # ★相手にも4枚渡す。相手の手札が細いときに撃つのは
            #   **相手を助ける**だけ(相手1〜3枚での使用が430回中116回あった)。
            if USE_JUDGE_GATE and p.op_hand < JUDGE_MIN_OP_HAND:
                return -1500.0
            # ★相手の手札が厚いときは**妨害札**として撃つ(ユーザー指定)。
            #   ジャッジマンは両者4枚にするので、相手が6枚以上なら削れる。
            # ★妨害目的で撃つのは**フーディン相手のときだけ**
            #   (2026-08-13 ユーザー指摘。全デッキに効かせていたのは私の誤り)。
            if (USE_HAND_DISRUPTION and p.op_is_fuudin
                    and p.op_hand >= JUDGE_DISRUPT_OP_HAND):
                return 3000.0
            # ★maco の実測(51試合・使用112回)では、判断基準は**手札のエネ**だった。
            #     基本草0枚での使用 95/112 (85%)
            #     グロウ草0枚での使用 110/112 (98%)  ← 持っていたら温存する
            #     相手の手札は使用・温存とも全域に分散し、**条件ではない**
            #   手札枚数は4〜6枚が中心で、7枚以上での使用は9%しかない。
            # ★本方針: **手札にエネ(基本草・グロウ草とも)が無いときに掘る**。
            #   手札の枚数は条件にしない(maco の使用112回でも手札は4〜6枚が
            #   中心なだけで、7枚以上でも9%使っている)。
            # ★エネを呼ぶ札が手札にあるなら、そちらが先(リーリエと同じ扱い)
            if (not _attachable_energy_in_hand(p)
                    and not _energy_fetch_in_hand(p)):
                return 2800.0
            return -1500.0
        if cid == CROWN:
            # ★相手の手札を大きく削れるなら妨害札として使う
            #   (2026-08-12 ユーザー指定・対フーディン)。
            #   クラウンは相手を**3枚か5枚**にする。相手が5枚以上なら削れる。
            #   フーディンのパワフルハンドは「手札の枚数x2個のダメカン」なので、
            #   手札を削ることがそのまま打点を下げる。
            if (USE_HAND_DISRUPTION and p.op_is_fuudin
                    and p.op_hand >= CROWN_MIN_OP_HAND):
                return 3000.0
            return 2600.0 if p.hand <= 3 else 900.0
        if cid == POKEGEAR:
            return 2200.0

        # -- 限定的な札 --
        if cid == N_PLOT:
            # ★ベンチ→前へエネを2個まで移す札。使うのは
            #   **その番のエネ付与を終えたあと、あと1〜2個で届く**とき
            #   (2026-08-12 ユーザー指定)。
            #   旧条件は「前のエネ3個以下 かつ ベンチに2個以上」で、
            #   倒せるかどうかを一切見ていなかった。
            if USE_N_PLOT_FOR_LETHAL:
                return (N_PLOT_SCORE if _n_plot_makes_lethal(p)
                        else -2000.0)
            if (p.active_energy <= N_PLOT_MAX_ACTIVE
                    and p.bench_energy >= 2):
                return 3400.0
            return -2000.0
        if cid == ACEROLA:
            # ★守れるのは**相手のex**のワザだけ。相手のバトル場がexでなければ
            #   何も起きない(キュワワー版で「場のどこかにex」より
            #   「バトル場がex」の方が良いと実測済み)。
            if p.op_prize > 2:
                return -2000.0
            if not p.op_active_ex:
                return -2000.0
            # ★**勝ちきれないのに次の番で倒される**なら最優先(2026-08-13 ユーザー指摘)。
            #   アセロラが打てる=相手のサイドは2枚以下。こちらのオーガポンexは
            #   サイド2枚なので、倒された時点で相手はサイドを取り切って勝つ。
            #   つまりこの場面の「倒されない」は延命ではなく**敗北の回避**。
            #   ブライアで勝ちきれるならそちら(3600)が上。
            if (USE_ACEROLA_URGENT and not _briar_closes_game(p)
                    and _op_can_ko_us(p)):
                return ACEROLA_URGENT_SCORE
            return ACEROLA_SCORE

        if cid == BRIAR:
            # 相手のサイドが**ちょうど2枚**のときだけ使える詰めの札。
            # 「この番、自分のテラスタルのワザで相手のバトル場が倒れたら
            #  サイドを**もう1枚**取る」=  KOできて初めて意味がある。
            # ★倒せない番に撃つとサポート枠を捨てるだけ。実測で使用43回のうち
            #   **26回(60%)が倒せない場面**だった(2026-08-11 ユーザー指摘)。
            #   点数は特性(8000)/手貼り(4000)より下なので、
            #   エネを付け終わった後の状態で判定される。
            if p.op_prize != 2:
                return -2000.0
            # ★「倒せる」だけでは足りず「**その番で勝ちきれる**」かを見る
            #   (2026-08-13 ユーザー指摘)。相手のサイドは2枚なので、
            #   勝ちきれなければ次の番にこちらのexが倒されてそのまま負ける。
            #   例: 相手の前がex(サイド2枚)で倒せる場面でも、
            #       こちらの残りサイドが3枚なら 2+1=3 で取り切れて勝ち → ブライア
            #       こちらの残りサイドが4枚なら取り切れない        → アセロラ
            if not _briar_closes_game(p):
                return -2000.0
            # ★ブライアより先に「盤面へ変換できる道具」を使い切る
            #   (2026-08-13 ユーザー指摘)。ブライアはサポート枠を使う詰めの札で、
            #   道具は使っても枠を食わない。先に道具を片付けてから撃つほうが、
            #   引いた札を見たうえで判断できる。
            #   実測(400試合): ブライア使用32回のうち18回が「ブライア→道具」で、
            #   逆順は2回しかなかった。撃てたのに撃たなかったKO可能な番も1回あった。
            #   ★待たせる条件は「その道具を**実際に撃つ**条件」と一致させること。
            #     ずれると撃たない道具を抱えたままブライアが永久に止まる。
            if USE_BRIAR_WAIT_FETCH and (_board_fetch_in_hand(p, me)
                                         or _grass_fetch_worth_it(p)):
                return SHUFFLE_WAIT_SCORE
            return 3600.0
        if cid == BOSS_ORDERS:
            # ★**今のバトル場を倒せるなら絶対に入れ替えない**
            #   (2026-08-11 ユーザー指摘)。オーロンゲexは草弱点で打点2倍、
            #   しかもexなのでサイド2枚。倒せる盤面でボスを撃つのは
            #   その2枚をドブに捨てる行為。
            if USE_KEEP_LETHAL and _lethal_now(p):
                # ★ただし**ベンチにもっとサイドの多い倒せる駒**が居るなら、
                #   そちらを取りに行く(2026-08-12 実測)。maco-macoo は
                #   「前を倒せる」16回中10回でボスを撃っていた。
                #   例: 前が1枚の駒で、ベンチに削れたキチキギスex(2枚)が居る場面。
                #   ベンチのexは逃がされたり回復されたりするので、取れるうちに取る。
                if _best_boss_gain(p, op) <= _prize_value(p.op_active):
                    return LETHAL_BLOCK
            # ★今のバトル場に**打点が通らない**なら、殴っても意味がない。
            #   いしずえのめんexのような壁が前に居るときは、
            #   殴れる相手を引きずり出すのが正解(2026-08-11 ユーザー指摘)。
            if (_damage_to(p, p.op_active) <= 0
                    and _any_damageable_bench(p, op)):
                return 3600.0
            # ★**負けが確定している番**なら、動けない駒を前に出す賭けに出る
            #   (2026-08-13 ユーザー指摘・リプレイ92628923)。
            #   ここは CHIP_THE_ACE より**先**に置く必要がある。
            #   「2回殴れば倒せる」は次の番が来る前提だが、この盤面では来ない。
            if USE_DESPERATION_BOSS and _desperation_boss(p):
                return DESPERATION_BOSS_SCORE
            # ★今のバトル場が「あと2回で倒せる高サイド」なら、
            #   ボスで1枚取りに行くより**殴り続けた方が得**
            #   (2026-08-11 ユーザー指摘)。
            #   実例: エネ5で打点210、メガルカリオex(HP340・サイド3枚)が無傷。
            #     ボスでマクノシタ(HP80)を倒す = サイド1枚、ルカリオは無傷
            #     ルカリオを殴る = 130残り。次の番はエネが増えて確実に倒せ、
            #     しかも**サイド3枚**。削りは次の番に残る
            # ★「相手のサイド4枚以下」という条件は**誤読だった**(2026-08-12)。
            #   使用16回のサイドは 6枚が5回/4枚が6回/2枚が5回で、**制限は無い**。
            #   中央値が低く出たのは「ターン8以降にしか撃たない」ことの反映で、
            #   エネが溜まるまで倒せないだけ。サイド枚数は交絡変数だった。
            #   本当の条件は**ベンチに倒せる駒が居ること**(16/16回で成立)。
            best_pv = _best_boss_gain(p, op)
            cur_dmg = _damage_to(p, p.op_active)
            if (USE_CHIP_THE_ACE and p.op_active is not None and cur_dmg > 0
                    and _prize_value(p.op_active) > best_pv
                    and cur_dmg * CHIP_TURNS >= _remaining_hp(p.op_active)):
                return -2000.0
            # ★このデッキでは「相手のエネもこちらの打点になる」ので、
            #   エネの乗った駒を引きずり出すと打点が伸びる。
            #   引き出して**倒せる**相手が居るときだけ撃つ。
            if best_pv > 0:
                return 2600.0
            return -2000.0
        if cid == CRUSH_HAMMER:
            # ★このワザの打点は**おたがいのバトル場**のエネで伸びる。
            #   相手のエネを剥がす価値は、剥がす場所で正負が変わる。
            #   剥がす先が無い(相手にエネが1個も無い)なら腐る。
            if not _op_has_energy(op):
                return -2000.0
            # ★相手の**ベンチ**にエネが無いなら、剥がせるのはバトル場だけ。
            #   それはこちらの打点を30下げる自傷になる(2026-08-12 ユーザー指摘)。
            #   実測: 対ドラパルト/フーディン/ブリジュラスでは前を叩く割合が
            #   34〜62%あり、いずれもベンチにエネが無い場面だった。
            if USE_HAMMER_BENCH_ONLY and not _op_bench_has_energy(op):
                return -2000.0
            # ★**この番に前を倒しきれる**なら、前のエネを剥がす意味は無い
            #   (2026-08-13 ユーザー指摘)。倒れる駒の攻撃を止めても価値はなく、
            #   Myriad Leaf Shower の打点が30下がるだけ。margin が薄ければ
            #   剥がしたせいで倒しきれなくなる。
            #   剥がせるのがバトル場しか無い場面では、ハンマーごと温存する。
            #   実測(400試合): 標的選択581回のうち **175回(30%)** が
            #   「倒しきれる x ベンチにエネ無し x バトル場を剥がす」だった。
            if (USE_HAMMER_SKIP_WHEN_LETHAL and _lethal_now(p)
                    and not _op_bench_has_energy(op)):
                return -2000.0
            # ★手札を流す札(2600〜3200)より**上**に置く。
            #   効果が相手の場に残るので、流す前に撃たないと丸損。
            #   実測: リーリエ124回 / ジャッジ52回 / クラウン6回、
            #   計182回(200試合)を撃たずに流していた(2026-08-13)。
            return CRUSH_HAMMER_SCORE

        if cid == TOOL_SCRAPPER:
            return 1600.0 if _op_has_tool(op) else -1500.0
        return 0.0

    # ---- Nの筋書きで「どのベンチからエネを取るか」 ----
    #      ctx=SWITCH_ENERGY / type=ENERGY / area=BENCH / 自分側 で来る。
    #      ★**エネの少ない個体から取る**(2026-08-12 ユーザー指定)。
    #        前が倒れたときに繰り出すのは `_placement_bonus` が選ぶ
    #        「エネの多い個体」なので、そこを削らない。
    if (t == OptionType.ENERGY and ctx == SelectContext.SWITCH_ENERGY
            and o.area == AreaType.BENCH
            and (o.playerIndex is None or o.playerIndex == state.yourIndex)):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            return N_PLOT_TAKE_SCORE - len(_energy_units(card)) * 400.0

    # ---- ハンマーの標的(ctx=DISCARD_ENERGY・type=ENERGY で来る) ----
    if (t == OptionType.ENERGY and o.playerIndex is not None
            and o.playerIndex != state.yourIndex):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            return _hammer_target_score(card, o.area, p)

    # ---- 相手のベンチから1体選ぶ(ボスの指令) ----
    if (t == OptionType.CARD and ctx == SelectContext.SWITCH
            and o.area == AreaType.BENCH
            and o.playerIndex is not None
            and o.playerIndex != state.yourIndex):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            return _boss_target_score(card, p)

    # ---- 自分の場から1体選ぶ(アセロラの守る対象) ----
    #     実測でこの選択は ctx=EFFECT_TARGET で来る。文脈を絞らないと
    #     他の「自分の場から選ぶ」場面まで巻き込む
    if (t == OptionType.CARD and ctx == SelectContext.EFFECT_TARGET
            and o.area in (AreaType.ACTIVE, AreaType.BENCH)
            and (o.playerIndex is None or o.playerIndex == state.yourIndex)):
        # 殴られるのはバトル場。ベンチを守っても意味がない
        return 3000.0 if o.area == AreaType.ACTIVE else -1000.0

    # ---- 手札を捨てる ----
    if (t == OptionType.CARD and ctx == SelectContext.DISCARD
            and o.area == AreaType.HAND):
        card = gh._hand_card(obs, o.index, me)
        if card is not None:
            return _discard_priority(card, p)
    return 0.0


def _ogerpon_left(p, me):
    """山札に残っているオーガポンの推定枚数(サイド落ちは見えないので上限)。"""
    seen = p.hand_counts.get(OGERPON, 0) + p.bench_ogerpon
    if p.active_id == OGERPON:
        seen += 1
    try:
        seen += len([c for c in (me.discard or [])
                     if c is not None and c.id == OGERPON])
    except (AttributeError, TypeError):
        pass
    return OGERPON_COPIES - seen


def _op_bench_has_energy(op):
    try:
        return any(_energy_units(x) for x in (op.bench or []) if x is not None)
    except (AttributeError, TypeError):
        return False


def _op_has_energy(op):
    try:
        field = ([x for x in (op.active or []) if x]
                 + [x for x in (op.bench or []) if x])
        return any(_energy_units(x) for x in field)
    except (AttributeError, TypeError):
        return False


def _hammer_target_score(card, area, p):
    """ハンマーでどのエネを剥がすか。**このデッキでは常識と逆になる。**

    Myriad Leaf Shower は `30 + 30 x (おたがいのバトル場のエネ数)`。
      ・相手の**バトル場**から剥がす → **こちらの打点が30下がる**。自傷になる
      ・相手の**ベンチ**から剥がす   → 打点は不変で、相手の準備だけ遅れる。純粋な得
    したがって既定は**ベンチ優先**。バトル場を叩いてよいのは、
    その1個を剥がすと**相手がその番に攻撃できなくなる**ときだけ。
    打点30を捨てても、相手の攻撃1回を消す方が価値が高い。

    ベンチの中では「最終形の打点が高いライン(=これから殴ってくる駒)」を優先する。
    """
    n = len(_energy_units(card))
    if n <= 0:
        return -1000.0
    if HAMMER_PREFER_ACTIVE:
        # 前の主力を優先する版(ユーザー指定でA/B)
        sc = 3000.0 if area == AreaType.ACTIVE else 800.0
        sc += min(_final_max_damage(card.id), ACE_DAMAGE_CAP) * 4.0
        sc += max(0, 4 - n) * 200.0
        return sc
    if area == AreaType.ACTIVE:
        # ★この番に倒しきれるなら、前を剥がす理由はどれも消える。
        #   攻撃を止める価値も無い(倒れるので)。ベンチが選べるなら必ずそちら。
        if USE_HAMMER_SKIP_WHEN_LETHAL and _lethal_now(p):
            return HAMMER_LETHAL_BLOCK
        # 剥がすと攻撃コストに届かなくなるか
        need = _cheapest_attack_cost(card.id)
        if need and n == need:
            return HAMMER_DENY_ATTACK
        return HAMMER_ACTIVE_SCORE      # 自分の打点が下がるので基本は避ける
    sc = HAMMER_BENCH_SCORE
    # ★最終形の打点だけで重み付けすると、**あと1〜2回進化しないと殴れない駒**
    #   (ドラメシヤ/マリィのベロバー/リオル)が最上位に来る。そこのエネを
    #   剥がしても効きが遅い(2026-08-13 ユーザー指摘)。
    #   残り段数で割り引き、**すぐ殴れる駒**を優先する。
    sc += (min(_final_max_damage(card.id), ACE_DAMAGE_CAP) * 4.0
           / (1.0 + _stages_left(card.id) * HAMMER_STAGE_PENALTY))
    sc += max(0, 4 - n) * 200.0         # あと1個で撃てる駒を優先して潰す
    # ★**エネが条件の特性**を持つ駒は、最後の1個を剥がすと特性ごと止まる
    #   (2026-08-13 ユーザー指定・対オーロンゲ)。
    #   マシマシラのアドレナブレインは「【悪】エネルギーがついているなら
    #   ダメカンを3個まで移す」。1個しか付いていないなら剥がす価値が高い。
    if n <= 1 and _energy_gated_ability(card.id):
        sc += HAMMER_ABILITY_BONUS
    return sc


_COST_CACHE = {}
_ATK_COST = None


_EG_CACHE = {}


def _energy_gated_ability(cid):
    """特性の発動条件に『自分についているエネルギー』が入っているか。"""
    v = _EG_CACHE.get(cid)
    if v is None:
        c = gh._CARD.get(cid)
        v = False
        for sk in (getattr(c, "skills", None) or []):
            t = (getattr(sk, "text", "") or "").replace("\u2019", "'").lower()
            if "energy attached" in t:
                v = True
        _EG_CACHE[cid] = v
    return v


def _stages_left(cid):
    """最終形まであと何回進化するか(0 = もう進化しない)。"""
    c = gh._CARD.get(cid)
    if c is None:
        return 0
    fwd = _evo_forward()
    n = 0
    cur = c
    while n < 3:
        nxt = fwd.get(cur.name) or []
        if not nxt:
            break
        cur = nxt[0]
        n += 1
    return n


def _cheapest_attack_cost(cid):
    """一番安いワザのエネコスト。0 なら不明。"""
    v = _COST_CACHE.get(cid)
    if v is None:
        c = gh._CARD.get(cid)
        costs = []
        if c is not None:
            from cg.api import all_attack
            global _ATK_COST
            if _ATK_COST is None:
                _ATK_COST = {a.attackId: len(a.energies or [])
                             for a in all_attack()}
            costs = [_ATK_COST.get(a, 0) for a in (c.attacks or [])]
        v = min([x for x in costs if x] or [0])
        _COST_CACHE[cid] = v
    return v


def _op_has_tool(op):
    try:
        field = [x for x in (op.active or []) if x] + [x for x in (op.bench or []) if x]
        return any(getattr(x, "tools", None) for x in field)
    except (AttributeError, TypeError):
        return False


def _breaks_any_lethal(p, op, plus_hp):
    """+plus_hp で「今この番に取れるKO」が1つでも消えるか。

    見るのは2つ。
      ・相手のバトル場(そのまま殴って倒せる相手)
      ・**ボスの指令が手札にあるとき**のベンチ(引き出して倒せる相手)
    どちらも+30の対象は**たね**だけなので、進化済みは無視してよい。
    """
    if _lethal_now(p) and _breaks_lethal_by(p, plus_hp):
        return True
    # ★ベンチのKOを守るのは、**その番に実際にボスを撃つときだけ**
    #   (2026-08-13 ユーザー指摘・リプレイ92577532 step54)。
    #   手札にボスがあるだけで止めていたので、
    #   「CHIP_THE_ACE で殴り続けると決めてボスは撃たない」番に、
    #   撃たないKOを守ってエキサイトスタジアムを張れずにいた。
    if not _would_boss_now(p, op):
        return False
    try:
        bench = [x for x in (op.bench or []) if x is not None]
    except (AttributeError, TypeError):
        return False
    for b in bench:
        cd = gh._CARD.get(b.id)
        if cd is None or not getattr(cd, "basic", False):
            continue
        d = _damage_to(p, b)
        hp = _remaining_hp(b)
        if hp and d >= hp and d < hp + plus_hp:
            return True
    return False


def _breaks_lethal_by(p, plus_hp):
    """相手のバトル場のHPが plus_hp 増えると、倒せなくなるか。"""
    o = p.op_active
    if o is None:
        return False
    cd = gh._CARD.get(o.id)
    if cd is None or not getattr(cd, "basic", False):
        return False                      # エキサイトスタジアムはたねだけ
    return _damage_to(p, o) < _remaining_hp(o) + plus_hp


def _free_retreat(card):
    """逃げエネ0か。引きずり出してもタダで戻される。"""
    cd = gh._CARD.get(card.id) if card is not None else None
    if cd is None:
        return False
    try:
        return (cd.retreatCost or 0) == 0
    except (AttributeError, TypeError):
        return False


def _worth_dragging(p, b):
    """引きずり出す価値があるか(打点が通り、逃げ0なら倒しきれること)。"""
    if _damage_to(p, b) <= 0:
        return False
    if not (USE_BOSS_SKIP_FREE_RETREAT and _free_retreat(b)):
        return True
    hp = _remaining_hp(b)
    return bool(hp) and _damage_to(p, b) >= hp


def _any_damageable_bench(p, op):
    """ベンチに「打点が通る」駒が居るか(壁から逃げる判断用)。

    ★逃げ0の駒しか居ないなら、引きずり出してもタダで戻されるので数えない
      (2026-08-13 ユーザー指摘)。ここを直さないと、壁が前に居る場面で
      ボスを撃つ判断(3600)だけが通って標的が無い、という状態になる。
    """
    try:
        return any(_worth_dragging(p, b)
                   for b in (op.bench or []) if b is not None)
    except (AttributeError, TypeError):
        return False


def _best_boss_gain(p, op):
    """ベンチから引きずり出して**倒せる**駒のうち、一番サイドが多いもの。

    ★**この番にワザを撃てないなら 0**(2026-08-13 ユーザー指摘・リプレイ92578488)。
      Myriad Leaf Shower は【草】3個が必要。エネ2で引きずり出しても倒せず、
      相手は次の番に好きな駒を前に出し直せる。実例: 前がマリィのベロバー(HP70)、
      ベンチにも同じマリィのベロバー。エネ2で撃てないのに入れ替えていた。
    """
    if not _can_attack_now(p):
        return 0
    best = 0
    try:
        bench = [x for x in (op.bench or []) if x is not None]
    except (AttributeError, TypeError):
        return 0
    for b in bench:
        if _damage_to(p, b) >= _remaining_hp(b) > 0:
            best = max(best, _prize_value(b))
    return best


def _would_boss_now(p, op):
    """この番、実際にボスの指令を撃って引きずり出すか。

    ボスの分岐と同じ条件をここに写している。`_breaks_any_lethal` から使う。
    """
    if not p.hand_counts.get(BOSS_ORDERS):
        return False
    best_pv = _best_boss_gain(p, op)
    if best_pv <= 0:
        return False
    if USE_KEEP_LETHAL and _lethal_now(p):
        if best_pv <= _prize_value(p.op_active):
            return False
    cur_dmg = _damage_to(p, p.op_active)
    if (USE_CHIP_THE_ACE and p.op_active is not None and cur_dmg > 0
            and _prize_value(p.op_active) > best_pv
            and cur_dmg * CHIP_TURNS >= _remaining_hp(p.op_active)):
        return False
    return True


def _stuck_on_bench(card):
    """その駒を前に出したとき、**この場で殴れず、逃げることもできない**か。

    エネが一番安いワザのコストに届いていなければ殴れない。
    逃げエネもエネから払うので、エネ0で逃げエネ1以上なら**動けない**。
    (相手は手貼り or 入れ替え札を引かないと復帰できない)
    """
    cd = gh._CARD.get(card.id)
    if cd is None:
        return False
    n = len(_energy_units(card))
    cost = _cheapest_attack_cost(card.id)
    if cost <= 0 or n >= cost:
        return False                      # 殴れる(か、コスト不明)
    try:
        return n < (cd.retreatCost or 0)  # 逃げるエネも足りない
    except (AttributeError, TypeError):
        return False


def _desperation_target(p):
    """賭けに出て引きずり出す駒。

    ★条件は「動けない」だけでは足りない(2026-08-13 実測)。
      **倒し切ればそのまま勝てる駒**に限る。1枚しか取れない駒を引き出しても
      次の番に倒されて負けは変わらず、ボスと殴る番を捨てるだけになる。
      実測でも1枚駒(ソルロック等)ばかり引き出して勝率を落としていた。
      リプレイ92628923の標的キチキギスexは**サイド2枚**で、
      こちらの残りサイドも2枚。倒せばそこで勝ち。
    """
    best, best_key = None, None
    for b in p.op_bench:
        if not _stuck_on_bench(b):
            continue
        if _prize_value(b) < p.my_prize:
            continue                      # 倒しても勝ち切れない
        dmg = _damage_to(p, b)
        if dmg <= 0 or dmg * DESPERATION_TURNS < _remaining_hp(b):
            continue                      # 2回殴っても落とせない
        key = (_prize_value(b), dmg - _remaining_hp(b))
        if best_key is None or key > best_key:
            best, best_key = b, key
    return best


def _desperation_boss(p, in_hand=True):
    """負けが決まっている番に、動けない駒を引きずり出す賭けに出るか。

    ★2026-08-13 ユーザー指摘・リプレイ 92628923。
      相手はドラパルトex(HP320)。こちらは前が残り80、サイド2枚どうし。
      次の番に殴られればサイドを取り切られて負けが確定していた。
      打点270ではドラパルトを倒せず、ブライアもKOが無いので腐り、
      アセロラも手札に無い。ここで**エネ0のキチキギスex**を引きずり出せば、
      相手が手札からエネか入れ替え札を出せない限り殴られない。
      通れば次の番に倒してサイド2枚で勝ち。**負け確なら賭ける方が得**。
    """
    if not USE_DESPERATION_BOSS:
        return False
    # ★標的を選ぶ場面ではボスは**もう手札から消えている**ので数えない。
    if in_hand and not p.hand_counts.get(BOSS_ORDERS):
        return False
    if p.active is None:
        return False
    if p.op_prize > _prize_value(p.active):
        return False                      # 倒されてもまだ負けではない
    # ★相手が**実際に撃てる**打点で見る(手貼り1回ぶんは見込む)。
    #   `_incoming_damage` の最大打点で判定すると過大に「負け確」になる。
    if _incoming_damage_soon(p) < _remaining_hp(p.active):
        return False
    if _has_survival_out(p):
        return False                      # 耐える手があるなら賭けない
    # ★「サイドが1枚取れる」だけでは賭けを降りる理由にならない
    #   (リプレイ92628923: ドラクロー(HP90)を引き出せば1枚取れたが、
    #    こちらのサイドは2枚。取っても次の番に倒されて負けは変わらない)。
    #   降りてよいのは**この番に取り切れる**ときだけ。
    if _wins_this_turn(p) or _briar_closes_game(p):
        return False
    if (p.hand_counts.get(ACEROLA) and p.op_prize <= ACEROLA_MAX_PRIZE
            and p.op_active_ex):
        return False                      # アセロラで凌げるならそちらが先
    return _desperation_target(p) is not None


def _wins_this_turn(p):
    """この番にサイドを取り切れるか(そのまま殴る/ボスで引き出して倒す)。"""
    best = _best_boss_gain_p(p)
    if _lethal_now(p) and p.op_active is not None:
        best = max(best, _prize_value(p.op_active))
    return best >= p.my_prize


def _best_boss_gain_p(p):
    """`_best_boss_gain` の Plan 版(相手ベンチは Plan に持たせてある)。"""
    if not _can_attack_now(p):
        return 0
    best = 0
    for b in p.op_bench:
        if _damage_to(p, b) >= _remaining_hp(b) > 0:
            best = max(best, _prize_value(b))
    return best


def _boss_target_score(card, p):
    """引きずり出す相手。**エネが乗っているほど自分の打点が上がる**。

    Myriad Leaf Shower は相手のバトル場のエネも数えるので、
    エネの多い駒を前に出すと、そのぶん打点が伸びて倒しやすくなる。
    倒しきれるなら最優先。
    """
    # ★殴れない相手は絶対に選ばない。いしずえのめんexを引きずり出して
    #   殴っていたのがこれ(打点0なので何回殴っても意味がない)。
    if _we_have_ability(p) and _blocks_ability_attackers(card.id):
        return -9999.0
    # ★捨て身のボスで撃ったときは、**動けない駒**を選ぶ(通常の評価とは
    #   狙いが逆で、エネが乗っていない駒ほど良い)。
    if USE_DESPERATION_BOSS and _desperation_boss(p, in_hand=False):
        tgt = _desperation_target(p)
        if tgt is not None:
            same = (getattr(card, "serial", None) == getattr(tgt, "serial", None)
                    if getattr(tgt, "serial", None) is not None
                    else card.id == tgt.id)
            return DESPERATION_TARGET_SCORE if same else -6000.0
    dmg = _damage_to(p, card)
    v = len(_energy_units(card)) * 300.0
    hp = _remaining_hp(card)
    # ★**逃げエネ0の駒は、倒しきれないなら引きずり出さない**
    #   (2026-08-13 ユーザー指摘・対ブリジュラス)。エースバーン(HP160/逃げ0)を
    #   前に出しても、相手はタダで元の駒に戻せる。ボスを1枚捨てるだけになる。
    #   倒しきれるなら普通に価値がある(サイドが取れる)ので、そのときは通す。
    if (USE_BOSS_SKIP_FREE_RETREAT and hp and dmg < hp
            and _free_retreat(card)):
        return BOSS_FREE_RETREAT_BLOCK
    if hp and dmg >= hp:
        # 倒せるなら**サイドの枚数**ぶん価値がある(ex=2枚, メガex=3枚)
        v += 3000.0 * _prize_value(card)
        # ★さらに「相手のエース、またはその進化前」を優先する
        #   (2026-08-11 ユーザー指定: メガルカリオかリオルを倒す)。
        #   進化前を倒しておけば本体が出てこない。
        v += min(_final_max_damage(card.id), ACE_DAMAGE_CAP) * ACE_WEIGHT
    return v


def _discard_priority(card, p):
    """捨てる順。大きいほど先に捨てる。エネは最後まで残す。"""
    cid = card.id
    if cid in ANY_ENERGY:
        # 草エネは打点そのもの。余っていても最後に捨てる
        return -2000.0 if p.grass_in_hand <= ENERGY_THIN else -500.0
    if cid == OGERPON:
        return -1500.0
    if cid in (ENERGY_SEARCH, BUG_CATCHING, ENERGY_RECOVER):
        return 500.0
    if cid in (TOOL_SCRAPPER, BOSS_ORDERS, BRIAR, N_PLOT):
        return 2500.0
    return 1500.0


def _placement_bonus(o, obs, state, me, p):
    """バトル場に出す駒。オーガポンしか居ないので**エネの多い個体**を選ぶ。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id != OGERPON:
        return 0.0
    # ベンチで溜めた個体をそのまま繰り出すのがこのデッキの回し方
    return 1000.0 + len(_energy_units(card)) * 400.0


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
        _resolve_attacks()
        obs = to_observation_class(obs_dict)
        select = obs.select
        state = obs.current
        me = state.players[state.yourIndex]
        op = state.players[1 - state.yourIndex]
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

        # 攻撃はターンを終える。特性/エネ/展開はタダなので先に回す
        if (USE_ACT_BEFORE_ATTACK and ctx == SelectContext.MAIN
                and select.option
                and select.option[order[0]].type == OptionType.ATTACK):
            prep = [i for i in order
                    if select.option[i].type in (OptionType.ABILITY,
                                                 OptionType.ATTACH,
                                                 OptionType.PLAY)
                    and scores[i] >= PREP_MIN_SCORE]
            if prep:
                order = [prep[0]] + [j for j in order if j != prep[0]]

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))
        if ctx in (SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO,
                   SelectContext.TO_HAND, SelectContext.TO_FIELD) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
