# Arithmetic quality floor — review round 1

Reviewed `main...job/quality-arith`, closely `199a827..7bf03b82bcb4b9517994b147096018a90da2f871`;
reviewed head **7bf03b82bcb4b9517994b147096018a90da2f871**.

**Verdict: BLOCK.** No P0; one P1.

- **P1-1 — bennett-arith-awg — `scripts/test:9-17`: stale bridge gives a false green.**
  The default runner rebuilds `.tmp/llvm18/oracle.so` only when absent. After a
  publication changes, numerical tests can keep executing the previous library;
  neither the current bitcode hash nor generator/bridge identity invalidates it.
  Confirmed in an isolated `git archive HEAD` fixture under
  `.tmp/rev-quality-arith-r1/tmp/cache-repro`: retain the head's cached oracle and
  constants, replace LLVM18 publication bitcode with `git show main:dist/llvm18/bennett-arith.bc`,
  and update its manifest/SHA256SUMS hashes to match. `timeout 180s <fixture>/scripts/test`
  passes **35/35** (58.694 s), despite the known-buggy publication. Move only the
  fixture's `oracle.so` aside and repeat: **exit 1, two failures** (27.696 s):
  `tanh_f16_rm(0x54e0,1)` returns `0x3c00`, expected `0x3bff`, and zero-low PPC FMA
  parity fails. Logs: `cache-repro-warm.txt` / `cache-repro-cold.txt` in that same
  job TMPDIR. Content-key or rebuild the cached bridge/support files, with a
  regression that changes the publication between default runs. The full gate's
  rebuild does not repair the separately advertised default command.

P2+ nits: **bennett-arith-hd9** — `tests/ppc_exact_oracle.py:1-4` still describes
0.2.12 and disclaims midpoint selection although `to_pair` now implements 0.2.13's total selector.

Verification (headless, job-local TMPDIR; Python checks do not use Rust parallelism flags):

- `timeout 180s scripts/test`: 35 passed, 20.018 s test body.
- `timeout 300s python3 -B -I tests/test_directed.py 18 23`: 18,810 exact checks per major.
- `timeout 300s python3 -B -I tests/test_trans.py 18`: 130,464 passed.
- `timeout 300s python3 -B -I tests/test_trans_extra.py 18`: 132,640 plus 24,978 sparse-PPC exp checks passed.
- `timeout 90s python3 -B -I tests/test_trans_boundaries.py 18`: 14,655 passed.
- Focused oversized-constant, pinned diagnostic-view, publication, LLVM23 parity and quality-ratchet checks passed.
  Independently compiled `0928081`/head C cores compared 17,290 result/flag tuples byte-identically
  (`timeout 120s python3 -B -I -`); a freshly linked LLVM18 bridge matched the existing cache byte-for-byte.
  Main-side inspection and the cold fixture confirm the new regressions detect the old rounding defects.
- Explicit promised raw modular validation and a sparse-PPC directed-tan witness remain red as documented;
  these existing obligations stay under their named switch/beads. No full repository or sibling gate run.

Coverage: closely read all hand-written changes, oracle/test integrity, exact-case table and phase split,
all anti-slop rules, quality baseline/gate check and HANDOFF retirement; read `main..199a827` for interactions;
skimmed regenerated certificate/manifest repetitions and publication hashes. No narrowing found.

Provenance: implementer **gpt-6.1-sol**; reviewer **gpt-6.1-sol**, fresh session (D9).
