"""Laptop compatibility, memory caps, nesting and deterministic dispatch."""
from io import BytesIO, TextIOWrapper
import os
from pathlib import Path
import subprocess
import sys
import threading
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import machine_profile as profile
from time_guard import seconds, test_main


class MachineProfile(unittest.TestCase):
    def setUp(self):
        overrides = {row["override"] for row in profile.PROFILE["pools"].values()}
        clean = {k: v for k, v in os.environ.items() if k not in overrides}
        env = patch.dict(os.environ, clean, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_laptop_widths(self):
        expected = dict(cargo=4, cases=4, receipts=4, suites=1, majors=1, builds=1)
        actual = {role: profile.workers(role, cpus=12, memory_mib=24576) for role in expected}
        self.assertEqual(actual, expected)

    def test_large_host_scales(self):
        self.assertEqual(profile.workers("receipts", cpus=64, memory_mib=62 * 1024), 21)
        self.assertEqual(profile.workers("suites", cpus=64, memory_mib=62 * 1024), 5)

    def test_available_memory_and_overrides_bound_admissions(self):
        with patch.dict(os.environ, BENNETT_ARITH_RECEIPT_WORKERS="99"):
            self.assertEqual(profile.workers("receipts", cpus=64, memory_mib=5120), 2)
        with patch.dict(os.environ, BENNETT_ARITH_RECEIPT_WORKERS="1"):
            self.assertEqual(profile.workers("receipts", cpus=64, memory_mib=62 * 1024), 1)
        self.assertEqual(profile.workers("receipts", cpus=1, memory_mib=5120), 1)
        with self.assertRaisesRegex(RuntimeError, "insufficient MemAvailable"):
            profile.workers("receipts", cpus=64, memory_mib=2048)

    def test_invalid_override_is_loud(self):
        for value in ("0", "-2", "invalid"):
            with patch.dict(os.environ, BENNETT_TEST_WORKERS=value), self.assertRaises(ValueError):
                profile.workers("cases")

    def test_ordered_map_really_overlaps(self):
        barrier = threading.Barrier(3)

        def work(value):
            barrier.wait(timeout=seconds("short"))
            return value * 2

        with patch.object(profile, "workers", return_value=3):
            self.assertEqual(list(profile.ordered_map(work, (3, 2, 1), "receipts")), [6, 4, 2])

    def test_commands_order_output_and_partition_child_resources(self):
        stdout, stderr = BytesIO(), BytesIO()
        outstream, errstream = TextIOWrapper(stdout, write_through=True), TextIOWrapper(stderr, write_through=True)
        commands = [[sys.executable, "-c", f"print({value})"] for value in (3, 2, 1)]
        with patch.object(profile, "workers", return_value=3), \
                patch.object(profile, "resources", return_value=(12, 24576)), \
                patch.object(sys, "stdout", outstream), \
                patch.object(sys, "stderr", errstream):
            profile.command_cases(commands, "suites", "short")
        self.assertEqual(stdout.getvalue(), b"3\n2\n1\n")
        child = [sys.executable, "-c", "import os; print(os.environ['BENNETT_POOL_CPUS'], "
                 "os.environ['BENNETT_POOL_MEMORY_MIB'])"]
        stdout = BytesIO()
        outstream = TextIOWrapper(stdout, write_through=True)
        with patch.object(profile, "workers", return_value=3), \
                patch.object(profile, "resources", return_value=(12, 24576)), \
                patch.object(sys, "stdout", outstream):
            profile.command_cases([child], "suites", "short")
        self.assertEqual(stdout.getvalue(), b"4 8192\n")

    def test_major_arguments_survive_dispatch(self):
        argv = ["probe.py", "23", "18", "--root", "/somewhere", "--quick"]
        with patch.object(sys, "argv", argv), patch.object(profile, "workers", return_value=2), \
                patch.object(profile, "command_cases") as dispatch:
            self.assertEqual(profile.majors([23, 18]), [])
        self.assertEqual(dispatch.call_args.args[0], [
            [sys.executable, "-B", "-I", "probe.py", str(major), "--root", "/somewhere", "--quick"]
            for major in (23, 18)])

    def test_pinned_build_uses_exact_profile_objects(self):
        import tomllib
        config = tomllib.loads((ROOT / "gate.toml").read_text())
        build = config["siblings"]["bennett-isa-spec"]["build"][0]
        for key, path in (("BENNETT_GATE_PROFILE_TABLE", "tests/timeouts.toml"),
                          ("BENNETT_GATE_PROFILE_HELPER", "scripts/machine_profile.py")):
            actual = subprocess.check_output(["git", "hash-object", str(ROOT / path)], text=True).strip()
            self.assertEqual(build["env"][key], actual, f"refresh gate.toml profile object for {path}")

    def test_pinned_bootstrap_needs_no_live_source_files(self):
        import tomllib
        build = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"]["bennett-isa-spec"]["build"][0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for name in ("tests/timeouts.toml", "scripts/machine_profile.py"):
                subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                               input=(ROOT / name).read_bytes(), check=True, capture_output=True)
            cwd = root / ".tmp/gate/cache/pin/sibling/reference-interpreter"
            cwd.mkdir(parents=True)
            argv = build["argv"][:-3] + [sys.executable, "-c", "import os; print(os.environ['CARGO_BUILD_JOBS'])"]
            done = subprocess.run(argv, cwd=cwd, env=dict(os.environ, **build["env"]),
                                  capture_output=True, text=True, timeout=seconds("short"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(int(done.stdout), profile.workers("cargo"))

    def test_real_major_receipts_match_when_called_via_runpy(self):
        from time_guard import run
        script = str(ROOT / "tests/test_contract.py")
        code = ("import sys,runpy; sys.path.insert(0,sys.argv[1]); import machine_profile as p; "
                "p.PROFILE['pools']['majors']['cpus_per_worker']=6; "
                "sys.argv=[sys.argv[2]]; runpy.run_path(sys.argv[0],run_name='__main__')")
        serial = run([sys.executable, "-B", "-I", script], capture_output=True, guard_class="short")
        pooled = run([sys.executable, "-B", "-I", "-c", code, str(ROOT / "scripts"), script],
                     capture_output=True, guard_class="short")
        self.assertEqual(serial.returncode, 0, serial.stderr)
        self.assertEqual(pooled.returncode, 0, pooled.stderr)
        self.assertEqual(serial.stdout, pooled.stdout)

    def test_default_pool_runs_selected_cases_in_order(self):
        from time_guard import run
        first = "test_quality.Quality.test_python_decisions_and_forwarder"
        second = "test_quality.Quality.test_nested_branch_and_wrapper_are_detected"
        code = ("import sys,runpy,types; sys.path.insert(0,sys.argv[1]); import machine_profile as p; "
                "p.PROFILE['pools']['suites']['cpus_per_worker']=6; "
                "cases=[types.SimpleNamespace(id=lambda n=n:n) for n in sys.argv[3:]]; "
                "sys.modules['test_default']=types.SimpleNamespace(suite=lambda:cases); "
                "sys.argv=[sys.argv[2]]; runpy.run_path(sys.argv[0],run_name='__main__')")
        done = run([sys.executable, "-B", "-I", "-c", code, str(ROOT / "scripts"),
                    str(ROOT / "tests/test_default.py"), first, second],
                   capture_output=True, text=True, guard_class="short")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stderr.count("Ran 1 test"), 2)
        reports = [line.split(" ", 1)[0] for line in done.stderr.splitlines() if line.startswith("test_")]
        self.assertEqual(reports, [first.rsplit(".", 1)[1], second.rsplit(".", 1)[1]])


if __name__ == "__main__":
    test_main()
