#!/usr/bin/env python3
"""Scores a run: builds report.md and summary.json from <out>/results.json and <out>/raw/*. Standard library only.

  python tools/report.py --out out/run [--against results/2026-11-21]

Every count is computed from the raw records; nothing is typed by hand. The report depends on the record only,
never on the machine or the checkout it runs on. With --against the totals and every case of the new run are
compared with the summary.json of a reference record (the published one); the exit code is 1 when they differ.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
LINE = re.compile(r"CT-BENCH (\S+) (PASS|FAIL)(?: (.*))?")
FAULT = re.compile(r"BusFault|UsageFault|MemManage|HardFault|Data Abort|Prefetch Abort|Undefined|exception 3\b")
TWIN_NOTE = re.compile(r"generated the (\S+) twin (twin:[0-9a-f]+) from (.+?) into the catalog")


def result_line(text):
    last = None
    for ln in text.splitlines():
        m = LINE.search(ln)
        if m:
            last = (m.group(2), (m.group(3) or "").strip())
    return last, "CT-BENCH-DONE" in text


def classify_twin(run):
    doc = run.get("result")
    if doc is not None and doc.get("verdict") is None and doc.get("error"):
        err = doc["error"]
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        return {"kind": "refused", "signals": [], "sig": ["refused"], "evidence": "ct refused the run (exit %s): %s" % (run.get("exit"), msg[:200])}
    if doc is None:
        return {"kind": "no-data", "signals": ["no-data"], "sig": ["no-data"],
                "evidence": "no result document (exit %s) %s" % (run.get("exit"), (run.get("stderr") or run.get("stdoutHead") or "")[:160])}
    console = "\n".join(str(v) for v in (doc.get("console") or {}).values())
    line, done = result_line(console)
    verdict = str(doc.get("verdict"))
    stop = doc.get("stop") or {}
    stop_kind = str(stop.get("kind", "?")) if isinstance(stop, dict) else str(stop)
    issues = doc.get("issues") or []
    counts = {}
    for i in issues:
        counts[str(i.get("code", "?"))] = counts.get(str(i.get("code", "?")), 0) + 1
    codes = sorted(counts)
    note = doc.get("verdictNote")
    signals = []
    if stop_kind in ("fault", "lockup"):
        signals.append("fault")
    if not done:
        signals.append("hang")
    elif line and line[0] == "FAIL":
        signals.append("self-check")
    # Informational issues (modelled bus behaviour such as an absent address) are listed in the evidence but are not a diagnostic.
    loud = [i for i in issues if str(i.get("severity", "")).lower() != "info"]
    if loud or note or verdict not in ("pass",):
        signals.append("twin-diagnostic")
    ev = []
    if line:
        ev.append("CT-BENCH %s %s" % line)
    else:
        ev.append("no result line")
    ev.append("verdict=%s stop=%s" % (verdict, stop_kind))
    if stop_kind == "fault":
        ev.append("fault=%s" % str((stop.get("fault") or {}).get("exception", "?")))
    if counts:
        ev.append("issues=%s" % ",".join("%s x%d" % (c, counts[c]) for c in codes))
    if note:
        ev.append("note=%s" % json.dumps(note, sort_keys=True)[:200])
    if doc.get("error"):
        ev.append("error=%s" % str(doc["error"])[:120])
    return {"kind": "ok", "signals": signals, "line": line, "evidence": "; ".join(ev), "engine": (doc.get("engine") or {}).get("revision"),
            "sig": sorted(set(signals) | set("code:" + c for c in codes) | {"line:" + (line[0] if line else "none"), "verdict:" + verdict})}


def classify_qemu(run):
    serial = run.get("serial", "")
    line, done = result_line(serial)
    faults = run.get("faults", "")
    signals = []
    if FAULT.search(faults):
        signals.append("fault")
    if not done:
        signals.append("hang")
    elif line and line[0] == "FAIL":
        signals.append("self-check")
    unimp = [ln.split(":")[0].strip().split()[-1] for ln in run.get("unimp", "").splitlines() if "unimplemented" in ln]
    unimp = sorted(set(unimp))
    ev = []
    if line:
        ev.append("CT-BENCH %s %s" % line)
    else:
        ev.append("no result line (%s)" % run.get("status", "?"))
    if FAULT.search(faults):
        m = re.search(r"(BusFault|UsageFault|MemManage|HardFault)[^\n]*", faults)
        ev.append("log: " + (m.group(0) if m else "fault exception"))
    if unimp:
        ev.append("unimplemented-device log: " + ",".join(unimp))
    return {"kind": "ok", "signals": signals, "line": line, "unimp": unimp, "evidence": "; ".join(ev),
            "sig": sorted(set(signals) | {"line:" + (line[0] if line else "none")})}


RENODE_FAULT = re.compile(r"\b(BusFault|UsageFault|MemManage|HardFault|Data Abort|Prefetch Abort|Lockup|CPU abort|Execution of invalid)\b")


def classify_renode(run):
    """Classifies a Renode run under the exact same pass/fail oracle rules as QEMU:
    fault (Cortex-M fault/abort), hang (no CT-BENCH-DONE before time limit), or self-check (CT-BENCH FAIL).
    Unhandled-register [WARNING] and [ERROR] log lines are recorded in evidence as information (like QEMU's unimplemented-device log)."""
    serial = run.get("serial", "")
    line, done = result_line(serial)
    fault_text = "\n".join(run.get("faultLinesHead") or []) + "\n" + "\n".join(run.get("errorsHead") or [])
    signals = []
    if RENODE_FAULT.search(fault_text):
        signals.append("fault")
    if not done:
        signals.append("hang")
    elif line and line[0] == "FAIL":
        signals.append("self-check")
    warn_periphs = set()
    for ln in run.get("warningsHead") or []:
        m = re.search(r"\[WARNING\]\s+([^:]+):", ln)
        if m:
            warn_periphs.add(m.group(1).strip())
    ev = []
    if line:
        ev.append("CT-BENCH %s %s" % line)
    else:
        ev.append("no result line (%s)" % run.get("status", "?"))
    if RENODE_FAULT.search(fault_text):
        m = RENODE_FAULT.search(fault_text)
        ev.append("fault: " + m.group(0))
    if run.get("errorCount"):
        first_err = (run.get("errorsHead") or [""])[0]
        first_err = re.sub(r"^\[[^\]]+\]\s+\[ERROR\]\s*", "", first_err)
        ev.append("errors=%d (%s)" % (run["errorCount"], first_err[:100]))
    if run.get("warningCount"):
        ev.append("warnings=%d (%s)" % (run["warningCount"], ",".join(sorted(warn_periphs)) or "log"))
    return {"kind": "ok", "signals": signals, "line": line, "warnings": sorted(warn_periphs), "evidence": "; ".join(ev),
            "sig": sorted(set(signals) | {"line:" + (line[0] if line else "none")})}


def caught(c):
    return c["kind"] != "refused" and bool(c["signals"])


def platform_seen(c):
    """A catch the platform made itself: not only the firmware's own FAIL line."""
    return c["kind"] != "refused" and any(s != "self-check" for s in c["signals"])


def label(c, correct, base=None):
    """base is the correct version's result on the same platform: a catch identical to it is not evidence of the bug."""
    if c is None:
        return "not run"
    if c["kind"] == "refused":
        return "refused by ct (not counted)"
    if correct:
        return "false alarm (%s)" % "+".join(c["signals"]) if caught(c) else "clean"
    if not caught(c):
        return "MISSED"
    same = base is not None and c["sig"] == base["sig"]
    return "caught (%s)%s" % ("+".join(c["signals"]), ", same as the correct version" if same else "")


def fw_toolchain(out):
    try:
        with open(os.path.join(out, "firmware-build.json"), encoding="utf-8") as f:
            d = json.load(f)
        return "`%s`, image id `%s`" % (d.get("image"), d.get("imageId"))
    except (OSError, ValueError):
        return "unknown"


def esc(s):
    return s.replace("|", "\\|").replace("\n", " ")


def pinned_ct(ct):
    """Whether the ct binary of the record is the build pinned in ct-release.json (a record may predate the flag)."""
    if "pinned" in ct:
        return bool(ct["pinned"])
    try:
        with open(os.path.join(ROOT, "ct-release.json"), encoding="utf-8") as f:
            pin = json.load(f)
        return pin["binaries"].get(os.path.basename(str(ct.get("exe", "")))) == ct.get("exeSha256")
    except (OSError, ValueError, KeyError):
        return False


def pinned_twin():
    """The id of the twin the published record was made with (ct-release.json)."""
    try:
        with open(os.path.join(ROOT, "ct-release.json"), encoding="utf-8") as f:
            return json.load(f)["twin"]["id"]
    except (OSError, ValueError, KeyError):
        return None


def twin_id(twin_runs):
    """The twin id and its documents, from the note `ct run` prints when it generates a twin, and the ids that are not the pinned twin."""
    found = {}
    for run in twin_runs:
        m = TWIN_NOTE.search(run.get("stderr") or "")
        if m:
            found[m.group(2)] = m.group(3)
    if not found:
        return "taken from the catalog (the runs print no generation note)", []
    pin = pinned_twin()

    def note(k):
        if not pin:
            return ""
        return ", the twin of the published record" if k == pin else ", NOT the twin of the published record (`%s`)" % pin
    return "; ".join("`%s` generated from %s%s" % (k, esc(found[k]), note(k)) for k in sorted(found)), [k for k in sorted(found) if pin and k != pin]


def compare(summary, ref_dir):
    """Differences between this run's summary and the reference summary: totals and every case on every platform."""
    with open(os.path.join(ref_dir, "summary.json"), encoding="utf-8") as f:
        ref = json.load(f)
    diffs = []
    if summary["totals"] != ref["totals"]:
        for k in sorted(set(summary["totals"]) | set(ref["totals"])):
            if summary["totals"].get(k) != ref["totals"].get(k):
                diffs.append("totals.%s: %s, reference %s" % (k, json.dumps(summary["totals"].get(k), sort_keys=True), json.dumps(ref["totals"].get(k), sort_keys=True)))
    mine = {(r["case"], r["version"]): r for r in summary["rows"]}
    theirs = {(r["case"], r["version"]): r for r in ref["rows"]}
    for key in sorted(set(mine) | set(theirs)):
        a, b = mine.get(key), theirs.get(key)
        name = "%s v%d" % key
        if a is None or b is None:
            diffs.append("%s: only in the %s" % (name, "reference" if a is None else "new run"))
            continue
        for plat in sorted(set(a["platforms"]) | set(b["platforms"])):
            if a["platforms"].get(plat) != b["platforms"].get(plat):
                diffs.append("%s %s: %s, reference %s" % (name, plat, json.dumps(a["platforms"].get(plat), sort_keys=True), json.dumps(b["platforms"].get(plat), sort_keys=True)))
    return diffs, len(theirs), sum(len(r["platforms"]) for r in ref["rows"])


def main():
    ap = argparse.ArgumentParser(description="Score a benchmark run and write report.md and summary.json next to its results.json.")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "run"), help="run directory with results.json and raw/ (default: out/run)")
    ap.add_argument("--against", metavar="DIR", help="reference record (a directory with summary.json) to compare the new run with")
    a = ap.parse_args()
    with open(os.path.join(ROOT, "cases.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(a.out, "results.json"), encoding="utf-8") as f:
        res = json.load(f)
    notes = {(c["id"], v["v"]): v for c in manifest["cases"] for v in c["versions"]}
    rows = []
    twin_runs = []
    for rec in res["records"]:
        v = notes[(rec["case"], rec["version"])]
        entry = {"case": rec["case"], "version": rec["version"], "kind": v["kind"], "bugClass": v.get("bugClass", ""),
                 "note": v.get("note", ""), "elfSha256": rec["elfSha256"], "platforms": {}}
        for plat in rec["runs"]:
            with open(os.path.join(a.out, rec["runs"][plat]["raw"]), encoding="utf-8") as f:
                run = json.load(f)
            if plat not in ("qemu", "renode"):
                twin_runs.append(run)
            if plat == "qemu":
                entry["platforms"][plat] = classify_qemu(run)
            elif plat == "renode":
                entry["platforms"][plat] = classify_renode(run)
            else:
                entry["platforms"][plat] = classify_twin(run)
        rows.append(entry)
    by = {(r["case"], r["version"]): r for r in rows}

    has_renode = any("renode" in r["platforms"] for r in rows)
    plats = [p for p in ("twin", "renode", "qemu") if any(p in r["platforms"] for r in rows)] if has_renode else ["twin", "qemu"]
    extras = sorted({p for r in rows for p in r["platforms"] if p.startswith("twin:")})
    s = {"platforms": {}}
    for p in plats:
        bugs = [r for r in rows if r["kind"] == "bug" and p in r["platforms"]]
        cors = [r for r in rows if r["kind"] == "correct" and p in r["platforms"]]
        disc = 0
        for r in bugs:
            c = r["platforms"][p]
            base = by[(r["case"], 0)]["platforms"].get(p)
            if caught(c) and (base is None or c["sig"] != base["sig"]):
                disc += 1
        s["platforms"][p] = {"buggyVersions": len(bugs), "caught": sum(caught(r["platforms"][p]) for r in bugs),
                             "missed": sum(not caught(r["platforms"][p]) for r in bugs),
                             "correctVersions": len(cors), "falseAlarms": sum(caught(r["platforms"][p]) for r in cors),
                             "caughtAndDifferentFromCorrect": disc,
                             "caughtByPlatformSignal": sum(platform_seen(r["platforms"][p]) for r in bugs)}
    if "twin" in plats and "qemu" in plats:
        bugs = [r for r in rows if r["kind"] == "bug" and "twin" in r["platforms"] and "qemu" in r["platforms"]]
        s["bothCaught"] = sum(caught(r["platforms"]["twin"]) and caught(r["platforms"]["qemu"]) for r in bugs)
        s["twinOnly"] = sum(caught(r["platforms"]["twin"]) and not caught(r["platforms"]["qemu"]) for r in bugs)
        s["qemuOnly"] = sum(not caught(r["platforms"]["twin"]) and caught(r["platforms"]["qemu"]) for r in bugs)
        s["neither"] = sum(not caught(r["platforms"]["twin"]) and not caught(r["platforms"]["qemu"]) for r in bugs)
    if "twin" in plats and "renode" in plats:
        bugs = [r for r in rows if r["kind"] == "bug" and "twin" in r["platforms"] and "renode" in r["platforms"]]
        s["twinAndRenode"] = sum(caught(r["platforms"]["twin"]) and caught(r["platforms"]["renode"]) for r in bugs)
        s["twinOnlyVsRenode"] = sum(caught(r["platforms"]["twin"]) and not caught(r["platforms"]["renode"]) for r in bugs)
        s["renodeOnlyVsTwin"] = sum(not caught(r["platforms"]["twin"]) and caught(r["platforms"]["renode"]) for r in bugs)
        s["neitherTwinNorRenode"] = sum(not caught(r["platforms"]["twin"]) and not caught(r["platforms"]["renode"]) for r in bugs)
    classes = {}
    for r in rows:
        if r["kind"] != "bug":
            continue
        d = classes.setdefault(r["bugClass"], {"versions": 0, **{p: 0 for p in plats}})
        d["versions"] += 1
        for p in plats:
            if p in r["platforms"] and caught(r["platforms"][p]):
                d[p] += 1
    s["byBugClass"] = classes

    ct = res.get("ct") or {}
    prov = res.get("provenance") or {}
    ct_rev = prov.get("sourceRevision") or (ct.get("release") or {}).get("sourceRevision")
    ct_clean = prov.get("cleanTree") or (ct.get("release") or {}).get("cleanTree")
    harness = res.get("harness") or {}
    title = "# Agent-bug benchmark: CircuitTwin versus Renode and QEMU" if has_renode else "# Agent-bug benchmark: CircuitTwin versus QEMU"
    out = [title, "",
           "Generated by `tools/report.py` from `results.json` and `raw/`; every count is computed.", "",
           "| item | value |", "|---|---|",
           "| date | %s |" % res["date"]]
    if harness:
        out.append("| harness revision | `%s`, %s |" % (harness.get("revision"), "uncommitted changes in the checkout" if harness.get("dirtyTree") else "clean checkout"))
    if ct_rev:
        out.append("| ct build source revision | `%s`, %s |" % (ct_rev, "clean source tree" if ct_clean else "tree state not recorded"))
    twin_text, other_twins = twin_id(twin_runs)
    unusable = sum(c["kind"] in ("refused", "no-data") for r in rows for c in r["platforms"].values())
    if unusable:
        out.append("| **runs without a verdict** | **%d** (refused by ct, or no result document: fix the cause and run them again) |" % unusable)
    if "twin" in plats:
        out += ["| twin board | `%s` (`ct --json run <elf> --board %s --until CT-BENCH-DONE`) |" % (res["twinBoard"], res["twinBoard"]),
                "| ct binary | %s |" % esc("%s; `%s`; sha256 `%s`; %s" % (ct.get("version", "?"), ct.get("exe", "?"), ct.get("exeSha256", "?"),
                                                                        "the pinned build (ct-release.json)" if pinned_ct(ct) else "not the pinned build (ct-release.json)")),
                "| twin | %s |" % twin_text,
                "| twin engine revision | `%s` |" % next((r["platforms"]["twin"].get("engine") for r in rows if r["platforms"].get("twin", {}).get("engine")), "unknown")]
    out.append("| firmware toolchain | %s |" % esc(fw_toolchain(a.out)))
    if "renode" in plats and res.get("renode"):
        rn_meta = res["renode"]
        out += ["| Renode | Renode %s (`%s`), platform `%s` |" % (rn_meta.get("version", "?"), rn_meta.get("build", "?"), rn_meta.get("platform", "?")),
                "| Renode image | `%s`, id `%s` |" % (rn_meta.get("image", "?"), rn_meta.get("imageId")),
                "| Renode binary sha256 | `%s` |" % rn_meta.get("binarySha256", "?")]
    if "qemu" in plats and res.get("qemu"):
        out += ["| QEMU | %s %s, machine `%s` |" % ("qemu-system-arm", res["qemu"]["version"], res["qemu"]["machine"]),
                "| QEMU image | `%s`, id `%s` |" % (res["qemu"]["image"], res["qemu"].get("imageId")),
                "| QEMU binary sha256 | `%s` |" % res["qemu"]["binarySha256"]]
    out.append("")
    out += ["## Totals", "", "| platform | buggy versions | caught | missed | correct versions | false alarms | caught and different from the correct version | caught by a platform signal (fault, hang, twin diagnostic), not only the firmware's FAIL line |", "|---|---|---|---|---|---|---|---|"]
    for p in plats:
        t = s["platforms"][p]
        out.append("| %s | %d | %d | %d | %d | %d | %d | %d |" % (p, t["buggyVersions"], t["caught"], t["missed"], t["correctVersions"], t["falseAlarms"], t["caughtAndDifferentFromCorrect"], t["caughtByPlatformSignal"]))
    if "bothCaught" in s:
        out += ["", "Buggy versions caught by both: %d; twin only: %d; QEMU only: %d; neither: %d." % (s["bothCaught"], s["twinOnly"], s["qemuOnly"], s["neither"])]
    if "twinAndRenode" in s:
        out += ["", "Buggy versions caught by both (twin & Renode): %d; twin only: %d; Renode only: %d; neither: %d." % (s["twinAndRenode"], s["twinOnlyVsRenode"], s["renodeOnlyVsTwin"], s["neitherTwinNorRenode"])]
    out += ["", "`caught` means the run was not a clean pass: a CT-BENCH FAIL line, no result line before the limit (hang), a fault exception, or (twin only) a",
            "non-pass verdict, issue or verdict note. A correct version that is flagged is a false alarm. `caught and different from the correct version`",
            "counts a catch only where the signal differs from what the correct version of the same case produced on that platform.", ""]
    out += ["## By bug class", "", "| bug class | versions | " + " | ".join(plats) + " |", "|---|---|" + "---|" * len(plats)]
    for k in sorted(classes):
        d = classes[k]
        out.append("| %s | %d | %s |" % (k, d["versions"], " | ".join("%d" % d[p] for p in plats)))
    plat_names = {"twin": "twin", "renode": "Renode", "qemu": "QEMU"}
    hdr_cols = ["case", "version", "bug class"] + [plat_names[p] for p in plats] + [plat_names[p] + " evidence" for p in plats]
    out += ["", "## Every case", "", "| " + " | ".join(hdr_cols) + " |", "|" + "---|" * len(hdr_cols)]
    for r in rows:
        correct = r["kind"] == "correct"
        vals = [r["case"], "v%d %s" % (r["version"], "correct" if correct else "bug"), esc(r["bugClass"] or "-")]
        for p in plats:
            vals.append(label(r["platforms"].get(p), correct, by[(r["case"], 0)]["platforms"].get(p)))
        for p in plats:
            c = r["platforms"].get(p)
            vals.append(esc(c["evidence"]) if c else "-")
        out.append("| " + " | ".join(vals) + " |")
    if extras:
        out += ["", "## Twin with a non-default option", "", "| case | version | option | result | evidence |", "|---|---|---|---|---|"]
        for r in rows:
            for p in extras:
                if p in r["platforms"]:
                    out.append("| %s | v%d | %s | %s | %s |" % (r["case"], r["version"], p.split(":", 1)[1], label(r["platforms"][p], r["kind"] == "correct", by[(r["case"], 0)]["platforms"].get(p)), esc(r["platforms"][p]["evidence"])))
    out += ["", "## Bug descriptions", "", "| case | version | description |", "|---|---|---|"]
    for r in rows:
        if r["kind"] == "bug":
            out.append("| %s | v%d | %s |" % (r["case"], r["version"], esc(r["note"])))
    out += ["", "## Firmware", "", "| ELF | sha256 |", "|---|---|"]
    for r in rows:
        out.append("| %s_v%d.elf | `%s` |" % (r["case"], r["version"], r["elfSha256"]))
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    summary = {"schema": "ct.agent-bench-summary/1", "date": res["date"], "ct": ct or None, "harness": res.get("harness"), "provenance": res.get("provenance"), "totals": s,
               "rows": [{k: r[k] for k in ("case", "version", "kind", "bugClass")} | {"platforms": {p: {"caught": caught(c), "signals": c["signals"], "evidence": c["evidence"]} for p, c in r["platforms"].items()}} for r in rows]}
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
    print("wrote report.md and summary.json:", json.dumps(s["platforms"], sort_keys=True))
    if unusable:
        print("warning: %d run(s) were refused by ct or have no result document; the totals do not describe them" % unusable)
    if other_twins:
        print("warning: the twin of these runs (%s) is not the one of the published record (%s): the numbers can differ" % (", ".join(other_twins), pinned_twin()))
    if a.against:
        diffs, n_cases, n_runs = compare(summary, a.against)
        if diffs:
            print("DIFFERENT from %s: %d difference(s)" % (a.against, len(diffs)))
            for d in diffs:
                print("  " + d)
            sys.exit(1)
        print("identical to %s: totals and %d cases (%d platform results: caught flag, signals and evidence)" % (a.against, n_cases, n_runs))


if __name__ == "__main__":
    main()
