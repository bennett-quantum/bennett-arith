# sweep-time-arith review, round 1

Reviewed `28033c5..a6e3055210646ddf5261802155ba531c90c3d71d` on
`job/sweep-time-arith`; the base is the arith local main specified in the brief.
**Verdict: BLOCK.** No P0 findings; one P1.

**P1-1 — gate: UNKNOWN becomes PASS** (`bennett-arith-bq6`).
`scripts/time_guard.py:159` returns zero after a timeout in `--gate-check` mode,
which `gate.toml:8`, `:12`, `:16`, and `:20` enable for every check. Thus a hang
guard that interrupts numerical checks or certificate replay produces an UNKNOWN
receipt but satisfies the push gate. The pinned tool's `gate_one` accepts a
check solely by its zero exit status; it does not inspect those receipts.
This contradicts COMMON standing rule 4's distinct nonzero UNKNOWN status and
prevents the orchestrator's required quiet-slot retry. The implementation's
earlier exit-zero interpretation is superseded by that binding rule.

Reproduced under the short-class outer `timeout 60`:

```sh
python3 -B -I scripts/time_guard.py short --gate-check python3 -c 'raise SystemExit(124)'
```

It emits `UNKNOWN/TIMEOUT` but exits **0**; removing `--gate-check` exits **124**.
The reviewer probe also ran just one synthetic check through the pinned tool's
`run_commands`: its recorded exit was 0 and the actual gate acceptance predicate
evaluated true. No gate preparation or full gate was invoked. Witness:
`.tmp/rev-sweep-time-arith-r1/tmp/review_probe.py`; evidence: `probe.log` in that
review directory. Propagate 124 through gate mode and change the regression at
`tests/test_time_guard.py:70`, which currently asserts the erroneous zero exit.

P2+ nits: `bennett-arith-b2a` (priority 3, review) groups the reproduced lint
bypasses at `scripts/time_literals.py:8`: quoted `timeout "60s"`,
`timeout -k 5s 60s`, and `Duration::from_secs_f64(0.1)` all return no violations.
The existing provisional-class follow-up remains `bennett-arith-b0z`.

Verification: headless, one focused command at a time, available memory above
6 GiB and load1 below 8 at every test launch; class-derived outer `timeout`,
one reference/numerical worker, build jobs 3 and Rust test threads 4. Commands
below use `python3 -B -I scripts/time_guard.py CLASS` before the listed command:

- `short python3 -B -I tests/test_time_guard.py`: six tests passed.
- `short python3 -B -I tests/test_time_literals.py`: three tests passed;
  the reviewer additionally applied the head lint to base sources, detecting
  35 locations (the original 29 plus six later-granted softfloat sites).
- `short python3 -B -I scripts/quality_metrics.py`: 59 files, no regression.
- `short python3 -B -I tests/circuits/test_objects.py Published.test_receipt_guards`:
  passed; UNKNOWN claims remain zero.
- `moderate python3 -B -I tests/test_compare_closure.py`: both LLVM majors passed
  all 15 closure checks.
- `moderate python3 -B -I tests/test_default_cache.py DefaultPreparation.test_support_sources_and_missing_outputs_are_refreshed`:
  passed, including the expected broken-source failure.
- `moderate python3 -B -I .tmp/rev-sweep-time-arith-r1/tmp/instance_parity.py`:
  unmodified base instantiation versus head produced identical LLVM18 f16/i8
  bitcode and manifest, with both exports checked.

All pre-existing quality-baseline values and both published bitcode blobs are
unchanged. All 37 inventory constants/fixtures were converted; class citations
and tenfold margins check out, with the eternal row explicitly provisional.
No converted correctness assertion was removed or weakened; the two softfloat
changes are time handling only. The gate ratchet remains registered and
`HANDOFF.md` remains retired. No new north-star narrowing found.

Coverage: closely read all source/config diffs, converted assertions, guard and
receipt paths, inventory, red/green evidence and anti-slop rules; skimmed
documentation/provenance diffs. Logs are under `.tmp/rev-sweep-time-arith-r1/`.
No full publication test, long numerical suites, full default suite or gate run.
The named implementation brief was absent; read the shared `sweep-time.md`
template and the review brief's explicit scope.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9).
