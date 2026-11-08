# Arithmetic quality floor

## Tiny paired PPC results

The tiny-argument table now covers both fields of `sincos` and `sincospi`,
including scalar `cos`. At `x=2^-700`, cosine rounds to `(1,+0)` in
nearest/even, upward and nearest/away modes, and `(1,-2^-1074)` downward
or toward zero. Sine uses the same signed analytic correction as scalar
`sin`. The cosine path retains the exact input square and six Taylor terms
at 4350 fractional bits before rounding; adding the tail to a 240-bit `1`
would discard the sparse residual. The existing global accuracy obligations
remain unchanged.

The MPFR-bracket tiny family checks both signs, all five modes, both paired
fields, flags and unrelated sticky-bit preservation. Its quick selection
also covers cosine quantum transitions, normal/subnormal endpoints and
four sparse two-component inputs. Both LLVM versions pass 1540 tiny checks
within `timeout 1200s python3 -B -I tests/test_directed.py 18 23 --quick`
(13510 total checks per major).
The initial family failed on both publications at `4cba9a9`; an independent
field inventory found scalar cosine, both `sincos` fields and `sincospi`
cosine wrong (290 field mismatches per major in the original 730-call family).

Both publications and test bridges were regenerated with `scripts/build 18`
and `scripts/build 23` under a user systemd scope with `MemoryMax=6G`, after
checking at least 6 GB available and load1 below 8. `tests/test_contract.py`
passes for both majors. The quality baseline is unchanged. Inspection of
aggregate exports and secondary outputs finds only `sincos`, `sincospi`,
`frexp` and `modf`; the latter two use exact decomposition/scaling paths,
so they do not bypass a transcendental correction table.

Final default validation was
`timeout 1200s systemd-run --user --scope
--unit=bennett-arith-paired-efficient-default -p MemoryMax=6G scripts/test`:
**36 tests passed, 89.822 s test body, 120.59 s wall time**, exit 0,
peak RSS 175580 KB. Preflight available memory was 14001930240 bytes and
load1 4.9644. The first fixed-point implementation passed in 239.41 s wall;
keeping the square unscaled, bounding its multiplication width from the
input domain, and stopping at a zero term preserves the arithmetic while
meeting the inherited 180 s default target. The accumulator precision and
quality baseline did not change.

No ISA circuit publication changed. The circuit manifest SHA-256 remains
`d8b11db684390251fb5d89510c6b79c6352a40be2118c5faa25da81ecc9aad2c`;
the existing full-publication receipt below remains applicable. No full
publication test or gate was rerun.

## Default and exhaustive checks

Default after the R40 receipt changes: `timeout 1200s systemd-run --user
--scope --unit=bennett-arith-quality-default -p MemoryMax=6G scripts/test`,
**36 tests passed in 72.97 s wall time** (55.963 s test body), exit 0.
The build started with 24 GB available (`free -g`) and load1 2.4741.
The test count changed because two pairs of metadata/reproduction checks
were consolidated and the guard regression was added; all checks remain.
The earlier cold run at 94cf09f passed 37 tests in 72.07 s after all six
bridge/support outputs were moved aside. Both runs regenerate and relink
support despite existing outputs. The ISA reader pin is
`62a0cf0ef9f1f1c1db12c84ed24846b6b9695cdc` (ISA 0.9 K94); the dialect pin is
`95a4b8d06933018a07fef3516296a25fd582fcde` (0.2.13). Both pins were
materialised and confirmed pushed by the pinned gate tool's `verify`
operation. A final ISA `git log -1 origin/main` still names the exact K94 pin.
Publication metadata still identifies its governing base text
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
  changed for this second re-pin. All 129 publication receipts now complete,
  covering 116 proofs and 105 evidence claims, resolving `bennett-arith-jn3`.
  Diagnostic execution coverage remains separate from raw certificate proof
  evidence.
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

The original scalar repair added a default eight-exponent family (both signs,
all five modes, all six operations) and the sparse exp witness, independently
rounded from MPFR bounds. That family's full form enumerated every exponent
358..1074; the paired expansion and its current quick counts are recorded above:
**43,030 exact value/flag checks passed on each LLVM major**, using
`timeout 1200s python3 -B -I tests/test_directed.py 18 23 --tiny-only`.
The `2^-358` endpoint was separately observed RED after the initial
conservative cutoff, before extending that cutoff. Quick directed
runs `timeout 240s python3 -B -I tests/test_directed.py 18 --quick` and the
corresponding `23 --quick` passed **12,460 checks each**. No tolerance or
baseline changed.

ISA 0.9 K91 at be109bd §12.3 requires canonical `token_aliases` and a
reader implementing its upgraded schema. Publications retain that metadata.
`Published.test_raw_publications_admitted` admits every manifest file and
replays every stored claim using the gate-pinned reader's public
`Object::verify_certificate` API. It asserts nonempty reports, exact claim
counts, matching object/interface identities, Established K92 applicability,
and Proof/Evidence-only outcomes. Structural `adjoint_table` claims require
Proof. The bridge links to the library beside the pinned reader binary;
CLI admission alone does not establish a certificate claim.

Red-first history: the old ecaaac0 reader rejected `token_aliases` in all 129
publications before replay. Adopting the upgraded API exposed six modular
K4 inverse-pair subjects bound to `g` rather than their owning action;
an owner-local regression failed before that binding was fixed. No body,
closure identity, partition or inverse-pair domain changed. Reader 3b10907
then reported the structural claims Unverified because their premises were
unspecified. Pin commit cf4af47 adopts pushed ISA 0.9 K94 at
`62a0cf0ef9f1f1c1db12c84ed24846b6b9695cdc`, which specifies and checks those
premises. A focused replay established all 37 structural claims as proof,
including the original `arith.bij.sub.w1` claim 1 witness. The universal
invocations, budgets, domains and K91 partitions were retained.

The bridge prints every accepted claim and a complete receipt. Unverified
is an explicit failing outcome, distinct from Rejected; a deliberately
mutated Cuccaro claim `0+0=1` rejects at §12.1 K13 full-tuple mismatch.
Image-relative or sampled structural claims also fail. Diagnostic table
replays retain the independent four-tuple width-one Cuccaro assertion,
including `[1,0] -> [1,1]` with phase exactly +1.

### Completed publication measurements

The earlier 600 s stage limits failed on three large receipts under load:
addmod replay stopped at 600.03 s, muladd admission at 600.21 s, and mul
admission at 600.18 s. The former test called `self.fail()` on those guards.
A 1200 s serial outer timeout also failed to produce a complete manifest
receipt. None of those outcomes was a refutation or a proof.

The requested once-only measurements ran serially on this 12-core/30-GB
host on **2026-11-07**, each under `/usr/bin/time -v`, `timeout 5400s` and
`systemd-run --user --scope --unit=bennett-heavy-arith-measure -p MemoryMax=6G`.
Before each start, `free -g` showed at least 6 GB available, load1 was below
8, and no other `bennett-heavy` scope was active. No 600 s inner limit applied.

| Publication and measured stage | Wall seconds | Peak RSS, KB | Result | Preflight available GB / load1 |
|---|---:|---:|---|---:|
| `arith.bij.addmod.w8.mfb`, full four-claim replay | 868.48 | 21,960 | Two sampled Evidence, two inverse-pair Proof; K92 Established | 23 / 1.23 |
| `arith.muladd.karatsuba.w32.r64`, admission | 465.91 | 1,086,448 | Accepted; matching published identity, no unresolved imports | 23 / 0.86 |
| `arith.mul.karatsuba.w32.r64`, admission | 473.02 | 972,712 | Accepted; matching published identity, no unresolved imports | 24 / 1.50 |

An earlier mul admission attempt was stopped after 17.64 s because its shell
continued after a failed resource preflight. That attempt is explicitly
discarded and does not set a guard. The corrected launcher starts work only
after its resource predicate succeeds. Quiet Karatsuba admissions completed
below 600 s despite the earlier loaded attempts timing out there; absolute
time is not a deterministic correctness assertion.

The required full publication test ran **once**, with the same preflight
rule (24 GB available, load1 4.2285, no other heavy scope), using:

```sh
/usr/bin/time -v -o .tmp/quality-arith/measure-full-publications.time timeout 7200s systemd-run --user --scope --unit=bennett-heavy-arith-measure -p MemoryMax=6G /usr/bin/python3 -B -I tests/circuits/test_objects.py
```

It passed **7 tests in 3158.577 s test-body time**, **3158.68 s wall**,
peak RSS **1,086,736 KB**, exit 0. The runner reported
**selected=129, COMPLETE=129, UNKNOWN=0, FAILED=0**, with **221 accepted
claims: 116 Proof and 105 Evidence**, including all **37 structural proofs**.
Both Karatsuba publications' single sampled claim completed as Evidence;
K92 applicability was Established. The addmod receipt completed its four
claims as two Proof and two Evidence. These are complete receipts rather
than admission-only results. `bennett-arith-jn3` is resolved; the earlier
K91/K94 rejection beads `bennett-arith-emu` and `bennett-arith-4ss` were
already resolved.

The live full run loaded 09e97d3. Logging-only commit d10fdf7 subsequently
added admission/replay durations to future completion lines; the selected
inputs, assertions and guards are identical. The actual transcript retains
its original total-only format. A read-only observer recovered kernel
process-start ticks and confirmed process exits, yielding conservative
phase wall upper bounds without rerunning or modifying a stage:

| Publication | Admission upper bound, seconds | Replay upper bound, seconds | Guard for each stage, seconds |
|---|---:|---:|---:|
| `arith.bij.addmod.w8.mfb` | Included in 853.55 s whole receipt | 853.67 | 8684.80 |
| `arith.muladd.karatsuba.w32.r64` | 444.08 | 452.52 | 4659.10 |
| `arith.mul.karatsuba.w32.r64` | 405.33 | 391.15 | 4730.20 |

Each per-entry guard is ten times the slower completed measurement across
its admission and replay stages, including the once-only measurements
above. The ordinary-publication guard is 5046 s, based on the earlier
504.60 s completed ordinary receipt including both stages; the largest
ordinary receipt in this full run was 205.74 s. Comments beside the named
constants cite measured values, this host and 2026-11-07. The separate
bridge-compilation guard is 60 s, based on a 0.108 s compile/link measurement
on the same host/date.

R40 guard expiry produces an explicit **UNKNOWN** receipt, printed
immediately and counted/listed at the end. UNKNOWN contributes **zero**
accepted claims. COMPLETE and FAILED are counted separately; completed
refuted, rejected or Unverified claims still fail. Compilation expiry marks
every selected receipt UNKNOWN before admission starts. The circuits runner
footer points to these statuses. Tests assert claim counts, identities,
full replay tuples and verdicts; they do not assert absolute seconds.

The deterministic guard regression failed against the old `self.fail()`
policy and passes for both admission and replay expiry. It also checks
completed valid work and propagation of invalid status, Rejected and
Unverified errors. Synthetic direct-runner probes attempted all 129 entries:
guarded work yielded UNKNOWN=129, COMPLETE=0, accepted claims=0, exit 0,
with all UNKNOWN entries listed; completed invalid work yielded FAILED=129,
accepted claims=0 and exit 1. A compilation-guard probe reported UNKNOWN=129
without attempting admission. Reproducibility and manifest checks share a
test, and the K91/inverse-pair traversal covers generated examples and every
publication. A permanent negative probe ensures generated examples cannot
satisfy the published-only inverse-pair count when the manifest is empty.
All original assertions remain, with budget typing additionally rejecting
booleans. The quality baseline is unchanged for all 55 source files.

The raw transcript, `/usr/bin/time -v` output, preflight, per-claim/per-entry
validation and phase envelopes are in `.tmp/quality-arith/` as
`measure-full-publications.log`, `measure-full-publications.time`,
`measure-full-publications-preflight.log`, `full-publication-receipts.json`
and `full-publication-phase-envelopes.json`. The transcript validator checks
every manifest entry and stored claim, rejecting missing or duplicate
reports; manifest SHA-256 is
`d8b11db684390251fb5d89510c6b79c6352a40be2118c5faa25da81ecc9aad2c`.
No full eight-hour gate was run; the orchestrator owns it.

<details>
<summary>All 129 completed receipts: measured wall time and accepted claim counts</summary>

Times below include admission and full certificate replay; these are
observations, not performance assertions. Every row is COMPLETE.

| Publication root | Wall seconds | Proof | Evidence |
|---|---:|---:|---:|
| `arith.add.cuccaro.w1` | 0.01 | 1 | 0 |
| `arith.add.cuccaro.w2` | 0.01 | 1 | 0 |
| `arith.add.cuccaro.w3` | 0.02 | 1 | 0 |
| `arith.add.cuccaro.w4` | 0.05 | 1 | 0 |
| `arith.add.cuccaro.w8` | 0.03 | 0 | 1 |
| `arith.add.cuccaro.w16` | 0.04 | 0 | 1 |
| `arith.add.cuccaro.w32` | 0.09 | 0 | 1 |
| `arith.add.cuccaro.w64` | 0.26 | 0 | 1 |
| `arith.add.cuccaro.w128` | 1.27 | 0 | 1 |
| `arith.add.cuccaro_carry.w1` | 0.01 | 1 | 0 |
| `arith.add.cuccaro_carry.w2` | 0.02 | 1 | 0 |
| `arith.add.cuccaro_carry.w3` | 0.04 | 1 | 0 |
| `arith.add.cuccaro_carry.w4` | 0.02 | 0 | 1 |
| `arith.add.cuccaro_carry.w8` | 0.02 | 0 | 1 |
| `arith.add.cuccaro_carry.w16` | 0.05 | 0 | 1 |
| `arith.add.cuccaro_carry.w32` | 0.09 | 0 | 1 |
| `arith.add.cuccaro_carry.w64` | 0.26 | 0 | 1 |
| `arith.add.cuccaro_carry.w128` | 1.39 | 0 | 1 |
| `arith.add.gidney.w1` | 0.01 | 1 | 0 |
| `arith.add.gidney.w2` | 0.01 | 1 | 0 |
| `arith.add.gidney.w3` | 0.03 | 1 | 0 |
| `arith.add.gidney.w4` | 0.05 | 1 | 0 |
| `arith.add.gidney.w8` | 0.02 | 0 | 1 |
| `arith.add.gidney.w16` | 0.05 | 0 | 1 |
| `arith.add.gidney.w32` | 0.28 | 0 | 1 |
| `arith.add.gidney.w64` | 1.62 | 0 | 1 |
| `arith.add.gidney.w128` | 13.37 | 0 | 1 |
| `arith.add.ripple.w1` | 0.01 | 1 | 0 |
| `arith.add.ripple.w2` | 0.05 | 1 | 0 |
| `arith.add.ripple.w3` | 0.03 | 0 | 1 |
| `arith.add.ripple.w8` | 0.04 | 0 | 1 |
| `arith.add.ripple.w16` | 0.05 | 0 | 1 |
| `arith.add.ripple.w32` | 0.16 | 0 | 1 |
| `arith.add.ripple.w64` | 0.51 | 0 | 1 |
| `arith.add.qcla.w1` | 0.02 | 1 | 0 |
| `arith.add.qcla.w2` | 0.04 | 1 | 0 |
| `arith.add.qcla.w3` | 0.02 | 0 | 1 |
| `arith.add.qcla.w8` | 0.04 | 0 | 1 |
| `arith.add.qcla.w16` | 0.08 | 0 | 1 |
| `arith.add.qcla.w32` | 0.23 | 0 | 1 |
| `arith.add.qcla.w64` | 0.69 | 0 | 1 |
| `arith.bij.add.w1` | 0.02 | 3 | 0 |
| `arith.bij.add.w2` | 0.03 | 3 | 0 |
| `arith.bij.add.w3` | 0.05 | 3 | 0 |
| `arith.bij.add.w4` | 0.15 | 3 | 0 |
| `arith.bij.add.w8` | 0.08 | 1 | 2 |
| `arith.bij.add.w16` | 0.09 | 1 | 2 |
| `arith.bij.add.w32` | 0.24 | 1 | 2 |
| `arith.bij.add.w64` | 1.09 | 1 | 2 |
| `arith.bij.add.w128` | 6.98 | 1 | 2 |
| `arith.bij.xor.w1` | 0.02 | 3 | 0 |
| `arith.bij.xor.w2` | 0.02 | 3 | 0 |
| `arith.bij.xor.w3` | 0.02 | 3 | 0 |
| `arith.bij.xor.w4` | 0.10 | 3 | 0 |
| `arith.bij.xor.w8` | 0.02 | 1 | 2 |
| `arith.bij.xor.w16` | 0.04 | 1 | 2 |
| `arith.bij.xor.w32` | 0.04 | 1 | 2 |
| `arith.bij.xor.w64` | 0.08 | 1 | 2 |
| `arith.bij.xor.w128` | 0.13 | 1 | 2 |
| `arith.bij.neg.w1` | 0.02 | 3 | 0 |
| `arith.bij.neg.w2` | 0.01 | 3 | 0 |
| `arith.bij.neg.w3` | 0.02 | 3 | 0 |
| `arith.bij.neg.w4` | 0.02 | 3 | 0 |
| `arith.bij.neg.w8` | 0.14 | 3 | 0 |
| `arith.bij.neg.w16` | 0.08 | 1 | 2 |
| `arith.bij.neg.w32` | 0.17 | 1 | 2 |
| `arith.bij.neg.w64` | 0.76 | 1 | 2 |
| `arith.bij.neg.w128` | 4.64 | 1 | 2 |
| `arith.bij.bswap.w16` | 0.04 | 1 | 2 |
| `arith.bij.bswap.w32` | 0.04 | 1 | 2 |
| `arith.bij.bswap.w64` | 0.08 | 1 | 2 |
| `arith.bij.bswap.w128` | 0.08 | 1 | 2 |
| `arith.bij.addk.w8.k1` | 0.20 | 3 | 0 |
| `arith.bij.addk.w32.k1` | 0.16 | 1 | 2 |
| `arith.bij.addk.w64.k1` | 0.70 | 1 | 2 |
| `arith.bij.xork.w8.kff` | 0.09 | 3 | 0 |
| `arith.bij.rotl.w8.r3` | 0.09 | 3 | 0 |
| `arith.bij.rotl.w32.r7` | 0.05 | 1 | 2 |
| `arith.bij.addmodk.w4.k5.mb` | 0.79 | 4 | 0 |
| `arith.bij.addmodk.w8.k64.mfb` | 12.22 | 4 | 0 |
| `arith.bij.addmod.w4.mb` | 13.83 | 4 | 0 |
| `arith.bij.addmod.w8.mfb` | 853.55 | 2 | 2 |
| `arith.bij.mulmodk.w4.k5.mb` | 0.69 | 4 | 0 |
| `arith.bij.mulmodk.w8.k11.mfb` | 11.47 | 4 | 0 |
| `arith.muladd.school.w1.r2` | 0.01 | 1 | 0 |
| `arith.mul.school.w1.r2` | 0.01 | 1 | 0 |
| `arith.muladd.school.w2.r4` | 0.08 | 1 | 0 |
| `arith.muladd.school.w2.r2` | 0.03 | 1 | 0 |
| `arith.mul.school.w2.r4` | 0.13 | 1 | 0 |
| `arith.mul.school.w2.r2` | 0.03 | 1 | 0 |
| `arith.muladd.school.w3.r6` | 0.03 | 0 | 1 |
| `arith.muladd.school.w3.r3` | 0.03 | 0 | 1 |
| `arith.mul.school.w3.r6` | 0.05 | 0 | 1 |
| `arith.mul.school.w3.r3` | 0.04 | 0 | 1 |
| `arith.muladd.school.w4.r8` | 0.05 | 0 | 1 |
| `arith.muladd.school.w4.r4` | 0.03 | 0 | 1 |
| `arith.mul.school.w4.r8` | 0.09 | 0 | 1 |
| `arith.mul.school.w4.r4` | 0.04 | 0 | 1 |
| `arith.muladd.school.w8.r16` | 0.25 | 0 | 1 |
| `arith.muladd.school.w8.r8` | 0.09 | 0 | 1 |
| `arith.mul.school.w8.r16` | 0.49 | 0 | 1 |
| `arith.mul.school.w8.r8` | 0.15 | 0 | 1 |
| `arith.muladd.school.w16.r32` | 3.52 | 0 | 1 |
| `arith.muladd.school.w16.r16` | 0.36 | 0 | 1 |
| `arith.mul.school.w16.r32` | 7.09 | 0 | 1 |
| `arith.mul.school.w16.r16` | 0.75 | 0 | 1 |
| `arith.muladd.school.w32.r64` | 103.51 | 0 | 1 |
| `arith.muladd.school.w32.r32` | 7.56 | 0 | 1 |
| `arith.mul.school.w32.r64` | 205.74 | 0 | 1 |
| `arith.mul.school.w32.r32` | 15.36 | 0 | 1 |
| `arith.muladd.karatsuba.w2.r4` | 0.14 | 1 | 0 |
| `arith.mul.karatsuba.w2.r4` | 0.14 | 1 | 0 |
| `arith.muladd.karatsuba.w4.r8` | 0.14 | 0 | 1 |
| `arith.mul.karatsuba.w4.r8` | 0.10 | 0 | 1 |
| `arith.muladd.karatsuba.w8.r16` | 3.89 | 0 | 1 |
| `arith.mul.karatsuba.w8.r16` | 3.33 | 0 | 1 |
| `arith.muladd.karatsuba.w16.r32` | 57.28 | 0 | 1 |
| `arith.mul.karatsuba.w16.r32` | 51.52 | 0 | 1 |
| `arith.muladd.karatsuba.w32.r64` | 896.38 | 0 | 1 |
| `arith.mul.karatsuba.w32.r64` | 796.34 | 0 | 1 |
| `arith.mul.tree.w2` | 0.08 | 1 | 0 |
| `arith.mul.tree.w4` | 0.16 | 0 | 1 |
| `arith.mul.tree.w8` | 2.05 | 0 | 1 |
| `arith.mul.tree.w16` | 50.46 | 0 | 1 |
| `arith.qrom.n3.w2.te0c3e191134bfb05` | 0.04 | 1 | 0 |
| `arith.qrom.n4.w8.t2a91cc1790fe9fbc` | 0.04 | 0 | 1 |
| `arith.qrom_ss.k2.n4.w8.t2a91cc1790fe9fbc` | 0.08 | 0 | 1 |
| `arith.qrom_ssd.k1.n3.w2.te0c3e191134bfb05` | 0.04 | 0 | 1 |
| `arith.qrom_ssd.k2.n4.w8.t2a91cc1790fe9fbc` | 0.11 | 0 | 1 |

</details>

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

## Central hang-guard classes

`tests/timeouts.toml` is the only clock-budget table. All test/script clocks,
including the offline instantiation CLI, select `short`, `moderate`, `long` or
`eternal` through `scripts/time_guard.py`. A single machine/config factor scales
every class; the runner rejects a class below ten times its cited measurement.
The R40 publication and bridge citations remain in the table. Publication bytes,
bitcode and correctness assertions are unchanged; the two softfloat source hashes
and their manifest checksums are refreshed as derived provenance metadata.

Each guarded command emits a JSON `command_receipt` with argv, class, wall and
CPU seconds, exit code and state, and appends the same row to
`$TMPDIR/command-receipts.jsonl` so captured child output cannot hide a receipt. CPU accounting uses wait4 for the specific
child, including concurrent reference-interpreter calls. Usage below 10% or
above 50% of the class produces a warning, never a performance assertion.
Timeouts terminate descendants and report `UNKNOWN/TIMEOUT`; they establish no
proof or evidence. Standalone commands/suites retain exit 124. Explicit
`--gate-check` mode exits zero on an UNKNOWN after emitting that receipt, per
the gate's own-check convention; real command failures still propagate.
Publication receipts retain COMPLETE/UNKNOWN/FAILED and UNKNOWN claims count zero.

The one provisional row is `eternal`: the current exhaustive `scripts/gate`
workload has no completed total. The table cites the historical 703.1 s gate
(2026-11-02), the 3158.68 s full publication run (2026-11-07), and the existing
per-entry receipts. **bennett-arith-b0z** requires the first future full gate to
supply the current envelope and per-command measurements. No full gate or full
publication test is rerun for this sweep.

Red-first commit `6ac74b8` rejected the original inventory; the completed
inventory is `.tmp/sweep-time-arith/inventory.md` (37 constants/fixtures).
The lint covers scripts, tests including softfloat tests, the instantiation CLI,
and all configuration formats; only the table and lint fixtures are exempt.
The existing quality baseline values are preserved. Four new source files get
initial entries; no existing file's allowance is raised.

Focused validation (all exited zero, class guards from the table):

- `python3 -B -I scripts/time_guard.py moderate scripts/test`: 45 tests,
  79.545 s body, 101.759527 s wall and 101.386932 CPU seconds.
- `python3 -B -I scripts/time_guard.py short python3 -B -I tests/test_time_guard.py`:
  six tests; UNKNOWN propagation, gate zero status versus real failures, CPU
  accounting, class margin/factor and persistent receipt output.
- `python3 -B -I scripts/time_guard.py short python3 -B -I tests/test_time_literals.py`:
  three tests, including the full scoped repository scan.
- `python3 -B -I scripts/time_guard.py moderate python3 -B -I tests/test_default_cache.py DefaultPreparation.test_support_sources_and_missing_outputs_are_refreshed`:
  one focused cache fixture passed in 51.573675 s wall.
- `python3 -B -I scripts/time_guard.py moderate python3 -B -I tests/test_compare_closure.py`:
  both LLVM majors passed all 15 closure checks, 6.191647 s wall.
- The small `softfloat/instantiate.py` LLVM18 f16/i8 request emitted bitcode and
  manifest byte-identical to the base implementation (both exports checked),
  19.669887 s including both builds. The differential script and logs are under
  `.tmp/sweep-time-arith/`. No exhaustive numerical suite was run.

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
"scripts/time_guard.py":{"cognitive_mass":25,"functions":11,"max_lines":24,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"scripts/time_literals.py":{"cognitive_mass":87,"functions":2,"max_lines":35,"over_100":0,"over_200":0,"over_25":1,"over_300":0,"over_50":0,"trivial_wrappers":0},
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
"tests/test_time_guard.py":{"cognitive_mass":9,"functions":6,"max_lines":14,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
"tests/test_time_literals.py":{"cognitive_mass":1,"functions":3,"max_lines":15,"over_100":0,"over_200":0,"over_25":0,"over_300":0,"over_50":0,"trivial_wrappers":0},
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
