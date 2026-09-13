#!/usr/bin/env python3
"""リーダーボードをページ送りで全部落として teamName -> (teamId, score) を作る。

リプレイには **チーム名しか入っていない**(teamId が無い)ので、
「このデッキを使っている人のリプレイをもっと落とす」には名前からIDを引く必要がある。

  python3 lb_dump.py --out lb_all.csv [--pages 20]
"""
import argparse
import csv
import os
import subprocess
import sys
import tempfile

KAGGLE = os.path.expanduser("~/kaggle-cli-venv/bin/kaggle")
COMP = "pokemon-tcg-ai-battle"


def page(token=None, size=200):
    args = [KAGGLE, "competitions", "leaderboard", COMP, "-s",
            "--page-size", str(size), "--format", "csv"]
    if token:
        args += ["--page-token", token]
    with tempfile.TemporaryFile("w+") as fo, tempfile.TemporaryFile("w+") as fe:
        p = subprocess.Popen(args, stdout=fo, stderr=fe,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            return [], None
        fo.seek(0)
        out = fo.read()
    nxt = None
    lines = []
    for line in out.splitlines():
        if line.startswith("Next Page Token"):
            nxt = line.split("=", 1)[1].strip()
        else:
            lines.append(line)
    rows = list(csv.DictReader(lines))
    return rows, nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", type=int, default=20)
    args = ap.parse_args()
    seen, token = {}, None
    for i in range(args.pages):
        rows, token = page(token)
        if not rows:
            break
        for r in rows:
            seen[r["teamId"]] = r
        print("page %d: +%d (計 %d) score末尾=%s"
              % (i + 1, len(rows), len(seen), rows[-1]["score"]), flush=True)
        if not token:
            break
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["teamId", "teamName", "submissionDate", "score"])
        w.writeheader()
        for r in seen.values():
            w.writerow(r)
    print("wrote %s (%d teams)" % (args.out, len(seen)))


if __name__ == "__main__":
    main()
