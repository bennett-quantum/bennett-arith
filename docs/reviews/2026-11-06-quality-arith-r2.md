# Arithmetic quality floor — review round 2

Reviewed `main...job/quality-arith`, round-2 fix scope `34eb4fc..e11bc94`;
reviewed head **e11bc944300b3fdd571de890523e397aa570d456**.
`main` was `5cf6e80a817417c4e7ef0c9c697fe6f025e1d405`, merge base
`6764ad25df3b6838e6082712726212796ed453a3`.

**Verdict: CLEAR. No P0/P1 findings.**

- **R1 P1-1 / bennett-arith-awg: fixed.** `scripts/test:13-18` regenerates
  support/constants and relinks the current publication unconditionally;
  `set -e` prevents a failed preparation from reaching the numerical suite.
  Independently reproduced the original case in an isolated head archive at
  `.tmp/rev-quality-arith-r2/tmp/cache-repro`: retain its head `oracle.so`,
  substitute `git show main:dist/llvm18/bennett-arith.bc`, and update the
  manifest bitcode hash and SHA256SUMS. With the pre-fix runner from
  `git show 34eb4fc:scripts/test`, `timeout 180s <fixture>/scripts/test`
  falsely passes **35/35 in 59.47 s**. Change only the runner to reviewed head
  and repeat: **exit 1, two failures, 51.49 s**. Directed
  `tanh_f16_rm(0x54e0,1)` observes `0x3c00` instead of `0x3bff`; zero-low PPC
  FMA parity also fails. The bitcode and stale library were unchanged between
  those invocations. Logs: `stale-before.txt`, `stale-after.txt` and matching
  `.time` files in the review TMPDIR. Independent evidence added to the bead.
- **R1 nit / bennett-arith-hd9: fixed.** The rational oracle docstring now
  identifies 0.2.13 and its total nearest-even midpoint selector.

Verification (headless, review-local TMPDIR/CARGO_TARGET_DIR; Python checks
have no Rust parallelism flags):

- Fresh `git archive` of reviewed head, no generated bridge/support:
  `timeout 180s <fixture>/scripts/test` passed **35/35, 114.71 s wall**
  (68.065 s suite body). The documented **176.90 s cold** result is an honest
  end-to-end measurement, including preparation, rather than a warm-cache or
  suite-only claim. It meets 180 s with only 3.10 s margin; shared-host timing
  varies, so it establishes a measured pass, not a guaranteed runtime bound.
- `timeout 600s python3 -B -I tests/test_default_cache.py`: **2/2 passed,
  149.40 s wall**. These execute real generators/compiler/bridge, mutate the
  publication between runs, verify both changed generators and damaged/missing
  support are refreshed, and require invalid bitcode to stop before the probe.
  The old existence guard would fail both tests; expected tanh bits are literal,
  not computed by the implementation. The exhaustive gate runs these tests.
- `timeout 60s python3 -B -I scripts/quality_metrics.py`: **55 files, no
  regression**. `bash -n scripts/test scripts/gate` and `git diff --check` passed.

Cache-path inspection confirms the remaining default/gate build products are
rebuilt before use; optional offline `--reuse` is absent from the gate, rational
caches are process-local, and sibling resolution still checks the pinned SHA.
No full repository or sibling gate was run; the required critical-batch council
round and merge gate remain with the orchestrator.

P2+ nits: **none**; no new finding beads. Existing awg/hd9 closures verified.

Coverage: closely read all six fix-diff files, default/gate preparation and cache
consumers, regression integrity, timing/coverage descriptions and every anti-slop
rule; skimmed unchanged arithmetic implementations and generated publications.
No narrowing, weakened tests, silent fallback or committed litter introduced.

Provenance: implementer **gpt-6.1-sol**; reviewer **gpt-6.1-sol**, fresh session (D9).
