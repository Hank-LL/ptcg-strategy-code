"""PTCG MaskablePPO 学習スクリプト

構成:
- PTCGEnv (ptcg_env.py) を SubprocVecEnv で並列実行
  ※ cgライブラリは1プロセス1対戦のため、並列化はプロセス分離が必須
- sb3-contrib の MaskablePPO で合法手マスク付き学習
- カスタム特徴抽出器: カードIDを共有Embeddingに通してから結合

実行:
    pip install sb3-contrib
    python train_ppo.py                # 学習(デフォルト200万ステップ)
    python train_ppo.py --eval PATH    # 保存済みモデルの評価のみ
"""

import argparse
import os
import time

import numpy as np
import torch
import torch.nn as nn
import gymnasium as gym

from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.callbacks import CheckpointCallback
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from sb3_contrib.common.maskable.evaluation import evaluate_policy

from ptcg_env import PTCGEnv, MAX_OPTIONS, MAX_CARD_ID
from stable_baselines3.common.monitor import Monitor


# ---------------------------------------------------------------- 環境生成
class MaskRecorder(gym.Wrapper):
    """直近の合法手マスクを保持し、ActionMasker から参照できるようにする。"""

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        self.last_mask = obs["mask"].astype(bool)
        return obs, info

    def step(self, action):
        obs, r, term, trunc, info = self.env.step(action)
        self.last_mask = obs["mask"].astype(bool)
        # 終局時のゼロマスクは全Trueに置換(PPO側の要件: 空マスク禁止)
        if not self.last_mask.any():
            self.last_mask = np.ones(MAX_OPTIONS, dtype=bool)
        return obs, r, term, trunc, info


def mask_fn(env) -> np.ndarray:
    return env.last_mask


# 相手デッキプール。自分は deck.csv 固定、相手は毎エピソードここから均等ランダム。
OPP_POOL = os.path.expanduser("~/ptcg/meta/top_decks")

# 外部エージェント(meta/opponents/)を相手に混ぜる割合。
# 相手役を generic_heuristic だけにすると勝率が約50pp過大に出ることが実測されたため
# (2026-07-22)、既定で本物のエージェントを混ぜる。--strong-ratio 0 で従来動作。
STRONG_RATIO = 0.3


def make_env(seed: int, strong_ratio: float = STRONG_RATIO,
             deck_csv: str = "deck.csv",
             opp_prize_penalty: float = 0.1, deckout_penalty: float = 0.3):
    # SubprocVecEnv はこのクロージャを pickle して子プロセスへ渡す。設定は
    # モジュールグローバルでなく引数で捕捉しないと子プロセスに伝わらない。
    def _init():
        env = PTCGEnv(deck_csv=deck_csv, prize_reward=0.1, seed=seed,
                      opponent_pool_dir=OPP_POOL,
                      external_opponents=strong_ratio > 0,
                      strong_ratio=strong_ratio,
                      opp_prize_penalty=opp_prize_penalty,
                      deckout_penalty=deckout_penalty)
        env = MaskRecorder(env)
        env = ActionMasker(env, mask_fn)
        env = Monitor(env)   # gym.wrappers.Monitor で学習曲線の可視化に必要な episode_reward, episode_length を記録
        return env
    return _init


# ---------------------------------------------------------------- 特徴抽出器
class PTCGExtractor(BaseFeaturesExtractor):
    """カードID埋め込み + 選択肢ごとのエンコード → 固定長特徴ベクトル。"""

    def __init__(self, observation_space: gym.spaces.Dict,
                 card_emb_dim: int = 32, type_emb_dim: int = 8,
                 opt_hidden: int = 32, features_dim: int = 512):
        super().__init__(observation_space, features_dim)
        self.card_emb = nn.Embedding(MAX_CARD_ID + 1, card_emb_dim, padding_idx=0)
        self.type_emb = nn.Embedding(24, type_emb_dim)

        poke_feat = observation_space["my_feat"].shape[1]
        opt_feat = observation_space["opt_feat"].shape[1]
        n_slots = observation_space["my_ids"].shape[0]
        global_dim = observation_space["global"].shape[0]

        self.opt_mlp = nn.Sequential(
            nn.Linear(card_emb_dim + type_emb_dim + opt_feat, opt_hidden),
            nn.ReLU(),
        )
        concat_dim = (
            global_dim
            + 2 * n_slots * (card_emb_dim + poke_feat)  # 自分/相手の場
            + card_emb_dim                              # 手札(sumプール)
            + MAX_OPTIONS * opt_hidden                  # 選択肢(順序保持)
        )
        self.head = nn.Sequential(
            nn.Linear(concat_dim, features_dim),
            nn.ReLU(),
            nn.Linear(features_dim, features_dim),
            nn.ReLU(),
        )

    def forward(self, obs: dict) -> torch.Tensor:
        b = obs["global"].shape[0]

        def field(ids_key, feat_key):
            e = self.card_emb(obs[ids_key].long())            # (B, S, E)
            return torch.cat([e, obs[feat_key]], dim=-1).flatten(1)

        my = field("my_ids", "my_feat")
        op = field("op_ids", "op_feat")
        hand = self.card_emb(obs["hand_ids"].long()).sum(dim=1)  # (B, E)

        opt_e = torch.cat([
            self.card_emb(obs["opt_ids"].long()),
            self.type_emb(obs["opt_type"].long().clamp(0, 23)),
            obs["opt_feat"],
        ], dim=-1)                                            # (B, 64, *)
        opt = self.opt_mlp(opt_e) * obs["mask"].unsqueeze(-1)  # 無効枠をゼロ化
        opt = opt.flatten(1)

        x = torch.cat([obs["global"], my, op, hand, opt], dim=-1)
        return self.head(x)


# ---------------------------------------------------------------- 評価
def evaluate(model, n_episodes: int = 200, strong_ratio: float = STRONG_RATIO,
             deck_csv: str = "deck.csv",
             opp_prize_penalty: float = 0.1, deckout_penalty: float = 0.3):
    env = DummyVecEnv([make_env(seed=9999, strong_ratio=strong_ratio,
                                deck_csv=deck_csv,
                                opp_prize_penalty=opp_prize_penalty,
                                deckout_penalty=deckout_penalty)])
    t0 = time.perf_counter()
    rewards, _ = evaluate_policy(
        model, env, n_eval_episodes=n_episodes,
        deterministic=True, return_episode_rewards=True)
    elapsed = time.perf_counter() - t0
    rewards = np.array(rewards)
    # prize_reward 込みなので「最終的に正なら勝ち」とみなす簡易判定
    win_rate = (rewards > 0.5).mean()
    print(f"[評価] {n_episodes}試合  勝率 {win_rate:.1%}  "
          f"平均報酬 {rewards.mean():+.2f}  ({elapsed:.0f}秒)")
    env.close()
    return win_rate


# ---------------------------------------------------------------- メイン
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=2_000_000)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--eval", type=str, default=None,
                        help="評価のみ: モデルパスを指定")
    parser.add_argument("--tag", type=str, default=None,
                        help="実行の識別名(既定: 日時)。保存先の名前に使う")
    parser.add_argument("--strong-ratio", type=float, default=STRONG_RATIO,
                        help="外部エージェント(本物のAI)を相手にする割合。0で従来動作")
    parser.add_argument("--deck", type=str, default="deck.csv",
                        help="自分のデッキ(既定 deck.csv)。フーディンは fuudin_deck.csv")
    parser.add_argument("--opp-prize-penalty", type=float, default=0.1,
                        help="相手にサイドを取られたときの負の報酬係数")
    parser.add_argument("--deckout-penalty", type=float, default=0.3,
                        help="デッキアウトで負けたときの追加の負の報酬")
    parser.add_argument("--init-bc", type=str, default=None,
                        help="BC重み(policy_weights_bc_*.pt)でポリシーを初期化")
    parser.add_argument("--resume", type=str, default=None,
                        help="既存モデル(zip)を読み込んで学習を継続する")
    parser.add_argument("--save-freq", type=int, default=100_000,
                        help="チェックポイント保存間隔(総ステップ数。既定10万)")
    parser.add_argument("--lr", type=float, default=None,
                        help="学習率を上書き(継続学習で暴れる時は下げる。例 2e-5)")
    args = parser.parse_args()

    rcfg = dict(deck_csv=args.deck,
                opp_prize_penalty=args.opp_prize_penalty,
                deckout_penalty=args.deckout_penalty)

    if args.eval:
        model = MaskablePPO.load(args.eval)
        evaluate(model, n_episodes=500, strong_ratio=args.strong_ratio, **rcfg)
        return

    # 実行ごとに一意なタグ。過去の学習成果物を上書きしないために使う。
    run_tag = args.tag or time.strftime("%Y%m%d_%H%M%S")

    vec_env = SubprocVecEnv([make_env(seed=i, strong_ratio=args.strong_ratio, **rcfg)
                             for i in range(args.n_envs)])

    if args.resume:
        # 既存モデルを読み込んで学習継続(10Mの成果を捨てずに続きを回す)。
        model = MaskablePPO.load(args.resume, device="cuda")
        model.set_env(vec_env)
        print(f"[resume] 継続学習: {args.resume}")
    else:
        model = MaskablePPO(
            "MultiInputPolicy",
            vec_env,
            policy_kwargs=dict(
                features_extractor_class=PTCGExtractor,
                net_arch=dict(pi=[256], vf=[256]),
            ),
            n_steps=256,          # 1環境あたり → 8env で 2048 サンプル/更新
            batch_size=512,
            learning_rate=5e-5,
            target_kl=0.03,
            gamma=0.99,
            gae_lambda=0.95,
            ent_coef=0.01,        # 探索促進。学習が単調化したら上げる
            clip_range=0.2,
            verbose=1,
            device="cuda",
            tensorboard_log="../experiments/tb",
        )

        # BC で学習済みの重みでポリシーを初期化(BC→PPO)。value head は BC に無いので
        # 未初期化のまま(PPOが学習する)。構造は policy_net.Policy と同一なので流し込める。
        if args.init_bc:
            bc = torch.load(args.init_bc, map_location=model.device)
            model.policy.features_extractor.load_state_dict(bc["features_extractor"])
            model.policy.mlp_extractor.policy_net.load_state_dict(bc["policy_net"])
            model.policy.action_net.load_state_dict(bc["action_net"])
            print(f"[init-bc] BC重みで初期化: {args.init_bc}")

    # 学習率の上書き(継続学習で方策が暴れる時に下げる)。SB3は lr_schedule で
    # 学習率を決めるので、両方を差し替える。
    if args.lr is not None:
        model.learning_rate = args.lr
        model.lr_schedule = lambda _: args.lr
        print(f"[lr] 学習率を {args.lr} に上書き")

    # 実行ごとに別ディレクトリ。以前は共通ディレクトリ + 同一prefixだったため、
    # 短い学習を回すと過去の実行の同ステップ数のckptを上書きしていた。
    ckpt_dir = f"../experiments/checkpoints/{run_tag}"
    checkpoint = CheckpointCallback(
        save_freq=max(args.save_freq // args.n_envs, 1),
        save_path=ckpt_dir,
        name_prefix="ppo_ptcg",
    )
    print(f"[run_tag] {run_tag}  (ckpt: {ckpt_dir})")

    print("学習開始前のベースライン評価(未学習モデル ≒ ランダム):")
    evaluate(model, n_episodes=100, strong_ratio=args.strong_ratio, **rcfg)

    model.learn(total_timesteps=args.steps, callback=checkpoint,
                progress_bar=True,
                reset_num_timesteps=not args.resume)
    # タグ付きが正本。ppo_ptcg_final.zip は「直近の学習」を指す別名として残す。
    tagged = f"../experiments/ppo_ptcg_{run_tag}"
    model.save(tagged)
    model.save("../experiments/ppo_ptcg_final")
    print(f"保存: {tagged}.zip (正本) / ppo_ptcg_final.zip (直近の別名)")

    print("学習後の評価:")
    evaluate(model, n_episodes=500, strong_ratio=args.strong_ratio, **rcfg)
    vec_env.close()


if __name__ == "__main__":
    main()