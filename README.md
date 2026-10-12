# idempotency-key-spec

idempotency-key-spec is a formal rule set (R1–R12) for idempotency-key semantics — key validity, fingerprint conflicts, replay, expiry — plus a stdlib-only conformance harness that runs any adapter against those rules and prints a per-rule PASS/FAIL verdict. Use it when you implement idempotent writes and want to *prove* your state layer obeys the contract, not just hope it does.

## Problem

Idempotency keys look simple and fail subtly: the same key replayed mid-flight, a different payload under a used key, a record that expires mid-retry, a double-complete that overwrites the stored result. Implementation libraries abound, but each bakes in private semantics, and teams discover the differences in production. The gap is at the *specification* layer: a written, testable contract that any implementation can be checked against.

## How it works

1. **The rules (R1–R12, normative text in the module docstring and README)** — `begin(key, fingerprint)` returns `FIRST`/`REPLAY`/`CONFLICT`; `complete` stores result or error and is idempotent (first write wins); keys are 1–255 printable-ASCII chars; fingerprints are sha256 over `METHOD path\npayload`; records expire after a TTL and then behave as unseen.
2. **The adapter contract** — your implementation exposes `begin`, `complete`, `lookup`, `purge` and accepts an injectable `clock` and `ttl`. Nothing else is required: no HTTP, no storage choice, no framework.
3. **The harness** — `run_conformance(factory)` executes R1–R12 with a controllable clock and returns per-rule `{rule, ok, detail}`. The CLI loads your adapter class from `file.py:ClassName` and exits `1` on any rule failure. A reference `demo_adapter.py` (in-memory) passes 12/12.

## Quickstart

Measured on a laptop, Python 3.10: total **~2 s**.

```bash
# ~0.5 s: prove the reference adapter obeys all 12 rules
python idempotency_spec.py conformance --adapter demo_adapter.py:InMemoryAdapter

# ~0.5 s: run your own adapter
python idempotency_spec.py conformance --adapter my_store.py:MyAdapter

# ~1 s: self-test (55 cases, includes a deliberately broken adapter that must fail)
python self_test.py
```

## Why not X

- **[rafael-piovesan/go-rocket-ride](https://github.com/rafael-piovesan/go-rocket-ride)** — a toy API implementing idempotency keys in Go with clean architecture. It is an *implementation* in a fixed stack; this repo is the layer above: rules any Go/.NET/Python implementation can be conformance-tested against.
- **[ietf-wg-httpapi/idempotency](https://github.com/ietf-wg-httpapi/idempotency)** — the IETF working-group draft for the Idempotency-Key HTTP header field. It standardizes the wire protocol (header, fingerprint, `425`/`409` semantics) but ships no executable conformance suite; this repo turns the core state semantics into runnable checks for your storage layer.
- **[ikyriak/IdempotentAPI](https://github.com/ikyriak/IdempotentAPI)** — a .NET library making POST/PATCH writes idempotent via attributes and caching. Again an implementation, bound to ASP.NET Core; the spec here is deliberately implementation-free and language-agnostic.

## Minimal Fallback (PLAN B)

Can't run the harness? Paste the R1–R12 list from the module docstring into a code review and hand-check your implementation against each rule — especially R3 (fingerprint conflict), R8 (expiry restart), and R12 (first-write-wins). Those three rules cause most real-world idempotency bugs; a manual checklist catches roughly the same class of defects at zero setup cost.

## Design Trade-offs

Priority order: **spec clarity > harness hermeticity (fresh adapter per rule) > breadth of covered semantics > adapter ergonomics.** The contract is intentionally small (four methods, injectable clock) — rich adapters (sharded stores, distributed locks) map onto it, but the suite cannot see partition behavior: conformance here is single-process, sequential semantics only. Expiry is checked lazily on access and eagerly in `purge`, matching both read-path and janitor styles.

## Limits & Second-order Effects

- No concurrency: two simultaneous `begin`s on one key are untestable in-process; adapters still need atomicity guarantees the suite cannot check.
- HTTP-layer rules from the IETF draft (header casing, error status codes) are out of scope; this spec stops at the state machine.
- A passing adapter can still misbehave operationally (unbounded memory, clock skew across nodes) — the suite checks semantics, not ops.
- Teams may treat a green conformance run as certification of *all* idempotency concerns; it covers exactly R1–R12, no more.

## FAQ

**Is this an idempotency library?** No — `demo_adapter.py` is a reference, not a product. The deliverable is the rule set plus the checker.

**Does it match the IETF draft exactly?** It reuses the core concepts (key, fingerprint, conflict, replay) as testable state-machine rules; wire-level details are out of scope.

**Can I test a Redis/Postgres adapter?** Yes — implement the four methods, inject a fake clock, run the CLI. Storage is your choice.

**When NOT to use this tool?** (1) You just need working idempotency in .NET or Go — use IdempotentAPI or go-rocket-ride-style patterns directly. (2) You need distributed-concurrency guarantees tested — this harness is sequential. (3) You need HTTP protocol conformance — test against the IETF draft's own materials. (4) You want a drop-in middleware — nothing here is middleware.

## [Core Assumptions]

1. Idempotency semantics can be pinned down as a finite state machine (PENDING/DONE/expired) observable through four methods.
2. A controllable clock is available to the adapter; real-time testing of TTLs is neither required nor reliable.
3. "First write wins" (R12) is the correct double-complete policy; implementations that last-write-win are non-conformant by definition.
4. Fingerprints cover method, path, and payload; header-based fingerprint variations are adapter extensions outside the spec.

## Confidence

That the reference adapter and rule implementations match the written R1–R12 text: **High (≥80%)** — covered by 55 self-test cases including a deliberately broken adapter. That the 12 rules capture "enough" of idempotency for production systems: **Medium** — concurrency and clock-skew classes are explicitly uncovered. That the rule set matches any particular vendor's semantics: **Low** — vendors differ; that is the point of having a spec.

*as of 2026-10-12*

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 55 purpose-built AI-engineering tools across neglected niches.

Related tools: [timezone-safety-check](https://github.com/chenhz01/timezone-safety-check) · [calendar-conflict-check](https://github.com/chenhz01/calendar-conflict-check) · [claim-verification-chain](https://github.com/chenhz01/claim-verification-chain)
