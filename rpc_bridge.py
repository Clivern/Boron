#!/usr/bin/env python3
# Copyright 2026 Clivern. All rights reserved.
# License can be found in the LICENSE file.

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import threading

HOST = "0.0.0.0"
PORT = int(os.environ.get("RPC_PORT", "8765"))
API_KEY = os.environ.get("RPC_API_KEY", "")
PI_MODEL = os.environ.get("PI_MODEL", "")
AUTH_TIMEOUT_S = 10

if not API_KEY:
    sys.exit("RPC_API_KEY is required")
if not PI_MODEL:
    sys.exit("PI_MODEL is required")

pi_env = os.environ.copy()
pi_env.pop("RPC_API_KEY", None)

proc = subprocess.Popen(
    ["pi", "--mode", "rpc", "--no-session", "--model", PI_MODEL],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=sys.stderr,
    bufsize=0,
    env=pi_env,
    cwd="/repo" if os.path.isdir("/repo") else None,
)
assert proc.stdin is not None
assert proc.stdout is not None

lock = threading.Lock()
current = None
pending = []


def keys_match(supplied, expected):
    return hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def pump_stdout():
    global current
    fd = proc.stdout.fileno()
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            os._exit(0)
        with lock:
            sock = current
            if sock is None:
                pending.append(chunk)
                continue
        try:
            sock.sendall(chunk)
        except OSError:
            with lock:
                if current is sock:
                    current = None
                pending.append(chunk)


def read_line(conn):
    buf = bytearray()
    while b"\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)
        if len(buf) > 8192:
            return None
    line, _, _ = buf.partition(b"\n")
    return line


def reject(conn):
    try:
        conn.sendall(b'{"type":"auth","success":false,"error":"invalid api key"}\n')
    except OSError:
        pass
    conn.close()


def handle(conn):
    global current
    conn.settimeout(AUTH_TIMEOUT_S)
    try:
        line = read_line(conn)
    except (TimeoutError, OSError):
        conn.close()
        return
    conn.settimeout(None)

    try:
        record = json.loads(line) if line else {}
    except json.JSONDecodeError:
        record = {}
    if not isinstance(record, dict):
        record = {}

    supplied = str(record.get("apiKey", ""))
    if record.get("type") != "auth" or not keys_match(supplied, API_KEY):
        reject(conn)
        return

    try:
        conn.sendall(b'{"type":"auth","success":true}\n')
    except OSError:
        conn.close()
        return

    with lock:
        backlog = b"".join(pending)
        pending.clear()
        current = conn
    try:
        if backlog:
            conn.sendall(backlog)
        while True:
            data = conn.recv(65536)
            if not data:
                break
            proc.stdin.write(data)
            proc.stdin.flush()
    except OSError:
        pass
    finally:
        with lock:
            if current is conn:
                current = None
        conn.close()


def main():
    threading.Thread(target=pump_stdout, daemon=True).start()
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    while True:
        conn, _ = server.accept()
        handle(conn)


if __name__ == "__main__":
    main()
