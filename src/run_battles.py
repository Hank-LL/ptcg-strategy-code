"""サンプルエージェント同士のローカル対戦 + 速度計測"""
import importlib.util
import time
import sys

from cg.game import battle_start, battle_select, battle_finish


def load_agent(main_py_path: str, name: str):
    """main.pyからagent関数とデッキを読み込む"""
    spec = importlib.util.spec_from_file_location(name, main_py_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod.agent


def get_deck(agent_fn) -> list[int]:
    """selectがNoneのダミーobsを渡してデッキを取得"""
    dummy = {
        "current": None,
        "select": None,
        "logs": [],
    }
    return agent_fn(dummy)


def run_one_battle(agent0, agent1, deck0, deck1, max_steps=2000) -> tuple[int, int]:
    """1試合実行。(result, steps)を返す"""
    obs, start_data = battle_start(deck0, deck1)
    if obs is None:
        raise RuntimeError(f"battle_start failed: player={start_data.errorPlayer} type={start_data.errorType}")
    agents = [agent0, agent1]
    steps = 0
    try:
        while obs["current"]["result"] == -1 and steps < max_steps:
            player = obs["current"]["yourIndex"]
            action = agents[player](obs)
            obs = battle_select(action)
            steps += 1
        return obs["current"]["result"], steps
    finally:
        battle_finish()


if __name__ == "__main__":
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    agent0 = load_agent("main.py", "agent0")
    agent1 = load_agent("main.py", "agent1")  # 同じサンプル同士
    deck0 = get_deck(agent0)
    deck1 = get_deck(agent1)

    wins = [0, 0, 0]  # p0勝ち, p1勝ち, 引き分け
    total_steps = 0
    t0 = time.perf_counter()
    for i in range(n_games):
        result, steps = run_one_battle(agent0, agent1, deck0, deck1)
        wins[result] += 1
        total_steps += steps
        if (i + 1) % 10 == 0:
            print(f"{i+1}試合完了...")
    elapsed = time.perf_counter() - t0

    print(f"\n=== 結果 ===")
    print(f"{n_games}試合 / {elapsed:.1f}秒 = 秒間{n_games/elapsed:.2f}試合")
    print(f"P0勝ち: {wins[0]}  P1勝ち: {wins[1]}  引き分け: {wins[2]}")
    print(f"平均ステップ数(意思決定回数): {total_steps/n_games:.0f}")