"""リプレイ(JSON)から BC 教師データ (obs, action) を抽出する。

対象: フーディン(Alakazam)専用BC・勝ちのみ。
  meta/replay/Alakazam/ の各リプレイで、勝者側の使用デッキがフーディン
  (Alakazam線を含む)なら、その勝者側の決定を教師にする。
  - 初手デッキ選択(context 41)を除き、選択肢が2つ以上あるものだけ。
  - マルチ選択(action が複数)は先頭indexを教師にする(近似)。
  - ラベルが合法マスク外のものは捨てる。

出力: bc_data.npz (encode_observation でエンコード済み配列 + label)。
      fuudin_deck.csv (教師のデッキ60枚, 取得できた場合)。
"""
import glob
import json
import os
import sys

import numpy as np

import ptcg_env as env

# フーディン(Alakazam線)の判定に使うカードid
FUUDIN_IDS = {741, 742, 743, 245, 109}
DECK_CONTEXT = 41
REPLAY_DIR = "../meta/replay/Alakazam"


def _iter_side_ids(d, side):
    """side の盤面(active/bench)に登場したポケモンidを列挙。"""
    for s in d["steps"]:
        if side >= len(s):
            continue
        cur = (s[side].get("observation") or {}).get("current") or {}
        pls = cur.get("players")
        if not pls or side >= len(pls):
            continue
        for area in ("active", "bench"):
            for c in (pls[side].get(area) or []):
                if isinstance(c, dict) and c.get("id") is not None:
                    yield c["id"]


def _deck_action(d, side):
    """side が context41 で返した60枚デッキ(あれば)。"""
    for s in d["steps"][:6]:
        if side >= len(s):
            continue
        p = s[side]
        obs = p.get("observation") or {}
        sel = obs.get("select")
        act = p.get("action")
        if sel is not None and sel.get("context") == DECK_CONTEXT and act:
            return act
    return None


def _is_fuudin(d, side):
    if any(cid in FUUDIN_IDS for cid in _iter_side_ids(d, side)):
        return True
    deck = _deck_action(d, side)
    return bool(deck) and any(cid in FUUDIN_IDS for cid in deck)


def extract(replay_dir):
    files = sorted(glob.glob(os.path.join(replay_dir, "*.json")))
    samples = []
    n_games = n_used = 0
    fuudin_deck = None
    for fp in files:
        try:
            d = json.load(open(fp))
        except Exception:
            continue
        n_games += 1
        rewards = d.get("rewards") or [0, 0]
        if rewards[0] == rewards[1]:
            continue
        winner = 0 if rewards[0] > rewards[1] else 1
        if not _is_fuudin(d, winner):
            continue                       # 勝者がフーディンでなければスキップ
        n_used += 1
        if fuudin_deck is None:
            dk = _deck_action(d, winner)
            if dk and len(dk) == 60:
                fuudin_deck = dk
        for s in d["steps"]:
            if winner >= len(s):
                continue
            p = s[winner]
            obs = p.get("observation") or {}
            sel = obs.get("select")
            act = p.get("action")
            if sel is None or not act:
                continue
            if sel.get("context") == DECK_CONTEXT:
                continue
            opts = sel.get("option") or []
            if len(opts) <= 1:
                continue
            label = act[0] if isinstance(act, list) else act
            if not isinstance(label, int) or label >= env.MAX_OPTIONS:
                continue
            try:
                enc = env.encode_observation(obs, winner)
            except Exception:
                continue
            if enc["mask"][label] != 1:
                continue
            samples.append((enc, label))
    return samples, dict(games=n_games, used=n_used), fuudin_deck


def save(samples, out="bc_data.npz"):
    if not samples:
        sys.exit("サンプル0件")
    keys = list(samples[0][0].keys())
    arrs = {k: np.stack([s[0][k] for s in samples]) for k in keys}
    arrs["label"] = np.array([s[1] for s in samples], dtype=np.int64)
    np.savez_compressed(out, **arrs)
    return arrs


if __name__ == "__main__":
    samples, info, deck = extract(REPLAY_DIR)
    print(f"リプレイ {info['games']}件 / 採用(勝者=フーディン) {info['used']}件")
    print(f"抽出サンプル(obs,action): {len(samples)} 件")
    arrs = save(samples)
    print(f"保存: bc_data.npz  keys={list(arrs.keys())}")
    print(f"ラベル分布(index上位10): {np.bincount(arrs['label'])[:10].tolist()}")
    if deck:
        with open("fuudin_deck.csv", "w") as f:
            f.write("\n".join(str(x) for x in deck) + "\n")
        print(f"教師デッキ保存: fuudin_deck.csv ({len(deck)}枚)")
    else:
        print("教師デッキは取得できず(勝者側がs.0でない等)。別途用意が必要")
