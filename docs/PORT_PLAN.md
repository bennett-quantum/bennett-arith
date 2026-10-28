# Port plan: Bennett.jl v1 -> ISA library objects

Reference implementations (read-only, in the Bennett.jl repo):

| v1 file | Target dir | Notes |
|---|---|---|
| `src/adder.jl` | `adders/` | ripple-carry full adder + Cuccaro in-place |
| `src/qcla.jl` | `adders/` | Draper-Kutin-Rains-Svore carry-lookahead |
| `src/multiplier.jl` | `multipliers/` | shift-and-add + Karatsuba |
| `src/mul_qcla_tree.jl` | `multipliers/` | Sun-Borissov polylog-depth, self-reversing |
| `src/partial_products.jl`, `src/parallel_adder_tree.jl`, `src/fast_copy.jl` | `multipliers/` | building blocks |
| `src/qrom.jl` | `qrom/` | Babbush-Gidney 2018 |
| `src/softfloat/*.jl` (fadd, fsub, fmul, fma, fdiv, fsqrt, fneg, fcmp, fpconv, fptosi, fptoui, sitofp, fround, fexp, fexp_julia, softfloat_common) | `softfloat/` | binary64 only |
| `src/divider.jl` | `adders/` or `multipliers/` | soft_udiv / soft_urem |

## Test conventions to carry over

- **Subnormal binade sweeps:** every transcendental gets a "subnormal-output
  range" test sweeping inputs where the native result is subnormal, in steps
  fine enough (0.25 or 0.5) to populate every binade (origin: soft_exp
  garbage-output bug, Bennett-wigl / Bennett-fnxg).
- **NaN bit-pattern comparison:** compare results as UInt64 bit patterns, never
  with `==`/`isequal`; NaN payload and sign must match native.
- **Scaling-relation regressions:** pin gate counts for explicit strategies, and
  assert doubling relations (e.g. ripple `x+1`: `total(2W) == 2*total(W) - 2`,
  Toffoli `T(2W) == 2*T(W) + 4`).
- Exhaustive at Int8; representative plus edge cases at wider widths; edge cases
  for floats: 0, -0, Inf, NaN, subnormals, overflow boundaries.
- Every object: all ancillae return to zero (certificate check), output equals
  native.
