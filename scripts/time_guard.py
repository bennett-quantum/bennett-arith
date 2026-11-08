#!/usr/bin/env python3
"""One class table, process-tree hang guards, and per-command wall/CPU receipts."""
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tomllib
import unittest

TABLE = tomllib.loads((Path(__file__).resolve().parents[1] / "tests/timeouts.toml").read_text())


def seconds(guard_class):
    row = TABLE["classes"][guard_class]
    factor = TABLE["machine_config_factor"]
    assert math.isfinite(factor) and factor > 0, "invalid machine/config factor"
    assert row["measurements"], f"uncited hang guard: {guard_class}"
    cap = row["seconds"] * factor
    assert cap >= TABLE["measurement_margin"] * max(m["wall_seconds"] for m in row["measurements"])
    return cap


class TimedProcess(subprocess.Popen):
    """wait4 accounts for this child, including when callers run concurrently."""
    cpu_seconds = 0.0

    def _try_wait(self, wait_flags):
        pid, status, usage = os.wait4(self.pid, wait_flags)
        if pid:
            self.cpu_seconds = usage.ru_utime + usage.ru_stime
        return pid, status


def record(argv, guard_class, began, process, state):
    wall = time.monotonic() - began
    cap = seconds(guard_class)
    row = {"event": "command_receipt", "argv": list(map(str, argv)), "class": guard_class,
           "guard_seconds": cap, "wall_seconds": wall, "cpu_seconds": process.cpu_seconds,
           "state": state, "exit": process.returncode, "machine": TABLE["machine"]}
    print(json.dumps(row, sort_keys=True), file=sys.stderr, flush=True)
    if wall < cap * 0.1 or wall > cap * 0.5:
        print(f"hang guard class warning: {guard_class}: {wall / cap:.1%} used by {argv}", file=sys.stderr)


def kill_tree(pid):
    """Nested guards have their own sessions; terminate descendants as well."""
    children = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        descendants = children.read_text().split()
    except FileNotFoundError:
        return
    for child in descendants:
        kill_tree(int(child))
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run(argv, *, guard_class="moderate", check=False, capture_output=False, input=None, **kwargs):
    """subprocess.run semantics, with UNKNOWN/TIMEOUT distinct from command failure."""
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    began = time.monotonic()
    with TimedProcess(argv, start_new_session=True, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=seconds(guard_class))
        except subprocess.TimeoutExpired as error:
            kill_tree(process.pid)
            process.communicate()
            record(argv, guard_class, began, process, "UNKNOWN/TIMEOUT")
            print(f"UNKNOWN/TIMEOUT: {argv}: class {guard_class} expired", file=sys.stderr, flush=True)
            raise error
        state = {0: "COMPLETE", 124: "UNKNOWN/TIMEOUT"}.get(process.returncode, "FAILED")
        record(argv, guard_class, began, process, state)
        if process.returncode == 124:
            raise subprocess.TimeoutExpired(argv, seconds(guard_class), stdout, stderr)
        result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def output(argv, **kwargs):
    return run(argv, check=True, stdout=subprocess.PIPE, **kwargs).stdout


class UnknownResult(unittest.TextTestResult):
    def addError(self, test, err):
        error = err[1]
        if isinstance(error, subprocess.TimeoutExpired):
            raise error
        if isinstance(error, subprocess.CalledProcessError) and error.returncode == 124:
            raise subprocess.TimeoutExpired(error.cmd, None)
        super().addError(test, err)


class GuardedTestRunner(unittest.TextTestRunner):
    resultclass = UnknownResult


def test_main(**kwargs):
    """Abort an inconclusive suite before unittest can label it FAIL or OK."""
    try:
        return unittest.main(testRunner=GuardedTestRunner, **kwargs)
    except subprocess.TimeoutExpired as error:
        print(f"UNKNOWN/TIMEOUT: {error.cmd}", file=sys.stderr, flush=True)
        raise SystemExit(124)


def command_main(command, *args):
    try:
        return command(*args)
    except subprocess.TimeoutExpired as error:
        print(f"UNKNOWN/TIMEOUT: {error.cmd}", file=sys.stderr, flush=True)
        raise SystemExit(124)


def main():
    guard_class, *argv = sys.argv[1:]
    if argv == ["--seconds"]:
        print(seconds(guard_class))
        return
    if not argv:
        raise SystemExit("usage: time_guard.py CLASS COMMAND [ARG ...] | CLASS --seconds")
    try:
        result = run(argv, guard_class=guard_class)
    except subprocess.TimeoutExpired:
        raise SystemExit(124)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
