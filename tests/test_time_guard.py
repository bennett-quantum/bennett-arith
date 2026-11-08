"""Hang guards preserve real failures and never turn incomplete work into proof."""
from contextlib import redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import time_guard as guard


class TimeGuards(unittest.TestCase):
    def test_class_citations_and_factor(self):
        self.assertEqual(set(guard.TABLE["classes"]), {"short", "moderate", "long", "eternal"})
        for name, row in guard.TABLE["classes"].items():
            self.assertGreaterEqual(guard.seconds(name), guard.TABLE["measurement_margin"] * max(m["wall_seconds"] for m in row["measurements"]))
            for measurement in row["measurements"]:
                self.assertTrue(all(measurement[k] for k in ("command", "date", "source")))
        with patch.dict(guard.TABLE, machine_config_factor=2):
            self.assertEqual(guard.seconds("short"), 2 * guard.TABLE["classes"]["short"]["seconds"])

    def test_receipt_and_nonzero_command(self):
        with redirect_stderr(StringIO()) as stream:
            done = guard.run([sys.executable, "-c", "print(sum(range(10000)))"], capture_output=True, text=True, check=True, guard_class="short")
        self.assertEqual(done.stdout.strip(), "49995000")
        row = json.loads(stream.getvalue().splitlines()[0])
        self.assertEqual(row["state"], "COMPLETE")
        self.assertGreater(row["wall_seconds"], 0)
        self.assertGreater(row["cpu_seconds"], 0)
        receipts = Path(os.environ["TMPDIR"]) / "command-receipts.jsonl"
        self.assertIn(row, [json.loads(line) for line in receipts.read_text().splitlines()])
        with redirect_stderr(StringIO()), self.assertRaises(subprocess.CalledProcessError) as error:
            guard.run([sys.executable, "-c", "raise SystemExit(7)"], check=True)
        self.assertEqual(error.exception.returncode, 7)

    def test_timeout_is_unknown_and_kills_descendants(self):
        process = MagicMock()
        process.cpu_seconds = 0
        process.returncode = -9
        process.communicate.side_effect = [subprocess.TimeoutExpired("probe", guard.seconds("short")), (None, None)]
        with patch.object(guard, "TimedProcess") as factory, patch.object(guard, "kill_tree") as kill:
            factory.return_value.__enter__.return_value = process
            with redirect_stderr(StringIO()) as stream, self.assertRaises(subprocess.TimeoutExpired):
                guard.run(["probe"], guard_class="short")
        kill.assert_called_once_with(process.pid)
        self.assertEqual(json.loads(stream.getvalue().splitlines()[0])["state"], "UNKNOWN/TIMEOUT")
        self.assertNotIn('"state": "FAILED"', stream.getvalue())

    def test_unittest_timeout_aborts_before_verdict(self):
        result = guard.GuardedTestRunner(stream=StringIO())._makeResult()
        error = subprocess.TimeoutExpired("probe", guard.seconds("short"))
        with self.assertRaises(subprocess.TimeoutExpired):
            result.addError(self, (type(error), error, None))
        nested = subprocess.CalledProcessError(124, "nested probe")
        with self.assertRaises(subprocess.TimeoutExpired):
            result.addError(self, (type(nested), nested, None))
        with self.assertRaises(subprocess.TimeoutExpired):
            result.addSubTest(self, self, (type(error), error, None))
        self.assertEqual(result.errors, [])
        result.failures.append((self, "earlier mismatch"))
        with self.assertRaises((SystemExit, subprocess.TimeoutExpired)) as prior:
            result.addError(self, (type(error), error, None))
        self.assertIsInstance(prior.exception, SystemExit)
        self.assertEqual(prior.exception.code, 1)
        self.assertIn("earlier mismatch", result.stream.getvalue())

    def test_gate_mode_reports_unknown_without_failing_own_checks(self):
        error = subprocess.TimeoutExpired("probe", guard.seconds("short"))
        with patch.object(sys, "argv", ["time_guard.py", "short", "--gate-check", "probe"]), patch.object(guard, "run", side_effect=error):
            with self.assertRaises(SystemExit) as result:
                guard.main()
        self.assertEqual(result.exception.code, 0)
        with patch.object(sys, "argv", ["time_guard.py", "short", "probe"]), patch.object(guard, "run", side_effect=error):
            with self.assertRaises(SystemExit) as result:
                guard.main()
        self.assertEqual(result.exception.code, 124)
        with patch.object(sys, "argv", ["time_guard.py", "short", "--gate-check", "probe"]), patch.object(guard, "run", return_value=subprocess.CompletedProcess(["probe"], 7)):
            with self.assertRaises(SystemExit) as result:
                guard.main()
        self.assertEqual(result.exception.code, 7)

    def test_top_level_timeout_preserves_status(self):
        code = (f"import sys;sys.path.insert(0,{str(Path(guard.__file__).parent)!r});"
                "import time_guard as g;import subprocess;sys.excepthook=g.unknown_excepthook;"
                "raise subprocess.TimeoutExpired('probe',g.seconds('short'))")
        with redirect_stderr(StringIO()), self.assertRaises(subprocess.TimeoutExpired):
            guard.run([sys.executable, "-c", code], capture_output=True, text=True, guard_class="short")


if __name__ == "__main__":
    guard.test_main()
