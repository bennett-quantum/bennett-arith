# Arithmetic quality floor

## Default and exhaustive checks

Default: `timeout 180s scripts/test`, 27 tests passed in 64.697 s on this
worktree with the reviewed ISA pin `ecaaac060c44e317d1181345fa6b8e38c096c099`.
The coverage-instrumented run passed the same 27 tests in 60.72 s wall time.
A missing LLVM18 bridge is built once by `scripts/test`; exhaustive vectors,
LLVM23 numeric sweeps and offline instantiation limits remain in `scripts/gate`.
No full eight-hour gate was run by this job; merge validation belongs to the orchestrator.

## Measured coverage

Python production statement coverage: **43.87%**
(684/1559 statements). This measures Python
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
* Named overflow: 112 independent LLVM23 APFloat comparisons passed. PPC
  zero-low parity: 12 hand-derived value/flag checks and 25491 exact-sum checks
  passed on each major after migration to dialect 0.2.13.
* `BENNETT_ARITH_PROMISED=1` exposes exact sparse-PPC libm failures
  (`bennett-arith-wvh`) and raw modular release validation
  (`bennett-arith-gdg`, `bennett-arith-vwi`). They remain red, with no restored
  tolerances. The pinned interpreter lacks K4 inverse-pair schema admission.
* K91 certificate partitions have unit tests against published ISA 0.9 text.
  No reviewed interpreter commit supporting them was available: the differential
  stays at ecaaac0, using an explicitly labelled diagnostic compatibility view.
  It cannot establish raw release compatibility (`bennett-arith-4ss`).
* Parity implementation is complete; `bennett-arith-4yg.1` remains open because
  its inherited release dependency on gdg prevents closure. No dependency override.

## Audit disposition

The core integer zero returns represent specified results: zero bit width and
invalid conversion accompanied by the invalid flag, respectively. They are not
quiet error fallbacks. Basic-operation oracle checks include negative square roots,
NaNs and exact zeros with sticky flags. The full gate retains the larger edge suite.

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
