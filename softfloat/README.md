# Soft-float binary edge

The driver links `dist/llvm<major>/bennett-arith.bc` with the program and the
same-major `bennett-runtimes` bitcode, **before** normalisation/materialisation.
Use `/usr/lib/llvm-18/bin/llvm-link` or `/usr/lib/llvm-23/bin/llvm-link` as
appropriate. Both the device and native comparison builds must use that same
linked, materialised closure. Do not compile the C source in the consumer or
substitute host libc/libm. The plugin consumes this binary edge only.

Each distribution includes `manifest.json` (all exported names, literal LLVM
signatures, formats, semantic status, and spec section), `staged_exports` (required
concrete signatures awaiting mechanics, each linked to a bead), three parametric
families and `SHA256SUMS` for the bitcode and manifest. The manifest is the complete
machine-readable entry-point list. Public wrappers use the dialect's LLVM carrier
ABI, not C's aggregate/sret ABI for `_BitInt(80)` or `_BitInt(128)`.

## Implemented

For `B = f16, bf16, f32, f64, f80, f128, ppcf128`, the carriers are
`i16, i16, i32, i64, i80, i128, i128`. IEEE claims below apply to the first six;
PPC follows the major-specific APFloat rules described below:

| Name after `__bennett_sf_` | Literal signature | Contract |
|---|---|---|
| `{add,sub,mul,div,rem}_B` | `C (C, C)` | correctly rounded; rem is exact fmod |
| `cmp_B` | `i1 (C, C, i32)` | all 16 LLVM predicates |
| `cmps_B_rm` | `i1 (C, C, i32 P, i32 R)` | signaling comparison, P = 0..15 and R = 0 |
| `{fptosi,fptoui,lround,llround,lrint,llrint}_B` | `i128 (C, i32 M)` | saturated, NaN → 0, signed/unsigned extension |
| `{sitofp,uitofp}_B` | `C (i128)` | correct rounding of exact integer |
| `{fpext,fptrunc}_S_D` | `C_D (C_S)` | exact extension; correctly rounded truncation |
| `{sqrt,floor,ceil,trunc,round,roundeven,rint,nearbyint,canonicalize}_B` | `C (C)` | §13.1, signed zeros and canonical arithmetic NaNs |
| `{minnum,maxnum,minimum,maximum,minimumnum,maximumnum}_B` | `C (C, C)` | §13.1 NaN selection; −0 < +0 |
| `fma_B` | `C (C, C, C)` | one rounding, never mul then add |
| `isfpclass_B` | `i1 (C, i32)` | ten bit-pattern classes |
| `ldexp_B` | `C (C, i32)` | exact scaling, correctly rounded subnormal result |
| `frexp_B` | `{ C, i32 } (C)` | exact fraction and exponent |
| `modf_B` | `{ C, C } (C)` | fractional, integral field order |
| `powi_B_iK` | `C (C, iK)` | deterministic repeated squaring with per-step format rounding; signed exponent retained |
| `{sin,cos,tan,asin,acos,atan,sinh,cosh,tanh,exp,exp2,exp10,log,log2,log10}_B` | `C (C)` | deterministic own-format integer libm; no correct-rounding claim |
| `{atan2,pow}_B` | `C (C, C)` | own-format libm, operand order retained |
| `{sincos,sincospi}_B` | `{ C, C } (C)` | sin then cos; sinpi then cospi |
| `{fptosi,fptoui,lround,llround,lrint,llrint}_B_wide` | `void (ptr, C, i32 M)` | exact saturated M-bit little-endian limb result |
| `{sitofp,uitofp}_B_wide` | `C (ptr, i32 M)` | correctly rounded from all M bits |

`_rm` variants of arithmetic, quiet/signaling comparison, conversion (including `_wide`), sqrt, integer
rounding, min/max and ldexp append `i32 R`. Modes 0–4 are nearest/even, downward,
upward, toward zero, nearest/away. They OR invalid=1, divbyzero=2, overflow=4,
underflow=8, inexact=16 into `__bennett_rt_fenv.flags`; ordinary entry points do
not access the environment. Tininess is detected after rounding. Non-saturating
and .sat FP-to-integer operations share the specified saturated implementation.
For rounding-to-integral functions the operation's named rounding rule applies;
`rint`/`nearbyint` and `lrint`/`llrint` use the supplied R in constrained
wrappers (nearest/even in their ordinary §13.1 wrappers). LLVM `fptrunc.round` can also use
`_rm`; flags may accumulate even when exceptions are ignored.

Quiet `cmp_B_rm` raises invalid only for a signaling NaN. Distinct `cmps_B_rm`
raises invalid for either quiet or signaling NaN, even for false/true predicates;
both return the same truth value and raise no other flags. Comparisons use R = 0
because their source constrained intrinsics have no rounding operand. Every
`_rm` comparison ORs its flags into the runtime environment without a host trap.
Exception-ignore lowering uses plain `cmp_B` for either source intrinsic and
leaves the environment unchanged. Arguments are read-only integer carriers.

Comparisons on f16, bf16, f32, f64 and f128 use format-specific integer IR.
Each export handles signed zeros, ordered predicates and NaNs directly;
constrained entries OR the exact invalid flag into the runtime global. Selecting
only one of these exports retains a single LLVM function with no arithmetic
helpers or scratch slots. `tests/test_compare_closure.py` checks all fifteen
closures in actual published bitcode. All seven formats remain available;
f80 and PPC retain their existing comparison implementations. Consumer
materialisation, budgets and performance must be verified against the newly
pinned publication; producer closure measurements alone do not establish them.

`__bennett_rt_fenv` is an **external runtime global**, with the ABI
`{ i32 round, i32 flags }`; the arith library does not define a competing copy.
For dynamic rounding the normaliser loads `round` and passes it as R. The test
bridge alone defines this global. Code using only unconstrained wrappers has no
reachable reference to it. Flags use ordinary loads/stores under the contract's
single-thread assumption.

The IEEE core uses unsigned 512-bit integers. Libm uses 224 working significand
bits and a 1024-bit integer product for Payne–Hanek reduction with 17,408 bits of
2/pi. Constants are generated with integer Chudnovsky and Python Decimal at
5,400 decimal digits. There are no LLVM FP instructions, APFloat calls, host
math, malloc, or external numerical dependencies in the publication. The six
IEEE formats retain their own precision; none is routed through binary64. x87 unnormals,
pseudo-denormals and pseudo-infinities become canonical NaN inputs. Arithmetic
NaN payload/sign are canonicalised; external bitwise operations preserve bits.
All ordered S/D conversion spellings are available, including redundant ones;
valid LLVM fpext routes are exact, and the numerical conversion machinery rounds
once if a precision-reducing route is called directly.

The bitcode has the tested x86_64 Linux triple and 64-bit little-endian layout.
Cross-target integration/execution is not certified by this gate. Vector
operations need no separate ABI: §13.2 applies these functions lane by lane after
N21; ordered reductions call the scalar operations in left-fold order. FP atomic
normalisation uses the same scalar add/sub/min/max functions. The gate tests
ordered reduction/reassociation inputs and the pinned unfused fmuladd witness;
it does not run or modify the sibling plugin.

## PPCDoubleDouble and libm semantics

PPC high double occupies carrier bits 0..63 and low double bits 64..127. Add and
multiply use the same component operation sequence as LLVM DoubleAPFloat, with
integer-only binary64 operations. Divide, fmod and FMA use LLVM's legacy 106-bit
fallback (minimum normal exponent −969, subnormal quantum 2^-1074). Comparison is lexicographic high,
then low. Canonical NaN is high 0x7ff8000000000000, low +0.

Dialect 0.2.12 resolves the PPC priority rule: exact-sum conversion and correctly
rounded canonical-pair sqrt/FMA/integral operations take precedence over legacy
APFloat fallbacks. On both LLVM majors, outgoing FP conversion rounds the exact
sum once, and integer conversion saturates the combined value. Integer inputs
retain every source bit, including sparse tails such as 2^1023+1. Integral
rounding preserves the named operation's flags, including the rint/nearbyint
difference. These paths use an exact 2176-bit magnitude at quantum 2^-1074.
Square root finds its bounding canonical pairs using an integer square root,
then compares exact squares and squared midpoints in 4352 bits. Only the final
result affects its flags; no intermediate binary64 underflow is reported.
Independent Fraction tests cover exact-value conversions, integer saturation,
canonical neighbours and hard square-root midpoints on both majors.

Incoming IEEE conversion and FMA still use legacy 106-bit rounding and remain in
**bennett-arith-4yg**. **bennett-arith-4yg.1** records a published tie-rule
ambiguity: at a zero-low transition both nearest neighbours can have odd parity
under the stated high-significand fallback. The exact witness is
`tests/ppc_zero_low_witness.py`. No arbitrary tie policy is claimed as contract
conformance. Same-major APFloat matching alone does not establish the explicit
canonical-pair guarantees. The separate named-format generator converts using
both PPC components.

Dialect 0.2.12 §13.4 requires a full-domain one-local-ulp envelope, correctly
rounded constrained selection, and exact mathematical flags. The current
libm v1 is a deterministic approximation evaluated at 224 working bits, then
rounded to the requested carrier format (including explicit R for `_rm`). The
engineering tests require <=4 ulp against MPFR at 384 bits, and exhaustive half/
bfloat sin <=1 ulp. Passing these tests is measured evidence, not a universal
error-bound or correct-rounding proof. No float/long-double host ABI is used.
Constrained wrappers preserve sticky flags; full-domain accuracy and exact-flag
implementation evidence remains in **bennett-arith-wvh**. Aggregate order and
signed zeros are tested separately.

The PPC exponential has a separate exact path for finite |x| <= 2^-112.
The exact input sum is first split into canonical h+l, including overlapping
or cancelling input fields. Its result has high component 1. The positive
correction exp(x)-1-x is too small to cross a low-component midpoint unless
x is exactly on it; that case selects the upper neighbour. Directed rounding
compares x with log(1+h): the exact quadratic term settles the comparison
unless it cancels l exactly, when the sign of the cubic term settles it.
These integer comparisons preserve sparse tails in all five modes and raise
only inexact; exp(±0) is exactly 1 with no flags. This fixes **bennett-arith-wvh.1**,
whose original exp(2^-700) result exceeded one local ulp by over 2^52.
`tests/test_ppc_exp.py` verifies every power-of-two exponent in this range,
both signs, sparse tails, component midpoints, quadratic cancellation, signed
zeros and final flags. Its oracle encloses the exact result between independent
rational Taylor bounds and requires both endpoints to round identically.
The earlier diagnostic `tests/ppc_exp_sparse_witness.py` retains the exact
counterexample bounds. Full-domain libm correctness remains in wvh; the
published contract's domain and available operations are unchanged.

The default bitcode publishes powi at K = 1, 8, 16, 32, 64, 128, 192, 256, 513,
1025 on every format, with `_rm` variants. `scripts/build 18 7 193` (or major 23)
adds exact i7/i193 signatures to that publication and its manifest. The generator
accepts any LLVM integer width 1..8388608 and emits repeated-squaring IR with the
original iK exponent throughout. A bitcode file has a finite export set; consumers
requiring another K must obtain the generated matching-major artifact and pin
its new SHA. The gate verifies the default publication; a custom artifact's
manifest lists its widths. No exponent is narrowed to i32/i128.

## Remaining parametric contracts

The offline generator below implements the 0.2.12 static request protocol.
The default `dist/` manifest targets 0.2.12 and records outstanding verification,
PPC and libm obligations in `conformance_pending`.

All 1,008 previously inventoried concrete signatures are published, plus 126
additional powi and seven signaling comparison signatures: **1,141 exports per
major**, no staged concrete bodies.
The remaining obligations are retained:

- `bennett-arith-38c`: named-format conversions and arbitrary powi widths are
  available through the documented offline generator below.
- `bennett-arith-chn`: the distinct 0.2.12 `cmps_B_rm` implementation is
  published and verified for all seven formats; **bennett-arith-chn.1** is
  closed. `softfloat/test_cmps.py` tests all predicates,
  half/bfloat NaN payloads, sticky flags and scalar lane sequences.

No placeholder numerical bodies or input-dependent unsupported traps implement
these unresolved families. This publication alone is not full DF/runtime or
plugin bp-7ni conformance. The consumer must re-pin BENNETT_ARITH_BITCODE hashes
and verify its own materialised L/CC closure. The plugin was read-only here.

## Offline instances (dialect 0.2.12)

Run `python3 -I softfloat/instantiate.py REQUEST.json OUTPUT_DIRECTORY` with
`TMPDIR` set to an existing job-local build directory. The installed LLVM 18 or
23 tools are used offline. The output is ordinary `bennett-arith.bc` and a JCS
`manifest.json`. The generator does not replace the default distribution.

A request has exactly these fields:

```json
{"schema":"bennett-arith-instantiations-1","llvm_major":23,"target_triple":"x86_64-unknown-linux-gnu","data_layout":"e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128","entries":[{"op":"convert_to","format":"Float6E3M2FN","base":"f128"},{"op":"convert_from","format":"Float8E4M3FN","base":"f80"},{"op":"powi","base":"ppcf128","exponent_bits":193}]}
```

`base` is any of the seven suffixes in the table above. A conversion entry has
exactly `op`, `format`, and `base`; a powi entry has exactly `op`, `base`, and
`exponent_bits`, with an integer width from 1 through 8388608 inclusive. Duplicate
entries request one instance. Requests reject unknown fields, duplicate JSON
keys, invalid widths and format names absent on their LLVM major.

LLVM 23 supports all eleven 0.2.12 interpretation names: `Float8E5M2`,
`Float8E5M2FNUZ`, `Float8E4M3`, `Float8E4M3FN`, `Float8E4M3FNUZ`,
`Float8E4M3B11FNUZ`, `Float8E3M4`, `Float8E8M0FNU`, `Float6E3M2FN`,
`Float6E2M3FN`, and `Float4E2M1FN`. Their carriers are i8, i6, or i4 as named.
LLVM 18 has no arbitrary-format intrinsic names; its requests can instantiate
powi. A missing LLVM APFloat intrinsic helper does not restrict this name set.

Conversion exports are exactly `iN @__bennett_sf_convert_to_<format>_<base>(C_B,
i32 R, i1 Sat)` and `C_B @__bennett_sf_convert_from_<format>_<base>(iN)`.
Conversions use integer arithmetic, canonical NaNs, zero bits for source poison
outcomes, explicit rounding and saturation, and no fenv side effect. PPC inputs
use both component values. Powi requests emit both plain and final-`_rm`
spellings with the original iK exponent and format-rounded repeated squaring.
The generated module contains the requested exported definitions and their
reachable implementation; it imports no host numerical library.

The C implementation first emits integer IR through the pinned x86 frontend,
whose `_BitInt` support includes the working precisions. The generator removes
CPU-specific attributes and assigns the request's triple and data layout to
both modules before linking. Private C function conventions remain internal;
public carrier wrappers are explicit LLVM IR. This also avoids LLVM 18's
AArch64 frontend limit of 128 bits. The limits test verifies AArch64 output
bitcode; numerical execution tests run on x86_64 Linux.
Target fields are checked against the requested LLVM major's interpretation;
LLVM 23 expands historical AArch64 layout spellings with its address-space and
function alignment defaults. The manifest retains the original request string.

Canonical request bytes use JCS with entries deduplicated and sorted by
`(op, base, format-or-empty, exponent_bits-or-zero)`. The manifest has schema
`bennett-arith-instances-1`, `request_sha256`, `bitcode_sha256`, the requested
`llvm_major`, `target_triple`, and `data_layout`, and `exports` sorted by `symbol`.
Each export records its exact LLVM `function_type`. Hashes cover the canonical
request bytes and the actual output bitcode. JCS files have no trailing newline.
Consumers link and pin this matching-major artifact before normalisation in
both builds. No finite set of default widths limits offline generation.

`python3 -I softfloat/test_instances.py` verifies the generated bitcode through
an independent LLVM dispatcher. It checks all source encodings of every named
format into all seven bases, conversion midpoints under all five modes and
both saturation settings, malformed requests, request/bitcode hashes, exact
exports, target fields, sticky flags, and the absence of hardware FP/imported
numerical routines. It does not establish the separate PPC sqrt/FMA or
full-domain transcendental obligations in `bennett-arith-4yg` and
`bennett-arith-wvh`.

`python3 -I softfloat/test_instance_limits.py --reproduce` verifies the inclusive
i8388608 exponent on both majors and AArch64 request fields. Run the numerical
test first: the reproduction check then regenerates its requests and compares
bitcode and JCS manifests byte for byte in different temporary directories.

## Verification

`scripts/gate` builds on both installed toolchains, checks byte-for-byte
reproduction of the publications, audits every manifest signature independently,
and compiles a test-only LLVM dispatcher against the **published bitcode**.
Python runs with `-I`; Fraction/integer division and squared midpoint comparisons
compute expected arithmetic, sqrt and rounding without host FP. No implementation
source is imported by the oracle. Tests cover all modes, canonical/signaling NaNs,
invalid x87 encodings, denormals, infinities, zeros, saturation, aggregate field
order, widths 129/193/257/513/1025, all pairwise format routes, and every export.
All 65,536 encodings of each of half and bfloat are checked for canonicalization,
extension/truncation round trip and square root. Finite arithmetic is otherwise
edge/seeded differential coverage, not an exhaustive proof over binary128.

The build uses `-O1`, disables vectorisation and host builtins, and records no
absolute source path. LLVM-generated integer/memory intrinsics remain for the
normaliser to materialise. Source integer flags/attributes also go through the
normaliser; this is link-input bitcode, not already-materialised ISA code.

The gate additionally sweeps exp/exp2/exp10 through every subnormal-output
exponent and overflow boundaries, and runs a test-only C++ oracle linked to the **same LLVM major's
APFloat**, MPFR 384-bit oracle comparisons, all 65,536 encodings of half and
bfloat sin, PPC sparse-tail conversions and all predicates, and powi transport
through i1025. `libmpfr.so.6` is required by tests only; LLVM development headers
and llvm-config provide the APFloat oracle. Each manifest records the bitcode
SHA-256, tool versions, and path-independent SHA-256/Git blob SHA-1 of every
implementation/build source. SHA256SUMS also hashes the manifest. Gate builds in
place and requires byte-identical bitcode, manifest and checksum reproduction.

The component adapter in ppc.h follows LLVM DoubleAPFloat algorithms under
Apache-2.0 WITH LLVM-exception; see LLVM-LICENSE.txt. The numerical core,
fixed-precision libm, constant generator and oracle drivers are local code.
