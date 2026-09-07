#!/usr/bin/env python3
"""
Puzzle Decoder Race client.

Fetches fragments concurrently, reassembles by index, prints, exits.

Sampling uses the coupon-collector / unseen-species framing for unknown n:
Chao1 estimates richness, Good–Turing estimates missing mass, and the next
wave size tracks n (H_n - H_s) instead of a huge fixed probe count.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
MAX_PIECES_HINT = 64


def fetch_fragment(base_url: str, fragment_id: int, timeout: float) -> dict[str, Any] | None:
    url = f"{base_url.rstrip('/')}/fragment?id={fragment_id}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def is_complete(pieces: dict[int, str]) -> bool:
    if not pieces:
        return False
    indexes = sorted(pieces)
    return indexes == list(range(indexes[-1] + 1))


def merge(
    pieces: dict[int, str],
    freqs: Counter[int],
    batch: list[dict[str, Any] | None],
) -> None:
    for data in batch:
        if data is None:
            continue
        index = int(data["index"])
        freqs[index] += 1
        if index not in pieces:
            pieces[index] = str(data["text"])


def fetch_batch(
    base_url: str,
    ids: range,
    timeout: float,
    workers: int,
) -> list[dict[str, Any] | None]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(fetch_fragment, base_url, fragment_id, timeout)
            for fragment_id in ids
        ]
        return [fut.result() for fut in futures]


def chao1_estimate(freqs: Counter[int]) -> float:
    """Chao1: n̂ ≈ S + f1²/(2 f2) (unseen-species richness)."""
    s = len(freqs)
    if s == 0:
        return 0.0
    f1 = sum(1 for c in freqs.values() if c == 1)
    f2 = sum(1 for c in freqs.values() if c == 2)
    if f2 > 0:
        return s + (f1 * f1) / (2.0 * f2)
    return s + (f1 * (f1 - 1)) / 2.0


def good_turing_missing_mass(freqs: Counter[int], probes: int) -> float:
    """Good–Turing: P(next draw is new) ≈ f1 / k."""
    if probes <= 0:
        return 1.0
    f1 = sum(1 for c in freqs.values() if c == 1)
    return f1 / probes


def harmonic(n: float) -> float:
    """H_n ≈ ln n + γ + 1/(2n)."""
    if n <= 0:
        return 0.0
    return math.log(n) + 0.5772156649 + 1.0 / (2.0 * n)


def coupon_collector_target(n_hat: float, miss_prob: float = 0.05) -> int:
    """≈ n ln n + n ln(1/ε) draws to collect all n types."""
    n = max(n_hat, 1.0)
    return int(math.ceil(n * math.log(n) + n * math.log(1.0 / miss_prob)))


def expected_additional_samples(n_hat: float, unique: int) -> float:
    """Expected extra draws given s distinct already: n (H_n - H_s)."""
    n = max(n_hat, float(unique), 1.0)
    s = max(unique, 0)
    if s >= n:
        return 0.0
    return n * (harmonic(n) - harmonic(float(s)))


def next_wave_size(
    freqs: Counter[int],
    probes: int,
    *,
    min_wave: int,
    max_wave: int,
) -> int:
    s = len(freqs)
    n_hat = max(chao1_estimate(freqs), float(s), 1.0)
    remaining = expected_additional_samples(n_hat, s) * 2.0  # safety factor
    missing = good_turing_missing_mass(freqs, probes)

    idxs = sorted(freqs)
    contiguous = bool(idxs) and idxs == list(range(idxs[-1] + 1))
    if contiguous and missing <= 0.12:
        remaining = min(remaining, max(float(min_wave), 0.5 * n_hat))

    if remaining <= 0:
        remaining = float(min_wave)
    if missing > 0.15:
        remaining = max(remaining, n_hat)
    return max(min_wave, min(max_wave, int(math.ceil(remaining))))


def should_stop(
    pieces: dict[int, str],
    freqs: Counter[int],
    probes: int,
    *,
    missing_mass_eps: float,
) -> bool:
    if not is_complete(pieces):
        return False
    s = len(pieces)
    n_hat = chao1_estimate(freqs)
    unseen = max(0.0, n_hat - s)
    missing = good_turing_missing_mass(freqs, probes)
    if missing == 0.0 and unseen < 2.0:
        return True
    return missing <= missing_mass_eps and unseen < 1.25


def solve(
    base_url: str,
    initial_wave: int,
    min_wave: int,
    max_wave: int,
    timeout: float,
    max_ids: int,
    missing_mass_eps: float,
    prior_n: float,
) -> tuple[str, float, int, dict[str, float]]:
    start = time.perf_counter()
    pieces: dict[int, str] = {}
    freqs: Counter[int] = Counter()
    next_id = 1
    probes = 0

    # Weak prior from challenge scale ("e.g. ≤10") → first wave via coupon formula.
    prior_target = coupon_collector_target(prior_n)
    first_wave = max(initial_wave, min(max_wave, prior_target))
    wave = first_wave

    while next_id <= max_ids:
        end = min(next_id + wave, max_ids + 1)
        batch_ids = range(next_id, end)
        if not batch_ids:
            break

        workers = min(len(batch_ids), max_wave)
        batch = fetch_batch(base_url, batch_ids, timeout, workers)
        probes += len(batch_ids)
        next_id = end
        merge(pieces, freqs, batch)

        if should_stop(pieces, freqs, probes, missing_mass_eps=missing_mass_eps):
            break

        if len(pieces) >= MAX_PIECES_HINT and is_complete(pieces):
            if good_turing_missing_mass(freqs, probes) <= missing_mass_eps:
                break

        wave = next_wave_size(freqs, probes, min_wave=min_wave, max_wave=max_wave)

    if not is_complete(pieces):
        raise RuntimeError(
            f"Puzzle incomplete after probing: have indexes {sorted(pieces)} "
            f"from {probes} requests"
        )

    stats = {
        "unique": float(len(pieces)),
        "chao1": chao1_estimate(freqs),
        "missing_mass": good_turing_missing_mass(freqs, probes),
        "coupon_target": float(coupon_collector_target(chao1_estimate(freqs))),
        "first_wave": float(first_wave),
    }
    message = " ".join(pieces[i] for i in range(len(pieces)))
    elapsed = time.perf_counter() - start
    return message, elapsed, probes, stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Puzzle Decoder Race client")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Puzzle server base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--prior-n",
        type=float,
        default=24.0,
        help="Weak prior on unknown piece count n (soft starting guess)",
    )
    parser.add_argument(
        "--initial-wave",
        type=int,
        default=32,
        help="Minimum size of the first parallel wave",
    )
    parser.add_argument(
        "--min-wave",
        type=int,
        default=12,
        help="Minimum size of later parallel waves",
    )
    parser.add_argument(
        "--max-wave",
        type=int,
        default=120,
        help="Maximum size of any single parallel wave",
    )
    parser.add_argument(
        "--missing-mass-eps",
        type=float,
        default=0.06,
        help="Good-Turing missing-mass threshold used to stop",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--max-ids",
        type=int,
        default=500,
        help="Safety cap on distinct ids to probe",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        message, elapsed, probes, stats = solve(
            base_url=args.base_url,
            initial_wave=args.initial_wave,
            min_wave=args.min_wave,
            max_wave=args.max_wave,
            timeout=args.timeout,
            max_ids=args.max_ids,
            missing_mass_eps=args.missing_mass_eps,
            prior_n=args.prior_n,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(message)
    print(
        "elapsed_seconds={:.3f} probes={} unique={:.0f} chao1={:.2f} "
        "missing_mass={:.3f} coupon_target={:.0f} first_wave={:.0f}".format(
            elapsed,
            probes,
            stats["unique"],
            stats["chao1"],
            stats["missing_mass"],
            stats["coupon_target"],
            stats["first_wave"],
        ),
        file=sys.stderr,
    )
    if elapsed < 1.0:
        print("bonus: under 1 second", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
