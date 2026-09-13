import tarfile, tempfile, subprocess, sys, os

OUT = "submission_D.tar.gz"
with tarfile.open(OUT, "w:gz") as tar:
    tar.add("main_generic.py", arcname="main.py")
    tar.add("generic_heuristic.py", arcname="generic_heuristic.py")
    tar.add("deck.csv", arcname="deck.csv")
    tar.add("cg", arcname="cg")

with tarfile.open(OUT) as tar:
    names = [n for n in tar.getnames() if "/" not in n]
print("内容:", names, "+ cg/")
print("サイズ:", round(os.path.getsize(OUT) / 1e6, 2), "MB")

# 検証: 展開して10試合
with tempfile.TemporaryDirectory() as tmp:
    with tarfile.open(OUT) as tar:
        tar.extractall(tmp)
    code = (
        "import sys, os\n"
        "sys.path.insert(0, %r); os.chdir(%r)\n"
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('m', os.path.join(%r, 'main.py'))\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['m'] = m\n"
        "spec.loader.exec_module(m)\n"
        "from cg.game import battle_start, battle_select, battle_finish\n"
        "deck = m.agent({'select': None, 'current': None, 'logs': []})\n"
        "assert len(deck) == 60, 'deck length'\n"
        "for g in range(10):\n"
        "    obs, sd = battle_start(list(deck), list(deck)); steps = 0\n"
        "    while obs['current']['result'] == -1 and steps < 2000:\n"
        "        obs = battle_select(m.agent(obs)); steps += 1\n"
        "    battle_finish()\n"
        "    print('game', g + 1, 'result', obs['current']['result'], 'steps', steps)\n"
        "print('検証OK: 10試合完走')\n"
    ) % (tmp, tmp, tmp)
    r = subprocess.run([sys.executable, "-c", code])
    sys.exit(r.returncode)
