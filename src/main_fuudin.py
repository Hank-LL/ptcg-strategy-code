"""提出用: BC→PPO 学習済みフーディン(Alakazam)エージェント。

ガブリアスRL提出(実績あり)と同じ堅牢パターンに準拠:
- policy_net の import と重みロードは import 時に try/except で囲む
  (torch が無い/読めない環境でも起動は継続し、generic に委譲)
- 重みパスは相対 → Kaggleパス(/kaggle_simulations/agent/) の順でフォールバック
  (__file__ には依存しない。Kaggleで未定義でもクラッシュしない)
- NN は全コンテキストを choose_k で選択(ローカル評価 eval_bc と同一挙動)
- どんな例外でも必ず合法手を返す多段フォールバック

同梱: main.py, policy_net.py, policy_weights.pt, generic_heuristic.py, deck.csv, cg/
"""
import os

import generic_heuristic as gh

# ---- NN方策のロード(import時。失敗しても起動は継続) ----
_policy = None
_encode = None
try:
    from policy_net import load_policy, encode_observation
    _encode = encode_observation
    _w = "policy_weights.pt"
    if not os.path.exists(_w):
        _w = "/kaggle_simulations/agent/policy_weights.pt"
    _policy = load_policy(_w)
except Exception as e:
    print(f"[warn] policy load failed, heuristic only: {e}")


def _nn_action(obs_dict: dict) -> list[int]:
    sel = obs_dict["select"]
    n = len(sel["option"])
    enc = _encode(obs_dict, obs_dict["current"]["yourIndex"])
    lo = sel["minCount"] if sel.get("minCount") is not None else 1
    hi = sel["maxCount"] if sel.get("maxCount") is not None else 1
    k = min(max(lo, 1), hi, n)
    idxs = [i for i in _policy.choose_k(enc, n) if 0 <= i < n][:k]
    if not idxs:
        raise ValueError("no legal nn action")
    return idxs


def agent(obs_dict: dict) -> list[int]:
    # 初回: デッキ提出(gh.read_deck_csv は Kaggleパス対応)
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()

    # 全コンテキストを NN で選択
    try:
        if _policy is not None:
            return _nn_action(obs_dict)
    except Exception as e:
        print(f"[warn] nn fallback: {e}")

    # フォールバック1: 汎用ヒューリスティック
    try:
        return gh.agent(obs_dict)
    except Exception as e:
        print(f"[warn] heuristic fallback: {e}")

    # 最終フォールバック: 最小限の合法手(絶対にクラッシュしない)
    select = obs_dict["select"]
    n = max(select["minCount"], 1) if select.get("minCount") is not None else 1
    n = min(n, len(select["option"]))
    return list(range(n))
