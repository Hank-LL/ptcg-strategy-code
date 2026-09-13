"""提出用エージェント: RL方策(MAIN) + 汎用ヒューリスティック(その他)

構成:
- MAIN コンテキスト: 学習済みNN(policy_weights.pt)で選択
- それ以外のコンテキスト / NN失敗時: generic_heuristic に委譲
- どんな例外でも必ず合法手を返す多段フォールバック

必要ファイル(同梱): main.py, generic_heuristic.py, policy_net.py,
                     policy_weights.pt, deck.csv, cg/
"""

import os

from cg.api import SelectContext

# 汎用ヒューリスティック(デッキ非依存、委譲先)
import generic_heuristic as gh

# ---- NN方策のロード(失敗しても起動は継続) ----
_policy = None
try:
    from policy_net import load_policy, encode_observation
    _w = "policy_weights.pt"
    if not os.path.exists(_w):
        _w = "/kaggle_simulations/agent/policy_weights.pt"
    _policy = load_policy(_w)
except Exception as e:
    print(f"[warn] policy load failed, heuristic only: {e}")


def _nn_action(obs_dict: dict) -> list[int]:
    my_player = obs_dict["current"]["yourIndex"]
    enc = encode_observation(obs_dict, my_player)
    idx = _policy.choose(enc)
    n_opts = len(obs_dict["select"]["option"])
    if idx >= n_opts:
        raise IndexError("policy chose out-of-range option")
    return [idx]


def agent(obs_dict: dict) -> list[int]:
    # 初回: デッキ提出
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()

    # MAIN は NN、その他は汎用ヒューリスティック
    try:
        if _policy is not None and \
                obs_dict["select"]["context"] == SelectContext.MAIN:
            return _nn_action(obs_dict)
    except Exception as e:
        print(f"[warn] nn fallback: {e}")

    try:
        return gh.agent(obs_dict)
    except Exception as e:
        print(f"[warn] heuristic fallback: {e}")

    # 最終フォールバック: 最小限の合法手(絶対にクラッシュしない)
    select = obs_dict["select"]
    n = max(select["minCount"], 1) if select["minCount"] is not None else 1
    n = min(n, len(select["option"]))
    return list(range(n))