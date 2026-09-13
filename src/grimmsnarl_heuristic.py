"""マリィのオーロンゲex 専用ヒューリスティック(ラダー1位の構築を再現した本流版)。

deck_grimmsnarl.csv 用。旧プール版(deck_marnie_grimmsnarl.csv 用の
grimmsnarl_pool_heuristic.py)とはデッキが異なる。1位のリプレイから再現した。

## 1位デッキの設計思想

プール版の「ノココッチでドローしサブアタッカーも積む何でも屋」に対し、
Luca版は**コンボ部品集めに全振りした一貫性特化型**:

  ロケット団のラムダ(1219)×4 … トレーナーズをサーチ。フル投入
  夜のタンカ(1097)×3        … トラッシュからポケモン/悪エネを回収
  スパイクタウンジム(1259)×4 … 毎ターン「マリィのポケモン」をサーチ
  → ベロバー→(ふしぎなアメ)→オーロンゲex を安定して最速で通す

加えて **ユキメノコ(104) + ユキワラシ(860) の氷エンジン**:
  ユキメノコ特性「いてつくとばり」= ポケモンチェックのたび、
  おたがいの**特性を持つポケモン全員**(ユキメノコを除く)にダメカン1個。
  相手が特性デッキ(フーディン/ガブリアス等)なら継続的に削れる。
  ※ このデッキは悪エネのみで、ユキワラシ/ユキメノコのワザは水コストなので
    撃てない。**ベンチに置いておくだけの特性エンジン**。
  ※ 自分のマシマシラ(特性)・オーロンゲex(特性)も1ずつ喰らうが、
    相手の特性ポケモンの方が数が多く小型なので割に合う。

## 核のコンボ(プール版と共通)

オーロンゲex(648) 特性パンクアップ: 手札から出して進化させたとき、
山札から基本【悪】エネルギーを5枚までマリィのポケモンに付ける。
ワザ シャドーバレット [悪,悪] 180 + 相手ベンチ1匹に30。
ふしぎなアメも「手札から進化」なのでパンクアップが乗る。

## 弱点
弱点【草】。exなのでイワパレスの特性に完封される(構造的、埋まらない)。
"""

import generic_heuristic as gh

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)

# ---------------------------------------------------------------- カードID
GRIMMSNARL_EX = 648   # マリィのオーロンゲex HP320 2進化
MORGREM = 647         # マリィのギモー      HP100 1進化
IMPIDIMP = 646        # マリィのベロバー    HP70  たね
MUNKIDORI = 112       # マシマシラ          HP110 たね(アドレナブレイン)
SNORUNT = 860         # ユキワラシ          HP70  たね(氷エンジンの進化元)
FROSLASS = 104        # ユキメノコ          HP90  1進化(いてつくとばり)

DARK_ENERGY = 7       # 基本【悪】エネルギー ×10

POFFIN = 1086         # なかよしポフィン(HP70以下のたね2枚)
RARE_CANDY = 1079     # ふしぎなアメ
POKE_PAD = 1152       # ポケパッド(ルール持ち以外のポケモンをサーチ)
LILLIE = 1227         # リーリエの決心(手札総入れ替えで6/8枚)
SPIKEMUTH_GYM = 1259  # スパイクタウンジム(毎ターン マリィのポケモンをサーチ)
DAWN = 1231           # ヒカリ(たね/1進化/2進化を1枚ずつ)
BOSS_ORDERS = 1182    # ボスの指令
ROCKET_LAMBDA = 1219  # ロケット団のラムダ(トレーナーズをサーチ)
NIGHT_STRETCHER = 1097  # 夜のタンカ(トラッシュからポケモン/基本エネ回収)
POKEGEAR = 1122       # ポケギア3.0(山札上7枚からサポートをサーチ)
UNFAIR_STAMP = 1080   # アンフェアスタンプ(ACE SPEC。きぜつ時に手札リフレッシュ)
TOOL_SCRAPPER = 1137  # ツールスクラッパー(どうぐをトラッシュ)

# ワザ・特性
ATK_SHADOW_BULLET = 937    # オーロンゲex [悪,悪] 180 + ベンチ30
ATK_CORKSCREW_MOR = 936    # ギモー   [悪,悪] 60
ATK_MIND_BEND = 141        # マシマシラ [超,無] 60 + こんらん

MARNIE_LINE = {IMPIDIMP, MORGREM, GRIMMSNARL_EX}   # パンクアップの対象
FROSLASS_LINE = {SNORUNT, FROSLASS}
GRASS = 1                  # オーロンゲexの弱点タイプ

# ---------------------------------------------------------------- 設定(A/B用)
USE_GENERIC_BASE = True

# 「KOできない攻撃はセットアップを全部終えてから」にするか。1位(Luca)の5リプレイ
# 分析で、MAINでの攻撃はLuca9%に対しこちら49%と殴りすぎ・盤面作りが不足と判明。
# Lucaはエネ付け35%/進化10%/特性6%で作り込んでから殴る。それに寄せる。
# ※ 唯一のローカル強敵フーディンはこのデッキの負け越しマッチかつ高速レース型で
#   攻撃が報われるため、この変更の検証には不適(ローカルでは中立〜微減)。
#   1位の実行動に基づく更新なので、最終判定はラダーで行う(ユーザー判断で有効化)。
SETUP_BEFORE_ATTACK = True
# 非KO時の攻撃スコア。有益なセットアップ(エネ付け~2200/進化/特性~1900/良プレイ)より
# 低く、END(10)やゴミ手より高い位置に置く。
# 500 で非KO攻撃が実際に減り、私の攻撃割合が 49%→38% と Luca(9%) 方向に動く
# (1500以上だとKO判定(6000)が優勢で49%のまま変化しない)。残り38%はKO攻撃。
# Luca の 9% はKOも見送る作り込みだが、KO見送りは事故リスクが高く再現しない。
# 対フーディンでは 29.4%→26.8% と約2.6pp下がるが、フーディンは高速レース型かつ
# このデッキの負け越しマッチで、Luca流が最も損をする不適な検証相手。
ATTACK_DEVELOP_SCORE = 500.0
USE_EVOLVE_RUSH = True       # ベロバー→(アメ)→オーロンゲex を最優先
USE_ENERGY_ROUTING = True    # 悪エネの付け先を用途で振り分ける
USE_ADRENA = True            # マシマシラのアドレナブレイン
USE_STADIUM_CARE = True      # スパイクタウンジムを維持
USE_GRASS_AWARENESS = True   # 草(弱点)の相手を警戒
USE_FROSLASS_ENGINE = True   # ユキメノコを立てて特性で削る
FIX_ICE_POSITION = True      # バトル場のユキワラシをユキメノコに進化させない(実戦悪手対策)
# 氷を「オーロンゲexが立ち相手に特性ポケが複数のとき」だけに絞るか。
# 対フーディンでは変化なし(27.3%→26.3%)、広い相手ではむしろ微減(+0.8%→-2.4%、
# ただし80試合/セルでノイズ大)。1位デッキに忠実な無条件を既定にする。
FROSLASS_AFTER_CORE = False
USE_SEARCH_ENGINE = True     # ラムダ/タンカ/ポケギアでコンボ部品を集める

# --- 2026-07-26 上位(Luca 33勝9敗)のリプレイ52件の実測に基づく追加 ---
# 傷んだオーロンゲexを、倒される前にベンチへ退避する。
# 実測: 傷んで逃げた16件のうち14件がオーロンゲexで、そのHP残存率は平均53%。
# (満タンで逃げた37件は小型の盤面整理でエネ1.57個しかなく、退避ではない)
# ※ ローカル測定では判定不能だったが、上位(Luca 1200)の実行動に基づくので有効化。
#    ローカルの相手4種(3つは自作)は本番を代表できず、最終判定はラダーで行う。
USE_GX_RETREAT = True
GX_RETREAT_HP = 0.6         # HP残存率がこれ以下なら退避する
# マシマシラを最優先でエネ起動する(回復エンジンを最速で立てる)。
# 実測: 最初のエネ付け先としてマシマシラが12回(最多タイ)、到達は平均3.0ターン(中央2)。
# ※ ローカルでは効果を検出できなかったが、上位の実行動なので有効化(ラダーで判定)。
USE_MUNKI_FIRST = True
# ボスの対象は「特性持ち」と「ex」を優先(HPは無関係)。
# 実測: 特性持ち 選んだ69% vs 見送り52% / ex 53% vs 42% / HP 121 vs 120(差なし)。
# ※ ローカルでは判定不能。上位の実行動なので有効化(ラダーで判定)。
#
# 【2026-07-26 測定の総括】上位(Luca)の観察を3点実装したが、いずれも勝率に出なかった:
#   反復5: 全OFF 29.1%±0.8 / 退避のみ 32.5%±1.9 / マシマシラのみ 29.4% / ボスのみ 31.2%
#   反復5: 3つ全部ON 28.4%±1.4  (単独ではプラスに見えるのに、組み合わせると悪化)
#   反復7: 全OFF 33.4%±1.2 / 退避+ボス 31.0% / 3つON 30.6%
# **同一設定の全OFFが測定ごとに 29.1→31.2→33.4% と4pp動く**ため、狙う効果(±3pp)を
# この測定系では検出できない。**ローカルの相手は4種(うち3つは自作)しかなく本番を
# 代表できない**ため、上位(Luca=1200)の実行動に忠実な方を採る方針で3点とも有効化した。
# 最終判定はラダー(基準点600)で行う。
#
# ※ 2026-07-26 追記: ユーザー指摘「倒せる相手に限り、その中で最も強い相手を
#   引き出すべき」に沿って書き換えたが(倒せない相手は -1000〜-2000、倒せるなら
#   pz*1000+hp で強い相手を優先)、**反復8回で 44.6%→42.2% と -2.4pp 悪化**した。
#   ワナイダー側でも同じ方針が -3pp 前後だった。倒せる相手が複数いる局面自体が
#   少なく、むしろ「特性持ちを止める」等の別の価値を捨てた副作用が疑われる。
#   → ただし**ローカルの相手4種(3つは自作)は本番を代表できない**ため、
#     「倒しきれない相手を引き出すと返り討ちに合う」という理屈を優先して有効化。
#     最終判定はラダーで行う(ユーザー判断)。
USE_BOSS_TARGETING = True
# パンクアップで山札の悪エネを「上限まで」取る。
# ★実戦の観察(ユーザー報告「オーロンゲにエネが1枚しか付いていない」)から発覚したバグ。
# パンクアップの配分は context22 / minCount=0 / maxCount=5 で来て、選択肢は全て
# 山札の基本悪エネ(id=7)。従来は k=min(max(lo,1),hi,...) で**最小の1枚しか取って
# いなかった**。悪エネは多く取るほど得なので上限まで取る。
USE_PUNK_MAX = True
# マシマシラのアドレナブレインを「攻撃より先に」使う。
# ★実戦の観察(ユーザー報告)から発覚: 攻撃(KO時6000)が特性(1900)を上回るため、
# オーロンゲが殴れる状況では特性を使わずにターンが終わっていた
# (実測: 特性が選べた66局面のうち14回は攻撃を優先=マシマシラが機能しない)。
# 攻撃はターンを終わらせるので、使える特性は必ず攻撃の前に使う。
USE_ADRENA_BEFORE_ATTACK = True
# 無意味な逃げを禁止する。
# ★実戦の観察: 「バトル場マシマシラ→ベンチのマシマシラと交代、両方HP満タン」
# という、逃げエネを捨てるだけの手が出ていた(RETREATの既定値が100点だったため)。
USE_NO_POINTLESS_RETREAT = True
# 手詰まり(手札に今使えるカードが1枚も無い)ならリーリエの決心で引き直す。
# ★実戦の観察: 手札=リーリエ2+ユキメノコ2、盤面=ベロバー3体で進化先が無いのに、
# 手札4枚で `hand<=3` を満たさず**使わずにターンエンド**して育つ前に負けていた。
USE_LILLIE_DEADHAND = True
# リーリエは手札を山札に戻すので、やれることを済ませてから使う
USE_OPPONENT_SIDE_BONUS_GR = True
# ヒカリ(たね/1進化/2進化サーチ)はラインが欠けているときだけ使う
USE_DAWN_CARE = True
# ボスの指令は「今ターン倒せる」ときだけ(サポート枠を消費するため)
USE_BOSS_NEEDS_ATTACK = True
# サイド6のときは8枚ドローになるのでリーリエを積極的に使う
BOSS_ORDERS_SCORE = 1550.0   # リーリエ(1600)に枠を譲る水準。実測で較正
USE_LILLIE_PRIZE6 = True
LILLIE_HAND_MAX_P6 = 6
LILLIE_HAND_MAX = 5   # 実測で較正
USE_LILLIE_LAST_GR = True
LILLIE_PREP_MIN_SCORE = 1000.0
# パンクアップの配分先を「エネが足りていない個体」に分散する。
# ★ユーザー指摘: オーロンゲが2体いるとき、既に2個付いている方には付けず、
# 2個に達していない個体に付けるべき(ベロバー/ギモーも含む)。
# 従来はカードの種類だけでスコアを付けていたため同じ個体に集中していた。
USE_ENERGY_SPREAD = True
# イワパレス(345)がいる相手には、オーロンゲexに進化させずギモーで止める。
# ★ユーザー提案。イワパレスの特性「しんぴのいしやど」=
#   「**このポケモン**は、相手の『ポケモンex』からワザのダメージを受けない」。
#   オーロンゲex(180打点)はダメージ0にされるが、**ギモー(647,非ex)は
#   コークスクリューパンチ[悪,悪]60ダメージが通る**(HP150を3発)。
#   進化させないことで「殴れる非exアタッカー」を残す。
USE_HOLD_EVOLVE_VS_CRUSTLE = True
# アドレナブレインの「移動元」を選ぶ(オーロンゲexを優先して救う)。
# ★ユーザー指摘「マシマシラHP40・オーロンゲHP20のときマシマシラから移していた」
#   から発覚。移動元(ctx=16)は選択肢が2〜3個出るケースがあり、実測で
#   オーロンゲexが候補にいるのにマシマシラから取っていた例が8件あった。
USE_ADRENA_SOURCE = True

# アドレナブレインでダメカンを移す「先」を選ぶ(ctx=13)。
# 従来は移し先が汎用スコア任せで、実測すると相手の**無傷のフーディンHP140/140**に
# 移していた(30では倒せず、ほぼ無駄)。30で倒せる相手を最優先にする。
# ユーザー提案: オーロンゲ(180)が撃てるなら、HP210以下は30入れればワザでKO圏。
# ※ 1度目の実装は基準値を下げてしまい**逆効果だった**(移し先スコアが低いと
#   アドレナブレイン自体が選ばれにくくなり、使用が67→28回に減って -2.8pp)。
#   今は下限1500を確保した上で順位付けだけ変える形にしている。
USE_ADRENA_TARGETING = True

# ★2026-07-28 1位(Dries @ Tufa Labs, 1226.7)のリプレイ59戦との差分分析から。
#   デッキは**うちと完全一致の60枚**なので、差は操縦のみ。
#   replay_diff.py で同じ観測を突き合わせた実測値:
#     ctx16(自分のどこからダメカンを剥がすか)  1位: マシマシラ51.6% / オーロンゲex41.8%
#                                              うち: マシマシラ24.2% / オーロンゲex70.2%
#     ctx13(相手のどこへ移すか)                1位: マシマシラ49.2% / うち28.0%
#     ctx15(シャドーバレットのベンチ30の先)    1位: インプ9.4%・オーロンゲex6.7%
#                                              うち: インプ1.3%・オーロンゲex16.1%
#   機序: アドレナブレインは「移す」ので、**移せる量(最大3個)は移動元を誰にしても
#   同じ**。つまり移動元の選択は純粋に自分側の延命問題。マシマシラはHP110で、
#   しかも自分のフロストラス(特性持ち全員にダメカン)で毎ターン削れる。
#   HP320のオーロンゲexから30を剥がしても生存にほとんど寄与しない。
USE_ADRENA_SOURCE_FRAGILE = True
# シャドーバレットの打点 = 生存閾値(バトル場180 / ベンチ30)
SHADOW_BULLET_ACTIVE = 180
SHADOW_BULLET_BENCH = 30
USE_ADRENA_SURVIVAL_THRESHOLD = True

# シャドーバレットの「相手ベンチへの30ダメージ」の対象(ctx=15)。
# ★これまで専用の分岐が無く、**ボスの指令用の分岐に落ちていた**。
#   そこは「180で倒せない相手は -1500」なので候補がほぼ全部同点になり、
#   選択が事実上でたらめになっていた(HP320のオーロンゲexに撒く等)。
USE_BENCH_DAMAGE_TARGET = True

# 相手の特性エンジン(マシマシラ)を優先して潰す。
USE_ENGINE_DENIAL = True

# 攻撃する前に「やれる準備」を全部済ませる(2026-07-27 ユーザー指摘)。
# 攻撃はターンを終わらせるので、進化・エネ付け・マシマシラの特性が残っているなら後回し。
USE_ACT_BEFORE_ATTACK = True
CRUSTLE = 345
DWEBBLE = 344
CRUSTLE_LINE = {CRUSTLE, DWEBBLE}

# ---------------------------------------------------------------- ターン内状態
_turn = -1
# ★アドレナブレインは「このポケモンにつき」1ターン1回なので、
#   **マシマシラ1体ごとに**使用済みを管理する(2026-07-26 ユーザー指摘)。
#   単一の bool にしていたため、1体使うと場の全マシマシラがブロックされ、
#   2体いても2回目が使えていなかった(実測: 同ターン1回目33回 vs 2回目4回。
#   ゲーム側は2体分の選択肢を出している)。
#   キーは (area, index) = 盤面上の位置。
_used_adrena_slots = set()


def _update_turn_state(state):
    global _turn, _used_adrena_slots
    if state.turn != _turn:
        _turn = state.turn
        _used_adrena_slots = set()


def reset_state():
    global _turn, _used_adrena_slots
    _turn = -1
    _used_adrena_slots = set()


# ---------------------------------------------------------------- 盤面の把握
class Plan:
    __slots__ = ("active", "active_id", "field_counts", "hand_counts",
                 "bench_free", "gx_in_play", "gx_ready", "damaged",
                 "op_active", "op_grass", "boss_target", "stadium_ours",
                 "can_candy", "froslass_in_play", "snorunt_in_play",
                 "op_ability_count", "active_hp_ratio", "bench_fresh_gx",
                 "incoming", "will_be_koed", "op_crustle")

    def __init__(self):
        self.active = None
        self.active_id = -1
        self.gx_in_play = 0
        self.gx_ready = False
        self.damaged = 0
        self.op_active = None
        self.op_grass = False
        self.boss_target = -1
        self.stadium_ours = False
        self.can_candy = False
        self.froslass_in_play = 0
        self.snorunt_in_play = 0
        self.op_ability_count = 0


# 「ダメカンN個」表記の可変ワザは generic の _ATK_VARIABLE に載っておらず、
# 推定ダメージが極端に小さく出る。被弾予測に使う主要な脅威だけ補正する。
#   1072 フーディン「パワフルハンド」= 手札1枚につきダメカン2個 = 手札×20
_VARIABLE_FIX = {
    1072: lambda atk, atk_side, def_side: (atk_side.handCount or 0) * 20,
}


def _incoming_damage(op, target, include_bench=True, me=None) -> int:
    """相手が次の番に target へ与えうる**最大ダメージ**の見積もり。

    バトル場のポケモンだけでなく、ベンチから入れ替えて出てくる可能性のある
    ポケモンのワザも含める(ユーザー要望)。エネルギーが足りていて実際に
    撃てるワザだけを数える。可変ダメージは gh._attack_damage が盤面から概算する。
    """
    if target is None:
        return 0
    cands = [c for c in (op.active or []) if c is not None]
    if include_bench:
        cands += [c for c in (op.bench or []) if c is not None]
    best = 0
    for atk in cands:
        d = gh._CARD.get(atk.id)
        if d is None:
            continue
        have = list(atk.energies or [])
        for aid in (d.attacks or []):
            at = gh._ATTACK.get(aid)
            if at is None:
                continue
            # コストを払えないワザは撃てない(ベンチから出てくる場合も同様)
            if not gh._can_pay(at.energies or [], have):
                continue
            # ★可変ダメージ(フーディンの「手札枚数×20」等)を正しく見積もるため、
            #   _attack_damage の (me, op) は **攻撃側=相手, 防御側=自分** で渡す。
            #   ここを None にしていると可変技が 0 と評価され、予測が破綻する。
            dmg = gh._attack_damage(aid, atk, target, op, me)
            # generic 側の _ATK_VARIABLE には「ダメカンN個」表記の可変技が
            # 登録されておらず(例: フーディンのパワフルハンドは手札1枚につき
            # ダメカン2個=×20 なのに 1 と評価される)、予測が壊れる。
            # 主要な脅威だけ自前で補正する。
            fix = _VARIABLE_FIX.get(aid)
            if fix is not None:
                dmg = max(dmg, fix(atk, op, me))
            if dmg > best:
                best = dmg
    return best


def _is_dark_from_deck(o, obs, me) -> bool:
    """この選択肢が「山札の基本【悪】エネルギー」か(パンクアップの配分候補)。"""
    if o.type != OptionType.CARD or o.area != AreaType.DECK:
        return False
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    return c is not None and c.id == DARK_ENERGY


def _can_progress(p, me) -> bool:
    """このターン、盤面を実質的に前進させられるか。

    「悪エネを1枚張る」だけは進展に数えない(それしか無い局面ではリーリエで
    引き直した方が良い)。進化・展開・サーチができるかを見る。
    """
    hc = p.hand_counts
    # 進化できる
    if p.field_counts.get(IMPIDIMP) and (hc.get(MORGREM) or p.can_candy):
        return True
    if p.field_counts.get(MORGREM) and hc.get(GRIMMSNARL_EX):
        return True
    if p.field_counts.get(SNORUNT) and hc.get(FROSLASS):
        return True
    # 展開・サーチができる
    for cid in (POFFIN, POKE_PAD, DAWN, RARE_CANDY, NIGHT_STRETCHER,
                ROCKET_LAMBDA, POKEGEAR, BOSS_ORDERS):
        if hc.get(cid):
            return True
    # ベンチにたねを出せる
    if p.bench_free > 0 and (hc.get(IMPIDIMP) or hc.get(MUNKIDORI)
                             or hc.get(SNORUNT)):
        return True
    return False


def _has_pending_setup_gr(p: Plan, me, state) -> bool:
    """攻撃する前に済ませておくべき準備が残っているか(オーロンゲ版)。

    攻撃はターンを終わらせるので、以下が残っているなら先にやる:
      - 手札のオーロンゲex/ギモーで場のポケモンを進化できる(パンクアップも乗る)
      - このターンまだエネを付けておらず、悪エネがあり足りない主砲がいる
      - マシマシラの特性(アドレナブレイン)が使えて移せるダメージがある
    """
    hc = p.hand_counts
    # 1) 進化(オーロンゲexの進化はパンクアップの起動条件でもある)
    if hc.get(GRIMMSNARL_EX) and (p.field_counts.get(MORGREM) or p.can_candy):
        return True
    if hc.get(MORGREM) and p.field_counts.get(IMPIDIMP):
        return True
    # 2) エネ付け: まだ付けておらず、悪エネがあり2個未満の主砲がいる
    if not state.energyAttached and hc.get(DARK_ENERGY):
        for c in ([x for x in (me.active or []) if x]
                  + [x for x in (me.bench or []) if x]):
            if c.id in (GRIMMSNARL_EX, MORGREM) and len(c.energies or []) < 2:
                return True
            if c.id == MUNKIDORI and not (c.energyCards or []):
                return True      # マシマシラの起動(回復エンジン)
    # 3) ベンチに空きがあり、手札にたねポケモンがいる(2026-07-27 ユーザー指摘)
    #    実測で攻撃176回のうち44回(25%)は、たねを出せるのに出さずに殴っていた。
    #    ベロバーは進化の起点、マシマシラは回復エンジン、ユキワラシは氷エンジン。
    #    攻撃はターンを終わらせるので、並べられるなら先に並べる。
    if p.bench_free > 0:
        for cid in (IMPIDIMP, MUNKIDORI, SNORUNT):
            if hc.get(cid):
                return True
    # 4) マシマシラの特性が使えて、移せるダメージがある
    if _total_movable_damage(me) > 0:
        for area, cards in ((AreaType.ACTIVE, me.active or []),
                            (AreaType.BENCH, me.bench or [])):
            for i, c in enumerate(cards):
                if c is None or c.id != MUNKIDORI:
                    continue
                if (area, i) in _used_adrena_slots:
                    continue
                if any(e.id == DARK_ENERGY for e in (c.energyCards or [])):
                    return True
    return False


def _movable_damage(me) -> int:
    """アドレナブレインで相手に移せるダメージ量(最大30=ダメカン3個)。

    「自分のポケモン**1体**からダメカンを3個まで移す」ので、
    **バトル場だけでなくベンチも対象**。最も傷んでいる1体から最大30まで移せる。
    ダメカン1個(10ダメージ)でも移す価値がある(自分が10回復し相手に10ダメージ)。
    """
    best = 0
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        mx = getattr(c, "maxHp", None) or c.hp or 0
        dmg = max(0, mx - (c.hp or 0))
        if dmg > best:
            best = dmg
    return min(best, 30)


def _total_movable_damage(me) -> int:
    """このターン**まだ使えるマシマシラ全員**で、合計いくら相手に移せるか。

    ユーザー要望(2026-07-26)の実装。判断材料は2つ:
      (1) 特性が未使用のマシマシラの体数(各1回、1回あたり最大3個=30ダメージ)
      (2) 自分の場にある「移せるダメカン」の総量
    移す元は「自分のポケモン1体から3個まで」なので、1回の上限は
    「その時点で最も傷んでいる個体の傷(最大30)」。複数体で使うなら、
    傷の総量まで運べる。よって
        合計 = min(場の傷の総量, 使えるマシマシラ数 × 30)
    例: マシマシラ2体が未使用で場の傷が60以上あれば **60まで移せる**。
        傷が40しかなければ 40 が上限。
    """
    # 特性を使える(=悪エネが付いている)マシマシラの体数。
    # ★このターン既に使った個体も数える: 移し先を選ぶ瞬間には使用済みとして
    #   記録されているため、除外すると常に0になってしまう。
    #   「今このターンに合計いくら運べるか」を見たいので、
    #   未使用の体数 + 今まさに使っている1体、という数え方にする。
    n_ready = 0
    n_used = 0
    for area, cards in ((AreaType.ACTIVE, me.active or []),
                        (AreaType.BENCH, me.bench or [])):
        for i, c in enumerate(cards):
            if c is None or c.id != MUNKIDORI:
                continue
            # 悪エネが付いていないと特性を使えない
            if not any(e.id == DARK_ENERGY for e in (c.energyCards or [])):
                continue
            if (area, i) in _used_adrena_slots:
                n_used += 1
            else:
                n_ready += 1
    # 今まさに使っている1体分は使用済みに入っているので、最低1回分は数える
    n_total = n_ready + (1 if n_used > 0 else 0)
    if n_total == 0:
        return 0
    n_ready = n_total
    total_dmg = 0
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        mx = getattr(c, "maxHp", None) or c.hp or 0
        total_dmg += max(0, mx - (c.hp or 0))
    # ★注意: 移し先を選ぶ瞬間(ctx=13)には、移動元から既にダメカンが外れている
    #   ことがあり、場の傷を数えると 0 になる。その場合は「1回分=30」を下限として
    #   扱う(特性を使う判断自体は済んでいるので、少なくとも1回分は移せる)。
    if total_dmg == 0:
        return min(30, n_ready * 30)
    return min(total_dmg, n_ready * 30)


def _dark_energy_need(plan, me) -> int:
    """パンクアップで山札から取るべき悪エネの枚数。

    デッキの悪エネは10枚しかなく、出所は山札。取りすぎると
    「パンクアップの対象外」であるマシマシラ(マリィのポケモンではない)に
    手張りする分が枯れる。**攻撃に必要な分だけ**取る。
      オーロンゲex : シャドーバレット[悪,悪] = 2個で十分(3個目以降は無価値)
      ギモー       : コークスクリューパンチ[悪,悪] = 2個(繋ぎ)

    実測(強い相手4種・反復6)で取得枚数の方針を比較:
      上限5枚 36.6%±1.3 / マリィ全体の必要数 40.5%±1.1 / **常に2枚 44.5%±1.8**
    → 取りすぎは明確に損。オーロンゲが撃つのに要る2個だけ取り、
      残りは山札に置いてドローで手札に来る確率を上げる方が強い。
      (実測: マシマシラが0エネの592局面のうち **474回=80%は手札に悪エネが無い**
       状態だった。パンクアップで山札から抜くほどこの状況が悪化する)
    """
    # 場のマリィのポケモンで「2個に達していない個体」の不足分を合計する。
    # (ユーザー指摘: オーロンゲが2体いてどちらも2個未満なら、両方を撃てるように
    #  したい。逆に既に2個ある個体には配分しない=不足分に数えない)
    need = 0
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        if c.id in (GRIMMSNARL_EX, MORGREM):
            need += max(0, 2 - len(c.energies or []))
        elif c.id == IMPIDIMP:
            # ベロバーは進化後に引き継ぐので1個までは前借りして良い
            need += max(0, 1 - len(c.energies or []))
    if need > 0:
        return min(need, 5)
    # ★不足が無いなら**取らない**(2026-07-26 実測で発覚)
    # 「場にオーロンゲ1体・既に2個」の状態でも2枚取って3個目4個目を付けており、
    # 山札の悪エネ(デッキに10枚)を完全に無駄にしていた。
    # 呼び出し側は max(1,...) を掛けないので 0 を返せば1枚も取らない。
    return 0


def _is_pickable_from_deck(o, obs, me) -> bool:
    """山札から複数枚まとめて取って良い選択肢か(悪エネ / このデッキで使うポケモン)。

    パンクアップの悪エネと、なかよしポフィンのたねが対象。
    どちらも「上限まで取るほど得」なので、取り漏らしを防ぐために使う。
    """
    if o.type != OptionType.CARD or o.area != AreaType.DECK:
        return False
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    if c.id == DARK_ENERGY:
        return True
    return c.id in MARNIE_LINE or c.id in FROSLASS_LINE or c.id == MUNKIDORI


def _is_basic_pokemon_option(o, obs, me) -> bool:
    """その選択肢が「たねポケモン」か(ベンチ空き枠で上限を絞るため)。"""
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    d = gh._CARD.get(c.id)
    return bool(d) and d.basic and d.cardType == 0


def _counts(cards):
    d = {}
    for c in cards or []:
        if c is not None:
            d[c.id] = d.get(c.id, 0) + 1
    return d


def _is_grass(pk) -> bool:
    d = gh._CARD.get(pk.id) if pk else None
    return bool(d) and d.energyType == GRASS


def _has_ability(pk) -> bool:
    d = gh._CARD.get(pk.id) if pk else None
    return bool(d) and bool(getattr(d, "skills", None))


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
    p.gx_ready = (p.active_id == GRIMMSNARL_EX
                  and len(p.active.energies or []) >= 2)
    p.froslass_in_play = p.field_counts.get(FROSLASS, 0)
    p.snorunt_in_play = p.field_counts.get(SNORUNT, 0)

    p.can_candy = bool(p.hand_counts.get(RARE_CANDY)
                       and p.hand_counts.get(GRIMMSNARL_EX)
                       and p.field_counts.get(IMPIDIMP))

    op_all = [c for c in (op.active or []) if c] + [c for c in (op.bench or []) if c]
    p.op_active = op.active[0] if op.active else None
    p.op_grass = _is_grass(p.op_active)

    # バトル場のHP残存率と、ベンチに元気なオーロンゲexがいるか。
    # 上位(Luca)の実測: 傷んで逃げた16件のうち**14件がオーロンゲexで、HP残存率53%**。
    # 倒される前に下げ、ベンチの元気なオーロンゲ(3枚積みなので複数体いる)を前に出し、
    # 下がったオーロンゲはマシマシラの特性(1.17回/試合)でダメカンを相手に移して回復する。
    p.active_hp_ratio = 1.0
    if p.active is not None:
        mx = getattr(p.active, "maxHp", None) or p.active.hp or 1
        p.active_hp_ratio = (p.active.hp or 0) / mx
    p.bench_fresh_gx = any(
        b is not None and b.id == GRIMMSNARL_EX
        and (b.hp or 0) >= (getattr(b, "maxHp", None) or b.hp or 1) * 0.9
        for b in (me.bench or []))

    # 次の番に相手から飛んでくる最大ダメージ(ベンチから出てくる相手も含む)。
    # これで「今のバトル場は次のターンに落ちるか」を判定して退避を決める。
    # 相手にイワパレス系がいるか(exのワザを無効化されるので進化を止める判断に使う)
    p.op_crustle = any(c.id in CRUSTLE_LINE for c in op_all)

    p.incoming = _incoming_damage(op, p.active, me=me)
    p.will_be_koed = (p.active is not None and p.incoming >= (p.active.hp or 0))
    p.op_ability_count = sum(1 for c in op_all if _has_ability(c))

    try:
        p.stadium_ours = bool(state.stadium) and state.stadium[0].id == SPIKEMUTH_GYM
    except (IndexError, AttributeError, TypeError):
        p.stadium_ours = False

    # ボスで引きずり出す相手。上位(Luca)の実測(選んだ36体 vs 見送り148体):
    #   特性持ち 69% vs 52% / ex 53% vs 42% / **HP 121 vs 120(差なし)**
    # → 「特性持ちのエンジン」と「ex」を優先し、HPの低さは基準にしない。
    #   ただし今の打点(シャドーバレット180)で倒し切れるなら、それが最優先。
    best = (-1, -1e9)
    for i, b in enumerate(op.bench or []):
        if b is None:
            continue
        d = gh._CARD.get(b.id)
        sc = 0.0
        if _is_grass(b):
            sc += 100.0                       # 弱点を突ける相手
        if USE_BOSS_TARGETING:
            # ★実測(2026-07-26 ユーザー指摘): ex を +90 していたため
            #   **exがベンチにいると必ず引き出していた**(選んだ13% vs 見送り0%)。
            #   倒し切れないexを前に出すのは、相手に殴る準備が整った状態を渡すだけで
            #   完全に逆効果。**倒せるかどうか**を最優先の基準にする。
            # ★「倒せる相手の中で最も強い相手」を選ぶ(2026-07-26 ユーザー指摘)
            # 倒しきれない相手(育成中/育ちきったポケモン)を引き出すと返り討ちに
            # 合うので**倒せる相手に限る**。その中では「サイドが多く、HPが高い
            # (=育っている)」相手を優先する(従来は -hp/20 で弱い方を選んでいた)。
            # 「倒せる」は自分が実際に殴れる場合のみ有効(前がオーロンゲでエネ2個。
            # イワパレス相手は ex のワザが通らないので殴れない扱い)。
            can_hit = p.gx_ready and not p.op_crustle
            killable = can_hit and b.hp <= 180
            is_ex = bool(d is not None and (d.ex or d.megaEx))
            if not killable:
                # 倒せない相手は引き出さない(exなら特に危険)
                sc -= 2000.0 if is_ex else 1000.0
            else:
                pz = (3 if d and d.megaEx else 2 if d and d.ex else 1)
                sc += pz * 1000.0 + (b.hp or 0)   # 強い相手ほど良い
            if getattr(d, "skills", None):
                sc += 300.0                   # 特性持ち = 相手のエンジンを止める
        else:
            if d is not None:
                sc += (3 if d.megaEx else 2 if d.ex else 1) * 20
            if b.hp <= 180:
                sc += 50.0
            sc -= b.hp / 40.0
        if sc > best[1]:
            best = (i + 1, sc)
    p.boss_target = best[0]
    return p


# ---------------------------------------------------------------- スコアリング
def _bonus(o, obs: Observation, state, me, op, p: Plan, ctx=None) -> float:
    t = o.type

    # ---- ワザ ----
    # 攻撃はターンを終わらせる。1位(Luca)のリプレイ分析では、MAINでの攻撃は
    # わずか9%で、エネ付け(35%)・進化(10%)・特性(6%)で盤面を作り切ってから殴る。
    # こちらは攻撃49%と殴りすぎだった。そこで「KOできるなら即・できないなら
    # セットアップを全部終えてから」に変える。非KO時は攻撃を低く置き、
    # 有益なセットアップ(エネ付け/進化/特性/良いプレイ)を先に通す。
    if t == OptionType.ATTACK:
        # ★攻撃はターンを終わらせるので、**先にやれることを全部やる**
        #   (2026-07-27 ユーザー指摘。ワナイダーと共通の問題)。
        if USE_ACT_BEFORE_ATTACK and _has_pending_setup_gr(p, me, state):
            return -3000.0
        aid = o.attackId
        if aid == ATK_SHADOW_BULLET:
            if not SETUP_BEFORE_ATTACK:
                return 4000.0
            oa = p.op_active
            lethal = oa is not None and oa.hp <= 180
            return 6000.0 if lethal else ATTACK_DEVELOP_SCORE
        if aid == ATK_CORKSCREW_MOR:
            # ★イワパレス相手は ex のワザが通らないので、ギモー(非ex)の60が
            #   唯一の有効打になる。抑制せず積極的に撃つ。
            if USE_HOLD_EVOLVE_VS_CRUSTLE and p.op_crustle:
                return 5000.0
            return 700.0 if not SETUP_BEFORE_ATTACK else min(700.0, ATTACK_DEVELOP_SCORE)
        if aid == ATK_MIND_BEND:
            return 600.0 if not SETUP_BEFORE_ATTACK else min(600.0, ATTACK_DEVELOP_SCORE)
        return -800.0        # 氷ラインのワザ等は撃たない(コストを払えない/低打点)

    # ---- 特性 ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            # ★ABILITY の選択肢は playerIndex=None のことがあり、その場合
            #   gh._get_card は None を返す。すると cid=None でどの分岐にも
            #   入らず `return 0.0` に落ち、**マシマシラの特性スコア(6500)が
            #   一度も適用されていなかった**(実測: bonus=0.0 のまま攻撃10220に負ける)。
            #   area から自分の場を直接引いて補完する。
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    card = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    card = me.bench[o.index or 0]
            except (IndexError, TypeError):
                card = None
        cid = card.id if card else None
        if cid == GRIMMSNARL_EX:
            return 5000.0                 # パンクアップ。最優先
        if cid == MUNKIDORI:
            # ★その個体が使ったかを見る(場に2体いれば2回使える)
            if not USE_ADRENA or (o.area, o.index) in _used_adrena_slots:
                return -2000.0
            # ★攻撃より先に使う(2026-07-26 実戦の観察から発覚)
            # 攻撃(シャドーバレットのKO時=6000)が特性(1900)を上回るため、
            # 「オーロンゲが殴れる状況ではマシマシラの特性を使わずにターンが終わる」
            # 状態だった(実測: 特性が選べた66局面のうち14回は攻撃を優先)。
            # 攻撃はターンを終わらせるので、使える特性は**必ず攻撃の前に**使う。
            # アドレナブレインは自分のダメカンを相手に移すので、
            #   ・自分に移せるダメージがある(damaged>=30) → 回復 + 相手に打点
            #   ・無傷でも相手のHPを削れば、その後の攻撃でKOに届く可能性が上がる
            # いずれも攻撃前に撃って損はない。
            if USE_ADRENA_BEFORE_ATTACK:
                # ★アドレナブレインは「自分のダメカンを相手に移す」特性なので、
                #   移せるダメージが無い状態では**無駄撃ち**(1ターン1回の権利を失う)。
                #   実測: 無傷でも撃つようにしたら使用回数が 20→7回に**減った**
                #   (早い段階で撃って権利を使い切り、必要な時に使えなくなった)。
                #   移せるダメージがあるときだけ、攻撃(KO時6000)より上に置く。
                # ★移せるダメカンが1個でもあれば使う(2026-07-26 ユーザー指摘)
                # アドレナブレインは「自分のポケモン**1体**からダメカンを**3個まで**
                # 相手に移す」。つまり10ダメージ(ダメカン1個)でも移す価値がある
                # (自分が10回復し、相手に10ダメージ)。以前は damaged>=30 に
                # 限定していたため、10/20ダメージの局面で使っていなかった。
                # また移す元は「自分のポケモン」なので**ベンチの傷も対象**。
                # 従来は p.damaged(バトル場のみ)しか見ていなかった。
                movable = _movable_damage(me)
                if movable >= 10:
                    # ★値の根拠(実測): 攻撃の合計は「固有6000 + 汎用 gh._score_option
                    #   4220 = 10220」に達する。特性に6500を付けても
                    #   「6500 + 汎用700 = 7200」で**攻撃に負けていた**。
                    #   攻撃はターンを終わらせるので、先に使える特性は確実に上に置く。
                    return 12000.0
                return 500.0
            return 1900.0 if p.damaged >= 30 else 500.0
        return 0.0

    # ---- 進化 ----
    if t == OptionType.EVOLVE:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        cid = card.id if card else None
        if cid == GRIMMSNARL_EX:
            # ★イワパレス相手はオーロンゲexに進化させない(ユーザー提案)
            # イワパレスの特性で ex のワザは**ダメージ0**にされる。一方
            # ギモー(非ex)のコークスクリューパンチ60は通るので、進化を保留して
            # 殴れるアタッカーを残す方が良い。
            # ただしベンチのギモーを進化させるのは構わない(前で殴る役は残る)ので、
            # 「バトル場のギモーを進化させる」場合だけ止める。
            if (USE_HOLD_EVOLVE_VS_CRUSTLE and p.op_crustle
                    and o.inPlayArea == AreaType.ACTIVE
                    and p.active_id == MORGREM):
                return -3000.0
            return 4500.0                 # 進化がパンクアップの起動条件
        if cid == FROSLASS:
            # 氷エンジンを立てる。1体で十分。相手に特性ポケが多いほど価値が高い。
            if not USE_FROSLASS_ENGINE or p.froslass_in_play >= 1:
                return 200.0
            # ★実戦の悪手: バトル場のユキワラシをユキメノコに進化させると、
            #   攻撃できない氷エンジンがバトル場を塞ぐ。ベンチのユキワラシだけ進化。
            if FIX_ICE_POSITION and o.inPlayArea == AreaType.ACTIVE:
                return -2000.0
            # コアのテンポと競合させない: オーロンゲexが立ってから、
            # かつ相手に特性ポケが複数いるときだけ立てる(高速相手には無駄になる)。
            if FROSLASS_AFTER_CORE and (p.gx_in_play == 0
                                        or p.op_ability_count < 2):
                return 100.0
            return 1600.0 + p.op_ability_count * 150.0
        if cid == MORGREM:
            if USE_EVOLVE_RUSH and p.can_candy:
                return -500.0             # アメでオーロンゲexに飛ぶ方が速い
            return 1400.0
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

        if dest_id == MUNKIDORI and USE_MUNKI_FIRST and n == 0:
            # ★上位はマシマシラを最初にエネ起動する(実測: 最初のエネ付け先として
            #   12回=最多タイ、到達は平均3.0ターン/中央2)。回復エンジンを最速で
            #   立てておくと、傷んだオーロンゲを下げて回復する動きが回る。
            #   オーロンゲexは特性パンクアップ(進化時に山札から悪エネ最大5枚)で
            #   自力で乗るので、手張りはマシマシラに回した方が効率が良い。
            return 2400.0
        if dest_id == GRIMMSNARL_EX:
            return 2200.0 if n < 2 else 200.0
        if dest_id == MUNKIDORI:
            # パンクアップ対象外なので手張りでアドレナブレインを起動
            return 1600.0 if n == 0 else 100.0
        if dest_id in (IMPIDIMP, MORGREM):
            return 900.0
        # 氷ラインに悪エネを付けても撃てないので無駄
        if dest_id in FROSLASS_LINE:
            return -1500.0
        return 200.0

    # ---- 手札からのプレイ ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None

        if cid == RARE_CANDY:
            if USE_EVOLVE_RUSH and p.can_candy:
                return 3800.0
            return -1000.0
        if cid == GRIMMSNARL_EX:
            return 2500.0
        if cid == SPIKEMUTH_GYM:
            if USE_STADIUM_CARE and p.stadium_ours:
                return -2000.0
            return 2000.0
        if cid == ROCKET_LAMBDA:
            # トレーナーズサーチ。序盤ほど価値が高い(アメ/ポフィン/ジムを集める)。
            if USE_SEARCH_ENGINE:
                return 2300.0 if p.gx_in_play == 0 else 1400.0
            return 800.0
        if cid == DAWN:
            # ★ヒカリは「たね/1進化/2進化を1枚ずつ手札に加える」。
            #   盤面は進まず手札が増えるだけなので、**ラインが欠けているときだけ**。
            #   実測(サポートが2種類以上使える726決定): 上位勢2.2%に対しうち9.5%と
            #   4倍使っていた。従来は常に2100点固定だった。
            if USE_DAWN_CARE:
                hc2 = p.hand_counts
                need_gx = (p.gx_in_play == 0 and not hc2.get(GRIMMSNARL_EX)
                           and not p.field_counts.get(MORGREM))
                if not need_gx:
                    return 500.0          # ラインは足りている
            return 2100.0                 # ライン一式
        if cid == POFFIN:
            # HP70以下のたね = ベロバー / ユキワラシ
            need_impidimp = p.field_counts.get(IMPIDIMP, 0) < 2
            need_snorunt = (USE_FROSLASS_ENGINE and p.froslass_in_play == 0
                            and p.snorunt_in_play == 0)
            if p.bench_free >= 2 and (need_impidimp or need_snorunt):
                return 2000.0
            return 300.0
        if cid == POKE_PAD:
            return 1300.0
        if cid == NIGHT_STRETCHER:
            # トラッシュから回収。オーロンゲexや悪エネが落ちている中盤以降に効く。
            if USE_SEARCH_ENGINE:
                return 1200.0 if state.turn >= 3 else 400.0
            return 400.0
        if cid == POKEGEAR:
            return 1100.0                 # サポートサーチ
        if cid == BOSS_ORDERS:
            # ★ボスの指令は**サポート枠(1ターン1枚)**を使う。引きずり出しても
            #   そのターンに倒せないなら、リーリエ等に枠を譲るべき
            #   (2026-07-28。実測でサポート2種以上の決定のうち
            #    上位勢5.9%に対しうち15.1%と使いすぎだった)。
            if USE_BOSS_NEEDS_ATTACK and not p.gx_ready:
                return 300.0
            # ★サポート枠はリーリエと奪い合う。上位勢の比率は
            #   リーリエ14.8% : ボス5.5% = 約2.7:1 なのに、うちは 9.6% : 10.8% と
            #   ほぼ互角だった。リーリエ(通常1600)に譲る水準まで下げる。
            return BOSS_ORDERS_SCORE if p.boss_target > 0 else 300.0
        if cid == LILLIE:
            hand = len(me.hand) if me.hand is not None else me.handCount
            # ★実戦の観察(2026-07-26): 手札が「リーリエ2枚 + ユキメノコ2枚」だけで
            #   盤面がベロバー3体(=進化先が無く手詰まり)なのに、手札4枚だったため
            #   `hand<=3` の条件を満たさず**使わずにターンエンド**していた。
            #   リーリエは手札をシャッフルして6枚(サイド6なら8枚)引き直す札なので、
            #   **手札が「今使えないカード」ばかりなら枚数に関わらず切るべき**。
            if USE_LILLIE_DEADHAND:
                # ★「オーロンゲexを完成させられそうか」で判断する(ユーザー要望)
                # このデッキの勝ち筋はオーロンゲexを立てて殴ること。その道筋が
                # 見えていないなら、手札を6枚(サイド6なら8枚)引き直した方が良い。
                #
                # 以前の実装は「手札に使えるカードが1枚でもあれば使わない」と
                # 緩すぎた(悪エネはデッキに10枚あるのでほぼ常に該当し、実測で
                # 使用0.50回/試合。**手札5枚で他に何もできず最高スコア10=END
                # の局面でも使っていなかった**)。
                hc = p.hand_counts
                # 既にオーロンゲexが場にいるなら、勝ち筋は立っている
                if p.gx_in_play == 0:
                    # このターン、または次のターンにオーロンゲexへ到達できるか
                    reachable = False
                    # 手札のオーロンゲ + (場のギモー or 場のベロバー+アメ)
                    if hc.get(GRIMMSNARL_EX) and (p.field_counts.get(MORGREM)
                                                  or p.can_candy):
                        reachable = True
                    # 手札のギモー + 場のベロバー → 次のターンにオーロンゲ
                    if hc.get(MORGREM) and p.field_counts.get(IMPIDIMP) \
                            and hc.get(GRIMMSNARL_EX):
                        reachable = True
                    # サーチ札で部品を集められる(ラムダ/ヒカリ/ポケパッド/ジム/タンカ)
                    for cid2 in (ROCKET_LAMBDA, DAWN, POKE_PAD, NIGHT_STRETCHER,
                                 POKEGEAR):
                        if hc.get(cid2):
                            reachable = True
                    if not reachable:
                        # オーロンゲに届く道筋が無い = 引き直す
                        return 2600.0
                # 手詰まり(このターン何もできない)なら枚数に関わらず引き直す
                if not _can_progress(p, me):
                    return 2600.0
                # ★以下、ユーザー指定の追加条件(2026-07-27)
                n_energy_hand = hc.get(DARK_ENERGY, 0)
                n_pokemon_hand = sum(
                    v for k, v in hc.items()
                    if (gh._CARD.get(k) is not None
                        and gh._CARD[k].cardType == 0))
                field_energy = sum(
                    len(c.energies or [])
                    for c in ([x for x in (me.active or []) if x]
                              + [x for x in (me.bench or []) if x]))
                # (1) 手札のエネが2枚以下 かつ ポケモンが1枚も無い(トレーナーだけ)
                if n_energy_hand <= 2 and n_pokemon_hand == 0:
                    return 2700.0
                # (2) 場のポケモンにエネがあまり付いていない
                #     (オーロンゲ/ギモーが2個に達しておらず、手札にもエネが無い)
                ready = any(
                    c.id in (GRIMMSNARL_EX, MORGREM) and len(c.energies or []) >= 2
                    for c in ([x for x in (me.active or []) if x]
                              + [x for x in (me.bench or []) if x]))
                if not ready and field_energy <= 1 and n_energy_hand == 0:
                    return 2650.0
            # ★サイドがちょうど6枚なら **6枚でなく8枚**引ける(カードテキスト)。
            #   上位勢のリーリエ使用の**65%がサイド6の局面**だった(実測360局面)。
            #   手札枚数も 使った4.5 / 使わなかった6.3 と明確に分かれる
            #   (手札は山札に戻るので、大きい手札で使うほど損)。
            #   従来は `hand <= 3` でしか使わず、上位勢13.8%に対しうち8.4%だった。
            if USE_LILLIE_PRIZE6:
                my_prize = len(me.prize) if me.prize is not None else 6
                if my_prize >= 6 and hand <= LILLIE_HAND_MAX_P6:
                    return 2400.0       # 8枚ドロー。序盤の展開の起点
                if hand <= LILLIE_HAND_MAX:
                    return 1600.0
                return -900.0
            return 1600.0 if hand <= 3 else -900.0
        if cid == UNFAIR_STAMP:
            # ACE SPEC。手札が細ったときの立て直し(使用条件はエンジン側が判定)。
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1700.0 if hand <= 2 else -500.0
        if cid == TOOL_SCRAPPER:
            return 500.0
        if cid == IMPIDIMP:
            return 1800.0
        if cid == SNORUNT:
            if not USE_FROSLASS_ENGINE or p.froslass_in_play:
                return 200.0
            # 氷を立てる条件を満たすときだけ進化元を用意する
            if FROSLASS_AFTER_CORE and (p.gx_in_play == 0
                                        or p.op_ability_count < 2):
                return 200.0
            return 1100.0
        if cid == MUNKIDORI:
            return 1000.0
        return 0.0

    # ---- 選択(サーチ先・ボス対象など) ----
    if t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        if o.playerIndex is not None and o.playerIndex != state.yourIndex:
            # ★相手の場から1体を選ぶ場面は用途が2つあり、**context で分離**する
            #   (2026-07-26: 同じ分岐に混在していて、ボス側の return が先に働き
            #    マシマシラの移し先ロジックに到達していなかった)。
            #     SelectContext.DAMAGE_COUNTER(13) … アドレナブレインの移し先
            #     それ以外(TO_ACTIVE/SWITCH等)     … ボスの指令で引き出す相手
            if ctx == SelectContext.DAMAGE_COUNTER:
                if USE_ADRENA_TARGETING:
                    # ★「このターン合計いくら移せるか」で判断する(ユーザー要望)
                    #   movable = min(場の傷の総量, 未使用マシマシラ数 × 30)
                    #   例: マシマシラ2体が使えて傷が60以上 → 60 移せる。
                    #       傷が40しかなければ 40。
                    #   優先順位:
                    #     1. その合計で**倒せる相手**(hp <= movable)
                    #     2. オーロンゲが撃てるなら「180 + movable」でKO圏に入る相手
                    #        (例: movable=60 なら HP180〜240 が対象)
                    #   ※ 基準値は下げない(下げると特性自体が選ばれにくくなり、
                    #     使用が 67→28回に減って勝率が落ちた実測がある)。
                    hp = card.hp or 0
                    d = gh._CARD.get(card.id)
                    pz = (3 if d and d.megaEx else 2 if d and d.ex else 1)
                    # 合計移動量(未使用マシマシラの体数×30 と 場の傷の総量の小さい方)。
                    # エネが付いていない=特性を使えないマシマシラは数えないので、
                    # ここが0なら実際に移せない(_movable_damage はエネを見ないため
                    # 併用しない)。
                    movable = _total_movable_damage(me)
                    sc = 1500.0
                    if movable > 0 and hp <= movable:
                        # ダメカンだけで倒せる = 最善(サイドが多い相手ほど良い)
                        sc += 2000.0 + pz * 300.0
                    elif p.gx_ready and hp <= 180 + movable:
                        # オーロンゲのワザ(180)と合わせてKOできる圏内。
                        # 必要な移動量が少ないほど確実なので、余裕がある方を優先。
                        need = max(0, hp - 180)
                        sc += 900.0 + (movable - need) * 5.0 + pz * 200.0
                    if USE_ENGINE_DENIAL and card.id == MUNKIDORI:
                        # 相手のマシマシラは「傷を全部こちらに押し返す」エンジン。
                        # HP110で落としやすく、落とせば相手の回復手段が消える。
                        sc += 700.0
                    sc -= hp / 4.0        # 同条件ならHPが低い方を削る
                    return sc
                return 0.0

            # ★シャドーバレットの「相手ベンチへの30ダメージ」の対象(ctx=15)。
            # 以前はここに来ず下のボス用分岐に落ちていたため、
            # 「180で倒せない相手は -1500」で候補が同点になり選択が壊れていた。
            if USE_BENCH_DAMAGE_TARGET and ctx == SelectContext.DAMAGE:
                cur_hp = card.hp or 0
                d3 = gh._CARD.get(card.id)
                mx3 = getattr(card, "maxHp", None) or cur_hp or 1
                pz3 = (3 if d3 and d3.megaEx else 2 if d3 and d3.ex else 1)
                sc3 = 1000.0
                if cur_hp <= 30:
                    # 30で落ちる = サイドが進む。最優先。
                    sc3 += 3000.0 + pz3 * 400.0
                else:
                    # 落ちないなら「30がHPに占める割合」が効く。
                    # HP320のオーロンゲexに30撒くのは9%で、ほぼ無駄。
                    sc3 += 1200.0 * min(30, cur_hp) / mx3
                    if USE_ENGINE_DENIAL and card.id == MUNKIDORI:
                        sc3 += 600.0
                    if d3 is not None and getattr(d3, "basic", False) and not (
                            d3.ex or d3.megaEx):
                        # 進化前のたね(インプ・ユキワラシ等)は今のうちに削ると
                        # 進化後の主砲を1回ぶん減らせる。
                        sc3 += 400.0
                return sc3

            # ボスの指令で引き出す相手。**その候補を直接評価**する
            # (boss_target のベンチ位置と選択肢indexの対応がずれることがある)。
            # 方針: 「倒せる相手に限り、その中で最も強い(サイド多い>HP高い)」。
            # 倒しきれない相手を引き出すと返り討ちに合う。
            if USE_BOSS_TARGETING:
                d2 = gh._CARD.get(card.id)
                hp2 = card.hp or 0
                can_hit2 = p.gx_ready and not p.op_crustle
                pz2 = (3 if d2 and d2.megaEx else 2 if d2 and d2.ex else 1)
                if not (can_hit2 and hp2 <= 180):
                    # ★倒せない相手でも**順位は付ける**(2026-07-28)。
                    #   従来は一律 -1500 で全候補が同点になり、
                    #   撃てないターン(gx_ready=False)には
                    #   **HP320のオーロンゲexやメガガルーラexを引きずり出していた**。
                    #   大きいexを前に出すと殴り返されるだけなので最悪。
                    #   実測: 倒せる中で最強を選べたのは48%(ルーティング修正後68%)。
                    sc0 = -1500.0 - pz2 * 200.0 - hp2 / 2.0
                    if USE_ENGINE_DENIAL and card.id == MUNKIDORI:
                        # 相手のマシマシラは「傷を押し返す」エンジン。
                        # 前に出せば殴って落とせる可能性が高く、特性も止まる。
                        sc0 += 2000.0
                    return sc0
                sc2 = 1500.0 + pz2 * 1000.0 + hp2
                if getattr(d2, "skills", None):
                    sc2 += 300.0
                if USE_ENGINE_DENIAL and card.id == MUNKIDORI:
                    # ★上位勢が引きずり出す相手は圧倒的にマシマシラだった
                    #   (実測28回中21回)。エンジンを止められる。
                    sc2 += 800.0
                return sc2
            if p.boss_target > 0 and o.index == p.boss_target - 1:
                return 1500.0
            if p.boss_target > 0 and o.index == p.boss_target - 1:
                return 1500.0
            return 0.0

        # ★アドレナブレインの「移動元」選択(2026-07-26 ユーザー指摘)
        # 「自分のポケモン1体から」ダメカンを移すので、どの1体から取るかを選ぶ
        # 場面(ctx=16)がある。実測で**選択肢が2〜3個出るケースが15回あり、
        # オーロンゲexが候補にいるのにマシマシラから取っていた例が8件**あった
        # (例: オーロンゲex HP250 と マシマシラ HP50 → マシマシラを選択)。
        # オーロンゲexは倒されるとサイド2枚を渡す主砲なので、**優先して救う**。
        if USE_ADRENA_SOURCE and o.area in (AreaType.ACTIVE, AreaType.BENCH):
            src = None
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    src = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    src = me.bench[o.index or 0]
            except (IndexError, TypeError):
                src = None
            if src is not None:
                mx = getattr(src, "maxHp", None) or src.hp or 1
                dmg = max(0, mx - (src.hp or 0))
                if dmg > 0:
                    removable = min(dmg, 30)
                    sc = 500.0 + removable * 5.0
                    # ★「剥がすと生存閾値を超える」候補を最優先にする
                    #   (2026-07-28 ユーザー提案 → 上位勢のリプレイで裏付け)。
                    #   シャドーバレットは バトル場180 + 相手ベンチ1体に30 なので、
                    #     バトル場: 残りHPが180以下だと次の一撃で落ちる
                    #     ベンチ  : 残りHPが30以下だと狙撃で落ちる
                    #   ダメカンを移せる量は移動元が誰でも同じなので、
                    #   **その30で生死が変わる個体から剥がす**のが最大の得。
                    #   実測(Dominic Peel 40試合): 閾値をまたげる候補がある場面で
                    #   **91%(60/66)でその候補を選んでいた**。
                    #   「傷が最多」(54%)や「マシマシラ」(59%)より強い予測因子。
                    #   うちは同じ場面で63%しか選べていなかった。
                    if USE_ADRENA_SURVIVAL_THRESHOLD:
                        hp_now = src.hp or 0
                        thr = (SHADOW_BULLET_ACTIVE if o.area == AreaType.ACTIVE
                               else SHADOW_BULLET_BENCH)
                        if hp_now <= thr < hp_now + removable:
                            sc += 4000.0      # 生死が変わる。最優先
                    if USE_ADRENA_SOURCE_FRAGILE:
                        # ★相手に移る量は移動元が誰でも同じ(最大3個)なので、
                        #   移動元の選択は**自分側の延命**だけの問題。
                        #   「剥がせる量が最大HPに占める割合」が生存への寄与。
                        #   マシマシラHP110なら30で27%、オーロンゲexHP320なら9%。
                        sc += 1800.0 * removable / mx
                        if src.id == MUNKIDORI:
                            # 特性エンジン本体。フロストラスで毎ターン自傷するので
                            # 放置すると勝手に落ちる。
                            sc += 700.0
                        elif src.id == GRIMMSNARL_EX and (src.hp or 0) <= 120:
                            # 主砲が本当に落ちる寸前のときだけ優先を戻す
                            sc += 900.0
                        elif src.id == MORGREM:
                            sc += 200.0
                    else:
                        if src.id == GRIMMSNARL_EX:
                            sc += 2000.0
                            if (src.hp or 0) <= 180:
                                sc += 800.0
                        elif src.id == MORGREM:
                            sc += 300.0
                    return sc

        # ★パンクアップの配分先選択(2026-07-26 ユーザー指摘)
        # 配分は「場のマリィのポケモンから1体選ぶ」を1枚ずつ繰り返す形式(ctx=21)。
        # 下のスコアは「カードの種類」だけを見ていたため、オーロンゲなら常に1200点で
        # **2体いても同じ個体に集中し、既に2個持っている個体にも付け続けていた**。
        # シャドーバレットは悪2個で撃てるので3個目以降は無駄。
        # 「まだ2個に達していない個体」を優先し、足りている個体は避ける。
        if USE_ENERGY_SPREAD and o.area in (AreaType.ACTIVE, AreaType.BENCH):
            target = None
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    target = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    target = me.bench[o.index or 0]
            except (IndexError, TypeError):
                target = None
            if target is not None and target.id in MARNIE_LINE:
                have = len(target.energies or [])
                if have >= 2:
                    return -1500.0        # もう撃てる。ここに足すのは無駄
                # 足りない個体を優先。バトル場(すぐ撃てる)を最優先、
                # 次に進化済み(オーロンゲ/ギモー)、最後にベロバー。
                score = 1400.0 - have * 300.0
                if o.area == AreaType.ACTIVE:
                    score += 400.0
                if target.id == GRIMMSNARL_EX:
                    score += 300.0
                elif target.id == MORGREM:
                    score += 100.0
                return score

        # 自分側サーチ先の優先度
        if card.id == GRIMMSNARL_EX:
            return 1200.0
        if card.id == RARE_CANDY:
            return 1100.0
        if card.id == IMPIDIMP:
            return 1000.0
        if card.id == SPIKEMUTH_GYM:
            return 900.0 if not p.stadium_ours else 100.0
        if card.id == DARK_ENERGY:
            return 800.0
        if card.id == POFFIN:
            return 700.0
        if card.id == MORGREM:
            return 500.0
        if card.id == FROSLASS and p.froslass_in_play == 0:
            return 600.0
        return 0.0

    # ---- 逃げる ----
    if t == OptionType.RETREAT:
        # ★実戦の悪手対策: 氷エンジン(ユキワラシ/ユキメノコ)や進化前のたねが
        #   バトル場に居座って攻撃できていない。ベンチに殴れるマリィ系がいるなら
        #   逃げてアタッカーを前に出す。
        # ★上位(Luca)の実測に基づく退避: 傷んだオーロンゲexは、倒されて
        #   サイドを2枚渡す前にベンチへ下げる(実測の逃げはHP残存率53%で発生)。
        #   下げた先はマシマシラの特性でダメカンを相手に移せば回復できる。
        #   ベンチに元気なオーロンゲがいるときだけ(前が空くと本末転倒)。
        # ★次の番の被弾を予測して退避する(相手のバトル場だけでなく、ベンチから
        #   入れ替えて出てくるポケモンのワザも計算に入れる)。
        #   オーロンゲexは倒されるとサイドを2枚渡すので、落ちる前に下げて
        #   ベンチの元気なオーロンゲと交代し、マシマシラでダメカンを移して回復する。
        if (USE_GX_RETREAT and p.active_id == GRIMMSNARL_EX
                and p.will_be_koed and p.bench_fresh_gx):
            return 1800.0
        # 予測が使えない/落ちないときも、大きく傷んでいれば従来どおり下げる
        if (USE_GX_RETREAT and p.active_id == GRIMMSNARL_EX
                and p.active_hp_ratio <= GX_RETREAT_HP and p.bench_fresh_gx):
            return 1500.0
        if USE_GRASS_AWARENESS and p.op_grass and p.active_id == GRIMMSNARL_EX:
            return 700.0
        if p.active_id == GRIMMSNARL_EX:
            return -1000.0
        # ★無意味な逃げの禁止(2026-07-26 実戦の観察から発覚)
        # 「バトル場マシマシラ → ベンチのマシマシラと交代、両方HP満タン」のような
        # 逃げが起きていた。逃げは逃げエネを捨てるので、得になる理由がなければ損。
        # 逃げて良いのは「前がアタッカーでなく、ベンチに殴れるアタッカーがいる」ときだけ。
        if USE_NO_POINTLESS_RETREAT:
            bench_attacker = any(
                b is not None and b.id == GRIMMSNARL_EX
                and len(b.energies or []) >= 2
                for b in (me.bench or []))
            # 同じ種類のポケモンへの入れ替えは無意味(打点も耐久も変わらない)
            same_kind = any(b is not None and b.id == p.active_id
                            for b in (me.bench or []))
            if bench_attacker and p.active_id != GRIMMSNARL_EX:
                return 600.0        # 殴れるオーロンゲを前に出す
            if same_kind or not bench_attacker:
                return -800.0       # 意味のない交代はしない
        return 100.0

    return 0.0


def _placement_bonus(o, obs, state, me, p: Plan) -> float:
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == GRIMMSNARL_EX:
        if USE_GRASS_AWARENESS and p.op_grass:
            return -400.0
        return 1600.0
    if card.id == IMPIDIMP:
        return 800.0
    if card.id == MUNKIDORI:
        return 500.0
    if card.id == SNORUNT:
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
            # ★相手の場から選ぶ選択肢は placement ではなく _bonus に回す
            #   (2026-07-28、ワナイダーで見つかった同じバグがこちらにもあった)。
            #   ボスの指令の「引きずり出す相手」は **ctx=3(SWITCH)** で来るが、
            #   SWITCH は placement に入っており `_placement_bonus` は
            #   相手側の選択肢に一律 0.0 を返す。そのため
            #   **USE_BOSS_TARGETING が一度も適用されていなかった**。
            is_opponent_side = (o.playerIndex is not None
                                and o.playerIndex != state.yourIndex)
            if ctx in placement and not (is_opponent_side
                                         and USE_OPPONENT_SIDE_BONUS_GR):
                extra = _placement_bonus(o, obs, state, me, plan)
            else:
                extra = _bonus(o, obs, state, me, op, plan, ctx)
            scores.append(base + extra)

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # ★リーリエの決心は「やれることを全部やってから」使う(2026-07-28)。
        #   テキストは「手札を**山札に戻して**シャッフル、6枚(サイド6なら8枚)引く」
        #   なので、手札に残したエネもポケモンも消える。
        #   ワナイダーで同じ修正を入れて効果があったものをオーロンゲにも移植。
        #   実測(Dominic Peel、サポートが2種類以上使える726局面):
        #     上位勢は **67.8%でサポートを使わず** 他のことを先にやっていた
        #     (うちは46.3%)。
        #   禁止ではなく後回し(禁止すると使用回数が半減するのを確認済み)。
        if (USE_LILLIE_LAST_GR and ctx == SelectContext.MAIN and select.option):
            top0 = select.option[order[0]]
            is_lillie = False
            if top0.type == OptionType.PLAY:
                hc0 = gh._hand_card(obs, top0.index, me)
                is_lillie = hc0 is not None and hc0.id == LILLIE
            if is_lillie:
                for i in order:
                    o2 = select.option[i]
                    if o2.type in (OptionType.EVOLVE, OptionType.ATTACH,
                                   OptionType.TOOL_CARD, OptionType.ABILITY):
                        pass
                    elif o2.type == OptionType.PLAY:
                        c2 = gh._hand_card(obs, o2.index, me)
                        d2 = gh._CARD.get(c2.id) if c2 is not None else None
                        if d2 is None:
                            continue
                        # たね(ベンチに空きがある)かグッズだけ先に回す。
                        # ※ Plan 変数は `plan`。`p` と書くと NameError が except に
                        #   握りつぶされて修正が丸ごと無効化される(既知の罠)。
                        ok = ((d2.cardType == 0 and d2.basic
                               and plan.bench_free > 0)
                              or d2.cardType == 1)
                        if not ok:
                            continue
                    else:
                        continue
                    if scores[i] >= LILLIE_PREP_MIN_SCORE:
                        order = [i] + [j for j in order if j != i]
                        break

        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                c = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if c is None:
                    # ABILITY は playerIndex=None のことがあり _get_card が None を
                    # 返す。ここで補完しないと使用済みフラグが立たず、同じ個体の
                    # 特性を何度も選び続ける(無限ループ的な浪費)恐れがある。
                    try:
                        if top.area == AreaType.ACTIVE and me.active:
                            c = me.active[top.index or 0]
                        elif top.area == AreaType.BENCH and me.bench:
                            c = me.bench[top.index or 0]
                    except (IndexError, TypeError):
                        c = None
                if c is not None and c.id == MUNKIDORI:
                    # ★個体ごとに記録(場に2体いれば2回使える)
                    _used_adrena_slots.add((top.area, top.index))

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))

        # ★パンクアップの取り漏らし修正(2026-07-26 実戦の観察から発覚)
        # オーロンゲexの特性パンクアップは「山札から基本【悪】エネを**5枚まで**選ぶ」。
        # この選択は minCount=0 / maxCount=5 で来るが、上の k は最小枚数(=1)しか
        # 取らないため、**5枚選べる場面で1枚しか取っていなかった**
        # (実戦で「オーロンゲにエネが1枚しか付いていない」と観察された原因)。
        # 悪エネは多く確保するほど得なので、こういう「多く選べる」場面では上限まで取る。
        # ★同じ取り漏らしは「なかよしポフィン(たね2枚をベンチへ)」でも起きていた
        # (min=0/max=2 なのに1枚しか選ばない。実戦の観察で発覚)。
        # 山札から複数枚選べる場面は、基本的に**上限まで取るのが得**なので一般化する。
        # ただしベンチに出す系は空き枠を超えて取らないよう上限を絞る。
        if USE_PUNK_MAX and hi > k and select.option:
            cand = [i for i in order
                    if _is_pickable_from_deck(select.option[i], obs, me)]
            if len(cand) >= k:
                take = hi
                # ポフィン等「たねをベンチに出す」選択はベンチ空き枠が上限
                if _is_basic_pokemon_option(select.option[cand[0]], obs, me):
                    take = min(take, max(1, plan.bench_free))
                # ★悪エネは「必要な枚数」だけ取る(2026-07-26 ユーザー指摘)
                # パンクアップの出所は**山札**で、デッキの悪エネは10枚しかない。
                # オーロンゲの技(シャドーバレット)は**悪2個で足りる**のに、
                # 上限5枚まで盛ると山札が枯れて、パンクアップの対象外である
                # **マシマシラ(マリィのポケモンではない)に手張りする分が無くなる**。
                # 実測: 1回で平均4.47枚取得、オーロンゲのエネ平均3.43個
                # (2個超の過剰が平均3.24個)、一方でマシマシラは平均0.67個・
                # **33%が0個=特性を起動できていない**状態だった。
                elif _is_dark_from_deck(select.option[cand[0]], obs, me):
                    take = min(take, _dark_energy_need(plan, me))
                # minCount が 0 の場面のみ「0枚」が合法。それ以外は最低 lo 枚返す。
                if take < lo:
                    take = lo
                if take <= 0:
                    return []
                return cand[:take]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
