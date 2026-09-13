#!/usr/bin/env python3
"""エピソードIDのリストを指定してリプレイを落とす(429はバックオフ)。

`harvest_replays.py` の走査で一度 KEEP したのに原本を消してしまった、
というときの回収用。ファイル名は `<episode>.json` に統一する。

  python3 fetch_episodes.py --ids ids.txt --out DIR
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import harvest_replays as H  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    ids = [x.strip() for x in open(args.ids) if x.strip().isdigit()]
    got = 0
    for eid in ids:
        dst = os.path.join(args.out, "%s.json" % eid)
        if os.path.exists(dst):
            continue
        path = H.fetch(eid, args.out)
        if path and path != dst:
            os.replace(path, dst)
        if os.path.exists(dst):
            got += 1
            print("ok %s (%d/%d)" % (eid, got, len(ids)), flush=True)
        else:
            print("NG %s" % eid, flush=True)
    print("done %d/%d" % (got, len(ids)))


if __name__ == "__main__":
    main()
