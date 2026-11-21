#!/usr/bin/env python3
"""Builds the benchmark firmware, one ELF per case version, in the pinned toolchain container. Standard library only; needs Docker.

  python tools/build-firmware.py --out build/fw [--expect results/2026-11-21/firmware-build.json]

The toolchain image is built from firmware/toolchain/Dockerfile when it is not there yet (it is never pulled).
Writes <out>/<case>_v<N>.elf and <out>/firmware-build.json: the image, its id, and the size and SHA-256 of every ELF.
With --expect the SHA-256 of every ELF is compared with a reference firmware-build.json (the published record's);
the exit code is 1 when one differs.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
IMAGE = "agent-bench/arm-gcc:12.2.rel1-1"
BUILD = ("set -e; cmake -S /work/firmware -B /tmp/b -G Ninja -DCMAKE_TOOLCHAIN_FILE=/work/firmware/cmake/arm-gcc-toolchain.cmake"
         " && cmake --build /tmp/b && find /tmp/b -maxdepth 1 -type f -name '*.elf' -exec cp {} /out/ \\;")


def docker(*args, check=True, **kw):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    p = subprocess.run(["docker", *args], env=env, **kw)
    if check and p.returncode != 0:
        sys.exit("docker %s failed with exit code %d" % (args[0], p.returncode))
    return p


def ensure_image():
    if docker("image", "inspect", IMAGE, check=False, capture_output=True).returncode != 0:
        print("building the toolchain image %s from firmware/toolchain" % IMAGE, flush=True)
        docker("build", "-t", IMAGE, os.path.join(ROOT, "firmware", "toolchain"))
    return docker("image", "inspect", "--format", "{{.Id}}", IMAGE, capture_output=True).stdout.decode().strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expected_names():
    with open(os.path.join(ROOT, "cases.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    return ["%s_v%d.elf" % (c["id"], v["v"]) for c in manifest["cases"] for v in c["versions"]]


def main():
    ap = argparse.ArgumentParser(description="Build the benchmark firmware in the pinned toolchain container.")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "fw"), help="output directory (default: build/fw)")
    ap.add_argument("--expect", metavar="FILE", help="reference firmware-build.json whose ELF digests the build must reproduce")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    names = expected_names()
    for name in names:
        try:
            os.remove(os.path.join(out, name))
        except FileNotFoundError:
            pass
    image_id = ensure_image()
    docker("run", "--rm", "--pull=never", "-v", "%s:/work/firmware:ro" % os.path.join(ROOT, "firmware"), "-v", "%s:/out" % out,
           "-e", "SOURCE_DATE_EPOCH=1700000000", IMAGE, "sh", "-c", BUILD)
    outputs = []
    for name in names:
        path = os.path.join(out, name)
        if not os.path.exists(path):
            sys.exit("the build did not produce %s" % name)
        outputs.append({"file": name, "sha256": sha256(path), "bytes": os.path.getsize(path)})
    doc = {"toolchain": "arm", "image": IMAGE, "imageId": image_id, "project": "firmware", "arguments": {"define": []}, "outputs": outputs}
    with open(os.path.join(out, "firmware-build.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    for o in outputs:
        print("%s  %7d  %s" % (o["sha256"], o["bytes"], o["file"]))
    print("built %d images in %s" % (len(outputs), IMAGE))
    if a.expect:
        with open(a.expect, encoding="utf-8") as f:
            ref = {o["file"]: o["sha256"] for o in json.load(f)["outputs"]}
        bad = [o["file"] for o in outputs if ref.get(o["file"]) != o["sha256"]]
        if bad or set(ref) != {o["file"] for o in outputs}:
            print("DIFFERENT from %s: %s" % (a.expect, ", ".join(bad) or "the set of images"))
            sys.exit(1)
        print("identical to %s: all %d images are byte-identical" % (a.expect, len(outputs)))


if __name__ == "__main__":
    main()
