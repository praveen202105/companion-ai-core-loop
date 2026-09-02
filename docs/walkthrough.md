# Assessment walkthrough (15–20 minutes)

## 0:00–2:00 — Frame the problem

Explain that the core risk is not merely forgetting. A companion can retrieve stale information,
contradict its own identity, or become less consistent as history grows. State the three invariants:
durable memory, one active current truth per canonical fact, and a versioned companion persona.

## 2:00–5:00 — Show the model and schema

Open Mira's versioned YAML, the memory domain model, and the initial migration. Point out owner,
type, canonical key, confidence, importance, temporal validity, source message, supersession link,
access statistics, and embedding. Show the partial unique index and append-only event table.

## 5:00–8:00 — Run the core demo

```bash
make demo
```

The script stores a name and location, changes Pune to Bengaluru, asks for the current location, and
prints the retrieval trace. Highlight that Pune remains in audit history but cannot be retrieved.

Then demonstrate restart persistence manually:

```bash
uv run --package companion-ai-api companion chat -m "My name is Praveen"
uv run --package companion-ai-api companion memory list
uv run --package companion-ai-api companion chat -m "What is my name?"
```

## 8:00–11:00 — Explain retrieval

Show the FTS5 and vector candidate paths, Reciprocal Rank Fusion, type-specific decay, and top-six
cap. Run:

```bash
uv run --package companion-ai-api companion explain-last-turn
```

Emphasize that the output contains auditable score factors—not chain-of-thought—and the full memory
store never enters the prompt.

## 11:00–14:00 — Show persona defense

Open the persona checker tests. Walk through a draft claiming Mira lives in Mumbai, the one repair
pass back to canonical Bengaluru, and the safe fallback when a second contradiction remains. Show
that only consistent assistant self-claims are persisted.

## 14:00–17:00 — Run evaluation

```bash
make eval
```

Open the committed report. Discuss restart persistence, targeted recall among 24 distractors,
relationship supersession, preference correction, relocation, and 52 turns of persona pressure.
Call out the `null` tone score: subjective evaluation is intentionally withheld without a separate
live judge run.

## 17:00–20:00 — Tradeoffs and production path

Explain why the custom memory engine is primary and Mem0 is deferred. Close by showing the
implemented production extension: FastAPI/SSE, PostgreSQL/pgvector, Redis rate limits and locks, an
HttpOnly-cookie Next.js BFF, passcode protection, retention cleanup, and the staging-first
Vercel/Railway runbook.
