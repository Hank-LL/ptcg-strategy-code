"""提出用エントリポイント(イダイナキバ入りキュワワー・ミル版)。

tusk_heuristic.agent に委譲するだけ。何があっても合法手を返すため、
読み込み失敗時は generic_heuristic に、それも駄目なら先頭の選択肢に落とす。
"""

try:
    import tusk_heuristic as _ch
    _main_agent = _ch.agent
except Exception:                                    # pragma: no cover
    _main_agent = None

try:
    import generic_heuristic as _gh
    _fallback_agent = _gh.agent
except Exception:                                    # pragma: no cover
    _fallback_agent = None


def _last_resort(obs_dict):
    select = obs_dict.get("select")
    if select is None:
        with open("deck.csv") as f:
            lines = f.read().split("\n")
        return [int(lines[i]) for i in range(60)]
    n = len(select["option"])
    lo = select.get("minCount") or 1
    hi = select.get("maxCount") or 1
    k = min(max(lo, 1), hi, n)
    return list(range(k))


def agent(obs_dict: dict) -> list[int]:
    if _main_agent is not None:
        try:
            return _main_agent(obs_dict)
        except Exception:
            pass
    if _fallback_agent is not None:
        try:
            return _fallback_agent(obs_dict)
        except Exception:
            pass
    return _last_resort(obs_dict)
