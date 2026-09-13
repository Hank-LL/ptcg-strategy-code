"""提出物 submission_fuudin.tar.gz(BC→PPO学習済みフーディン)の組み立て + 検証。

同梱物:
    main.py            = main_fuudin.py (NN推論 + generic フォールバック)
    policy_net.py      (SB3非依存の推論ネット)
    policy_weights.pt  = policy_weights_ppo_fuudin.pt (上位デッキで130M学習した版)
    generic_heuristic.py (フォールバック)
    deck.csv           = ../meta/top_decks/deck_fuudin_top.csv (上位勢の主力構築)
    cg/                (公式ライブラリ)

※ meta/opponents/ の外部エージェント(他者の公開物)は同梱しない。
"""
import glob
import os
import subprocess
import sys
import tarfile
import tempfile

OUT = "submission_fuudin.tar.gz"
POOL = "../meta/top_decks"

FILES = [
    ("main.py", "main_fuudin.py"),
    ("policy_net.py", "policy_net.py"),
    ("policy_weights.pt", "policy_weights_ppo_fuudin.pt"),
    ("generic_heuristic.py", "generic_heuristic.py"),
    ("deck.csv", "../meta/top_decks/deck_fuudin_top.csv"),
]
DIRS = ["cg"]


def build():
    for arc, src in FILES:
        if not os.path.exists(src):
            sys.exit(f"エラー: {src} がありません")
    for d in DIRS:
        if not os.path.isdir(d):
            sys.exit(f"エラー: {d}/ がありません")

    with open("../meta/top_decks/deck_fuudin_top.csv") as f:
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
