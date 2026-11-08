"""Dependency stages stay ordered; independent harnesses use the machine profile."""
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from machine_profile import command_cases, ordered_map
from time_guard import run, command_main

ROOT = Path(__file__).resolve().parents[1]
PYTHON = [sys.executable, "-B", "-I"]
CIRCUITS = ("test_pins", "test_adders", "test_multipliers", "test_qrom",
            "test_receipt_status", "test_receipt_parallel", "test_objects")
NUMERIC = ("test_contract", "test_edge", "test_ppc", "test_extended", "test_powi",
           "test_powi_limit", "test_trans", "test_trans_extra", "test_trans_boundaries",
           "test_directed", "test_pair_parity", "test_trans_phases", "test_named_overflow")
INSTANCES = ("test_instances", "test_instance_limits", "test_cmps", "test_publication")
PUBLICATIONS = ("bennett-arith.bc", "manifest.json", "SHA256SUMS")


def rebuild(major):
    directory = ROOT / f"dist/llvm{major}"
    saved = Path(os.environ["TMPDIR"]) / f"expected-llvm{major}"
    saved.mkdir(parents=True, exist_ok=True)
    for name in PUBLICATIONS:
        shutil.copyfile(directory / name, saved / name)
    done = run([str(ROOT / "scripts/build"), str(major)], capture_output=True)
    if done.returncode == 0:
        for name in PUBLICATIONS:
            assert (saved / name).read_bytes() == (directory / name).read_bytes(), (major, name)
    return done


def gate():
    run([*PYTHON, str(ROOT / "tests/test_default_cache.py")], check=True)
    for result in ordered_map(rebuild, (18, 23), "builds"):
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        result.check_returncode()
    command_cases([[*PYTHON, str(ROOT / "tests" / (name + ".py"))] for name in NUMERIC], "suites")
    command_cases([[*PYTHON, str(ROOT / "softfloat" / (name + ".py"))] for name in INSTANCES], "suites")
    print("gate: both published bitcode edges reproduced and passed")


def circuits():
    command_cases([[*PYTHON, str(ROOT / "tests/circuits" / (name + ".py"))]
                   for name in CIRCUITS], "suites")
    print("circuits: checks finished; raw receipt summary distinguishes COMPLETE, UNKNOWN and FAILED")


def prepare():
    directory, *extra = sys.argv[2:]
    command_cases([[*PYTHON, str(ROOT / "softfloat/generate.py"), directory, *extra],
                   [*PYTHON, str(ROOT / "softfloat/constants.py"), directory]], "builds", "moderate")


def default_suite():
    sys.path.insert(0, str(ROOT / "tests"))
    import test_default
    commands = [[*PYTHON, str(ROOT / "tests/test_default.py"), ".".join(case.id().rsplit(".", 2)[-2:])]
                for case in test_default.suite()]
    command_cases(commands, "suites", "moderate")


if __name__ == "__main__":
    command_main({"gate": gate, "circuits": circuits, "prepare": prepare}[sys.argv[1]])
