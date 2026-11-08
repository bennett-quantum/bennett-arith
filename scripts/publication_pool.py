"""Prepare one bridge before dispatching independent publication receipts."""
from pathlib import Path
import os
import subprocess
import sys

from time_guard import run


def bridge(binary, source, entries, receipts, receipt_type, unknown_state):
    deps = Path(binary).parent / "deps"
    libraries = list(deps.glob("libbennett_isa_ref-*.rlib"))
    assert len(libraries) == 1, f"expected one pinned ISA reader library in {deps}"
    verifier = Path(os.environ["TMPDIR"]) / "verify-certificate"
    try:
        run(["rustc", "--edition=2021", str(source), "--extern", f"bennett_isa_ref={libraries[0]}",
             "-L", f"dependency={deps}", "-o", str(verifier)], check=True, guard_class="short")
    except subprocess.TimeoutExpired as error:
        message = f"UNKNOWN: certificate bridge compilation hang guard {error.timeout:.2f}s expired"
        print(message, flush=True)
        receipts.update((entry["root"], receipt_type(unknown_state, message, 0, 0.0)) for entry in entries)
        raise
    return verifier


def replay(run, argv, output):
    try:
        done = run(argv, check=True, guard_class="long", capture_output=True, text=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        stdout = error.output or ""
        stderr = error.stderr or ""
        print(stdout.decode() if isinstance(stdout, bytes) else stdout, end="", file=output, flush=True)
        print(stderr.decode() if isinstance(stderr, bytes) else stderr, end="", file=sys.stderr, flush=True)
        raise
    print(done.stdout, end="", file=output, flush=True)
    print(done.stderr, end="", file=sys.stderr, flush=True)
