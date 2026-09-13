"""BC学習済みポリシーを使うエージェント。

全コンテキストを NN(policy_net.Policy) で選ぶ。例外時は generic_heuristic に委譲。
デッキは fuudin_deck.csv(教師のデッキ)。
"""
import os
import generic_heuristic as gh
from policy_net import load_policy, encode_observation

_WEIGHTS = os.environ.get(
    "BC_WEIGHTS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "policy_weights_bc_fuudin.pt"))
_DECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuudin_deck.csv")

_policy = None


def _get_policy():
    global _policy
    if _policy is None:
        _policy = load_policy(_WEIGHTS)
    return _policy


def read_deck():
    with open(_DECK) as f:
        lines = [x for x in f.read().split("\n") if x.strip()]
    return [int(x) for x in lines[:60]]


def agent(obs_dict):
    if obs_dict.get("select") is None:
        return read_deck()
    try:
        sel = obs_dict["select"]
        n = len(sel["option"])
        enc = encode_observation(obs_dict, obs_dict["current"]["yourIndex"])
        lo = sel.get("minCount") if sel.get("minCount") is not None else 1
        hi = sel.get("maxCount") if sel.get("maxCount") is not None else 1
        k = min(max(lo, 1), hi, n)
        idxs = [i for i in _get_policy().choose_k(enc, n) if 0 <= i < n][:k]
        if not idxs:
            return gh.agent(obs_dict)
        return idxs
    except Exception:
        return gh.agent(obs_dict)
