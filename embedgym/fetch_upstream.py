#!/usr/bin/env python3
"""Fetch pinned EmbedGym-Bench metadata, task specs, and selected agent .hex runs.

Standard library only. Downloads upstream EmbedGym assets from the pinned website
data release (verified by SHA-256 against manifest.json) into a local cache
directory without committing upstream files into this repository.

Usage:
  python embedgym/fetch_upstream.py --cache D:/ct/tmp/embedgym-upstream
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PIN_PATH = os.path.join(HERE, "upstream-pin.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_url(url, dest, expected_sha256=None, timeout=60):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        if expected_sha256 is None or sha256_file(dest) == expected_sha256:
            return dest
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "agent-bench-embedgym/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        while True:
            buf = resp.read(1 << 16)
            if not buf:
                break
            out.write(buf)
    if expected_sha256 is not None:
        got = sha256_file(tmp)
        if got != expected_sha256:
            os.remove(tmp)
            raise RuntimeError(f"SHA-256 mismatch for {url}: got {got}, expected {expected_sha256}")
    os.replace(tmp, dest)
    return dest


def select_controls(runs, supported_tasks, targets):
    """Deterministically pick the lexicographically first passing run and
    (when available) lexicographically first failing run with hasFirmware=True
    for every (target, task) pair. Zero cherry-picking."""
    by_key = {}
    for r in runs:
        t = r.get("target")
        tid = r.get("task")
        v = r.get("verdict")
        if t in targets and tid in supported_tasks and v in ("pass", "fail") and r.get("hasFirmware"):
            by_key.setdefault((t, tid, v), []).append(r)

    selected = []
    for t in sorted(targets):
        for tid in sorted(supported_tasks):
            for v in ("pass", "fail"):
                cands = sorted(by_key.get((t, tid, v), []), key=lambda x: x["id"])
                if cands:
                    selected.append(cands[0])
    return selected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", required=True, help="Local cache directory for upstream EmbedGym data")
    ap.add_argument("--workers", type=int, default=8, help="Concurrent HTTP downloads")
    args = ap.parse_args()

    pin = json.load(open(PIN_PATH, encoding="utf-8"))
    base = pin["upstream"]["dataBaseUrl"].rstrip("/")
    cache = os.path.abspath(args.cache)
    os.makedirs(cache, exist_ok=True)

    print(f"Fetching manifest.json from {base} ...", flush=True)
    manifest_path = fetch_url(f"{base}/manifest.json", os.path.join(cache, "manifest.json"), timeout=120)
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    got_commit = manifest.get("sourceCommit")
    exp_commit = pin["upstream"]["manifestSourceCommit"]
    if got_commit != exp_commit:
        print(f"WARNING: upstream manifest sourceCommit changed: got {got_commit}, pinned {exp_commit}", file=sys.stderr)

    asset_sha = {a["path"]: a["sha256"] for a in manifest.get("assets", [])}

    fetch_url(f"{base}/catalog.json", os.path.join(cache, "catalog.json"), asset_sha.get("catalog.json"))
    runs_gz = fetch_url(f"{base}/runs.json.gz", os.path.join(cache, "runs.json.gz"), asset_sha.get("runs.json.gz"))
    runs_json = os.path.join(cache, "runs.json")
    if not os.path.isfile(runs_json):
        raw = gzip.decompress(open(runs_gz, "rb").read())
        open(runs_json, "wb").write(raw)
    runs = json.load(open(runs_json, encoding="utf-8"))

    # Download all 117 task specifications (needed for full coverage audit + supported task runs).
    catalog = json.load(open(os.path.join(cache, "catalog.json"), encoding="utf-8"))
    task_jobs = []
    for t in catalog["tasks"]:
        rel = f"tasks/{t['id']}.json"
        task_jobs.append((f"{base}/{rel}", os.path.join(cache, rel), asset_sha.get(rel)))

    supported_tasks = sorted({tid for grp in pin["supportedTasks"].values() for tid in grp})
    supported_targets = sorted(k for k, v in pin["targets"].items() if v["status"] == "supported_subset")
    selected = select_controls(runs, set(supported_tasks), set(supported_targets))

    run_jobs = []
    for r in selected:
        rel = f"runs/{r['id']}.json.gz"
        run_jobs.append((f"{base}/{rel}", os.path.join(cache, rel), asset_sha.get(rel)))

    print(f"Downloading {len(task_jobs)} task specs and {len(run_jobs)} selected agent runs (pass+fail controls)...", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_url, u, d, s) for u, d, s in task_jobs + run_jobs]
        for f in concurrent.futures.as_completed(futs):
            f.result()

    index = {
        "schema": "agent-bench.embedgym-cache-index/1",
        "manifestSourceCommit": got_commit,
        "manifestSha256": sha256_file(manifest_path),
        "selectedRuns": [
            {
                "id": r["id"],
                "target": r["target"],
                "task": r["task"],
                "model": r["model"],
                "mode": r["mode"],
                "verdict": r["verdict"],
                "passed": r["passed"],
                "failed": r["failed"],
            }
            for r in selected
        ],
    }
    idx_path = os.path.join(cache, "selected-runs.json")
    open(idx_path, "w", encoding="utf-8").write(json.dumps(index, indent=2) + "\n")
    pass_n = sum(1 for r in selected if r["verdict"] == "pass")
    fail_n = sum(1 for r in selected if r["verdict"] == "fail")
    print(f"Done. Cached {len(task_jobs)} tasks and {len(selected)} runs ({pass_n} pass, {fail_n} fail) -> {idx_path}")


if __name__ == "__main__":
    main()
