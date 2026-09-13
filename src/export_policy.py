"""SB3(MaskablePPO)のチェックポイント → 提出用 policy_weights.pt に変換

使い方:
    python export_policy.py ../experiments/ppo_ptcg_final.zip
    python export_policy.py ../experiments/checkpoints/ppo_ptcg_XXXX_steps.zip

変換後、同ディレクトリの policy_net.py で推論できるか自己検証も行う。
"""

import sys

import numpy as np
import torch
from sb3_contrib import MaskablePPO

import policy_net as pn


def main():
    ckpt_path = sys.argv[1] if len(sys.argv) > 1 else "../experiments/ppo_ptcg_final.zip"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "policy_weights.pt"

    model = MaskablePPO.load(ckpt_path, device="cpu")
    p = model.policy
    torch.save({
        "features_extractor": p.features_extractor.state_dict(),
        "policy_net": p.mlp_extractor.policy_net.state_dict(),
        "action_net": p.action_net.state_dict(),
    }, out_path)
    print(f"書き出し完了: {out_path}")

    # ---- 自己検証: SB3本体と純torch版の出力一致を確認 ----
    policy = pn.load_policy(out_path)

    rng = np.random.default_rng(0)
    enc = {
        "global": rng.random(pn.GLOBAL_DIM).astype(np.float32),
        "my_ids": rng.integers(0, 700, pn.N_SLOTS),
        "my_feat": rng.random((pn.N_SLOTS, pn.POKE_FEAT)).astype(np.float32),
        "op_ids": rng.integers(0, 700, pn.N_SLOTS),
        "op_feat": rng.random((pn.N_SLOTS, pn.POKE_FEAT)).astype(np.float32),
        "hand_ids": rng.integers(0, 700, pn.MAX_HAND),
        "opt_type": rng.integers(0, 17, pn.MAX_OPTIONS),
        "opt_ids": rng.integers(0, 700, pn.MAX_OPTIONS),
        "opt_feat": rng.random((pn.MAX_OPTIONS, pn.OPT_FEAT)).astype(np.float32),
        "mask": (rng.random(pn.MAX_OPTIONS) > 0.5).astype(np.float32),
    }
    enc["mask"][0] = 1.0  # 少なくとも1つ合法

    a_pure = policy.choose(enc)
    obs_t = {k: torch.as_tensor(v).unsqueeze(0) for k, v in enc.items()}
    a_sb3, _ = model.predict(
        {k: v.numpy() for k, v in obs_t.items()},
        action_masks=enc["mask"].astype(bool), deterministic=True)
    a_sb3 = int(np.asarray(a_sb3).item())

    status = "一致 ✓" if a_pure == a_sb3 else "不一致 ✗ (構造の同期ズレを確認せよ)"
    print(f"自己検証: 純torch版 action={a_pure} / SB3版 action={a_sb3} → {status}")


if __name__ == "__main__":
    main()
