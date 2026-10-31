# bennett-arith

Arithmetic bitcode and ISA libraries for Bennett. The soft-float M1 publishes
integer-only bitcode for LLVM 18 and 23 against dialect **0.2.10 @023f5a7** and
ISA **0.8** (see `SPEC_VERSIONS.toml`).

- [LLVM 18 bitcode](dist/llvm18/bennett-arith.bc) · [entry-point manifest](dist/llvm18/manifest.json)
- [LLVM 23 bitcode](dist/llvm23/bennett-arith.bc) · [entry-point manifest](dist/llvm23/manifest.json)
- [Linking, signatures, exactness and staged scope](softfloat/README.md)
- [Current handoff](HANDOFF.md)

Run `scripts/gate` to reproduce both checked-in publications and execute the
independent integer/rational oracle suites. `scripts/pre-push` tests a detached,
clean checkout of every pushed commit. Install it with `scripts/install-hooks.sh`.
Everything is local and headless, with temporary files under `.tmp/`.

The wider arithmetic scope remains: `adders/`, `multipliers/`, `qrom/` and
soft-float as ISA library objects with certificates. See `docs/PORT_PLAN.md`.
This milestone publishes ordinary LLVM bitcode; ISA objects/certificates are
produced by the downstream driver pipeline, not claimed here.
