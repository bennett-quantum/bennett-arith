"""Literal clocks must fail regardless of their former spelling or language."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from time_literals import bare_times, inventory
import subprocess

REJECTED_CASES = [
    ("tests/probe.py", "run(timeout=90)"),
    ("tests/probe.py", "HANG_GUARD_FACTOR = 10"),
    ("tests/probe.py", "PUBLICATION_STAGE_WALL_S = {'entry': 504.60}"),
    ("tests/probe.py", "time.sleep(0.1)"),
    ("tests/probe.py", "signal.alarm(30)"),
    ("tests/probe.py", "assert time.monotonic() - start < 3"),
    ("tests/probe.py", "def f(timeout=10): pass"),
    ("scripts/gate", "timeout 600s python3 test.py"),
    ("scripts/gate", "timeout .5s python3 test.py"),
    ("gate.toml", "timeout_s = 28800"),
    ("tests/probe.rs", "Duration::from_millis(50)"),
    ("config.yaml", "deadline = 5"),
    ("config.yaml", "timeout: 10"),
    ("config.json", '{"timeout_s": 10}'),
]

class TimeLiterals(unittest.TestCase):
    def test_literal_forms(self):
        for name, text in REJECTED_CASES:
            with self.subTest(text=text):
                self.assertEqual(bare_times(name, text), [1])
    def test_classes_and_non_time_work(self):
        self.assertEqual(bare_times("tests/probe.py", "run(timeout=seconds('short'))\nassert steps < 100"), [])
        self.assertEqual(bare_times("tests/timeouts.toml", "timeout_s = 10"), [])
        self.assertEqual(bare_times("tests/test_time_literals.py", "time.sleep(1)"), [])

    def test_repository_has_no_bare_time_literals(self):
        root = Path(__file__).resolve().parents[1]
        paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0")
        self.assertEqual(inventory(root, sorted(set(paths) - {""})), [])

if __name__ == "__main__": unittest.main()
