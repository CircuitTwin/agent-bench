#!/usr/bin/env python3
"""Runs every benchmark firmware image on CircuitTwin (`ct run`) and on a pinned QEMU. Standard library only.

  python tools/run.py --ct <ct> --fw build/fw --out out/run [--server URL --token-file FILE]

Writes <out>/raw/<case>_v<N>.<platform>.json and <out>/results.json. tools/report.py turns them into the report.
Absolute paths of this machine (the firmware, catalog, checkout and home directories) are replaced by
placeholders (<fw>, <catalog>, <repo>, <out>, <ct>, <home>) before anything is written.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
QEMU_LOCK = os.path.join(ROOT, "qemu", "qemu-system-arm.lock.json")
CT_RELEASE = os.path.join(ROOT, "ct-release.json")
TWIN_BOARD = "stm32f4-discovery"
QEMU_MACHINE = "olimex-stm32-h405"


def git_state():
    """Revision and cleanliness of this checkout; None outside a git checkout."""
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


def make_scrubber(pairs):
    """Returns a function that replaces every (absolute path, placeholder) pair in the strings of a JSON value."""
    rules = []
    for path, name in sorted((p for p in pairs if p[0]), key=lambda p: -len(p[0])):
        path = path.rstrip("/\\")
        for variant in {path.replace("\\", "/"), path.replace("/", "\\")}:
            rules.append((re.compile(re.escape(variant) + r"([/\\])?", re.I),
                          lambda m, n=name: n + ("/" if m.group(1) else "")))

    def scrub(value):
        if isinstance(value, str):
            for rx, sub in rules:
                value = rx.sub(sub, value)
            return value
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        return value
    return scrub


def run_capture(cmd, timeout, env=None, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env, cwd=cwd)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        return None, out, "wall timeout after %ss" % timeout


def twin_env(a):
    """The environment of the ct runs: this process's, plus the server, token and catalog given on the command line."""
    env = dict(os.environ)
    if a.server:
        env["CT_SERVER"] = a.server
    if a.token_file:
        with open(a.token_file, encoding="utf-8") as f:
            env["CT_TOKEN"] = f.read().strip()
    if a.catalog_dir:
        env["CT_CATALOG_DIR"] = os.path.abspath(a.catalog_dir)
    return env


def ct_info(ct_exe):
    """Version and digest of the ct binary, and whether it is the build pinned in ct-release.json."""
    _, out, _ = run_capture([ct_exe, "--version"], 60)
    info = {"exe": os.path.basename(ct_exe), "exeSha256": sha256(ct_exe), "version": out.strip(), "pinned": False}
    try:
        with open(CT_RELEASE, encoding="utf-8") as f:
            pin = json.load(f)
        if pin["binaries"].get(info["exe"]) == info["exeSha256"]:
            info["pinned"] = True
            info["release"] = {"platform": pin["platform"], "sourceRevision": pin["sourceRevision"], "cleanTree": pin.get("cleanTree")}
    except (OSError, ValueError, KeyError):
        pass
    return info


def run_twin(ct_exe, elf, max_ms, extra, wall_s, env, scrub):
    cmd = [ct_exe, "--json", "run", elf, "--board", TWIN_BOARD, "--max-ms", str(max_ms),
           "--until", "CT-BENCH-DONE"] + extra
    rc, out, err = run_capture(cmd, wall_s, env)
    doc = None
    start = out.find("{")
    if start >= 0:
        try:
            doc = json.loads(out[start:])
        except ValueError:
            doc = None
    return {"command": scrub([os.path.basename(cmd[0])] + cmd[1:]), "exit": rc, "result": scrub(doc),
            "stdoutHead": scrub(out[:600]) if doc is None else "", "stderr": scrub(err)[-1500:]}


def split_qemu(text):
    parts = {}
    key = "status"
    buf = []
    for line in text.splitlines():
        if line in ("---SERIAL---", "---STDOUT---", "---FAULTS---", "---UNIMP---", "---GUEST---"):
            parts[key] = "\n".join(buf)
            key = line.strip("-").lower()
            buf = []
        else:
            buf.append(line)
    parts[key] = "\n".join(buf)
    return parts


def check_qemu_image(lock):
    """The image must exist (it is never pulled) and hold the pinned qemu-system-arm; returns the image id."""
    image = lock["image"]
    insp = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True)
    if insp.returncode != 0:
        sys.exit("QEMU image %s is missing: docker build -t %s qemu" % (image, image))
    rc, out, _ = run_capture(["docker", "run", "--rm", "--pull=never", "--entrypoint", "sha256sum", image, lock["binary"]], 120)
    got = out.split()[0] if rc == 0 and out.split() else ""
    if got != lock["binarySha256"]:
        sys.exit("%s in %s has sha256 %r, qemu/qemu-system-arm.lock.json pins %r" % (lock["binary"], image, got, lock["binarySha256"]))
    return insp.stdout.decode().strip()


def run_qemu(image, fw_dir, elf_name, limit_s, scrub):
    # qemu/run.sh is stripped of carriage returns in the container, so a CRLF checkout still runs.
    cmd = ["docker", "run", "--rm", "--pull=never", "-v", "%s:/fw:ro" % fw_dir,
           "-v", "%s:/qemu-run.sh:ro" % os.path.join(ROOT, "qemu", "run.sh"),
           "--entrypoint", "sh", image, "-c",
           "tr -d '\\r' < /qemu-run.sh > /tmp/r.sh; sh /tmp/r.sh %s %d" % (elf_name, int(limit_s * 10))]
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    rc, out, err = run_capture(cmd, 120, env)
    parts = split_qemu(out)
    return {"image": image, "machine": QEMU_MACHINE, "dockerExit": rc, "status": parts.get("status", "").strip(),
            "serial": parts.get("serial", ""), "stdout": parts.get("stdout", ""), "faults": parts.get("faults", ""),
            "unimp": parts.get("unimp", ""), "guest": parts.get("guest", ""),
            "stderr": scrub(err)[-800:]}


def main():
    ap = argparse.ArgumentParser(description="Run every benchmark firmware version on CircuitTwin and on pinned QEMU.")
    ap.add_argument("--ct", default=shutil.which("ct") or "", metavar="EXE", help="the ct binary (default: ct on PATH)")
    ap.add_argument("--server", metavar="URL", help="CircuitTwin server for the ct runs (default: CT_SERVER, else the sign-in `ct login` stored)")
    ap.add_argument("--token-file", metavar="FILE", help="file holding the access token for the ct runs (default: CT_TOKEN, else the stored sign-in); "
                    "the token is handed to ct only and never written to the record")
    ap.add_argument("--catalog-dir", metavar="DIR", help="twin catalog of the ct runs (default: CT_CATALOG_DIR, else ct's own default)")
    ap.add_argument("--fw", default=os.path.join(ROOT, "build", "fw"),
                    help="directory with the built <case>_v<N>.elf files (default: build/fw, from tools/build-firmware.py)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "run"), help="output directory (default: out/run)")
    ap.add_argument("--date", default=datetime.date.today().isoformat(), help="date written to the record (default: today)")
    ap.add_argument("--only", help="comma list of case ids")
    ap.add_argument("--skip-twin", action="store_true")
    ap.add_argument("--skip-qemu", action="store_true")
    ap.add_argument("--qemu-limit-s", type=float, default=4.0, help="wall limit of one QEMU run (default 4)")
    a = ap.parse_args()
    a.fw = os.path.abspath(a.fw)
    a.out = os.path.abspath(a.out)

    with open(os.path.join(ROOT, "cases.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(QEMU_LOCK, encoding="utf-8") as f:
        lock = json.load(f)
    image = lock["image"]
    image_id = None if a.skip_qemu else check_qemu_image(lock)

    env = twin_env(a)
    scrub = make_scrubber([(a.fw, "<fw>"), (env.get("CT_CATALOG_DIR", ""), "<catalog>"), (ROOT, "<repo>"), (a.out, "<out>"),
                           (os.path.dirname(os.path.abspath(a.ct)) if a.ct else "", "<ct>"), (os.path.expanduser("~"), "<home>")])
    info = None
    if not a.skip_twin:
        if not a.ct or not os.path.exists(a.ct):
            sys.exit("no ct binary: pass --ct <path> (or put ct on PATH)")
        info = ct_info(a.ct)
        print("ct: %s, sha256 %s: %s" % (info["version"], info["exeSha256"],
              "the pinned build" if info["pinned"] else "NOT the pinned build (ct-release.json): the numbers can differ from the published record"))

    build_json = os.path.join(a.fw, "firmware-build.json")
    os.makedirs(a.out, exist_ok=True)
    if os.path.exists(build_json):
        with open(build_json, encoding="utf-8") as f:
            fw_build = json.load(f)
        with open(os.path.join(a.out, "firmware-build.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(fw_build, f, indent=1, sort_keys=True)

    only = set(a.only.split(",")) if a.only else None
    raw_dir = os.path.join(a.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)
    records = []
    for case in manifest["cases"]:
        if only and case["id"] not in only:
            continue
        max_ms = case.get("maxMs", manifest["defaultMaxMs"])
        for ver in case["versions"]:
            name = "%s_v%d" % (case["id"], ver["v"])
            elf = os.path.join(a.fw, name + ".elf")
            if not os.path.exists(elf):
                sys.exit("missing firmware %s (build it with: python tools/build-firmware.py --out %s)" % (elf, a.fw))
            rec = {"case": case["id"], "version": ver["v"], "name": name, "elfSha256": sha256(elf), "runs": {}}
            if not a.skip_twin:
                rec["runs"]["twin"] = run_twin(a.ct, elf, max_ms, manifest.get("twinArgs", []), 180, env, scrub)
                for extra in case.get("twinExtra", []):
                    rec["runs"]["twin:" + extra["label"]] = run_twin(a.ct, elf, max_ms, manifest.get("twinArgs", []) + extra["args"], 180, env, scrub)
            if not a.skip_qemu:
                rec["runs"]["qemu"] = run_qemu(image, a.fw, name + ".elf", a.qemu_limit_s, scrub)
            for plat, run in rec["runs"].items():
                with open(os.path.join(raw_dir, "%s.%s.json" % (name, plat.replace(":", "-"))), "w", encoding="utf-8", newline="\n") as f:
                    json.dump(run, f, indent=1, sort_keys=True)
            records.append(rec)
            print("ran", name, {p: ("done" if r else "none") for p, r in rec["runs"].items()}, flush=True)

    prior = {}
    old_meta = {}
    results_path = os.path.join(a.out, "results.json")
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            old_meta = json.load(f)
        prior = {r["name"]: r for r in old_meta.get("records", [])}
        info = info or old_meta.get("ct")
    merged = {}
    for r in records:
        runs = {p: {"raw": "raw/%s.%s.json" % (r["name"], p.replace(":", "-"))} for p in r["runs"]}
        old_rec = prior.pop(r["name"], None)
        if old_rec and old_rec["elfSha256"] == r["elfSha256"]:
            runs = dict(old_rec["runs"], **runs)
        merged[r["name"]] = dict(r, runs=runs)
    merged.update(prior)
    qemu_meta = {"machine": QEMU_MACHINE, "image": image, "imageId": image_id,
                 "binarySha256": lock["binarySha256"], "version": lock["version"]}
    if a.skip_qemu and old_meta.get("qemu"):
        qemu_meta = old_meta["qemu"]
    meta = {"schema": "ct.agent-bench-results/1", "date": a.date, "twinBoard": TWIN_BOARD, "qemu": qemu_meta,
            "ct": info, "label": "provisional", "harness": git_state(), "records": [merged[k] for k in sorted(merged)]}
    with open(results_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
    print("wrote", results_path)


if __name__ == "__main__":
    main()
