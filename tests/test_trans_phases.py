"""Unit checks for domain, core and packing phase boundaries."""
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def run(source=ROOT):
    work=Path(os.environ["TMPDIR"])/"trans-phases"
    work.mkdir(parents=True,exist_ok=True)
    exe=work/"phases"
    subprocess.run(["/usr/lib/llvm-18/bin/clang","-std=c2x","-O0",
                    "-DBENNETT_LLVM_MAJOR=18",f'-DBENNETT_CORE="{source}/softfloat/core.c"',
                    "-I",str(ROOT/".tmp/llvm18"),str(ROOT/"tests/trans_phases.c"),
                    "-o",str(exe)],check=True,timeout=60)
    subprocess.run([str(exe)],check=True,timeout=10)
    print("domain/core/pack/exactness-table invariants passed")

if __name__=="__main__":run(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT)
