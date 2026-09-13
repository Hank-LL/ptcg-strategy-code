"""フーディン専用ヒューリスティック。

設計:
  generic_heuristic の汎用スコアを土台にし、その上にフーディン固有の
  「ターン逆算プランニング」を加算レイヤーとして重ねる。

  - 汎用側が全 SelectContext を一応カバーするので、固有ロジックを書いていない
    局面でも常識的な手が出る(参考にした公開実装は49コンテキスト中40個が素通り
    だった。ここを埋めるのが本実装の主眼のひとつ)。
  - 固有側は「このターン手札を何枚まで増やせるか」→「その打点で誰を倒せるか」
    を先に決め、その計画を実行する方向にボーナス/ペナルティを付ける。

デッキの中核:
  フーディン(743)のワザ「Powerful Hand」(id=1072)は
  「手札1枚につきダメカン2個」= 手札枚数 × 20 ダメージ。
  よって打点は自分で完全に計算できる。手札を増やす手段:
    ケーシィ→ユンゲラー進化: 特性で2枚ドロー (手札-1+2 = 純+1)
    ユンゲラー→フーディン進化: 特性で3枚ドロー (純+2)
    ノコッチ→ノココッチ進化:   特性で3枚ドロー (純+2、ただし下記注意)
    ノココッチ特性 Run Away Draw: 3枚ドロー (純+3、ただし自身を山札に戻す)
    キチキギスex特性 Flip the Script: 3枚ドロー (純+3、**要きぜつ条件**)
    サポート ヒカリ/トウコ: 純+1〜+2

参考にした公開ノートブックとの主な違い:
  1. キチキギスexの +3 を無条件に数えない(相手の前の番に自分のポケモンが
     きぜつした場合のみ使える特性なので、サイド残数の変化で条件を判定する)
  2. 最小打点(確定で届く打点)も実際に計算する。公開実装は min を 0 固定にして
     いて機能していなかった。確定KOと不確定KOを区別して立ち回りを変える。
  3. 未対応コンテキストを汎用ヒューリスティックに委譲する

**ただし上の3点はいずれも勝率への寄与が確認できていない。**
公開実装との対戦で差分を1つずつ外した実測(各240試合, SE±3.2%):
    全差分あり 42.5% / 1を外す 44.6% / 2を外す 45.4% / 3を外す 42.5%(同値)
    (参考) 汎用ヒューリスティックのみ 12.9%
差はすべて誤差内で、名目上はむしろ外した方が高い。効いているのは
「手札枚数から打点を逆算して目標を選ぶ」という中核構造(公開実装と同じ発想)で、
汎用比 +30pp はそこから来ている。上の USE_* フラグで再測定できる。
1 は勝率に出ないが打点見積もりとして事実が正しいので残している。
"""

import generic_heuristic as gh

from cg.api import (AreaType, OptionType, SelectContext, Observation,
                    to_observation_class)

# ---------------------------------------------------------------- カードID
ABRA = 741            # ケーシィ
KADABRA = 742         # ユンゲラー
ALAKAZAM = 743        # フーディン
DUNSPARCE = 305       # ノコッチ
DUDUNSPARCE = 66      # ノココッチ
FEZANDIPITI = 140     # キチキギスex
GENESECT = 142        # ゲノセクト
PSYDUCK = 858         # コダック
SHAYMIN = 343         # シェイミ

RARE_CANDY = 1079     # ふしぎなアメ
ENHANCED_HAMMER = 1081  # 改造ハンマー
POFFIN = 1086         # なかよしポフィン
NIGHT_STRETCHER = 1097  # 夜のタンカ
SACRED_ASH = 1129     # せいなるはい
POKE_PAD = 1152       # ポケパッド
LUCKY_HELMET = 1156   # ラッキーメット
BOSS_ORDERS = 1182    # ボスの指令
HILDA = 1225          # トウコ
DAWN = 1231           # ヒカリ
BATTLE_CAGE = 1264    # バトルコロシアム
# --- 上位勢の主力構築(270試合231勝39敗=86%)に入っていて、公開5位デッキには
#     無かったカード。deck_fuudin_top.csv 用。
XEROSIC = 1197        # ゼロの大空洞…ではなく「Xerosic's Machinations」
                      # サポート: 相手の手札を3枚になるまで捨てさせる(強力な妨害)
NIGHTTIME_MINE = 1266  # スタジアム: テラポケモンのワザコストを+1(対テラのメタ)
LANAS_AID = 1184      # サポート: トラッシュから非ex/基本エネを計3枚回収
                      # → 場切れ・山札切れの回復札(我々の最大の負け筋への対策)

BASIC_PSYCHIC = 5
TELEPATH_PSYCHIC = 19
ENRICHING_ENERGY = 13
PSYCHIC_ENERGIES = {BASIC_PSYCHIC, TELEPATH_PSYCHIC}

# ワザID
ATK_TELEPORT = 1070       # ケーシィ 10
ATK_SUPER_PSY_BOLT = 1071  # ユンゲラー 30
ATK_POWERFUL_HAND = 1072   # フーディン 手札×20

ABRA_LINE = {ABRA, KADABRA, ALAKAZAM}
DUNSPARCE_LINE = {DUNSPARCE, DUDUNSPARCE}
DAMAGE_PER_CARD = 20

# 「まだ手札を伸ばせるが、KOには届かない」ときに攻撃を先送りする強さ。
# 大きすぎると攻撃しなくなって負ける(0/1000/2000 を各120試合で実測し、
# 39.2% / 43.3% / 40.8%。差は誤差内だが最良の1000を採用)。
ATTACK_DELAY_PENALTY = 1000.0

# --- 参考にした公開実装との差分。切り分け測定(ablation)用のフラグ。
# False にすると公開実装寄りの挙動に戻る。
USE_FEZANDIPITI_CONDITION = True   # キチキギスexの+3を条件付きにする
USE_BOSS_AVAILABILITY = True       # ボスを撃てるときだけベンチを狙う
USE_GENERIC_BASE = True            # 汎用ヒューリスティックを土台に敷く

# 手札を1枚使うと打点が DAMAGE_PER_CARD だけ下がる。フーディンで殴れる状態の
# ときに「手札が減るだけのカード」を切ると、その分そのまま打点を失う。
# 実測(200試合)で、殴る瞬間の平均手札が 自作13.61枚 に対し公開実装は14.44枚、
# 打点にして272 vs 289 と負けていた。そこでコストをスコアに反映してみたが、
# **効果はなかった**ので既定はオフ(0.0)。
#
# 300試合の掃引では 0→41.7% / 400→44.3% / 900→46.3% / 1500→44.7% と
# 改善に見えたが、900 を600試合で追試すると 42.0%(ベースライン40.0%)で誤差内。
# 決定的なのは機序が動いていないこと: 殴る瞬間の平均手札は 13.61 → 13.64 と
# ほぼ不変で、最小手札はむしろ 2 → 1 に悪化した。
# 温存するとカードを使うスコアが下がる分だけ攻撃が相対的に上がり、早く殴って
# しまう副作用があると見られる。打点差の是正には別の手が要る。
HAND_COST_PENALTY = 0.0

# カードごとの手札収支(実カードテキストで検証済み)。
#   ヒカリ  : -1して たね/1進化/2進化 を1枚ずつサーチ            → 純+2
#   トウコ  : -1して 進化ポケモンとエネルギーを1枚ずつサーチ       → 純+1
#   ふしぎなアメ: -1(自身)-1(2進化) だが特性で3ドロー             → 純+1
#   ポケパッド: -1して ポケモン1枚サーチ                        → ±0
#   夜のタンカ: -1して トラッシュから1枚回収                     → ±0
#   ポフィン  : -1して たね2枚を「ベンチ」に出す(手札には来ない)    → 純-1
#   改造ハンマー / せいなるはい / バトルコロシアム                → 純-1
# ※ 以前ここで ふしぎなアメ・ポケパッド・夜のタンカ を「減る側」と
#   誤分類していた。アメは実際には増える側。
_HAND_NEGATIVE = {POFFIN, ENHANCED_HAMMER, BATTLE_CAGE, SACRED_ASH}

# 手札収支を意識したスコアリングを使うか(A/B用)。
# 実測(150試合, 1試合あたりの使用回数)で、自作は手札が減る改造ハンマーを
# 1.41回使う一方(公開実装は0.00回)、手札が増えるトウコ/ヒカリを
# それぞれ0.83回/0.51回少なくしか使っていなかった。
USE_HAND_ECONOMY = True

# 山札切れ対策を有効にするか(A/B用)。
# 実測(各300試合×5回)で、山札0での敗北が 19.9% → 10.9% に半減、
# 勝率は 45.4% → 48.9%。公開実装の山札0敗北は4.7%。
USE_DECK_SAFETY = True

# 山札の安全マージン。safe_draws = 山札 - サイド - この値。
# 1 は「次の番の開始時ドロー1枚ぶん」だけを見込んだ最小値(公開実装と同じ)。
DECK_SAFETY_BUFFER = 1

# 公開ノートブックの Playing Principles に書かれていて未実装だった規則群。
#   - ラッキーメットの付け先(ゲノセクト優先、なければバトル場)
#   - エネルギーの付け先(基本超/テレパス超 → ケーシィ系、リッチ → ノコッチ系)
#   - 同じポケモンにエネルギーを2個以上付けない
#   - ベンチを1枠空けておく / ケーシィ系を場に3体保つ
#   - 進化の優先順: フーディン(バトル場) → ユンゲラー → ノココッチ → フーディン(ベンチ)
USE_NOTEBOOK_RULES = True

# ATTACHのエネルギー種別による振り分けを有効にするか。
# 実測でこの振り分けは逆効果だった(50.3%→43.7%)ため既定でオフ。
# フーディンデッキは超エネをケーシィ系に付ければ十分で、細かい振り分けの
# スコア値が未調整だったのが原因。イワパレスは草の供給が死活的なので
# あちらでは同じ修正がプラスに働いた(対フーディン32.8%→38.3%)。
ATTACH_FIX = False

# ケーシィ先付け: 殴れる状態(確定KOでない)のとき、殴る前にベンチのケーシィ系へ
# 超エネを先付けして次アタッカーを準備する。手札が減る=打点-20の懸念があったが、
# 発動するのはオーバーキル気味のターンなのでKO結果は変わらず、次アタッカーの準備が
# 効いた。実測(各2400試合×8反復)で 48.5%→51.0%(+2.5pp, 対応t検定 約2σ)。
# 確実ではないが害はないため既定ON。0で無効化できる。
USE_CASEY_PRELOAD = True

# ケーシィの「テレポート」を配置直しに使うか。
# 公開実装は1試合0.4回使う(自作は0回だった)。
USE_TELEPORT = True

# --- 2026-07-25 ユーザー指定の作り込み(6ルール)。A/B用フラグ。
#   1. 絶対にデッキ0で負けにしない(安全マージンを厚くする)
#   2. フーディンを早く揃える(進化ラインを更に優先)
#   3. 超エネ付きフーディンがベンチにいたら最優先で前に出す
#   4. エネ無しフーディンがベンチ + 手札に超エネ → 前に出す(次のターン殴れる形)
#   5. バトル場のフーディンにエネ無し → 超エネを付ける(実装済み)
#   6. ベンチの超エネ無しフーディン線(進化前含む) → 超エネを優先して付ける(実装済み)
USE_SETUP_V2 = True
# ルール1: デッキ安全マージン(safe_draws = 山札 - サイド - これ)を厚くする。
# 実測(対公開フーディン, 各240×5): buffer と デッキ切れ負け率は
#   1→7.1% / 2→7.2% / 6→4.2% / 8→3.8% / 10→3.0% と単調に減り、
#   勝率は 50.7〜51.5% でほぼ不変(バッファを上げても打点は落ちない=
#   元々「引きすぎて浪費&自滅」していた)。「絶対にデッキ切れしない」を優先し 6。
# より安全にしたいなら 8〜10(デッキ切れ3%台, 勝率は誤差内で不変)。
DECK_SAFETY_BUFFER_V2 = 6

# 各行動が山札から減らす枚数(ドロー・サーチ・ベンチ出し)。
# これが p.safe_draws を超える行動は、山札切れ自滅につながるので避ける。
_DECK_COST_PLAY = {
    DAWN: 3,            # たね/1進化/2進化 を1枚ずつサーチ
    HILDA: 2,           # 進化ポケモンとエネルギーを1枚ずつ
    POKE_PAD: 1,        # ポケモン1枚
    RARE_CANDY: 3,      # 2進化が出て特性で3ドロー
    POFFIN: 2,          # たね2枚をベンチへ
}
_DECK_COST_EVOLVE = {ALAKAZAM: 3, KADABRA: 2, DUDUNSPARCE: 3}
_DECK_COST_ABILITY = {DUDUNSPARCE: 3, FEZANDIPITI: 3}

# 相手の場に見えたら出したいテク要員
DUSKULL = 131                                   # → コダック
WATER_THREATS = {162, 327, 33, 945, 108, 257}   # → シェイミ
DRAGAPULT_LINE = {119, 120, 121}                # → バトルコロシアム

# ---------------------------------------------------------------- 相手アーキタイプ
# 上位勢のリプレイ(371勝)を相手別に分解すると、明確に立ち回りを変えている:
#   相手         攻撃/試 KO率 ボス/試 逃げ/試 決着T シェイミ出場率
#   オーロンゲex   3.14  79%  2.23  0.97  11.6  65%
#   フーディン     1.89  79%  1.58  0.77  13.7  18%
#   イワパレス     2.42  29%  0.79  0.48  10.9   3%
#   ワナイダー     8.35  69%  1.65  2.94  29.1  24%
#   ドラパルト     1.73  74%  0.73  0.91  11.1  27%
# 自作は相手に関係なく一律(攻撃4.69/ボス0.66)だった。
GRIMMSNARL_LINE = {648, 646, 647}     # オーロンゲex(ベンチ狙撃)
CRUSTLE_LINE = {345, 344}             # イワパレス(exのワザを無効化)
SPIDOPS_LINE = {401, 400}             # ワナイダー(go-wide)
STARMIE_LINE = {1030, 1031, 1032}     # メガスターミーex

# シェイミ「はなのカーテン」= 自分のベンチの「ルールを持たない」ポケモン全員が
# 相手のワザのダメージを受けない。フーディン線(741/742/743)は全て非exなので
# 完全に守られる。→ **ベンチを狙撃してくる相手にこそ出す**。
# 上位勢はオーロンゲex相手に65%出す(イワパレス相手は3%=ベンチを叩かれないので無意味)。
# 旧実装は WATER_THREATS(水弱点)にしか反応せず、オーロンゲもドラパルトも
# 対象外だった(-2000点で「出さない」)。
BENCH_SNIPERS = GRIMMSNARL_LINE | DRAGAPULT_LINE | STARMIE_LINE

# シェイミをベンチ狙撃デッキに対して出すか(A/B用)
# 実測(強い相手のみ=公開フーディンAI+自作専用オーロンゲ/イワパレス/ワナイダー,
# 各40×4反復): OFF 48.1%±2.3 → シェイミのみ **52.2%±1.7 (+4.1pp)**。採用。
USE_SHAYMIN_VS_SNIPER = True

# 「N枚まで選べる」場面で上限まで拾う(取り漏らし修正)。
# ★オーロンゲで同じバグを見つけて点検した結果、フーディンでも起きていた。
# 実測(対公開フーディン40試合): ctx=5 が57回で平均1.00枚/上限2.00枚、
# **ctx=9(Lana's Aid のトラッシュ回収)が26回で平均1.00枚/上限4.00枚**。
# Lana's Aid は最大の負け筋(場切れ・山札切れ)への回復札なので致命的だった。
USE_PICK_MAX = True

# 「大型exの進化前」を完成前にボスで引きずり出して狩るか(A/B用)。
# 例: リオル(677) → メガルカリオex(678, HP340)。フーディンの打点は手札×20なので
# HP340は手札17枚が必要で現実的に倒せない([[ptcg-alakazam-heuristic]]の
# 対ガブリアスex HP330=3% と同じ構造)。実測でメガルカリオexは**平均6.3ターンで
# 完成**し89%の試合で出現する。完成後に対処するのは困難なので、進化前の
# リオル(HP70前後)のうちに引きずり出して倒しておく。
USE_PREEVO_SNIPE = True
# 進化前を狩る対象(進化前ID -> 完成形が手に負えない大型ex)
PREEVO_TARGETS = {
    677: 678,   # リオル → メガルカリオex(HP340)
    333: 678,
    974: 678,
}
# この打点で倒しきれる進化前だけを狙う(倒せないなら引きずり出す意味が薄い)

# 長期戦になる相手(イワパレス/ワナイダー)では引き控えて山札切れを防ぐか(A/B用)。
# 実測(強い相手4種, 各30×4反復):
#   OFF(6一律)  総合51.5%  イワパレス山札切れ44.2% / ワナイダー30.8%
#   ON(12)      総合52.7%  イワパレス41.7% / **ワナイダー20.0%**  ← 採用
#   ON(18)      総合50.2%  イワパレス32.5% / ワナイダー23.3% (引き控えすぎで打点不足)
# ワナイダー戦は山札切れ-10.8pp・勝率41.7→44.2%と明確に改善。
# **イワパレス戦の山札切れ41.7%は未解決** = 決着30.6ターンという試合の長さ自体が原因で、
# 引き控えでは根治しない([[ptcg-iwaparesu-hard-counter]])。上位勢は同じ相手を
# 10.9ターンで終わらせており、試合の作り方自体が違うと見られる。
USE_OPPONENT_SIDE_BONUS_AL = True
# 改造ハンマーは「ロケット団エネが付いたミュウツーex」を狙う(対ワナイダー)
USE_HAMMER_TARGETING = True
ROCKET_ENERGY = 15
ROCKET_MEWTWO_EX = 431
USE_GRINDY_SAFETY = True
GRINDY_SAFETY_BUFFER = 12

# 相手アーキタイプに応じてボスを序盤妨害に使うか(A/B用)。
# **実測で効果なし → 既定オフ。** 上位勢の使い方(ドローを捨てて序盤から撃つ)を
# 再現し、機序は動いた(0.59→0.88回/試合)が勝率は 48.0%(OFF 48.1%)と不変。
# さらにシェイミと併用すると 47.7% とシェイミ単体(52.2%)より悪化し、
# 特に対イワパレスが 56%→48% に落ちた。ボスは手札-1=打点-20を払うので、
# 倒しきれない相手には純損失になる。上位勢が使えているのは、こちらが再現できて
# いない別の前提(例: 引きずり出した後の詰め筋)があると見られる。
USE_ARCHETYPE_BOSS = False

# ---------------------------------------------------------------- ターン内状態
# cg は1プロセス1対戦なのでモジュールグローバルで持てる。
_turn = -1
# ★ノココッチの Run Away Draw は「このポケモンにつき」1ターン1回なので、
#   **個体ごと**に使用済みを管理する(2026-07-26 ユーザー指摘)。
#   単一 bool にしていたため、1体使うと場の全ノココッチがブロックされていた
#   (実測: ノココッチ2体以上の239局面のうち134回で選択肢が2個出ているのに、
#    同ターン2回目の使用は16回だけ)。キーは (area, index)。
_used_dudunsparce_slots = set()
# キチキギスexの Flip the Script はカードテキストに
# 「You can't use more than 1 Flip the Script Ability each turn.」と明記が
# あるので**場全体で1回**。こちらは単一フラグが正しい。
_used_fezandipiti = False
_op_prize_at_my_turn = None   # 自分の番の開始時に見た「相手の残りサイド」
_lost_pokemon_last_turn = False


def _update_turn_state(state, me, op):
    """ターンが変わったタイミングで、ターン内フラグときぜつ検出を更新する。"""
    global _turn, _used_dudunsparce_slots, _used_fezandipiti
    global _op_prize_at_my_turn, _lost_pokemon_last_turn

    if state.turn == _turn:
        return
    _turn = state.turn
    _used_dudunsparce_slots = set()
    _used_fezandipiti = False

    # 相手の残りサイドが減っていれば、相手がサイドを取った = 自分のポケモンが
    # きぜつした。キチキギスexの Flip the Script はこの場合だけ使える。
    op_prize_now = len(op.prize) if op.prize is not None else 6
    if _op_prize_at_my_turn is None:
        _lost_pokemon_last_turn = False
    else:
        _lost_pokemon_last_turn = op_prize_now < _op_prize_at_my_turn
    _op_prize_at_my_turn = op_prize_now


def reset_state():
    """対戦をまたぐときに呼ぶ(評価スクリプト用。提出時は毎回新プロセス)。"""
    global _turn, _used_dudunsparce_slots, _used_fezandipiti
    global _op_prize_at_my_turn, _lost_pokemon_last_turn
    _turn = -1
    _used_dudunsparce_slots = set()
    _used_fezandipiti = False
    _op_prize_at_my_turn = None
    _lost_pokemon_last_turn = False


# ---------------------------------------------------------------- 盤面の集計
class Plan:
    """このターンの計画。"""

    __slots__ = ("hand_size", "min_hand", "max_hand", "min_dmg", "max_dmg",
                 "target_idx", "target", "use_boss", "can_kill", "sure_kill",
                 "prize_gain", "field", "hand_counts", "field_counts",
                 "bench_free", "active", "active_id", "active_has_psychic",
                 "kadabra_finish", "need_more_hand", "growth_available",
                 "lethal_now", "safe_draws", "can_win_now", "psychic_in_hand",
                 "op_ids", "op_sniper", "op_crustle", "op_ex_count", "op_grindy")

    def __init__(self):
        self.target_idx = -1
        self.target = None
        self.use_boss = False
        self.can_kill = False
        self.sure_kill = False
        self.prize_gain = 0
        self.kadabra_finish = False
        self.need_more_hand = False
        self.growth_available = False
        self.lethal_now = False
        self.safe_draws = 99
        self.can_win_now = False


def _counts(cards):
    d = {}
    for c in cards or []:
        if c is not None:
            d[c.id] = d.get(c.id, 0) + 1
    return d


def _prize_value(pk) -> int:
    d = gh._CARD.get(pk.id)
    if d is None:
        return 1
    return 3 if d.megaEx else 2 if d.ex else 1


def _is_worth_picking(o, obs, me) -> bool:
    """「N枚まで選べる」場面で、上限まで拾って良い候補か。

    山札/トラッシュ/サイドから複数枚取れる場面(ポフィン、Lana's Aid、
    せいなるはい等)で使う。拾って損しないカードだけを対象にする。
    """
    if o.type != OptionType.CARD:
        return False
    if o.area not in (AreaType.DECK, AreaType.DISCARD, AreaType.PRIZE):
        return False
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    # アタッカーの進化ライン、ドローエンジン、超エネは何枚でも欲しい
    return (c.id in ABRA_LINE or c.id in DUNSPARCE_LINE
            or c.id in PSYCHIC_ENERGIES or c.id == FEZANDIPITI)


def _is_basic_pokemon_opt(o, obs, me) -> bool:
    """その候補が「たねポケモン」か(ベンチ空き枠で上限を絞るため)。"""
    c = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if c is None:
        return False
    d = gh._CARD.get(c.id)
    return bool(d) and d.basic and d.cardType == 0


def _dudunsparce_used_at(slot) -> bool:
    """場のスロット(0=バトル場, 1..=ベンチ位置)のノココッチが今ターン使用済みか。

    使用済みキーは選択肢の (area, index) なので、盤面スロットを対応させる。
      slot 0      -> (AreaType.ACTIVE, 0)
      slot i(>=1) -> (AreaType.BENCH, i-1)
    """
    if slot == 0:
        return (AreaType.ACTIVE, 0) in _used_dudunsparce_slots
    return (AreaType.BENCH, slot - 1) in _used_dudunsparce_slots


def _has_psychic(card) -> bool:
    """このポケモンに超エネルギーが付いているか。"""
    return bool(card) and any(
        e.id in PSYCHIC_ENERGIES for e in (getattr(card, "energyCards", None) or []))


def _build_plan(obs: Observation, state, me, op) -> Plan:
    p = Plan()

    field = []
    for c in (me.active or []):
        if c is not None:
            field.append((0, c))
    for i, c in enumerate(me.bench or []):
        if c is not None:
            field.append((i + 1, c))
    p.field = field
    p.field_counts = _counts([c for _, c in field])
    p.hand_counts = _counts(me.hand)
    p.hand_size = len(me.hand) if me.hand is not None else me.handCount
    p.bench_free = (me.benchMax or 5) - len(me.bench or [])

    p.active = me.active[0] if me.active else None
    p.active_id = p.active.id if p.active else -1
    p.active_has_psychic = bool(p.active) and any(
        e.id in PSYCHIC_ENERGIES for e in (p.active.energyCards or []))

    fc, hc = p.field_counts, p.hand_counts
    # 手札に超エネルギーがあるか(ルール4: エネ無しフーディンを前に出す判断に使う)
    p.psychic_in_hand = any(hc.get(e) for e in PSYCHIC_ENERGIES)

    # ---- 相手アーキタイプの把握(見えている場のポケモンから) ----
    op_all = [c for c in (op.active or []) if c] + [c for c in (op.bench or []) if c]
    p.op_ids = {c.id for c in op_all}
    p.op_sniper = bool(p.op_ids & BENCH_SNIPERS)   # ベンチ狙撃してくる相手
    p.op_crustle = bool(p.op_ids & CRUSTLE_LINE)   # イワパレス(exを無効化)
    p.op_ex_count = sum(
        1 for c in op_all
        if (gh._CARD.get(c.id) is not None
            and (gh._CARD[c.id].ex or gh._CARD[c.id].megaEx)))
    # 長期戦になる相手(=山札切れ自滅のリスクが高い相手)。
    # 実測(各60試合)で負け方を分類したところ、負けの内訳が相手で全く違った:
    #   イワパレス: 負け23のうち**18が山札切れ**、決着30.6ターン
    #   ワナイダー: 山札切れ17 + 場切れ19、決着21.8ターン、勝率40%(最弱)
    #   フーディン/オーロンゲ: 場切れ主体、決着15〜16ターン
    # **全相手でサイド負けは0**。つまり負けは殴り合いではなくリソース枯渇。
    p.op_grindy = bool(p.op_ids & (CRUSTLE_LINE | SPIDOPS_LINE))

    # ---- 手札増加量の見積もり ----
    # min = 確定で得られる分, max = 全部うまくいった場合
    min_inc = max_inc = 0
    for slot, pk in field:
        if pk.id == KADABRA and hc.get(ALAKAZAM):
            min_inc += 2      # 進化でドロー3、手札からフーディン1枚消費 → 純+2
            max_inc += 2
        elif pk.id == ABRA and hc.get(KADABRA):
            min_inc += 1      # 進化でドロー2、手札から1枚消費 → 純+1
            max_inc += 1
        elif pk.id == ABRA and hc.get(RARE_CANDY) and hc.get(ALAKAZAM):
            min_inc += 1      # アメ+フーディン: 手札-2、ドロー3 → 純+1
            max_inc += 1
        elif pk.id == DUNSPARCE and hc.get(DUDUNSPARCE):
            min_inc += 2      # 進化でドロー3、手札から1枚消費 → 純+2
            max_inc += 2
        elif pk.id == DUDUNSPARCE and not _dudunsparce_used_at(slot):
            min_inc += 3      # Run Away Draw(自身は山札に戻る)。個体ごとに1回
            max_inc += 3
        elif pk.id == FEZANDIPITI and not _used_fezandipiti:
            # ★参考実装は無条件に+3していたが、実際は「相手の前の番に自分の
            #   ポケモンがきぜつしていたなら」という条件付き。
            if _lost_pokemon_last_turn or not USE_FEZANDIPITI_CONDITION:
                min_inc += 3
                max_inc += 3

    # 手札のキチキギスexをベンチに出してから使う場合(出す-1、ドロー+3 → 純+2)
    if (hc.get(FEZANDIPITI) and p.bench_free > 0
            and not fc.get(FEZANDIPITI)
            and (_lost_pokemon_last_turn or not USE_FEZANDIPITI_CONDITION)):
        max_inc += 2

    # サポートは1枚だけ
    sup = []
    if not state.supporterPlayed:
        if hc.get(DAWN):
            sup.append(2)          # ヒカリ
        if hc.get(HILDA):
            sup.append(1)          # トウコ
    if sup:
        max_inc += max(sup)
        min_inc += max(sup)        # 撃つと決めれば確定

    # リッチエネルギー(ACE SPEC): フーディンに超エネが既に付いていれば
    if (hc.get(ENRICHING_ENERGY) and not state.energyAttached
            and p.active_id == ALAKAZAM and p.active_has_psychic):
        max_inc += 3

    p.min_hand = p.hand_size + min_inc
    p.max_hand = p.hand_size + max_inc
    p.min_dmg = p.min_hand * DAMAGE_PER_CARD
    p.max_dmg = p.max_hand * DAMAGE_PER_CARD
    # このターン、まだ手札を増やす手が残っているか。
    # 残っているなら「殴る」より先にそちらを済ませる。
    p.growth_available = max_inc > 0

    # ---- 攻撃目標の決定 ----
    op_active = op.active[0] if op.active else None
    if state.turn < 2 or op_active is None:
        return p

    my_prize = len(me.prize) if me.prize is not None else 6

    # ユンゲラーで足りるならフーディンを温存する
    if op_active.hp <= 30 and (fc.get(KADABRA) or p.active_id == KADABRA):
        p.target_idx, p.target = 0, op_active
        p.can_kill = p.sure_kill = True
        p.prize_gain = _prize_value(op_active)
        p.kadabra_finish = True
        return p

    # ベンチを狙えるのは、実際にボスの指令を撃てるときだけ。
    # (持っていないのにベンチを目標にすると、引っぱれないまま攻撃を
    #  先送りし続けて何もできなくなる)
    boss_available = (bool(hc.get(BOSS_ORDERS)) and not state.supporterPlayed
                      if USE_BOSS_AVAILABILITY else True)

    cands = [(0, op_active)]
    if boss_available:
        for i, b in enumerate(op.bench or []):
            if b is not None:
                cands.append((i + 1, b))

    scored = []
    for idx, pk in cands:
        pz = _prize_value(pk)
        scored.append((idx, pk, pz,
                       pk.hp <= p.max_dmg,     # 届く可能性がある
                       pk.hp <= p.min_dmg))    # 確実に届く

    # 優先1: 倒せば勝ちが決まる相手
    win = [x for x in scored if x[3] and my_prize <= x[2]]
    pool = win if win else [x for x in scored if x[3]]
    if pool:
        # 確定で倒せるものを優先し、次にサイド獲得数、次にHP(硬い方から潰す)
        best = max(pool, key=lambda x: (x[4], x[2], x[1].hp))
        p.target_idx, p.target, p.prize_gain, p.can_kill, p.sure_kill = best
        p.use_boss = p.target_idx != 0
    else:
        p.target_idx, p.target = 0, op_active

    # 山札切れの管理。このデッキは毎ターン大量に引くので、放っておくと
    # 山札が尽きて自滅する(実測: 自作は300試合中59回=19.7%が山札0で敗北。
    # 公開実装は4.7%)。公開実装の原則:
    #   「山札の残りを、自分の残りサイドより少なくしてはいけない。
    #    ただしこのターンの攻撃で残りサイドを全部取って勝てるなら0でもよい」
    p.can_win_now = p.can_kill and my_prize <= p.prize_gain
    if p.can_win_now:
        p.safe_draws = 99
    else:
        # バッファは「次の自分の番の開始時ドロー」分が最低1。
        # 大きくすると安全側だが、引けないぶん打点が落ちる。実測で決める。
        # ルール1: USE_SETUP_V2 では厚めのバッファで「絶対にデッキ切れしない」に寄せる。
        buf = DECK_SAFETY_BUFFER_V2 if USE_SETUP_V2 else DECK_SAFETY_BUFFER
        # 長期戦になる相手(イワパレス/ワナイダー)では更に引き控える。
        # これらの相手には負けの大半が山札切れだった。
        if USE_GRINDY_SAFETY and p.op_grindy:
            buf = GRINDY_SAFETY_BUFFER
        p.safe_draws = max(0, (me.deckCount or 0) - my_prize - buf)

    # 今の手札のままで目標を倒しきれるか(倒せるなら伸ばさずに殴ってよい)
    if p.target is not None:
        cur = p.hand_size * DAMAGE_PER_CARD
        p.lethal_now = cur >= p.target.hp and not p.use_boss
        # 「もっと引く」は打点が足りない場合だけ。use_boss を条件に混ぜると
        # ボスを撃てない局面で攻撃が永久に止まる。
        if p.can_kill and cur < p.target.hp:
            p.need_more_hand = True
    return p


# ---------------------------------------------------------------- スコアリング
def _deck_cost(o, obs, me, p: Plan) -> int:
    """この選択肢が山札から減らす枚数。分からないものは0。"""
    t = o.type
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        return _DECK_COST_PLAY.get(card.id, 0) if card else 0
    if t == OptionType.EVOLVE:
        # ★gh._get_card は EVOLVE の選択肢で必ず None を返す(playerIndex を
        #   持たないため)。手札から引き直さないとこの分岐が死ぬ。
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        return _DECK_COST_EVOLVE.get(card.id, 0) if card else 0
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        return _DECK_COST_ABILITY.get(card.id, 0) if card else 0
    if t == OptionType.ATTACH:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is not None:
            if card.id == ENRICHING_ENERGY:
                return 4      # 付けたとき4枚ドロー
            if card.id == TELEPATH_PSYCHIC:
                return 2      # 付けたとき超たね2枚をベンチへ
    return 0


def _preevo_snipe_target(op, p: Plan):
    """完成すると手に負えない大型exの「進化前」がベンチにいたら、その位置を返す。

    倒しきれる場合だけ返す(引きずり出しても倒せないなら、こちらが殴られるだけ)。
    完成形が既に場にいる場合は手遅れなので狙わない。
    """
    dmg = p.hand_size * DAMAGE_PER_CARD
    for i, b in enumerate(op.bench or []):
        if b is None or b.id not in PREEVO_TARGETS:
            continue
        if b.hp > dmg:
            continue                       # 倒しきれないなら意味がない
        # 完成形が既に出ているなら、進化前を狩っても遅い
        if PREEVO_TARGETS[b.id] in p.op_ids:
            continue
        return (i + 1, b)
    return None


def _boss_disrupt_target(op, p: Plan):
    """ボスで引きずり出して潰す価値のあるベンチのポケモンを返す(無ければ None)。

    上位勢が実際に引きずり出した209体と、見送った1348体を比較すると、
    **HP・エネ量・ex率・倒しやすさには差が無かった**(通説はすべて外れ):
        HP 107.6 vs 102.5 / エネ 0.3 vs 0.2 / ex 10.5% vs 8.8% / 倒せる 88% vs 90%
    唯一有意なのは **たね率 56% vs 69%(-13pp) = 進化済みを狙う**。
    そして狙われた顔ぶれが答え:
        Froslass22 / Munkidori17 / Roserade14 / Kadabra11 / Fezandipiti ex10
    いずれも**場にいるだけで仕事をする特性持ちの中核(エンジン)**。
    → 基準は「倒しやすさ」でも「サイド枚数」でもなく、
      **相手のエンジンを引きずり出して機能停止させること**。

    ただし**「今このターン倒し切れるex」が最優先**。妨害(特性を止める)は
    相手のテンポを削るだけだが、exのKOはサイドを2〜3枚進める確定利益なので、
    完成したフーディンで倒し切れるなら妨害より常に優先する。
    """
    dmg = p.hand_size * DAMAGE_PER_CARD
    # フーディンが完成していて実際に殴れるか(倒し切れる判定の前提)
    can_attack = p.active_id == ALAKAZAM and p.active_has_psychic
    best = None
    best_score = 0.0
    for i, b in enumerate(op.bench or []):
        if b is None:
            continue
        d = gh._CARD.get(b.id)
        if d is None:
            continue
        score = 0.0
        killable = b.hp <= dmg
        is_ex = bool(d.ex or d.megaEx)
        # 0) 最優先: 完成フーディンで倒し切れる ex。妨害より確定のサイド獲得。
        if can_attack and killable and is_ex:
            score += 400.0 + 50.0 * _prize_value(b)
        # 1) 特性持ち = 相手のエンジン。前に出せば仕事をさせにくくなる。
        if getattr(d, "skills", None):
            score += 100.0
        # 2) 進化済みを狙う(たねは避ける)。育て直しのコストが高い。
        if not d.basic:
            score += 60.0
        # 3) 倒しきれるなら更に良い(ただし主目的ではない)
        if killable:
            score += 40.0
        # 4) サイドが多く取れるなら加点(副次的)
        score += 15.0 * _prize_value(b)
        if score > best_score:
            best_score, best = score, (i + 1, b)
    # 特性持ちでも進化済みでもない的を引きずり出す価値は薄い(手札-1=打点-20)
    if best_score < 100.0:
        return None
    return best


def _bonus(o, obs: Observation, state, me, op, p: Plan, ctx=None) -> float:
    """フーディン固有の加点/減点。汎用スコアに足す。"""
    t = o.type
    hc = p.hand_counts

    # 山札切れの回避。引きすぎると次の番のドローができずに負ける。
    if USE_DECK_SAFETY:
        if _deck_cost(o, obs, me, p) > p.safe_draws:
            return -8000.0
        # せいなるはい: トラッシュのポケモンを山札に戻す = 山札切れの回復札
        if t == OptionType.PLAY:
            c = gh._hand_card(obs, o.index, me)
            if c is not None and c.id == SACRED_ASH and p.safe_draws <= 4:
                return 3000.0

    # ---- ワザ ----
    if t == OptionType.ATTACK:
        if o.attackId == ATK_POWERFUL_HAND:
            # 攻撃はターンを終わらせるので、先に手札を伸ばしたい。ただし
            # 「伸ばせる余地があるなら常に待つ」は成立しない(待ち続けて
            # 何もせずターンを渡してしまい、実測で 46% → 18% に悪化した)。
            # 届く見込みのあるKOを逃す場合だけ強く止め、それ以外は
            # 進化やドローに負ける程度の弱いペナルティに留める。
            if p.need_more_hand:
                return -5000.0
            dmg = p.hand_size * DAMAGE_PER_CARD
            s = 3000.0 + dmg
            if p.lethal_now:
                s += 4000 + p.prize_gain * 1000
            elif p.growth_available:
                s -= ATTACK_DELAY_PENALTY
            return s
        if o.attackId == ATK_SUPER_PSY_BOLT:
            return 3500.0 if p.kadabra_finish else -1000.0
        if o.attackId == ATK_TELEPORT:
            # ケーシィの「テレポート」は10ダメージだが、自分をベンチと入れ替える。
            # 逃げエネを払わずに配置を直せるので、
            #   ・バトル場が非アタッカー(ケーシィ)で
            #   ・ベンチにエネ付きのフーディン/ユンゲラーがいて
            #   ・逃げるだけのエネルギーが無い
            # ときは、10ダメージ + 次の番に殴れる形、として価値がある。
            # 注意: このワザ自体のコストが【超】1個で、ケーシィの逃げエネも1個。
            # つまり「撃てる = 逃げられる」ので、「逃げエネが無いとき」を条件に
            # すると絶対に成立しない(最初の実装がこれで、使用回数0だった)。
            # 逃げてもターンは終わらないぶん逃げる方が得なので、テレポートの
            # 出番は「このターンすでに逃げた後」に限られる。
            if USE_TELEPORT and state.retreated:
                better = any(
                    b is not None and b.id in (ALAKAZAM, KADABRA)
                    for b in (me.bench or []))
                if better:
                    return 2000.0
            return -3000.0          # それ以外は10ダメージの無駄撃ち
        return 0.0

    # ---- 特性 ----
    if t == OptionType.ABILITY:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            # ABILITY の選択肢は playerIndex=None のことがあり、_get_card では
            # 取れない(実戦のリプレイ 88050459 で判明)。
            # ここで全面的に補完すると、今まで素通り(0.0)だった他の特性の
            # ペナルティが一斉に発火して棋力が落ちた(51〜53% → 44.8%, 実測)ので、
            # **自殺手の検出にだけ**使う。他の特性は従来どおり素通りさせる。
            try:
                if o.area == AreaType.ACTIVE and me.active:
                    c2 = me.active[o.index or 0]
                elif o.area == AreaType.BENCH and me.bench:
                    c2 = me.bench[o.index or 0]
                else:
                    c2 = None
            except (IndexError, TypeError):
                c2 = None
            # ノココッチの特性は自身を山札に戻す。バトル場でベンチが空なら
            # 場が全滅して即負けるので、そこだけは絶対に禁止する。
            if (c2 is not None and c2.id == DUDUNSPARCE
                    and o.area == AreaType.ACTIVE
                    and not [c for c in (me.bench or []) if c is not None]):
                return -1e9
            return 0.0
        if card.id == DUDUNSPARCE:
            # ★自殺手の禁止(2026-07-25 実戦のラダーで負けた実例あり)
            # ノココッチの特性は「3枚引いて**自身を山札に戻す**」。バトル場にいて
            # ベンチが空のときに使うと、場のポケモンが全滅してその場で負ける。
            # 実際にターン4で場を空にして敗北したリプレイ(88050459)がある。
            # -2000 では「他がもっと低い」ときに選ばれてしまうので、
            # 絶対に選ばれない値で禁止する。
            on_active = (o.area == AreaType.ACTIVE
                         or o.inPlayArea == AreaType.ACTIVE
                         or (p.active is not None and card is p.active))
            bench_count = len([c for c in (me.bench or []) if c is not None])
            if on_active and bench_count == 0:
                return -1e9
            # 自身が山札に戻るので、手札が足りているなら使わない
            if (o.area, o.index) in _used_dudunsparce_slots:
                return -2000.0    # この個体は今ターン使用済み
            if not p.need_more_hand:
                return -2000.0
            return 2500.0
        if card.id == FEZANDIPITI:
            if USE_FEZANDIPITI_CONDITION and not _lost_pokemon_last_turn:
                return -2000.0      # 条件を満たしていないので撃てない/無駄
            return 2400.0 if p.need_more_hand else -500.0
        return 0.0

    # ---- 進化(ドローが付いてくるので基本的に最優先) ----
    if t == OptionType.EVOLVE:
        # ★同上: EVOLVE は playerIndex を持たないので _get_card が None を返す。
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None and o.area == AreaType.HAND:
            card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None
        # 公開実装の優先順: フーディン(バトル場) → ユンゲラー → ノココッチ
        #                  → フーディン(ベンチ)
        if USE_NOTEBOOK_RULES and cid == ALAKAZAM:
            on_active = (o.inPlayArea == AreaType.ACTIVE)
            return 3000.0 if on_active else 2300.0
        if cid == ALAKAZAM:
            return 3000.0           # ドロー3
        if cid == KADABRA:
            return 2600.0           # ドロー2
        if cid == DUDUNSPARCE:
            return 2400.0           # ドロー3
        return 1500.0

    # ---- 手札からのプレイ ----
    if t == OptionType.PLAY:
        card = gh._hand_card(obs, o.index, me)
        cid = card.id if card else None

        # 手札が減るだけのカードは、フーディンで殴れる状態なら打点をそのまま失う。
        # 確定でKOできる場合は打点に余裕があるので気にしない。
        cost = 0.0
        if (HAND_COST_PENALTY and cid in _HAND_NEGATIVE
                and p.active_id == ALAKAZAM and p.active_has_psychic
                and not p.lethal_now):
            cost = HAND_COST_PENALTY

        if cid == DAWN:
            # 純+2。打っただけで打点+40なので、KOが見えていなくても常に高い。
            if USE_HAND_ECONOMY:
                return 2400.0
            return 2200.0 if p.need_more_hand else 800.0
        if cid == HILDA:
            # 純+1。同上。
            if USE_HAND_ECONOMY:
                return 2250.0
            return 2100.0 if p.need_more_hand else 700.0
        if cid == BOSS_ORDERS:
            # 手札が1枚減るので、ベンチを引っぱる必要があるときだけ
            if p.use_boss and p.can_kill:
                return 2300.0
            # 大型exの進化前(リオル等)を、完成する前に引きずり出して倒す。
            if USE_PREEVO_SNIPE and _preevo_snipe_target(op, p) is not None:
                return 2320.0
            # --- 序盤妨害としてのボス(上位勢の実測に基づく) ---
            # 上位勢663回の使用局面を分析すると、通説と違い「決め技」ではなかった:
            #   ・78% は手札にドローサポ(ヒカリ/トウコ)もある = **ドローを捨てて撃つ**
            #   ・自分のサイド残は最頻値6(44%)、平均4.66 = **序盤から撃つ**
            #   ・47% はバトル場が準備済みフーディンでない = 殴れなくても撃つ
            #   ・ターン平均7.3
            # つまり「相手が育てようとしているキーポケモンを引きずり出して潰す」妨害。
            # 自作は KO確定時のみ(0.66回/試合)で、この発想が欠けていた(上位1.79回)。
            # ただしイワパレス相手は倒せないので温存する(上位0.79回と半減)。
            if USE_ARCHETYPE_BOSS and not p.op_crustle:
                target = _boss_disrupt_target(op, p)
                if target is not None:
                    # ドロー(ヒカリ2400/トウコ2250)より上に置くと打点を捨てる。
                    # 上位勢はそれをやっているが、フーディンは手札=打点なので
                    # 「引きずり出す価値が高い的」に限る。
                    return 2350.0
            return -2500.0
        if cid == RARE_CANDY:
            base = 2000.0 if hc.get(ALAKAZAM) else -500.0
            # ルール2: まだフーディンが場にいなければ、アメで即立てるのを最優先に。
            if USE_SETUP_V2 and hc.get(ALAKAZAM) and not p.field_counts.get(ALAKAZAM):
                base = 2800.0
            return base - cost
        if cid == POFFIN:
            # たね展開。ケーシィ系は場に3体が理想(公開実装の原則)。
            # ベンチは1枠空けておく(進化元やキチキギスexを置く余地を残す)。
            line = p.field_counts.get(ABRA, 0) + p.field_counts.get(KADABRA, 0) \
                + p.field_counts.get(ALAKAZAM, 0)
            if USE_NOTEBOOK_RULES and p.bench_free <= 1:
                return -1200.0
            return (1800.0 if line < 3 else 300.0) - cost
        if cid == POKE_PAD:
            return 1200.0 - cost
        # --- 上位勢の主力構築のカード ---
        if cid == LANAS_AID:
            # トラッシュから非ex/基本エネを3枚回収。実測で我々の最大の負け筋は
            # 「場切れ」と「山札切れ」なので、ケーシィ系やエネを拾い直せるこの札は
            # そこに直接効く。手札も純+2(1枚使って3枚回収)なので打点も上がる。
            return 2350.0
        if cid == XEROSIC:
            # 相手の手札を3枚まで捨てさせる妨害。相手の手札が多いほど価値が高い。
            # 自分は手札-1(打点-20)を払うので、相手が溜め込んでいる時に撃つ。
            op_hand = op.handCount if op.handCount is not None else 0
            if op_hand >= 7:
                return 2200.0
            if op_hand >= 5:
                return 1500.0
            return -500.0
        if cid == NIGHTTIME_MINE:
            # テラポケモンのワザコスト+1。相手にテラがいる時だけ意味がある。
            # スタジアムは張り替え合戦になるので、自分の場に既にあるなら不要。
            try:
                ours = bool(state.stadium) and state.stadium[0].id == NIGHTTIME_MINE
            except (IndexError, AttributeError, TypeError):
                ours = False
            if ours:
                return -1500.0
            # 相手スタジアムを潰す価値は常にある(相手のスタジアムが出ている時)
            return 900.0 if state.stadium else 300.0
        if cid == BATTLE_CAGE:
            op_all = [c for c in (op.active or []) if c] + \
                     [c for c in (op.bench or []) if c]
            if any(c.id in DRAGAPULT_LINE for c in op_all):
                return 1900.0 - cost      # ドラパルト対策
            return -800.0
        if cid == ENHANCED_HAMMER:
            # 手札-1 = 打点-20 を毎回払う。公開実装は150試合で一度も使わず、
            # 自作は1試合1.41回使っていた。相手のワザを止められる保証もないので
            # 基本は撃たない。特殊エネが実際に付いている相手にだけ意味がある。
            # 公開実装は150試合で一度も使わないので「手札-1=打点-20が損」と考えて
            # 禁止してみたが、**逆効果だった**(600試合で 42.3% → 38.0%)。
            # 使用回数は1.37→0.00、殴る瞬間の平均手札は13.91→14.41枚と
            # 公開実装(14.33〜14.44)に並んだのに勝率は下がった。
            # 相手のテレパス超エネを割るとフーディンの攻撃自体を止められるので、
            # 打点20を払う価値がある。打点差は負けの原因ではなく相関でしかなかった。
            return 900.0 - cost
        if cid == PSYDUCK:
            op_all = [c for c in (op.active or []) if c] + \
                     [c for c in (op.bench or []) if c]
            return 1400.0 if any(c.id == DUSKULL for c in op_all) else -2000.0
        if cid == SHAYMIN:
            op_all = [c for c in (op.active or []) if c] + \
                     [c for c in (op.bench or []) if c]
            # ベンチ狙撃デッキ(オーロンゲex/ドラパルト/メガスターミー)相手には
            # 「はなのカーテン」でフーディン線(全て非ex)を丸ごと守れる。
            # 上位勢はオーロンゲ相手に65%出す。ベンチ枠は空いている時に限る。
            if USE_SHAYMIN_VS_SNIPER and p.op_sniper and p.bench_free > 0:
                return 2000.0
            if any(c.id in WATER_THREATS for c in op_all):
                return 1400.0
            return -2000.0
        if cid == FEZANDIPITI:
            return 1000.0 if _lost_pokemon_last_turn else -1500.0
        if cid in (ABRA, DUNSPARCE):
            return 1300.0
        return 0.0

    # ---- エネルギー・どうぐ付け ----
    if t == OptionType.ATTACH:
        # ATTACHの選択肢は playerIndex=None なので _get_card では取れない。
        # 付けるエネは手札にあるので me.hand から取る。
        # ※ ただし ATTACH_FIX を有効にすると、下の未調整なエネ振り分けが
        #   走って**逆効果**になる(50.3%→43.7%, 実測)。振り分けのスコア値は
        #   バグで一度も実行されておらず未検証だった。既定では元の挙動
        #   (cid=None で振り分けをスキップ)に合わせて False にしてある。
        card = (gh._hand_card(obs, o.index, me)
                if (ATTACH_FIX and o.area == AreaType.HAND) else None)
        cid = card.id if card else None

        # --- ケーシィ先付け(実験): バトル場のフーディンが既に殴れる状態で、
        # このターンまだエネを付けていないなら、ベンチのケーシィ/ユンゲラー
        # (超エネ未装備)に先付けして、次のアタッカーを準備する。
        # 攻撃(Powerful Hand ~3300)より上に置き、殴る前に付ける。
        # 注意: フーディンの打点は手札枚数×20なので、手札のエネを場に付けると
        #   そのターンの打点が20下がる。確定KOを逃さないよう lethal_now では発動しない。
        if USE_CASEY_PRELOAD and o.area == AreaType.HAND and not state.energyAttached \
                and not p.lethal_now and p.active_id == ALAKAZAM and p.active_has_psychic:
            ecard = gh._hand_card(obs, o.index, me)
            if ecard is not None and ecard.id in PSYCHIC_ENERGIES \
                    and o.inPlayArea == AreaType.BENCH and me.bench:
                bt = me.bench[o.inPlayIndex or 0]
                if bt is not None and bt.id in ABRA_LINE \
                        and not any(e.id in PSYCHIC_ENERGIES for e in (bt.energyCards or [])):
                    return 3600.0

        if not USE_NOTEBOOK_RULES:
            if o.inPlayArea == AreaType.ACTIVE and p.active_id in ABRA_LINE:
                return 1000.0
            if o.inPlayArea == AreaType.BENCH:
                return 200.0
            return 100.0

        # 付け先のポケモンを特定する
        dest = None
        try:
            if o.inPlayArea == AreaType.ACTIVE and me.active:
                dest = me.active[o.inPlayIndex or 0]
            elif o.inPlayArea == AreaType.BENCH and me.bench:
                dest = me.bench[o.inPlayIndex or 0]
        except (IndexError, TypeError):
            dest = None
        dest_id = dest.id if dest else -1
        dest_energy = len(dest.energyCards or []) if dest else 0
        is_active = o.inPlayArea == AreaType.ACTIVE

        # ラッキーメット: 殴られるたび2ドロー。ゲノセクト(特性でACE SPECを封じる)に
        # 付けられるならそこ、なければバトル場のポケモンに。
        if cid == LUCKY_HELMET:
            if dest_id == GENESECT:
                return 1600.0
            return 1100.0 if is_active else 200.0

        # リッチエネルギー(付けたとき4ドロー)はノコッチ系に回す。
        # フーディンのエネ枠を潰さないため。
        if cid == ENRICHING_ENERGY:
            if dest_id in DUNSPARCE_LINE:
                return 1500.0
            return 300.0 if not p.active_has_psychic else 100.0

        # 基本超/テレパス超はケーシィ系(アタッカー)に。
        # テレパス超は付けたとき超たね2枚をベンチに出せる展開札でもある。
        if cid in PSYCHIC_ENERGIES:
            if dest_id in ABRA_LINE:
                # 同じポケモンに2個以上付けない(1個で撃てるため無駄)
                if dest_energy >= 1:
                    return -1500.0
                return 1400.0 if is_active else 1200.0
            return -800.0

        if is_active:
            return 400.0
        return 200.0

    # ---- 選択(サーチ先・ボスの対象など) ----
    if t == OptionType.CARD:
        card = gh._get_card(obs, o.area, o.index, o.playerIndex)
        if card is None:
            return 0.0
        # 相手の場から選ぶ場面(ボスの指令の対象など)
        if o.playerIndex is not None and o.playerIndex != state.yourIndex:
            # ★改造ハンマーの対象(2026-07-29 ユーザー要望: 対ワナイダー対策)。
            #   ロケット団エネルギー(15)は「超と悪を好きな組み合わせで**2個ぶん**」。
            #   ミュウツーexのイレイザーボールは[超,超,無]で、
            #   **ロケット団エネ1枚+何か1個で完成する**。つまりこれを割ると
            #   3個中2個が飛び、ミュウツーexが完全に機能停止する。
            #   ワナイダー本体(ロケットラッシュ=[草,無])に付いた分は
            #   基本草で代替できるので価値が低い。
            if USE_HAMMER_TARGETING and ctx == SelectContext.DISCARD_ENERGY_CARD:
                sc = 0.0
                for e in (getattr(card, "energyCards", None) or []):
                    if getattr(e, "id", None) != ROCKET_ENERGY:
                        continue
                    sc = 2000.0
                    if card.id == ROCKET_MEWTWO_EX:
                        sc += 2500.0     # 3個中2個が飛ぶ。最優先
                    elif card.id in SPIDOPS_LINE:
                        sc += 200.0      # 草で代替されるので価値は低い
                if sc:
                    return sc
            if p.use_boss and p.target is not None and o.index == p.target_idx - 1:
                return 2000.0
            # 大型exの進化前を狩る(リオル等)。妨害より優先。
            if USE_PREEVO_SNIPE:
                t = _preevo_snipe_target(op, p)
                if t is not None and o.index == t[0] - 1:
                    return 2500.0
            # 妨害ボスで撃つと決めた的(KO確定でない序盤妨害)
            if USE_ARCHETYPE_BOSS and not p.op_crustle:
                t = _boss_disrupt_target(op, p)
                if t is not None and o.index == t[0] - 1:
                    return 1800.0
            return 0.0
        # トラッシュからの回収(Lana's Aid / 夜のタンカ / せいなるはい)。
        # 場切れ・山札切れが最大の負け筋なので、アタッカーの進化ラインを最優先で拾う。
        if o.area == AreaType.DISCARD:
            if card.id in (ALAKAZAM, KADABRA):
                return 1100.0
            if card.id == ABRA:
                return 1000.0        # 場を維持するたねが最重要
            if card.id in PSYCHIC_ENERGIES:
                return 800.0
            if card.id in DUNSPARCE_LINE:
                return 600.0
        # 自分側: 進化ラインを優先して手札に加える
        if card.id == ALAKAZAM:
            return 900.0
        if card.id == KADABRA:
            return 800.0
        if card.id == DUDUNSPARCE:
            return 700.0
        if card.id == ABRA:
            return 600.0
        if card.id == DUNSPARCE:
            return 500.0
        if card.id in PSYCHIC_ENERGIES:
            return 400.0
        return 0.0

    # ---- ベンチ/バトル場への配置 ----
    if t in (OptionType.RETREAT,):
        # ルール3(逃げ版): ベンチに超エネ付きフーディンがいて、今の前が
        # 「準備済みフーディン」でないなら、入れ替えて即戦力を前に出す。
        if USE_SETUP_V2:
            bench_ready = any(b is not None and b.id == ALAKAZAM and _has_psychic(b)
                              for b in (me.bench or []))
            active_ready = p.active_id == ALAKAZAM and p.active_has_psychic
            if bench_ready and not active_ready:
                return 1200.0
        # フーディンを前に出したいときだけ逃げる
        if p.active_id not in ABRA_LINE and (p.field_counts.get(ALAKAZAM)
                                             or p.field_counts.get(KADABRA)):
            return 600.0
        return -500.0

    return 0.0


def _switch_bonus(o, obs, state, me, p: Plan) -> float:
    """SWITCH / TO_ACTIVE / SETUP 系で、どのポケモンを前に置くか。"""
    card = gh._get_card(obs, o.area, o.index, o.playerIndex)
    if card is None or (o.playerIndex is not None
                        and o.playerIndex != state.yourIndex):
        return 0.0
    energy = len(card.energyCards or []) if hasattr(card, "energyCards") else 0
    if card.id == ALAKAZAM:
        if USE_SETUP_V2:
            # ルール3: 超エネ付きフーディンは最優先で前に出す。
            if _has_psychic(card):
                return 3000.0
            # ルール4: エネ無しでも手札に超エネがあれば前に出す(次の番に殴れる形)。
            if p.psychic_in_hand:
                return 1800.0
            return 1000.0
        return 1000.0 + energy * 100
    if card.id == KADABRA:
        return 900.0 if p.kadabra_finish else 300.0
    if card.id == ABRA:
        return 200.0
    if card.id in DUNSPARCE_LINE:
        return 100.0
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

        _update_turn_state(state, me, op)
        plan = _build_plan(obs, state, me, op)

        ctx = select.context
        scores = []
        for o in select.option:
            base = gh._score_option(o, obs, me, op) if USE_GENERIC_BASE else 0.0
            # ★相手の場から選ぶ選択肢は _switch_bonus ではなく _bonus に回す
            #   (2026-07-29。ワナイダー/オーロンゲで見つけたのと同じバグ)。
            #   引きずり出しや改造ハンマーの対象は ctx=3(SWITCH) 等で来るが、
            #   `_switch_bonus` は相手側の選択肢に一律 0.0 を返すため、
            #   **対象選択のロジックが一度も適用されていなかった**。
            is_opponent_side = (o.playerIndex is not None
                                and o.playerIndex != state.yourIndex)
            if ctx in (SelectContext.SWITCH, SelectContext.TO_ACTIVE,
                       SelectContext.SETUP_ACTIVE_POKEMON,
                       SelectContext.SETUP_BENCH_POKEMON) \
                    and not (is_opponent_side and USE_OPPONENT_SIDE_BONUS_AL):
                extra = _switch_bonus(o, obs, state, me, plan)
            else:
                extra = _bonus(o, obs, state, me, op, plan, ctx)
            scores.append(base + extra)

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # 特性を使ったらフラグを立てる(同じターンに二度使えないため)
        if select.option:
            top = select.option[order[0]]
            if top.type == OptionType.ABILITY:
                card = gh._get_card(obs, top.area, top.index, top.playerIndex)
                if card is None:
                    # ABILITY は playerIndex=None のことがあり _get_card が None を
                    # 返す。補完しないと使用済みが記録されず同じ個体を選び続ける。
                    try:
                        if top.area == AreaType.ACTIVE and me.active:
                            card = me.active[top.index or 0]
                        elif top.area == AreaType.BENCH and me.bench:
                            card = me.bench[top.index or 0]
                    except (IndexError, TypeError):
                        card = None
                if card is not None:
                    global _used_fezandipiti
                    if card.id == DUDUNSPARCE:
                        # ★個体ごとに記録(場に2体いればそれぞれ1回使える)
                        _used_dudunsparce_slots.add((top.area, top.index))
                    elif card.id == FEZANDIPITI:
                        _used_fezandipiti = True

        lo = select.minCount if select.minCount is not None else 1
        hi = select.maxCount if select.maxCount is not None else 1
        k = min(max(lo, 1), hi, len(order))

        # ★「N枚まで選べる」場面の取り漏らし修正(2026-07-26)
        # 上の k は最小枚数しか取らないため、複数枚選べる場面で1枚しか取って
        # いなかった。実測(対公開フーディン40試合)で:
        #   ctx=5  57回 平均1.00枚/上限2.00枚 … 山札からケーシィ/ノコッチを2枚
        #   ctx=9  26回 平均1.00枚/上限4.00枚 … **Lana's Aid でトラッシュから回収**
        # 特に Lana's Aid は最大の負け筋(場切れ・山札切れ)への回復札なので、
        # 1枚しか拾えないのは致命的だった。上限まで拾う。
        if USE_PICK_MAX and hi > k and select.option:
            cand = [i for i in order
                    if _is_worth_picking(select.option[i], obs, me)]
            if len(cand) >= k:
                take = hi
                # ベンチに出す系(山札のたね)は空き枠を超えて取らない
                # ※ agent() 内の Plan 変数は `plan`(_bonus 内は `p`)。
                #   ここを p にすると NameError が except に握りつぶされて
                #   修正が丸ごと無効化される(オーロンゲで実際に踏んだ)。
                if _is_basic_pokemon_opt(select.option[cand[0]], obs, me):
                    take = min(take, max(1, plan.bench_free))
                # 山札から取る場合は山札切れの安全余裕を超えない。
                # (上限まで取ると山札切れ負けが 0%→8% に増えたため)
                if select.option[cand[0]].area == AreaType.DECK:
                    take = min(take, max(1, plan.safe_draws))
                return cand[:take]
        return order[:k]
    except Exception:
        # 何があっても合法手を返す
        return gh.agent(obs_dict)
