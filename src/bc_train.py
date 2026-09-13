"""BC(Behavior Cloning) 学習。

bc_data.npz の (obs, action) を教師に、policy_net.Policy を教師あり学習する。
ネットは train_ppo.py / policy_net.py と同一構造なので、出力重みは
  - 提出の NN 経路(main.py が load_policy) でそのまま使える
  - PPO 微調整の初期値にも使える
形で保存する(features_extractor / policy_net / action_net の3 state_dict)。

使い方(CUDA使うなら CUDA_VISIBLE_DEVICES=0 を付ける):
    python bc_train.py --epochs 40 --out policy_weights_bc_fuudin.pt
"""
import argparse
import numpy as np
import torch
import torch.nn as nn

from policy_net import Policy, MAX_OPTIONS

KEYS = ["global", "my_ids", "my_feat", "op_ids", "op_feat", "hand_ids",
        "opt_type", "opt_ids", "opt_feat", "mask"]
INT_KEYS = {"my_ids", "op_ids", "hand_ids", "opt_type", "opt_ids"}


def load_data(path="bc_data.npz"):
    z = np.load(path)
    n = len(z["label"])
    data = {}
    for k in KEYS:
        t = torch.as_tensor(z[k])
        data[k] = t.long() if k in INT_KEYS else t.float()
    label = torch.as_tensor(z["label"]).long()
    return data, label, n


def batch_slice(data, idx):
    return {k: v[idx] for k, v in data.items()}


def forward_logits(policy, batch):
    feats = policy.features_extractor(batch)
    logits = policy.action_net(policy.policy_net(feats))
    logits = logits.masked_fill(batch["mask"] == 0, -1e9)
    return logits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--wd", type=float, default=0.0)
    ap.add_argument("--balance", action="store_true",
                    help="index頻度の逆数でCEを重み付け(index0偏重を抑える)")
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--out", default="policy_weights_bc_fuudin.pt")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={dev}")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    data, label, n = load_data()
    print(f"サンプル {n} 件")
    # train/val 分割
    perm = np.random.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx = torch.as_tensor(perm[:n_val])
    tr_idx = torch.as_tensor(perm[n_val:])

    data = {k: v.to(dev) for k, v in data.items()}
    label = label.to(dev)

    # ベースライン: 常に index0(合法な範囲で)
    base = (label[val_idx] == 0).float().mean().item()
    print(f"ベースライン(常にindex0)の val 正答率: {base*100:.1f}%")

    policy = Policy().to(dev)
    opt = torch.optim.Adam(policy.parameters(), lr=args.lr, weight_decay=args.wd)
    weight = None
    if args.balance:
        cnt = torch.bincount(label[tr_idx], minlength=MAX_OPTIONS).float()
        weight = (1.0 / cnt.clamp(min=1).sqrt())
        weight[cnt == 0] = 0.0
        weight = (weight / weight.sum() * (cnt > 0).sum()).to(dev)
    ce = nn.CrossEntropyLoss(weight=weight)

    best = 0.0
    for ep in range(1, args.epochs + 1):
        policy.train()
        order = tr_idx[torch.randperm(len(tr_idx))]
        tot = 0.0
        for i in range(0, len(order), args.batch):
            bi = order[i:i + args.batch]
            batch = batch_slice(data, bi)
            logits = forward_logits(policy, batch)
            loss = ce(logits, label[bi])
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(bi)
        # 評価
        policy.eval()
        with torch.no_grad():
            vb = batch_slice(data, val_idx)
            vl = forward_logits(policy, vb)
            vacc = (vl.argmax(1) == label[val_idx]).float().mean().item()
            tb = batch_slice(data, tr_idx[:len(val_idx) * 4])
            tl = forward_logits(policy, tb)
            tacc = (tl.argmax(1) == label[tr_idx[:len(val_idx) * 4]]).float().mean().item()
        if vacc > best:
            best = vacc
            torch.save({
                "features_extractor": policy.features_extractor.state_dict(),
                "policy_net": policy.policy_net.state_dict(),
                "action_net": policy.action_net.state_dict(),
            }, args.out)
        if ep % 2 == 0 or ep == 1:
            print(f"ep{ep:3d}  loss={tot/len(order):.3f}  "
                  f"train_acc={tacc*100:.1f}%  val_acc={vacc*100:.1f}%")

    # 最終エポックの重みも別名で保存(過学習だが「よく学習した」版の実戦比較用)
    final_out = args.out.replace(".pt", "_final.pt")
    torch.save({
        "features_extractor": policy.features_extractor.state_dict(),
        "policy_net": policy.policy_net.state_dict(),
        "action_net": policy.action_net.state_dict(),
    }, final_out)

    print(f"\n最良 val 正答率: {best*100:.1f}%  (ベースライン {base*100:.1f}%)")
    print(f"保存: {args.out} (best-val) / {final_out} (最終ep)")


if __name__ == "__main__":
    main()
