# Alignment Audit (Rules 85-100 / 16 items) — idempotency-key-spec v0.1.1

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | Safety/Ethics section | N/A | Not a security-research repo; no dual-use surface. Fails closed (exit 2) on unreadable adapters/spec violations exit 1 |
| 2 | Privacy/dezero | PASS | No secrets/tokens/real names; no contact line needed; grep `(sk-\|ghp_\|api[_-]?key\s*=\s*['"][A-Za-z0-9])` → 0 hits |
| 3 | Copyright boundary | PASS | Anchors (go-rocket-ride, ietf-wg-httpapi/idempotency, IdempotentAPI) restated structurally (implementation vs spec layer, wire protocol vs state machine, ASP.NET binding), no >50-char copied text; MIT LICENSE present, "zhengming contributors" |
| 4 | Fact-check annotation | PASS | Quickstart ~2 s marked [Measured] with repro `python self_test.py`; big-payload fingerprint <2 s [Measured in c10]; rule-coverage claims qualitative |
| 5 | Confidence grading | PASS | Spec/implementation match [High ≥80%]; rule sufficiency [Medium]; vendor-match [Low]; visible in Confidence section |
| 6 | PLAN B built-in | PASS | "Minimal Fallback (PLAN B)": manual R1-R12 review checklist focused on R3/R8/R12 |
| 7 | Timeout preset | PASS | Quickstart states "~2 s" total with per-step ≈0.5 s / ≈1 s markers |
| 8 | Rule-conflict arbitration | PASS | "Design Trade-offs" opens with priority order: spec clarity > harness hermeticity > breadth of covered semantics > adapter ergonomics |
| 9 | Version changelog | PASS | CHANGELOG.md v0.1.0 + v0.1.1; v0.1.1 lists clock-injection fix, CLI error-surface fixes, test delta 50→55 |
| 10 | Exemption instruction | N/A | Session-level rule; static repo content not applicable |
| 11 | External-knowledge cutoff | PASS | IETF draft referenced conceptually (header field, conflict/replay semantics) without version-pinned claims; anchors restated from 2026-10 candidate pool snapshot |
| 12 | Assumption explicitness | PASS | "[Core Assumptions]" section with 4 items (state machine pinning, controllable clock, first-write-wins policy, fingerprint scope) |
| 13 | Logic-check trio | PASS | self_test.py tiers: [A] functional (20), [B] exception/CLI paths (20), [C] extreme edges (15: TTL 0/1e18/frozen clock, 255/256 boundary, 0x20/0x7E key edges, 1MB payload timing, 200 keys, purge idempotency). Final run: `python self_test.py` → `SUMMARY: PASS 55/55` |
| 14 | Socratic question | PASS | FAQ "When NOT to use this tool?" with 4 concrete anti-use-cases (need implementation, need concurrency testing, need HTTP conformance, want middleware) |
| 15 | Pareto improvement | PASS | v0.1.1: test count 50→55 (+10%) plus 2 correctness fixes (clock injection for R8/R9, precise adapter-load errors); documented in CHANGELOG, suite re-run green |
| 16 | Ultimate fallback (≤60-word opener) | PASS | First paragraph = 59 words, contains what/who-needs-it judgment sentence |

Second-order effects (rule 16 bonus): PASS — "Limits & Second-order Effects" lists green-run-as-certification overreach, sequential-semantics blindness, and operational-failure invisibility.

Scan evidence: `grep -rEn "(sk-\|ghp_\|api[_-]?key\s*=\s*['\"][A-Za-z0-9])" .` → 0 hits; `python self_test.py` → `SUMMARY: PASS 55/55`.
