"""ロケット団ワナイダー(Team Rocket's Spidops) 専用ヒューリスティック。

deck_wanaider_top.csv 用。ラダー上位(THIRD PTCG Club)の構築を再現した本流版。
設計は他の専用ヒューリスティックと同じ「generic_heuristic のスコアを土台に、
デッキ固有の判断を加算レイヤーで重ねる」形。

## このデッキの正体: 横に広げて盤面数で殴る(go-wide)

ロケット団のワナイダー(401) HP130/1進化。
  特性チャージアップ: 自分の番に1回、トラッシュから基本エネを1枚自身に付ける(自己加速)。
  ワザ ロケットラッシュ[草,無] = **30 × 自分の場の「ロケット団のポケモン」の数**。
  → **盤面が広いほど打点が上がる。** 上位の実測では盤面のロケット団は平均4.4匹
    (中央5)で、ロケットラッシュ平均133打点。

盤面を広げる手段:
  ロケット団のランス(1220): 山札からたねロケット団を3枚サーチ(先攻1ターン目も可)。
  なかよしポフィン(1086)/ポケパッド(1152)/むしとりセット(1094): たね/草の展開。
  ロケット団のレシーバー(1134): ロケット団サポートをサーチ。
  ロケット団のアテナ(1216): 5枚ドロー(全部ロケット団なら8枚)。
  ロケット団のファクトリー(1257): ロケット団サポートを使った番、毎ターン2ドロー。

サブアタッカー:
  ロケット団のミュウツーex(431) HP280: ロケット団4匹以上でないと攻撃不可。
    イレイザーボール[超超無]160(+ベンチのエネを最大2枚トラッシュして×60)。
  ロケット団のフリーザー(414): 特性で自分のたねロケット団をワザの効果から守る。
  ロケット団のヤミカラス(463): サポサーチ/ワザロック。
  ロケット団のソーナンス(432): ベンチのダメカンを相手バトル場に移す。

ロケット団エネルギー(15): ロケット団にしか付かず、【超】【悪】2個ぶん。

## 観測された上位の立ち回り(7リプレイ)
MAIN行動: PLAY44% / ATTACH27% / ATTACK9% / ABILITY8% / RETREAT6% / EVOLVE3%。
→ **攻撃は9%だけ**。盤面を広げ、エネを付け、特性を回してから殴る。他の上位デッキと同じ。

## 弱点
ワナイダー/タマンチュラの弱点は【炎】(weakness=2)。
"""

import generic_heuristic as gh

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)

# ---------------------------------------------------------------- カードID
TAROUNTULA = 400   # ロケット団のタマンチュラ HP50 たね(ワナイダーの進化元)
SPIDOPS = 401      # ロケット団のワナイダー   HP130 1進化(主砲)
MEWTWO_EX = 431    # ロケット団のミュウツーex HP280 たね(サブ主砲)
ARTICUNO = 414     # ロケット団のフリーザー   HP120 たね(効果ガード)
MURKROW = 463      # ロケット団のヤミカラス   HP80  たね(サポサーチ/ロック)
WOBBUFFET = 432    # ロケット団のソーナンス   HP110 たね(ダメカン移動)
MIMIKYU = 434      # ロケット団のミミッキュ   HP60  たね(相手のテラのワザをコピー)
                   # 上位構築(deck_wanaider_top2)に2枚。go-wideの頭数にもなる。

# 「ロケット団のポケモン」= ロケットラッシュのカウント対象
ROCKET_POKEMON = {TAROUNTULA, SPIDOPS, MEWTWO_EX, ARTICUNO, MURKROW, WOBBUFFET,
                  MIMIKYU}

ROCKET_ENERGY = 15   # ロケット団エネルギー(ロケット団専用、超/悪2個ぶん)
GRASS_ENERGY = 1     # 基本【草】(ロケットラッシュの草コスト)
PSYCHIC_ENERGY = 5   # 基本【超】(ミュウツーexのコスト)

POFFIN = 1086        # なかよしポフィン
POKE_PAD = 1152      # ポケパッド
BUG_SET = 1094       # むしとりセット(草ポケ+草エネを2枚)
ENERGY_TRANSFER = 1119  # エネルギー転送(基本エネをサーチ)
NIGHT_STRETCHER = 1097  # 夜のタンカ
RECEIVER = 1134      # ロケット団のレシーバー(ロケット団サポートをサーチ)
LILLIE = 1227        # リーリエの決心(手札をシャッフル→6枚ドロー、サイド6なら8枚)
ULTRA_BALL = 1121    # ウルトラボール(手札2枚を捨ててポケモンサーチ)
ATHENA = 1216        # ロケット団のアテナ(5/8枚ドロー)
GIOVANNI = 1218      # ロケット団のサカキ(入れ替え+相手を引きずり出す)
LANCE = 1220         # ロケット団のランス(たねロケット団3枚サーチ)
APOLLO = 1217        # ロケット団のアポロ(手札リフレッシュ、要きぜつ)
LAMBDA = 1219        # ロケット団のラムダ(トレーナーズサーチ)
FACTORY = 1257       # ロケット団のファクトリー(スタジアム、毎ターン2ドロー)
HERO_CLOAK = 1159    # ヒーローマント(HP+100)
BRAVE_BANGLE = 1175  # ブレイブバングル(ex相手に+30)
HYPNOTIZER = 1154
USE_HYPNOTIZER = True
# 相手が眠っているならサカキで起こさない(交代させない)
USE_KEEP_ASLEEP = True


ROCKET_SUPPORTERS = {RECEIVER, ATHENA, GIOVANNI, LANCE, APOLLO, LAMBDA}
# たねのロケット団(ランスでサーチできる面々)。手札にこれが1枚も無い番は
# 盤面を広げられない = ロケットラッシュ(30×頭数)が伸びない。
ROCKET_BASICS = {TAROUNTULA, ARTICUNO, MEWTWO_EX, MIMIKYU, MURKROW, WOBBUFFET}

# ワザ・特性
ATK_ROCKET_RUSH = 560     # ワナイダー [草,無] 30×ロケット団数
ATK_ERASURE_BALL = 608    # ミュウツーex [超,超,無] 160+
ATK_DARK_FROST = 583      # フリーザー [水,無,無] 60
ATK_TORMENT = 653         # ヤミカラス [悪,無] 30(ワザロック)
ATK_DECEIT = 652          # ヤミカラス [無] サポサーチ
ATK_TAKE_DOWN = 559       # タマンチュラ [草] 30
ATK_ROCKET_MIRROR = 609   # ソーナンス ダメカン移動
ATK_HEADBUTT = 610        # ソーナンス [超,無,無] 70

FIRE = 2                  # 弱点タイプ

# ---------------------------------------------------------------- 設定(A/B用)
USE_GENERIC_BASE = True
SETUP_BEFORE_ATTACK = True   # KOできない攻撃はセットアップを優先(上位は攻撃9%)
ATTACK_DEVELOP_SCORE = 500.0
USE_GO_WIDE = True           # ロケット団を並べて盤面数を稼ぐ
USE_CHARGE_UP = True         # ワナイダーの特性チャージアップを毎ターン使う
USE_ENERGY_ROUTING = True    # 草をワナイダーに、ロケットエネを主砲に
# ※ USE_ROCKET_SUPPORT は定義だけで**どこからも参照されていなかった**ため削除
#   (2026-07-28 のフラグ監査)。ロケット団サポートの優先度は各カードのスコアで表現。
# ロケットラッシュを優先する最低盤面数。
# 上位勢の勝ち111試合を実測すると **攻撃時の盤面ロケット団数は平均5.54(中央6)**。
# 自作の実測は4.2〜4.3で、1.3体ぶん=約40打点も低かった。上位に合わせて5にする。
WIDE_ENOUGH = 5

# ベンチ狙撃してくる相手への対策(A/B用)。
# オーロンゲex(648)の「シャドーバレット」= バトル場180 + **ベンチ1体に30**。
# タマンチュラはHP50なので、ベンチに置きっぱなしだと30ダメージ2発で落ちる。
# 実測(上位デッキ 対オーロンゲ): 失ったポケモンの最多が**タマンチュラ66体**、
# 負けの**94%が場切れ**(143/152)。ワナイダー(HP130)に上げれば4発必要になる。
# ※ フリーザーの特性は「効果」を防ぐがカード文に「ダメージは効果ではない」と
#   明記されているので、この狙撃は防げない。
USE_ANTI_SNIPE = True
# 「N枚まで選べる」場面で上限まで拾う(取り漏らし修正)。
# ★オーロンゲ→フーディンで同じバグを見つけ、ワナイダーでも点検して発覚。
# 特に ctx=7(ランス=たね3枚サーチ)が93回で取得1.06枚/上限2.52枚だった。
# go-wideデッキの盤面拡大エンジンなので、ここを取り逃がすと打点が出ない。
USE_PICK_MAX = True
# 「これを付けたら攻撃できる」エネ付けを最優先し、足りている個体には付けない。
# ★ユーザー指摘: (1)バトル場のミュウツーがロケ2個で草1枚あれば撃てる場面なのに
#   ベンチのワナイダーに付けて攻撃機会を逃していた(実測34回)。
#   (2)同じワナイダー/進化前に草を何個も付けていた(3個以上が705回。
#   ロケットラッシュは[草,無]の2個で撃てるので3個目以降は完全な無駄)。
USE_ATTACK_ENABLING_ATTACH = True
# 無意味な逃げを禁止する(オーロンゲと同じバグがワナイダーにもあった)。
# ★ユーザー指摘の実戦例: バトル場タマンチュラ(草エネ1) / ベンチにタマンチュラ2体と
#   ミュウツー(0エネ) / 手札にワナイダー。**次ターン進化させれば良いのに**
#   タマンチュラを下げて0エネのミュウツーを前に出し、草エネを無駄にしていた。
#   RETREAT の既定値が 100 点だったため、他に良い手がないと逃げが選ばれていた。
# ※ ローカル勝率では -3.1pp と出たが、**ローカルの相手4種(3つは自作)は本番を
#   代表できない**ためユーザー判断で有効化(判定はラダー)。機序は明確に改善している
#   (エネ付きを下げる 39→18回、逃げ総数 60→25回)。
USE_NO_POINTLESS_RETREAT = True
# ボスの指令(サカキ)で引き出す相手の選び方。
# ★ユーザー指摘: 「倒しきれないのに育っている途中/育ったポケモンを引き出すと
#   返り討ちに合う」。**倒せる相手に限り、その中で最も強い(サイド多い>HP高い)**
#   相手を選ぶ。従来は ex に加点しつつ `-hp/40` で弱い方を優先していた。
# ※ ローカル勝率では改善しなかったが、「倒しきれない相手を引き出すと返り討ち」
#   という理屈は明確なのでユーザー判断で有効化(判定はラダー)。
USE_BOSS_TARGETING = True
GRIMMSNARL_LINE = {648, 646, 647}   # マリィのオーロンゲex系
DRAGAPULT_LINE = {119, 120, 121}
# メガルカリオex系。673/674/677/678 は**弱点が超**(ミュウツーexが2倍)。
# 675 ルナトーン / 676 ソルロックは草弱点なのでワナイダーが刺さる。
LUCARIO_LINE = {673, 674, 675, 676, 677, 678}
# ブリジュラス(Archaludon)系。190 ブリジュラスex は HP300・**抵抗力【草】**で、
# ロケットラッシュ(草)が -30 される。169/839/992 ジュラルドンも同じ抵抗力。
ARCHALUDON_LINE = {169, 190, 839, 992}
# メガユキメノコex系。**うらみのハミング = 相手(こちら)の手札1枚につき50**。
#   ワナイダー(HP130)は手札3枚、ミュウツーex(HP280)は手札6枚で落ちる。
#   実測(2026-07-29、30試合): ターン終了時の手札は平均5.47枚(=274打点)で、
#   **51%のターンが6枚以上**。ハミングで落とされた駒は
#   ワナイダー35 / ミュウツーex21 / フリーザー10 で、渡したサイドは計98枚。
#   ミュウツーexは**サイド2枚**なので、落ちる圏では前に置かないほうが安い。
FROSLASS_LINE = {860, 861}
FULL_METAL_LAB = 1244   # スタジアム: 【鋼】は相手のワザのダメージを30少なく受ける
RESISTANCE_CUT = 30.0
FULL_METAL_LAB_CUT = 30.0
# ★キチキギスex(Fezandipiti ex, 140) を追加(2026-07-28 ユーザー報告)。
#   ワザ Cruel Arrow は「無3で**相手のポケモン1体に100**」。ベンチも指定できる。
#   従来 BENCH_SNIPERS はオーロンゲ/ドラパルトだけで、**フーディンデッキに
#   入っているキチキギスexが入っておらず、狙撃対策が一度も発動していなかった**。
FEZANDIPITI_EX = 140
# 100ダメージ級の狙撃。30(シャドーバレット)とは対処が変わる:
#   タマンチュラ(HP50)・ミミッキュ(HP60)・ヤミカラス(HP80)は**1発で落ちる**。
#   ワナイダー(130)に進化すれば耐える。ヒーローマント(+100)でも耐える。
HEAVY_SNIPERS = {FEZANDIPITI_EX}
# ★キチキギスexは BENCH_SNIPERS には**入れない**(2026-07-28、実測)。
#   入れると USE_ANTI_SNIPE が「進化を最優先(5600)」にしてしまい、
#   上位勢の実際の対応(進化をやめて頭数を増やす)と逆になる。
#   一致率も 54.38%→54.21% に悪化した。判定は op_heavy_sniper で別に持つ。
BENCH_SNIPERS = GRIMMSNARL_LINE | DRAGAPULT_LINE
# 100の狙撃で1発で落ちるたね(ロケットラッシュの頭数がそのまま打点なので、
# 削られると打点も落ちる)
SNIPE_FRAGILE = {400: 50, 434: 60, 463: 80}
# ★メガスターミーex系。ジェットブローは **120 + 相手ベンチ1体に50**。
#   BENCH_SNIPERS(=USE_ANTI_SNIPE も動かす)には入れず、
#   「ベンチにHPの低い駒を置かない」規則だけに使う別集合にする
#   (キチキギスexを BENCH_SNIPERS に入れて悪化した前例があるため。173行の注記)。
STARMIE_LINE = {1030, 1031}
BENCH_SNIPE_DECKS = GRIMMSNARL_LINE | DRAGAPULT_LINE | STARMIE_LINE | {FEZANDIPITI_EX}
# 「進化したらHPが上がる駒」は**進化後のHP**で評価する(2026-07-29 ユーザー要望)。
#   タマンチュラはHP50だが→ワナイダー130になるので、狙撃相手でも本命として置く。
#   ミミッキュ(60)/ヤミカラス(80)は進化しないので、置くとそのまま的になる。
EFFECTIVE_HP = {400: 130, 401: 130, 414: 120, 431: 280,
                434: 60, 463: 80, 432: 110}
# これ未満のHPは「狙撃で落ちる圏」。ジェットブロー50・シャドーバレット30の
# 重ねとキチキギス100を想定して 100 に置く。
STURDY_HP_MIN = 100



# フリーザー(レジストヴェール)を置いておきたい相手(ユーザー指定)。
#   フーディン / ワナイダー(ミラー) / ドラパルト / オーロンゲ
#
# ★特性の正しい理解(2026-07-27 ユーザーに訂正いただいた):
#   「自分の場の**たね**ロケット団全員は、相手のポケモンが使う**ワザの効果**を
#    受けない」。ベンチ限定ではなく**バトル場のたねも含む**。
#   よって「ダメカンを乗せる」系のワザは**完全に無効化できる**:
#     フーディン パワフルハンド「手札の枚数×2個のダメカンを相手のバトル場に乗せる」
#       → **たねロケット団(ミュウツーex等)が前にいれば一切通らない**
#     ドラパルトex ファントムダイブ「ベンチにダメカン6個」→ ベンチのたねを守れる
#   一方「◯◯ダメージ」と書かれたワザは効果ではないので防げない:
#     オーロンゲex シャドーバレット(ベンチに30ダメージ) / キチキギスex(100ダメージ)
FUUDIN_LINE = {741, 742, 743, 305, 66, 140}
WANAIDER_LINE = {401, 400, 431}
GUARD_TARGETS = FUUDIN_LINE | WANAIDER_LINE | DRAGAPULT_LINE | GRIMMSNARL_LINE
# ミュウツーex軸(たねを前に立ててワザの効果を無効化する)が有効な相手。
# **ダメカンを乗せる系のワザを使うデッキ限定**: フーディン と ドラパルト。
# オーロンゲ/ミラーは「ダメージ」なので前に立てても防げない。
MEWTWO_AXIS_TARGETS = FUUDIN_LINE | DRAGAPULT_LINE
USE_ARTICUNO_GUARD = True
# フリーザーがベンチにいるとき、**相手がフーディン/ドラパルトなら**
# ミュウツーex軸で戦う(2026-07-27 ユーザー要望)。
# レジストヴェールは「たねロケット団はワザの**効果**を受けない」ので、
# **たねであるミュウツーex(HP280)を前に立てると**:
#   フーディンのパワフルハンド(ダメカンを乗せる効果) → **完全に無効化**
#   ドラパルトのファントムダイブ(ベンチにダメカン)   → ベンチも守れる
# ワナイダー(401)は1進化なので保護対象外。前を張るのはたねのミュウツーexが適任。
USE_MEWTWO_AXIS = True
# イレイザーボールで「必要な枚数だけ」ベンチのエネをトラッシュする(ユーザー要望)。
# ワザは 160 + 60×n。相手HP <= 160+60n を満たす最小の n を選ぶ。
# 実測では相手HP140(160で足りる)なのに1枚トラッシュしていた=浪費。
USE_ERASURE_DISCARD = True
# 攻撃する前に「やれる準備」を全部済ませる(2026-07-27 ユーザー指摘)。
# 攻撃はターンを終わらせるので、エネ付け・進化・特性・展開が残っているなら後回し。
USE_ACT_BEFORE_ATTACK = True
# 「攻撃前にやれることを全部やる」の判定を、手札の中身ではなく
# **その場の選択肢リスト**から取るようにする(2026-07-28、flgとの差分から)。
USE_ACT_BEFORE_ATTACK_BROAD = True
# たねロケット団を出すときの役割別スコア(2026-07-28、flgとの採用率差から)。
# タマンチュラだけがワナイダーに進化する本命。他は頭数/特性要員。
BASIC_PLAY_SCORE = {}      # 下でカードIDが定義された後に埋める
# ファクトリーは「サポートの+2ドローの前提条件」で、スタジアムを張るのも
# ターンを終えないタダの行動。先に張って損がない。
FACTORY_PLAY_SCORE = 5000.0
# 攻撃より優先する準備の最低スコア。低いほど「殴らずに準備」に寄る。
EVOLVE_SPIDOPS_SCORE = 3200.0   # 修正後はflg比で十分(加算は不要だった)
PREP_MIN_SCORE = 1000.0   # flgのATTACK比率10.6%に一致する値(実測で較正)
# 倒せるとき即攻撃するか。準備はタダなので既定はFalse(先に準備)。
USE_LETHAL_ATTACK_NOW = False
# 主砲(ミュウツーex/ワナイダー/タマンチュラ)が場にも手札にも無いなら
# リーリエの決心で引き直す(2026-07-27 ユーザー指摘)。
# 実測で該当17局面すべてで使わずターンを渡していた。
USE_LILLIE_NO_CORE = True
# ロケット団サポートを使う前にファクトリーを張る(2026-07-27 ユーザー指摘)。
# ガイド通り「サポート使用時に+2ドロー」を活かすため、同じターンに
# サポートを使う予定があるならスタジアムを先に置く。
# ※ USE_FACTORY_FIRST は上記のとおり到達不能になったため削除(2026-07-28)
USE_FACTORY_PRIORITY = True
USE_FACTORY_DRAW = True
USE_LILLIE_LAST = True
USE_GIOVANNI_OPPONENT_CHECK = True
# ベンチのアタッカーで今の相手を倒せるのに、引きずり出す先が倒せないときは
# サカキを使わない(撃墜を逃すため)。
USE_GIOVANNI_KEEP_KO = True
# ★サカキのスコアは**上位勢のリプレイに合わせて較正する**(2026-08-01)。
#   同一観測605局面で、上位(kashiwashira 1053)の採用率は **8%** なのに対し
#   うちは **21%(126回)** と 2.5倍撃っていた。特に
#   「前が撃てない/ベンチに撃てる駒あり/倒せる的あり」の136局面では
#   上位13% に対し **うち88%**。サカキは1ターンのサポート枠を食うので、
#   アテナ(2400)/ランス(2500)を押しのけて撃つ価値は基本的に無い。
#   較正結果(605局面でうちの採用率を掃引):
#     3000/3400/2200 → 20.8%   2200/2600/1600 → 12.6%
#     **1800/2200/1400 → 8.3%**(上位勢の8%に一致)   1400/1800/1200 → 5.5%
USE_GIOVANNI_CALIBRATED = True
GIOVANNI_STUCK_SCORE = 1800.0
GIOVANNI_TARGET_SCORE = 2200.0
GIOVANNI_TARGET_SCORE2 = 1400.0
_GIO_OLD = (3000.0, 3400.0, 2200.0)   # A/B用の旧値
# ベンチのワナイダーが「チャージアップ1回で撃てる」なら入れ替え先に数える案。
# **既定 False**(2026-08-01 実測): サカキの使用回数は 0.47→0.47 で**一切動かない**。
#   条件(ベンチにワナイダーが居て、エネ1個、トラッシュに基本エネ)が揃う番が
#   ほとんど無いため。対オーロンゲでは自分の番の **59%がベンチにワナイダー0体**、
#   **62%がトラッシュに基本エネ0**。門を緩める話ではなく供給の話だった。
# ベンチのワナイダーが「チャージアップ1回で撃てる」なら入れ替え先に数える案。
# **既定 False**(2026-08-01 実測): サカキの使用回数は 0.47→0.47 で**一切動かない**。
#   条件(ベンチにワナイダーが居て、エネ1個、トラッシュに基本エネ)が揃う番が
#   ほとんど無いため。対オーロンゲでは自分の番の **59%がベンチにワナイダー0体**、
#   **62%がトラッシュに基本エネ0**。門を緩める話ではなく供給の話だった。
USE_CHARGEUP_COUNTS_AS_READY = False
# 盤面を直接触る特性を持つ、優先して引きずり出したい相手。
#   112 マシマシラ … アドレナブレイン(ダメカン3個を相手に移す=回復+30ダメージ)
#   104 ユキメノコ … こごえるとばり(毎ターン特性持ち全員にダメカン1個)
ENGINE_TARGETS = {112, 104}
# ★「進化されるとこちらの最大打点で落とせなくなる」相手の**進化前**。
#   うちの最大打点は イレイザーボール280(160+60×2) / ロケットラッシュ180。
#   メガミミロップex(849) は **HP330** で、どちらでも1発では落ちない。
#   一方 進化前のミミロル(758)は **HP70** なので頭数3のロケットラッシュ(90)で落ちる。
#   しかも向こうのギャロップスラストは「ベンチから出てきたターンは60+170=230」で
#   こちらのワナイダー(130)を毎ターン1発にする。
#   → **進化される前に引きずり出して潰す**価値が、サイド枚数以上にある
#     (2026-08-01 ユーザー指摘)。
USE_PRE_EVO_TARGET = True
PRE_EVO_PRIORITY = {758}      # ミミロル → メガミミロップex(HP330)
PRE_EVO_BONUS = 1500.0
USE_ENGINE_TARGET = True
USE_ENGINE_TARGET = True
ENGINE_TARGET_BONUS = 1200.0
# 相手の場から選ぶ選択肢を placement ではなく _bonus に回す(引きずり出しの対象選択)
USE_OPPONENT_SIDE_BONUS = True
# ロケット団エネはミュウツーex専用に温存する(超悪2個ぶん = イレイザーボールの要)
USE_ROCKET_ENERGY_FOR_MEWTWO = True
# ダメカン系デッキ相手にはフリーザーを2枚目まで置く
USE_ARTICUNO_SECOND = True
# 100ダメージ級の狙撃(キチキギスex)への対処
USE_FRONTLINE_CAN_ATTACK = True
USE_SACRIFICE_FRONTLINE = True
# 撃破後の入れ替えは「次のターンに撃てるか」で選ぶ
USE_NEXT_TURN_FRONTLINE = True
USE_HEAVY_SNIPE_CARE = True
EVOLVE_SCORE_VS_HEAVY_SNIPER = 1000.0   # 実測で較正(進化率66%→52%)
USE_CHARGEUP_BEFORE_ATTACH = True
USE_RETREAT_NON_ATTACKER = False  # 実測: にげる率は合うが flg一致率が 55.69→55.3%台に悪化。保留
RETREAT_NON_ATTACKER_SCORE = 2000.0
USE_SAVE_DAMAGED_RETREAT = False  # 実測で効果なし(にげる1.3→1.4%、一致率は微減)
SAVE_RETREAT_HP_RATIO = 0.4
USE_DRAW_WHEN_STUCK = True   # 詰み局面では山札切れを恐れず引き直す
# ★ただし**山札が本当に尽きる寸前では例外を認めない**(2026-07-31)。
#   ラダー154試合で敗因の13%が山札切れ。その9試合ではリーリエ2.44回/アテナ2.78回
#   (それ以外の試合は1.30/1.43)と**倍**引いていた。
#   「引かなければ確実に負ける」という理屈で入れた例外だが、
#   **引いた結果その場で山札切れになるなら、負けを確定させているだけ**。
#   自分の番のドロー1枚ぶんも残らない水準では引かせない。
DRAW_WHEN_STUCK_MIN_DECK = 6
# 山札の残りがこれ以下なら、任意のドローは一切しない(強制ドローの余地を残す)。
HARD_DECK_FLOOR = 4
USE_GRASS_FIRST_FOR_SPIDOPS = True   # ワナイダー系には草を優先(ロケ団エネは温存)
USE_FEWER_FRAGILE_VS_SNIPER = True   # 狙撃相手にミミッキュを並べすぎない
# ★ベンチ狙撃デッキ(オーロンゲ/ドラパルト/メガスターミー/キチキギス)相手には、
#   **HPが低くて進化もしない駒をベンチに置かない**(2026-07-29 ユーザー要望)。
#   実測: ミミッキュは出した1.12回/試合が**そのまま1.12回ベンチで落ちて**いた
#   (対メガスターミー24試合)。対オーロンゲでも 0.88→0.71 で8割が落ちる。
#   頭数(=ロケットラッシュの打点)が足りないときだけ例外的に許す。
# **既定 False**(2026-07-29 実測でプラマイなし)。
#   6反復×40試合: 対メガスターミー 28.8%±2.5 → 31.7%±2.4(+2.9)
#                対オーロンゲ     69.2%±4.5 → 66.7%±2.2(-2.5)
#   そもそも**優先順位は既に要望どおり**だった。頑丈な駒ともろい駒の両方を
#   出せる局面で、もろい方を選んだのは 対メガスターミー11% / 対オーロンゲ20%
#   (規則OFFの状態で)。タマンチュラ5200 / ミュウツー4000 / フリーザー2000 は
#   すべてミミッキュ1600 より上なので、順位はもとから正しい。
#   残る「置いてしまう」1.0回/試合は**他に出せる駒が手札に無い**局面で、
#   ここを禁止しても打点(30×頭数)を失うだけだった。
#   機序としては、ミミッキュが**避雷針**になっている面もある
#   (ベンチのきぜつ合計 7.29→6.83 で、ミミッキュが約1回/試合ぶん吸っていた。
#    置かないと同じ狙撃がタマンチュラ(HP50→ワナイダー)に飛ぶ)。
USE_STURDY_BENCH_VS_SNIPER = False
STURDY_BENCH_SCORE = -800.0   # 実質「置かない」
STURDY_MIN_HEADS = 3          # 頭数2以下なら例外的に置く
USE_ONE_ARTICUNO_ENOUGH = True       # フリーザーは場に1体で十分(枠を空ける)
USE_KEEP_SLOT_FOR_ARTICUNO = True    # フリーザー未設置ならベンチを埋め切らない
USE_GIOVANNI_WHEN_STUCK = True       # 前が撃てないならサカキで入れ替える
# 対フーディンでフリーザー不在ならミュウツーexを控える。**既定 False**。
# 実測(2026-07-29): 手札にミュウツーexとタマンチュラが両方ある局面 40 回で
# ミュウツーを選んだのは **0 回**。タマンチュラ(5200)が元から上で、
# 要望の挙動は既に成立していた。逆に下げると代わりにミミッキュ等を出し、
# アリーナ総合が 73.3% → 69.2% に落ちた。
USE_MEWTWO_NEEDS_GUARD = False
USE_LILLIE_FIND_ARTICUNO = True      # 対フーディンでフリーザー不在ならリーリエで探す
# 対ドラパルトでフリーザーをベンチに置く規則。**既定 False**(2026-07-29 実測)。
# 実測で「バトル場に出す判断」は既に正しかった: 入場選択283回のうち
# フリーザーを選んだのは22回で、その**全てが他に選択肢の無い強制入場**だった。
# しかもフリーザーにはエネを付けないので、一度前に出ると「にげる」自体が
# 選択肢に現れない(120試合で機会0)。よってここに足せる改善は無い。
USE_ARTICUNO_BENCH_VS_DRAGAPULT = False
USE_MEWTWO_VS_LUCARIO = True         # 対メガルカリオはミュウツーexを主砲にする
MEWTWO_LUCARIO_PLAY_SCORE = 5400.0   # タマンチュラ(5200)より上
MEWTWO_MAIN_ENERGY_SCORE = 3000.0    # ミュウツー主砲の相手へのエネ優先度
USE_LILLIE_BENCH_THIN = True         # ベンチが薄いならリーリエで引き直す
LILLIE_BENCH_MIN = 4
# 対ブリジュラス(Archaludon)もミュウツーexを主砲にする。**エネの寄せ先だけ**を
# 変える(配置優先は上げない)。上位ワナイダー勢の実測(2026-07-29、3試合3勝):
#   エネの付け先 ミュウツー4.33 / ワナイダー2.00、ワザ イレイザーボール2.67 /
#   ロケットラッシュ2.00 と**ミュウツー寄り**。うちは逆(2.67/3.29、2.04/2.96)だった。
# 対メガユキメノコex。「ハミングでどうせ落ちるなら、サイド2枚のミュウツーexを
# 前に置かない」という対策。**既定 False**(2026-07-29 実測で悪化)。
#   6反復×40試合: 32.5%±3.0 → **25.4%±3.3**(-7.1pp)。
#   理由は明白で、ミュウツーexはこのデッキで唯一の硬い壁(HP280)かつ主砲。
#   下げると殴れない番が増え、ジェットブロー(120+ベンチ50)に一方的に削られる。
#   ハミングは手札3枚でワナイダー(HP130)も落とすので、
#   **前に誰を置いても落ちる**。サイドを節約しても攻撃を失う損の方が大きい。
USE_FROSLASS_CHEAP_FRONT = False
FROSLASS_DMG_PER_CARD = 50.0
# 相手が**草弱点**(オーロンゲ系など)ならロケットラッシュが2倍になるので、
# エネはワナイダー系に寄せる(2026-07-29 ユーザー要望)。
# イレイザーボールは超なので等倍のまま。mewtwo_main と対になる概念。
#   6反復×40試合: オーロンゲ(top) 70.0%±3.1 → **74.6%±2.6**(+4.6pp)
#                オーロンゲ(マリィ) 76.2%±1.4 → 75.8%±1.2(横ばい)
#   ⚠️ 最初の測定は **-6.2pp と出たが無効**だった。ヘルパ
#      `_spidops_line_unfueled` の定義を入れ忘れており、NameError が
#      `except Exception: return gh.agent(...)` に飲まれて
#      **その局面だけ generic に落ちていた**。規則の良し悪しではなく
#      エージェントが別物に化けていた。定義を入れて測り直した値が上記。
#      → 規則を足したら「genericへのフォールバック回数0」を必ず確認する。
# ★ラダー実戦154試合(810帯)の実測(2026-07-31):
#   **自分の番の63%が「手札にたねロケット団0枚」**。
#   攻撃時にベンチが空いていた264回のうち、手札にたねがあったのは22回(8%)だけで、
#   残りは**出したくても出せない**状態だった。1試合に出したたねは5.64体、
#   ベンチで失ったのは7.10体で、供給が消費に追いついていない。
#   一方ランス(たねロケット団3枚サーチ)は **提示5.62回/試合に対し使用0.88回(16%)**。
#   → たねが手札に無いときはランスを最優先にする。
# ★場切れ負け(敗因の10%)の実測(2026-07-31、実戦171試合中9試合):
#   終盤5決定の頭数が **1.09**(それ以外の試合は5.10)で、じわじわではなく崩壊している。
#   「ベンチに空きがあり手札にたねが無い」局面97回のうち90回は**出す物が無かった**。
#   そこで持っていた札を数えると **夜のタンカを14回持っていて使用1回(7%)**。
#   トラッシュからたねロケット団を回収できるのは実質この札だけ。
# ★サーチ/回収の行き先。ワナイダーは**1進化**なので、進化元のタマンチュラが
#   場にいなければ手札で腐る。実測(2026-07-31): 夜のタンカで回収した22枚のうち
#   **14枚がワナイダー**で、場切れ寸前でもベンチを増やせない札を選んでいた。
USE_SEARCH_BASIC_WHEN_THIN = True
USE_STRETCHER_REBUILD = True
STRETCHER_REBUILD_SCORE = 3600.0
USE_LANCE_WHEN_NO_BASIC = True
LANCE_NO_BASIC_SCORE = 3400.0        # リーリエの「主砲なし」3000より上
USE_WANAIDER_MAIN_VS_GRASS_WEAK = True
WANAIDER_MAIN_ENERGY_SCORE = 3000.0
USE_MEWTWO_VS_ARCHALUDON = True
USE_RESISTANCE_AWARE = True          # 抵抗力【草】とフルメタルラボの-30を打点に反映
USE_WEAKNESS_AWARE = True            # 草弱点(オーロンゲ系)には打点2倍
USE_BENCH_AMMO = True                # イレイザーボールの弾はベンチにだけ積む
USE_CRUSTLE_AWARE = True             # イワパレスが前にいるならexの打点は0
# イワパレス(345)がバトル場にいるときのイレイザーボールのスコア。
# generic のベース(最大3300前後)を確実に下回らせるため大きな負値にする。
CRUSTLE_ATTACK_SCORE = -9000.0
USE_ROCKET_ENERGY_ONLY_WHEN_NEEDED = True
# ★ロケット団エネは**特殊エネ**。フーディンの改造ハンマー(Enhanced Hammer, 1081)は
#   「相手の特殊エネを1個トラッシュ」で**コイン無し・確定**。フーディン系は4枚積み。
#   イレイザーボールは[超,超,無]=3個で、ロケット団エネは2個ぶん。
#     A: 1ターン目にロケット団エネ(2個・撃てない) → 2ターン目に草 → 撃つ
#     B: 1ターン目に草(1個)         → 2ターン目にロケット団エネ → 撃つ
#   **どちらも撃てるのは2ターン目**だが、Aは相手の番をまたいで特殊エネを晒す。
#   Bなら付けた瞬間に撃つので剥がされない。→ **完成しないなら後回し**にする。
#   実測(2026-08-01): 対フーディン24試合で、ミュウツーへのロケット団エネ付け49回のうち
#   **23回が「付けても撃てない」**状態だった。
USE_ROCKET_ENERGY_LAST = True
USE_PLAY_BEFORE_ATTACH = True
USE_DISCARD_KEEP_ARTICUNO = True
USE_DISCARD_DEAD_SUPPORT = True
USE_CHARGEUP_COVERS_SPIDOPS = True
CHARGEUP_BASE_MAX = 2     # ロケットラッシュは[草,無]の2個で足りる
CHARGEUP_MAX_ENERGY = 4   # flgのチャージアップ採用率41.9%に一致(実測で較正)
FACTORY_DRAW_SCORE = 3400.0   # flgとの一致率が最大になる値(実測で較正)
BASIC_PLAY_SCORE.update({
    TAROUNTULA: 5200.0,     # 本命(→ワナイダー)
    MEWTWO_EX: 4000.0,
    ARTICUNO: 2000.0,
    MIMIKYU: 1600.0,
    MURKROW: 2500.0,
    WOBBUFFET: 2500.0,
})
# サカキ(1218)は「自分のバトル場を**強制的に**ベンチと入れ替える」+
# 「相手のベンチを引きずり出す」。自分側の交代で損をしないか確認してから使う。
# ★ユーザー指摘の事故: ロケット団エネ+草が付いたミュウツーが前にいるのに、
#   エネ0のワナイダーと交代していた。
USE_GIOVANNI_CARE = True
# 手札を捨てる場面(ハイパーボールのコスト)で、捨てて良いカードを選ぶ。
# ★ユーザー指摘: ワナイダー2枚を捨ててワナイダー1枚を得る無駄をしていた。
# ガイド通り「基本エネルギーを捨てながらワナイダーをサーチ」する
# (草はチャージアップで拾い直せる)。
USE_DISCARD_CARE = True

# 山札切れ対策(フーディンで効果が確認できた仕組みの移植)。
# 実測(強い相手4種, 各40×5反復): 安全ロジック無し 59.1% → 有り 64.0%(+4.9pp)。
# 特に対フーディンが 54.5%→69.5% と+15pp。バッファは3/6/10で 63.9/63.4/65.6% と
# 有意差なし(フーディンと同じ傾向)なので、山札切れをより確実に防ぐ 10 を採用。
USE_DECK_SAFETY = True
DECK_SAFETY_BUFFER = 10
# 各カードが山札から減らす枚数(ドロー・サーチ・ベンチ出し)
_DECK_COST_PLAY = {
    1216: 5,   # アテナ: 5枚ドロー(全部ロケット団なら8)
    1227: 5,   # リーリエの決心: 大量ドロー
    1220: 3,   # ランス: たね3枚サーチ
    1086: 2,   # ポフィン: たね2枚
    1094: 2,   # むしとりセット
    1152: 1,   # ポケパッド
    1134: 1,   # レシーバー
    1121: 1,   # ウルトラボール
    1097: 1,   # 夜のタンカ
}

# ---------------------------------------------------------------- ターン内状態
_turn = -1
# ★チャージアップは「このポケモンにつき」1ターン1回なので、
#   **ワナイダー1体ごとに**使用済みを管理する(2026-07-26 ユーザー指摘)。
#   単一の bool にしていたため、1体使うと場の全ワナイダーがブロックされ、
#   2体以上いても2回目以降が使えていなかった
#   (実測: 同ターン1回目65回 / 2回目9回 / 3回目1回。ゲーム側は2〜3体分の
#    選択肢を出している)。go-wideで4枚積みなので自己加速の差が大きい。
#   キーは (area, index) = 盤面上の位置。
_used_chargeup_slots = set()


def _update_turn_state(state):
    global _turn, _used_chargeup_slots
    if state.turn != _turn:
        _turn = state.turn
        _used_chargeup_slots = set()


def reset_state():
    global _turn, _used_chargeup_slots
    _turn = -1
    _used_chargeup_slots = set()


# ---------------------------------------------------------------- 盤面の把握
class Plan:
    __slots__ = ("active", "active_id", "field_counts", "hand_counts",
                 "bench_free", "rocket_count", "spidops_active",
                 "spidops_ready", "op_active", "op_active_hp", "boss_target",
                 "played_rocket_support", "safe_draws", "op_sniper", "op_heavy_sniper",
                 "op_needs_guard", "articuno_on_bench", "discard_basic_energy",
                 "op_crustle_active", "op_fuudin", "op_dragapult", "op_lucario", "articuno_anywhere",
                 "op_archaludon", "op_full_metal_lab", "mewtwo_main",
                 "op_froslass", "refrain_dmg", "op_bench_snipe",
                 "wanaider_main",
                 "op_damage_counter_deck")

    def __init__(self):
        self.active = None
        self.active_id = -1
        self.rocket_count = 0
        self.spidops_active = False
        self.spidops_ready = False
        self.op_active = None
        self.op_active_hp = 9999
        self.boss_target = -1
        self.played_rocket_support = False
        self.safe_draws = 99
        self.op_sniper = False
        self.op_heavy_sniper = False
        self.op_needs_guard = False
        self.discard_basic_energy = 0
        self.op_crustle_active = False
        self.op_fuudin = False
        self.op_dragapult = False
        self.op_lucario = False
        self.op_archaludon = False
        self.op_full_metal_lab = False
        self.op_froslass = False
        self.refrain_dmg = 0.0
        self.op_bench_snipe = False
        self.wanaider_main = False
        self.mewtwo_main = False
        self.articuno_anywhere = False
        self.articuno_on_bench = False
        self.op_damage_counter_deck = False


def _counts(cards):
    d = {}
    for c in cards or []:
        if c is not None:
            d[c.id] = d.get(c.id, 0) + 1
    return d


def _setup_option_available(obs, p: Plan, me, state) -> bool:
    """「今この選択肢の中に、攻撃より先にやるべき手が実際にあるか」。

    _has_pending_setup は手札の中身から判断するが、それだけだと
    **選択肢に出ていない=実行できない準備**でも攻撃を止めてしまい、
    結果として何もせずターンエンドする事故が起きる(実測9回)。
    そこで「選択肢に実際に含まれているか」を必ず併せて確認する。
    """
    try:
        options = obs.select.option
    except AttributeError:
        return False

    if not USE_ACT_BEFORE_ATTACK_BROAD:
        # 旧判定: 手札の中身から「準備が残っているか」を先に見る。
        # これだと**手札に残ったサポート/グッズが準備として数えられず**、
        # ゲートが素通りして早撃ちになっていた(下の実測を参照)。
        if not _has_pending_setup(p, me, state):
            return False
        for o in options:
            t = o.type
            if t in (OptionType.EVOLVE, OptionType.ABILITY, OptionType.ATTACH):
                return True
            if t == OptionType.PLAY:
                c = gh._hand_card(obs, o.index, me)
                if c is None:
                    continue
                d = gh._CARD.get(c.id)
                if d is not None and d.cardType == 0 and d.basic:
                    return True
                if c.id in (LANCE, POFFIN, POKE_PAD, BUG_SET, ATHENA, RECEIVER,
                            ULTRA_BALL, NIGHT_STRETCHER, LAMBDA):
                    return True
        return False

    # ★2026-07-28 flg(2位 1174.4、取得リプレイ内で27戦22勝)との差分から。
    #   **攻撃はターンを終わらせるが、他の行動は全部タダ**。だから
    #   「使える手が残っているなら先に全部使う」が正しい。
    #   同じ観測での実測(MAIN文脈の行動内訳):
    #       ATTACK  flg 10.9%  ←→ うち 30.7%
    #       EVOLVE  flg  6.7%  ←→ うち  1.5%
    #       ABILITY flg 14.0%  ←→ うち  6.6%
    #   うちが攻撃した747局面のうち、**68%はflgなら別の行動**をしていた。
    #   旧判定は _has_pending_setup(手札の中身)を先に見ており、
    #   「手札にサポート/グッズが残っている」を準備と数えていなかった。
    #   ここでは**選択肢リストを直接見る**ので、
    #   「実行できない準備で攻撃を止めて何もせずEND」事故は起きない。
    for o in options:
        t = o.type
        if t in (OptionType.EVOLVE, OptionType.ABILITY, OptionType.ATTACH):
            # 進化・特性(チャージアップ)・エネ付け/どうぐ付けはすべて純粋な得
            return True
        if t == OptionType.PLAY:
            c = gh._hand_card(obs, o.index, me)
            if c is None:
                continue
            d = gh._CARD.get(c.id)
            if d is None:
                continue
            if d.cardType == 0:
                # たねを出す = ロケットラッシュの打点(30×体数)が直接上がる
                if d.basic and p.bench_free > 0:
                    return True
                continue
            if d.cardType == 3:                       # サポート(1ターン1枚)
                if not getattr(state, "supporterPlayed", False):
                    return True
                continue
            if d.cardType in (1, 4):                  # グッズ・スタジアム
                return True
    return False


CRUSTLE = 345          # イワパレス: 相手の【ex】のワザのダメージを受けない
DWEBBLE = 344


def _weakness_mult(target, atk_type: int) -> float:
    """相手が atk_type 弱点なら打点2倍。atk_type は E_GRASS / E_PSYCHIC。

    ★オーロンゲ系(マリィのオーロンゲex/ギモー/ベロバー)は**3種とも弱点が草**で、
      ワナイダーは草タイプ(ロケットラッシュも草)。つまり**打点が2倍**になる。
      これを打点計算に入れないと「倒せるのにサカキで逃がす」判断が起きる
      (2026-07-29 ユーザー指摘)。

    ★メガルカリオ系(メガルカリオex/リオル/マクノシタ/ハリテヤマ)は**闘タイプで
      弱点が超**。ミュウツーex(超)のイレイザーボール160は弱点で320になり、
      HP340のメガルカリオexをベンチのエネ1個トラッシュ(+60)で落とせる
      (2026-07-29 ユーザー指摘)。ワナイダーの草は同デッキのルナトーン/
      ソルロック(草弱点)にだけ刺さる。
    """
    if target is None:
        return 1.0
    d = gh._CARD.get(target.id)
    if d is None:
        return 1.0
    return 2.0 if getattr(d, "weakness", None) == atk_type else 1.0


def _damage_cut(target, atk_type: int, p: "Plan") -> float:
    """弱点計算のあとに引かれる固定値(抵抗力 + フルメタルラボ)。

    ★ブリジュラスex(190)/ジュラルドン(169等)は**抵抗力【草】**を持つ。
      ロケットラッシュは草なので **−30**。さらに相手のスタジアム
      フルメタルラボ(1244)は「【鋼】ポケモンは相手のワザのダメージを
      **30少なく**受ける(弱点・抵抗力の計算後)」なので、重なると **−60**。
      HP300 のブリジュラスexを 30×頭数 で落とすには頭数12が必要になり、
      **構造的に届かない**(2026-07-29、上位リプレイとシミュレータで実測。
      素点−実効の分布が 0/30/60 の3山になることを確認した)。
      イレイザーボールは超なので抵抗力を受けない。
    """
    if target is None:
        return 0.0
    d = gh._CARD.get(target.id)
    if d is None:
        return 0.0
    cut = 0.0
    if getattr(d, "resistance", None) == atk_type:
        cut += RESISTANCE_CUT
    if p.op_full_metal_lab and getattr(d, "energyType", None) == E_METAL:
        cut += FULL_METAL_LAB_CUT
    return cut


def _basic_in_discard(me) -> bool:
    """トラッシュに たねロケット団 が眠っているか(夜のタンカで回収できる)。"""
    for c in (me.discard or []):
        if c is not None and c.id in ROCKET_BASICS:
            return True
    return False


def _spidops_line_unfueled(p: "Plan", me) -> bool:
    """ワナイダー/タマンチュラで**まだロケットラッシュが撃てない個体**がいるか。

    ロケットラッシュは [草,無] の2個。草弱点の相手には打点が2倍になるので、
    ミュウツーにエネを回す前にこちらを完成させたい。
    """
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        if c.id in (SPIDOPS, TAROUNTULA) and len(_energy_units(c)) < 2:
            return True
    return False


def _vs_active(base: float, atk_type: int, p: "Plan") -> float:
    """素点 base が**相手のバトル場に実際に通る**打点。

    順序はゲームと同じで、弱点2倍 → そのあと固定値を引く。
      弱点(×2) → 抵抗力【草】(-30) → フルメタルラボ(-30)

    ★「倒せるか」の判定は**必ずこれを通す**(2026-07-29 ユーザー指摘)。
      素点のまま比べると、ブリジュラスex(抵抗力【草】)+フルメタルラボ相手に
      ロケットラッシュが **-60** されるのを見落として
      「30×頭数で倒せる」と誤判定する。実測では 30×6=180 の素点に対し
      実効は 120 しか通っていない。
    """
    if USE_WEAKNESS_AWARE:
        base *= _weakness_mult(p.op_active, atk_type)
    if USE_RESISTANCE_AWARE:
        base = max(0.0, base - _damage_cut(p.op_active, atk_type, p))
    return base


def _attacker_damage(c, p: Plan) -> float:
    """その個体が「今バトル場にいたら」出せる打点(概算)。0なら撃てない。

    ロケットラッシュ = 30 × 自分の場のロケット団の数(場所によらない)。
    イレイザーボール = 160(ベンチのエネを最大2個トラッシュして+60ずつだが、
    ここでは確実に出る分だけを見る)。
    ブレイブバングルの+30は「ルールを持たないポケモンが相手のバトル場のexを
    殴るとき」だけ乗る。
    """
    if c is None:
        return 0.0
    need = _energy_need(c)
    if need <= 0 or len(c.energies or []) < need:
        return 0.0
    if c.id == SPIDOPS:
        dmg = _vs_active(p.rocket_count * 30.0, E_GRASS, p)
    elif c.id == MEWTWO_EX:
        # ★イワパレスは「相手の【ex】のワザのダメージを受けない」。
        #   ミュウツーexで殴っても**0ダメージ**なので、打点として数えない
        #   (2026-07-29 ユーザー指摘。メガガルーラデッキもイワパレスを積む)。
        #   ここで0にすると、前線選択・サカキ・KO判定すべてに波及する。
        if USE_CRUSTLE_AWARE and p.op_crustle_active:
            return 0.0
        dmg = _vs_active(160.0, E_PSYCHIC, p)
    else:
        return 0.0
    if c.id != MEWTWO_EX:
        has_bangle = any(getattr(t, "id", None) == BRAVE_BANGLE
                         for t in (getattr(c, "tools", None) or []))
        if has_bangle and p.op_active is not None:
            od = gh._CARD.get(p.op_active.id)
            if od is not None and (od.ex or od.megaEx):
                dmg += 30.0
    return dmg


def _our_active_damage(p: Plan, me) -> float:
    """今バトル場にいるポケモンが出せる打点。0なら撃てない。"""
    return _attacker_damage(p.active, p)


def _best_attacker_damage(p: Plan, me) -> float:
    """バトル場に立てられるアタッカーの最大打点(ベンチも含む)。

    ★サカキは「自分のバトル場をベンチと入れ替える」ので、**ベンチの駒も
      バトル場に出せる**。引きずり出した相手を倒せるかどうかは、
      入れ替わった**後**に殴る駒の打点で判定しないといけない
      (2026-07-28 ユーザー指摘)。従来は「今のバトル場のロケットラッシュ」
      固定で見ており、前が育っていないときに一切引きずり出せなかった。
    """
    best = 0.0
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        d = _attacker_damage(c, p)
        if d > best:
            best = d
    return best


def _best_bench_attacker_damage(p: Plan, me) -> float:
    """**ベンチだけ**で見た最大打点。

    ★サカキは自分のバトル場を**強制的にベンチと入れ替える**ので、
      入れ替わった後に前に立つのは**ベンチの駒**。
      バトル場を含めて計算すると「今の前が撃てるから大丈夫」と誤判定する。
      実戦(88719658 t51)で、**ロケット団エネ2枚(4個)で撃てるミュウツーex**が
      前にいるのに、倒せる的(イシズマイHP70)を引きずり出すためにサカキを使い、
      **エネ1個の撃てないミュウツーex**と入れ替わって攻撃機会を失った。
    """
    best = 0.0
    for c in [x for x in (me.bench or []) if x]:
        d = _attacker_damage(c, p)
        # ★ワナイダーは特性チャージアップで**このターン中に**トラッシュから
        #   基本エネを1個自身に付けられる。サカキ→攻撃は同じターンなので、
        #   「今1個足りないだけ」の個体も入れ替え先として数えてよい
        #   (2026-08-01 実測: 対オーロンゲでサカキが使えなかった局面の
        #    **68%** が「ベンチに撃てる駒が無い」で弾かれていた)。
        if (d <= 0 and USE_CHARGEUP_COUNTS_AS_READY and c.id == SPIDOPS
                and p.discard_basic_energy > 0
                and len(_energy_units(c)) >= _energy_need(c) - 1):
            d = _vs_active(p.rocket_count * 30.0, E_GRASS, p)
        if d > best:
            best = d
    return best



def _best_killable_bench(op, dmg: float):
    """相手ベンチのうち dmg で倒せる中で **最も強い** 個体の (スコア, カード)。

    強さ = サイド枚数 > HP(育っている) > 特性持ち。倒せる的が無ければ None。
    """
    best = None
    for b in (op.bench or []):
        if b is None or dmg <= 0:
            continue
        if (b.hp or 0) > dmg:
            continue
        d = gh._CARD.get(b.id)
        pz = (3 if d and d.megaEx else 2 if d and d.ex else 1)
        sc = pz * 1000.0 + (b.hp or 0)
        if getattr(d, "skills", None):
            sc += 300.0
        # ★盤面を直接触る特性持ちは、サイド枚数以上に価値がある
        #   (2026-08-01 ユーザー指摘 + 実測)。マシマシラ(112)の
        #   アドレナブレインは「自分のポケモンのダメカンを3個まで
        #   **相手に移す**」= 相手を回復しつつこちらに30。
        #   実戦で **1試合3.50回** 使われていた(=最大105ダメージ移動)。
        if USE_ENGINE_TARGET and b.id in ENGINE_TARGETS:
            sc += ENGINE_TARGET_BONUS
        # ★進化されると手が付けられなくなる相手は、今のうちに潰す。
        #   この加点は標的の選択だけでなく、サカキ自体のスコア
        #   (GIOVANNI_TARGET_SCORE + best[0]/2)にも半分乗る。
        if USE_PRE_EVO_TARGET and b.id in PRE_EVO_PRIORITY:
            sc += PRE_EVO_BONUS
        if best is None or sc > best[0]:
            best = (sc, b)
    return best


# ※ _pending_before_lillie は agent() 側の order 入れ替えに移したため削除(2026-07-28)
def _no_attacker_at_all(p, me) -> bool:
    """このターンも次のターンも殴れる駒が無いか(=詰んでいるか)。

    ★リーリエが山札切れガードで弾かれる問題への判定(2026-07-29 ユーザー指摘)。
      実戦(88715772 t113)で **手札4枚・場は瀕死のミミッキュとエネ1のミュウツー**
      という詰み局面なのに、`safe_draws=3 < リーリエの6枚` で -8000 され、
      **何もせずターンエンド**していた。
      引かなければ確実に負ける局面では、山札切れのリスクを取る方が良い。
    """
    for c in ([x for x in (me.active or []) if x] + [x for x in (me.bench or []) if x]):
        if _can_attack_now(c, p, _bench_pokemon_count(me)):
            return False
        if _can_attack_next_turn(c, p, _bench_pokemon_count(me)):
            return False
    return True


def _has_pending_setup(p: Plan, me, state) -> bool:
    """このターン、攻撃する前に済ませておくべき準備が残っているか。

    攻撃はターンを終わらせるので、以下が残っているなら先にやる:
      - まだエネを付けていない(1ターン1回)かつ、手札にエネがあり付け先が足りない
      - 手札のワナイダーで場のタマンチュラを進化できる
      - チャージアップ(特性)が使えるワナイダーがいる
      - ベンチに空きがあり、手札にたねロケット団がいる(go-wideなので打点が増える)
    """
    hc = p.hand_counts
    # 1) エネ付け: このターンまだ付けておらず、足りていない主砲がいる
    if not state.energyAttached:
        has_energy = any(hc.get(e) for e in (GRASS_ENERGY, ROCKET_ENERGY,
                                             PSYCHIC_ENERGY))
        if has_energy:
            for c in ([x for x in (me.active or []) if x]
                      + [x for x in (me.bench or []) if x]):
                need = _energy_need(c)
                if need > 0 and len(c.energies or []) < need:
                    return True
    # 2) 進化: 手札のワナイダーで場のタマンチュラを進化できる
    if hc.get(SPIDOPS) and p.field_counts.get(TAROUNTULA):
        return True
    # 3) チャージアップが使えるワナイダー(エネ2個未満)がいる
    for area, cards in ((AreaType.ACTIVE, me.active or []),
                        (AreaType.BENCH, me.bench or [])):
        for i, c in enumerate(cards):
            if c is None or c.id != SPIDOPS:
                continue
            if (area, i) in _used_chargeup_slots:
                continue
            if len(c.energies or []) < 2:
                return True
    # 4) 盤面を広げられる(go-wideは頭数がそのまま打点)
    #    ★ユーザー指摘(2026-07-27): 盤面が目標(WIDE_ENOUGH)に達していても、
    #      ベンチに空きがあり手札にたねがいるなら**出してから殴る**。
    #      ロケットラッシュは 30×頭数 なので、1体増えるだけで打点が30上がる。
    if p.bench_free > 0:
        for cid in ROCKET_POKEMON:
            d = gh._CARD.get(cid)
            if d is not None and d.basic and hc.get(cid):
                return True
    return False


def _discard_energy_id(o, me):
    """トラッシュ選択の候補が指している「エネルギーカードのID」を返す。"""
    try:
        if o.area == AreaType.BENCH and me.bench:
            tgt = me.bench[o.index or 0]
        elif o.area == AreaType.ACTIVE and me.active:
            tgt = me.active[0]
        else:
            return None
        ei = getattr(o, "energyIndex", None)
        cards = tgt.energyCards or []
        if ei is None or ei >= len(cards):
            return None
        return cards[ei].id
    except (IndexError, TypeError, AttributeError):
        return None


def _erasure_wins_game(p: Plan, me, n_discard: int) -> bool:
    """イレイザーボールで n枚トラッシュして撃つと、**それで勝てる**か。

    「相手のバトル場を倒せる」かつ「そのサイド獲得で自分のサイドが0になる」。
    このときだけロケット団エネをトラッシュしてよい(ユーザー指定の例外)。
    """
    oa = p.op_active
    if oa is None:
        return False
    dmg = 160 + 60 * n_discard
    act = p.active
    if act is not None and act.id == MEWTWO_EX:
        d = gh._CARD.get(oa.id)
        has_bangle = any(getattr(t, "id", None) == BRAVE_BANGLE
                         for t in (getattr(act, "tools", None) or []))
        if has_bangle and d is not None and (d.ex or d.megaEx):
            dmg += 30
    if dmg < (oa.hp or 0):
        return False
    d = gh._CARD.get(oa.id)
    prize_gain = 3 if d and d.megaEx else 2 if d and d.ex else 1
    my_prize = len(me.prize) if me.prize is not None else 6
    return my_prize <= prize_gain


def _erasure_discard_need(p: Plan, me) -> int:
    """イレイザーボールで**トラッシュすべきベンチのエネ枚数**(0〜2)。

    ユーザー指定(2026-07-27)の計算式:
      ワザは 160 + 60 × (トラッシュしたエネ枚数)。
      「相手のHP <= 160 + 60×n」を満たす最小の n を選ぶ(無駄打ちしない)。
      相手のHPが160以下なら 0 枚(そのまま倒せる)。
      ミュウツーがブレイブバングルを持ち、かつ相手がexなら +30 されるので
      判定HPから30を引いて計算する。
      ※ ただしブレイブバングルは「ルールを持たないポケモン」限定なので、
        ミュウツーex(ルールボックス持ち)には**効果がない**。仕様上は常に
        補正なしになるが、ご指定通り条件だけは実装しておく。
    草エネをトラッシュしてもワナイダーのチャージアップで拾い直せるので、
    倒せるなら惜しまずトラッシュする。
    """
    oa = p.op_active
    if oa is None:
        return 0
    hp = oa.hp or 0
    act = p.active
    if act is not None and act.id == MEWTWO_EX:
        d = gh._CARD.get(oa.id)
        has_bangle = any(getattr(t, "id", None) == BRAVE_BANGLE
                         for t in (getattr(act, "tools", None) or []))
        if has_bangle and d is not None and (d.ex or d.megaEx):
            hp -= 30
    # ★弱点・抵抗力・フルメタルラボを通した実効打点で必要枚数を決める
    #   (2026-07-29 ユーザー指摘)。素点で数えると、-30される相手に
    #   1枚足りないままトラッシュを打ち切ってしまう。
    for n in range(0, 3):
        if hp <= _vs_active(160.0 + 60.0 * n, E_PSYCHIC, p):
            return n
    return 2          # 2枚でも届かないなら最大まで乗せる


def _energy_need(pk) -> int:
    """このポケモンがワザを撃つのに必要なエネの総数。

      ワナイダー(401)   ロケットラッシュ [草,無]     = 2個
      タマンチュラ(400) たいあたり       [草]        = 1個(が、進化前なので2個まで許容)
      ミュウツーex(431) イレイザーボール [超,超,無]  = 3個
        ※ ロケット団エネ(15)は【超】【悪】2個ぶんなので、ロケ2個+1個で撃てる。
          ここでは「枚数」で数えるので3を返し、判定側で枚数比較する。
      それ以外(フリーザー/ヤミカラス等) = 主砲ではないので0(付ける必要なし)
    """
    if pk is None:
        return 0
    if pk.id == SPIDOPS:
        return 2
    if pk.id == TAROUNTULA:
        return 2          # 進化後にそのまま引き継げる
    if pk.id == MEWTWO_EX:
        return 3
    return 0


def _looking_card(obs, idx):
    """LOOKING(area=12)の候補カード。**gh._get_card は None を返す**。

    ★2026-07-29 発覚。むしとりセット(山札の上7枚を見て、草ポケモン/基本草エネを
      **2枚まで**手札に)の候補は area=LOOKING で来るが、
      `_is_worth_picking` が LOOKING を対象外にしていたため
      **常に1枚しか取っていなかった**(実測51局面で 上位勢1.96枚 vs うち1.00枚)。
      カードの実体は observation の current.looking にある。
    """
    try:
        lk = obs.current.looking or []
    except AttributeError:
        return None
    if not isinstance(idx, int) or idx >= len(lk):
        return None
    return lk[idx]


def _is_worth_picking(o, obs, me) -> bool:
    """「N枚まで選べる」場面で、上限まで拾って良い候補か。

    ランス(たね3枚サーチ)/ポフィン/チャージアップの配分先などで使う。
    go-wideデッキなのでロケット団ポケモンは何体でも欲しい。草エネも同様。
    """
    if o.type != OptionType.CARD:
        return False
    if o.area not in (AreaType.DECK, AreaType.DISCARD, AreaType.PRIZE,
                      AreaType.BENCH, AreaType.ACTIVE, AreaType.LOOKING):
        return False
    if o.area == AreaType.LOOKING:
        c = _looking_card(obs, o.index)
    else:
        c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    return (c.id in ROCKET_POKEMON or c.id == GRASS_ENERGY
            or c.id == ROCKET_ENERGY)


def _is_basic_pokemon_opt(o, obs, me) -> bool:
    """その候補が「たねポケモン」か(ベンチ空き枠で上限を絞るため)。"""
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    d = gh._CARD.get(c.id)
    return bool(d) and d.basic and d.cardType == 0


def _rocket_on_field(me) -> int:
    n = 0
    for c in (me.active or []):
        if c is not None and c.id in ROCKET_POKEMON:
            n += 1
    for c in (me.bench or []):
        if c is not None and c.id in ROCKET_POKEMON:
            n += 1
    return n


def _build_plan(obs: Observation, state, me, op) -> Plan:
    p = Plan()
    field = [c for c in (me.active or []) if c] + [c for c in (me.bench or []) if c]
    p.field_counts = _counts(field)
    p.hand_counts = _counts(me.hand)
    p.bench_free = (me.benchMax or 5) - len(me.bench or [])

    p.active = me.active[0] if me.active else None
    p.active_id = p.active.id if p.active else -1
    p.rocket_count = _rocket_on_field(me)
    p.spidops_active = p.active_id == SPIDOPS
    # ロケットラッシュは [草,無]。草エネが1個以上付いていれば撃てる。
    p.spidops_ready = (p.spidops_active
                       and len(p.active.energies or []) >= 2)

    p.op_active = op.active[0] if op.active else None
    p.op_active_hp = p.op_active.hp if p.op_active else 9999

    # 山札の安全余裕。フーディンで効果が確認できた仕組みをこちらにも入れる。
    # 実測(対フーディン80試合)で、上位構築(リーリエ4枚)を使うと山札切れ負けが
    # 14→29件に倍増していた。引きすぎの自滅を防ぐ。
    my_prize = len(me.prize) if me.prize is not None else 6
    p.safe_draws = max(0, (me.deckCount or 0) - my_prize - DECK_SAFETY_BUFFER)

    # ベンチを狙撃してくる相手か(オーロンゲex=シャドーバレットでベンチに30)。
    op_all = [c for c in (op.active or []) if c] + [c for c in (op.bench or []) if c]
    # ★トラッシュの基本エネ枚数(チャージアップで回収できる分)。
    #   トラッシュは観測から見える(2026-07-28 リプレイで確認)。
    try:
        p.discard_basic_energy = sum(
            1 for c in (me.discard or [])
            if c is not None and gh._CARD.get(c.id) is not None
            and gh._CARD[c.id].cardType == 5)
    except (AttributeError, TypeError):
        p.discard_basic_energy = 0
    # ★相手のバトル場がイワパレスなら、こちらのexは打点0になる
    p.op_crustle_active = any(c is not None and c.id == CRUSTLE
                              for c in (op.active or []))
    p.op_sniper = any(c.id in BENCH_SNIPERS for c in op_all)
    # ベンチに「ダメージ」を飛ばしてくるデッキ(フリーザーでは防げない)
    p.op_bench_snipe = any(c.id in BENCH_SNIPE_DECKS for c in op_all)
    # 100ダメージ級の狙撃(キチキギスex)。たねが1発で落ちるので対処が変わる。
    p.op_heavy_sniper = any(c.id in HEAVY_SNIPERS for c in op_all)
    # フリーザーを置いておきたい相手(ユーザー指定の4デッキ)。
    # 本命はドラパルト(ファントムダイブのダメカン配置=「効果」なので防げる)。
    p.op_needs_guard = any(c.id in GUARD_TARGETS for c in op_all)
    # ★相手のアーキタイプを個別に持つ(2026-07-29 ユーザー指摘)
    p.op_fuudin = any(c.id in FUUDIN_LINE for c in op_all)
    p.op_dragapult = any(c.id in DRAGAPULT_LINE for c in op_all)
    p.op_lucario = any(c.id in LUCARIO_LINE for c in op_all)
    p.op_archaludon = any(c.id in ARCHALUDON_LINE for c in op_all)
    # ★うらみのハミングで**今こちらに入る打点**。相手のターンに撃たれるので、
    #   基準はこちらの手札枚数(ターンを渡した瞬間の枚数に近い)。
    p.op_froslass = any(c.id in FROSLASS_LINE for c in op_all)
    _hand_n = len(me.hand) if me.hand is not None else (me.handCount or 0)
    p.refrain_dmg = FROSLASS_DMG_PER_CARD * _hand_n if p.op_froslass else 0.0
    # フルメタルラボが場に出ているか(スタジアムはどちらが出しても効く)
    p.op_full_metal_lab = bool(state.stadium) and state.stadium[0].id == FULL_METAL_LAB
    # ミュウツーexを主砲に据える相手。
    #   メガルカリオ = 弱点【超】でイレイザーボールが2倍(実測320)
    #   ブリジュラス = 抵抗力【草】+フルメタルラボでロケットラッシュが-60
    p.mewtwo_main = ((USE_MEWTWO_VS_LUCARIO and p.op_lucario)
                     or (USE_MEWTWO_VS_ARCHALUDON and p.op_archaludon))
    # ★相手が草弱点ならロケットラッシュが2倍。ワナイダーを主砲にする。
    #   カードデータの weakness を見るので、オーロンゲ系に限らず効く。
    if USE_WANAIDER_MAIN_VS_GRASS_WEAK and not p.mewtwo_main:
        p.wanaider_main = any(
            getattr(gh._CARD.get(c.id), "weakness", None) == E_GRASS
            for c in op_all)

    # フリーザーが「手札・ベンチ・バトル場のどこかにいるか」
    p.articuno_anywhere = bool(p.field_counts.get(ARTICUNO, 0)
                               or p.hand_counts.get(ARTICUNO, 0))
    # フリーザーがベンチにいる = レジストヴェールが効いていてベンチが安全。
    # このときはミュウツーex(HP280)を前に置く軸で戦う(ユーザー要望)。
    p.articuno_on_bench = any(c is not None and c.id == ARTICUNO
                              for c in (me.bench or []))
    # 相手が「ダメカンを乗せる」系のワザを使うデッキか(フーディン/ドラパルト)。
    # このときだけ、たねを前に立てる意味がある(効果を無効化できる)。
    p.op_damage_counter_deck = any(c.id in MEWTWO_AXIS_TARGETS for c in op_all)

    # 今の盤面数で撃つロケットラッシュの打点
    rush = p.rocket_count * 30

    # ★ボスで引っぱる相手の選び方(2026-07-26 ユーザー指摘)
    # 「倒しきれないのに育っている途中/育ったポケモンを引き出すと返り討ちに合う」
    # ので、**倒せる相手に限り、その中で最も強い(サイドが多くHPが高い)相手**を選ぶ。
    # 倒せる相手が一人もいなければ引き出さない(boss_target=-1)。
    #
    # 従来は ex に +40〜60、倒せるなら +50、さらに `-hp/40` で
    # **HPが低い方**を優先していた。これだと倒せないexを引き出しうるし、
    # 倒せる相手が複数いても弱い方を選んでしまう。
    # ★打点の基準は「入れ替わった後に殴る駒」(2026-07-28 ユーザー指摘)。
    #   サカキは自分のバトル場もベンチと入れ替えるのでベンチも候補。
    if USE_GIOVANNI_OPPONENT_CHECK:
        rush = max(rush, _best_attacker_damage(p, me))
    best = (-1, -1e9)
    for i, b in enumerate(op.bench or []):
        if b is None:
            continue
        d = gh._CARD.get(b.id)
        if b.hp > rush:
            continue                      # 今の打点で倒せない相手は引き出さない
        pz = (3 if d and d.megaEx else 2 if d and d.ex else 1)
        # 倒せる中で「最も強い」= サイドが多い > HPが高い(育っている)
        sc = pz * 1000.0 + (b.hp or 0)
        if getattr(d, "skills", None):
            sc += 300.0                   # 特性持ちを止められるなら更に良い
        if sc > best[1]:
            best = (i + 1, sc)
    p.boss_target = best[0]
    return p


# ---------------------------------------------------------------- スコアリング
def _bench_pokemon_count(me) -> int:
    return sum(1 for c in (me.bench or []) if c is not None)


E_GRASS, E_PSYCHIC, E_DARK, E_ROCKET, E_METAL = 1, 5, 7, 11, 8


def _energy_units(c):
    """付いているエネルギーの「個数」リスト。**手札のカードには energies が無い**。

    ★2026-07-28 の監査で発覚: `_frontline_score` が `card.energies` を無条件に
      見ていたため、**手札から場に出す場面(ゲーム開始時の場出し等)で
      AttributeError → agent 全体が generic にフォールバック**していた
      (60試合4108回中18回)。場出しの判断が丸ごと自前ロジックを通っていなかった。
    """
    return list(getattr(c, "energies", None) or [])


def _current_hp(c) -> int:
    """残りHP。**手札のカードには hp が無い**ので、その場合は最大HP(=無傷)。"""
    hp = getattr(c, "hp", None)
    if hp is None:
        d = gh._CARD.get(getattr(c, "id", None))
        hp = getattr(d, "hp", None) or 0
    return hp or 0


def _bench_ammo(me) -> int:
    """イレイザーボールでトラッシュできる「ベンチのエネ」の数(2で打ち止め)。

    テキストは「**ベンチの**ポケモンからエネを最大2個トラッシュし、1個につき+60」。
    **バトル場のエネは対象外**なので数えない。
    """
    n = 0
    for c in [x for x in (me.bench or []) if x]:
        n += len(getattr(c, "energies", None) or [])
        if n >= 2:
            return 2
    return n


def _erasure_plan(p: Plan, me) -> bool:
    """イレイザーボールを撃つ算段があるか(=ベンチのエネが「弾」として活きるか)。

    ★ミュウツーexのパワーセーバーは「場のロケット団4体以上」でないと攻撃できない。
      さらに超系2個(ロケット団エネ1枚で足りる)+1個が要る。
      その見込みが無いのにワナイダーへエネを積むのは純粋な無駄
      (実測: エネ4個まで積んでイレイザーボール0回)。
    """
    if p.rocket_count < 4:
        return False
    for c in ([x for x in (me.active or []) if x]
              + [x for x in (me.bench or []) if x]):
        if c.id != MEWTWO_EX:
            continue
        en = _energy_units(c)
        psy = sum(1 for e in en if e in (E_PSYCHIC, E_DARK, E_ROCKET))
        # 既に撃てる、または手札のロケット団エネ1枚で撃てる形になる
        if psy >= 2 or p.hand_counts.get(ROCKET_ENERGY):
            return True
    return False


def _can_attack_now(card, p: Plan, n_bench: int) -> bool:
    """その個体が今バトル場に出たら実際にワザを撃てるか。

    ★`card.energies` は**エネルギーの「個数」**のリスト(型番号)であって
      カード枚数ではない(2026-07-28 リプレイで確認)。
      ロケット団エネ1枚は `[11, 11]` の**2個**として入る。
      従来コードは「エネ2個以上ならミュウツーは撃てる」としていたが、
      イレイザーボールは[超,超,無]の**3個**必要で、これは過大評価だった。
    さらに**型**も見る必要がある:
      ロケットラッシュ  [草,無]     … 草が1個以上ないと撃てない
                                    (ロケット団エネは超/悪しか出さない)
      イレイザーボール  [超,超,無]  … 超/悪系が2個以上ないと撃てない
                                    (草だけ3個では撃てない)
    """
    en = _energy_units(card)
    if card.id == SPIDOPS:
        return sum(1 for e in en if e == E_GRASS) >= 1 and len(en) >= 2
    if card.id == MEWTWO_EX:
        # ★イワパレスが前なら ex のワザは通らない = 実質「撃てない」
        if USE_CRUSTLE_AWARE and p.op_crustle_active:
            return False
        psy = sum(1 for e in en if e in (E_PSYCHIC, E_DARK, E_ROCKET))
        # パワーセーバー: 場のロケット団4体以上でないと攻撃できない
        return (p.rocket_count >= 4 and psy >= 2 and len(en) >= 3
                and n_bench >= 3)
    return False


def _can_attack_next_turn(card, p: Plan, n_bench: int) -> bool:
    """★撃破されて前を埋める場面は、**直後に自分のターンが来る**ので
    「今すぐ撃てるか」ではなく「次のターンに撃てるか」で選ぶ(2026-07-28 ユーザー指摘)。

    次のターンに足せるのは:
      - 手張り1回(手札のエネ。ロケット団エネは2個ぶん)
      - ワナイダーならチャージアップ(トラッシュの基本エネを自身に。手張りとは別枠)
    例: ロケット団エネ付きミュウツー(超系2個)+ 手札に草 → 3個になって撃てる。
        草1個のワナイダー + トラッシュに基本エネ → チャージアップで2個になって撃てる。
    """
    en = _energy_units(card)
    t = len(en)
    hc = p.hand_counts
    has_grass = hc.get(GRASS_ENERGY, 0) > 0
    has_rocket = hc.get(ROCKET_ENERGY, 0) > 0
    has_psychic = hc.get(PSYCHIC_ENERGY, 0) > 0

    if card.id == SPIDOPS:
        g = sum(1 for e in en if e == E_GRASS)
        # 手張り(1回だけ)
        if has_grass:
            g, t = g + 1, t + 1
        elif has_rocket:
            t += 2               # ロケット団エネは超/悪なので草は増えない
        # チャージアップ(トラッシュの基本エネ。手張りとは別枠)
        if p.discard_basic_energy > 0:
            g, t = g + 1, t + 1
        return g >= 1 and t >= 2

    if card.id == MEWTWO_EX:
        if p.rocket_count < 4 or n_bench < 3:
            return False         # パワーセーバー
        psy = sum(1 for e in en if e in (E_PSYCHIC, E_DARK, E_ROCKET))
        if has_rocket:
            psy, t = psy + 2, t + 2
        elif has_psychic:
            psy, t = psy + 1, t + 1
        elif has_grass:
            t += 1
        return psy >= 2 and t >= 3
    return False


def _frontline_score(card, p: Plan, me, after_ko: bool = False):
    """バトル場が空いたとき、ベンチのミュウツー/ワナイダーを「攻撃力で比較」して
    出す方を決めるスコア。ミュウツー/ワナイダー以外なら None。

    - ミュウツーex: 自身含めベンチ3以上で候補。イレイザーボール=160
      (発火条件: 場のロケット団4匹以上 + エネ2個以上=ロケット団エネは超悪2個ぶん)。
      **エネ2個以上ならワナイダーより優先。**
    - ワナイダー(ワナイダー): 自身含めベンチ4以上で候補。
      ロケットラッシュ=30×場のロケット団数。
    どちらの候補条件も満たすときは攻撃力(160 vs 30×匹数)が高い方が勝つ。
    撃てば勝ち(相手をKO)なら最優先。"""
    n_bench = _bench_pokemon_count(me)
    field_rockets = p.rocket_count    # 誰を前に出しても場のロケット団数は不変

    # ★2026-07-28 ユーザーのリプレイ(88613386)から発覚した致命的な選択ミス。
    #   12ターン目、バトル場が倒されて入れ替える場面で
    #     ミュウツーex **HP10** ・エネ1(3個必要なので撃てない)  ← これを選んだ
    #     ワナイダー   HP130 ・エネ2(ロケットラッシュが撃てる)
    #   となり、瀕死で攻撃もできないミュウツーexを前に出してサンドバッグになった。
    #   exなので倒されるとサイド2枚を渡す。
    #   原因: このスコアが**残りHPを一切見ておらず**、しかも
    #   「撃てないミュウツー(2200)」が「撃てるワナイダー(1180)」に勝っていた。
    #   → 「撃てるか」を最優先し、撃てないなら**残りHPで壁として評価**する。
    # ★この関数は「ミュウツー/ワナイダー以外は None」を返す契約。
    #   新ブロックを前に置いたとき対象を絞り忘れ、**フリーザーやミミッキュにも
    #   適用されて `_placement_bonus` の既存ルール(フリーザーは前に出さない等)を
    #   潰していた**(2026-07-28)。必ずここで弾く。
    if card.id not in (MEWTWO_EX, SPIDOPS):
        return None

    if USE_FRONTLINE_CAN_ATTACK:
        n_energy = len(_energy_units(card))
        hp = _current_hp(card)
        d0 = gh._CARD.get(card.id)
        prizes = 3 if (d0 and d0.megaEx) else 2 if (d0 and d0.ex) else 1
        can_fire = _can_attack_now(card, p, n_bench)
        # ★実効打点(弱点2倍 → 抵抗力/フルメタルラボの-30)で評価する。
        #   素点だと「前に出せば倒せる」と誤判定して、倒せない相手に
        #   駒を差し出すことになる(2026-07-29 ユーザー指摘)。
        power_full = (_vs_active(160.0, E_PSYCHIC, p) if card.id == MEWTWO_EX
                      else _vs_active(30.0 * field_rockets, E_GRASS, p))
        power = power_full if can_fire else 0.0


        # ★撃破されて前を埋める場面は、直後に自分のターンが来るので
        #   「次のターンに撃てるか」で選ぶ(2026-07-28 ユーザー指摘)。
        #   逃げ/サポートでの交代(バトル場が空でない)は今のターンの話なので
        #   従来どおり「今すぐ撃てるか」で判断する。
        if after_ko and USE_NEXT_TURN_FRONTLINE:
            if _can_attack_next_turn(card, p, n_bench):
                sc = 5000.0 + power_full + hp * 2.0
                if prizes >= 2:
                    # 削れたexは倒されるとサイド2枚。同じ撃てるなら硬い方。
                    sc -= (280 - hp) * 3.0
                return sc
            # 次のターンも撃てないなら下の「捨て駒」判定へ

        if can_fire and p.op_active is not None and p.op_active_hp <= power:
            return 9000.0 + power         # 出せば倒せる。最優先

        # ★対メガユキメノコex: うらみのハミングで落ちる圏なら、
        #   ミュウツーex(サイド2枚)を前に置かない(2026-07-29 ユーザー要望)。
        #   ハミングは手札1枚につき50。HP280のミュウツーは手札6枚で落ち、
        #   落ちると**サイドを2枚**渡す。同じ落ちるならサイド1枚の駒を出す。
        #   逆に落ちない圏(手札5枚以下)では HP280 が最も硬い壁なので触らない。
        #   ※ 判定は「今の手札」ではなく**無条件**にする(2026-07-29 実測)。
        #     前線を選ぶのはKO直後=自分の番の頭で、そのときの手札はまだ小さい。
        #     手札枚数で条件を付けると規則が発火せず、
        #     ミュウツーexが前に出る回数はむしろ 21→29 に増えた。
        #     殴られるのは**ターンを渡した後**なので、そこを基準にする。
        if (USE_FROSLASS_CHEAP_FRONT and p.op_froslass and prizes >= 2):
            return 300.0
        if can_fire and not after_ko:
            return 5000.0 + power         # 撃てる駒は撃てない駒より必ず上
        # ★撃てないなら「倒されるのが確定」なので、**一番安い捨て駒**を出す。
        #   最初は「HPが高い方が良い壁」と考えたが、上位勢の実測は逆だった:
        #   誰も撃てない96場面での選択は
        #     ミミッキュHP60 21回 / タマンチュラHP50・20 23回 /
        #     ワナイダーHP130 10回 / フリーザー4回 / **ミュウツーex 4回だけ**
        #   に対し、うちは**ミュウツーex(HP280)を24回**出していた。
        #   exは倒されるとサイド2枚。前に出して耐えても得はなく、
        #   サイド1枚の駒を差し出す方が損が小さい。
        if prizes >= 2:
            return 200.0                  # exは前に出さない
        sc = 900.0 + hp * 0.5             # サイド1枚。同格ならHPで僅差
        if (USE_MEWTWO_AXIS and card.id == MEWTWO_EX
                and p.articuno_on_bench and p.op_damage_counter_deck):
            sc += 600.0
        return sc

    if card.id == MEWTWO_EX:
        if n_bench < 3:               # 自身含めベンチ3未満は候補外
            return 400.0
        n_energy = len(_energy_units(card))
        can_fire = field_rockets >= 4 and n_energy >= 2
        eb = _vs_active(160.0, E_PSYCHIC, p)      # 実際に通る打点
        if can_fire and p.op_active is not None and p.op_active_hp <= eb:
            return 6000.0             # 撃てば勝ち
        power = eb if can_fire else 0.0
        # ★フリーザーがベンチにいるならミュウツー軸で戦う(ユーザー要望)
        # レジストヴェールでベンチのたねロケット団がワザの効果を受けないので、
        # 後続(タマンチュラ→ワナイダー)を安全に育てられる。その間、
        # HP280のミュウツーexが前で受けるのが最も硬い。
        if USE_MEWTWO_AXIS and p.articuno_on_bench and p.op_damage_counter_deck:
            if n_energy >= 2:
                return 5200.0 + power     # ワナイダー(最大5500)と競える水準
            return 2200.0 + power         # 育成中でも前を任せる価値がある
        if n_energy >= 2:
            return 4500.0 + power     # エネ2個以上ならワナイダーより優先
        return 1000.0 + power
    if card.id == SPIDOPS:
        # ロケットラッシュの打点(弱点・抵抗力・フルメタルラボ込み)
        power = _vs_active(30.0 * field_rockets, E_GRASS, p)
        if n_bench < 4:               # 自身含めベンチ4未満でも主砲として出す価値は残す
            return 1500.0
        n_energy = len(_energy_units(card))
        if n_energy >= 2 and p.op_active is not None and p.op_active_hp <= power:
            return 5500.0             # 撃てば勝ち
        return 1000.0 + power
    return None


def _bonus(o, obs: Observation, state, me, op, p: Plan, ctx=None) -> float:
    t = o.type
    hc = p.hand_counts

    # 山札切れの回避。引きすぎると次の番のドローができずに負ける。
    if USE_DECK_SAFETY and t == OptionType.PLAY:
        c = gh._hand_card(obs, o.index, me)
        deck_left = me.deckCount or 0
        cost = _DECK_COST_PLAY.get(c.id, 0) if c is not None else 0
        # ★残りがこれ以下なら、詰んでいようと任意のドローはしない。
        #   引いた枚数ぶん自分の番のドローが消えて、そのまま負ける。
        if cost > 0 and deck_left <= HARD_DECK_FLOOR:
            return -8000.0
        if c is not None and cost > p.safe_draws:
            # ★殴れる駒が今も次も無いなら、引かない方が確実に負ける。
            #   山札切れのリスクを取ってでも引き直す(2026-07-29 ユーザー指摘)。
            #   ただし山札が DRAW_WHEN_STUCK_MIN_DECK 以下では認めない。
            if not (USE_DRAW_WHEN_STUCK and c.id in (LILLIE, ATHENA)
                    and _no_attacker_at_all(p, me)
                    and deck_left > DRAW_WHEN_STUCK_MIN_DECK):
                return -8000.0


    # ---- ワザ ----
    # 上位は攻撃9%。KOできるなら即、できないなら盤面を広げてから殴る。
    if t == OptionType.ATTACK:
        # ★イワパレス(345)の判定は**いちばん先に**置く(2026-07-29 実測)。
        #   下の USE_ACT_BEFORE_ATTACK は早期 return するので、その後ろに
        #   置いていると「準備が残っている局面」でこの判定を飛ばしていた
        #   (-9000 にしても 14→3 で 3回残ったのはこの経路)。
        if (USE_CRUSTLE_AWARE and p.op_crustle_active
                and o.attackId == ATK_ERASURE_BALL):
            return CRUSTLE_ATTACK_SCORE
        # ★攻撃はターンを終わらせるので、**先にやれることを全部やる**
        #   (2026-07-27 ユーザー指摘)。実測で攻撃198回のうち、エネ付けできた
        #   のが114回・進化65回・特性61回あり、それらを捨てて殴っていた。
        #   同じターンにできる有益な準備が残っているなら攻撃を後回しにする。
        # ★「準備が残っているなら攻撃を後回し」だが、**実際にその準備を選べる
        #   選択肢が今あるときだけ**にする(2026-07-27 ユーザー指摘)。
        #   従来は手札の中身だけで判定していたため、選択肢に出ていない準備
        #   (=実行不可能)でも攻撃を -3000 して**攻撃せずEND**していた。
        #   実測: 攻撃できる768局面のうち9回、完成したミュウツーex(エネ3)が
        #   相手HP210に攻撃せずターンエンドしていた。
        if USE_ACT_BEFORE_ATTACK and _setup_option_available(obs, p, me, state):
            # 準備を優先するが、**ENDより下げない**。下げると「準備もできず
            # 攻撃もせずターンエンド」という最悪の手になる(実測で発生)。
            # END は base=10 なので、それを確実に上回る小さい正の値にする。
            return -1120.0 + 200.0
        aid = o.attackId
        # ★素点でなく**実効打点**で倒せるかを判定する(2026-07-29 ユーザー指摘)
        rush = _vs_active(p.rocket_count * 30.0, E_GRASS, p)
        if aid == ATK_ROCKET_RUSH:
            lethal = p.op_active is not None and p.op_active_hp <= rush
            # go-wideデッキ。盤面が狭いうちに弱いロケットラッシュで小型を早撃ち
            # すると、盤面が育たず打点も伸びない(実測: 汎用は盤面4.0まで広げて
            # 勝つのに、専用は盤面3.2で早撃ちして負けが増えた)。
            # 盤面が十分広い(WIDE_ENOUGH以上)ときだけ攻撃を優先する。
            wide_enough = p.rocket_count >= WIDE_ENOUGH
            if SETUP_BEFORE_ATTACK and not (lethal and wide_enough):
                return ATTACK_DEVELOP_SCORE
            return 5000.0 + rush
        if aid == ATK_ERASURE_BALL:
            # ★イワパレスが前にいるとミュウツーex(ex)のワザは**0ダメージ**。
            #   撃つだけ無駄なので、ロケットラッシュ/交代に譲る
            #   (2026-07-29 ユーザー指摘。メガガルーラもイワパレスを積む)。
            if USE_CRUSTLE_AWARE and p.op_crustle_active:
                # ★-2000 では足りなかった(2026-07-29 実測)。
                #   総合スコアは generic のベース + このボーナスで、
                #   generic は ATTACK に `1000 + 打点×2`(倒せると更に +2000以上)を
                #   与える。イレイザーボールは打点160扱いなので base は 3300 前後あり、
                #   -2000 を足しても正のままで **END(10) に勝ってしまっていた**。
                #   実測: イワパレス(345)がバトル場にいるのに20試合で14回撃っていた。
                return CRUSTLE_ATTACK_SCORE

            lethal = (p.op_active is not None
                      and p.op_active_hp <= _vs_active(160.0, E_PSYCHIC, p))
            if SETUP_BEFORE_ATTACK and not lethal:
                return ATTACK_DEVELOP_SCORE
            return 4800.0
        if aid == ATK_DARK_FROST:
            return min(1200.0, ATTACK_DEVELOP_SCORE) if SETUP_BEFORE_ATTACK else 1200.0
        if aid == ATK_TORMENT:
            # ワザロック。相手の主砲を止める価値。序盤の繋ぎ。
            return 900.0 if p.rocket_count < 4 else -500.0
        if aid == ATK_TAKE_DOWN:
            return 600.0 if not p.spidops_active else -800.0
        return -800.0

    # ---- 特性(チャージアップ: トラッシュから基本エネをワナイダーに) ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            # ABILITY の選択肢は playerIndex=None のことがあり _get_card が
            # None を返す。area から自分の場を直接引いて補完する。
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    card = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    card = me.bench[o.index or 0]
                elif o.area == AreaType.STADIUM and state.stadium:
                    # ★スタジアムを見ていなかった(2026-07-28 判明)。
                    card = state.stadium[0]
            except (IndexError, TypeError):
                card = None

        # ★ロケット団のファクトリーの特性を一度も使っていなかった。
        #   テキスト:「各プレイヤーの番に1回、そのプレイヤーが名前に
        #   『ロケット団』とつくサポートを手札から使っていたなら、2枚引く」。
        #   flgとの同一観測比較で **提示253回に対し flg 59.7% / うち 5.5%**。
        #   原因は (a) area=STADIUM を補完していなかったので card=None、
        #   (b) ABILITY 分岐がワナイダー以外を一律 0.0 にしていた、の2つ。
        #   タダの2ドローなので、山札が持つ限り毎ターン使う。
        if USE_FACTORY_DRAW and card is not None and card.id == FACTORY:
            if p.safe_draws >= 2:
                return FACTORY_DRAW_SCORE
            return -1500.0          # 山札切れが近いなら引かない

        if card is not None and card.id == SPIDOPS:
            # ★その個体が使ったかを見る(場に複数いればそれぞれ1回使える)
            if USE_CHARGE_UP and (o.area, o.index) not in _used_chargeup_slots:
                # ★足りている個体には使わない(2026-07-26 ユーザー指摘)
                # チャージアップは「トラッシュから基本エネを**自身に**付ける」。
                # ロケットラッシュは[草,無]の2個で撃てるので、既に2個ある個体に
                # 使うのは無駄(実測でワナイダーのエネ3個以上が多発していた)。
                # ★上限を2→3に緩めた(2026-07-28、flgとの機序比較)。
                #   1ターンあたりのチャージアップ使用が flg 0.275 に対し
                #   うち 0.150(0.54倍)で、この門が主因だった。
                #   ロケットラッシュは[草,無]の2個で足りるが、**ベンチのエネは
                #   イレイザーボールの弾**(ベンチのエネを最大2個トラッシュして
                #   +60ずつ)なので3個目は無駄ではない。しかもチャージアップは
                #   トラッシュから拾う回収なので、打っても手札を消費しない。
                # ★上限は「イレイザーボールを撃つ算段があるか」で変える
                #   (2026-07-29 ユーザー指摘)。実戦(88698945)で
                #   **ワナイダーにエネ4個まで積んだのにイレイザーボール0回**という
                #   完全な無駄が出ていた。ロケットラッシュは[草,無]の2個で足り、
                #   3個目以降は「ベンチのエネをトラッシュして+60」の弾としてしか
                #   意味がない。ミュウツーexが場にいて撃てる算段があるときだけ積む。
                # ★イレイザーボールは「**ベンチの**ポケモンからエネを最大2個
                #   トラッシュして+60ずつ」。つまり**バトル場に積んだエネは
                #   弾として一切使えない**(2026-07-29 ユーザー指摘、テキストで確認)。
                #   しかもバトル場は倒されやすく、積むほど失う量が増える。
                #   → 3個目以降を許すのは**ベンチにいる個体だけ**。
                on_bench = (o.area == AreaType.BENCH)
                cap = (CHARGEUP_MAX_ENERGY
                       if (on_bench and _erasure_plan(p, me))
                       else CHARGEUP_BASE_MAX)
                if USE_ATTACK_ENABLING_ATTACH and (
                        len(card.energies or []) >= cap):
                    return -1500.0
                return 3000.0                 # 毎ターン使う。無料の加速
            return -2000.0
        return 0.0

    # ---- 進化(タマンチュラ→ワナイダー) ----
    if t == OptionType.EVOLVE:
        # ★gh._get_card は EVOLVE の選択肢で **必ず None を返す**(2026-07-28 判明)。
        #   EVOLVE の option は {area:HAND, index, inPlayArea, inPlayIndex} で
        #   **playerIndex を持たない**ため。実測: 771件すべて None、
        #   一方 _hand_card は全件で id=401(ワナイダー)を返した。
        #   つまり**この分岐は丸ごと死んでおり、進化は常に下の 1000.0 固定**だった。
        #   ABILITY/ATTACH で既に踏んだのと同じ罠。
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        if card is not None and card.id == SPIDOPS:
            # ベンチ狙撃してくる相手(オーロンゲex シャドーバレット=バトル場180+
            # ベンチ1体に30)には、タマンチュラ(HP50)がベンチに置きっぱなしだと
            # 30ダメージ2発で落ちる。実測で失ったポケモンの最多がタマンチュラ66体で、
            # 負けの94%が場切れだった。HP130のワナイダーに上げれば4発必要になる。
            # → 狙撃相手のときは、たね展開(5200)より進化を優先する。
            # ★2026-07-28 flgとの差分。進化できる275局面で flg 57.5% 進化に対し
            #   うちは24.4%で、53.8%はカードを出す方に流れていた(flgは16.7%)。
            #   3200 は「たね展開 5200」に負けており、主砲が立たなかった。
            # ★100ダメージ級の狙撃(キチキギスex Cruel Arrow)が相手にいるときは、
            #   **進化より頭数**(2026-07-28、上位勢の実測)。
            #   ロケットラッシュは30×盤面数なので、たねを1体足すと打点が+30。
            #   進化はその1体を守るだけで打点は増えない。しかも対フーディンは
            #   ミュウツーex軸なのでワナイダーは主砲ではない。
            #   実測(進化とたね展開が両方できる局面での上位勢の選択):
            #     キチキギスex入り … 進化17% / たね展開50%
            #     それ以外        … 進化45% / たね展開34%
            #   うちは相手を問わず進化73〜74%だった。
            if USE_HEAVY_SNIPE_CARE and p.op_heavy_sniper:
                return EVOLVE_SCORE_VS_HEAVY_SNIPER
            if USE_ANTI_SNIPE and p.op_sniper:
                return 5600.0
            return EVOLVE_SPIDOPS_SCORE      # 主砲を立てる
        return 1000.0

    # ---- エネルギー付け ----
    if t == OptionType.ATTACH:
        if not USE_ENERGY_ROUTING:
            return 500.0 if o.inPlayArea == AreaType.ACTIVE else 200.0
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
        dest_id = dest.id if dest else -1

        # ★どうぐ(cardType=2)も ATTACH として来る(2026-07-27 判明)
        # PLAY(type=7)には cardType 0/1/3/4 しか出ず、どうぐは **ATTACH(type=8)** で
        # エネルギーと同じ枠に混ざって来る。従来はここをエネ前提で処理していたため
        # **ヒーローマント/ブレイブバングルが一度も付けられていなかった**
        # (実測: 手札に持っている局面1202回で装着0回)。
        if cid is not None:
            _cd = gh._CARD.get(cid)
            if _cd is not None and _cd.cardType == 2:
                if cid == HYPNOTIZER and USE_HYPNOTIZER:
                    # バトル場に立つ(立つ予定の)駒だけに価値がある。
                    # ワナイダー: 主砲でありバトル場の常連。最優先。
                    # タマンチュラ: 序盤のバトル場役。進化しても引き継がれるので
                    #   実質ワナイダーに付けるのと同じ。
                    # ミュウツーex: ヒーローマント(HP+100)を優先したいので低め。
                    #   さいみん装置は「殴られてから」効くので、
                    #   きぜつでサイド2枚を渡すexに投資する価値は薄い。
                    # ★HPの高い駒に付ける(2026-07-29 ユーザー指摘)。
                    #   さいみん装置は「バトル場でダメージを受けたとき」に働くので、
                    #   **長く前に立てる駒ほど発動機会が多い**。
                    #   ミュウツーex(HP280)は最も硬く、ヒーローマントが
                    #   別の個体に付いているなら装着先として最適。
                    if dest_id == MEWTWO_EX:
                        return 2600.0 if o.inPlayArea == AreaType.ACTIVE else 2000.0
                    if dest_id == SPIDOPS:
                        return 2400.0 if o.inPlayArea == AreaType.ACTIVE else 1800.0
                    if dest_id == TAROUNTULA:
                        # HP50だがワナイダーに進化すると引き継がれる
                        return 2200.0 if o.inPlayArea == AreaType.ACTIVE else 1600.0
                    return -1500.0    # 殴られない/バトル場に出さない駒には無駄
                if cid == HERO_CLOAK:
                    # HP+100。ガイド通り**ミュウツーex**に付けたい(HP280→380)。
                    # 次点は主砲のワナイダー。
                    # ★攻撃役以外(ミミッキュ等)には付けない(2026-07-27 ユーザー指摘)
                    if dest_id == MEWTWO_EX:
                        return 2600.0
                    if dest_id == SPIDOPS:
                        return 1800.0
                    if dest_id == TAROUNTULA:
                        # ★キチキギスexの Cruel Arrow(100)がいる相手には、
                        #   HP50のタマンチュラが**1発で落ちる**。マント(+100)で
                        #   150になれば耐え、ロケットラッシュの頭数も守れる
                        #   (2026-07-28。上位勢もマントをタマンチュラに付けていた)。
                        if USE_HEAVY_SNIPE_CARE and p.op_heavy_sniper:
                            return 2000.0
                        return 600.0        # 進化後に引き継ぐ
                    return -1500.0
                if cid == BRAVE_BANGLE:
                    # 「ルールを持たないポケモン」限定なので**ミュウツーexには無効**。
                    # 非exのワナイダー(進化前のタマンチュラも可)に付ける。
                    # ★効果は「相手のバトル場のexへの打点+30」なので、
                    #   相手にexがいる時ほど価値が高い(2026-07-27 ユーザー指摘)。
                    # ★テキストは「相手の**バトル場**のex への打点+30」。
                    #   従来は「相手の場のどこかにexがいれば」で判定し、
                    #   1体もいなくても2400点付けていた。実測(1ターンあたり)で
                    #   flg 0.047 に対しうち 0.095 と2倍付けていた原因。
                    def _is_ex(c):
                        d0 = gh._CARD.get(c.id)
                        return d0 is not None and (d0.ex or d0.megaEx)
                    op_active_ex = any(_is_ex(c) for c in (op.active or []) if c)
                    op_bench_ex = any(_is_ex(c) for c in (op.bench or []) if c)
                    if dest_id == SPIDOPS:
                        if op_active_ex:
                            return 3200.0      # 今すぐ+30が乗る
                        if op_bench_ex:
                            return 1600.0      # 出てくれば乗る
                        return 400.0           # ex不在なら完全に死に札
                    if dest_id == TAROUNTULA:
                        if op_active_ex:
                            return 1400.0
                        return 500.0 if op_bench_ex else -600.0
                    return -2000.0
                return 200.0

        # ★「これを付けたら攻撃できるようになる」付け方を最優先(2026-07-26 ユーザー指摘)
        # 実戦で「バトル場のミュウツーがロケ2個で、あと草1枚で撃てる場面なのに
        # ベンチのワナイダーに付けて攻撃機会を逃す」ことがあった(実測34回)。
        # 各ワザのコストは:
        #   ワナイダー ロケットラッシュ [草,無]   = **2個で撃てる**
        #   ミュウツーex イレイザーボール [超,超,無] = 3個。ロケット団エネは
        #     超/悪2個ぶんなので **ロケ2個 + 何か1個** で撃てる
        dest_n = len(dest.energies or []) if dest else 0
        if USE_ATTACK_ENABLING_ATTACH and dest is not None:
            need = _energy_need(dest)
            # ★「まだ足りていない」個体に限る。dest_n >= need なら既に撃てるので
            #   付ける意味がない(ここを見ないと2個持ちのワナイダーにも付けて
            #   3個以上の過剰が 6%→19% に増えた)。
            if (need > 0 and dest_n < need and dest_n + 1 >= need
                    and o.inPlayArea == AreaType.ACTIVE):
                # これを付ければバトル場が今すぐ撃てる形になる
                if cid == ROCKET_ENERGY and dest_id not in ROCKET_POKEMON:
                    pass                      # ロケット団以外に付けると即トラッシュ
                elif (USE_GRASS_FIRST_FOR_SPIDOPS and cid == ROCKET_ENERGY
                      and dest_id in (SPIDOPS, TAROUNTULA)
                      and hc.get(GRASS_ENERGY, 0) > 0):
                    # ★手札に草があるならワナイダー系には草を使う
                    #   (2026-07-29 ユーザー指摘)。ここも上と同じ「先に4000で
                    #   return してしまう」経路で、下のロケット団エネ専用の
                    #   分岐に到達していなかった。
                    pass
                elif (USE_ROCKET_ENERGY_FOR_MEWTWO and cid == ROCKET_ENERGY
                      and dest_id != MEWTWO_EX
                      and (any(c is not None and c.id == MEWTWO_EX
                               and len(c.energies or []) < 3
                               for c in ([x for x in (me.active or []) if x]
                                         + [x for x in (me.bench or []) if x]))
                           or hc.get(MEWTWO_EX))):
                    # ★ここが「ロケット団エネがワナイダー系に流れる」主因だった
                    #   (2026-07-28)。この分岐は「付ければ今すぐ撃てる」を
                    #   **エネの種類を問わず4000点**にしていたため、
                    #   バトル場のタマンチュラ/ワナイダーにロケット団エネを
                    #   使ってしまっていた(下のロケット団エネ専用の分岐に
                    #   到達すらしていなかった)。
                    #   ロケット団エネはイレイザーボールの要(超悪2個ぶん)で、
                    #   しかも改造ハンマーの的。ミュウツーが欲しがっているなら温存する。
                    pass
                else:
                    return 4000.0

        # ロケット団エネルギーはミュウツーex(超超無)に回すと強い。
        if cid == ROCKET_ENERGY:
            if dest_id == MEWTWO_EX:
                # ★超枠が既に埋まっているなら、残りは**無色1個**なので
                #   草で足りる。ロケット団エネは2個ぶんなので1個が無駄になり、
                #   しかも改造ハンマー(特殊エネを1枚トラッシュ)の的が増える。
                #   実測: 上位勢は草で完成させていた。
                if USE_ROCKET_ENERGY_ONLY_WHEN_NEEDED and dest is not None:
                    psy = sum(1 for e in _energy_units(dest)
                              if e in (E_PSYCHIC, E_DARK, E_ROCKET))
                    # ★「草に譲る」のは**草が実際に手札にあるとき**だけ
                    #   (2026-07-29 ユーザー指摘)。手札がロケット団エネしか
                    #   無いのに下げると、**イレイザーボールを撃てるはずの
                    #   ターンを丸ごと逃す**。手張りは1ターン1回しかない。
                    cheaper = hc.get(GRASS_ENERGY, 0) > 0 or hc.get(PSYCHIC_ENERGY, 0) > 0
                    if psy >= 2 and cheaper:
                        return 300.0     # 超枠は足りている。草に譲る
                # ★付けても撃てないなら、基本エネを先に置く(上の注記参照)。
                #   代わりが手札に無いときは従来どおり付ける
                #   (手張りは1ターン1回なので、待つと丸ごと1ターン損)。
                if USE_ROCKET_ENERGY_LAST and dest is not None:
                    units_after = len(_energy_units(dest)) + 2
                    cheaper_in_hand = (hc.get(GRASS_ENERGY, 0) > 0
                                       or hc.get(PSYCHIC_ENERGY, 0) > 0)
                    if units_after < 3 and cheaper_in_hand:
                        return 300.0
                if dest_n < 3:
                    # ★対メガルカリオ/ブリジュラスはミュウツーexが主砲なので
                    #   エネを最優先で寄せる(p.mewtwo_main)
                    if p.mewtwo_main:

                        return MEWTWO_MAIN_ENERGY_SCORE
                    # ★相手が草弱点なら、まだ撃てないワナイダー系を先に完成させる
                    if p.wanaider_main and _spidops_line_unfueled(p, me):
                        return 900.0
                    return 1800.0

                return -500.0
            if dest_id in ROCKET_POKEMON:
                # ★ロケット団エネは**ミュウツーex専用**に取っておく
                #   (2026-07-28、上位ワナイダー勢の対フーディン戦から)。
                #   カードテキスト:「超と悪を好きな組み合わせで**2個ぶん**」。
                #   イレイザーボール[超,超,無] は ロケット団エネ1枚+草1枚で完成する。
                #   一方ロケットラッシュは[草,無]で、草は代用できないので
                #   ロケット団エネは**無の1枠しか埋められず1個ぶん無駄になる**。
                #   実測(同じ観測): ロケット団エネをワナイダー系に付けた回数は
                #   上位勢3回に対しうち13回だった。
                # ★手札に草があるなら草を使う(2026-07-29 ユーザー指摘)。
                #   ロケットラッシュは[草,無]。ロケット団エネは超/悪しか出さず
                #   無の1枠しか埋められないので**2個ぶんのうち1個が確実に無駄**。
                #   しかも改造ハンマー(特殊エネを1枚トラッシュ)の的になる。
                if USE_GRASS_FIRST_FOR_SPIDOPS and hc.get(GRASS_ENERGY, 0) > 0:
                    return -900.0
                if USE_ROCKET_ENERGY_FOR_MEWTWO:
                    mewtwo_wants = any(
                        c is not None and c.id == MEWTWO_EX
                        and len(c.energies or []) < 3
                        for c in ([x for x in (me.active or []) if x]
                                  + [x for x in (me.bench or []) if x]))
                    if mewtwo_wants or hc.get(MEWTWO_EX):
                        return -1200.0     # ミュウツーのために温存する
                    # ★ミュウツーが要らない場合でも、ワナイダー系に付けて良いのは
                    #   **それでこのターン撃てる形になるときだけ**。
                    #   ロケットラッシュは[草,無]で、草の枠はロケット団エネでは
                    #   埋められない(超/悪しか出ない)。つまり無の1枠を埋めるだけで
                    #   **2個ぶんのうち1個が確実に無駄**になり、しかも
                    #   改造ハンマー(特殊エネを1枚トラッシュ)の的になる。
                    n_grass = sum(1 for e in (dest.energyCards or [])
                                  if e.id == GRASS_ENERGY) if dest is not None else 0
                    if not (n_grass >= 1 and dest_n + 1 >= _energy_need(dest)):
                        return -900.0
                # ★足りている個体には付けない(ユーザー指摘)
                return 800.0 if dest_n < _energy_need(dest) else -800.0
            return -2000.0                    # ロケット団以外に付けると即トラッシュ
        # 草エネはワナイダーの草コスト(ロケットラッシュ)に。
        if cid == GRASS_ENERGY:
            # ★相手が草弱点(=ロケットラッシュ2倍)なら、ワナイダー系の
            #   未完成な個体を最優先で完成させる(2026-07-29 ユーザー要望)。
            if (p.wanaider_main and dest_id in (SPIDOPS, TAROUNTULA)
                    and dest_n < CHARGEUP_BASE_MAX):
                return WANAIDER_MAIN_ENERGY_SCORE
            if dest_id == SPIDOPS:
                # ★ロケットラッシュは[草,無]の2個で撃てる。3個目以降は無駄。
                #   実測で3個以上が705回(4個246回/5個193回)もあった。
                if dest_n >= 2:
                    # ★ベンチなら「イレイザーボールの弾」として意味がある。
                    #   ミュウツーexが撃てる算段があり、弾が2個に満たないときだけ
                    #   3個目を許す(バトル場には積まない)。
                    if (USE_BENCH_AMMO and o.inPlayArea == AreaType.BENCH
                            and dest_n < 4 and _erasure_plan(p, me)
                            and _bench_ammo(me) < 2):
                        return 1200.0
                    return -1000.0
                # ★**チャージアップで足りるなら手張りを使わない**
                #   (2026-07-29 ユーザー指摘)。手張りは1ターン1回の貴重な行動で、
                #   チャージアップは「トラッシュの基本エネを自身に」で無料。
                #   実戦(88698945)で、手札にロケット団エネがありベンチに
                #   ミュウツーexがいるのに、草をワナイダーへ手張りしていた。
                #   正しくは「特性で草を足し、手張りはロケット団エネを
                #   ミュウツーexへ」。
                if USE_CHARGEUP_COVERS_SPIDOPS and dest is not None:
                    # ★「その個体のチャージアップが今ターンまだ使えるか」も見る。
                    #   使用済みなら譲っても補充されないので手張りするのが正しい。
                    slot = ((AreaType.ACTIVE, 0) if o.inPlayArea == AreaType.ACTIVE
                            else (AreaType.BENCH, o.inPlayIndex or 0))
                    chargeup_left = slot not in _used_chargeup_slots
                    covered = (chargeup_left and p.discard_basic_energy > 0
                               and dest_n + 1 >= _energy_need(dest))
                    other_need = (p.hand_counts.get(ROCKET_ENERGY, 0) > 0
                                  and any(c is not None and c.id == MEWTWO_EX
                                          and len(_energy_units(c)) < 3
                                          for c in ([x for x in (me.active or []) if x]
                                                    + [x for x in (me.bench or []) if x])))
                    if covered and other_need:
                        return -800.0     # 特性に任せ、手張りはミュウツーへ
                return 2000.0
            if dest_id == TAROUNTULA:
                # 進化後に引き継ぐが、2個で足りるので前借りは1個まで
                return 1200.0 if dest_n < 1 else -600.0
            # ★攻撃に使わないポケモンには草を付けない(2026-07-27 ユーザー指摘)
            # ミミッキュ/フリーザー/ヤミカラス/ソーナンスは、このデッキでは
            # 「盤面の頭数」や「特性」が役割で、草エネでワザを撃つことはない
            # (実測でミミッキュに8回付けていた)。エネの完全な無駄。
            if dest_id in (MIMIKYU, ARTICUNO, MURKROW, WOBBUFFET):
                return -1500.0
            if dest_id == MEWTWO_EX:
                # ★超枠が埋まっていて残り1個(無色)なら、草で完成させるのが最安。
                if USE_ROCKET_ENERGY_ONLY_WHEN_NEEDED and dest is not None:
                    psy = sum(1 for e in _energy_units(dest)
                              if e in (E_PSYCHIC, E_DARK, E_ROCKET))
                    if psy >= 2 and dest_n < 3:
                        # これで撃てる形になる(ミュウツー主砲の相手はさらに優先)
                        return (MEWTWO_MAIN_ENERGY_SCORE
                                if p.mewtwo_main else 2200.0)
                # ★草はミュウツーには1個まで(2026-07-27 ユーザー指摘)
                # イレイザーボールは[超,超,無]。草が埋められるのは**無色枠1個だけ**で、
                # 2個目以降は超枠を埋められず完全な無駄
                # (実測: 草2個以上が7%、3個も2%あった)。
                n_grass = sum(1 for e in (dest.energyCards or [])
                              if e.id == GRASS_ENERGY)
                if n_grass >= 1:
                    return -1200.0
                if dest_n < 3:
                    return (MEWTWO_MAIN_ENERGY_SCORE
                            if p.mewtwo_main else 1500.0)
                return -500.0
            return 300.0
        # ※このデッキに基本【超】は**0枚**(草8/ロケット団エネ4のみ)。
        #   実質デッドコードだが、構築を変えたときのために残す(2026-07-29 実測)。
        if cid == PSYCHIC_ENERGY:
            if dest_id == MEWTWO_EX:
                # ★ミュウツー主砲の相手には超エネを最優先で寄せる
                return (MEWTWO_MAIN_ENERGY_SCORE
                        if p.mewtwo_main else 1400.0)
            return 200.0
        return 300.0

    # ---- 手札からのプレイ ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None
        d = gh._CARD.get(cid) if cid else None

        # ★フリーザーを対象デッキ相手にベンチへ置く(2026-07-26 ユーザー要望)
        # 特性レジストヴェール = 自分の場の**たね**ロケット団全員が、
        # 相手のワザの「効果」を受けない(**ダメージは効果ではない**)。
        # 4デッキの技を実際に調べた結果、防げるのは:
        #   ドラパルトex ファントムダイブ「ベンチにダメカン6個を置く」→ **効果なので防げる**
        # 防げないもの(いずれも「ダメージ」なので特性の対象外):
        #   オーロンゲex シャドーバレット「ベンチに30ダメージ」
        #   キチキギスex クルーエルアロー「100ダメージ」
        # → ドラパルト相手が本命だが、go-wideの頭数にもなるので指定4デッキで優先する。
        # ※ 実測すると**フリーザーは元から73〜87%出場していた**(go-wideの頭数として
        #   並ぶため)。そこで「対象デッキのときだけ僅かに優先度を上げる」に留める。
        #   大きく上げると他のたね展開を押し出し、対象外の相手(イワパレス)で
        #   出場率が 87%→73% に落ちる副作用が出た。
        if (USE_ARTICUNO_GUARD and cid == ARTICUNO and p.bench_free > 0
                and p.op_needs_guard):
            # ★対フーディン等の「ダメカンを乗せる」デッキでは、フリーザーの
            #   レジストヴェールが要になる(2026-07-28、上位勢の対フーディン戦から)。
            #   テキスト:「相手のポケモンのワザの効果を、自分の**たね**の
            #   ロケット団ポケモンが受けない」。フーディンのパワフルハンドは
            #   ダメカンを乗せる=効果なので、たね(ミュウツーex含む)が守られる。
            #   実測(同じ観測): フリーザーを出した回数は上位勢26回に対しうち10回。
            #   ※全体(全マッチ)では逆に出しすぎだったので、
            #     BASIC_PLAY_SCORE では低く抑えたまま**ここだけ上げる**。
            #   2枚目も置く価値がある(1枚目が倒されると特性ごと消えるため)。
            n_art = p.field_counts.get(ARTICUNO, 0)
            if n_art == 0:
                return 5400.0
            if n_art == 1 and USE_ARTICUNO_SECOND:
                # ★2体目は「ベンチに余裕があるとき」だけ(2026-07-29 ユーザー指摘)。
                #   実戦(対ドラパルト)で、既にフリーザーが1体いるのに2体目を出し、
                #   **ベンチが埋まってミュウツーexを出せなくなった**。
                #   レジストヴェールは場に1体いれば効くので、枠を潰す価値はない。
                if USE_ONE_ARTICUNO_ENOUGH:
                    others = (p.hand_counts.get(MEWTWO_EX, 0)
                              + p.hand_counts.get(TAROUNTULA, 0)
                              + p.hand_counts.get(SPIDOPS, 0))
                    if p.bench_free <= 1 or others > 0:
                        return 400.0      # 他の駒に枠を譲る
                return 3000.0     # 保険。ただしタマンチュラ(5200)より下
            return 200.0

        # 盤面を広げる: たねのロケット団を出すのが最優先(打点=盤面数)。
        if USE_GO_WIDE and d is not None and d.basic and cid in ROCKET_POKEMON:
            if p.bench_free > 0:
                # 上位勢は攻撃時の盤面が平均5.54(中央6)。自作は3.85で、しかも
                # 6割の攻撃はベンチに空きがある状態だった(=並べきる前に殴っている)。
                # 盤面が目標に届くまでは、たねを出すことを攻撃より確実に上に置く。
                if p.rocket_count < WIDE_ENOUGH:
                    # ★2026-07-28 flgとの差分。従来は**たねロケット団を全部
                    #   一律5200**にしていたため、タマンチュラとミミッキュ/
                    #   フリーザーが同格になり、ベンチが埋め草で埋まっていた。
                    #   同じ観測での採用率(flg ←→ うち):
                    #     タマンチュラ 68.9% ←→ 46.8%   (足りない)
                    #     ミミッキュ   17.5% ←→ 54.3%   (出しすぎ)
                    #     フリーザー   31.4% ←→ 70.5%   (出しすぎ)
                    #     ミュウツーex 37.3% ←→ 56.0%   (出しすぎ)
                    #   タマンチュラだけが「ワナイダーに進化して打点と
                    #   チャージアップになる」本命なので、役割で差を付ける。
                    sc_basic = BASIC_PLAY_SCORE.get(cid, 4200.0)
                    # ★ベンチ狙撃デッキ相手にミミッキュ(HP60)を並べすぎない
                    #   (2026-07-29 ユーザー指摘)。メガスターミーの
                    #   ジェッティングブローはベンチに50、キチキギスexは100。
                    #   すぐ落ちてサイドを渡すだけになる。
                    # ★条件に p.op_bench_snipe を追加(2026-07-29)。
                    #   注記どおりジェットブローを想定していたのに、
                    #   **メガスターミーが BENCH_SNIPERS に入っておらず**
                    #   対メガスターミーではこの規則が一度も発火していなかった。
                    if (USE_FEWER_FRAGILE_VS_SNIPER and cid == MIMIKYU
                            and (p.op_sniper or p.op_heavy_sniper
                                 or p.op_bench_snipe)
                            and p.field_counts.get(MIMIKYU, 0) >= 1):

                        # ★2体目は「頭数が足りないとき」だけ許す
                        #   (2026-07-29 ユーザー指摘)。ロケットラッシュの打点や
                        #   ミュウツーのパワーセーバー(場のロケット団4体以上)を
                        #   満たすためなら置く価値がある。
                        need_heads = p.rocket_count < 4      # パワーセーバー条件
                        # ガードが要るデッキ相手にフリーザーの枠を潰さない
                        if (p.op_needs_guard
                                and p.field_counts.get(ARTICUNO, 0) == 0
                                and p.bench_free <= 1):
                            need_heads = False
                        if not (need_heads and p.field_counts.get(MIMIKYU, 0) < 2):
                            sc_basic = 800.0
                    # ★ベンチ狙撃デッキ相手は「HPが低く、進化もしない駒」を
                    #   ベンチに置かない(2026-07-29 ユーザー要望)。
                    #   評価は**進化後のHP**で行う: タマンチュラはHP50でも
                    #   →ワナイダー130になるので本命のまま。ミミッキュ(60)と
                    #   ヤミカラス(80)は進化しないので、置くと的になるだけ。
                    if (USE_STURDY_BENCH_VS_SNIPER and p.op_bench_snipe
                            and EFFECTIVE_HP.get(cid, 999) < STURDY_HP_MIN):
                        # ただし盤面が極端に狭い(頭数2以下)ときは、
                        #   殴る駒すら足りないので置く。
                        if p.rocket_count >= STURDY_MIN_HEADS:
                            sc_basic = min(sc_basic, STURDY_BENCH_SCORE)

                    # ★フリーザーが既にベンチにいるなら2体目より他を優先
                    #   (2026-07-29 ユーザー指摘)。実戦で2体目のフリーザーが
                    #   ベンチ枠を埋め、ミュウツーexが出せなくなっていた。
                    #   レジストヴェールは**場に1体いれば効く**。
                    if (USE_ONE_ARTICUNO_ENOUGH and cid == ARTICUNO
                            and p.field_counts.get(ARTICUNO, 0) >= 1):
                        sc_basic = 700.0
                    # ★フリーザーが場に無いうちは、対フーディン等で
                    #   **ベンチを埋め切らない**(後からフリーザーを置けるように)
                    if (USE_KEEP_SLOT_FOR_ARTICUNO and p.op_needs_guard
                            and p.field_counts.get(ARTICUNO, 0) == 0
                            and cid != ARTICUNO
                            and p.hand_counts.get(ARTICUNO, 0) == 0
                            and p.bench_free <= 1):
                        sc_basic = min(sc_basic, 600.0)
                    # ★対フーディンでフリーザーがどこにも無いなら、
                    #   ミュウツーex(たね・サイド2枚)を先に出さない
                    #   (2026-07-29 ユーザー指摘)。パワフルハンドのダメカンは
                    #   レジストヴェールでしか止められず、無防備に晒すと
                    #   サイド2枚を献上するだけになる。ワナイダーを先に立てる。
                    #   ※「ワナイダーより下げる」であって「何より下げる」ではない。
                    #     手札にタマンチュラが無いときまで下げると、代わりに
                    #     ミミッキュ等の頭数を出してしまい総合が -5pp 悪化した
                    #     (2026-07-29 実測)。**代わりが手札にあるときだけ**下げる。
                    # ★対メガルカリオはミュウツーexが主砲(超弱点2倍で320)。
                    #   タマンチュラ(5200)より上げて先に場に出す
                    #   (2026-07-29 ユーザー要望)。
                    if (USE_MEWTWO_VS_LUCARIO and cid == MEWTWO_EX
                            and p.op_lucario):
                        sc_basic = max(sc_basic, MEWTWO_LUCARIO_PLAY_SCORE)
                    if (USE_MEWTWO_NEEDS_GUARD and cid == MEWTWO_EX
                            and p.op_fuudin and not p.articuno_anywhere
                            and p.hand_counts.get(TAROUNTULA, 0) > 0):
                        sc_basic = min(sc_basic, 1500.0)
                    return sc_basic
                return 2600.0
            return 200.0
        # ランス: たねロケット団を3枚サーチ = 盤面拡大エンジン
        if cid == LANCE:
            # ★手札にたねが1枚も無いなら最優先(2026-07-31 実測。上記参照)
            # ★ただし**盤面がまだ狭いときだけ**。頭数が足りているなら、
            #   3枚のたねより アテナ/リーリエ のドロー(エネ・グッズも引ける)が上。
            #   条件なしで最優先にすると対オーロンゲが 75.8%→70.4% に落ちた。
            if (USE_LANCE_WHEN_NO_BASIC and p.bench_free >= 1
                    and p.rocket_count < WIDE_ENOUGH
                    and not any(p.hand_counts.get(x) for x in ROCKET_BASICS)):
                return LANCE_NO_BASIC_SCORE
            return 2500.0 if p.bench_free >= 1 else 800.0

        # ロケット団サポート(ファクトリー2ドロー・レシーバー連鎖と噛む)
        if cid == ATHENA:
            # 全部ロケット団なら8枚。基本いつでも強い。
            return 2400.0
        if cid == RECEIVER:
            return 2000.0
        if cid == LAMBDA:
            return 1600.0
        if cid == GIOVANNI:
            # ★サカキは「自分のバトル場を**強制的に**ベンチと入れ替える」+
            #   「相手のベンチを引きずり出す」の2段構え(2026-07-27 ユーザー指摘)。
            #   従来は `not p.spidops_active` で判定していたため、
            #   **エネの付いた準備済みミュウツーが前にいるのに、エネ0の
            #   ワナイダーと交代してしまう**事故が起きていた。
            #   自分側の交代で損をしないことを先に確認する。
            # ★相手の場も見る(2026-07-28 ユーザー指摘)。
            #   サカキは相手の**ベンチ**から1体を引きずり出すので、
            #   前にいる相手を倒せる状況で使うと、その的を逃がしてしまう。
            # ★さいみん装置版限定: 相手のバトル場が**ねむり**なら動かさない
            #   (2026-07-29 ユーザー指摘)。サカキは相手のベンチを前に出すので、
            #   せっかく眠らせた相手を**元気な個体と交代させてしまう**。
            #   ねむりは相手の攻撃を止めている状態なので、そのまま維持する。
            if USE_KEEP_ASLEEP and getattr(op, "asleep", False):
                return -2500.0
            if USE_GIOVANNI_OPPONENT_CHECK:
                my_dmg = _our_active_damage(p, me)
                if (my_dmg > 0 and p.op_active is not None
                        and p.op_active_hp <= my_dmg):
                    # 今のバトル場を倒せる。サカキを使うと逃がすので使わない。
                    return -2500.0
                # ★引きずり出した相手を殴るのは「入れ替わった**後**の駒」なので、
                #   ベンチのアタッカーも含めた最大打点で判定する
                #   (2026-07-28 ユーザー指摘)。従来はバトル場の打点だけを見ており、
                #   **前が育っていないときに一切引きずり出せなかった**。
                # ★入れ替わった後に前に立つのは**ベンチの駒**なので、
                #   バトル場を含めない(2026-07-29 ユーザー指摘)。
                swap_dmg = _best_bench_attacker_damage(p, me)
                # ★前が撃てないなら、**倒せる的がいなくても**入れ替える価値がある
                #   (2026-07-29 ユーザー指摘)。攻撃できないターンを作るより、
                #   撃てる駒を前に出して殴った方が良い。
                #   引きずり出す相手が育っていない(エネ無し)なら尚更。
                if (USE_GIOVANNI_WHEN_STUCK and my_dmg <= 0 and swap_dmg > 0):
                    # ★ベンチのアタッカーが**今の相手を倒せる**なら、サカキで
                    #   引きずり出すと的が入れ替わって撃墜を逃す。
                    #   引きずり出す先も倒せるなら損はしないので、
                    #   「今の相手は倒せる / 引きずり出す先は倒せない」ときだけ避ける。
                    #   実測(2026-08-01、実戦123試合): サカキ73回のうち44回は
                    #   ベンチのアタッカーで今の相手を倒せた。ただしその**40回は
                    #   引きずり出す先も倒せていた**ので損はしていない。
                    #   残り4回がユーザー報告の「撃墜の見逃し」に当たる。
                    if (USE_GIOVANNI_KEEP_KO and p.op_active is not None
                            and swap_dmg >= p.op_active_hp
                            and _best_killable_bench(op, swap_dmg) is None):
                        return -2500.0
                    weak_target = any(
                        b is not None and len(_energy_units(b)) == 0
                        for b in (op.bench or []))
                    _sc = (GIOVANNI_STUCK_SCORE if USE_GIOVANNI_CALIBRATED
                           else _GIO_OLD[0])
                    return _sc + (600.0 if weak_target else 0.0)
                best = _best_killable_bench(op, swap_dmg)
                if best is not None:
                    if my_dmg <= 0:
                        # 前が撃てない → 「撃てる駒を前に出す」と
                        # 「倒せる的を引きずり出す」の二重の得。最優先。
                        return ((GIOVANNI_TARGET_SCORE if USE_GIOVANNI_CALIBRATED
                                 else _GIO_OLD[1]) + best[0] / 2.0)
                    # 前は撃てるが今の相手は倒せない(キチキギスex HP210 等)。
                    # 倒せる的に差し替える。
                    return ((GIOVANNI_TARGET_SCORE2 if USE_GIOVANNI_CALIBRATED
                             else _GIO_OLD[2]) + best[0] / 2.0)

            if USE_GIOVANNI_CARE:
                act = p.active
                act_ready = (act is not None and _energy_need(act) > 0
                             and len(act.energies or []) >= _energy_need(act))
                # ベンチに「今すぐ撃てる」ロケット団がいるか
                bench_ready = any(
                    b is not None and _energy_need(b) > 0
                    and len(b.energies or []) >= _energy_need(b)
                    for b in (me.bench or []))
                # 前が撃てる状態なのに、ベンチに撃てる駒がいない → 交代は純損
                if act_ready and not bench_ready:
                    return -2000.0
                # 前が撃てないなら、撃てる駒を前に出せる時だけ使う
                if not act_ready and bench_ready:
                    return 2000.0
                # 相手のベンチから倒せる的を引きずり出せるなら価値がある
                if p.boss_target > 0 and (act_ready or bench_ready):
                    return 1900.0
                return -500.0
            return 1900.0 if (not p.spidops_active or p.boss_target > 0) else 600.0
        if cid == APOLLO:
            hand = len(me.hand) if me.hand is not None else me.handCount
            return 1700.0 if hand <= 3 else -500.0
        # 展開グッズ
        if cid == POFFIN:
            return 2200.0 if p.bench_free >= 2 else 300.0
        if cid == LANCE:
            return 2500.0
        if cid == BUG_SET:
            return 1500.0
        if cid == POKE_PAD:
            return 1400.0
        if cid == ENERGY_TRANSFER:
            return 1100.0
        if cid == NIGHT_STRETCHER:
            # ★盤面が薄く手札にたねが無いなら、トラッシュから回収して建て直す
            if (USE_STRETCHER_REBUILD and p.bench_free >= 1
                    and not any(p.hand_counts.get(x) for x in ROCKET_BASICS)
                    and _basic_in_discard(me)):
                return STRETCHER_REBUILD_SCORE
            return 900.0
        if cid == FACTORY:
            # スタジアム。ロケット団サポートを使う番は2ドロー。維持したい。
            try:
                ours = bool(state.stadium) and state.stadium[0].id == FACTORY
            except (IndexError, AttributeError, TypeError):
                ours = False
            if ours:
                return -1500.0
            # ★サポートを使う前に張る(2026-07-27 ユーザー指摘)
            # ガイド:「ファクトリーを場に出しておくとロケット団サポートで+2ドロー」。
            # 従来は1300点で、アテナ(2400)やレシーバー(2000)より低かったため
            # **サポートを先に使ってしまい+2ドローを取り逃がしていた**
            # (実測: サポート413回中ファクトリー展開中は55回=13%だけ)。
            # このターンにロケット団サポートを使う予定があるなら、先に張る。
            # ★相手のスタジアムが出ているなら上書きする(2026-07-27)
            # 実測でサポート使用331回のうち **157回(47%)は相手のスタジアムに
            # 場所を取られていて** ファクトリーの+2ドローを使えていなかった。
            # スタジアムは1枚しか場に出ないので、張り替えれば相手の効果も消せる。
            other_stadium = False
            try:
                other_stadium = bool(state.stadium) and state.stadium[0].id != FACTORY
            except (IndexError, AttributeError, TypeError):
                other_stadium = False
            # ★USE_FACTORY_PRIORITY を先に見る(2026-07-28)。
            #   下の 2600 が先に return していたため、上げたスコアに
            #   到達せず採用率が 13.3%→22.6% までしか動かなかった。
            # ※ 以前の USE_FACTORY_FIRST(2600) / other_stadium(1800) の分岐は
            #   USE_FACTORY_PRIORITY を手前に置いた時点で**到達不能**になっていた
            #   (2026-07-28 のフラグ監査で検出)。役割は下の一本に統合した。
            if USE_FACTORY_PRIORITY:
                return FACTORY_PLAY_SCORE
            if not state.supporterPlayed and any(
                    hc.get(x) for x in ROCKET_SUPPORTERS):
                return 2600.0          # サポートを使う前に張ると+2ドロー
            if other_stadium:
                return 1800.0          # 相手のスタジアムを消せる
            return 1300.0
        if cid == LILLIE:
            # ★リーリエの決心は**手札を山札に戻して**引き直す(2026-07-28 ユーザー指摘)。
            #   つまり手札のエネもポケモンも**全部消える**。
            #   報告された事故: エネを付けられる場面でエネを付けず先にリーリエを
            #   使い、手札のエネが流れてしまった。
            #   → 「まだこのターンにやれることが残っていないか」を先に確認する。
            #   下の各分岐(主砲なし/エネ不足など)はどれも「引き直したい理由」を
            #   見ているだけで、**やり残しの有無を一切見ていなかった**ので、
            #   ここで一括してゲートする。
            # ※ ここでは弾かない。**順序で後ろに回す**方式にしている
            #   (agent() の USE_LILLIE_LAST を参照)。
            #   最初はここで -3000 して禁止したが、価値の低いグッズが手札に
            #   1枚あるだけでそのターン一生使えなくなり、
            #   使用回数が 88→47回(半減)まで落ちた。
            #   ユーザーの要望は「やれることを済ませてから使う」なので、
            #   禁止ではなく後回しが正しい。
            # 手札をシャッフルして6枚ドロー(サイドが6枚のままなら8枚)。
            # 上位構築は4枚積み(現行2枚)で、序盤の8枚ドローが展開の起点になる。
            hand = len(me.hand) if me.hand is not None else me.handCount
            my_prize = len(me.prize) if me.prize is not None else 6
            # ★主砲が場にも手札にも無いなら引き直す(2026-07-27 ユーザー指摘)
            # ミュウツーex/ワナイダー/タマンチュラのどれも無い手札は、
            # このデッキでは何も始まらない。実測で該当17局面すべてで
            # リーリエを使わずターンを渡していた。
            # ★対フーディンでフリーザーが手札・ベンチ・バトル場のどこにも
            #   無いなら、探しに行く価値がある(2026-07-29 ユーザー指摘)。
            #   レジストヴェールはパワフルハンド(ダメカン配置=効果)への
            #   唯一の対策で、これが無いとたねが一方的に削られる。
            if (USE_LILLIE_FIND_ARTICUNO and p.op_fuudin
                    and not p.articuno_anywhere):
                return 2750.0
            if USE_LILLIE_NO_CORE:
                core_on_field = any(
                    p.field_counts.get(x) for x in (MEWTWO_EX, SPIDOPS, TAROUNTULA))
                core_in_hand = any(
                    hc.get(x) for x in (MEWTWO_EX, SPIDOPS, TAROUNTULA))
                if not core_on_field and not core_in_hand:
                    return 3000.0
                # ★以下、ユーザー指定の追加条件(2026-07-27)
                # 手札のエネ枚数と、場に付いているエネの総数を数える
                n_energy_hand = sum(hc.get(e, 0) for e in
                                    (GRASS_ENERGY, ROCKET_ENERGY, PSYCHIC_ENERGY))
                field_energy = sum(
                    len(c.energies or [])
                    for c in ([x for x in (me.active or []) if x]
                              + [x for x in (me.bench or []) if x]))
                # (1) 手札のエネが2枚以下 かつ ポケモンが1枚も無い(トレーナーだけ)
                n_pokemon_hand = sum(
                    v for k, v in hc.items()
                    if (gh._CARD.get(k) is not None
                        and gh._CARD[k].cardType == 0))
                if n_energy_hand <= 2 and n_pokemon_hand == 0:
                    return 3000.0
                # (2) このターン、手札から何も使えない(=盤面を進められない)
                if not _has_pending_setup(p, me, state) and n_pokemon_hand == 0:
                    return 2900.0
                # (3) 場のポケモンにエネがあまり付いていない
                #     (主砲が1体も撃てる形になっていない = 打点が出ない)
                ready = any(
                    _energy_need(c) > 0 and len(c.energies or []) >= _energy_need(c)
                    for c in ([x for x in (me.active or []) if x]
                              + [x for x in (me.bench or []) if x]))
                if not ready and field_energy <= 1 and n_energy_hand == 0:
                    return 2800.0
            # ★ベンチが4体未満なら引き直す(2026-07-29 ユーザー要望)。
            #   ワナイダーが立っていても、ベンチにタマンチュラ/ミュウツーが
            #   いなければ盤面は進まない(ロケットラッシュの打点も伸びない)。
            #   ※ USE_LILLIE_LAST で順序は最後尾なので、
            #     「他にやることが無いターン」にだけ発動する。
            if USE_LILLIE_BENCH_THIN and len(me.bench or []) < LILLIE_BENCH_MIN:
                return 2700.0
            if my_prize >= 6 and hand <= 6:
                return 2300.0          # 8枚ドローできる序盤は強力
            return 1500.0 if hand <= 3 else -800.0
        if cid == ULTRA_BALL:
            # 手札2枚を捨ててポケモンをサーチ。盤面が狭いうちは展開札として価値が高い。
            hand = len(me.hand) if me.hand is not None else me.handCount
            if p.rocket_count < WIDE_ENOUGH and hand >= 4:
                return 1900.0
            return 300.0
        if cid in (HERO_CLOAK, BRAVE_BANGLE):
            return 1000.0 if p.spidops_active else 200.0
        # たね(進化元タマンチュラ等)は go-wide で既に高得点。その他は控えめ。
        if cid == TAROUNTULA:
            return 2400.0 if p.bench_free > 0 else 200.0
        return 0.0

    # ---- どうぐ(TOOL_CARD) ----
    # ※ どうぐは PLAY ではなく TOOL_CARD で来るため、PLAY分岐に書いた
    #    ヒーローマント/ブレイブバングルのスコアは**一度も評価されていなかった**
    #    (対オーロンゲ50試合で使用回数0)。ここで正しく扱う。
    if t == OptionType.TOOL_CARD:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None
        # 付け先を特定
        dest = None
        try:
            if o.inPlayArea == AreaType.ACTIVE and me.active:
                dest = me.active[o.inPlayIndex or 0]
            elif o.inPlayArea == AreaType.BENCH and me.bench:
                dest = me.bench[o.inPlayIndex or 0]
        except (IndexError, TypeError):
            dest = None
        dest_id = dest.id if dest else -1
        if cid == HERO_CLOAK:
            # HP+100。負けの大半は「並べたそばから狩られる場切れ」なので、
            # 主砲(ワナイダー)を落とされにくくする価値が高い。
            if dest_id == SPIDOPS:
                return 2000.0
            if dest_id in ROCKET_POKEMON:
                return 900.0
            return 100.0
        if cid == BRAVE_BANGLE:
            # ★付け先を主砲だけに限定する(2026-07-27 ユーザー要望)
            # 「ルールを持たないポケモンが持つと、相手のバトル場のexへの打点+30」。
            # ミュウツーexは**ルールボックス持ちなので効果を受けられない**
            # (ご要望では対象に含まれていたが、カード仕様上つけても無意味)。
            # → 有効なのは非exのワナイダー(進化後に引き継ぐタマンチュラも可)。
            if dest_id == SPIDOPS:
                return 1600.0
            if dest_id == TAROUNTULA:
                return 700.0
            return -2000.0        # それ以外には付けない(無駄なので)
        return 300.0

    # ---- 手札を捨てる場面(ハイパーボールのコスト等) ----
    # ★ユーザー指摘(2026-07-27): ハイパーボールで**手札のワナイダー2枚を捨てて
    #   ワナイダー1枚を得る**という無意味な行動をしていた。
    #   ガイド:「ハイパーボールで**基本エネルギーをトラッシュしながら**
    #   ワナイダーを手札に加えられると理想的」。
    #   草エネはワナイダーの特性チャージアップでトラッシュから拾い直せるので、
    #   捨てるコストが最も小さい。主砲や展開札は絶対に捨てない。
    if USE_DISCARD_CARE and ctx == SelectContext.DISCARD and o.area == AreaType.HAND:
        card = gh._hand_card(obs, o.index, me)
        if card is not None:
            cid = card.id
            if cid == GRASS_ENERGY:
                return 3000.0        # 最優先で捨てる(チャージアップで回収できる)
            if cid == ROCKET_ENERGY:
                return 500.0         # 超悪2個ぶん。草より惜しいが回収は可能
            # 主砲・進化元は捨てない
            if cid in (SPIDOPS, MEWTWO_EX, TAROUNTULA):
                return -3000.0
            # ★フリーザーは**2枚しかない防御の要**なので残す
            #   (2026-07-29、上位勢との差分から)。レジストヴェールは
            #   ダメカン系デッキ(フーディン/ドラパルト)への主要な対策。
            #   実測(ハイパーボールの捨て札28局面): フリーザーを捨てたのは
            #   **上位勢2回に対しうち7回**だった。
            if USE_DISCARD_KEEP_ARTICUNO and cid == ARTICUNO:
                return -2000.0
            # ★ランスは「たねロケット団3枚サーチ」。**盤面が広がった後は死に札**
            #   なので、上位勢は積極的に捨てていた(上位11回 vs うち2回)。
            #   アテナも4枚積みなので重複は惜しくない(上位6回 vs うち0回)。
            if USE_DISCARD_DEAD_SUPPORT:
                if cid == LANCE and (p.bench_free <= 0
                                     or p.rocket_count >= WIDE_ENOUGH):
                    return 1800.0    # 出す先が無い = 死に札
                if cid == ATHENA and p.hand_counts.get(ATHENA, 0) >= 2:
                    return 1600.0    # 4枚積みの重複
            # 展開・サーチの要も残す
            if cid in (LANCE, ATHENA, RECEIVER, FACTORY, POFFIN, ULTRA_BALL):
                return -1500.0
            # 重複しているサポート等は捨ててよい
            if p.hand_counts.get(cid, 0) >= 2:
                return 1500.0
            return 800.0

    # ---- 選択(サーチ先・入れ替え対象など) ----
    if t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        # 相手の場から選ぶ(サカキ等の引きずり出し)
        if o.playerIndex is not None and o.playerIndex != state.yourIndex:
            # ★boss_target(ベンチ位置)と選択肢indexの対応がずれることがあるので、
            #   **その候補を直接評価する**(2026-07-26 ユーザー指摘の修正)。
            #   方針: 「倒せる相手に限り、その中で最も強い(サイド多い>HP高い)」。
            #   倒しきれない相手を引き出すと返り討ちに合う。
            if USE_BOSS_TARGETING:
                # ★打点の基準は「入れ替わった後に殴る駒」。サカキは自分の
                #   バトル場もベンチと入れ替えるので、ベンチのアタッカーも
                #   候補になる(2026-07-28 ユーザー指摘)。
                #   従来は今のバトル場のロケットラッシュ固定で、
                #   前が育っていないと全候補が -1500 になっていた。
                rush = (_best_attacker_damage(p, me) if USE_GIOVANNI_OPPONENT_CHECK
                        else p.rocket_count * 30)
                d = gh._CARD.get(card.id)
                hp = card.hp or 0
                if hp > rush:
                    return -1500.0            # 倒せない相手は選ばない
                pz = (3 if d and d.megaEx else 2 if d and d.ex else 1)
                sc = 1500.0 + pz * 1000.0 + hp   # 強い相手ほど良い
                if getattr(d, "skills", None):
                    sc += 300.0
                return sc
            if p.boss_target > 0 and o.index == p.boss_target - 1:
                return 1500.0
            return 0.0
        # バトル場が空いたときの入れ替え先(ベンチのミュウツー/ワナイダー)は
        # 攻撃力で比較して選ぶ。山札からのサーチ(area=DECK)には影響させない。
        if o.area == AreaType.BENCH and card.id in (MEWTWO_EX, SPIDOPS):
            fl = _frontline_score(card, p, me,
                                  not (me.active and me.active[0] is not None))
            if fl is not None:
                return fl
        # 自分側サーチ先: ワナイダー系 > たねロケット団 > 草エネ
        if card.id == SPIDOPS:
            # ★進化元が場にいなければ手札で腐るので、たねに譲る
            if (USE_SEARCH_BASIC_WHEN_THIN
                    and not p.field_counts.get(TAROUNTULA)):
                return 500.0
            return 1200.0
        if card.id == TAROUNTULA:
            # ★盤面が狭いときは頭数(=打点)に直結するので最優先
            if (USE_SEARCH_BASIC_WHEN_THIN and p.bench_free >= 1
                    and p.rocket_count < WIDE_ENOUGH):
                return 1600.0
            return 1000.0
        if card.id in ROCKET_POKEMON:
            d0 = gh._CARD.get(card.id)
            if (USE_SEARCH_BASIC_WHEN_THIN and d0 is not None and d0.basic
                    and p.bench_free >= 1 and p.rocket_count < WIDE_ENOUGH):
                return 1400.0
            return 900.0

        if card.id == GRASS_ENERGY:
            return 700.0
        if card.id in ROCKET_SUPPORTERS:
            return 600.0
        return 0.0

    # ---- 逃げる ----
    if t == OptionType.RETREAT:
        # ★無意味な逃げの禁止(2026-07-26 ユーザー指摘)
        # 実戦例: バトル場タマンチュラ(草エネ1個) / ベンチにタマンチュラ2体と
        #   ミュウツー(0エネ) / 手札にワナイダー。**次のターン進化させれば良いのに**
        #   タマンチュラを下げて0エネのミュウツーを前に出していた。
        #   → 付けた草エネが無駄になり、しかもミュウツーは0エネで撃てない。
        # 逃げは逃げエネを捨てるので、明確な利得がなければ損。
        # ★ミュウツー軸: フリーザーがベンチにいて相手がフーディン/ドラパルトなら、
        #   **たねのミュウツーexを前に出す**(レジストヴェールでワザの効果を無効化)。
        #   1進化のワナイダーは保護対象外なので、前を張るのはたねが適任。
        # ★「今撃てるポケモン」は逃がさない(2026-07-27 ユーザー指摘)
        # 実測で逃げ24回中17回(71%)が「撃てる状態なのに逃げる」だった。
        # 逃げると逃げエネを失い、しかも攻撃機会も失う二重の損。
        # ワナイダーはロケット団エネ(超悪2個ぶんの貴重な札)を逃げに使うことすらあった。
        if USE_NO_POINTLESS_RETREAT and p.active is not None:
            need_a = _energy_need(p.active)
            if need_a > 0 and len(p.active.energies or []) >= need_a:
                # 前が撃てる。ベンチに「もっと強い攻撃ができる」駒がいる時だけ許す。
                better = False
                for b in (me.bench or []):
                    if b is None:
                        continue
                    nb = _energy_need(b)
                    if nb <= 0 or len(b.energies or []) < nb:
                        continue
                    # ミュウツーex(160+)はワナイダー(30×頭数)より上と見なす
                    if b.id == MEWTWO_EX and p.active.id != MEWTWO_EX \
                            and p.rocket_count >= 4:
                        better = True
                if not better:
                    return -2500.0

        # ※ この軸判定は「撃てるなら逃がさない」より**後**に置く。
        #   先に置くと、撃てるミュウツー/ワナイダーまで下げてしまう。
        if (USE_MEWTWO_AXIS and p.articuno_on_bench and p.op_damage_counter_deck
                and p.active is not None):
            act_d = gh._CARD.get(p.active.id)
            act_protected = bool(act_d and act_d.basic
                                 and p.active.id in ROCKET_POKEMON)
            if not act_protected:
                # 前が「守られないポケモン」なら、ベンチのミュウツーexと交代したい
                for b in (me.bench or []):
                    if b is not None and b.id == MEWTWO_EX:
                        return 3000.0

        if USE_NO_POINTLESS_RETREAT:
            act = p.active
            # ★攻撃しない駒がバトル場に居座っているなら退かす
            #   (2026-07-28、flgの逃げ68回の実態から)。
            #   内訳は ミミッキュ57% / フリーザー15% / タマンチュラ16% で、
            #   **75%は無傷**、エネ0が36回・エネ1が24回。つまりflgの逃げは
            #   「傷ついた主砲を下げる」ではなく「殴れない駒をどかす」動きだった。
            #   うちは下の「エネが1個でも付いていたら -1200」で止めており、
            #   flgの逃げの35%(エネ1個)がここで潰れていた。
            #   ミミッキュ/ヤミカラス/ソーナンスはこのデッキでは一度も殴らない。
            #   ※フリーザーは「相手のワザの効果を受けない」ので、
            #     ダメカン系デッキが相手のときだけ前に置く価値がある。
            # ★対ドラパルトのフリーザーだけは独立して下げる(2026-07-29 ユーザー要望)。
            #   上の USE_RETREAT_NON_ATTACKER は既定 False なので、そこに条件を
            #   足しても効かない(2026-07-29 に死にコードだったことを実測)。
            #   実測: 対ドラパルトでフリーザーがバトル場にいた 222 局面のうち
            #   176 (79%) はベンチに攻撃役(タマンチュラ/ワナイダー/ミュウツーex)が
            #   いた。レジストヴェールはベンチでも効くので、前に置く理由はない。
            if (USE_ARTICUNO_BENCH_VS_DRAGAPULT and act is not None
                    and act.id == ARTICUNO and p.op_dragapult
                    and any(b is not None and b.id in (SPIDOPS, TAROUNTULA, MEWTWO_EX)
                            for b in (me.bench or []))):
                return 2600.0
            if USE_RETREAT_NON_ATTACKER and act is not None:
                # ★対ドラパルトは例外でフリーザーを**ベンチに置いておく**
                #   (2026-07-29 ユーザー指摘)。ドラパルトはファントムダイブで
                #   バトル場に本体ダメージを撃ってくるので、前に置くと
                #   レジストヴェールごと落とされる。ベンチにいれば特性は効く。
                non_attacker = act.id in (MIMIKYU, MURKROW, WOBBUFFET) or (
                    act.id == ARTICUNO and not p.op_damage_counter_deck)
                if non_attacker and any(
                        b is not None and b.id in (SPIDOPS, TAROUNTULA, MEWTWO_EX)
                        for b in (me.bench or [])):
                    return RETREAT_NON_ATTACKER_SCORE
            # (1) バトル場が「今すぐ進化できる」なら下げない(エネを引き継げる)
            if act is not None and act.id == TAROUNTULA and p.hand_counts.get(SPIDOPS):
                return -2000.0
            # (2) バトル場にエネが付いているのに、まだ撃てる形でないだけなら
            #     下げるとそのエネを捨てることになる。次ターンに賭ける。
            act_ene = len(act.energies or []) if act is not None else 0
            # (3) 交代先が「今すぐ撃てる」なら逃げる価値がある
            best_ready = False
            for b in (me.bench or []):
                if b is None:
                    continue
                need = _energy_need(b)
                if need > 0 and len(b.energies or []) >= need:
                    best_ready = True
            if best_ready and not p.spidops_ready:
                return 900.0          # 撃てるアタッカーを前に出す
            # ★瀕死の主砲を下げて生かす(2026-07-28、flgとの機序比較)。
            #   flgは1ターンあたり0.111回にげるのに対しうちは0.023回(1/5)。
            #   下の「エネが付いていたら一律 -1200」が、**倒される寸前の
            #   ワナイダーを下がらせない**主因だった。倒されればエネも
            #   ポケモンもサイドも失うので、下げる方が損が小さい。
            #   ※ ユーザー指摘の「元気なアタッカーを未完成の駒と替える」は
            #     上の USE_NO_POINTLESS_RETREAT ブロックで従来どおり禁止。
            if USE_SAVE_DAMAGED_RETREAT and act is not None and best_ready:
                mx = getattr(act, "maxHp", None) or act.hp or 1
                if (act.hp or 0) <= mx * SAVE_RETREAT_HP_RATIO:
                    return 1200.0
            if act_ene > 0:
                return -1200.0        # エネを捨てるだけの交代はしない
            # 前が非アタッカーで、ベンチに主砲(ワナイダー)がいるなら入れ替える
            bench_spidops = any(c is not None and c.id == SPIDOPS
                                for c in (me.bench or []))
            if not p.spidops_active and bench_spidops:
                return 800.0
            return -800.0
        # 非アタッカーが前で、ベンチにワナイダーがいるなら逃げて主砲を前に。
        bench_spidops = any(c is not None and c.id == SPIDOPS
                            for c in (me.bench or []))
        if not p.spidops_active and bench_spidops:
            return 800.0
        return 100.0

    return 0.0


def _placement_bonus(o, obs, state, me, p: Plan) -> float:
    """誰をバトル場に置くか。ミュウツー/ワナイダーは攻撃力で比較して決める。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    # ★「撃破されて前を埋める」のか「逃げ/サポートで交代する」のかを区別する
    #   (2026-07-28 ユーザー指摘)。判定はバトル場が空かどうか。
    #   撃破後は直後に自分のターンが来るので「次のターンに撃てるか」で選ぶ。
    after_ko = not (me.active and me.active[0] is not None)
    fl = _frontline_score(card, p, me, after_ko)   # 攻撃力で比較
    if fl is not None:
        return fl
    # ★フリーザーはバトル場に出さない(2026-07-26 ユーザー要望)
    # 特性レジストヴェールは「場にいるかぎり」効くので**ベンチにいれば十分**。
    # 前に出すと殴られて落ち、特性ごと失う。しかもワザは[水,無,無]で
    # このデッキは草/ロケット団エネしかないので**撃てない**。
    if USE_ARTICUNO_GUARD and card.id == ARTICUNO:
        bench_other = [c for c in (me.bench or [])
                       if c is not None and c.id != ARTICUNO]
        if bench_other:
            return -1500.0       # 他に前に出せる駒があるなら絶対に出さない
        return -300.0            # 他が居なければ仕方なく(場が空くのは論外)
    # ★誰も撃てないときの前線は「一番安い捨て駒」を出す(2026-07-28、実測)。
    #   ミミッキュ/ヤミカラス/ソーナンスはこのデッキで一度も殴らない純粋な頭数なので
    #   差し出しても失うのはサイド1枚と打点30だけ。ミュウツーex(サイド2枚)や
    #   育ったワナイダーを前に出すより損が小さい。
    if USE_SACRIFICE_FRONTLINE and card.id in (MIMIKYU, MURKROW, WOBBUFFET):
        return 1400.0
    if card.id == TAROUNTULA:
        return 1200.0 if USE_SACRIFICE_FRONTLINE else 1000.0
    if card.id in ROCKET_POKEMON:
        return 600.0
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
            #   (2026-07-28 判明)。サカキの「引きずり出す相手」は
            #   **ctx=3(SWITCH)** で来るが、SWITCH は placement に入っており
            #   _placement_bonus は相手側の選択肢に一律 0.0 を返す。
            #   そのため **USE_BOSS_TARGETING が一度も適用されておらず**、
            #   generic の基礎点(100〜120)だけで決まっていた。
            #   実測: 倒せる中で最強を選べたのは 55回中14回(25%)＝ほぼ偶然。
            is_opponent_side = (o.playerIndex is not None
                                and o.playerIndex != state.yourIndex)
            if ctx in placement and not (is_opponent_side and USE_OPPONENT_SIDE_BONUS):
                extra = _placement_bonus(o, obs, state, me, plan)
            else:
                extra = _bonus(o, obs, state, me, op, plan, ctx)
            scores.append(base + extra)

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # ★リーリエの決心は「やれることを全部やってから」使う(2026-07-28 ユーザー指摘)
        # リーリエは**手札を山札に戻して**引き直すので、手札に残したエネや
        # ポケモンは消える。報告された事故: エネを付けられる場面で付けずに
        # 先にリーリエを使い、手札のエネが流れた。
        # 実測(80試合): リーリエ88回のうち**59回(67%)がエネを付けられる場面**で、
        # 手札のエネを1試合あたり1.29枚流していた。
        # 禁止ではなく後回しにする(禁止だと使用回数が半減した)。
        if (USE_LILLIE_LAST and ctx == SelectContext.MAIN and select.option):
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
                        # たね(ベンチに空きがある)かグッズだけを先に回す。
                        # サポートは1ターン1枚なのでここでは比較しない。
                        # ★agent() 内の Plan 変数は `plan`。`p` と書くと NameError が
                        #   except に握りつぶされて修正が丸ごと無効化される
                        #   (2026-07-28 の監査で実際に踏んでいた。7/120試合で発生)。
                        ok = ((d2.cardType == 0 and d2.basic
                               and plan.bench_free > 0)
                              or d2.cardType == 1)
                        if not ok:
                            continue
                    else:
                        continue
                    # うちのスコアでも「やる価値がある」と出ている手だけに譲る。
                    # これが無いと、やらない手に永久に譲り続けてしまう。
                    if scores[i] >= PREP_MIN_SCORE:
                        order = [i] + [j for j in order if j != i]
                        break

        # ★手張りより先にチャージアップを試す(2026-07-28 ユーザー指摘)
        # 報告された事故: バトル場のワナイダーに草エネ1個 → ロケット団エネを
        # 手張り → その後チャージアップで草エネを付けた。チャージアップだけで
        # 攻撃可能(ロケットラッシュは[草,無]の2個)になったので手張りは不要だった。
        # チャージアップは「トラッシュから基本エネを1枚**自身に**」で無料・
        # ターン1回、手張りも1ターン1回の貴重な行動。**先に無料の方を使えば、
        # 手張りを本当に必要な場所(ミュウツーex等)に回せる**。
        # ロケット団エネはミュウツーの超悪2個ぶんなので浪費が特に痛い。
        # 実測: 80試合でワナイダーへの手張り273回のうち7回がこの無駄で、
        # うち4回はロケット団エネだった。
        if (USE_CHARGEUP_BEFORE_ATTACH and ctx == SelectContext.MAIN
                and select.option
                and select.option[order[0]].type == OptionType.ATTACH):
            top = select.option[order[0]]
            is_energy_attach = False
            if top.area == AreaType.HAND:
                hc = gh._hand_card(obs, top.index, me)
                d0 = gh._CARD.get(hc.id) if hc is not None else None
                # 5=基本エネ / 6=特殊エネ。どうぐ(2)はここでは対象外
                is_energy_attach = d0 is not None and d0.cardType in (5, 6)
            if is_energy_attach:
                # ★手張りは**盤面が固まってから最後に決める**(2026-07-29)。
                #   1ターン1回しかないので、先にたねを出す/特性を使うと
                #   「もっと良い付け先」や「そもそも付けなくて良い」が判明する。
                #   実測(上位勢との差分152件): うちがATTACHした場面で
                #   上位勢は **PLAY 32件 / ABILITY 11件** を先にやっていた。
                for i in order:
                    o2 = select.option[i]
                    if scores[i] < PREP_MIN_SCORE:
                        continue          # うちのスコアで価値がある手だけに譲る
                    if o2.type == OptionType.ABILITY:
                        src = gh._get_card(obs, o2.area, o2.index, o2.playerIndex)
                        if src is None:
                            try:
                                if o2.area == AreaType.ACTIVE and me.active:
                                    src = me.active[o2.index or 0]
                                elif o2.area == AreaType.BENCH and me.bench:
                                    src = me.bench[o2.index or 0]
                            except (IndexError, TypeError):
                                src = None
                        if src is not None and src.id == SPIDOPS:
                            order = [i] + [j for j in order if j != i]
                            break
                    elif o2.type == OptionType.PLAY and USE_PLAY_BEFORE_ATTACH:
                        c2 = gh._hand_card(obs, o2.index, me)
                        d2 = gh._CARD.get(c2.id) if c2 is not None else None
                        if d2 is None:
                            continue
                        # たね(ベンチに空きがある)= 新しい付け先が増える
                        # グッズ = サーチで付け先/エネが変わりうる
                        if ((d2.cardType == 0 and d2.basic and plan.bench_free > 0)
                                or d2.cardType == 1):
                            order = [i] + [j for j in order if j != i]
                            break

        # ★攻撃を最後に回す(2026-07-28、flgとの差分から)
        # _bonus 側で攻撃に負の値を返すだけでは足りなかった。合計スコアは
        # 「generic の基礎点 + bonus」で、攻撃の基礎点が大きいため -920 程度では
        # 順位が変わらず、実測で ATTACK 30.6%→28.6% しか動かなかった。
        # 攻撃はターンを終わらせるので、**実際に選べる準備行動があるなら
        # 順位そのものを入れ替える**。END より下には落とさないので
        # 「準備もせず攻撃もせずEND」にはならない。
        if (USE_ACT_BEFORE_ATTACK and ctx == SelectContext.MAIN
                and select.option and USE_ACT_BEFORE_ATTACK_BROAD
                and select.option[order[0]].type == OptionType.ATTACK
                and _setup_option_available(obs, plan, me, state)):
            # ただし**倒せるなら即殴る**。また、譲る相手は
            # 「うちのスコアで見ても実際に価値がある準備」に限る。
            # 無条件に譲ると ATTACK 5.1% まで落ちてしまい、flg(10.6%)より
            # 殴らなくなった(選択肢に残っているだけで価値のないPLAYが多いため)。
            top_atk = select.option[order[0]]
            # ★ここも実効打点で見る(素点だと -60 される相手を倒せると誤認する)
            rush = _vs_active(plan.rocket_count * 30.0, E_GRASS, plan)
            eb = _vs_active(160.0, E_PSYCHIC, plan)
            lethal = (USE_LETHAL_ATTACK_NOW and plan.op_active is not None
                      and ((top_atk.attackId == ATK_ROCKET_RUSH
                            and plan.op_active_hp <= rush)
                           or (top_atk.attackId == ATK_ERASURE_BALL
                               and plan.op_active_hp <= eb)))
            if not lethal:
                prep = [i for i in order
                        if select.option[i].type not in (OptionType.ATTACK,
                                                         OptionType.END)
                        and scores[i] >= PREP_MIN_SCORE]
                if prep:
                    rest = [i for i in order if i != prep[0]]
                    order = [prep[0]] + rest

        # チャージアップを使ったらフラグを立てる(1ターン1回)
        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                c = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if c is None:
                    # ここで補完しないと使用済みが記録されず、同じ個体の特性を
                    # 何度も選び続けて他の行動ができなくなる恐れがある。
                    try:
                        if top.area == AreaType.ACTIVE and me.active:
                            c = me.active[top.index or 0]
                        elif top.area == AreaType.BENCH and me.bench:
                            c = me.bench[top.index or 0]
                    except (IndexError, TypeError):
                        c = None
                if c is not None and c.id == SPIDOPS:
                    # ★個体ごとに記録(場に複数いればそれぞれ1回使える)
                    _used_chargeup_slots.add((top.area, top.index))

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))

        # ★「N枚まで選べる」場面の取り漏らし修正(2026-07-26)
        # 上の k は最小枚数しか取らないため、複数枚選べる場面で1枚しか取って
        # いなかった。実測(対公開フーディン40試合)で:
        #   ctx=7  93回 取得1.06枚/上限2.52枚 … **ランス(たね3枚サーチ)**
        #   ctx=5  15回 取得1.00枚/上限2.00枚 … ポフィン等の展開
        #   ctx=26 13回 取得1.00枚/上限2.00枚 … チャージアップの配分先
        # ランスは go-wide の盤面拡大エンジンで、3枚取れるのに1枚しか取れて
        # いなかった(攻撃時の盤面が3.6止まりだった原因の一つ)。
        # ※ agent() 内の Plan 変数は `plan`(_bonus 内は `p`)。ここを p にすると
        #   NameError が except に握りつぶされて修正が丸ごと無効化される。
        # ★イレイザーボールのエネトラッシュ枚数(2026-07-27 ユーザー要望)
        # 「相手HP <= 160 + 60×n」を満たす最小の n だけトラッシュする。
        # 草エネはワナイダーのチャージアップで拾い直せるので、倒せるなら惜しまない。
        if (USE_ERASURE_DISCARD and ctx == SelectContext.DISCARD_ENERGY_CARD
                and hi > 1 and select.option):
            need = _erasure_discard_need(plan, me)
            need = min(need, hi, len(order))
            if need <= 0:
                return [] if lo == 0 else order[:lo]
            # ★トラッシュして良いのは**草エネだけ**(2026-07-27 ユーザー指摘)
            # 草はワナイダーのチャージアップでトラッシュから拾い直せるので損が小さい。
            # ロケット団エネは【超】【悪】2個ぶんとして働く貴重な札なので温存する。
            # (※ トラッシュ1枚につき+60。ロケット団エネでも1枚は1枚なので+60で、
            #    2個ぶんだからといって+120にはならない。失う価値だけが2倍)
            # 例外: ロケット団エネを切って**倒せ、それで自分のサイドが0になる**
            #       (=勝てる)なら切ってよい。
            grass_idx = []
            other_idx = []
            for i in order:
                eid = _discard_energy_id(select.option[i], me)
                if eid == GRASS_ENERGY:
                    grass_idx.append(i)
                elif eid is not None:
                    other_idx.append(i)
            if len(grass_idx) >= need:
                return grass_idx[:need]
            # 草だけでは足りない。勝ち切れるなら他のエネも使う。
            if _erasure_wins_game(plan, me, need):
                pick = (grass_idx + other_idx)[:need]
                if pick:
                    return pick
            # 勝てないなら草の範囲だけで妥協する(ロケット団エネは温存)
            if grass_idx:
                return grass_idx
            return [] if lo == 0 else order[:lo]

        if USE_PICK_MAX and hi > k and select.option:
            cand = [i for i in order
                    if _is_worth_picking(select.option[i], obs, me)]
            if len(cand) >= k:
                take = hi
                # ベンチに出す系(山札のたね)は空き枠を超えて取らない
                if _is_basic_pokemon_opt(select.option[cand[0]], obs, me):
                    take = min(take, max(1, plan.bench_free))
                # 山札から引く系は山札切れの安全余裕を超えない
                if select.option[cand[0]].area == AreaType.DECK:
                    take = min(take, max(1, plan.safe_draws))
                if take < lo:
                    take = lo
                if take > 0:
                    return cand[:take]
        return order[:k]
    except Exception:
        return gh.agent(obs_dict)
