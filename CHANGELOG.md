# Changelog — idempotency-key-spec

## v0.1.1 — 2026-10-12

- Fixed: conformance factory now receives injected `clock`/`ttl` kwargs
  (R8/R9 use a controllable clock); previously time-based rules could not run
  hermetically against adapters with default real-time clocks.
- Fixed: CLI `--adapter` loading reports a precise error when the module
  imports but the class is missing, and when the spec string has no `:` separator.
- Self-review round: test suite grew 50 → 55 cases (added broken-adapter CLI
  path, boundary key lengths 255/256, purge idempotency, huge/zero TTL edges,
  unicode payload fingerprints).

## v0.1.0 — 2026-10-11

- Initial cut (session-interrupted build): normative rules R1-R12 in the
  module docstring, adapter contract (begin/complete/lookup/purge with
  injectable clock+ttl), `run_conformance` harness, CLI `conformance`
  subcommand with per-rule PASS/FAIL output, reference InMemoryAdapter,
  50 self-test cases.
