"""提出用: 汎用ヒューリスティックのみ(NN不使用)"""
import generic_heuristic as gh

def agent(obs_dict):
    if obs_dict.get("select") is None:
        return gh.read_deck_csv()
    return gh.agent(obs_dict)
