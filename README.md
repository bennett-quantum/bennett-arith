# bennett-arith

Adders, multipliers, QROM and soft-float as **ISA library objects with
certificates**.

- `adders/` ripple, Cuccaro, QCLA
- `multipliers/` shift-and-add, Karatsuba, QCLA-tree
- `qrom/` Babbush-Gidney QROM
- `softfloat/` IEEE 754 binary64 in integer arithmetic

The v1 Bennett.jl generators (`src/adder.jl`, `src/qcla.jl`,
`src/multiplier.jl`, `src/softfloat/`) are the reference implementations to
port; see `docs/PORT_PLAN.md`.

Depends on: `bennett-dialect-spec` and the driver (build tool).
