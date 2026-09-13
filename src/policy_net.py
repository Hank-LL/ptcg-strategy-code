"""提出用 推論モジュール (SB3非依存、torch+numpyのみ)

学習時の PTCGExtractor / encode_observation と完全に同一の構造を再現する。
train_ppo.py / ptcg_env.py 側を変更した場合は、このファイルも同期すること。
"""

import numpy as np
import torch
import torch.nn as nn

# ---- ptcg_env.py と同一の定数(同期必須) ----
MAX_OPTIONS = 64
N_SLOTS = 9
MAX_HAND = 20
POKE_FEAT = 8
OPT_FEAT = 6
GLOBAL_DIM = 14
MAX_CARD_ID = 1400
HP_SCALE = 340.0

# OptionType の整数値 (cg.api と同期)
OPT_PLAY = 7
OPT_ATTACK = 13


# ---------------------------------------------------------------- 観測エンコード
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
        if t == OPT_PLAY and me["hand"] is not None:
            idx = o.get("index")
            if idx is not None and idx < len(me["hand"]):
                cid = me["hand"][idx]["id"]
        elif o.get("cardId"):
            cid = o["cardId"]
        elif t == OPT_ATTACK:
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


# ---------------------------------------------------------------- ネットワーク
class PTCGExtractor(nn.Module):
    """train_ppo.py の PTCGExtractor と同一構造(state_dict互換)。"""

    def __init__(self, card_emb_dim=32, type_emb_dim=8,
                 opt_hidden=32, features_dim=512):
        super().__init__()
        self.card_emb = nn.Embedding(MAX_CARD_ID + 1, card_emb_dim, padding_idx=0)
        self.type_emb = nn.Embedding(24, type_emb_dim)
        self.opt_mlp = nn.Sequential(
            nn.Linear(card_emb_dim + type_emb_dim + OPT_FEAT, opt_hidden),
            nn.ReLU(),
        )
        concat_dim = (
            GLOBAL_DIM
            + 2 * N_SLOTS * (card_emb_dim + POKE_FEAT)
            + card_emb_dim
            + MAX_OPTIONS * opt_hidden
        )
        self.head = nn.Sequential(
            nn.Linear(concat_dim, features_dim), nn.ReLU(),
            nn.Linear(features_dim, features_dim), nn.ReLU(),
        )

    def forward(self, obs: dict) -> torch.Tensor:
        def field(ids_key, feat_key):
            e = self.card_emb(obs[ids_key].long())
            return torch.cat([e, obs[feat_key]], dim=-1).flatten(1)

        my = field("my_ids", "my_feat")
        op = field("op_ids", "op_feat")
        hand = self.card_emb(obs["hand_ids"].long()).sum(dim=1)
        opt_e = torch.cat([
            self.card_emb(obs["opt_ids"].long()),
            self.type_emb(obs["opt_type"].long().clamp(0, 23)),
            obs["opt_feat"],
        ], dim=-1)
        opt = self.opt_mlp(opt_e) * obs["mask"].unsqueeze(-1)
        x = torch.cat([obs["global"], my, op, hand, opt.flatten(1)], dim=-1)
        return self.head(x)


class Policy(nn.Module):
    """特徴抽出 + SB3のpiヘッド(net_arch pi=[256], 活性化Tanh) + action_net。"""

    def __init__(self, features_dim=512, pi_dim=256):
        super().__init__()
        self.features_extractor = PTCGExtractor(features_dim=features_dim)
        self.policy_net = nn.Sequential(nn.Linear(features_dim, pi_dim), nn.Tanh())
        self.action_net = nn.Linear(pi_dim, MAX_OPTIONS)

    @torch.no_grad()
    def _logits(self, enc: dict):
        tensors = {k: torch.as_tensor(v).unsqueeze(0) for k, v in enc.items()}
        feats = self.features_extractor(tensors)
        logits = self.action_net(self.policy_net(feats))[0]
        mask = tensors["mask"][0] > 0
        logits[~mask] = -1e9
        return logits

    @torch.no_grad()
    def choose(self, enc: dict) -> int:
        return int(self._logits(enc).argmax().item())

    @torch.no_grad()
    def choose_k(self, enc: dict, k: int) -> list[int]:
        """スコア上位 k 個の合法indexを返す(複数選択コンテキスト用)。"""
        logits = self._logits(enc)
        order = torch.argsort(logits, descending=True).tolist()
        return order[:max(1, k)]


def load_policy(path: str) -> Policy:
    ckpt = torch.load(path, map_location="cpu")
    policy = Policy()
    policy.features_extractor.load_state_dict(ckpt["features_extractor"])
    policy.policy_net.load_state_dict(ckpt["policy_net"])
    policy.action_net.load_state_dict(ckpt["action_net"])
    policy.eval()
    return policy
