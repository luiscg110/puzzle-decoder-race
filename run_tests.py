#!/usr/bin/env python3
"""Integration tests against a live puzzle server on :8080."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8080"


def get(fragment_id: int) -> dict:
    with urllib.request.urlopen(f"{BASE}/fragment?id={fragment_id}", timeout=3) as resp:
        return json.loads(resp.read().decode())


def test_schema_and_determinism() -> None:
    a = get(42)
    b = get(42)
    assert a == b, (a, b)
    assert set(a) == {"id", "index", "text"}, a
    assert a["id"] == 42
    assert isinstance(a["index"], int)
    assert isinstance(a["text"], str) and a["text"]
    print("PASS schema + deterministic id=42")


def test_discover_pieces() -> dict[int, str]:
    pieces: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=64) as pool:
        results = list(pool.map(get, range(1, 161)))
    for data in results:
        pieces.setdefault(data["index"], data["text"])
    indexes = sorted(pieces)
    contiguous = indexes == list(range(indexes[-1] + 1))
    message = " ".join(pieces[i] for i in indexes)
    print(f"PASS discover: n={len(pieces)} indexes={indexes} contiguous={contiguous}")
    print(f"     message={message!r}")
    assert contiguous, indexes
    assert 1 <= len(pieces) <= 64
    return pieces


def test_decoder_runs(expected: str, runs: int = 5) -> list[float]:
    times: list[float] = []
    messages: list[str] = []
    for i in range(1, runs + 1):
        proc = subprocess.run(
            [sys.executable, "decoder.py"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        msg = proc.stdout.strip()
        messages.append(msg)
        elapsed_line = [ln for ln in proc.stderr.splitlines() if "elapsed_seconds=" in ln]
        assert elapsed_line, proc.stderr
        elapsed = float(elapsed_line[0].split("elapsed_seconds=")[1].split()[0])
        times.append(elapsed)
        bonus = "bonus" in proc.stderr
        print(f"PASS decoder run {i}: {elapsed:.3f}s bonus={bonus} msg={msg!r}")
        assert msg == expected, (msg, expected)

    assert len(set(messages)) == 1
    under = sum(1 for t in times if t < 1.0)
    mean = sum(times) / len(times)
    print(f"PASS consistency: identical message across {runs} runs")
    print(f"INFO timing: times={times} under_1s={under}/{runs} mean={mean:.3f}s")
    assert under == runs, f"bonus too rare: {under}/{runs}"
    return times


def main() -> int:
    started = time.perf_counter()
    print("=== Integration tests vs", BASE, "===")
    get(1)  # connectivity
    print("PASS server reachable")
    test_schema_and_determinism()
    pieces = test_discover_pieces()
    expected = " ".join(pieces[i] for i in range(len(pieces)))
    test_decoder_runs(expected)
    print(f"=== ALL TESTS PASSED in {time.perf_counter() - started:.2f}s ===")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("FAIL", exc, file=sys.stderr)
        raise SystemExit(1)
