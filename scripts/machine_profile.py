"""Memory-bounded harness widths; policy lives beside the hang-guard classes."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
TABLE_OBJECT = os.environ.get("BENNETT_GATE_PROFILE_TABLE")
TABLE_TEXT = (subprocess.check_output(["git", "-C", str(ROOT), "cat-file", "blob", TABLE_OBJECT], text=True)
              if TABLE_OBJECT else (ROOT / "tests/timeouts.toml").read_text())
PROFILE = tomllib.loads(TABLE_TEXT)["parallelism"]


def resources():
    cpus = len(os.sched_getaffinity(0))
    fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    memory = int(fields["MemAvailable"].split()[0]) // 1024
    return min(cpus, int(os.environ.get("BENNETT_POOL_CPUS", cpus))), min(
        memory, int(os.environ.get("BENNETT_POOL_MEMORY_MIB", memory)))


def workers(role, *, cpus=None, memory_mib=None):
    detected_cpus, detected_memory = resources()
    cpus = detected_cpus if cpus is None else cpus
    memory_mib = detected_memory if memory_mib is None else memory_mib
    row = PROFILE["pools"][role]
    available = max(0, memory_mib - PROFILE["reserve_mib"])
    memory_width = available // row["mib_per_worker"]
    if memory_width < 1:
        raise RuntimeError(f"insufficient MemAvailable for {role}: {memory_mib} MiB, "
                           f"need {PROFILE['reserve_mib'] + row['mib_per_worker']} MiB")
    width = min(row["max_workers"], max(1, cpus // row["cpus_per_worker"]), memory_width)
    requested = os.environ.get(row["override"], "")
    if requested:
        requested = int(requested)
        if requested < 1:
            raise ValueError(f"{row['override']} must be positive")
        width = min(width, requested)
    return width


def ordered_map(function, cases, role):
    """Consume results in input order, including exceptions, at a bounded width."""
    with ThreadPoolExecutor(max_workers=workers(role)) as pool:
        yield from pool.map(function, cases)


def command_cases(commands, role, guard_class="eternal"):
    """Independent subprocesses spool output; only the caller emits it in order."""
    from time_guard import run, seconds
    cpus, memory = resources()
    width = workers(role)
    env = dict(os.environ, BENNETT_POOL_CPUS=str(max(1, cpus // width)),
               BENNETT_POOL_MEMORY_MIB=str(memory // width))

    def execute(case):
        index, argv = case
        digest = hashlib.sha256(json.dumps(argv).encode()).hexdigest()[:16]
        directory = Path(env["TMPDIR"]) / f"commands/{index}-{digest}"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            return run(argv, guard_class=guard_class, capture_output=True, env=dict(env, TMPDIR=str(directory)))
        except subprocess.TimeoutExpired as error:
            return subprocess.CompletedProcess(argv, 124, error.output or b"", error.stderr or b"")

    codes = []
    for result in ordered_map(execute, enumerate(commands), role):
        sys.stdout.buffer.write(result.stdout)
        sys.stdout.buffer.flush()
        sys.stderr.buffer.write(result.stderr)
        sys.stderr.buffer.flush()
        codes.append(result.returncode)
    if any(code and code != 124 for code in codes):
        raise subprocess.CalledProcessError(next(code for code in codes if code and code != 124), commands)
    if 124 in codes:
        raise subprocess.TimeoutExpired(commands, seconds(guard_class))


def majors(values, *, script=None):
    """Keep each major in its own process, preserving script arguments and output."""
    values = list(values)
    if len(values) < 2 or workers("majors") == 1:
        return values
    args = [arg for arg in sys.argv[1:] if arg not in set(map(str, values))]
    from time_guard import command_main
    command_main(command_cases, [[sys.executable, "-B", "-I", script or sys.argv[0], str(major), *args]
                                for major in values], "majors")
    return []


def main():
    action, *args = sys.argv[1:]
    if action == "exec":
        role, *argv = args
        os.environ["CARGO_BUILD_JOBS"] = str(workers(role))
        os.execvp(argv[0], argv)
    elif action == "width":
        print(workers(args[0]))
    else:
        raise SystemExit("usage: machine_profile.py width ROLE | exec ROLE COMMAND ...")


if __name__ == "__main__":
    main()
