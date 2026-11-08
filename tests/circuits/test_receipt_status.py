"""Publication verdicts survive the circuits runner and gate-check wrapper."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from time_guard import seconds, test_main  # noqa: E402
sys.path.insert(0, str(ROOT / "tests/circuits"))
from publication_receipts import Receipt, ReceiptState, report_receipts  # noqa: E402

POLICY = ("A gate with any UNKNOWN publication receipt is UNKNOWN, not PASS and not FAIL: it exits 124; "
          "re-run only the UNKNOWN receipts once in a quiet slot; a second UNKNOWN on the same receipt is a bead; "
          "nothing merges or pushes on UNKNOWN.")
ENTRIES = json.loads((ROOT / "adders/objects/manifest.json").read_text())["entries"]

# Only admission/replay and the unittest selection are mocked. The publication
# entry point, shell runner and both process guards execute their real code.
PROBE = r'''
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

root = Path(os.environ["RECEIPT_PROBE_ROOT"])
sys.path[:0] = [str(root / "scripts"), str(root / "tests/circuits")]
import harness
import time_guard

entries = json.loads((root / "adders/objects/manifest.json").read_text())["entries"]
by_file = {entry["file"]: entry["root"] for entry in entries}
outcomes = json.loads(os.environ["RECEIPT_PROBE_OUTCOMES"])
trace = Path(os.environ["RECEIPT_PROBE_TRACE"])

def run(argv, *, guard_class, **kwargs):
    stage = "compile" if argv[0] == "rustc" else "admission" if argv[0] == "admission" else "replay"
    assert guard_class == ("short" if stage == "compile" else "long"), (stage, guard_class)
    name = "compile" if stage == "compile" else by_file[Path(argv[1]).relative_to(root).as_posix()]
    with trace.open("a") as stream:
        stream.write(json.dumps([stage, name]) + "\n")
    outcome = outcomes.get(name, "COMPLETE")
    if outcome == stage + "-UNKNOWN":
        raise subprocess.TimeoutExpired(argv, time_guard.seconds(guard_class))
    if stage == "replay" and outcome in ("Rejected", "Unverified"):
        raise subprocess.CalledProcessError(1, argv, stderr=outcome)
    return subprocess.CompletedProcess(argv, 0)

def check(path, *, guard_class):
    run(["admission", str(path)], guard_class=guard_class)
    cert = json.loads(path.read_text().rpartition("section certificate\n")[2])
    entry_root = by_file[path.relative_to(root).as_posix()]
    return {"status": "invalid" if outcomes.get(entry_root) == "FAILED" else "ok",
            "object_hash": cert["bindings"]["object_hash"],
            "symbols": {"arith.add.cuccaro.w1": {
                "interface_hash": "0e350e9c21db62e93d801271076c0f77424fb2ca4f0986a856a8312102036dae"}}}

original_main = time_guard.test_main
def receipt_main(**kwargs):
    kwargs["defaultTest"] = "Published.test_raw_publications_admitted"
    return original_main(**kwargs)

reader = Path(os.environ["RECEIPT_PROBE_READER"])
with patch.object(harness, "RefInterp", return_value=SimpleNamespace(binary=reader, check=check)), \
        patch.object(time_guard, "run", side_effect=run), \
        patch.object(time_guard, "test_main", side_effect=receipt_main):
    runpy.run_path(str(root / "tests/circuits/test_objects.py"), run_name="__main__")
'''


class ReceiptStatus(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.fixture = Path(self.temp.name)
        for name in ("scripts/time_guard.py", "tests/timeouts.toml", "tests/circuits/run"):
            destination = self.fixture / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        circuits = self.fixture / "tests/circuits"
        for name in ("test_pins", "test_adders", "test_multipliers", "test_qrom", "test_receipt_status"):
            (circuits / (name + ".py")).write_text("print('UNRELATED SUITE')\n")
        (circuits / "test_objects.py").write_text(PROBE)
        (self.fixture / "deps").mkdir()
        (self.fixture / "deps/libbennett_isa_ref-probe.rlib").touch()

    def probe(self, outcomes, selection=None):
        env = {k: v for k, v in os.environ.items() if k != "BENNETT_ARITH_RECEIPTS"}
        env.update(RECEIPT_PROBE_ROOT=str(ROOT), RECEIPT_PROBE_OUTCOMES=json.dumps(outcomes),
                   RECEIPT_PROBE_TRACE=str(self.fixture / "trace.jsonl"),
                   RECEIPT_PROBE_READER=str(self.fixture / "reader"))
        if selection is not None:
            env["BENNETT_ARITH_RECEIPTS"] = selection
        return subprocess.run([sys.executable, "-B", "-I", str(ROOT / "scripts/time_guard.py"), "short",
                            "--gate-check", "bash", str(self.fixture / "tests/circuits/run")],
                              timeout=seconds("short"), capture_output=True, text=True, env=env)

    def test_one_unknown_never_passes(self):
        done = self.probe({ENTRIES[1]["root"]: "replay-UNKNOWN"})
        self.assertEqual(done.returncode, 124, done.stdout + done.stderr)
        self.assertIn(f"COMPLETE={len(ENTRIES) - 1} UNKNOWN=1 FAILED=0", done.stdout)
        self.assertIn(POLICY, done.stdout)

    def test_all_complete_passes(self):
        done = self.probe({})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"COMPLETE={len(ENTRIES)} UNKNOWN=0 FAILED=0", done.stdout)
        self.assertIn(POLICY, done.stdout)

    def test_summary_exit_status(self):
        for states, expected in (((ReceiptState.COMPLETE,), 0), ((ReceiptState.UNKNOWN,), 124),
                                 ((ReceiptState.FAILED,), 1), ((ReceiptState.UNKNOWN, ReceiptState.FAILED), 1)):
            with self.subTest(states=states), redirect_stdout(StringIO()) as output:
                receipts = {str(i): Receipt(state, state.value, 0, 0.0) for i, state in enumerate(states)}
                self.assertEqual(report_receipts(receipts), expected)
                self.assertIn(POLICY, output.getvalue())

    def test_failed_wins_over_unknown_in_either_order(self):
        for failed in ("FAILED", "Rejected", "Unverified"):
            for first, second in ((0, 1), (1, 0)):
                with self.subTest(failed=failed, first=first):
                    done = self.probe({ENTRIES[first]["root"]: failed, ENTRIES[second]["root"]: "replay-UNKNOWN"})
                    self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                    self.assertIn(f"COMPLETE={len(ENTRIES) - 2} UNKNOWN=1 FAILED=1", done.stdout)

    def test_selection_runs_only_named_receipts(self):
        roots = [ENTRIES[1]["root"], ENTRIES[2]["root"]]
        done = self.probe({roots[1]: "admission-UNKNOWN"}, ",".join(roots))
        self.assertEqual(done.returncode, 124, done.stdout + done.stderr)
        self.assertIn("selected=2 COMPLETE=1 UNKNOWN=1 FAILED=0", done.stdout)
        self.assertNotIn("UNRELATED SUITE", done.stdout)
        trace = [json.loads(line) for line in (self.fixture / "trace.jsonl").read_text().splitlines()]
        self.assertEqual(trace, [["compile", "compile"], ["admission", roots[0]], ["replay", roots[0]], ["admission", roots[1]]])
        retry = next(line for line in done.stdout.splitlines() if line.startswith("BENNETT_ARITH_RECEIPTS="))
        self.assertEqual(retry, f"BENNETT_ARITH_RECEIPTS={roots[1]} tests/circuits/run")
        (self.fixture / "trace.jsonl").unlink()
        complete = self.probe({}, retry.split("=", 1)[1].split()[0])
        self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
        self.assertIn("selected=1 COMPLETE=1 UNKNOWN=0 FAILED=0", complete.stdout)
        self.assertNotIn("UNRELATED SUITE", complete.stdout)

    def test_invalid_selection_fails_before_guarded_work(self):
        for selection in ("", "missing.receipt", ENTRIES[0]["root"] + ",", "," + ENTRIES[0]["root"]):
            with self.subTest(selection=selection):
                done = self.probe({}, selection)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertIn("invalid BENNETT_ARITH_RECEIPTS", done.stdout + done.stderr)
                self.assertFalse((self.fixture / "trace.jsonl").exists())

    def test_bridge_timeout_marks_only_selected_receipts_unknown(self):
        root = ENTRIES[1]["root"]
        done = self.probe({"compile": "compile-UNKNOWN"}, root)
        self.assertEqual(done.returncode, 124, done.stdout + done.stderr)
        self.assertIn("selected=1 COMPLETE=0 UNKNOWN=1 FAILED=0", done.stdout)
        self.assertIn(f"BENNETT_ARITH_RECEIPTS={root} tests/circuits/run", done.stdout)


if __name__ == "__main__":
    test_main()
