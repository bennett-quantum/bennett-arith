"""Build a test-only arithmetic edge without publishing or changing dist/.

Usage: python3 -I tests/build_stage.py MAJOR STAGING_ROOT
The result follows Edge's dist/.tmp layout and uses the publication build flags.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from time_guard import run as guarded_run, unknown_excepthook
sys.excepthook = unknown_excepthook

def module(name):
    s=importlib.util.spec_from_file_location(name,ROOT/f'softfloat/{name}.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def run(args):
    guarded_run([str(x) for x in args],check=True,guard_class="moderate")

if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit(__doc__)
    major=int(sys.argv[1]);stage=Path(sys.argv[2]).resolve()
    if major not in (18,23):raise ValueError('major must be 18 or 23')
    if stage==ROOT or stage.is_relative_to(ROOT/'dist'):
        raise ValueError('a staging root must not overwrite the publication')
    work=stage/f'.tmp/llvm{major}';dist=stage/f'dist/llvm{major}'
    work.mkdir(parents=True,exist_ok=True);dist.mkdir(parents=True,exist_ok=True)
    module('generate').generate(work);module('constants').constants(work)
    llvm=Path(f'/usr/lib/llvm-{major}/bin')
    run([llvm/'clang','-I',work,'-target','x86_64-unknown-linux-gnu','-std=c2x',
         f'-DBENNETT_LLVM_MAJOR={major}','-O1','-ffreestanding','-fno-builtin',
         '-fno-vectorize','-fno-slp-vectorize','-fno-ident','-S','-emit-llvm',
         ROOT/'softfloat/core.c','-o',work/'core.ll'])
    p=work/'core.ll';p.write_text(re.sub(r'^source_filename = .*','source_filename = "softfloat/core.c"',p.read_text(),flags=re.M))
    for name in ('core','wrappers'):run([llvm/'llvm-as',work/f'{name}.ll','-o',work/f'{name}.bc'])
    run([llvm/'llvm-link',work/'core.bc',work/'wrappers.bc','-o',work/'linked.bc'])
    bc=dist/'bennett-arith.bc'
    run([llvm/'opt','-passes=internalize,globaldce',f'-internalize-public-api-file={work/"exports.txt"}',work/'linked.bc','-o',bc])
    run([llvm/'opt','-passes=verify','-disable-output',bc])
    run([llvm/'llvm-dis',bc,'-o',work/'published.ll'])
    run([llvm/'clang','-target','x86_64-unknown-linux-gnu','-shared','-fPIC',bc,work/'bridge.ll','-o',work/'oracle.so'])
    m=json.loads((work/'manifest.json').read_text());m['llvm_major']=major
    m['bitcode_sha256']=hashlib.sha256(bc.read_bytes()).hexdigest()
    (dist/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print(f'LLVM {major}: staged test edge at {stage}; default dist unchanged',flush=True)
