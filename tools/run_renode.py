#!/usr/bin/env python3
"""Runs every benchmark firmware image on pinned official Renode v1.17.0. Standard library only.

  python tools/run_renode.py --fw build/fw --out out/run [--only clk_gpio,wdg]

Writes <out>/raw/<case>_v<N>.renode.json and merges into <out>/results.json.
Verifies the pinned Renode binary SHA-256 from renode/renode.lock.json before running,
and runs the container with --network none using the pre-warmed SVD cache.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
RENODE_LOCK = os.path.join(ROOT, "renode", "renode.lock.json")


def git_state():
    def git(*args):
        try:
            p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=False)
        except OSError:
            return None
        return p.stdout.strip() if p.returncode == 0 else None
    rev = git("rev-parse", "HEAD")
    if not rev:
        return None
    return {"revision": rev, "dirtyTree": bool(git("status", "--porcelain"))}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_renode_image(lock):
    """The image must exist (never pulled) and hold the pinned Renode binary; returns the image id."""
    if not shutil.which("docker"):
        sys.exit("docker is not on PATH: the Renode runs need Docker with Linux containers")
    image = lock["image"]
    insp = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True)
    if insp.returncode != 0:
        sys.exit("Renode image %s is missing: docker build -t %s renode" % (image, image))
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    p = subprocess.run(
        ["docker", "run", "--rm", "--pull=never", "--entrypoint", "sha256sum", image, lock["binary"]],
        capture_output=True, text=True, env=env, timeout=120,
    )
    got = p.stdout.split()[0] if p.returncode == 0 and p.stdout.split() else ""
    if got != lock["binarySha256"]:
        sys.exit("%s in %s has sha256 %r, renode/renode.lock.json pins %r" % (lock["binary"], image, got, lock["binarySha256"]))
    return insp.stdout.decode().strip()


def run_renode_batch(lock, fw_dir, raw_dir, specs, network_none=True):
    """Runs all requested ELFs in a single ephemeral container (fresh Renode process per ELF)."""
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    cmd = ["docker", "run", "--rm", "--pull=never"]
    if network_none:
        cmd += ["--network", "none"]
    cmd += [
        "-v", "%s:/fw:ro" % os.path.abspath(fw_dir),
        "-v", "%s:/renode:ro" % os.path.join(ROOT, "renode"),
        "-v", "%s:/out" % os.path.abspath(raw_dir),
        "--entrypoint", "python3",
        lock["image"], "/renode/run_one.py", "/out",
        *specs,
    ]
    p = subprocess.run(cmd, env=env)
    if p.returncode != 0:
        sys.exit("Renode container exited with code %d" % p.returncode)


def main():
    ap = argparse.ArgumentParser(description="Run benchmark firmware images on pinned official Renode.")
    ap.add_argument("--fw", default=os.path.join(ROOT, "build", "fw"),
                    help="directory with the built <case>_v<N>.elf files (default: build/fw)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "run"), help="output directory (default: out/run)")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="date written to the record (default: today)")
    ap.add_argument("--only", help="comma list of case ids")
    ap.add_argument("--allow-network", action="store_true", help="allow container network access (default: --network none)")
    a = ap.parse_args()
    a.fw = os.path.abspath(a.fw)
    a.out = os.path.abspath(a.out)

    with open(os.path.join(ROOT, "cases.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(RENODE_LOCK, encoding="utf-8") as f:
        lock = json.load(f)

    image_id = check_renode_image(lock)
    raw_dir = os.path.join(a.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    build_json = os.path.join(a.fw, "firmware-build.json")
    if os.path.exists(build_json) and not os.path.exists(os.path.join(a.out, "firmware-build.json")):
        with open(build_json, encoding="utf-8") as f:
            fw_build = json.load(f)
        with open(os.path.join(a.out, "firmware-build.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(fw_build, f, indent=1, sort_keys=True)

    only = set(a.only.split(",")) if a.only else None
    specs = []
    entries = []
    for case in manifest["cases"]:
        if only and case["id"] not in only:
            continue
        max_ms = case.get("maxMs", manifest["defaultMaxMs"])
        for ver in case["versions"]:
            name = "%s_v%d" % (case["id"], ver["v"])
            elf = os.path.join(a.fw, name + ".elf")
            if not os.path.exists(elf):
                sys.exit("missing firmware %s (build it with: python tools/build-firmware.py --out %s)" % (elf, a.fw))
            specs.append("%s.elf:%d" % (name, max_ms))
            entries.append({"case": case["id"], "version": ver["v"], "name": name, "elfSha256": sha256(elf)})

    print("Running %d ELF(s) on Renode %s (%s)..." % (len(specs), lock["version"], lock["platform"]), flush=True)
    run_renode_batch(lock, a.fw, raw_dir, specs, network_none=not a.allow_network)

    prior = {}
    old_meta = {}
    results_path = os.path.join(a.out, "results.json")
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            old_meta = json.load(f)
        prior = {r["name"]: r for r in old_meta.get("records", [])}

    merged = {}
    for e in entries:
        runs = {"renode": {"raw": "raw/%s.renode.json" % e["name"]}}
        old_rec = prior.pop(e["name"], None)
        if old_rec and old_rec["elfSha256"] == e["elfSha256"]:
            runs = dict(old_rec["runs"], **runs)
        merged[e["name"]] = dict(e, runs=runs)
    merged.update(prior)

    renode_meta = {
        "version": lock["version"],
        "build": lock["build"],
        "platform": lock["platform"],
        "image": lock["image"],
        "imageId": image_id,
        "binarySha256": lock["binarySha256"],
        "archiveSha256": lock["archiveSha256"],
    }
    meta = dict(old_meta) if old_meta else {
        "schema": "ct.agent-bench-results/1",
        "label": "provisional",
    }
    meta["date"] = a.date
    meta["renode"] = renode_meta
    meta["harness"] = git_state()
    meta["records"] = [merged[k] for k in sorted(merged)]
    with open(results_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    print("wrote", results_path)


if __name__ == "__main__":
    main()
