"""学習用の「相手エージェント」レジストリ。

ptcg_env.py の相手役は従来 generic_heuristic 1種類だけだった。実測では、
同じデッキでも操縦者を本物のエージェントに変えると勝率が 87% → 38% に落ちる
(2026-07-22, フーディン100試合)。つまりデッキを多様化しても相手の打ち回しが
弱いままでは、学習も評価も歪む。

このモジュールは meta/opponents/<name>/ に置かれた外部エージェント
(main.py + deck.csv) を読み込み、(名前, デッキ, agent関数) の組にして返す。

**このモジュールは学習・評価専用で、提出物には含めない。**
build_submission.py の FILES に入れないこと(外部エージェントは他者の公開物)。

外部エージェントの注意点:
- main.py は import 時に cwd の deck.csv を読む実装が多い → cwd を切り替えて読む
- モジュールグローバルに状態を持つ実装がある → エピソード境界でリセットする
- 例外を出す可能性がある → 呼び出し側で generic_heuristic にフォールバックする
"""

import importlib.util
import os
import sys

OPPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "meta", "opponents")

# エピソード境界で初期値に戻すグローバル(外部エージェントがターン内状態を持つため)
_RESET_GLOBALS = {
    "pre_turn": 0,
    "ability_used_dudunsparce": False,
    "ability_used_fezandipiti": False,
}


def _load_module(name, workdir):
    """workdir/main.py を、cwd を workdir にした状態で読み込む。"""
    path = os.path.join(workdir, "main.py")
    if not os.path.exists(path):
        return None
    prev_cwd = os.getcwd()
    os.chdir(workdir)
    sys.path.insert(0, workdir)
    try:
        spec = importlib.util.spec_from_file_location(f"opp_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"opp_{name}"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None
    finally:
        os.chdir(prev_cwd)
        if workdir in sys.path:
            sys.path.remove(workdir)


def _load_deck(workdir):
    p = os.path.join(workdir, "deck.csv")
    with open(p) as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


class ExternalOpponent:
    """外部エージェントを、例外に強い呼び出し可能オブジェクトとして包む。"""

    def __init__(self, name, deck, module, fallback):
        self.name = name
        self.deck = deck
        self._mod = module
        self._fallback = fallback

    def reset_state(self):
        """エピソード開始時に、外部エージェントのターン内グローバルを初期化する。"""
        for k, v in _RESET_GLOBALS.items():
            if hasattr(self._mod, k):
                setattr(self._mod, k, v)

    def __call__(self, obs):
        try:
            action = self._mod.agent(obs)
        except Exception:
            return self._fallback(obs)
        # 合法性の最低限の検証(外部コードを信用しきらない)
        try:
            n = len(obs["select"]["option"])
            if (not action or len(set(action)) != len(action)
                    or any((not isinstance(a, int)) or a < 0 or a >= n for a in action)):
                return self._fallback(obs)
        except (KeyError, TypeError):
            return self._fallback(obs)
        return action


def load_opponents(fallback, opponent_dir=None):
    """meta/opponents/ 以下の全エージェントを読み込む。

    Args:
        fallback: 外部エージェントが失敗したときに使う agent 関数
                  (通常 generic_heuristic.agent)
    Returns:
        list[ExternalOpponent] (読めなかったものは黙って除外)
    """
    base = os.path.abspath(opponent_dir or OPPONENT_DIR)
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        wd = os.path.join(base, name)
        if not os.path.isdir(wd):
            continue
        try:
            deck = _load_deck(wd)
        except (OSError, ValueError, IndexError):
            continue
        if len(deck) != 60:
            continue
        mod = _load_module(name, wd)
        if mod is None or not hasattr(mod, "agent"):
            continue
        out.append(ExternalOpponent(name, deck, mod, fallback))
    return out


if __name__ == "__main__":
    import generic_heuristic as gh
    opps = load_opponents(gh.agent)
    print(f"読み込めた外部エージェント: {len(opps)}")
    for o in opps:
        print(f"  {o.name}: デッキ{len(o.deck)}枚")
