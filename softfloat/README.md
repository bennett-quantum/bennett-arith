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

`_rm` variants of arithmetic, quiet comparison, conversion (including `_wide`), sqrt, integer
rounding, min/max and ldexp append `i32 R`. Modes 0–4 are nearest/even, downward,
upward, toward zero, nearest/away. They OR invalid=1, divbyzero=2, overflow=4,
underflow=8, inexact=16 into `__bennett_rt_fenv.flags`; ordinary entry points do
not access the environment. Tininess is detected after rounding. Non-saturating
and .sat FP-to-integer operations share the specified saturated implementation.
For rounding-to-integral functions the operation's named rounding rule applies;
`rint`/`nearbyint` and `lrint`/`llrint` use the supplied R in constrained
wrappers (nearest/even in their ordinary §13.1 wrappers). LLVM `fptrunc.round` can also use
`_rm`; flags may accumulate even when exceptions are ignored.

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
fallback (minimum normal exponent −969, subnormal quantum 2^-1074). LLVM 18 uses
that fallback for integral/integer conversion too; LLVM 23 uses its newer
component algorithms, preserving sparse integer tails. Wide integer inputs and
outputs retain all bits; tests include 2^1023+1. Comparison is lexicographic high,
then low. Canonical NaN is high 0x7ff8000000000000, low +0.

The explicit APFloat rule conflicts with other §13.1 sentences. In both tested
majors APFloat PPC-to-IEEE conversion reads **only the high component**; it does
not implement the sentence “fpext is exact”. LLVM subtraction can return −0 in
both components; LLVM 23 unsigned integer conversion can saturate a positive
sum with a negative integral low component. These are reproduced against the
same-major oracle and deliberately retained. APFloat has no PPC sqrt; that entry
uses a correctly rounded legacy 106-bit result and nearest/even component split.
See dialect **b-dialect-spec-dfd** for both readings and requested resolution.
This is not a claim of ideal IEEE double-double arithmetic.

§13.4 explicitly waives correct rounding and gives **no numerical error bound**.
Libm v1 is a deterministic approximation evaluated at 224 working bits, then
rounded to the requested carrier format (including explicit R for `_rm`). The
engineering tests require <=4 ulp against MPFR at 384 bits, and exhaustive half/
bfloat sin <=1 ulp. Passing these tests is measured evidence, not a universal
error-bound or correct-rounding proof. No float/long-double host ABI is used.
Constrained wrappers preserve sticky flags; approximation inexact/flag policy
and the missing quantitative contract are recorded in dialect
**b-dialect-spec-1av**. Aggregate order and signed zeros are tested separately.

The default bitcode publishes powi at K = 1, 8, 16, 32, 64, 128, 192, 256, 513,
1025 on every format, with `_rm` variants. `scripts/build 18 7 193` (or major 23)
adds exact i7/i193 signatures to that publication and its manifest. The generator
accepts any LLVM integer width 1..8388608 and emits repeated-squaring IR with the
original iK exponent throughout. A bitcode file has a finite export set; consumers
requiring another K must obtain the generated matching-major artifact and pin
its new SHA. The gate verifies the default publication; a custom artifact's
manifest lists its widths. No exponent is narrowed to i32/i128.

## Remaining parametric contracts

All 1,008 previously inventoried concrete signatures are published, plus 126
additional powi signatures: **1,134 exports per major**, no staged concrete bodies.
The remaining obligations are retained:

- `bennett-arith-38c`: metadata-named arbitrary APFloat conversion families. The
  accepted dialect gives no metadata/name/carrier schema or finite format list;
  dialect **b-dialect-spec-z7u** requests that schema and instantiation protocol.
- `bennett-arith-chn`: signaling constrained comparison cannot share quiet
  `cmp_B_rm` with identical operands/P/R. Dialect **b-dialect-spec-21a** requests
  the exact signaling ABI.

No placeholder numerical bodies or input-dependent unsupported traps implement
these unresolved families. This publication alone is not full DF/runtime or
plugin bp-7ni conformance. The consumer must re-pin BENNETT_ARITH_BITCODE hashes
and verify its own materialised L/CC closure. The plugin was read-only here.

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
