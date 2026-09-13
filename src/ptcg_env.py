"""PTCG AI Battle Challenge 用 Gymnasium 環境ラッパー (汎用ヒューリスティック版)

前回からの変更:
- 相手デッキを毎エピソード、相手プール(opponent_pool_dir 内の deck_*.csv)から
  均等ランダムに選ぶよう変更。自分デッキは deck_csv 固定のまま。
  プール未指定・空なら従来動作(相手=自分と同じデッキ)にフォールバックする。
- 委譲先(非MAIN選択)・相手役を、デッキ専用の main.py から
  デッキ非依存の generic_heuristic.agent に差し替え。
- generic_heuristic は obs から毎回計算する純粋関数で対戦状態を
  グローバルに持たないため、委譲先・相手役で同一関数を共有できる
  (前回の二重ロードは不要)。
- 観測エンコード / step / 報酬設計は変更なし。

構成: SelectContext.MAIN のみRL、その他はヒューリスティック委譲。
"""

import glob
import os
import random
import sys

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from cg.game import battle_start, battle_select, battle_finish
from cg.api import SelectContext, OptionType

import generic_heuristic as gh

# ---------------------------------------------------------------- 定数
MAX_OPTIONS = 64
N_SLOTS = 9
MAX_HAND = 20
POKE_FEAT = 8
OPT_FEAT = 6
GLOBAL_DIM = 14
MAX_CARD_ID = 1400
MAX_STEPS = 2000
HP_SCALE = 340.0


def load_deck_csv(path: str = "deck.csv") -> list[int]:
    with open(path) as f:
        lines = f.read().split("\n")
    return [int(lines[i]) for i in range(60)]


# ---------------------------------------------------------------- 特徴量化
def _encode_pokemon_slot(p, ids, feat, slot, statuses=()):
    if p is None:
        return
    ids[slot] = p["id"]
    feat[slot, 0] = 1.0
    feat[slot, 1] = p["hp"] / HP_SCALE
    feat[slot, 2] = p["maxHp"] / HP_SCALE
    feat[slot, 3] = len(p["energies"]) / 5.0
    feat[slot, 4] = len(p["tools"]) / 2.0
    feat[slot, 5] = len(p["preEvolution"]) / 2.0
    feat[slot, 6] = 1.0 if p["appearThisTurn"] else 0.0
    feat[slot, 7] = 1.0 if any(statuses) else 0.0


def _encode_player(ps):
    ids = np.zeros(N_SLOTS, dtype=np.int64)
    feat = np.zeros((N_SLOTS, POKE_FEAT), dtype=np.float32)
    statuses = (ps["poisoned"], ps["burned"], ps["asleep"],
                ps["paralyzed"], ps["confused"])
    active = ps["active"][0] if ps["active"] else None
    _encode_pokemon_slot(active, ids, feat, 0, statuses)
    for i, p in enumerate(ps["bench"][:N_SLOTS - 1]):
        _encode_pokemon_slot(p, ids, feat, 1 + i)
    return ids, feat


def encode_observation(obs: dict, my_player: int) -> dict:
    state = obs["current"]
    select = obs["select"]
    me = state["players"][my_player]
    op = state["players"][1 - my_player]

    g = np.zeros(GLOBAL_DIM, dtype=np.float32)
    g[0] = state["turn"] / 30.0
    g[1] = 1.0 if state["firstPlayer"] == my_player else 0.0
    g[2] = len(me["prize"]) / 6.0
    g[3] = len(op["prize"]) / 6.0
    g[4] = me["deckCount"] / 60.0
    g[5] = op["deckCount"] / 60.0
    g[6] = me["handCount"] / 15.0
    g[7] = op["handCount"] / 15.0
    g[8] = 1.0 if state["supporterPlayed"] else 0.0
    g[9] = 1.0 if state["energyAttached"] else 0.0
    g[10] = 1.0 if state["retreated"] else 0.0
    g[11] = 1.0 if state["stadiumPlayed"] else 0.0
    g[12] = len(me["discard"]) / 40.0
    g[13] = state["stadium"][0]["id"] / MAX_CARD_ID if state["stadium"] else 0.0

    my_ids, my_feat = _encode_player(me)
    op_ids, op_feat = _encode_player(op)

    hand_ids = np.zeros(MAX_HAND, dtype=np.int64)
    if me["hand"] is not None:
        for i, c in enumerate(me["hand"][:MAX_HAND]):
            hand_ids[i] = c["id"]

    opt_type = np.zeros(MAX_OPTIONS, dtype=np.int64)
    opt_ids = np.zeros(MAX_OPTIONS, dtype=np.int64)
    opt_feat = np.zeros((MAX_OPTIONS, OPT_FEAT), dtype=np.float32)
    mask = np.zeros(MAX_OPTIONS, dtype=np.float32)

    options = select["option"][:MAX_OPTIONS]
    for i, o in enumerate(options):
        mask[i] = 1.0
        opt_type[i] = o["type"]
        opt_feat[i, 0] = 1.0
        cid = 0
        t = o["type"]
        if t == OptionType.PLAY and me["hand"] is not None:
            idx = o.get("index")
            if idx is not None and idx < len(me["hand"]):
                cid = me["hand"][idx]["id"]
        elif o.get("cardId"):
            cid = o["cardId"]
        elif t == OptionType.ATTACK:
            opt_feat[i, 1] = (o.get("attackId") or 0) / 2000.0
        opt_ids[i] = cid
        opt_feat[i, 2] = (o.get("index") or 0) / 20.0
        opt_feat[i, 3] = (o.get("inPlayIndex") or 0) / 8.0
        opt_feat[i, 4] = 1.0 if o.get("inPlayArea") is not None else 0.0
        opt_feat[i, 5] = (o.get("number") or 0) / 10.0

    return {
        "global": g,
        "my_ids": my_ids, "my_feat": my_feat,
        "op_ids": op_ids, "op_feat": op_feat,
        "hand_ids": hand_ids,
        "opt_type": opt_type, "opt_ids": opt_ids,
        "opt_feat": opt_feat, "mask": mask,
    }


# ---------------------------------------------------------------- 環境本体
class PTCGEnv(gym.Env):
    """MAIN のみ RL、その他は汎用ヒューリスティックに委譲する PTCG 環境。

    Args:
        deck_csv: 自分が使うデッキ(固定)
        prize_reward: サイド差分の中間報酬係数(0で無効)
        opponent_pool_dir: 相手デッキプールのディレクトリ。中の deck_*.csv を
            全て読み、reset ごとに均等ランダムで1つ選ぶ。None または読める
            デッキが無い場合は相手も deck_csv と同じデッキになる(従来動作)。
        external_opponents: True なら meta/opponents/ の外部エージェントも
            相手候補に加える。外部エージェントは自前のデッキとセットで使う。
        strong_ratio: 外部エージェントを相手にする確率(0〜1)。残りの確率で
            従来どおり「プールのデッキ + generic_heuristic」になる。
            外部エージェントが1体も読めなければ無視される。
    """

    metadata = {"render_modes": []}

    def __init__(self, deck_csv: str = "deck.csv",
                 prize_reward: float = 0.0, seed: int | None = None,
                 opponent_pool_dir: str | None = None,
                 external_opponents: bool = False,
                 strong_ratio: float = 0.3,
                 opp_prize_penalty: float = 0.0,
                 deckout_penalty: float = 0.0):
        super().__init__()
        self._rng = random.Random(seed)
        # 委譲先・相手役はどちらも汎用ヒューリスティック(純粋関数なので共有可)
        self.helper = gh.agent
        self.opponent = gh.agent
        self.deck = load_deck_csv(deck_csv)
        self.prize_reward = prize_reward
        # 負の報酬: 相手にサイドを取られたら罰(対称サイド差分)、
        # デッキアウトで負けたら追加罰。
        self.opp_prize_penalty = opp_prize_penalty
        self.deckout_penalty = deckout_penalty

        # 外部エージェント(強い相手)。読めなければ空リストのまま従来動作。
        self.external: list = []
        if external_opponents:
            try:
                import opponent_agents
                self.external = opponent_agents.load_opponents(gh.agent)
            except Exception:
                self.external = []
        self.strong_ratio = strong_ratio if self.external else 0.0
        self._last_opp_label = ""

        # 相手デッキプール(名前は集計・デバッグ用)
        self.opponent_pool: list[list[int]] = []
        self.opponent_pool_names: list[str] = []
        if opponent_pool_dir:
            pattern = os.path.join(os.path.expanduser(opponent_pool_dir), "deck_*.csv")
            for p in sorted(glob.glob(pattern)):
                try:
                    d = load_deck_csv(p)
                except (OSError, ValueError, IndexError):
                    continue
                if len(d) == 60:
                    self.opponent_pool.append(d)
                    self.opponent_pool_names.append(os.path.basename(p))
        if not self.opponent_pool:
            self.opponent_pool = [self.deck]
            self.opponent_pool_names = [os.path.basename(deck_csv)]
        self._last_opp_idx = -1

        self.observation_space = spaces.Dict({
            "global": spaces.Box(-1, 2, (GLOBAL_DIM,), np.float32),
            "my_ids": spaces.Box(0, MAX_CARD_ID, (N_SLOTS,), np.int64),
            "my_feat": spaces.Box(-1, 2, (N_SLOTS, POKE_FEAT), np.float32),
            "op_ids": spaces.Box(0, MAX_CARD_ID, (N_SLOTS,), np.int64),
            "op_feat": spaces.Box(-1, 2, (N_SLOTS, POKE_FEAT), np.float32),
            "hand_ids": spaces.Box(0, MAX_CARD_ID, (MAX_HAND,), np.int64),
            "opt_type": spaces.Box(0, 20, (MAX_OPTIONS,), np.int64),
            "opt_ids": spaces.Box(0, MAX_CARD_ID, (MAX_OPTIONS,), np.int64),
            "opt_feat": spaces.Box(-1, 2, (MAX_OPTIONS, OPT_FEAT), np.float32),
            "mask": spaces.Box(0, 1, (MAX_OPTIONS,), np.float32),
        })
        self.action_space = spaces.Discrete(MAX_OPTIONS)

        self._obs = None
        self._active = False
        self.my_player = 0
        self._steps = 0
        self._my_prize_before = 6

    def _close_battle(self):
        if self._active:
            battle_finish()
            self._active = False

    def _delegate(self) -> None:
        """自分の MAIN 以外・相手の全選択を委譲しつつ進める。"""
        while True:
            state = self._obs["current"]
            if state["result"] != -1 or self._steps >= MAX_STEPS:
                return
            turn_player = state["yourIndex"]
            select = self._obs["select"]
            if turn_player == self.my_player and select["context"] == SelectContext.MAIN:
                return
            agent_fn = self.helper if turn_player == self.my_player else self.opponent
            action = agent_fn(self._obs)
            self._obs = battle_select(action)
            self._steps += 1

    def _terminal_reward(self) -> float:
        result = self._obs["current"]["result"]
        if result == self.my_player:
            return 1.0
        if result == 2:
            return 0.0
        return -1.0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._close_battle()
        self.my_player = self._rng.randint(0, 1)
        self._steps = 0

        # 相手を選ぶ。確率 strong_ratio で外部エージェント(自前デッキ付き)、
        # それ以外は「プールのデッキ + generic_heuristic」。自席は常に self.deck。
        if self.external and self._rng.random() < self.strong_ratio:
            ext = self.external[self._rng.randrange(len(self.external))]
            ext.reset_state()
            self.opponent = ext
            opp_deck = ext.deck
            self._last_opp_idx = -1
            self._last_opp_label = f"ext:{ext.name}"
        else:
            self.opponent = gh.agent
            self._last_opp_idx = self._rng.randrange(len(self.opponent_pool))
            opp_deck = self.opponent_pool[self._last_opp_idx]
            self._last_opp_label = self.opponent_pool_names[self._last_opp_idx]

        if self.my_player == 0:
            deck0, deck1 = self.deck, opp_deck
        else:
            deck0, deck1 = opp_deck, self.deck

        obs, start_data = battle_start(list(deck0), list(deck1))
        if obs is None:
            raise RuntimeError(
                f"battle_start failed: player={start_data.errorPlayer} "
                f"type={start_data.errorType}")
        self._active = True
        self._obs = obs
        self._delegate()

        if self._obs["current"]["result"] != -1:
            return self.reset(seed=seed, options=options)

        self._my_prize_before = len(
            self._obs["current"]["players"][self.my_player]["prize"])
        self._op_prize_before = len(
            self._obs["current"]["players"][1 - self.my_player]["prize"])
        return encode_observation(self._obs, self.my_player), {}

    def step(self, action: int):
        select = self._obs["select"]
        n_opts = min(len(select["option"]), MAX_OPTIONS)
        if action >= n_opts:
            action = 0
        self._obs = battle_select([int(action)])
        self._steps += 1
        self._delegate()

        state = self._obs["current"]
        terminated = state["result"] != -1
        truncated = (not terminated) and self._steps >= MAX_STEPS

        reward = 0.0
        if self.prize_reward > 0:
            my_prize_now = len(state["players"][self.my_player]["prize"])
            reward += self.prize_reward * (self._my_prize_before - my_prize_now)
            self._my_prize_before = my_prize_now
        if self.opp_prize_penalty > 0:
            # 相手が取ったサイド(=相手のサイド山の減少)ぶんだけ負の報酬
            op_prize_now = len(state["players"][1 - self.my_player]["prize"])
            reward -= self.opp_prize_penalty * (self._op_prize_before - op_prize_now)
            self._op_prize_before = op_prize_now
        if terminated:
            reward += self._terminal_reward()
            # デッキアウト負け(自分の負け かつ 自分の山札が0)に追加罰
            if (self.deckout_penalty > 0
                    and state["result"] != self.my_player and state["result"] != 2
                    and state["players"][self.my_player]["deckCount"] == 0):
                reward -= self.deckout_penalty

        if terminated or truncated:
            enc = self._last_safe_encoding()
            self._close_battle()
            return enc, reward, terminated, truncated, {}

        return encode_observation(self._obs, self.my_player), reward, False, False, {}

    def _last_safe_encoding(self) -> dict:
        try:
            return encode_observation(self._obs, self.my_player)
        except (KeyError, TypeError, IndexError):
            return {k: np.zeros(sp.shape, dtype=sp.dtype)
                    for k, sp in self.observation_space.spaces.items()}

    def close(self):
        self._close_battle()


# ---------------------------------------------------------------- 動作確認
OPP_POOL_DIR = os.path.expanduser("~/ptcg/meta/top_decks")

if __name__ == "__main__":
    import collections
    import time

    n_episodes = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    mode = sys.argv[2] if len(sys.argv) > 2 else "random"  # random / heuristic / poolcheck
    pool_dir = sys.argv[3] if len(sys.argv) > 3 else OPP_POOL_DIR

    env = PTCGEnv(prize_reward=0.0, opponent_pool_dir=pool_dir,
                  external_opponents=True)
    print(f"相手プール({pool_dir}): {len(env.opponent_pool)}デッキ")
    for name in env.opponent_pool_names:
        print(f"  - {name}")
    print(f"外部エージェント: {len(env.external)}体 "
          f"(採用率{env.strong_ratio:.0%})")
    for e in env.external:
        print(f"  - {e.name}")

    # 検証A: 対戦は回さず reset だけ繰り返して相手の分布を見る
    if mode == "poolcheck":
        counts = collections.Counter()
        seats = collections.Counter()
        t0 = time.perf_counter()
        for _ in range(n_episodes):
            env.reset()
            counts[env._last_opp_label] += 1
            seats[env.my_player] += 1
        elapsed = time.perf_counter() - t0
        print(f"\n=== 相手の分布 ({n_episodes}回 reset, {elapsed:.0f}秒) ===")
        for name, c in sorted(counts.items()):
            print(f"  {name:28s} {c:4d}回 ({c/n_episodes:5.1%})")
        ext_total = sum(c for n, c in counts.items() if n.startswith("ext:"))
        print(f"出現種類: {len(counts)}  外部エージェント合計: "
              f"{ext_total}回 ({ext_total/n_episodes:.1%})")
        print(f"自分の座席: player0={seats[0]}回 / player1={seats[1]}回")
        env.close()
        sys.exit(0)

    wins = draws = 0
    opt_counts = []
    per_deck = collections.defaultdict(lambda: [0, 0])  # name -> [試合数, 勝数]
    t0 = time.perf_counter()
    for ep in range(n_episodes):
        obs, _ = env.reset()
        opp_name = env._last_opp_label
        done = False
        final_r = 0.0
        while not done:
            legal = np.flatnonzero(obs["mask"])
            opt_counts.append(len(legal))
            if mode == "heuristic":
                action = gh.agent(env._obs)[0]
                action = min(action, MAX_OPTIONS - 1)
            else:
                action = int(np.random.choice(legal))
            obs, r, term, trunc, _ = env.step(action)
            final_r = r
            done = term or trunc
        per_deck[opp_name][0] += 1
        if final_r > 0.5:
            wins += 1
            per_deck[opp_name][1] += 1
        elif abs(final_r) < 0.5:
            draws += 1
        if (ep + 1) % 25 == 0:
            print(f"{ep+1}試合: 勝率 {wins/(ep+1):.1%}")
    elapsed = time.perf_counter() - t0

    oc = np.array(opt_counts)
    print(f"\n=== {mode}方策 vs 汎用AI ({n_episodes}試合) ===")
    print(f"勝率: {wins/n_episodes:.1%}  引き分け: {draws}")
    print(f"速度: 秒間{n_episodes/elapsed:.1f}試合")
    print(f"MAIN選択肢数: 平均{oc.mean():.1f} / 中央値{np.median(oc):.0f} / "
          f"最大{oc.max()} / 1択の割合{(oc==1).mean():.1%}")
    print("相手別:")
    for name in sorted(per_deck):
        n, w = per_deck[name]
        rate = f"{w/n:.0%}" if n else "-"
        print(f"  {name:28s} {w:3d}/{n:3d}  {rate}")
    env.close()