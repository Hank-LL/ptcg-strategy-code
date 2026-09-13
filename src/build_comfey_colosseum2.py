"""提出物 submission_comfey_colosseum2.tar.gz の組み立て + 検証。

同梱物:
    main.py               = main_comfey.py
    comfey_heuristic.py (キュワワー・ミル固有ロジック)
    generic_heuristic.py  (土台の汎用ロジック)
    deck.csv              = ワナイダーデッキ
    cg/                   (公式ライブラリ)

※ meta/opponents/ の外部エージェント(他者の公開物)は同梱しない。

使い方(~/ptcg/src で実行):
    python build_comfey.py            # 組み立て + 検証
    python build_comfey.py --no-test  # 組み立てのみ
"""

import glob
import os
import subprocess
import sys
import tarfile
import tempfile

OUT = "submission_comfey_colosseum2.tar.gz"
# デッキは hikarimaru(882) の実戦81試合から抽出した構築をそのまま使う
# (439試合の実測で総合55%、勝ちの4割が相手の山札切れ)。
# ★カポエラー1枚を**バトルコロシアム**に差し替えた版を使う(2026-08-02)。
#   ベンチにダメカンを置く手段(ファントムダイブ/アドレナブレイン/こごえるとばり)を
#   まとめて止める。実測: 対ドラパルトのベンチ被害 2510→1470、
#   アリーナ総合 76.0%±1.4 → 78.6%±1.7。
# ★さらに ハンドトリマー1枚 → **オーガポン いしずえのめんex(117)** に差し替え
#   (2026-08-03)。特性持ちが主力の相手には「ワザのダメージが一切通らない壁」。
#   ただし**ダメカン(マシマシラ/ユキメノコ/ドラパルト)は素通り**するので、
#   ダメカン源を一度でも見た相手には出さない。
#   実測(5反復×24試合): 対ワナイダー 64.2%→**91.7%** / 対ブリジュラス 87.5%→91.7%
#   / 対オーロンゲ 50.8%→55.0%。アリーナ総合 78.1%±1.7 → 79.7%±2.1。
DECK_SRC = "../meta/top_decks/deck_comfey_colosseum2.csv"
POOL = "../meta/top_decks"

# (アーカイブ内の名前, コピー元)
FILES = [
    ("main.py", "main_comfey.py"),
    ("comfey_heuristic.py", "comfey_heuristic.py"),
    ("generic_heuristic.py", "generic_heuristic.py"),
    ("deck.csv", DECK_SRC),
]
DIRS = ["cg"]


def build():
    for arc, src in FILES:
        if not os.path.exists(src):
            sys.exit(f"エラー: {src} がありません")
    for d in DIRS:
        if not os.path.isdir(d):
            sys.exit(f"エラー: {d}/ がありません")

    with open(DECK_SRC) as f:
        n = len([x for x in f.read().split("\n") if x.strip()])
    if n != 60:
        sys.exit(f"エラー: デッキが{n}枚(60でない)")

    with tarfile.open(OUT, "w:gz") as tar:
        for arc, src in FILES:
            tar.add(src, arcname=arc)
        for d in DIRS:
            tar.add(d, arcname=d)

    size_mb = os.path.getsize(OUT) / 1e6
    print(f"作成完了: {OUT} ({size_mb:.1f} MB)  デッキ{n}枚")
    with tarfile.open(OUT) as tar:
        print("内容:", [x for x in tar.getnames() if "/" not in x], "+ cg/")


def test():
    """展開した状態を再現し、プール全デッキ相手に完走するか確認する。"""
    print("\n--- 検証: 展開して全デッキ相手に対戦 ---")
    pool = os.path.abspath(POOL)
    src = os.path.abspath(".")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(OUT) as tar:
            tar.extractall(tmp)
        script = f'''
import glob, os, sys, time, traceback
sys.path.insert(0, {tmp!r})
os.chdir({tmp!r})
import importlib.util
spec = importlib.util.spec_from_file_location("sub", os.path.join({tmp!r}, "main.py"))
m = importlib.util.module_from_spec(spec); sys.modules["sub"] = m
spec.loader.exec_module(m)
sys.path.insert(0, {src!r})
from cg.game import battle_start, battle_select, battle_finish
import generic_heuristic as gh

deck = m.agent({{"select": None, "current": None, "logs": []}})
assert len(deck) == 60, f"deck length {{len(deck)}}"
print(f"デッキ {{len(deck)}}枚")

def load(p):
    lines = open(p).read().split("\\n")
    return [int(x) for x in lines if x.strip()]

worst = 0.0
total = errs = wins = 0
for path in sorted(glob.glob(os.path.join({pool!r}, "deck_*.csv"))):
    opp = load(path)
    w = 0
    for g in range(4):
        me = g % 2
        d0, d1 = (deck, opp) if me == 0 else (opp, deck)
        try:
            obs, sd = battle_start(list(d0), list(d1))
            assert obs is not None, f"battle_start {{sd.errorType}}"
            steps = 0
            while obs["current"]["result"] == -1 and steps < 3000:
                turn = obs["current"]["yourIndex"]
                t0 = time.perf_counter()
                act = m.agent(obs) if turn == me else gh.agent(obs)
                worst = max(worst, time.perf_counter() - t0)
                obs = battle_select(act); steps += 1
            if obs["current"]["result"] == me: w += 1; wins += 1
            battle_finish()
        except Exception:
            errs += 1; traceback.print_exc()
        total += 1
    print(f"  {{os.path.basename(path):28s}} {{w}}/4")
print(f"\\n合計 {{total}}試合 / 例外 {{errs}}件 / 勝率 {{wins/total:.0%}}")
print(f"最長思考時間 {{worst*1000:.0f}}ms")
if errs:
    sys.exit("検証失敗")
print("検証OK")
'''
        r = subprocess.run([sys.executable, "-c", script])
        if r.returncode != 0:
            sys.exit("検証失敗: 上のエラーを確認してください")


if __name__ == "__main__":
    build()
    if "--no-test" not in sys.argv:
        test()
