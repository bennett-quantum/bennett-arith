# Current state — soft-float M1 (2026-10-31)

Published binary edge: `dist/llvm18/bennett-arith.bc` and
`dist/llvm23/bennett-arith.bc`, with same-directory `manifest.json` and
`SHA256SUMS`. Pinned dialect 0.2.10 @023f5a7, ISA 0.8. The manifests enumerate
606 integer-only exported carrier signatures for binary16, bfloat16, binary32,
binary64, x86_fp80 and binary128, plus every staged concrete signature and
parametric family. See `softfloat/README.md` for the signature table and semantics.

The plugin/driver should link only the matching-major `.bc` using llvm-link,
with the program and runtimes **before normalisation**, then materialise the
whole reachable closure for both device and native comparison builds. Constrained
wrappers expect the runtime-owned external `{ i32 round, i32 flags }` global
`__bennett_rt_fenv`. No source integration or host FP/libm is required. This is
ordinary bitcode for the tested x86_64 Linux/64-bit little-endian layout;
cross-target execution is not certified. Nothing in the plugin was modified.

Gate: `env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-arith/.tmp /home/tobias/Projects/bennett-workspace/bennett-arith/scripts/gate`.
It rebuilds both artefacts, requires byte-identical publications, audits the
required manifest, and runs 1,029,583 independent rational/integer numerical
checks per major against the actual bitcode; all 606 exported signatures are
exercised. The manifest audit accounts for 1,008 concrete signatures and three
parametric families. `scripts/pre-push` gates every pushed SHA in a clean detached
worktree; run `scripts/install-hooks.sh` to install it under the active hooks path.
No CI, push, Dolt sync, desktop process or system /tmp output is used.

Still staged, never rejected/trapped/narrowed: PPCDoubleDouble and its conversion
routes (`bennett-arith-r3d`, §13.1/13.3); all seven own-format transcendental/libm
families and powi exponent widths other than i32 (`bennett-arith-0he`, §13.4);
metadata-named arbitrary APFloat formats (`bennett-arith-38c`, §13.1). Each bead
quotes the determining contract sentence and is exported in `.beads/issues.jsonl`.
Signaling constrained comparison needs the ABI clarification in
`bennett-arith-chn` (§13.5); quiet comparison `_rm` is implemented, and the
manifest records this contract question. Constrained powi is staged in 0he.
The full required scope remains; this is not full DF conformance. The i128
sitofp, scalar arithmetic/comparison, ordered reassociation and unfused fmuladd
edge needed for fp-rot-fastmath-reassoc is published, but closing bp-7ni remains
the consumer's decision after linking and testing its materialised closure.
Adders, multipliers, QROM and emitted ISA objects/certificates remain later scope.
