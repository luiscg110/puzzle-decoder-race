#!/usr/bin/env python3
"""Local stand-in for ifajardov/puzzle-server (same API contract)."""

from __future__ import annotations

import hashlib
import json
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Fixed puzzle used only for local testing when Docker is unavailable.
PUZZLE = [
    "Concurrency",
    "beats",
    "latency",
    "when",
    "you",
    "fetch",
    "fragments",
    "in",
    "parallel",
]


def fragment_for_id(fragment_id: int) -> dict:
    digest = hashlib.sha256(str(fragment_id).encode()).digest()
    index = digest[0] % len(PUZZLE)
    return {"id": fragment_id, "index": index, "text": PUZZLE[index]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter than default
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/fragment":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        raw_id = (params.get("id") or ["0"])[0]
        try:
            fragment_id = int(raw_id)
        except ValueError:
            self.send_error(400, "id must be an integer")
            return

        time.sleep(random.uniform(0.1, 0.4))
        body = json.dumps(fragment_for_id(fragment_id)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host, port = "127.0.0.1", 8080
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Mock puzzle server on http://{host}:{port}/fragment?id=1")
    print(f"Secret message: {' '.join(PUZZLE)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
