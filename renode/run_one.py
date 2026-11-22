#!/usr/bin/env python3
"""Inside-container Renode runner for agent-bench. Standard library only.

Runs one or more ELFs, each in a fresh Renode process using Renode's unmodified
built-in platforms/boards/stm32f4_discovery.repl (via renode/stm32f4_discovery.resc).
Advances virtual time deterministically in small slices via Renode's monitor socket
so execution stops cleanly as soon as CT-BENCH-DONE appears on USART2 or at max_ms.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time

PLATFORM_REPL = "platforms/boards/stm32f4_discovery.repl"
RESC_PATH = "/renode/stm32f4_discovery.resc"
PROMPT_RE = re.compile(rb"\([^)\r\n]+\)\s*$")
FAULT_LINE_RE = re.compile(
    r"\b(BusFault|UsageFault|MemManage|HardFault|Data Abort|Prefetch Abort|Lockup|CPU abort|Execution of invalid|Watchdog reset)\b"
)


def wait_for_prompt(sock, deadline):
    buf = bytearray()
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        sock.settimeout(min(0.5, remaining))
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
            if PROMPT_RE.search(bytes(buf[-256:])):
                return buf.decode("utf-8", "replace"), True
        except socket.timeout:
            continue
    return buf.decode("utf-8", "replace"), False


def send_cmd(sock, cmd, timeout_s=30.0):
    sock.sendall((cmd + "\n").encode("utf-8"))
    return wait_for_prompt(sock, time.monotonic() + timeout_s)


def build_slices_ms(max_ms):
    """Virtual-time slices totaling max_ms: 5 ms early so marker stops promptly, 25 ms later."""
    slices = []
    acc = 0
    while acc < max_ms:
        step = 5 if acc < 50 else 25
        if acc + step > max_ms:
            step = max_ms - acc
        slices.append(step)
        acc += step
    return slices


def fmt_timespan(ms):
    return "00:00:%02d.%03d" % (ms // 1000, ms % 1000)


def run_one(elf_name, max_ms, port=12345, wall_limit_s=60.0):
    serial_path = "/tmp/serial.txt"
    log_path = "/tmp/renode.log"
    for p in (serial_path, log_path):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass

    t0 = time.monotonic()
    proc = subprocess.Popen(
        ["renode", "--disable-xwt", "--plain", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    sock = None
    status = "unknown"
    vtime_info = ""
    errors = []

    try:
        connect_deadline = time.monotonic() + 25.0
        while time.monotonic() < connect_deadline:
            if proc.poll() is not None:
                status = "renode-exited-early-%d" % proc.returncode
                break
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
                break
            except OSError:
                time.sleep(0.1)

        if sock is None:
            if status == "unknown":
                status = "connect-timeout"
        else:
            _, ok = wait_for_prompt(sock, time.monotonic() + 20.0)
            if not ok:
                status = "banner-timeout"
            else:
                # Strip CRLF in case the repo was checked out with Windows line endings.
                clean_resc = "/tmp/stm32f4_discovery.resc"
                with open(RESC_PATH, "rb") as rf:
                    resc_bytes = rf.read().replace(b"\r\n", b"\n")
                with open(clean_resc, "wb") as wf:
                    wf.write(resc_bytes)
                setup_cmds = [
                    "$bin=@/fw/%s" % elf_name,
                    "$serial=@%s" % serial_path,
                    "$log=@%s" % log_path,
                    "include @%s" % clean_resc,
                ]
                setup_ok = True
                for cmd in setup_cmds:
                    resp, ok = send_cmd(sock, cmd, timeout_s=45.0)
                    if not ok:
                        status = "setup-timeout:%s" % cmd
                        setup_ok = False
                        break
                    if "Error" in resp or "There was an error" in resp or "Bad parameters" in resp:
                        errors.append("%s: %s" % (cmd, resp.strip()[:300]))

                if setup_ok:
                    run_deadline = time.monotonic() + wall_limit_s
                    for step_ms in build_slices_ms(max_ms):
                        rem = run_deadline - time.monotonic()
                        if rem <= 0:
                            status = "wall-timeout"
                            break
                        _, ok = send_cmd(sock, 'emulation RunFor "%s"' % fmt_timespan(step_ms), timeout_s=min(30.0, rem))
                        if not ok:
                            status = "run-timeout"
                            break
                        if os.path.exists(serial_path):
                            with open(serial_path, "rb") as sf:
                                if b"CT-BENCH-DONE" in sf.read():
                                    status = "marker"
                                    break
                    if status == "unknown":
                        status = "time-limit"
                    resp, _ = send_cmd(sock, "emulation GetTimeSourceInfo", timeout_s=5.0)
                    vtime_info = resp.strip()
                    try:
                        sock.sendall(b"quit\n")
                    except OSError:
                        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)

    wall_ms = int((time.monotonic() - t0) * 1000)
    serial = ""
    if os.path.exists(serial_path):
        with open(serial_path, "r", encoding="utf-8", errors="replace") as sf:
            serial = sf.read()

    log_full = ""
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
            log_full = lf.read()

    warnings = []
    err_lines = []
    fault_lines = []
    for ln in log_full.splitlines():
        if "[ERROR]" in ln:
            err_lines.append(ln)
        elif "[WARNING]" in ln:
            warnings.append(ln)
        if FAULT_LINE_RE.search(ln):
            fault_lines.append(ln)

    return {
        "platform": PLATFORM_REPL,
        "status": status,
        "maxMs": max_ms,
        "wallMs": wall_ms,
        "vtimeInfo": vtime_info,
        "serial": serial,
        "monitorErrors": errors,
        "warningCount": len(warnings),
        "errorCount": len(err_lines),
        "warningsHead": warnings[:40],
        "errorsHead": err_lines[:40],
        "faultLinesHead": fault_lines[:40],
        "logTail": log_full[-2000:],
    }


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: run_one.py <out_dir> <elf1:max_ms> [<elf2:max_ms> ...]")
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    ver = subprocess.run(["renode", "--version"], capture_output=True, text=True).stdout.strip()
    for idx, spec in enumerate(sys.argv[2:]):
        elf_name, max_ms_s = spec.split(":")
        res = run_one(elf_name, int(max_ms_s), port=12345 + (idx % 20))
        res["renodeVersion"] = ver
        name = elf_name[:-4] if elf_name.endswith(".elf") else elf_name
        with open(os.path.join(out_dir, "%s.renode.json" % name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(res, f, indent=1, sort_keys=True)
        line = next((ln.strip() for ln in res["serial"].splitlines() if "CT-BENCH " in ln), "(no result line)")
        print(
            "%s  status=%s  wall=%dms  warn=%d  err=%d  | %s"
            % (name.ljust(16), res["status"].ljust(10), res["wallMs"], res["warningCount"], res["errorCount"], line),
            flush=True,
        )


if __name__ == "__main__":
    main()
