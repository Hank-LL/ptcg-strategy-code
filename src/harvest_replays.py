#!/usr/bin/env python3
"""リプレイを落として「デッキと勝敗」だけ残し、本体は消す。

4.6MB/件 なので全部は置いておけない。走査フェーズでは
`{episode, teams, decks, rewards}` の小さな要約だけを溜め、
狙ったマッチ(--keep で指定したアーキタイプ同士)のときだけ原本を残す。

  python3 harvest_replays.py scan  --lb lb.csv --out idx.jsonl --per-team 2
  python3 harvest_replays.py mine  --team <id> --out idx.jsonl --keep-dir DIR \
      --keep ワナイダー --keep-vs Archaludon,メガルカリオex,メガスターミーex
"""
import argparse
import collections
import csv
import json
import os
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

KAGGLE = os.path.expanduser("~/kaggle-cli-venv/bin/kaggle")
COMP = "pokemon-tcg-ai-battle"


def jp_ids():
    """カード名 -> IDの**集合**。

    ★同名別IDが実在する(イワパレス = 345 と 533)。1つだけ持つと、
      もう片方を使った構築をアーキタイプ判定で丸ごと取りこぼす
      (2026-07-29、イワパレスデッキが Cinderace 扱いになっていた)。
    """
    path = os.path.join(os.path.dirname(BASE), "data",
                        "pokemon-tcg-ai-battle", "JP_Card_Data.csv")
    out = collections.defaultdict(set)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                out[r["カード名"]].add(int(r["カード ID"]))
            except (KeyError, TypeError, ValueError):
                pass
    return out


# 代表カード1枚でアーキタイプを決める(先に一致した方を採る)
ARCH_KEYS = [
    ("メガルカリオex", "メガルカリオex"),
    ("Archaludon", "ブリジュラスex"),
    ("メガスターミーex", "メガスターミーex"),
    ("ドラパルトex", "ドラパルトex"),
    ("ワナイダー", "ロケット団のワナイダー"),
    ("オーロンゲex", "マリィのオーロンゲex"),
    ("フーディン", "フーディン"),
    ("イワパレス", "イワパレス"),
    ("メガガルーラex", "メガガルーラex"),
    ("メガリザードンex", "メガリザードンex"),
    ("Cinderace", "エースバーン"),
    # ★2026-08-01 に台頭した新顔(ユーザー報告)。判定に無いと "?" に落ちる。
    ("メガミミロップex", "メガミミロップex"),
    ("オーガポンex", "オーガポン みどりのめんex"),
    ("オーガポン", "オーガポン みどりのめん"),
    ("ノココッチ", "ノココッチ"),
]


def build_arch():
    jp = jp_ids()
    out = []
    for label, name in ARCH_KEYS:
        ids = jp.get(name)
        if ids:
            out.append((label, set(ids)))
    return out


ARCH = None


def archetype(deck):
    s = set(deck or [])
    for label, ids in ARCH:
        if s & ids:
            return label
    return "?"


def run(args, timeout=90, tries=5):
    """kaggle CLI を叩く。

    ★出力は **一時ファイル** に受ける。`capture_output=True`(=PIPE)だと、
      CLI が孫プロセスにパイプを継がせたまま終わったときに
      `subprocess.run` が communicate で永久に止まる(実測でここに嵌った)。
    ★429(Too Many Requests)は指数バックオフで投げ直す。
    """
    wait = 5.0
    for _ in range(tries):
        with tempfile.TemporaryFile("w+") as fo, tempfile.TemporaryFile("w+") as fe:
            try:
                p = subprocess.Popen(args, stdout=fo, stderr=fe,
                                     stdin=subprocess.DEVNULL,
                                     start_new_session=True)
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                return ""
            except OSError:
                return ""
            fo.seek(0), fe.seek(0)
            out, err = fo.read(), fe.read()
        # ★"429" の単純な部分一致で判定してはいけない。エピソードIDや
        #   タイムスタンプ("88774295" 等)に普通に含まれており、正常な応答を
        #   レート制限と誤判定して延々バックオフに入る(実測で30分溶かした)。
        blob = out + err
        if "Too Many Requests" not in blob and "429 Client Error" not in blob:
            return out
        time.sleep(wait)
        wait = min(wait * 2, 60.0)
    return ""


def submissions(team_id):
    """そのチームの提出ID(新しい順)。アクティブ枠は2つあるので複数返る。"""
    out = run([KAGGLE, "competitions", "team-submissions", str(team_id),
               "--format", "csv"])
    return [r["id"] for r in csv.DictReader(out.splitlines()) if r.get("id")]


def latest_submission(team_id):
    subs = submissions(team_id)
    return subs[0] if subs else None


def episodes(sub_id, limit=None):
    out = run([KAGGLE, "competitions", "episodes", str(sub_id), "--format", "csv"])
    ids = []
    for row in csv.DictReader(out.splitlines()):
        eid = row.get("id")
        if eid and "COMPLETED" in (row.get("state") or ""):
            ids.append(eid)
    return ids[:limit] if limit else ids


def fetch(eid, tmpdir):
    run([KAGGLE, "competitions", "replay", str(eid), "-p", tmpdir])
    # 実際のファイル名は `episode-<id>-replay.json`
    for fn in os.listdir(tmpdir):
        if str(eid) in fn and fn.endswith(".json"):
            return os.path.join(tmpdir, fn)
    return None


def summarize(path, eid):
    try:
        with open(path) as f:
            rep = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    info = rep.get("info") or {}
    rw = rep.get("rewards") or [0, 0]
    decks, arcs = [], []
    for pi in (0, 1):
        try:
            d = rep["steps"][1][pi]["action"]
        except (IndexError, KeyError, TypeError):
            d = None
        d = d if isinstance(d, list) and len(d) == 60 else None
        decks.append(d)
        arcs.append(archetype(d))
    return {
        "episode": int(eid),
        "teams": info.get("TeamNames") or ["?", "?"],
        "arcs": arcs,
        "decks": decks,
        "rewards": rw,
        "steps": len(rep.get("steps") or []),
    }


def main():
    global ARCH
    ARCH = build_arch()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["scan", "mine"])
    ap.add_argument("--lb")
    ap.add_argument("--team")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-team", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--subs", type=int, default=2,
                    help="mine で見る提出数(アクティブ枠は2)")
    ap.add_argument("--keep-dir")
    ap.add_argument("--keep", default="")        # 自分側のアーキタイプ
    ap.add_argument("--keep-vs", default="")     # 相手側のアーキタイプ(カンマ区切り)
    args = ap.parse_args()

    seen = set()
    if os.path.exists(args.out):
        with open(args.out) as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["episode"])
                except (json.JSONDecodeError, KeyError):
                    pass

    keep_vs = {s for s in args.keep_vs.split(",") if s}
    if args.keep_dir:
        os.makedirs(args.keep_dir, exist_ok=True)

    teams = []
    if args.mode == "scan":
        with open(args.lb) as f:
            for row in csv.DictReader(f):
                teams.append(row["teamId"])
    else:
        teams = [args.team]

    tmpdir = tempfile.mkdtemp(prefix="rep_")
    n_kept = 0
    with open(args.out, "a") as fo:
        for ti, team in enumerate(teams):
            subs = submissions(team)
            if args.mode == "scan":
                subs = subs[:1]
            elif args.subs:
                subs = subs[:args.subs]
            eids = []
            for sub in subs:
                eids += episodes(sub, args.per_team if args.mode == "scan" else None)
            eids = list(dict.fromkeys(eids))
            if args.limit:
                eids = eids[:args.limit]
            for eid in eids:
                if int(eid) in seen:
                    continue
                path = fetch(eid, tmpdir)
                if not path:
                    continue
                s = summarize(path, eid)
                if s:
                    seen.add(s["episode"])
                    fo.write(json.dumps(s, ensure_ascii=False) + "\n")
                    fo.flush()
                    hit = False
                    if args.keep_dir and args.keep:
                        for pi in (0, 1):
                            if (s["arcs"][pi] == args.keep
                                    and s["arcs"][1 - pi] in keep_vs):
                                hit = True
                    if hit:
                        os.replace(path, os.path.join(args.keep_dir,
                                                      "%s.json" % eid))
                        n_kept += 1
                        print("KEEP %s  %s vs %s" % (eid, s["arcs"][0], s["arcs"][1]),
                              flush=True)
                if os.path.exists(path):
                    os.remove(path)
            print("[%d/%d] team=%s done (kept=%d)" % (ti + 1, len(teams), team, n_kept),
                  flush=True)
    os.rmdir(tmpdir) if not os.listdir(tmpdir) else None


if __name__ == "__main__":
    main()
