#!/usr/bin/env python3
"""キュワワー(Comfey)ミル・デッキ専用ヒューリスティック。

## 教材
hikarimaru(882) の実戦 **81試合**(構築は1種のみ)。`analyze_play_rules.py` で
「誰を前に置くか / 各カードをどんな状態で使うか」を逆算した数値をそのまま目標にする。

## 勝ち筋(実測)
勝ち方は サイド取り切り32 / **相手の山札切れ23**(勝ちの42%)。
終局時の山札は 自分17.6 / **相手6.1**。平均16.3ターン。総合勝率68%。

## デッキの正体: 「ex を無効化する殻」+「両者ドロー」
  キュワワー(164, HP70, 超) **フラワーシャワー[超1] = 両者が3枚引く**  ← 本体(5.86回/試合)
    自分のドローは 夜のタンカ4/スイレンのお世話2 で回収して支え、
    相手には クセロシキのたくらみ4(手札を3枚まで捨てさせる) を重ねる。
  ニュートラルセンター(1247, スタジアム)
    **ルールを持たないポケモンは、相手のポケモンex/Vのワザのダメージを受けない**
    → このデッキは**全員ルール無し**なので、ex主体のデッキは一切通らない。
      実測: 対Archaludon 10戦10勝 / 対メガルカリオ 6戦6勝。
  シェイミ(343) 特性フラワーカーテン = 自分のルール無しベンチはダメージを受けない
  アノクサ(817)→アノホラグサ(818) 特性プリズンパニック
    = 手札から進化させたとき**相手のバトル場をこんらん**(進化1.19回/試合)
  クラッシュハンマー4 / 改造ハンマー2 = 相手のエネを割って攻撃自体を遅らせる

## 弱点(実測)
対オーロンゲ 6戦1勝(17%) / 対メガスターミー 2戦0勝。
どちらも**非exの攻撃手段**を持つのでニュートラルセンターが効かない。

## 実測した打ち方(=このファイルの目標値)
  初手のバトル場: キュワワー52% / アノクサ26% / カポエラー12% / シェイミ10%
  バトル場に立つ割合: キュワワー **77.7%**
  ワザ: フラワーシャワー **5.86回/試合**(他はほぼ0)
  エネの付け先: キュワワー(ベンチ2.98 + バトル場1.54) / アノホラグサ0.64
  ハンマーの標的: **相手のバトル場** かつ **エネ1個の個体**を最優先
     (クラッシュ 68回中48回がエネ1個 / 改造 45回中26回)
  カード使用(1試合あたり / 提示に対する採用率):
     キュワワー2.22(74%) / クラッシュハンマー2.02(38%) / クセロシキ1.84(22%)
     夜のタンカ1.78(27%) / ポケパッド1.51(16%) / ポフィン1.48(21%)
     トウコ1.22(9%) / ハンドトリマー0.72(8%・相手の手札中央値11)
     改造ハンマー0.56(44%) / ニュートラルセンター0.52(9%)
     アセロラ0.37(16%・ターン14) / スイレン0.25(4%・ターン14)
     **リーリエ0.68(採用率2%)** ← ドロー札ではなく**山札の回復札**。
       「手札を山に戻して6枚引く」ので山札は (手札-6) 枚**増える**。
       実測の使用時は 手札 中央値10 / 山札 中央値14 で、増減は中央値 +4(73%がプラス)。
       これが「自分の山札切れ負けが81試合中2回だけ」の理由。
"""
import collections

from cg.api import (AreaType, OptionType, SelectContext, to_observation_class)
import generic_heuristic as gh

# ---- ポケモン ----
COMFEY = 164            # HP70 超  フラワーシャワー[超] = 両者3枚ドロー
BRAMBLIN = 817          # HP50 超  → アノホラグサ
BRAMBLEGHAST = 818      # HP100 超 進化時こんらん
SHAYMIN = 343           # HP80 草  特性: ルール無しベンチを守る
HITMONTOP = 972         # HP100 闘 手札を山に戻して6枚引く
POKEMON_IDS = {COMFEY, BRAMBLIN, BRAMBLEGHAST, SHAYMIN, HITMONTOP}
# ベンチにダメカンを置いてくる面々(ワザの効果 or 特性)
#   121 ドラパルトex(ファントムダイブ) / 112 マシマシラ(アドレナブレイン)
#   104 ユキメノコ(こごえるとばり) / 103 ユキワラシ(進化して104になる)
COUNTER_PLACERS = {121, 120, 119, 112, 104, 103}
# ★シェイミ(ベンチへの**ダメージ**を防ぐ)が実際に働く相手。
#   648 マリィのオーロンゲex(シャドーバレット ベンチに30)
#   646/647 その進化前(オーロンゲデッキの判別用)
#   1031/1030 メガスターミーex(ジェットブロー ベンチに50)
#   ※ キチキギスex(140)は理屈上防げるが、実戦でほとんど撃ってこない
#     (2026-08-02 ユーザー指摘)ので入れない。
BENCH_DAMAGERS = {648, 647, 646, 1031, 1030}

# ---- エネルギー ----
PSYCHIC_ENERGY = 5      # 基本【超】
TELEPATH_ENERGY = 19    # テレパス【超】: 付けたとき たね超ポケモン2体をベンチに

# ---- グッズ/どうぐ ----
POFFIN = 1086           # HP70以下のたね2体をベンチに
HAND_TRIMMER = 1087     # 両者 手札5枚まで捨てる(相手が先)
NIGHT_STRETCHER = 1097  # トラッシュからポケモン/基本エネを1枚
BASIC_ENERGY_TYPE = 5   # cardType: 5=基本エネルギー / 6=特殊エネルギー
# 手札にも前にもエネが無いなら、トラッシュからは弾を取る
USE_STRETCHER_ENERGY = True
STRETCHER_ENERGY_SCORE = 3000.0
# ★キュワワーが場にも手札にも居ないなら、弾より先に頭数(2026-08-13)。
#   実測(対応のあるA/B・200試合x6回を2系列): 常に取る +0.21pp に対し、
#   殴り手が居るときだけ取る **+2.7pp**。貼る先が無いのにエネを拾うと、
#   キュワワーを引き直す機会をそのぶん捨てることになる。
STRETCHER_NEEDS_ATTACKER = True
CRUSH_HAMMER = 1120     # コイン: 相手のエネを1個トラッシュ
POKE_PAD = 1152         # ルール無しポケモンをサーチ
HANDHELD_FAN = 1161     # どうぐ: 殴られたら相手のエネを移動させる
ENHANCED_HAMMER = 1081  # 相手の**特殊エネ**を1個トラッシュ(コイン無し)
# ---- サポート ----
LANA = 1184             # トラッシュからルール無しポケモン/基本エネを3枚
XEROSIC = 1197          # 相手の手札を3枚まで捨てさせる
HILDA = 1225            # 進化ポケモン+エネをサーチ
LILLIE = 1227           # 手札を山に戻して6枚(8枚)ドロー
ACEROLA = 1228          # 相手のサイド2枚以下のとき、自分の1体を守る
# ---- スタジアム ----
NEUTRAL_CENTER = 1247   # ルール無しは ex/V のワザのダメージを受けない
# ★バトルコロシアム: ベンチ(両者)に、相手の**ワザの効果と特性**で
#   ダメカンが置かれるのを防ぐ。ワザのダメージは通る。
#   実測でシェイミを抜けてベンチを削っていた
#     ドラパルトのファントムダイブ(ダメカン6個) / マシマシラのアドレナブレイン /
#     ユキメノコのこごえるとばり
#   はすべて「ダメカンを置く」ので、これで止まる。
BATTLE_COLOSSEUM = 1264
BOSS_ORDERS = 1182      # 相手のベンチを1体バトル場に引きずり出す(サポート)
# ★オーガポン いしずえのめんex(117) HP210 闘 弱点草 にげる1。**ex(サイド2枚)**。
#   特性コアストーンフォルム:
#     「**特性を持つ相手のポケモン**のワザによるダメージをすべて防ぐ」
#   環境の主力アタッカーのうち特性持ちは
#     オーロンゲ24% / フーディン20.5% / ブリジュラス12.3% / イワパレス7% /
#     ワナイダー4.7% / オーガポンex2.9% = **約71%**
#   → その相手には**一切ダメージが通らない壁**になる。
#   ※ ただし ex なので **ニュートラルセンターもシェイミも保護対象外**、
#     倒されるとサイド2枚。壁として機能する相手にだけ出す。
CORNERSTONE_OGERPON = 117

ATK_FLOWER_SHOWER = None
ATK_SNEAKY_PLACEMENT = None
ATK_SPIN_AND_DRAW = None

USE_GENERIC_BASE = True
# 本来の用途が無くても、相手のスタジアムを流すために張る
# ★相手が張っていても**流さない**スタジアム(2026-08-11 ユーザー指定)。
#   どれもこちらに利があるか、少なくとも害が無い。
#     公民館(1242)         … 起動はおたがい。こちらも回復に使える
#     エキサイトスタジアム(1251) … 場のたね全員+30HP。こちらのたねも上がる
#     めまいの谷(1265)      … こんらんが進化で回復しない。アノホラグサの
#                            ロックが剥がれなくなるので**こちらの得**
#     ニュートラルセンター(1247) … ルール無しのこちらの駒を守ってくれる
STADIUM_KEEP = (1242, 1251, 1265, 1247)
# センターはコロシアム(6200)より上。ex のワザを丸ごと止める方が価値が高い
NEUTRAL_CENTER_SCORE = 6400.0
USE_STADIUM_DISRUPTION = True
STADIUM_DISRUPT_SCORE = 2200.0
# 番が終わるスタジアム特性(ミアレシティ)を、ベンチが居るときは使わない
USE_SKIP_TURN_ENDING_ABILITY = True
USE_ACT_BEFORE_ATTACK = True    # 攻撃はターンを終えるのでタダの行動を先に
PREP_MIN_SCORE = 1000.0
# ★リーリエは「手札を山に戻して6枚引く」= **山札は (手札-6) 枚増える**。
#   実測(hikarimaru の使用55回 / 提示2271回 = 採用率2%):
#     使用時の手札 中央値 **10**(最小3 最大19) / 山札 中央値 **14**
#     山札の増減は中央値 **+4** で、**73%がプラス**
#     手札8枚以上での使用が55回中40回、そのときの山札 中央値13
#   → 彼らはリーリエを**ドロー札ではなく山札の回復札**として使っている。
#     これが「自分の山札切れで負けたのが81試合中2回だけ」の理由。
USE_AVOID_SELF_MILL = True
LILLIE_REFILL_DECK = 16      # 山札がこれ以下なら回復札として最優先
LILLIE_REFILL_NET = 2
# ★ベンチが0体のときも撃つ(2026-08-04 ユーザー指定)。
#   ただしリーリエは**手札を山に戻す**ので、たねポケモンを持っているときに
#   撃つとそれごと流してしまう。点数をキュワワー(4600)/ヒトモシ(4400)より
#   下に置くことで「ベンチに置ける駒があるならそちらが先、無ければリーリエ」
#   という順序になる。
#   実測(128試合): ベンチ0の場面は85〜125回あり、これまで撃っていたのは
#   「ベンチ0 **かつ 手札にポケモン0**」の25回/17回だけだった。
#   ★条件は「ベンチ0 **かつ 手札に置けるたねが無い**」に絞る(2026-08-04)。
#     点数だけで順序を付けた版(たねがあれば先に置く)は、置いた次の番には
#     ベンチが1になって条件が消えるため、たねを持ったまま撃つ場面が残っていた。
#     撃つ回数は 25回 -> 97回(絞る前)。
USE_LILLIE_WHEN_BENCH_EMPTY = True
LILLIE_BENCH_EMPTY_SCORE = 4000.0        # 戻す枚数-6 がこれ以上のときだけ(=手札8枚以上)
# ハンマーは「相手のバトル場・エネが少ない個体」を狙う(実測の7割がエネ1個)
USE_HAMMER_TARGETING = True
HAMMER_ACTIVE_SCORE = 3000.0   # バトル場を最優先
HAMMER_BENCH_SCORE = 800.0
HAMMER_ACE_WEIGHT = 6.0        # 相手の主力(最終形の打点)を優先
HAMMER_ACE_CAP = 300.0
HAMMER_STAGE_PENALTY = 1.5     # 進化が残っているほど割り引く
HAMMER_ABILITY_BONUS = 2500.0  # エネで起動する特性を止められる標的
# サーキュレーターの移し先を「害のない駒」に選ぶ
USE_CIRCULATOR_TARGET = True
# ニュートラルセンターは相手の場に ex が出てから張る(実測 86% vs 30%)
USE_NC_ONLY_VS_EX = True
# アセロラは終盤の延命札。実測の採用率20%に合わせて他のサポートより下に置く
# カポエラーを山札回復のために前に出すか
USE_HITMONTOP_REFILL = False
HITMONTOP_REFILL_SCORE = 5400.0
# ボスの指令: ニュートラルセンターが場にあり、相手のバトル場が非ex、
# かつベンチにex/Vが居るときだけ撃つ
USE_BOSS_UNDER_NEUTRAL_CENTER = True
# 置物にできる駒をベンチから引きずり出して足止めする
USE_BOSS_STALL = True
BOSS_MIN_GAIN = 800.0
BOSS_GAP_CAP = 2
# 最終形がこの差以内で相手の最大打点に並ぶなら「エースの進化ライン」とみなす
BOSS_ACE_MARGIN = 20.0
BOSS_SCORE = 3400.0
# --- 手札を捨てる順(大きいほど先に捨てる) ---
USE_DISCARD_PRIORITY = True
DISC_HAMMER = 3000.0          # ハンマー類。相手のエネ1個ぶんで代えが利く
DISC_TOOL = 2600.0            # どうぐ
DISC_ENERGY_SPARE = 2200.0    # 2枚目以降のエネ
DISC_DEFAULT = 1000.0
DISC_ENERGY_LAST = 500.0      # 攻撃に要るぶんのエネは残す
DISC_TRIMMER = 1400.0         # ハンドトリマー(妨害札)
DISC_ENERGY_KEEP = 1           # 手札に残しておくエネの枚数
DISC_KEEP_SUPPORTER = -1000.0
DISC_KEEP_POKEMON = -1500.0
DISC_KEEP_BRAMBLE = -2500.0   # こんらんの本体。最後まで残す
ACEROLA_SCORE = 2600.0
# 倒される見込みのときは引く札より優先する
USE_ACEROLA_URGENT = True
ACEROLA_URGENT_SCORE = 5000.0
# ★採用したのは「相手のバトル場がex」だけ(2026-08-04)。
#   下の op_has_ex 版は**中間条件のほうが弱かった**ので False にしてある。
#     条件なし 74.2%±1.4(採用100%) / 場のどこかにex 67.2%±3.6(77%)
#     / バトル場がex 72.7%±1.5(採用50%)   ※キュワワー・8反復×32試合
#   バトル場がex版は条件なしと同等の勝率で、採用率が上位プレイヤーの20%に近づく。
#   なお op_active_ex は op_has_ex の部分集合なので、下を True にしても挙動は変わらない。
USE_ACEROLA_ONLY_VS_EX = False
# 相手の**バトル場**がexのときだけ撃つ(次の番に殴ってくるのはそこ)
USE_ACEROLA_WHEN_ACTIVE_EX = True
# シェイミは「ベンチにダメージを飛ばす相手」にだけ置く
USE_SHAYMIN_ONLY_VS_BENCH_DAMAGE = True
# 効かない相手には出さない。ベースを打ち消して END も下回る値
SHAYMIN_BLOCK = -2000.0
# いしずえのめんexを壁として出す条件(相手のサイド枚数)
USE_OGERPON_WALL = True
# ダメカン源が見えている相手には壁を出さないか。
# ★False。以前は対イワパレスで +8.0pp あったが、それは**進化を想定していなかった
#   旧判定**の副産物だった。進化前提に直したあと測り直すと
#   86.5%(出す) vs 86.0%(出さない) で差が消えた(10反復×40試合)。
#   イワパレスは壁が完全に刺さる相手なので出す(2026-08-03 ユーザー指定)。
USE_OGERPON_AVOID_COUNTER_DECK = False
# 壁として意味がある最低ライン(これ以上の打点を防げないなら出さない)
# 「殴り手が特性持ちか」を打点で見るか(False=場に特性持ちが1体でもいれば、の旧判定)
USE_OGERPON_THREAT_SPLIT = True
# 壁として成立しない相手には、ベンチにも置かない(ベンチ0のときだけ例外)
USE_OGERPON_BENCH_DENY = True
# 可変ダメージ技の概算倍率(ベース値 × これ)
VARIABLE_DMG_MULT = 3
# ダメカンを置く技の打点換算。★これは壁では防げないので必ず「素通り」側に数える
COUNTER_ATTACK_DMG = 100
# ★実際には殴ってこない駒(2026-08-03 ユーザー指定)。
#   ノココッチはドロー特性の要員で、技を持っていても撃ってこない。
#   打点で見ると「主力の進化前」に見えるが、エネを渡しても害がない。
#   ★シェイミ/カポエラーも「殴らない駒」。以前ここより前に同名の定義があり、
#     この行に潰されて死んでいた(2026-08-04 に統合)。
#   キチキギスex(1153)も実戦ではほぼ攻撃してこない(ユーザー指摘)
FEZANDIPITI = 1153
NON_ATTACKERS = {65, 66, 305, 306, 996, 997, SHAYMIN, HITMONTOP, FEZANDIPITI}
OGERPON_MIN_BLOCKED = 100.0
# 素通りする打点の上限(HP210がすぐ落ちるなら壁にならない)
OGERPON_MAX_LEAK = 80.0
# ダメカン源がいても、これ以上の打点を無効化できるなら壁を出す。
# いしずえのめんexは**exなのでサイド2枚**。ダメカンで削り切られると献上になるが、
# オーロンゲexのシャドーバレット180のような一撃を止め続けられるなら釣り合う。
# 実測(6反復×40試合): 対オーロンゲは出す/出さないが誤差内(49.6 vs 48.3)、
# 対イワパレス(防げる打点120・素通り0)だけは出さない方が **+8.0pp**。
# イワパレスは打点を完全に防げるぶん、マシマシラのダメカンが唯一の攻め手になり、
# 壁がそのままサイド2枚になる。
OGERPON_MIN_PRIZE = 1
OGERPON_MAX_PRIZE = 2   # 相手のサイド2枚以下(2026-08-03 ユーザー指定)
# ベンチが空で手札にもポケモンが無いときの優先順位。
# 「確実にポケモンを得られる札 > リーリエ(ランダム6枚) > 妨害」
USE_REBUILD_WHEN_NO_BACKUP = True
# 相手が既に状態異常ならアノホラグサの進化を待つ(特性の空撃ちを避ける)
USE_HOLD_EVOLVE_WHEN_LOCKED = True
# アノホラグサの進化を待つときの値。EVOLVE のベース800と足しても
# END(10) を下回る必要がある(下回らないと「他に何も無い番」で結局進化する)
BRAMBLE_HOLD_SCORE = -3000.0
# 相手が進化しきるまでアノホラグサの進化を待つ
USE_HOLD_EVOLVE_UNTIL_FULLY_EVOLVED = True
NB_POFFIN = 6000.0      # たね2体を直接ベンチに = 最強
NB_POKE_PAD = 5600.0    # ルール無しポケモンをサーチ
NB_RECOVER = 5400.0     # 夜のタンカ / スイレンのお世話(トラッシュから)
NB_LILLIE = 5000.0      # 6枚引く。確実ではないが唯一の出口になりうる
NB_DISRUPT = 300.0      # 妨害札はこの状況では後回し
# クセロシキ/ハンドトリマーを撃つ相手の手札枚数のしきい値(実測の分布から)
# ★相手の手札が3枚になるまで捨てさせる札。4枚だと1枚しか削れず、
#   サポート枠を使う価値がない(2026-08-12 ユーザー指定で 4 -> 6)。
XEROSIC_MIN_OPHAND = 6
# トラッシュから基本エネを拾える札(リーリエを撃つ前にこちらを使う)
ENERGY_FETCHERS = (NIGHT_STRETCHER, LANA)
USE_LILLIE_WHEN_NO_ENERGY = True
# 手札を流す前に、盤面に残る札を先に使う
USE_PLAY_BEFORE_SHUFFLE = True
LILLIE_WAIT_SCORE = 800.0    # 盤面に残る札(最低1200)より確実に下
USE_LILLIE_WHEN_NO_COMFEY = True
LILLIE_NO_COMFEY_SCORE = 4400.0    # 盤面に残る札(最低1200)より確実に下
LILLIE_NO_ENERGY_SCORE = 4000.0
TRIMMER_MIN_OPHAND = 8
# 自分の山札がこれ以下なら回収札(スイレン/夜のタンカ)を最優先
LOW_DECK = 12

_turn_seen = -1
# ★「相手のデッキにダメカン源がある」ことは**一度見たら覚えておく**。
#   場に出ていない瞬間だけを見て壁を出すと、後からマシマシラが出てきて
#   バトル場のオーガポンが削られる(実測: 対イワパレスが 92.5%→85.0% に低下)。
_seen_counter_source = False


def reset_state():
    global _turn_seen, _seen_counter_source
    _turn_seen = -1
    _seen_counter_source = False


def _resolve_attacks():
    global ATK_FLOWER_SHOWER, ATK_SNEAKY_PLACEMENT, ATK_SPIN_AND_DRAW
    if ATK_FLOWER_SHOWER is not None:
        return
    from cg.api import all_attack
    for a in all_attack():
        if a.name == "Flower Shower":
            ATK_FLOWER_SHOWER = a.attackId
        elif a.name == "Sneaky Placement":
            ATK_SNEAKY_PLACEMENT = a.attackId
        elif a.name == "Spin and Draw":
            ATK_SPIN_AND_DRAW = a.attackId


_ATK_DMG = None
_ATK_TEXT = {}
_ATK_COST = None


def _max_damage(cid):
    """そのカードのワザの最大打点。可変ダメージ(damage=0)は考慮しない概算。"""
    global _ATK_DMG, _ATK_TEXT
    if _ATK_DMG is None:
        from cg.api import all_attack
        _ATK_DMG = {a.attackId: (a.damage or 0) for a in all_attack()}
        _ATK_TEXT = {a.attackId: (getattr(a, "text", "") or "") for a in all_attack()}
    c = gh._CARD.get(cid)
    if c is None:
        return 0
    best = 0
    for aid in (c.attacks or []):
        d = _ATK_DMG.get(aid, 0)
        # ★可変ダメージ技は API 上 damage=0。そのままだと
        #   ロケットラッシュ(30×自分の場のロケット団数)のワナイダーが
        #   「打点0の無害な駒」に見える。generic が持つベース値で概算する。
        v = gh._ATK_VARIABLE.get(aid)
        if v:
            d = max(d, v[0] * VARIABLE_DMG_MULT)

        best = max(best, d)
    return best


_EVO_FWD = None


def _evo_forward():
    """名前 -> そこから進化するカード一覧。"""
    global _EVO_FWD
    if _EVO_FWD is None:
        m = collections.defaultdict(list)
        for c in gh._CARD.values():
            ef = getattr(c, "evolvesFrom", None)
            if ef:
                m[ef].append(c)
        _EVO_FWD = m
    return _EVO_FWD


def _final_forms(cid):
    """★進化前でずっと殴ってくる相手はいない(2026-08-03 ユーザー指摘)。

    盤面に今いる姿ではなく、**そのカードが行き着く最終形**で脅威を見る。
    例) マーニーのインプ(特性なし10) は放っておけばオーロンゲex(特性あり180)。
        今の姿で判定すると「殴り手が特性なし」と誤読して壁を出さない。
    """
    c = gh._CARD.get(cid)
    if c is None:
        return []
    fwd = _evo_forward()
    seen, stack, finals = set(), [c], []
    while stack:
        x = stack.pop()
        if x.cardId in seen:
            continue
        seen.add(x.cardId)
        nxt = fwd.get(x.name) or []
        if nxt:
            stack.extend(nxt)
        else:
            finals.append(x)
    return finals or [c]


def _final_max_damage(cid):
    return max([max(_max_damage(f.cardId), _counter_attack_damage(f.cardId))
                for f in _final_forms(cid) if f.cardId not in NON_ATTACKERS] or [0])


def _counter_attack_damage(cid):
    """『ダメカンを置く』技の打点換算。

    ★これは**壁では防げない**(いしずえのめんexが防ぐのはワザの「ダメージ」だけ)。
    フーディンのパワフルハンドを『防げる側』に数えていたせいで、
    フーディン相手に「壁が効く」と誤判定しかけていた(2026-08-03)。
    """
    if cid in NON_ATTACKERS:
        return 0
    c = gh._CARD.get(cid)
    if c is None:
        return 0
    _max_damage(cid)          # _ATK_TEXT を初期化させる
    for aid in (c.attacks or []):
        if "damage counter" in (_ATK_TEXT.get(aid) or "").lower():
            return COUNTER_ATTACK_DMG
    return 0


def _norm(t):
    return (t or "").replace("\u2019", "'").replace("\u2018", "'").lower()


_BYPASS_CACHE = {}


def _bypasses_wall(aid):
    """そのワザが「相手のバトルポケモンにかかっている効果を計算しない」か。

    ★いしずえのめんexの特性は**バトル場の自分にかかる効果**なので、
      この文言を持つワザには**貫通される**(2026-08-04 ユーザーが実戦で確認)。
      実例: イワパレス(345) Superb Scissors 120
        "This attack's damage isn't affected by any effects on
         your opponent's Active Pokemon."
      カード名ではなくテキストで判定するので、同じ文言の新カードにも効く。
    """
    v = _BYPASS_CACHE.get(aid)
    if v is None:
        _max_damage(0)                      # _ATK_TEXT を初期化させる
        t = _norm(_ATK_TEXT.get(aid))
        v = (("isn't affected by" in t or "is not affected by" in t)
             and "effects on your opponent" in t)
        _BYPASS_CACHE[aid] = v
    return v


def _attack_split(cid):
    """そのカードの打点を (壁で防げる最大, 壁を貫通する最大) に分ける。"""
    c = gh._CARD.get(cid)
    if c is None:
        return 0, 0
    _max_damage(cid)
    blocked = bypass = 0
    for aid in (c.attacks or []):
        d = _ATK_DMG.get(aid, 0)
        v = gh._ATK_VARIABLE.get(aid)
        if v:
            d = max(d, v[0] * VARIABLE_DMG_MULT)
        if _bypasses_wall(aid):
            bypass = max(bypass, d)
        else:
            blocked = max(blocked, d)
    return blocked, bypass


def _threat_split(op_field):
    """相手の場を「いしずえのめんexで防げる打点」と「素通りする打点」に割る。

    防げるのは**特性を持つポケモンのワザのダメージ**だけ。
    例) オーロンゲex(648)は Punk Up 持ち → シャドーバレット180は防げる。
        一方オーロンゲの進化前ギモー(647)は特性なし → 60は通る。
        メガスターミーex(1031)は**特性なし** → 210がそのまま通る = 壁にならない。
    """
    #   ★左右で見方を変える(2026-08-03 ユーザー指摘)。
    #   ・防げる側は**進化を想定**する。マーニーのインプ(今は特性なし10)は
    #     放っておけばオーロンゲex(特性あり180)。今の姿で見ると壁を出し損ねる。
    #   ・素通り側は**今そこに立っていて、もう進化しない特性なし**だけを数える。
    #     進化前をそのまま脅威に数えると、相手のデッキに入っていない最終形
    #     (スノーラント -> メガユキメノコex150 等)まで数えて過剰に怖がる。
    #     実際に進化してきたら、その姿が場に出た時点で数えられる。
    blocked = leak = 0
    fwd = _evo_forward()
    for c in op_field:
        cd = gh._CARD.get(c.id)
        if cd is None:
            continue
        for f in _final_forms(c.id):
            if f.cardId in NON_ATTACKERS:
                continue
            if getattr(f, "skills", None):
                blk, byp = _attack_split(f.cardId)
                blocked = max(blocked, blk)
                # 壁を貫通するワザは、特性持ちでも「素通り」側
                leak = max(leak, byp)
        # ★素通り側は**今そこに立っている姿**だけで数える。最終形まで辿ると、
        #   相手のデッキに入っていないカードまで数えてしまう。
        #   実例: ユキワラシの最終形にオニゴーリ(ダメカン技)が含まれ、
        #   オーロンゲ相手の漏が 0 -> 100 になって壁を出せなくなっていた。
        if c.id not in NON_ATTACKERS:
            # ダメカンを置く技は特性の有無によらず素通りする
            leak = max(leak, _counter_attack_damage(c.id))
            if (not (fwd.get(cd.name) or [])
                    and not getattr(cd, "skills", None)):
                leak = max(leak, _max_damage(c.id))
    return blocked, leak


class Plan:
    __slots__ = ("active", "active_id", "hand_counts", "field_counts",
                 "bench_free", "hand", "deck", "op_hand", "op_deck",
                 "op_active", "my_prize", "op_prize", "shaymin_on_bench",
                 "bench", "bench_used", "comfey_ready", "stadium_ours", "stadium_id", "op_has_ex", "no_backup", "op_locked", "op_counter_deck", "op_ability_attacker", "basic_in_hand", "op_active_ex", "op_active_can_evolve", "op_bench_ex", "boss_gain", "op_top_threat", "op_bench_damager")

    def __init__(self):
        self.active = None
        self.active_id = -1
        self.hand_counts = {}
        self.field_counts = {}
        self.bench_free = 0
        self.bench_used = 0
        self.bench = []
        self.hand = 0
        self.basic_in_hand = False
        self.deck = 0
        self.op_hand = 0
        self.op_deck = 0
        self.op_active = None
        self.my_prize = 6
        self.op_prize = 6
        self.shaymin_on_bench = False
        self.comfey_ready = False
        self.stadium_ours = False
        self.stadium_id = None
        self.op_has_ex = False
        self.op_active_ex = False
        self.op_active_can_evolve = False
        self.op_bench_ex = False
        self.boss_gain = 0.0
        self.op_top_threat = 0.0
        self.no_backup = False
        self.op_locked = False
        self.op_counter_deck = False
        self.op_ability_attacker = False
        self.op_bench_damager = False


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
    p.active = (me.active or [None])[0]
    p.active_id = p.active.id if p.active else -1
    p.hand_counts = _counts(me.hand)
    # ★手札に「今すぐベンチに置けるたねポケモン」があるか。
    #   進化カード(アノホラグサ/シャンデラ等)は手札にあっても置けないので、
    #   「ポケモンを持っている」と数えてはいけない。
    p.basic_in_hand = any(
        (gh._CARD.get(c.id) is not None and gh._CARD[c.id].cardType == 0
         and gh._CARD[c.id].basic)
        for c in (me.hand or []) if c is not None)
    field = [x for x in (me.active or []) if x] + [x for x in (me.bench or []) if x]
    p.field_counts = _counts(field)
    p.bench = [x for x in (me.bench or []) if x is not None]
    p.bench_used = len(p.bench)
    p.bench_free = (me.benchMax or 5) - p.bench_used
    p.hand = len(me.hand) if me.hand is not None else (me.handCount or 0)
    p.deck = me.deckCount or 0
    p.op_hand = (len(op.hand) if op.hand is not None else (op.handCount or 0))
    p.op_deck = op.deckCount or 0
    p.op_active = (op.active or [None])[0]
    p.my_prize = len(me.prize) if me.prize is not None else 6
    p.op_prize = len(op.prize) if op.prize is not None else 6
    p.shaymin_on_bench = any(b is not None and b.id == SHAYMIN
                             for b in (me.bench or []))
    # フラワーシャワーは超1個。バトル場のキュワワーが撃てる形か。
    p.comfey_ready = (p.active_id == COMFEY
                      and len(_energy_units(p.active)) >= 1)
    try:
        p.stadium_id = state.stadium[0].id if state.stadium else None
    except (AttributeError, IndexError, TypeError):
        p.stadium_id = None
    try:
        p.stadium_ours = bool(state.stadium) and state.stadium[0].id == NEUTRAL_CENTER
    except (AttributeError, IndexError, TypeError):
        p.stadium_ours = False
    # ★ニュートラルセンターは「相手の**ex/V**のワザ」しか止められない。
    #   相手の場にexが1体も居ないなら張っても無意味(しかも1枚しかない)。
    op_field = [x for x in (op.active or []) if x] + [x for x in (op.bench or []) if x]
    p.op_has_ex = any((gh._CARD.get(c.id) is not None
                       and (gh._CARD[c.id].ex or gh._CARD[c.id].megaEx))
                      for c in op_field)
    #   ★アセロラは「**次の相手の番**、選んだ1体が相手exのワザを受けない」札。
    #     守る意味があるのは、次に殴ってくる**相手のバトル場がex**のときだけ。
    a0 = (op.active or [None])[0]
    p.op_active_ex = bool(a0 is not None and gh._CARD.get(a0.id) is not None
                          and (gh._CARD[a0.id].ex or gh._CARD[a0.id].megaEx))
    #   ★相手の**ベンチ**に ex/V が居るか(ボスの指令で引きずり出す価値)
    p.op_bench_ex = any(
        (gh._CARD.get(b.id) is not None
         and (gh._CARD[b.id].ex or gh._CARD[b.id].megaEx))
        for b in (op.bench or []) if b is not None)
    #   ★ボスの指令で入れ替えたときの得(置物度の差)。
    #     今前に立っている駒より「置物にできる」駒がベンチに居るときだけ撃つ。
    #   相手の場の最大打点(エース判定の基準)
    _fld = [x for x in (op.active or []) if x] + [x for x in (op.bench or []) if x]
    p.op_top_threat = max([_final_max_damage(x.id) for x in _fld] or [0.0])
    _cand = [_boss_stall_value(b, p.op_top_threat)
             for b in (op.bench or []) if b is not None]
    p.boss_gain = ((max(_cand) - _boss_stall_value(a0, p.op_top_threat))
                   if (_cand and a0 is not None) else -9999.0)
    #   ★相手のバトル場が**まだ進化する**か(アノホラグサのこんらんの狙い時)。
    #     進化するとこんらんは解けるので、進化前に撃つと無駄撃ちになる
    #     (2026-08-05 ユーザー指摘)。オーロンゲはベロバー→ギモー→オーロンゲexと
    #     2回進化するので、途中で撃つと2回とも解かれる。
    _a0c = gh._CARD.get(a0.id) if a0 is not None else None
    p.op_active_can_evolve = bool(
        _a0c is not None and (_evo_forward().get(_a0c.name) or []))
    # ★**ベンチが空 かつ 手札にポケモンが1枚も無い**= バトル場が倒れたら即負け。
    #   このときは妨害より「ポケモンを探す」を最優先にする(2026-08-02 ユーザー指摘)。
    #   実測(60試合): この状態が44回あり、うち5回でクセロシキ、
    #   1回ずつクラッシュハンマー/ニュートラルセンターを切っていた。
    p.no_backup = (not [x for x in (me.bench or []) if x]
                   and not any(p.hand_counts.get(x) for x in POKEMON_IDS))
    # ★相手のバトル場が既に「こんらん/ねむり/マヒ」なら、プリズンパニックの
    #   こんらんは**上書きにしかならない**(この3つは同時に1つしか付かない)。
    #   ねむり・マヒは「攻撃も逃げもできない」ので、こんらん(50%失敗)に
    #   差し替えるのはむしろ**格下げ**。どく・やけどは共存するので対象外。
    # ★ダメカンを置いてくるカードが相手の場にいるか(バトルコロシアムの価値)
    global _seen_counter_source
    # ★トラッシュは見ない。**トラッシュのマシマシラはダメカンを動かせない**ので、
    #   それを理由に壁を諦めるのは筋が通らない(2026-08-03 ユーザー指摘)。
    #   「場に出た」ことだけを覚えておく。
    if any(c.id in COUNTER_PLACERS for c in op_field):
        _seen_counter_source = True
    # 一度でも見えたら、その試合はずっと「ダメカン源あり」として扱う
    p.op_counter_deck = _seen_counter_source
    # ★相手の場のポケモンが「特性持ち」か(いしずえのめんが壁になる条件)。
    #   壁にするのはバトル場に立つ相手なので、場にいる面々で判定する。
    #   ただし「場に特性持ちが1体でもいるか」では緩すぎる。マシマシラやユキメノコは
    #   **攻撃してこない**ので、それを根拠に壁を出すと、実際の殴り手が特性なし
    #   (メガスターミーex=特性なし)でも出してしまう。
    #   **殴り手の打点**で見る: 防げる最大打点と、防げずに通る最大打点を比べる。
    blocked, leak = _threat_split(op_field)
    if USE_OGERPON_THREAT_SPLIT:
        p.op_ability_attacker = (blocked >= OGERPON_MIN_BLOCKED
                                 and leak <= OGERPON_MAX_LEAK)
    else:
        p.op_ability_attacker = any(
            (gh._CARD.get(c.id) is not None
             and getattr(gh._CARD[c.id], "skills", None)) for c in op_field)
    #   ★ここで p.op_counter_deck を書き換えてはいけない(2026-08-05 に削除)。
    #     この変数は**バトルコロシアムの発動条件**でもあり、オーガポンの都合で
    #     False にしていたせいで、オーロンゲ(防180)・ワナイダー(160)・
    #     ブリジュラス(220)相手にコロシアムを一度も張らなくなっていた。
    #     マシマシラやユキメノコが居るのはまさにそれらのデッキ。
    #     オーガポン側は USE_OGERPON_AVOID_COUNTER_DECK=False で
    #     この変数を見ていないので、害だけが残っていた。
    # ★シェイミが本当に効く相手(ベンチに**ダメージ**を飛ばす面々)がいるか
    p.op_bench_damager = any(c.id in BENCH_DAMAGERS for c in op_field)
    p.op_locked = bool(getattr(op, "confused", False)
                       or getattr(op, "asleep", False)
                       or getattr(op, "paralyzed", False))
    return p


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


def _op_can_ko_us(p):
    """相手のバトル場のワザで、こちらのバトル場が倒されるか(弱点こみ)。"""
    o = p.op_active
    a = p.active
    if o is None or a is None:
        return False
    d = float(_max_damage(o.id))
    oc = gh._CARD.get(o.id)
    mc = gh._CARD.get(a.id)
    if oc is not None and mc is not None and d > 0:
        if mc.weakness is not None and mc.weakness == oc.energyType:
            d *= 2.0
        elif mc.resistance is not None and mc.resistance == oc.energyType:
            d -= 30.0
    try:
        hp = max(0, a.hp or 0)
    except (AttributeError, TypeError):
        hp = 0
    return hp > 0 and d >= hp


def _hammer_target_score(card, area, p):
    """ハンマーの標的スコア。

    ★この関数は長らく**一度も呼ばれていなかった**(2026-08-11 発覚)。
      標的の選択肢は `OptionType.ENERGY`(ctx=DISCARD_ENERGY)で来るのに、
      呼び出しを `OptionType.CARD` の分岐にしか置いていなかった。
      実際の標的選びは generic 任せで、リプレイ 92162863 では
      バトル場のドラパルトex(エネ1)を差し置いて
      ベンチのスボミー(エネ1)からエネを剥がしていた。

    優先順位(ユーザー指定):
      1. **バトル場** … 今まさに殴ってくる駒
      2. **相手の主力** … 最終形の打点が高いライン
      3. エネが少ない個体 … 1個割れば攻撃自体が消える
    """
    n = len(_energy_units(card))
    if n <= 0:
        return -1000.0
    sc = HAMMER_ACTIVE_SCORE if area == AreaType.ACTIVE else HAMMER_BENCH_SCORE
    # ★最終形の打点だけで重み付けすると、**あと1〜2回進化しないと殴れない駒**
    #   (マリィのベロバー/ドラメシヤ)が主力扱いになる。残り段数で割り引く
    #   (2026-08-13、オーガポン版から移植)。
    sc += (min(_final_max_damage(card.id), HAMMER_ACE_CAP) * HAMMER_ACE_WEIGHT
           / (1.0 + _stages_left(card.id) * HAMMER_STAGE_PENALTY))
    sc += max(0, 4 - n) * 300.0        # エネ1個が最優先
    # ★**エネが条件の特性**は、最後の1個を剥がすと止まる(ユーザー指定)。
    #   マシマシラのアドレナブレインは「【悪】エネがついているなら
    #   ダメカンを3個まで移す」。毎ターン30を動かす能力を消せる。
    if n <= 1 and _energy_gated_ability(card.id):
        sc += HAMMER_ABILITY_BONUS
    return sc


def _circulator_target_score(card):
    """ハンディサーキュレーターで相手ベンチのどこにエネを移すか。

    ★移し先は「主力とその進化前」を避け、**そのエネを攻撃に変えない駒**にする
    (2026-08-03 ユーザー指定)。
      ワナイダー/ミュウツー -> ロケット団のフリーザー、ミミッキュ
      オーロンゲ           -> マシマシラ、ユキメノコ(進化前含む)
      フーディン           -> ノコッチ
      ドラパルト           -> マシマシラ、ノコッチ
    共通するのは「最終的に到達する打点が低い」こと。進化前をそのまま見ると
    ベロバー(10)やタマンチュラ(30)が無害に見えてしまうので、**最終形の打点**で見る。
    """
    if card.id in NON_ATTACKERS:
        return 3200.0        # 殴ってこない駒。ここに渡すのが一番安全
    d = _final_max_damage(card.id)
    score = 3000.0 - d * 10.0
    # ★「打点が低い＝安全」ではない。**エネルギーが条件の特性**を持つ駒に渡すと、
    #   こちらから起動させてしまう(2026-08-03 実測で発覚)。
    #   マシマシラのアドレナブレインは「【悪】エネルギーがついているなら」が条件で、
    #   相手の攻撃エネはたいてい悪。ここに移していたせいで
    #   対オーロンゲ -5.9pp / 対ワナイダー -7.9pp だった。
    if _energy_gated_ability(card.id):
        score -= 4000.0
    return score


_EG_CACHE = {}


def _energy_gated_ability(cid):
    """特性の発動条件に『自分についているエネルギー』が入っているか。"""
    v = _EG_CACHE.get(cid)
    if v is None:
        c = gh._CARD.get(cid)
        v = False
        for sk in (getattr(c, "skills", None) or []):
            t = (getattr(sk, "text", "") or "").lower()
            if "energy attached" in t or "energy attached to this" in t:
                v = True
        _EG_CACHE[cid] = v
    return v


def _boss_stall_value(card, top_threat=0.0):
    """引きずり出して『置物』にできる度合い。高いほど良い標的。

    ★狙いは殴り手の無力化ではなく **時間稼ぎ**(2026-08-05 ユーザー指定)。
      評価の柱は4つ:
        ・**逃げ0はそもそも対象外**。ロケット団のミミッキュは逃げエネ0なので
          引きずり出しても即座にタダで戻られる(ユーザー指摘)。
        ・**今の打点**が低いほど良い(支配項)。マクノシタ(今30)はハリテヤマ(今210)
          より良い標的。育っていないものを前に置くのが目的。
        ・**エースの進化ライン**は避ける。最終形が相手の最大打点に並ぶ駒
          (ベロバー→オーロンゲex、ドラメシヤ→ドラパルトex)は、
          引き出すとそこで進化させられ、こちらから主力を据えることになる。
        ・**ex は避ける**。サイド2枚を抱えているので相手は必ず逃がしにくる。
      ユキワラシが下位に沈んでいた件は、最終形をゲーム全体の進化グラフから
      引いてメガユキメノコex(150)としていたため。エース判定(相手の場の
      最大打点との比較)にしたことで、150 < 180 となり上位に戻った。
    """
    cd = gh._CARD.get(card.id)
    if cd is None:
        return -9999.0
    retreat = cd.retreatCost or 0
    if retreat == 0:
        return -9999.0                      # タダで逃げられる = 足止めにならない
    n = len(_energy_units(card))
    ready, gap = _attack_readiness(card.id, n)
    now = max(_max_damage(card.id), _counter_attack_damage(card.id))
    v = 3000.0
    v -= now * 20.0                         # 今の打点(支配項)
    v -= ready * 15.0                       # 今すぐ出せる打点は特に悪い
    v += min(gap, BOSS_GAP_CAP) * 700.0     # 撃てるまでに足りないエネ
    v += min(retreat, 3) * 200.0            # 逃げにくいほど居座らせられる
    if card.id in NON_ATTACKERS:
        v += 1500.0                         # そもそも殴ってこない駒
    if cd.ex or cd.megaEx:
        v -= 1500.0                         # サイド2枚。相手は必ず逃がす
    if _final_max_damage(card.id) >= top_threat - BOSS_ACE_MARGIN:
        v -= 3000.0                         # エース本体、またはその進化前
    return v


def _boss_target_score(card, p):
    return _boss_stall_value(card, p.op_top_threat)


def _attack_readiness(cid, n):
    """(今のエネ数で出せる最大打点, 一番安いワザに足りないエネ数) を返す。"""
    c = gh._CARD.get(cid)
    if c is None:
        return 0.0, 0
    _max_damage(cid)                            # _ATK_DMG を初期化
    from cg.api import all_attack
    global _ATK_COST
    if _ATK_COST is None:
        _ATK_COST = {a.attackId: len(a.energies or []) for a in all_attack()}
    ready = 0.0
    need = None
    for aid in (c.attacks or []):
        cost = _ATK_COST.get(aid, 0)
        d = _ATK_DMG.get(aid, 0)
        vv = gh._ATK_VARIABLE.get(aid)
        if vv:
            d = max(d, vv[0] * VARIABLE_DMG_MULT)
        if cost <= n:
            ready = max(ready, d)
        need = cost if need is None else min(need, cost)
    return ready, max(0, (need or 0) - n)


PERSISTENT_PLAYS = None


COMFEY_FETCHERS = None


def _no_comfey_backup(p):
    """ベンチにキュワワーが居らず、手札にも無く、呼ぶ札も無いか。"""
    global COMFEY_FETCHERS
    if COMFEY_FETCHERS is None:
        COMFEY_FETCHERS = (POFFIN, POKE_PAD, NIGHT_STRETCHER, LANA)
    if any(b is not None and b.id == COMFEY for b in p.bench):
        return False
    if p.hand_counts.get(COMFEY):
        return False
    return not any(p.hand_counts.get(x) for x in COMFEY_FETCHERS)


def _holds_persistent_play(p):
    """手札に「使えば盤面に残る」札があるか。

    ・エネルギー(付ければポケモンに残る)
    ・なかよしポフィン(たねをベンチに置く)
    ・ハンマー類(相手のエネを削る) / どうぐ / スタジアム
    「山や手札を探すだけ」の札(ポケパッド/夜のタンカ)は、先に使っても
    直後のリーリエで一緒に流れるので**含めない**。
    """
    global PERSISTENT_PLAYS
    if PERSISTENT_PLAYS is None:
        PERSISTENT_PLAYS = (PSYCHIC_ENERGY, TELEPATH_ENERGY, POFFIN,
                            CRUSH_HAMMER, ENHANCED_HAMMER, HANDHELD_FAN,
                            BATTLE_COLOSSEUM, NEUTRAL_CENTER)
    return any(p.hand_counts.get(x) for x in PERSISTENT_PLAYS)


def _need_energy_from_trash(p):
    """手札にエネが無く、バトル場にもエネが付いていないか。

    この状態だとフラワーシャワー(超エネ1個)が撃てず、その番も次の番も
    殴れない。トラッシュから拾うならポケモンより先に弾を取る。
    ★特殊エネ(テレパス超)も手貼りはできるので「手札にエネがある」に数える。
      ただし夜のタンカが持ってこられるのは**基本エネだけ**。
    """
    if any(p.hand_counts.get(x) for x in (PSYCHIC_ENERGY, TELEPATH_ENERGY)):
        return False
    # ★殴り手そのものが居ないなら、弾より先に頭数(2026-08-13 A/B用)
    if STRETCHER_NEEDS_ATTACKER and _no_comfey_backup(p):
        return False
    return p.active is None or not _energy_units(p.active)


def _stuck_without_energy(p):
    """バトル場が撃てず、手札にエネもエネを呼ぶ札も無いか。

    ★キュワワーのフラワーシャワーは超エネ1個で撃てる。付いていないのに
      手札にエネが無く、トラッシュから拾う札(夜のタンカ/スイレンのお世話)も
      無ければ、その番は何もできない。
    """
    if p.active_id != COMFEY:
        return False
    if _energy_units(p.active):
        return False                      # 既に撃てる
    if any(p.hand_counts.get(x) for x in (PSYCHIC_ENERGY, TELEPATH_ENERGY)):
        return False                      # 手貼りできる
    return not any(p.hand_counts.get(x) for x in ENERGY_FETCHERS)


def _discard_priority(card, p):
    """手札を捨てさせられるときの**捨てる順**。大きいほど先に捨てる。

    ★ハンマー類を残してアノホラグサを捨てていた(2026-08-05 ユーザー指摘)。
      実測(240試合): アノホラグサの被トラッシュ率 **94%**、
      一方でハンディサーキュレーターは **5%** しか捨てていなかった。
      ハンマーは相手のエネを1個削るだけで、引き直しも効く。
      アノホラグサ(こんらん)とサポートの方が代えが利かない。
    """
    cid = card.id
    cd = gh._CARD.get(cid)
    if cid in (CRUSH_HAMMER, ENHANCED_HAMMER):
        return DISC_HAMMER
    if cid == HAND_TRIMMER:
        # ハンドトリマーは「ハンマー」ではなく妨害札。ハンマーほど軽く扱わない
        return DISC_TRIMMER
    if cid == HANDHELD_FAN:
        return DISC_TOOL
    if cid in (PSYCHIC_ENERGY, TELEPATH_ENERGY):
        # ★何個手元に残すかはデッキによる。キュワワーは1個で撃てるが、
        #   イダイナキバのランドコラプスは**2個**要る。ここを1個固定にしていた
        #   せいで、イダイナキバ版は -6.2pp だった。
        n = (p.hand_counts.get(PSYCHIC_ENERGY, 0)
             + p.hand_counts.get(TELEPATH_ENERGY, 0))
        return (DISC_ENERGY_SPARE if n > DISC_ENERGY_KEEP else DISC_ENERGY_LAST)
    if cid in (BRAMBLEGHAST, BRAMBLIN):
        return DISC_KEEP_BRAMBLE
    if cd is not None and cd.cardType == 0:
        return DISC_KEEP_POKEMON
    if cd is not None and cd.cardType == 3:      # サポート
        return DISC_KEEP_SUPPORTER
    return DISC_DEFAULT


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

def _stadium_disruption(p, cid):
    """自分のスタジアムを「相手のスタジアムを流す」ためだけに張るか。

    ★本来の用途が無くても、相手のスタジアムを消すために張る価値はある
      (2026-08-11 ユーザー指定)。ただし**本来の用途で要る方は温存する**。
        ・相手がフーディンのように、こちらのスタジアム2種とも
          用途が無い相手 → どちらを張ってもよい
        ・ニュートラルセンターが要る相手(exが居る) → コロシアムを妨害に回す
        ・コロシアムが要る相手(ダメカン源が居る)   → センターを妨害に回す
      場に出ているのが自分の札(どちらか)なら、上書きしても何も変わらないので張らない。
    """
    if not USE_STADIUM_DISRUPTION:
        return False
    if p.stadium_id is None:
        return False                       # 流す相手が居ない
    if p.stadium_id in (NEUTRAL_CENTER, BATTLE_COLOSSEUM):
        return False                       # 同じ効果に張り替えても無意味
    if p.stadium_id in STADIUM_KEEP:
        return False                       # 流すと損をする札
    if cid == NEUTRAL_CENTER and p.op_has_ex:
        return False                       # 本来の用途がある。温存する
    if cid == BATTLE_COLOSSEUM and p.op_counter_deck:
        return False
    return True


def _bonus(o, obs, state, me, op, p, ctx=None):
    t = o.type
    hc = p.hand_counts

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        _resolve_attacks()
        if o.attackId == ATK_FLOWER_SHOWER:
            return 9000.0          # 本体。毎ターン撃つ(実測5.86回/試合)
        if o.attackId == ATK_SNEAKY_PLACEMENT:
            return 1500.0          # ダメカン1個。繋ぎ
        if o.attackId == ATK_SPIN_AND_DRAW:
            # リーリエと同じ「手札を山に戻して6枚」= 山札は (手札-6) 増える。
            # 山札が薄く手札が厚いときだけ、攻撃を1回捨ててでも回復する。
            if (p.deck <= LILLIE_REFILL_DECK
                    and p.hand - 6 >= LILLIE_REFILL_NET):
                return 6500.0
            # ★-500 では ATTACK のベース(最大4820)を打ち消せず、
            #   END(10) も下回らない。撃つ意味が無い番に空撃ちしうる
            return -6000.0
        return 200.0

    # ---- 進化(アノクサ→アノホラグサ: 相手をこんらん) ----
    if t == OptionType.EVOLVE:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is not None and card.id == BRAMBLEGHAST:
            # ★相手が既に状態異常(こんらん/ねむり/マヒ)なら特性が無駄になるので
            #   進化を待つ(2026-08-02 ユーザー指摘)。
            #   実測: 進化74回のうち **18回(24%)** が「相手が既にこんらん」だった。
            if (USE_HOLD_EVOLVE_UNTIL_FULLY_EVOLVED
                    and p.op_active_can_evolve):
                # ★相手がまだ進化する = こんらんさせても進化で解かれる。
                #   進化しきるまで手札で待つ。
                return BRAMBLE_HOLD_SCORE
            if USE_HOLD_EVOLVE_WHEN_LOCKED and p.op_locked:
                # ★300 では効かない。EVOLVE の generic ベースが 800 あるので
                #   合計1100となり、agent() の「攻撃より準備を先に」の
                #   しきい値 PREP_MIN_SCORE(1000) を超えて**先頭に繰り上がる**。
                #   合計が1000を下回る値にする(実測で 20%→ に改善)。
                # ★さらに **END(10) も下回らせる**必要がある(2026-08-05)。
                #   -600 では合計200で END より高く、
                #   **選択肢が「進化」と「番を終える」しか無い番では結局進化していた**
                #   (リプレイ 91195681 step113: こんらん中に2体目を進化)。
                #   3つの閾値(END / generic のベース / PREP_MIN)を全部下回らせる。
                return BRAMBLE_HOLD_SCORE
            return 5000.0          # 進化時に相手をこんらん(実測1.19回/試合)
        return 600.0

    # ---- 特性 ----
    if t == OptionType.ABILITY:
        _sc = _stadium_ability_score(o, p)
        if _sc is not None:
            return _sc
        return 800.0

    # ---- エネルギー / どうぐ ----
    if t == OptionType.ATTACH:
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
        if dest is None or cid is None:
            return 0.0
        n = len(_energy_units(dest))
        if cid == HANDHELD_FAN:
            # どうぐ。殴られる前提のバトル場のキュワワーに付ける
            return 1500.0 if dest.id == COMFEY else -500.0
        if cid in (PSYCHIC_ENERGY, TELEPATH_ENERGY):
            if dest.id == COMFEY:
                # フラワーシャワーは超1個で足りる。2個目以降は無駄。
                if n == 0:
                    # バトル場が撃てないなら前を優先、撃てるならベンチの控えへ
                    if o.inPlayArea == AreaType.ACTIVE and not p.comfey_ready:
                        return 5000.0
                    return 4000.0
                return -800.0
            if dest.id == BRAMBLEGHAST:
                return 1200.0 if n < 3 else -600.0
            return -500.0          # 攻撃しない駒にエネは付けない
        return 100.0

    # ---- 場に出す / グッズ・サポート ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        if card is None:
            return 0.0
        cid = card.id

        # ★ベンチが空で手札にもポケモンが無い = 次に倒されたら負け。
        #   ポケモンを探す札を最優先にし、妨害札は後回しにする。
        if USE_REBUILD_WHEN_NO_BACKUP and p.no_backup:
            if cid == POFFIN:
                return NB_POFFIN
            if cid == POKE_PAD:
                return NB_POKE_PAD
            if cid in (NIGHT_STRETCHER, LANA):
                return NB_RECOVER
            if cid == LILLIE:
                # ★緊急時でも「盤面に残る札」は先に使う(2026-08-13)。
                #   エネを手札に抱えたまま流すと、その1個ぶん永久に損をする。
                if USE_PLAY_BEFORE_SHUFFLE and _holds_persistent_play(p):
                    return LILLIE_WAIT_SCORE
                return NB_LILLIE
            if cid in (XEROSIC, HAND_TRIMMER, CRUSH_HAMMER,
                       ENHANCED_HAMMER, NEUTRAL_CENTER, ACEROLA):
                return NB_DISRUPT

        # -- ポケモン --
        if cid == COMFEY:
            # 実測: 提示の74%で出す。控えを絶やさない(前が倒れても即再開)
            return 4600.0 if p.bench_free > 0 else 100.0
        if cid == SHAYMIN:
            # ★シェイミが防げるのは「ベンチへの**ダメージ**」だけ。
            #   実際に飛ばしてくるのは オーロンゲ(シャドーバレット30)と
            #   メガスターミー(ジェットブロー50)くらいなので、
            #   それ以外の相手ではベンチ枠をキュワワーに使う
            #   (2026-08-02 ユーザー指摘)。
            if USE_SHAYMIN_ONLY_VS_BENCH_DAMAGE and not p.op_bench_damager:
                # ★200 では効いていなかった。PLAY のベース400と足して600で
                #   END(10)を上回るため、他にやることが無い番に結局出していた。
                #   ドラパルト相手にベンチへ出して**的を増やしていた**
                #   (2026-08-11 ユーザー指摘。ファントムダイブはダメカンなので
                #    シェイミでは防げず、置くだけ損)。
                #   ベンチが空のときだけは、控えとして出してよい。
                return 3000.0 if p.bench_used == 0 else SHAYMIN_BLOCK
            if p.bench_free > 0 and not p.shaymin_on_bench:
                return 5200.0
            return 100.0
        if cid == CORNERSTONE_OGERPON:
            # ★相手の主力が特性持ちなら「絶対に倒されない壁」になる。
            #   ただし ex(サイド2枚)なので、壁として成立する相手にだけ、
            #   しかも**終盤(相手のサイド1〜3)**に出す(ユーザー指定)。
            # ★条件は「特性持ちが主力」だけでは足りない(2026-08-02 実測)。
            #   壁が防ぐのは**ワザのダメージ**だけなので、
            #   ダメカンを置いてくる相手(マシマシラ/ユキメノコ/ドラパルト)には
            #   素通りされる。5反復×24試合の実測:
            #     ワナイダー   69.2%→**78.3%**(抜けるのはタマンチュラ30のみ)
            #     ブリジュラス 85.0%→**96.7%**(抜けるのはジュラルドン80のみ)
            #     オーロンゲ   65.8%→**45.8%**(マシマシラ+ユキメノコ+ギモーが素通り)
            #   → ダメカン源が見えている相手には出さない。
            if (USE_OGERPON_WALL and p.op_ability_attacker
                    and not (USE_OGERPON_AVOID_COUNTER_DECK and p.op_counter_deck)
                    and OGERPON_MIN_PRIZE <= p.op_prize <= OGERPON_MAX_PRIZE
                    and p.bench_free > 0
                    and not p.field_counts.get(CORNERSTONE_OGERPON)):
                return 5800.0
            # ★壁として成立しない相手には**ベンチにも置かない**(ユーザー指定)。
            #   置けばサイド2枚ぶんの的をベンチに晒すだけで、
            #   キュワワーを置く枠も潰す。
            #   例外はベンチが**0**のとき。控えが居ないと次に倒された時点で負けなので、
            #   そのときだけ駒として出す。
            if p.bench_used == 0 and p.bench_free > 0:
                return 3000.0
            return -2000.0 if USE_OGERPON_BENCH_DENY else 200.0
        if cid == BRAMBLIN:
            return 2600.0 if p.bench_free > 0 else 100.0
        if cid == HITMONTOP:
            return 1200.0 if p.bench_free > 0 else 100.0

        # -- ボスの指令: ニュートラルセンターの下で相手のexを前に引き出す --
        if cid == BOSS_ORDERS:
            # ★ニュートラルセンターは「相手の**ex/V**のワザのダメージ」を止める。
            #   相手のバトル場が非exだとその効果が働かないので、
            #   ベンチのexを引きずり出して**殴り手を無力化する**(ユーザー指定)。
            #   p.stadium_ours は「場のスタジアムがニュートラルセンター」の意味。
            # ★相手が状態異常なら撃たない。入れ替えると**こんらんが解けてしまう**
            #   (2026-08-05 ユーザー指摘)。せっかくの足止めを自分で外すことになる。
            if p.op_locked:
                return -2000.0
            if USE_BOSS_STALL and p.boss_gain >= BOSS_MIN_GAIN:
                return BOSS_SCORE
            if (USE_BOSS_UNDER_NEUTRAL_CENTER and p.stadium_ours
                    and not p.op_active_ex and p.op_bench_ex):
                return BOSS_SCORE
            return -2000.0

        # -- スタジアム: ex デッキを無効化する本体 --
        if cid == BATTLE_COLOSSEUM:
            # ダメカンを置いてくる相手にだけ価値がある。
            # スタジアム枠はニュートラルセンターと奪い合うので、
            # 「相手がダメカン系を持っている」ときだけ張る。
            if p.stadium_ours:
                return -1500.0
            if p.op_counter_deck:
                return 6200.0
            return (STADIUM_DISRUPT_SCORE
                    if _stadium_disruption(p, cid) else -1200.0)
        if cid == NEUTRAL_CENTER:
            # ★実測(hikarimaru 提示452回/使用42回=9%): **使ったときは相手に
            #   ex/Vが居た割合が86%、温存したときは30%**。
            #   1枚しかないので「exが場に出てから」張る。
            #   ※ シェイミの有無は使用38% / 温存37% で**相関しない**
            #     (シェイミはベンチ限定・全攻撃対象、こちらはバトル場も守るが
            #      ex/V限定。役割が別なので排他にはしない)。
            if p.stadium_ours:
                return -1500.0
            if USE_NC_ONLY_VS_EX and not p.op_has_ex:
                return (STADIUM_DISRUPT_SCORE
                        if _stadium_disruption(p, cid) else -1200.0)
            # ★相手にexが居るならコロシアム(6200)より優先する
            #   (2026-08-11 ユーザー指摘)。センターは ex/V のワザのダメージを
            #   **丸ごと0**にするのに対し、コロシアムが止めるのは
            #   ベンチのダメカンだけ。守備範囲が違いすぎる。
            #   実測: 対オーロンゲで両方手札にある場面3回のうち2回、
            #   コロシアムを先に張っていた。
            return NEUTRAL_CENTER_SCORE

        # -- 妨害 --
        if cid in (CRUSH_HAMMER, ENHANCED_HAMMER):
            # 相手にエネが付いていないなら腐る
            has = (p.op_active is not None and _energy_units(p.op_active)) or any(
                b is not None and _energy_units(b) for b in (op.bench or []))
            if not has:
                return -800.0
            # 改造ハンマーはコイン無しで確定なので上(実測の採用率も44% > 38%)
            return 3000.0 if cid == ENHANCED_HAMMER else 2600.0
        if cid == XEROSIC:
            return 2800.0 if p.op_hand >= XEROSIC_MIN_OPHAND else -400.0
        if cid == HAND_TRIMMER:
            # 両者5枚まで捨てるので、相手の手札が厚いときだけ
            return 2400.0 if p.op_hand >= TRIMMER_MIN_OPHAND else -600.0

        # -- 回収・サーチ --
        if cid == LANA:
            # ルール無しポケモン/基本エネを3枚回収。山札が薄いほど価値が高い
            return 3200.0 if p.deck <= LOW_DECK else 1200.0
        if cid == NIGHT_STRETCHER:
            return 2200.0 if p.deck <= LOW_DECK else 1400.0
        if cid == POKE_PAD:
            return 2000.0 if p.field_counts.get(COMFEY, 0) < 3 else 900.0
        if cid == POFFIN:
            return 2600.0 if p.bench_free >= 2 else 400.0
        if cid == HILDA:
            return 1600.0 if p.field_counts.get(BRAMBLEGHAST, 0) == 0 else 700.0

        # -- 守り --
        if cid == ACEROLA:
            # ★相手のサイド2枚以下でしか使えない=終盤の延命札。
            #   実測の採用率は **20%**(提示151回/使用30回)で、
            #   守る対象は **30回すべてバトル場**(キュワワー23/アノホラグサ6/アノクサ1)。
            #   毎回切るとサポート枠を食って妨害が止まるので、
            #   クセロシキ(2800)/スイレン(3200)に譲る水準に置く。
            # ★アセロラは「回収」ではなく「守り」。しかも**相手のex**のワザしか
            #   防げない。相手にexが居ない場面での使用が実測で
            #   13%(キュワワー)〜29%(シャンデラ)あった。
            #   さらに採用率は **99%** で、上位プレイヤーの **20%** と乖離していた。
            #   → 「相手のバトル場がex」= 次の番に実際に殴ってくる場面に絞る。
            if p.op_prize > 2:
                return -2000.0
            if USE_ACEROLA_ONLY_VS_EX and not p.op_has_ex:
                return -2000.0
            if USE_ACEROLA_WHEN_ACTIVE_EX and not p.op_active_ex:
                return -2000.0
            # ★相手のexのワザで**こちらの前が倒される**見込みなら最優先。
            #   サポートは1ターン1枚なので、2600ではリーリエ(4000〜4400)に
            #   負けて撃てない。実例(リプレイ 92362721 turn15):
            #   相手のサイド残り1枚・前がオーロンゲexで、アセロラを撃てば
            #   耐えられたのにリーリエを撃っていた(2026-08-13 ユーザー指摘)。
            if USE_ACEROLA_URGENT and _op_can_ko_us(p):
                return ACEROLA_URGENT_SCORE
            return ACEROLA_SCORE

        # -- ドロー(自分の山札を焼くので基本は使わない) --
        if cid == LILLIE:
            # ★手札を山に戻す前に、**盤面に残る札**を先に使う
            #   (2026-08-13 ユーザー指摘)。実測で 1.03回/試合、
            #   ポフィン/ハンマー/サーキュレーター/スタジアム/エネを
            #   使わずに流していた。ここで一旦低い点を返すと、
            #   それらが先に処理され、次の決定でリーリエが撃たれる。
            if USE_PLAY_BEFORE_SHUFFLE and _holds_persistent_play(p):
                return LILLIE_WAIT_SCORE
            # ★ベンチにキュワワーが居らず、手札にも無いなら掘る
            #   (2026-08-13 ユーザー指定)。前が倒れたら殴り手が絶える。
            #   ただし**キュワワーを呼べる札**(ポフィン/ポケパッド/夜のタンカ/
            #   スイレン)が手札にあるなら、そちらを先に使う。上の
            #   `_holds_persistent_play` でポフィンは既に待機するので、
            #   ここでは残りのサーチ札を見る。
            if USE_LILLIE_WHEN_NO_COMFEY and _no_comfey_backup(p):
                return LILLIE_NO_COMFEY_SCORE
            # ★山札の回復札として使う(上の注記参照)。
            #   ドロー目的では使わない(自分の山を焼くのはミル側の自殺)。
            if (USE_AVOID_SELF_MILL and p.deck <= LILLIE_REFILL_DECK
                    and p.hand - 6 >= LILLIE_REFILL_NET):
                return 4200.0
            #   ★手札になかよしポフィンがあるならそちらが先(2026-08-05 ユーザー指定)。
            #     ポフィンは**たね2体をそのままベンチに置く**。リーリエは手札を
            #     山に戻して6枚引くだけで、たねを引ける保証がない。
            #     no_backup の緊急ラダーでは既に ポフィン6000 > リーリエ5000 だが、
            #     ベンチ0の分岐(4000)はポフィン(2600)に勝ってしまっていた。
            if (USE_LILLIE_WHEN_BENCH_EMPTY and p.bench_used == 0
                    and not p.hand_counts.get(POFFIN)
                    and not p.basic_in_hand):
                return LILLIE_BENCH_EMPTY_SCORE
            # ★バトル場のキュワワーにエネが付いておらず、手札にエネも
            #   **エネを呼ぶ札も無い**なら撃つ(2026-08-12 ユーザー指定)。
            #   フラワーシャワーは超1個で撃てるので、エネが無い＝
            #   その番は何もできない。掘りに行くしかない。
            if USE_LILLIE_WHEN_NO_ENERGY and _stuck_without_energy(p):
                return LILLIE_NO_ENERGY_SCORE
            if p.hand <= 2:
                return 1200.0      # 手札が枯れて何もできないとき
            return -2500.0
        return 0.0

    # ---- 手札を捨てる(クセロシキ/ハンドトリマーを撃たれたとき) ----
    if (USE_DISCARD_PRIORITY and t == OptionType.CARD
            and ctx == SelectContext.DISCARD and o.area == AreaType.HAND):
        card = gh._hand_card(obs, o.index, me)
        if card is not None:
            return _discard_priority(card, p)

    # ---- ハンマーの標的(ctx=DISCARD_ENERGY・type=ENERGY で来る) ----
    if (t == OptionType.ENERGY and USE_HAMMER_TARGETING
            and o.playerIndex is not None
            and o.playerIndex != state.yourIndex):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            return _hammer_target_score(card, o.area, p)

    # ---- トラッシュから手札に加える(夜のタンカ / スイレンのお世話) ----
    # ★手札にエネが無く、バトル場にもエネが付いていないなら、
    #   ポケモンではなく**基本エネ**を取る(2026-08-13 ユーザー指定)。
    #   キュワワーのフラワーシャワーは超エネ1個で撃てるので、
    #   この状態はその番も次の番も殴れない。頭数より先に弾を確保する。
    #   実測(300試合): 「手札エネ0 x 前エネ0」で夜のタンカを撃った56回のうち
    #   **41回(73%)がポケモンを取っていた**。
    #   ★area は DISCARD に限定する。DECK(ポケパッド等のサーチ)まで
    #     巻き込むと別の札の挙動が変わる。
    if (USE_STRETCHER_ENERGY and t == OptionType.CARD
            and ctx == SelectContext.TO_HAND and o.area == AreaType.DISCARD):
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        cd = gh._CARD.get(card.id) if card is not None else None
        if (cd is not None and cd.cardType == BASIC_ENERGY_TYPE
                and _need_energy_from_trash(p)):
            return STRETCHER_ENERGY_SCORE

    # ---- 相手のカードを選ぶ ----
    if t == OptionType.CARD and USE_HAMMER_TARGETING:
        if o.playerIndex is not None and o.playerIndex != state.yourIndex:
            card = gh._get_card(obs, o.area, o.index, o.playerIndex)
            if card is not None:
                # ★ハンディサーキュレーターの移し先は**逆向き**に選ぶ。
                #   ハンマーは「一番おいしい相手」を狙うが、こちらは
                #   相手にエネを渡す側なので「一番害のない相手」を選ぶ。
                if (USE_CIRCULATOR_TARGET and o.area == AreaType.BENCH
                        and ctx == SelectContext.ATTACH_FROM):
                    return _circulator_target_score(card)
                # ★ボスの指令で引きずり出す先。ここも**逆向き**に選ぶ必要がある。
                #   ハンマーの標的関数に流していたので、exでない駒を
                #   引っぱり出しかねなかった(サーキュレーターと同じ型のバグ)。
                if (USE_BOSS_UNDER_NEUTRAL_CENTER
                        and o.area == AreaType.BENCH
                        and ctx == SelectContext.SWITCH):
                    return _boss_target_score(card, p)
                return _hammer_target_score(card, o.area, p)
        # ★自分の**場**から1体選ぶ場面(アセロラのいたずらの対象)は、
        #   実測で 30回すべて**バトル場**だった(キュワワー23/アノホラグサ6/アノクサ1)。
        #   守るべきは殴られる駒。ベンチはシェイミの特性で既に守られている。
        if o.area in (AreaType.ACTIVE, AreaType.BENCH):
            return 3000.0 if o.area == AreaType.ACTIVE else -500.0
        # 自分側のサーチ先: キュワワー > アノクサ > エネ
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            if card.id == COMFEY:
                return 2000.0
            if card.id == SHAYMIN and not p.shaymin_on_bench:
                return 2200.0
            if card.id in (BRAMBLIN, BRAMBLEGHAST):
                return 1200.0
            if card.id in (PSYCHIC_ENERGY, TELEPATH_ENERGY):
                return 900.0
        return 0.0

    # ---- にげる(実測 0.45回/試合。ほぼ逃げない) ----
    if t == OptionType.RETREAT:
        # ★壁を張れる状況なら、撃てるキュワワーでも下げていしずえのめんに交代する
        if (USE_OGERPON_WALL and p.op_ability_attacker
                and not (USE_OGERPON_AVOID_COUNTER_DECK and p.op_counter_deck)
                and OGERPON_MIN_PRIZE <= p.op_prize <= OGERPON_MAX_PRIZE
                and p.active_id != CORNERSTONE_OGERPON
                and p.field_counts.get(CORNERSTONE_OGERPON)):
            return 4000.0
        if p.comfey_ready:
            return -2000.0         # 撃てるキュワワーは下げない
        return 200.0
    return 0.0


def _placement_bonus(o, obs, state, me, p):
    """バトル場に出す駒。実測: キュワワー52% / アノクサ26% / カポエラー12%。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    if card.id == CORNERSTONE_OGERPON:
        # ★壁として成立する状況ならバトル場に立てる。
        #   ここに立つとフラワーシャワーは撃てなくなるが、
        #   相手も一切ダメージを通せないので、**互いに干渉できない盤面**になり
        #   残り山札の多い側(=削り勝っているこちら)が勝つ(ユーザー指定の作戦)。
        if (USE_OGERPON_WALL and p.op_ability_attacker
                and not (USE_OGERPON_AVOID_COUNTER_DECK and p.op_counter_deck)
                and OGERPON_MIN_PRIZE <= p.op_prize <= OGERPON_MAX_PRIZE):
            return 6000.0
        # 壁として成立しないなら、他に出せる駒があるかぎり選ばない
        return -800.0 if USE_OGERPON_BENCH_DENY else 200.0
    if card.id == COMFEY:
        return 5000.0
    if card.id == BRAMBLIN:
        return 2000.0
    if card.id == BRAMBLEGHAST:
        return 1500.0
    if card.id == HITMONTOP:
        # ★スピンアンドドロー(手札を山に戻して6枚)は**バトル場に立たないと撃てない**。
        #   配置1000ではキュワワー(5000)に絶対勝てず、実測で 671回ベンチに出して
        #   技は **0回** だった。リーリエの回復条件と同じ局面だけ前に出す。
        if (USE_HITMONTOP_REFILL and p.deck <= LILLIE_REFILL_DECK
                and p.hand - 6 >= LILLIE_REFILL_NET):
            return HITMONTOP_REFILL_SCORE
        return 1000.0
    if card.id == SHAYMIN:
        return 300.0               # 特性要員。前に出さない
    return 200.0


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    try:
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

        # 攻撃はターンを終えるので、タダの行動(進化/エネ/特性/展開)を先に
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
        if ctx in (SelectContext.ATTACH_FROM, SelectContext.ATTACH_TO,
                   SelectContext.TO_HAND, SelectContext.TO_FIELD) and hi > k:
            k = min(hi, len(order))
        if k <= 0:
            return [] if lo == 0 else order[:max(lo, 1)]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
