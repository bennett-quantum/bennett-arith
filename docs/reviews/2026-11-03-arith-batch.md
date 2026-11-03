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
