# Current state — soft-float v2

Updated 2026-11-01T13:45:50Z (real `date -u`). Accepted dialect 0.2.10
@023f5a771a814270634db3be9cfde88ded69f975, ISA 0.8. No push.

LLVM 18 and 23 each publish **1,134 integer-only carrier exports**, preserving
all 606 previous signatures and adding 528. All 1,008 previously inventoried
concrete entries now have definitions; no staged concrete placeholder remains.
Includes PPCDoubleDouble scalar/wide arithmetic, all cross-format routes,
all seven own-format libm families (ordinary and `_rm`), and powi at ten widths
1/8/16/32/64/128/192/256/513/1025. Additional exact iK definitions are generated
with `scripts/build MAJOR K ...`; LLVM's inclusive i8388608 limit is verified.
Custom i7 bitcode executed 2^3=8; default publications were restored.

## Binary edge and consumer action

- LLVM 18 `dist/llvm18/bennett-arith.bc` SHA-256:
  `8d99956e8741803f2115e48fa28c6c71795fb0041e992f8835851b71dd4b6fc1`
- LLVM 23 `dist/llvm23/bennett-arith.bc` SHA-256:
  `59563a3a10949b1ea48ca8b79027310ac9f9f7e28c85a30e70a013ced04a6793`

Same-directory manifests record every literal signature, bitcode digest,
tool versions and SHA-256/Git blob SHA-1 of implementation/build sources;
SHA256SUMS also hashes the manifest. Link the matching-major artifact with
program/runtimes **before normalisation**, then materialise its reachable
closure in both builds. `_rm` wrappers use runtime-owned external
`__bennett_rt_fenv` (`{ i32 round, i32 flags }`). No host FP/libm dependency.
The tested layout remains x86_64 Linux, 64-bit little endian.

**bennett-plugin must re-pin BENNETT_ARITH_BITCODE SHAs**, then verify its own
L/CC closure and decide bp-xms/bp-7ni disposition. The plugin was read-only.
Its tables/probes and softfloat receipt were inspected; arith does not claim
that new producer exports alone close the consumer's complete blocker.

## Semantics and remaining contracts

§13.1/13.3 PPC uses the LLVM-major APFloat interpretation: component add/mul;
legacy 106-bit divide/fmod/FMA and conversions where LLVM uses that fallback;
LLVM23 component integral/integer conversion differs from LLVM18. Sparse wide
integers, classification, modf and combined subnormal ldexp are tested.
PPC-to-IEEE APFloat conversion uses only the high component, contradicting
“fpext is exact”; special sign/status behavior and LLVM23 unsigned negative-low
saturation are retained. APFloat lacks PPC sqrt: its implementation uses a
correctly rounded legacy 106-bit result. Both readings and priority questions
are in **b-dialect-spec-dfd**. This is not idealized IEEE double-double arithmetic.

§13.4 explicitly waives correct rounding and gives no error bound. Libm v1 uses
224 working significant bits and 17,408-bit Payne–Hanek constants, entirely in
integer bitcode. Ordinary MPFR sweeps report a maximum of 0.5 ulp (rounded
reporting); tests allow <=4 ulp, exhaustive half/bfloat sin <=1 ulp. This is
empirical evidence, not a global correct-rounding/ulp-bound proof. Accuracy and
§13.5 approximation flag policy questions are **b-dialect-spec-1av**.

Closed: **r3d**, **0he**, and one libm bead per format (**0he.1–0he.7**).
Still blocked, full capability retained: **38c** (metadata-named arbitrary
APFloat schema; dialect **z7u**) and **chn** (distinct signaling constrained
comparison ABI; dialect **21a**). No spec text was edited; only exported
`.beads/issues.jsonl` was committed in that repo. No full DF/runtime claim.

## Verification

`scripts/gate` reproduces both publications and exercises the actual bitcode:

| Checks | LLVM 18 | LLVM 23 |
|---|---:|---:|
| Original numerical regression, 606 prior exports | 1,029,583 | 1,029,583 |
| Same-major PPC/APFloat | 792,786 | 792,786 |
| Additional boundary/signatures | 519 | 526 |
| Width-preserving powi | 3,668 | 3,668 |
| MPFR/pair main sweep | 130,464 | 130,464 |
| Exhaustive sin/PPC/libm rounding | 137,860 | 137,860 |
| Subnormal-output/overflow sweep | 14,655 | 14,655 |
| **Total numerical checks** | **2,109,535** | **2,109,542** |

Also checks integer-only linked closure, all literal signatures, every half and
bfloat sin encoding (65,536 each), every PPC predicate, NaNs/zeros, sparse
2^1023+1 integer transport, f128 precision/range extremes, log just below 1,
pi-adjacent arguments, all rounding modes and sticky flags. MPFR is test-only
at 384 bits; APFloat oracle uses the installed same-major LLVM development
library. The max-width powi test is structural assembly/verification.

Root gate plus the new boundary sweep passed. Final source at 7826a10 reproduced
bitcode, manifests and checksums exactly from a separate archived directory;
default bitcode is byte-identical to bb79deb. Clean detached pre-push gate exited 0 on
bb79deb44bea7f727717b3a9ddd59cd0ca3c75a8; its identical numerical bitcode passed the entire table
above. The max-width validation fix was verified separately and changed only
manifest provenance. Final-source relocated reproduction also passed. The
temporary pre-push worktree was removed; no push occurred.
See `docs/verification.json` for the committed evidence and added export names.
Superseded/red/interrupted attempts are not green receipts. No CI, push, Dolt
sync, desktop process or system /tmp artifact was used.
