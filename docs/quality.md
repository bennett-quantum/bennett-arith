# Arithmetic quality floor

## Default and exhaustive checks

Default at 7089922: `timeout 1200s systemd-run --user --scope -p MemoryMax=6G
scripts/test`, **37 tests passed in 67.91 s wall time** (51.470 s test body).
The build started with 23.72 GiB available and load1 5.71. The earlier cold
run at 94cf09f passed 37 tests in 72.07 s after all six bridge/support outputs
were moved aside. Both runs regenerate and relink support despite existing
outputs. The ISA reader pin is
`62a0cf0ef9f1f1c1db12c84ed24846b6b9695cdc` (ISA 0.9 K94); the dialect pin is
`95a4b8d06933018a07fef3516296a25fd582fcde` (0.2.13). The pinned gate tool's
`verify --repo MAIN --sha cf4af47` materialised both and built the ISA reader
in 10.97 s under a 6 GiB systemd scope, with 24.19 GiB available and load1
3.37. At adoption the ISA gated push was pending (`pushed=False`); the dialect
was pushed. Publication metadata still identifies its governing base text
and K91 extension separately; the gate pin selects the reader used to check it.
The cold bridge build does not regenerate or mutate the published bitcode.
Every default invocation regenerates ABI support files and constants, then
relinks the bridge from the current publication before loading any numerical
test. Existing outputs do not bypass preparation; a generation or compiler
failure stops the run before the suite can load the previous library.
Exhaustive vectors, LLVM23 numeric sweeps and offline instantiation limits
remain in `scripts/gate`. No full eight-hour gate was run by this job;
merge validation belongs to the orchestrator.

`tests/test_default_cache.py` exercises the real runner in an isolated fixture
whose suite body is a single exact `tanh_f16_rm(0x54e0, 1)` probe. It changes
the published function between two default invocations, updates the publication
hashes, and requires the second invocation to observe the deliberately wrong
`0x3c00` result and fail. It also changes both generator sources, damages or
removes generated support, and verifies repair; invalid bitcode must stop
before the previous library reaches the probe. Both regressions failed against
the existence-only reuse rule. The multiple real rebuilds run under a 600 s
timeout in `scripts/gate`, outside the bounded default suite. Verified with
`timeout 600s python3 -B -I tests/test_default_cache.py`: two tests passed in
255.13 s wall time (254.816 s test body).

Cache audit: `scripts/build` already regenerates every softfloat build output
for each major before gate tests load it. Phase/overflow executables, APFloat
oracles, comparison closures, circuit fixtures and offline instances are
rebuilt unconditionally on their default/gate paths. The offline tests' optional
`--reuse` switch is never supplied by the gate. Python rational-oracle caches
are process-local. The sibling checkout cache resolves the `gate.toml` SHA and
rejects a mismatched HEAD (covered by `tests/circuits/test_pins.py`); the gate
tool itself is addressed by `tool_sha`. No other existence-only reuse of locally
generated test outputs was found on these paths.

## Measured coverage

Python production statement coverage at e11bc94: **45.98%**
(755/1642 statements). This measures Python
production sources; the integer C core is exercised by black-box numerical tests,
not included in this Python percentage. It is a measurement, not a gate threshold.

Commands (coverage.py 7.17.2 installed locally with
`uv pip install --target .tmp/quality-arith/python coverage`):

```sh
export PYTHONPATH="$PWD/.tmp/quality-arith/python"
export COVERAGE_FILE="$PWD/.tmp/quality-arith/covdata/.coverage"
timeout 180s python3 -B -m coverage run --source=adders,multipliers,qrom,softfloat,scripts tests/test_default.py
python3 -m coverage report --omit='*/test_*.py'
```

The refreshed coverage-instrumented default run passed all 35 tests in 81.65 s
wall time (80.067 s test body), retaining 755/1642 covered production statements.

The five least-covered production modules are all 0% in the default in-process
measurement: `adders/generate.py`, `scripts/provenance.py`,
`softfloat/constants.py`, `softfloat/generate.py`, and `softfloat/instantiate.py`.
The CLI and reproducible publication checks execute these in isolated subprocesses;
subprocess coverage was not collected. The full gate builds both publications and
runs every `softfloat/test_*.py` script, including invalid requests, all named
formats, maximal integer widths and publication metadata. These expensive paths
stay outside the bounded default measurement.

## Test evidence and open obligations

* Exact MPFR brackets: all five former numeric tolerance locations now select
  carrier bits from directed lower/upper bounds; precision refines up to 65536 bits
  and an inconclusive bracket fails loudly. The additional sincospi tolerance was
  removed too. LLVM18 nearest sweep: 130464 checks passed; boundary sweep: 14655.
* Directed sweep covers all 19 elementary scalar/pair entry points, five modes,
  tiny, large and near-one inputs. Quick IEEE sweep: 11970 checks on LLVM18.
* Named overflow: 112 independent LLVM23 APFloat comparisons passed. An
  additional focused request generated all seven affected f32 conversion
  exports through `softfloat/instantiate.py`; loading that actual bitcode
  and comparing the same 112 overflow cases against APFloat also passed. PPC
  zero-low parity: 12 hand-derived value/flag checks and 25491 exact-sum checks
  passed on each major after migration to dialect 0.2.13.
* `BENNETT_ARITH_PROMISED=1` exposes exact sparse-PPC libm failures
  (`bennett-arith-wvh`). The mandatory circuits suite separately checks raw
  release admission for **every** manifest entry and replays every certificate
  claim/table through the pinned reader API, without an opt-in switch. These
  checks reject unverified structural claims as well as malformed objects
  (`bennett-arith-emu`, also inherited `bennett-arith-gdg`/`bennett-arith-vwi`).
* K91 certificate partitions have unit tests against published ISA 0.9 text.
  The reader at `62a0cf0ef9f1` admits `token_aliases` and establishes all
  **37 universal `adjoint_table` claims as proof** under §12.1 K94. The
  previous `3b1090790d82` reader returned `Unverified` because the syntactic
  premises were unspecified. No certificate bytes, claims, aliases or domains
  changed for this second re-pin. Three large-publication receipts remain
  explicitly incomplete (`bennett-arith-jn3`, P2); diagnostic execution
  coverage remains separate from raw certificate proof evidence.
* Parity implementation is complete; `bennett-arith-4yg.1` remains open because
  its inherited release dependency on gdg prevents closure. No dependency override.

## Sparse PPC and publication admission repair

Dialect 0.2.13 §13.4 requires directed neighbours in the ordered canonical-pair
set. At `x=2^-700`, `sin(x)` lies strictly between `(x,-2^-1074)` and `(x,+0)`.
Its cubic correction is below their midpoint, so nearest/upward/nearest-away
select `(x,+0)` and downward/towardzero select `(x,-2^-1074)`, with inexact.
The 015b424 publication returned low `-2^-940` in all five modes; the new
MPFR-bracket regression was run against that exact publication and failed.

For `0<|x|<=2^-358`, the six odd functions sin/sinh/tan/atan/asin/tanh have
strict cubic corrections smaller than `2^-1075`. Exact pair sums and canonical
midpoints lie on the `2^-1075` grid. Rounding the exact sum perturbed by the
correction's sign at `2^-1076` therefore selects the same neighbour as the
analytic result, including noncanonical input sums. Existing exact packing
sets inexact and tininess-after-rounding flags. The IEEE small-argument path
now uses the same six-operation sign table. Both publications were rebuilt
with `timeout 600s scripts/build 18` and `timeout 600s scripts/build 23`.

`tests/test_directed.py` includes a default eight-exponent family (both signs,
all five modes, all six operations) and the sparse exp witness, independently
rounded from MPFR bounds. Its full form enumerates every exponent 358..1074:
**43,030 exact value/flag checks passed on each LLVM major**, using
`timeout 1200s python3 -B -I tests/test_directed.py 18 23 --tiny-only`.
The `2^-358` endpoint was separately observed RED after the initial
conservative cutoff, before extending that cutoff. Quick directed
runs `timeout 240s python3 -B -I tests/test_directed.py 18 --quick` and the
corresponding `23 --quick` passed **12,460 checks each**. No tolerance or
baseline changed.

ISA 0.9 K91 at be109bd §12.3 explicitly requires canonical `token_aliases` and
states that closed-schema readers require its upgrade. Publications retain
this required metadata. The unconditional
`Published.test_raw_publications_admitted` checks all 129 unmodified files and
then uses the pinned reader's public `Object::verify_certificate` API to
replay every stored claim, accepting only proof or sampled evidence reports.
A nonempty report set and exact claim count prevent vacuous success. The
bridge links only to the library built beside the gate-pinned reader binary.
It does not substitute the local ISA working tree or generator output. The
CLI `check` only validates admission and identities; the Rust verifier is
required because the documented public API performs full certificate replay,
including borrowed-wire domains that CLI `run-action` cannot initialise.

At ec37c21 with the old ecaaac0 reader,
`timeout 240s python3 -B -I tests/circuits/test_objects.py Published.test_raw_publications_admitted`
was reproduced **RED: all 129 publications reject `token_aliases` before replay**
(1.375 s test body). Pin-only commit 6dd2531 moves the reader to pushed
`3b1090790d82a00ac95d30b8da6b42d1d7a9f5d1`. Materialisation used:

```sh
timeout 1200s python3 /home/tobias/Projects/bennett-workspace/bennett-arith/.tmp/gate/tool/gate_run-01c0314c9aaa4a37313ab530da2134efafe9cbd5.py verify --repo /home/tobias/Projects/bennett-workspace/bennett-arith --sha 6dd2531
```

The new public API returns `CertificateReport`; the bridge now reads its
`claims` field, retains exact claim-count and Proof/Evidence-only assertions,
and rejects every unestablished K92 applicability obligation. The old bridge
failed compilation against this pin before that adaptation.

Raw verification exposed two further issues. Six modular objects bound their
K4 inverse-pair subjects to `g` instead of the owning action. ISA 0.9 §12.3
K92 requires owner-local entries and claim indices. An added owner-subject
regression failed before fixing that binding, then passed. No body, closure
identity, token partition or inverse-pair domain changed.

Pin commit cf4af47 adopts ISA 0.9 K94 at `62a0cf0ef9f1`, which specifies the
adjoint theorem's decidable premises and implements their checks. A focused
raw-byte replay of manifest indices 41..77 completed all **111 claims**, with
all **37 structural claims Established (proof)**, in 26.87 s wall time.
This includes `arith.bij.sub.w1` claim 1, the original unchecked witness.
The invocation remains universal over arguments, budgets and K91 partitions;
no claim or domain was reduced and no publication regenerated.

The replay bridge prints each established claim and a final complete receipt.
It distinguishes failing `Unverified` outcomes from `Rejected` false or
malformed claims, and refuses image-relative or sampled structural proofs.
Using the old pinned public API reproduces the unchecked witness: the former
diagnostic failed a distinct-`Unverified:` check, then the updated bridge
passed it while retaining a nonzero result. A deliberately mutated Cuccaro
table claiming `0+0=1` rejects at §12.1 K13 full-tuple mismatch, distinctly
from Unverified. Timeout diagnostics print `INCOMPLETE`, the publication,
admission/replay stage, bound and measured wall time, then fail the test.

Separately, `timeout 240s python3 -B -I tests/circuits/test_objects.py
Published.test_interpreter_replays_table_rows Published.test_token_aliases
Published.test_manifest_is_current Published.test_reproduces_byte_for_byte`
passed four tests at the K94 pin in 7.13 s wall time (6.988 s test body).
`Published.test_certificates_tell_the_truth` also passed in 0.494 s. The bounded default suite includes
this diagnostic replay and an independent four-tuple width-one Cuccaro
assertion, including `[1,0] -> [1,1]` with phase exactly +1. The full circuits
suite selects unconditional raw admission and claim replay; the remaining
large-publication work limits still prevent a complete green receipt.

The canonical `timeout 1200s systemd-run --user --scope -p MemoryMax=6G
python3 -B -I tests/circuits/test_objects.py
Published.test_raw_publications_admitted` at the K94 pin exited **124 at
1200.00 s**. A serial outer timeout does not establish a complete manifest
receipt. Complementary two-worker sweeps call the same committed raw helper
and public pinned-reader verifier for every manifest entry, preserving the
600 s bounds for admission and replay. The suffix at indices 118..128
attempted all eleven publications: nine complete (all four tree multipliers
and five QROM objects), two incomplete, exit 1 in **753.33 s** wall time.
The prefix at indices 0..117 attempted all 118 publications: 117 complete,
one incomplete, exit 1 in **902.81 s**. Comparing both result arrays with the
manifest confirms every one of the **129 entries attempted exactly once**,
**126 complete receipts covering 215 claims**, and exactly the three
incomplete receipts below. All 37 universal structural claims are proof;
no rejected or Unverified verdict was reported at this pin. This is not a green
full-manifest receipt. The original K91/K94 rejection regressions
(`bennett-arith-emu`, `bennett-arith-4ss`) are resolved; the incomplete
performance receipts remain open in `bennett-arith-jn3`.

The three previously incomplete receipts remain explicit P2 work in
`bennett-arith-jn3`:

| Publication | Incomplete stage | Bound | Measured wall time |
|---|---|---|---|
| `arith.bij.addmod.w8.mfb` | Full four-claim replay after successful admission | 600 s | 600.03 s |
| `arith.muladd.karatsuba.w32.r64` | Admission | 600 s | 600.21 s |
| `arith.mul.karatsuba.w32.r64` | Admission | 600 s | 600.18 s |

The earlier serial run at the previous pin stopped at the large muladd
publication at its 1200 s outer bound; the new direct attempt supplies the
more precise admission timeout above. None of these timeouts is a refutation
or a proof. Every incomplete receipt remains a visible failing test result;
no bound increased and no domain element, claim or publication was removed.
The P2 follow-up proposes an optimized build of the identical pinned reader,
per-publication API replay at the same bounds, profiling quadratic admission,
and avoiding duplicate CLI/API parsing when identities can be checked from
the same parsed object. This cheaper route has not been verified here.
The final quality ratchet passes for all 55 source files without increasing
any baseline. No full gate was run.

## Audit disposition

The core integer zero returns represent specified results: zero bit width and
invalid conversion accompanied by the invalid flag, respectively. They are not
quiet error fallbacks. Basic-operation oracle checks include negative square roots,
NaNs and exact zeros with sticky flags. A focused test also checks all six IEEE
formats, both integer conversion kinds and all five modes: a NaN conversion
returns zero **and** the invalid flag (60 checks passed), so the sentinel cannot
hide an invalid conversion. `pack` receives operation-local flags, not the fenv
sticky word; retaining mathematical inexact from the transcendental phase is
intentional for tininess-after-rounding. No public reproducer justified changing
that policy. The full gate retains the larger edge suite.

All tracked sources currently have no semantics-bearing function over 300 lines.
The elementary evaluator now has named domain, core and packing phases, and
a per-operation exact-case table. The phase/table unit test was red against the
pre-refactor source, then passed. `timeout 120s python3 -B -I
.tmp/quality-arith/refactor-differential.py` compared 13965 calls with a saved
pre-refactor LLVM18 bridge: all result-pair bytes and sticky flags were identical.
That scratch comparison is evidence, not a committed fixture or numerical oracle.
The full IEEE directed sweep passed 18810 scalar/pair checks:
`timeout 180s python3 -B -I tests/test_directed.py 18`.
`tests/test_trans_phases.py` remains in both the default and exhaustive suites.

## Source and publication hygiene

The fail-fast audit found specified zero results, not swallowed errors; the
invalid-conversion regression checks the required flag. Process identifiers
were removed from generator metadata and emitted manifests; outstanding
capabilities use descriptive obligation names. The product-source grep first
failed on ten occurrences, then passed after cleanup. No tracked pycache,
logs, lock, backup or progress files remain. Existing ignore rules cover
`__pycache__/`, `*.pyc`, `*.log`, `.beads/**/LOCK` and `*.darc`.
README counts, dialect version and helper documentation now match publication.

## Quality back pressure

`python3 -B -I scripts/quality_metrics.py --report` measures tracked and
nonignored source files; the sole quality check in `gate.toml` compares them
with the baseline below. Any per-file numeric increase, or increase in litter
or process-identifier count, rejects the push. Deliberate growth requires an
explicit baseline update for review. Deletions may improve the metric.
The baseline adds only the new runner-regression file: four test/fixture
functions, maximum 24 lines, cognitive mass 3, and one shared subprocess helper.
Existing per-file limits are unchanged.

Lengths are physical function lines. Distribution columns count functions
longer than 25, 50, 100, 200 and 300 lines (cumulative). Cognitive mass is a local
syntax metric: Python control decisions add 1 plus decision nesting, Boolean
operators add one per extra operand; C control/conditional tokens add 1 plus
brace nesting, Boolean operators add one. This is a reproducible approximation,
not a claim of Sonar compatibility. Per-file totals include test sources.
Trivial wrappers count single call-only function bodies; ratcheting them alongside
complexity prevents replacing branches with a growing collection of forwarding
functions. The script's regression tests cover nested branches, wrappers, new
files, litter and process identifiers; the missing-baseline check was red first.

The production identifier grep is
`\bbennett-arith-[a-z0-9]{3}(?:\.[0-9]+)?\b` plus job/shift/round labels;
test names and test files may retain issue identifiers. Litter checks all
tracked/nonignored files for pycache, pyc, logs, locks, backups and progress files.

| file | functions | max lines | >25 / >50 / >100 / >200 / >300 | cognitive mass | wrappers |
|---|---:|---:|---|---:|---:|
| adders/circuits.py | 50 | 37 | 1 / 0 / 0 / 0 / 0 | 111 | 11 |
| adders/constructions.py | 46 | 50 | 4 / 0 / 0 / 0 / 0 | 163 | 0 |
| adders/generate.py | 3 | 31 | 3 / 0 / 0 / 0 / 0 | 59 | 0 |
| multipliers/constructions.py | 25 | 52 | 1 / 1 / 0 / 0 / 0 | 65 | 1 |
| qrom/constructions.py | 13 | 39 | 1 / 0 / 0 / 0 / 0 | 42 | 0 |
| scripts/pinned_sibling.py | 2 | 15 | 0 / 0 / 0 / 0 / 0 | 6 | 0 |
| scripts/provenance.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| scripts/quality_metrics.py | 6 | 19 | 0 / 0 / 0 / 0 / 0 | 75 | 0 |
| softfloat/constants.py | 1 | 19 | 0 / 0 / 0 / 0 / 0 | 7 | 0 |
| softfloat/core.c | 23 | 128 | 1 / 1 / 1 / 0 / 0 | 424 | 0 |
| softfloat/generate.py | 5 | 163 | 4 / 1 / 1 / 0 / 0 | 260 | 0 |
| softfloat/instantiate.py | 10 | 88 | 1 / 1 / 0 / 0 / 0 | 89 | 4 |
| softfloat/named.c | 4 | 28 | 1 / 0 / 0 / 0 / 0 | 80 | 0 |
| softfloat/ppc.h | 8 | 104 | 2 / 1 / 1 / 0 / 0 | 205 | 0 |
| softfloat/ppc_round.h | 7 | 41 | 1 / 0 / 0 / 0 / 0 | 71 | 0 |
| softfloat/ppc_sum.h | 18 | 35 | 3 / 0 / 0 / 0 / 0 | 164 | 0 |
| softfloat/test_cmps.py | 2 | 7 | 0 / 0 / 0 / 0 / 0 | 10 | 0 |
| softfloat/test_instance_limits.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| softfloat/test_instances.py | 6 | 28 | 1 / 0 / 0 / 0 / 0 | 69 | 1 |
| softfloat/test_publication.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| softfloat/trans.h | 26 | 57 | 3 / 1 / 0 / 0 / 0 | 365 | 2 |
| softfloat/trans_exact.h | 9 | 67 | 1 / 1 / 0 / 0 / 0 | 129 | 0 |
| tests/build_stage.py | 2 | 3 | 0 / 0 / 0 / 0 / 0 | 1 | 1 |
| tests/circuits/harness.py | 24 | 40 | 2 / 0 / 0 / 0 / 0 | 145 | 0 |
| tests/circuits/test_adders.py | 55 | 36 | 1 / 0 / 0 / 0 / 0 | 235 | 1 |
| tests/circuits/test_multipliers.py | 19 | 25 | 0 / 0 / 0 / 0 / 0 | 70 | 1 |
| tests/circuits/test_objects.py | 16 | 47 | 1 / 0 / 0 / 0 / 0 | 150 | 2 |
| tests/circuits/test_pins.py | 19 | 18 | 0 / 0 / 0 / 0 / 0 | 2 | 1 |
| tests/circuits/test_qrom.py | 17 | 18 | 0 / 0 / 0 / 0 / 0 | 37 | 1 |
| tests/named_oracle.cpp | 1 | 21 | 0 / 0 / 0 / 0 / 0 | 4 | 0 |
| tests/ppc_exact_oracle.py | 14 | 31 | 1 / 0 / 0 / 0 / 0 | 138 | 1 |
| tests/ppc_exp_sparse_witness.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/ppc_oracle.cpp | 1 | 34 | 1 / 0 / 0 / 0 / 0 | 50 | 0 |
| tests/ppc_zero_low_witness.py | 2 | 4 | 0 / 0 / 0 / 0 / 0 | 2 | 0 |
| tests/test_compare_closure.py | 1 | 22 | 0 / 0 / 0 / 0 / 0 | 11 | 0 |
| tests/test_contract.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/test_default.py | 15 | 12 | 0 / 0 / 0 / 0 / 0 | 41 | 5 |
| tests/test_default_cache.py | 4 | 24 | 0 / 0 / 0 / 0 / 0 | 3 | 1 |
| tests/test_directed.py | 2 | 34 | 1 / 0 / 0 / 0 / 0 | 56 | 0 |
| tests/test_edge.py | 16 | 229 | 2 / 2 / 1 / 1 / 0 | 842 | 2 |
| tests/test_extended.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/test_named_overflow.py | 1 | 21 | 0 / 0 / 0 / 0 / 0 | 9 | 0 |
| tests/test_pair_parity.py | 1 | 19 | 0 / 0 / 0 / 0 / 0 | 13 | 0 |
| tests/test_powi.py | 1 | 7 | 0 / 0 / 0 / 0 / 0 | 6 | 0 |
| tests/test_powi_limit.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/test_ppc.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/test_ppc_exact.py | 1 | 111 | 1 / 1 / 1 / 0 / 0 | 152 | 0 |
| tests/test_ppc_exp.py | 2 | 51 | 1 / 1 / 0 / 0 / 0 | 28 | 0 |
| tests/test_quality.py | 6 | 6 | 0 / 0 / 0 / 0 / 0 | 2 | 2 |
| tests/test_review_numeric.py | 2 | 78 | 1 / 1 / 0 / 0 / 0 | 151 | 0 |
| tests/test_trans.py | 9 | 21 | 0 / 0 / 0 / 0 / 0 | 36 | 0 |
| tests/test_trans_boundaries.py | 0 | 0 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/test_trans_extra.py | 2 | 9 | 0 / 0 / 0 / 0 / 0 | 7 | 0 |
| tests/test_trans_phases.py | 1 | 10 | 0 / 0 / 0 / 0 / 0 | 0 | 0 |
| tests/trans_phases.c | 6 | 15 | 0 / 0 / 0 / 0 / 0 | 7 | 0 |

Litter: 0. Product process identifiers: 0. No functions exceed 300 lines.

<!-- quality-baseline -->
```json
{"files":{
"adders/circuits.py":{"cognitive_mass":111,"functions":50,"max_lines":37,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":11},
"adders/constructions.py":{"cognitive_mass":163,"functions":46,"max_lines":50,"over_100":0,"over_200":0,"over_25":4,"over_300":0,"over_50":0,"trivial_wrappers":0},
"adders/generate.py":{"cognitive_mass":59,"functions":3,"max_lines":31,"over_100":0,"over_200":0,"over_25":3,"over_300":0,"over_50":0,"trivial_wrappers":0},
"multipliers/constructions.py":{"cognitive_mass":65,"functions":25,"max_lines":52,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":1},
"qrom/constructions.py":{"cognitive_mass":42,"functions":13,"max_lines":39,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
"scripts/pinned_sibling.py":{"cognitive_mass":6,"functions":2,"max_lines":15,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"scripts/provenance.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"scripts/quality_metrics.py":{"cognitive_mass":75,"functions":6,"max_lines":19,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/constants.py":{"cognitive_mass":7,"functions":1,"max_lines":19,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/core.c":{"cognitive_mass":424,"functions":23,"max_lines":128,"over_100":1,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":0},
"softfloat/generate.py":{"cognitive_mass":260,"functions":5,"max_lines":163,"over_100":1,"over_200":0,"over_25":4,"over_300":0,"over_50":1,"trivial_wrappers":0},
"softfloat/instantiate.py":{"cognitive_mass":89,"functions":10,"max_lines":88,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":4},
"softfloat/named.c":{"cognitive_mass":80,"functions":4,"max_lines":28,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/ppc.h":{"cognitive_mass":205,"functions":8,"max_lines":104,"over_100":1,"over_200":0,"over_25":2,"over_300":0,"over_50":1,"trivial_wrappers":0},
"softfloat/ppc_round.h":{"cognitive_mass":71,"functions":7,"max_lines":41,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/ppc_sum.h":{"cognitive_mass":164,"functions":18,"max_lines":35,"over_100":0,"over_200":0,"over_25":3,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/test_cmps.py":{"cognitive_mass":10,"functions":2,"max_lines":7,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/test_instance_limits.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/test_instances.py":{"cognitive_mass":69,"functions":6,"max_lines":28,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":1},
"softfloat/test_publication.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"softfloat/trans.h":{"cognitive_mass":365,"functions":26,"max_lines":57,"over_100":0,"over_200":0,"over_25":3,"over_300":0,"over_50":1,"trivial_wrappers":2},
"softfloat/trans_exact.h":{"cognitive_mass":129,"functions":9,"max_lines":67,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":0},
"tests/build_stage.py":{"cognitive_mass":1,"functions":2,"max_lines":3,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/circuits/harness.py":{"cognitive_mass":145,"functions":24,"max_lines":40,"over_100":0,"over_200":0,"over_25":2,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/circuits/test_adders.py":{"cognitive_mass":235,"functions":55,"max_lines":36,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/circuits/test_multipliers.py":{"cognitive_mass":70,"functions":19,"max_lines":25,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/circuits/test_objects.py":{"cognitive_mass":150,"functions":16,"max_lines":47,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":2},
"tests/circuits/test_pins.py":{"cognitive_mass":2,"functions":19,"max_lines":18,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/circuits/test_qrom.py":{"cognitive_mass":37,"functions":17,"max_lines":18,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/named_oracle.cpp":{"cognitive_mass":4,"functions":1,"max_lines":21,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/ppc_exact_oracle.py":{"cognitive_mass":138,"functions":14,"max_lines":31,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/ppc_exp_sparse_witness.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/ppc_oracle.cpp":{"cognitive_mass":50,"functions":1,"max_lines":34,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/ppc_zero_low_witness.py":{"cognitive_mass":2,"functions":2,"max_lines":4,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_compare_closure.py":{"cognitive_mass":11,"functions":1,"max_lines":22,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_contract.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_default.py":{"cognitive_mass":41,"functions":15,"max_lines":12,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":5},
"tests/test_default_cache.py":{"cognitive_mass":3,"functions":4,"max_lines":24,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":1},
"tests/test_directed.py":{"cognitive_mass":56,"functions":2,"max_lines":34,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_edge.py":{"cognitive_mass":842,"functions":16,"max_lines":229,"over_100":1,"over_200":1,"over_25":2,"over_300":0,"over_50":2,"trivial_wrappers":2},
"tests/test_extended.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_named_overflow.py":{"cognitive_mass":9,"functions":1,"max_lines":21,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_pair_parity.py":{"cognitive_mass":13,"functions":1,"max_lines":19,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_powi.py":{"cognitive_mass":6,"functions":1,"max_lines":7,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_powi_limit.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_ppc.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_ppc_exact.py":{"cognitive_mass":152,"functions":1,"max_lines":111,"over_100":1,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":0},
"tests/test_ppc_exp.py":{"cognitive_mass":28,"functions":2,"max_lines":51,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":0},
"tests/test_quality.py":{"cognitive_mass":2,"functions":6,"max_lines":6,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":2},
"tests/test_review_numeric.py":{"cognitive_mass":151,"functions":2,"max_lines":78,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":1,"trivial_wrappers":0},
"tests/test_trans.py":{"cognitive_mass":36,"functions":9,"max_lines":21,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_trans_boundaries.py":{"cognitive_mass":0,"functions":0,"max_lines":0,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_trans_extra.py":{"cognitive_mass":7,"functions":2,"max_lines":9,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_trans_phases.py":{"cognitive_mass":0,"functions":1,"max_lines":10,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/trans_phases.c":{"cognitive_mass":7,"functions":6,"max_lines":15,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0}
},"litter":[],"process_identifiers":[]}
```
<!-- /quality-baseline -->

The local HANDOFF.md is retired; README links to the ecosystem handoff.

The default sparse-PPC regression now includes the repaired sine witness
and exponent family described above. The broader full-domain elementary
and PPC arithmetic obligations remain open; no full gate or new council
CLEAR claim follows from the re-pin checks.
