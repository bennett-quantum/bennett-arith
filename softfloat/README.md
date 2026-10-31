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

For `B = f16, bf16, f32, f64, f80, f128`, `C = i16, i16, i32, i64, i80, i128`:

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
| `powi_B_i32` | `C (C, i32)` | deterministic repeated squaring with per-step rounding |
| `{fptosi,fptoui,lround,llround,lrint,llrint}_B_wide` | `void (ptr, C, i32 M)` | exact saturated M-bit little-endian limb result |
| `{sitofp,uitofp}_B_wide` | `C (ptr, i32 M)` | correctly rounded from all M bits |

`_rm` variants of arithmetic, conversion (including `_wide`), sqrt, integer
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

All finite arithmetic uses unsigned 512-bit integers, not LLVM FP instructions,
APFloat, host math, malloc, or a native runtime numerical dependency. The six
formats keep their own precision; none is routed through binary64. x87 unnormals,
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

## Mechanics still staged, scope retained

- `bennett-arith-r3d`: all PPCDoubleDouble operations, rounding and routes to/from
  the other six formats, matching the LLVM major's APFloat semantics (§13.1/13.3).
- `bennett-arith-0he`: own-format sin/cos/tan/asin/acos/atan/atan2,
  sinh/cosh/tanh, exp/exp2/exp10, log/log2/log10, pow, sincos/sincospi for **all
  seven formats**, plus powi exponent widths other than 32 (§13.4). No correctly
  rounded transcendental claim is required; deterministic own-format semantics
  are required. modf and i32 powi are already implemented for the six IEEE formats.
- `bennett-arith-38c`: metadata-named arbitrary APFloat format conversion families
  for all seven formats (§13.1).

Each bead quotes its determining sentence. No staged symbol has a placeholder
body, a narrowing substitute, or an input-dependent unsupported trap. These are
unimplemented mechanics, not removed capabilities. This publication is **not full
DF/runtime conformance** and does not alone discharge the plugin's entire bp-7ni.

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
