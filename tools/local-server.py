#!/usr/bin/env python3
"""Starts a throwaway CircuitTwin server with development sign-in on the loopback interface, and writes an access token for it.

  python tools/local-server.py --server-bin <ct-server> [--port 8137] [--data-dir work/server] [--token-file work/token.txt]

--server-bin is the ct-server binary of the release pinned in ct-release.json. The server keeps running until you stop it
(Ctrl-C). The access token (scope `twins`: enough for `ct run`) is written to --token-file (created with mode 600 where the
system has file modes) for `tools/run.py --token-file`; it is never printed. Development sign-in exists only with
CT_ENV=dev and CT_AUTH=dev on a loopback address, and any well-formed e-mail address signs in. Standard library only.
"""
import argparse
import hashlib
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mint_token(base, email, scopes):
    """Signs in through the development endpoint and creates a personal access token; returns its secret."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), {"x-ct-csrf": "1", "content-type": "application/json"}, method="POST")
        try:
            return json.loads(opener.open(req, timeout=60).read().decode())
        except urllib.error.HTTPError as e:
            sys.exit("POST %s answered %s: %s" % (path, e.code, e.read().decode("utf-8", "replace")[:300]))
    post("/auth/dev/login", {"email": email})
    return post("/api/v1/tokens", {"name": "agent-bench", "scopes": scopes})["token"]


def main():
    ap = argparse.ArgumentParser(description="Start a throwaway CircuitTwin server (development sign-in) and write an access token for it.")
    ap.add_argument("--server-bin", required=True, metavar="EXE", help="the ct-server binary")
    ap.add_argument("--port", type=int, default=8137, help="loopback port (default 8137)")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "work", "server"), help="the server's storage directory (default: work/server)")
    ap.add_argument("--token-file", default=os.path.join(ROOT, "work", "token.txt"), help="where the access token is written (default: work/token.txt)")
    ap.add_argument("--email", default="agent-bench@example.invalid", help="the account the token belongs to (made on first use; the server wants a domain with a dot)")
    a = ap.parse_args()
    server = os.path.abspath(a.server_bin)
    data_dir = os.path.abspath(a.data_dir)
    token_file = os.path.abspath(a.token_file)
    if not os.path.exists(server):
        sys.exit("no ct-server binary at %s" % server)
    try:
        with open(os.path.join(ROOT, "ct-release.json"), encoding="utf-8") as f:
            pin = json.load(f)["binaries"].get(os.path.basename(server))
    except (OSError, ValueError, KeyError):
        pin = None
    if pin != sha256(server):
        print("warning: this ct-server is not the build pinned in ct-release.json", file=sys.stderr)

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    listen = "127.0.0.1:%d" % a.port
    env = dict(os.environ, CT_ENV="dev", CT_AUTH="dev", CT_DATA_DIR=data_dir, CT_SERVER_LISTEN=listen)
    log_path = data_dir + ".log"
    with open(log_path, "wb") as log:
        proc = subprocess.Popen([server], env=env, cwd=data_dir, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 60
        while True:
            if proc.poll() is not None:
                sys.exit("ct-server exited with code %s; see %s" % (proc.returncode, log_path))
            with open(log_path, "rb") as f:
                if b"ct-server listening on" in f.read():
                    break
            if time.time() > deadline:
                sys.exit("ct-server did not start within 60 s; see %s" % log_path)
            time.sleep(0.2)
        token = mint_token("http://" + listen, a.email, ["twins"])
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        print("ct-server is ready on http://%s (storage %s, log %s)" % (listen, data_dir, log_path))
        print("access token written to %s" % token_file)
        print("Leave this running; stop it with Ctrl-C.", flush=True)
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
