#!/usr/bin/env python3
# Copyright 2026 Clivern. All rights reserved.
# License can be found in the LICENSE file.

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import uuid
from typing import Any, Callable, Iterator, Optional


EventHandler = Callable[[dict[str, Any]], None]


class BridgeClient:
    def __init__(self, host: str, port: int, api_key: str):
        self.host = host
        self.port = port
        self.api_key = api_key
        self._sock: Optional[socket.socket] = None
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._handlers: list[EventHandler] = []
        self._reader: Optional[threading.Thread] = None

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port))
        self._sock = sock
        self._send({"type": "auth", "apiKey": self.api_key})
        reply = self._read_record()
        if not reply or reply.get("type") != "auth" or not reply.get("success"):
            sock.close()
            err = (reply or {}).get("error", "auth failed")
            raise RuntimeError(err)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._closed.set()
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def on_event(self, handler: EventHandler) -> Callable[[], None]:
        self._handlers.append(handler)

        def unsubscribe() -> None:
            try:
                self._handlers.remove(handler)
            except ValueError:
                pass

        return unsubscribe

    def send(self, command: dict[str, Any]) -> None:
        if "id" not in command:
            command = {**command, "id": str(uuid.uuid4())}
        self._send(command)

    def prompt(self, message: str, **extra: Any) -> str:
        req_id = str(uuid.uuid4())
        cmd: dict[str, Any] = {"id": req_id, "type": "prompt", "message": message}
        cmd.update(extra)
        self._send(cmd)
        return req_id

    def prompt_and_wait(
        self,
        message: str,
        timeout: float = 300.0,
        **extra: Any,
    ) -> list[dict[str, Any]]:
        done = threading.Event()
        events: list[dict[str, Any]] = []

        def handler(event: dict[str, Any]) -> None:
            events.append(event)
            if event.get("type") == "agent_settled":
                done.set()

        unsub = self.on_event(handler)
        try:
            self.prompt(message, **extra)
            if not done.wait(timeout):
                raise TimeoutError(f"timed out after {timeout}s waiting for agent_settled")
            return events
        finally:
            unsub()

    def _send(self, record: dict[str, Any]) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        data = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        with self._lock:
            self._sock.sendall(data)

    def _read_record(self) -> Optional[dict[str, Any]]:
        assert self._sock is not None
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                return None
            self._buf.extend(chunk)
        line, _, rest = self._buf.partition(b"\n")
        self._buf[:] = rest
        if line.endswith(b"\r"):
            line = line[:-1]
        if not line:
            return None
        return json.loads(line.decode())

    def _pump(self) -> None:
        assert self._sock is not None
        try:
            while not self._closed.is_set():
                record = self._read_record()
                if record is None:
                    break
                for handler in list(self._handlers):
                    try:
                        handler(record)
                    except Exception as exc:  # noqa: BLE001 — keep pump alive
                        print(f"event handler error: {exc}", file=sys.stderr)
        except OSError:
            pass
        finally:
            self._closed.set()


def _print_event(event: dict[str, Any], verbose: bool) -> None:
    etype = event.get("type")
    if etype == "message_update":
        ame = event.get("assistantMessageEvent") or {}
        if ame.get("type") == "text_delta":
            sys.stdout.write(str(ame.get("delta", "")))
            sys.stdout.flush()
            return
    if etype == "response" and not event.get("success", True):
        print(f"\n[error] {json.dumps(event)}", file=sys.stderr)
        return
    if verbose and etype not in {"message_update"}:
        print(f"\n[{etype}] {json.dumps(event)}", file=sys.stderr)


def _iter_prompts(args: argparse.Namespace) -> Iterator[str]:
    if args.message:
        yield " ".join(args.message)
        return
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            yield text
            return
    print("Enter prompts (Ctrl-D to quit):", file=sys.stderr)
    while True:
        try:
            line = input("> ")
        except EOFError:
            print(file=sys.stderr)
            break
        line = line.strip()
        if line:
            yield line


def main() -> int:
    parser = argparse.ArgumentParser(description="Talk to a boron RPC bridge")
    parser.add_argument("message", nargs="*", help="prompt to send (default: stdin/REPL)")
    parser.add_argument("--host", default=os.environ.get("RPC_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("RPC_PORT", "8765")))
    parser.add_argument(
        "--api-key",
        default=os.environ.get("RPC_API_KEY", ""),
        help="bridge API key (or set RPC_API_KEY)",
    )
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for agent_settled")
    parser.add_argument("-v", "--verbose", action="store_true", help="print non-text events")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("--api-key or RPC_API_KEY is required")

    client = BridgeClient(args.host, args.port, args.api_key)
    client.on_event(lambda event: _print_event(event, args.verbose))
    try:
        client.connect()
    except (OSError, RuntimeError) as exc:
        print(f"connect failed: {exc}", file=sys.stderr)
        return 1

    try:
        for prompt in _iter_prompts(args):
            try:
                client.prompt_and_wait(prompt, timeout=args.timeout)
                print(file=sys.stdout)
            except TimeoutError as exc:
                print(f"\n{exc}", file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
