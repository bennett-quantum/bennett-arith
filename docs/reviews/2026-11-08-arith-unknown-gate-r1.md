# arith-unknown-gate — review round 1

Reviewed range: local main `1fc22020ebc16408ba028ff2856c50e53fa024c5`..`d7024830d2b10ee52f2821021bc03e52642796e0`, branch `job/arith-unknown-gate` (one implementation commit). The explicit base is used throughout, irrespective of the current `main` ref.

Verdict: **CLEAR** — no P0/P1 findings in this change. P0/P1 IDs: none.

The circuits entry point, shell runner and `time_guard.py --gate-check` preserve UNKNOWN/124; FAILED/Rejected/Unverified wins in either receipt order. Counts and accepted claims cover only the selected publications; the retry command names exactly UNKNOWN roots. Empty/unknown selectors fail before guarded work. The pinned gate's `base_env` strips inherited `BENNETT_ARITH_RECEIPTS` with a diagnostic, so an exported selector cannot silently reduce the push gate. Its acceptance predicate requires every check exit to be zero.

P2+ nits: **bennett-arith-dum** (priority 3, review) — pre-existing external-tool gap: `gate.toml:4` pins tool `01c0314c9aaa4a37313ab530da2134efafe9cbd5`, whose `tools/gate_run.py:347`, `:444`, `:447`, `:448` classify a check exit 124 as aggregate FAIL/1. It rejects UNKNOWN safely, but the complete gate does **not** yet preserve UNKNOWN/124 as the printed ruling requires. Pin/tool behavior is unchanged at the base; policy rule 4 makes pre-existing gaps nonblocking. No other nits found.

Verification (headless, isolated review TMPDIR, serial, every test wrapped in `timeout` using the table's `short` seconds):

- `python3 -B -I scripts/time_guard.py short python3 -B -I tests/circuits/test_receipt_status.py`: 7 tests pass, 9.630 s.
- Same guarded invocation for `tests/test_time_guard.py`: 6 pass; `tests/circuits/test_objects.py Published.test_receipt_guards`: 1 pass; `scripts/quality_metrics.py`: 61 files, no regression.
- `BENNETT_ARITH_RECEIPTS=arith.add.cuccaro.w1 python3 -B -I scripts/time_guard.py short --gate-check tests/circuits/run`: exit 0, selected=1 COMPLETE=1 UNKNOWN=0 FAILED=0, one accepted proof; real pinned reader and freshly compiled bridge. Preflight load1=3.8, available memory=23,369,502,720 bytes; one rustc process, no Cargo build.
- Independent inline mocked probes executing `git show 1fc2202:tests/circuits/test_objects.py` with the base shell runner: all COMPLETE → 0; admission, replay and compilation UNKNOWN → 124; FAILED/Rejected/Unverified mixed with UNKNOWN → 1. No branch switch/worktree. Base guard is byte-identical to head. The original exit-zero premise is stale: red-first assertions concern missing policy/selection, not a new 124 behavior. Base code inspection agrees; no publication-UNKNOWN-to-zero path found.
- AST-only extraction of pinned environment filtering and acceptance/return expressions: inherited selector scrubbed loudly; [0] accepted/0; [124], [1], [0,124] rejected/1. No gate entry point or command runner executed.
- Independent baseline comparison: all 59 original metric rows unchanged, exactly two added file rows. `git diff --check 1fc2202...d702483` and `bash -n tests/circuits/run` pass.

Evidence logs: `.tmp/rev-arith-unknown-gate-r1/{receipt-status,time-guard,receipt-guards,quality,small-publication,base-probes,static-probes}.log`. No full publication test, full gate, sibling gate or gate-tool invocation.

Coverage: read closely all five changed files, implementer progress/red/green/small-publication evidence, base publication code, guard result handling, shell propagation, pinned environment/acceptance, and publication harness calls; skimmed historical quality documentation and sweep progress. Checked every COMMON anti-slop category: no new bug-hiding defaults, flag state, dispatch chains, repeated predicates, unexplained limits, oversized functions, trivial wrappers, process identifiers, litter or unsound expectations. Plan 9–11: ratchet remains in gate.toml; HANDOFF.md retired and README points to meta handoff; anti-slop checklist applied. No north-star capability narrowed. Full-gate validation remains the orchestrator's responsibility.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session (D9).
