# bennett-arith

Arithmetic bitcode and ISA libraries for Bennett. The soft-float library publishes
1,141 integer-only carrier definitions per major for LLVM 18 and 23 against dialect **0.2.13 @95a4b8d** and
ISA **0.8** (see `SPEC_VERSIONS.toml`).

- [LLVM 18 bitcode](dist/llvm18/bennett-arith.bc) · [entry-point manifest](dist/llvm18/manifest.json)
- [LLVM 23 bitcode](dist/llvm23/bennett-arith.bc) · [entry-point manifest](dist/llvm23/manifest.json)
- [Linking, signatures, exactness and staged scope](softfloat/README.md)
- [Current handoff](../bennett/HANDOFF.md)

Run `scripts/test` for bounded default checks and `scripts/gate` to reproduce both checked-in publications and execute the
independent integer/rational, same-major APFloat, and MPFR oracle suites.
PPCDoubleDouble and all seven own-format libm families are published; arbitrary
metadata formats are delivered by the offline instance generator, and signaling comparison is published. `scripts/pre-push` tests a detached,
clean checkout of every pushed commit. Install it with `scripts/install-hooks.sh`.
Everything is local and headless, with temporary files under `.tmp/`.

The wider arithmetic scope remains: `adders/`, `multipliers/`, `qrom/` and
soft-float as ISA library objects with certificates. See `docs/PORT_PLAN.md`.
This repository publishes ordinary LLVM bitcode and circuit objects with certificates.
The pinned reader proves all 37 universal `adjoint_table` claims; two large-publication receipts remain incomplete, as recorded in [quality evidence](docs/quality.md).
