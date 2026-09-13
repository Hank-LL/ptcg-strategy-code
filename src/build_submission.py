"""提出物 submission.tar.gz の組み立て + ローカル検証 (汎用ヒューリスティック版)

前提のファイル配置(~/ptcg/src で実行):
    main.py               (提出用: main_submission.py をリネームしたもの)
    generic_heuristic.py  (汎用ヒューリスティック)
    policy_net.py
    policy_weights.pt     (export_policy.py の出力)
    deck.csv
    cg/                   (公式ライブラリ)

使い方:
    python build_submission.py           # 組み立て + 検証対戦10試合
    python build_submission.py --no-test # 組み立てのみ
"""

import subprocess
import sys
import tarfile
import tempfile
import os

FILES = ["main.py", "generic_heuristic.py", "policy_net.py",
         "policy_weights.pt", "deck.csv"]
DIRS = ["cg"]
OUT = "submission.tar.gz"


def build():
    for f in FILES:
        if not os.path.exists(f):
            sys.exit(f"エラー: {f} がありません")
    for d in DIRS:
        if not os.path.isdir(d):
            sys.exit(f"エラー: {d}/ がありません")

    with tarfile.open(OUT, "w:gz") as tar:
        for f in FILES:
            tar.add(f, arcname=f)
        for d in DIRS:
            tar.add(d, arcname=d)

    with tarfile.open(OUT) as tar:
        names = tar.getnames()
    size_mb = os.path.getsize(OUT) / 1e6
    print(f"作成完了: {OUT} ({size_mb:.1f} MB)")
    print(f"内容: {[n for n in names if '/' not in n]} + cg/ 一式")


def test():
    """tar.gz を展開した状態を再現し、提出物の main.py で10試合回す。"""
    print("\n--- 提出物の検証(展開して10試合) ---")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(OUT) as tar:
            tar.extractall(tmp)
        script = f"""
import sys
sys.path.insert(0, {tmp!r})
import os
os.chdir({tmp!r})
import importlib.util
spec = importlib.util.spec_from_file_location("sub_main", os.path.join({tmp!r}, "main.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["sub_main"] = m
spec.loader.exec_module(m)
from cg.game import battle_start, battle_select, battle_finish

deck = m.agent({{"select": None, "current": None, "logs": []}})
assert len(deck) == 60, "deck length"
wins = 0
for g in range(10):
    obs, sd = battle_start(list(deck), list(deck))
    assert obs is not None, f"battle_start error {{sd.errorType}}"
    steps = 0
    while obs["current"]["result"] == -1 and steps < 2000:
        obs = battle_select(m.agent(obs))
        steps += 1
    battle_finish()
    print(f"game {{g+1}}: result={{obs['current']['result']}} steps={{steps}}")
print("検証OK: クラッシュなしで10試合完走")
"""
        r = subprocess.run([sys.executable, "-c", script])
        if r.returncode != 0:
            sys.exit("検証失敗: 上のエラーを確認してください")


if __name__ == "__main__":
    build()
    if "--no-test" not in sys.argv:
        test()