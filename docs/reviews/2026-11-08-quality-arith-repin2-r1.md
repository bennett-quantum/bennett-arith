# Quality arith re-pin 2, review round 1

Verdict: **BLOCK** — P0-1 (`bennett-arith-phx`); no P1 findings.

Reviewed head: `d062ed3f2c45c6e3d79571967045f62551f17803`, branch `job/quality-arith`.
Range inventoried: `main..job/quality-arith` / `main...job/quality-arith`;
close review limited to `015b424..d062ed3` (24 files), including the
`cf4af47..d062ed3` pin work and R40 changes through `e40397d..d062ed3`.
Earlier reviewed commits were consulted only for changed paths and red-first comparison.

**P0-1 — rung 1, incorrect scalar transcendental result through paired entry point.**
`softfloat/trans.h:193` adds a tiny-argument correction table for `SIN` but omits
`SINCOS`; consequently `:232` leaves the paired call on the old approximation
path at `:249`. At `x=2^-700`, both published LLVM 18/23
`__bennett_sf_sincos_ppcf128_rm` implementations return sine
`(2^-700,-2^-940)` in all five modes. Independent directed MPFR brackets and
the repaired scalar `sin` return `(2^-700,+0)` for modes 0/2/4 and
`(2^-700,-2^-1074)` for modes 1/3. The error is roughly `2^134` local ulps;
pinned dialect 0.2.13 §13.4 explicitly applies its bound to each paired field.
The new family at `tests/test_directed.py:20` exercises six scalar operations
and misses this public entry point of the same repaired bug class.
Run: `timeout 30s python3 -B -I .tmp/rev-quality-arith-repin2-r1/test_sincos_tiny.py`:
exit 1, **10/10 subtests fail**, after scalar-sin controls pass. Fresh bridges
were linked directly to each head publication with its matching clang;
transcript: `.tmp/rev-quality-arith-repin2-r1/sincos-red.log`.
Bead: **bennett-arith-phx** (priority 0, `review`).

P2+ nits: **bennett-arith-1jj** (priority 3, `review`) — the shared hang guard
still becomes a unittest error in diagnostic-only admission/replay
(`tests/circuits/harness.py:278`, `tests/circuits/test_objects.py:169`);
`timeout 30s python3 -B -I .tmp/rev-quality-arith-repin2-r1/check_diagnostic_guard.py`
deterministically confirms it. This harness issue does not block.

Other verification: `timeout 180s python3 -B -I .tmp/rev-quality-arith-repin2-r1/check_receipts.py`
passed: reconciled all 129 stored publication hashes and all 221 claim identities
against the full-run transcript, including 37 structural proofs; four small raw
publications replayed successfully at ISA `62a0cf0`; mutated `0+0=1` rejected at K13.
`timeout 60s python3 -B -I tests/circuits/test_objects.py Published.test_receipt_guards Published.test_token_aliases`
passed (2 tests); `timeout 60s python3 -B .tmp/quality-arith/guard-regression.py`
passed (4 tests, including mocked 129-entry UNKNOWN/FAILED reporting).
`timeout 60s python3 -B -I tests/test_contract.py` passed for both publications.
`timeout 120s python3 -B -I tests/circuits/test_objects.py Published.test_manifest_is_current`
passed. The focused `timeout 240s python3 -B -I .tmp/rev-quality-arith-repin2-r1/check_numeric.py`
completed 43,030 scalar tiny-family checks on LLVM 18, then hit the reviewer's
outer limit during LLVM 23 (exit 124; that sweep remains incomplete).
No full publication test, gate, or quality-gate command was run.

Coverage: read closely all changed executable source/tests, K94 and dialect §13.4,
six certificate subject-only changes, receipt/verdict handling and measured guard
citations; skimmed documentation and distribution metadata, with independent hash
checks. Anti-slop rules checked; P0-1 is the substantive missing dispatch case.
Plan items 9–11 checked: ratchet present in `gate.toml`, baseline unchanged since
`015b424`, local HANDOFF retired and README points to the ecosystem handoff.

Provenance: implementer **gpt-6.1-sol**; reviewer **gpt-6.1-sol**, fresh session (D9).
