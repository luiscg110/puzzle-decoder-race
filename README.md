# Puzzle Decoder Race

Client that fetches out-of-order puzzle fragments from a server, reassembles them, and prints the full message as fast as possible.

## Requirements

- Python 3.10+ (**stdlib only** — no `pip install`)
- Docker (official puzzle server)

## Start the puzzle server

```bash
docker run -d --name puzzle-server -p 8080:8080 ifajardov/puzzle-server
```

Or:

```bash
docker compose up -d
```

If Docker is unavailable, use the local mock (same API, different message):

```bash
python3 mock_server.py
```

## Run the decoder

```bash
python3 decoder.py
```

- **Stdout:** assembled message  
- **Stderr:** timing (`elapsed_seconds=…`), probe count, and bonus line when under 1s

Optional knobs (defaults already work):

```bash
python3 decoder.py --prior-n 24 --max-wave 120
```

## Strategy

The server returns fragments out of order, each with a random 100–400ms delay, and the total piece count is unknown.

1. **Ask in parallel** — fire a wave of requests together so wall-clock time is about one delay, not N delays.
2. **Cache by position** — store `index → text`; ignore duplicates.
3. **Guess how many pieces exist** — start from a small prior, then refine from how often each index appears (Chao1 / Good–Turing style counting).
4. **Ask only what you still need** — if something is still missing, size the next wave from that estimate instead of always requesting a huge fixed number.
5. **Stop when complete** — indexes form `0..max` with no gaps, and new unique indexes have effectively stopped appearing.
6. **No third-party deps** — `urllib` + threads.

## Bonus (< 1 second)

Against the official `ifajardov/puzzle-server` (28 fragments), default settings typically finish in **~0.53s** with **~120 probes** (verified 10/10 under 1s in local runs).

```bash
python3 run_tests.py
```

## Layout

| File | Role |
|------|------|
| `decoder.py` | Concurrent puzzle client |
| `mock_server.py` | Local stand-in server |
| `run_tests.py` | Integration tests vs a live `:8080` server |
| `docker-compose.yml` | Official image on `:8080` |
| `start-server.sh` | Docker pull/run helper |
| `reasoning-log.md` | Session analysis / decisions log |
