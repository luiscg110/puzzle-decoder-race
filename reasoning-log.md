# Puzzle Decoder Race — Reasoning Log

This file records **assumptions, prompts/questions I used while solving**, and how the reasoning evolved during the challenge. It is meant for the submission requirement about documenting the thinking process—not only the final code.

---

## Starting assumptions (before coding)

1. The Docker image `ifajardov/puzzle-server` is the source of truth; I do not need its source code—only the HTTP API.
2. Piece count is **unknown**. The PDF’s “e.g. ≤10” is an example bound, not a hard guarantee.
3. Same `id` → same fragment; different ids can return duplicates.
4. Serial requests cannot hit the &lt;1s bonus reliably (each call sleeps 100–400ms).
5. Completion must not be “I saw N pieces”; it must detect when the contiguous message is fully covered.

### Prompts / questions I kept asking myself

- “If I don’t know `n`, how do I know when to stop?”
- “How many parallel requests should the first wave use without picking a magic huge number?”
- “What fails if I stop at contiguous `0..k` too early?”
- “Is the live server really ≤10 pieces?”

---

## Phase 1 — Intake and first strategy

**Assumption:** concurrency is mandatory; store by `index`; ignore duplicate indexes.

**Plan:** many parallel GETs → map `index → text` → stop when indexes are contiguous and “quiet”.

**Delegation / tooling notes:**
- Created project under `Projects/puzzle-decoder-race`.
- Docker from the agent environment was initially blocked; added `mock_server.py` with the same API contract so development could continue offline.

**External reference (not copied as the submission):** saw that other solvers used concurrent workers + contiguous completion; confirmed the intended shape, then implemented an original stdlib version.

---

## Phase 2 — First working client (quiescence)

**What I tried:** asyncio workers + stop after no new unique index for ~0.2s.

**Result on mock:** correct message, under 1s.

**New doubt / prompt:**  
“Contiguous `0..k` + quiet time can still be wrong if a higher index exists but wasn’t sampled yet.”

**Decision:** add stronger confirmation (more duplicate hits after the last new index).

**Tradeoff learned:** safer completion made runs slower (often &gt;1s).

---

## Phase 3 — Burst waves

**Prompt:** “Wall-clock should be one delay window per wave, not per request.”

**What I tried:** large parallel bursts, then a confirm burst.

**Bug found:** default asyncio/thread pool was too small → sleeps were mostly serialized (~2s).

**Decision:** use an explicit `ThreadPoolExecutor(max_workers=wave_size)`.

**Temporary fixed knobs:** e.g. `--burst 80/160` + confirm wave. Worked for speed, but still a “pick a big number” strategy.

---

## Phase 4 — Live official server changes the assumptions

**Critical discovery:** with `ifajardov/puzzle-server` up (and after killing a leftover mock on the same port), the puzzle had **28 fragments**, not ≤10.

Full message:

`hello world quick brown fox jumps over lazy dog you have to call all request at same time if you want to see the puzzle fragments fast enough`

**Assumption that broke:** treating “≤10” as an early-success stop (`MAX_PIECES=10`) → incomplete assembly.

**Prompt after that:**  
“The PDF example bound is not the live `n`. Don’t hard-code 10. Don’t hard-code 28 either.”

---

## Phase 5 — Math for unknown `n` (what shipped)

**Prompt:** “What is the mathematical problem when the number of coupon types is unknown?”

Research framing used:
- **Coupon collector** — about `n ln n + n ln(1/ε)` samples when `n` is known
- Expected remaining given `s` found — `n (H_n − H_s)`
- **Chao1** — estimate unknown richness from frequencies
- **Good–Turing** — missing mass ≈ `f1 / probes` as a stop signal

**Final design decisions:**
1. Weak prior `prior_n=24` (soft guess near the PDF’s “small n”, not the live 28).
2. First wave sized by coupon formula, capped by `--max-wave` (default 120).
3. Later waves sized by `2 * n̂ * (H_n̂ − H_s)`.
4. Stop when indexes are contiguous `0..max` and missing mass / Chao1 say almost nothing unseen remains.
5. Stdlib only (`urllib` + threads).

**Why prior 24 (assumption, not a server fact):**
- PDF suggests small `n` (~10).
- Pure 10 makes the first wave too small → extra latency wave.
- 24 is a soft middle ground; 28 is learned from data, not hard-coded.

---

## Validation prompts I used

- “Does the same `id` always return the same JSON?” → yes.
- “Is the assembled message stable across runs?” → yes.
- “Do we finish under 1s reliably?” → yes (e.g. 10/10 local runs ~0.52–0.56s).

Commands used for checking:

```bash
python3 decoder.py
python3 run_tests.py
```

---

## Final repo state (aligned with this reasoning)

| File | Role |
|------|------|
| `decoder.py` | Adaptive concurrent client (shipped solution) |
| `mock_server.py` | Offline API twin |
| `run_tests.py` | Live integration tests |
| `docker-compose.yml` / `start-server.sh` | Official server helpers |
| `README.md` | How to run + strategy |
| `reasoning-log.md` | This reasoning / assumptions log |
