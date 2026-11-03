# Arithmetic batch review

**Verdict: BLOCK.** Reviewed all 41 commits in `7deb59b71..b5010bb7d828b87380dc4236709bfbed2083abf5`; the latter is the exact reviewed HEAD. No implementation changes.

Contracts read: pinned dialect 0.2.10 §13, the publication's 0.2.12 numerical obligations retained in published 0.2.13 §13, ISA 0.9 at the circuit manifest's `5513d7822edc7cfc54aeda37092bfb3f2fec7581`, and current certificate/borrow clauses. Root version-pin drift is a nit.

| Priority / bead | Location | Confirmed failure; reproduction |
|---|---|---|
| P0 **bennett-arith-8re** | `softfloat/ppc.h:11`, `:24`, `:190`; `softfloat/core.c:254` | FMA of `(1,2^-200) * 1 + 0` returns `(1,0)` instead of the unchanged exact pair. Incoming binary128 `1+2^-110` converts to `(1,0)`, flags16, instead of `(1,2^-110)`, flags0. Both majors; **N**. These concretize the remaining `4yg` fallback gap and do not involve the accepted `4yg.1` tie-parity repair. |
| P0 **bennett-arith-57g** | `softfloat/trans.h:88`, `:200`, `:220` | Upward `exp(-100000)` returns zero instead of least-positive-subnormal; `exp2(-100000)` also loses required flags24. Downward `tanh(256)` returns 1 instead of `0x3fefffffffffffff`. Strict elementary bounds determine each neighbour. Both majors; **N**. |
| P0 **bennett-arith-l95** | `softfloat/trans.h:212`, `:224` | `pow(2,3)`, `log10(10)`, `exp10(1)` return exact 8, 1, 10 but spuriously raise inexact16 instead of flags0. Both majors; **N**. This and the previous finding concretize `wvh`. |
| P0 **bennett-arith-rn8** | `adders/constructions.py:573` | Accepted `mulmod_const(4,31,11)`, input10 → 10 instead of 2: the emitted i8 product wraps 310 to54 before `%11`. **C** executes the unchanged generated oracles without certificate metadata, isolating arithmetic from the separate load failure. |
| P1 **bennett-arith-gdg** | `tests/circuits/test_objects.py:83`; `adders/circuits.py:444` | The publication check removes inverse-pair claims before validation. Raw shipped `arith.bij.addmodk.w4.k5.mb.bisa` fails reference `check` at `inverse_pairs.budget` (string11 versus JSON number); its stripped test view passes. **C**. This confirms a release-validation gap despite existing `vwi`; it does not assign the underlying schema discrepancy to the producer. |
| P1 **bennett-arith-rhn** | `adders/generate.py:110` | `one qrom 1 0 1` parses the single table word as an integer and raises `TypeError: object of type int has no len()`. The supported address-free QROM cannot be expressed through this public CLI. **C**. |

**Reproductions run**, from the repository root with DISPLAY/WAYLAND_DISPLAY/DBUS_SESSION_BUS_ADDRESS/BROWSER unset and job-local TMPDIR/CARGO_TARGET_DIR:

```sh
timeout 180s python3 -I .tmp/rev-arith/setup_bridge.py
timeout 30s python3 -I .tmp/rev-arith/confirmed_numeric.py  # N
timeout 45s python3 -I .tmp/rev-arith/circuit_probe.py      # C
```

All exited 0: N asserts 16 observed disagreements against exact identities/bounds across fresh bridges to the two actual publications; C asserts the three circuit failures. Reference binary SHA-256: `91def6d030d289f58f2966835db55b52c1c7d2d45ed943aafc9795a70a0a2374`. Bitcode and recorded source hashes match both manifests.

Focused checks passed: `softfloat/test_cmps.py` (135,532/major), `tests/test_ppc_exact.py` (25,491/major), `tests/test_compare_closure.py` (15 closures/major), contract/publication audits, and seven selected adder/multiplier/QROM unittest methods. Every test had a timeout; no full gate ran (R3). All P2+ items are consolidated in **bennett-arith-tx4** (`nit`, P3).

**Coverage:** closely read all soft-float numeric sources, wrappers/instantiation, circuit construction/emission/certificates, build/gate scripts and numerical/publication tests; skimmed remaining test details, generated object bodies/manifests, hooks/configuration and administrative documentation. Ordinary bitcode preserves the native/mixed-fat-object route.

**Provenance / R14:** gpt-6.1-sol xhigh review under R14; the orchestrator queues the Claude cross-check of Codex-marked work. Codex markers (`codex job` in messages; these also carry Claude trailers): `de98e29 e9edebb aab308f 4d0147c 5244842 d4e9e9e 4058b05 dbdd10c 5b42dd0 335acd1 f7ff63d 95d70b4 ba74850 bb8a648 2e13940 5e9b450`. Claude-only trailers: `d0db037 d64f797 a02afbc 200d858 d4ac4a5 00dfcc3 2dc607e 7a52334 18858d3 1129cf9 2bb9a27 b5010bb`. The other 13 commits are unmarked; no authorship is inferred.

## Round 2 check (Claude Sonnet 5.5, 2026-11-03T11:40Z)

Scope: sol-arith-softfloat fixes in `a4fa23e..31c110d` for the three numeric P0s. rn8, gdg and rhn are not fixed yet and were not checked. I read the diff of `softfloat/{core.c,ppc.h,ppc_round.h,ppc_sum.h,trans.h,trans_exact.h,generate.py}` and `tests/`, not the commit messages. Dist matches the recorded hash (`c37b7520…`, LLVM18).

- **bennett-arith-8re: RESOLVED.**
  - Evidence: `ppc_round.h:44-83` (`ppc_fma` and `ppc_round`) forms the exact product and sum in 4352 bits at quantum 2^-2148 and rounds once to the adjacent canonical pairs. Incoming conversion (`core.c:255`) keeps the source exponent.
  - It handles cancellation, zero sign, NaN/Inf/invalid, overflow and the subnormal flag.
  - Beyond the repro I ran `.tmp/sonnet-r2check-arith/probe.py` with fresh seeds. It checks FMA on random sparse and dense pairs, exact-cancellation and near-cancellation addends, and f128/f80 incoming conversions near 1+2^-k and across the exponent range, all in 5 rounding modes. Result: 3815 checks on LLVM18 and 18800 on LLVM23, 0 failures.
  - Expected values come from `tests/ppc_exact_oracle.py` (`fma`, `incoming`, `to_pair`). They use Fractions and a canonical-neighbour search, with no call into the C code. The test expectations are not computed by the code under test.
  - Caveat: the oracle's zero-low tie rule is the 0.2.12 interpretation. It replaced the earlier assertion of "unexpected parity ambiguity". This is the already-open 4yg.1 migration, so I am not filing it. The oracle and the C code are only independent on this one point.
- **bennett-arith-57g: RESOLVED.**
  - Evidence: `trans.h:88` (`texp` keeps ±1·2^±100000 instead of returning zero, so final packing sees a strictly positive tail) and `trans.h:203-220` (tanh limit branch).
  - Upward exp, exp2 and exp10 at -100000 give the least positive subnormal with flags 24, and the other modes give 0. My probe `probe2.py` covers 5 modes, 6 formats plus ppcf128, and x from -17 to -65535, wherever the result is below half the least subnormal. Result: 0 failures on both majors.
  - tanh outside the IEEE formats: the finite limit is 1-2^-480 before packing, which lies far inside half an ulp for every IEEE format. Directed modes pick the correct side, in both signs, at x=256 and 1024.
  - ppcf128 tanh at 21 hand-picked x in [256,600] plus 25 random x in [256,512), both signs, 5 modes (`probe3.py`): each compared against an MPFR-2048 interval, with the lower and upper bound required to select the same canonical pair. 460 checks on each major, 0 failures. This includes the 372.5–373 band where the tail crosses half the least PPC quantum.
- **bennett-arith-l95: RESOLVED.**
  - Evidence: `trans_exact.h:50-107` identifies exact dyadic pow, exp2, exp10, log2, log10 and half-integer sincospi results and rounds once. The old `exact` flag chain in `trans.h:246` is now keyed by operation. It also corrects the old always-exact acos(0), atan(inf) and atan2 with infinite arguments, which are now inexact.
  - Reasoning, not just the repro:
    - A square root removes one factor of 2 from the exponent's denominator, so a failed integer root proves the result is not dyadic.
    - A significand wider than 2176 bits cannot be exact in any carrier.
    - The sign and zero rules are IEEE-correct.
  - Probes: exp2(k), exp10(0..3), log10(10^k), log2(2^k) and pow with exact integer, half and quarter exponents, negative bases, odd and even powers, on all 6 formats plus ppcf128, 5 modes, flags 0 required (`probe2.py`). 1485 checks on each major, 0 failures. The inexact neighbours still raise 16 in the review's own checks.
  - I found no special-casing of the repro.

**Re-run:**
- `timeout 600 python3 -u -I tests/test_extended.py 18 23`: exit 0. Each major shows 527 original boundary/signature checks and 2718 review checks.
- `timeout 900 python3 -u -I tests/test_ppc.py 18 23`: exit 0. Each major shows 792786 PPC component/exact-value checks, 25491 exact-sum conversion/integral/integer/sqrt checks and 15 comparison closures.

Expected values in `tests/test_review_numeric.py` come from the independent Python encoder, the Fraction oracle and MPFR (ctypes). The tests were not weakened, skipped or replaced by tolerance. The only oracle relaxation is the zero-low tie assertion described above.

**New P0/P1: none. Beads filed: none.**

**Verdict: CLEAR for 8re, 57g and l95.** The overall batch stays BLOCK until rn8, gdg and rhn are fixed and checked.

## Claude cross-check of Codex-authored commits (Sonnet 5.5, 2026-11-03T12:32Z)

**Commits covered:** the 16 Codex-tagged commits `de98e29 e9edebb aab308f 4d0147c 5244842 d4e9e9e 4058b05 dbdd10c 5b42dd0 335acd1 f7ff63d 95d70b4 ba74850 bb8a648 2e13940 5e9b450`. All are soft-float/publication/bead changes; none touches `adders/`, so the circuit-construction risks are out of this set. I read the HEAD (`d8472a2`) form of every file they touch: `softfloat/{core.c,ppc.h,ppc_round.h,ppc_sum.h,trans.h,trans_exact.h,named.c,instantiate.py,generate.py}`, the dist manifests and the tests. I did not re-report sol's rows or the Round 2 section.

**Publication digests: clean.** `sha256sum -c dist/llvm{18,23}/SHA256SUMS` OK; every `manifest.sources` sha256 equals the working-tree file; `tests/build_stage.py` rebuilds both majors byte-identical to the published bitcode (`c37b7520…` LLVM 18, `dfe0da8e…` LLVM 23). The manifest's `numerical_accuracy` block says "deterministic approximation; no global correct-rounding or ulp-bound proof" and names `wvh`, so the open accuracy gap is honestly labelled. The findings below are concrete violations inside that umbrella, in the same way sol's 57g/l95 were.

**Method.** An independent oracle for each new finding: `.tmp/sonnet-xcheck-arith/probe_trans.py`, `probe2.py` and `probe3.py` call the published `_rm` entry points and compare with the correct rounding of an MPFR (6000-bit) lower/upper bracket, with the repo's Fraction encoder only for the final rounding. Cases where the bracket does not decide a mode are skipped (`inconclusive`). The named-format check uses LLVM 23 `APFloat::convert` as the oracle (`.tmp/sonnet-xcheck-arith/apf/`).

### New P0/P1

| Priority / bead | Location | Failure and reproduction |
|---|---|---|
| P0 **bennett-arith-ufr** | `softfloat/trans.h:202` (limit branch only for `\|x\|>=256`), `:241-242` | Directed `tanh_<fmt>_rm` for 78<=\|x\|<256 returns exactly 1.0: the 224-bit quotient has no room for the 2e^(-2\|x\|) tail. `tanh_f64_rm(100.0, down)` gives `0x3ff0000000000000`, correct `0x3fefffffffffffff`. Also x=80 and 255 (f64), 161 (f32, want `0x3f7fffff`), 136 (f16, want `0x3bff`); negative x mirrored. This is the 57g defect one range over; Round 2 called 57g CLEAR on the `>=256` branch only. `timeout 100 python3 -I .tmp/sonnet-xcheck-arith/repro2.py 18` (also 23); `probe2.py 23 5 0`: 120 failures, all tanh, all 6 IEEE formats. **N** |
| P0 **bennett-arith-8eb** | `softfloat/trans.h:221-222` (tan = s/c), `:225-230` (asin via `tatan2`), `:237-240` (tanh series) | For tiny \|x\| (about < 2^-112, so every f64/f80/f128 subnormal and a large normal range) the quotient of two independently jammed 224-bit values lands on the wrong side of x: `tan_f64_rm(2^-169, up)` returns x (want succ x); `tanh_f64_rm(2^-169, down)` returns x (want pred x); `asin_f128_rm(2^-300, down)` returns pred x (true asin > x, want x). `timeout 100 python3 -I .tmp/sonnet-xcheck-arith/repro_tiny.py` and `timeout 110 python3 -I -u .tmp/sonnet-xcheck-arith/probe3.py 23 11 12`: 39/90/156 failures on f64/f80/f128, only tan, asin, tanh (sin, cos, atan, sinh, cosh, exp*, log*, pow, atan2 pass); LLVM 18 repro identical. **N** |
| P1 **bennett-arith-yuk** | `softfloat/named.c:41-62`; `softfloat/test_instances.py` `expected_to` (commit `de98e29`) | `named_pack` decides overflow from the unbounded-exponent rounding whatever the mode, then returns inf (IEEE-like) or 0 bits. IEEE/APFloat directed rounding saturates to the largest finite value. f32 1e10 -> Float8E5M2 rm=toward-zero: APFloat 23 `0x7b`, ours `0x7c` (rm=down too; -1e10 up/zero `0xfb` vs `0xfc`); Float8E4M3 `0x77` vs `0x78`, Float8E3M4 `0x6f` vs `0x70`; E4M3FN rm=zero on f32 `0x43fffffe` gives APFloat `0x7e`, ours `0`. Over 2333 f32 inputs x 5 modes the directed-mode mismatches are 429/366/795 (E5M2 down/up/zero). The test cannot fail: `expected_to` hardcodes inf for every rm, i.e. the expectation mirrors the implementation. `convert_from` agrees with APFloat on all 2192 codes (NaN payloads aside). Command: `cd .tmp/sonnet-xcheck-arith/apf && ./cmp < inputs.txt > apf.out; ./mine < inputs.txt > mine.out` then diff (sources `cmp.cpp`, `mine.c`). **C** |

Provenance: ufr and 8eb are in the generic transcendental path introduced before the Codex commits (`bb79deb`); the Codex lines `bb8a648`/`2e13940` and the 57g repair leave them untouched or adjacent. They are reported because the batch review and Round 2 missed them in the reviewed range, and tests/test_trans*.py assert only `<=4 ulp` for `_rm`, so these 13.4 side/correct-rounding failures cannot fail them. yuk is in a Codex-authored commit proper.

### Checked and found clean
Round-2 areas are not repeated. Additionally no mismatch against the MPFR bracket for: all five modes of sin, cos, atan, sinh, cosh, exp, exp2, exp10, log, log2, log10, atan2, pow at tiny +/- x, log and asin/acos near 1, exp/sinh/cosh around the overflow threshold, sin/cos/tan at large arguments (10^k), on the six IEEE formats, 10,000+ checks per major, flags included. The `named.c` rounding (non-directed) and `convert_from` agree with APFloat 23. PPC integral/sqrt/convert/FMA paths are covered by independent Fraction oracles whose expected values do not call the code under test (read, not re-derived).

### P2 and below (one nit bead, bennett-arith-9ss)
Tracked `tests/__pycache__/*.pyc` (f7ff63d); `_rm` tests accept 4 ulp; named non-saturating nearest-mode overflow (zero bits vs APFloat NaN/max) needs a LangRef reading (unconfirmed, not filed as a defect); `pack()` tininess reads the accumulated flags word (`core.c:95`; unconfirmed, no repro); non-descriptive `wip(codex job ...)` subjects.

**Verdict: ADDS-BLOCKERS** (new P0: ufr, 8eb; new P1: yuk). Round 2 stays valid for 8re, 57g and l95 as scoped, but 57g's tanh claim is only true for `|x|>=256`.
