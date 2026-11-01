"""Inclusive LLVM integer width, target propagation, and reproducibility checks.

The giant integer is verified in bitcode rather than passed to a host backend.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ['TMPDIR'])/'limit-test'
WORK.mkdir(parents=True,exist_ok=True)
for major in (18,23):
    llvm=Path(f'/usr/lib/llvm-{major}/bin')
    layout='e-m:e-i8:8:32-i16:16:32-i64:64-i128:128-n32:64-S128'
    request=dict(schema='bennett-arith-instantiations-1',llvm_major=major,
                 target_triple='aarch64-unknown-linux-gnu',data_layout=layout,
                 entries=[dict(op='powi',base='f128',exponent_bits=8388608)])
    path=WORK/f'request-{major}.json';path.write_text(json.dumps(request))
    out=WORK/f'llvm{major}'
    if '--reuse' not in sys.argv:
        subprocess.run([sys.executable,'-I',str(ROOT/'softfloat/instantiate.py'),str(path),str(out)],check=True,timeout=300)
    manifest=json.loads((out/'manifest.json').read_text())
    expected=[dict(symbol='__bennett_sf_powi_f128_i8388608',function_type='i128 (i128, i8388608)'),
              dict(symbol='__bennett_sf_powi_f128_i8388608_rm',function_type='i128 (i128, i8388608, i32)')]
    assert manifest['exports']==expected
    bc=out/'bennett-arith.bc'
    assert manifest['bitcode_sha256']==hashlib.sha256(bc.read_bytes()).hexdigest()
    canonical=json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    assert manifest['request_sha256']==hashlib.sha256(canonical).hexdigest()
    ir=subprocess.check_output([str(llvm/'llvm-dis'),str(bc),'-o','-'],text=True)
    assert 'lshr i8388608 %n, 1' in ir
    assert 'target triple = "aarch64-unknown-linux-gnu"' in ir
    # Compare the actual layout to LLVM's interpretation of the requested
    # string. LLVM 23 adds historical AArch64 address-space/function alignment
    # defaults when it reads an older layout spelling, even for a new module.
    ref=WORK/f'target-{major}.ll';refbc=ref.with_suffix('.bc')
    ref.write_text(f'target datalayout = "{layout}"\ntarget triple = "aarch64-unknown-linux-gnu"\n')
    subprocess.run([str(llvm/'llvm-as'),str(ref),'-o',str(refbc)],check=True,timeout=60)
    reference=subprocess.check_output([str(llvm/'llvm-dis'),str(refbc),'-o','-'],text=True)
    target=lambda s:[line for line in s.splitlines() if line.startswith('target ')]
    assert target(ir)==target(reference)
    subprocess.run([str(llvm/'opt'),'-passes=verify','-disable-output',str(bc)],check=True,timeout=60)
    print(f'LLVM {major}: inclusive i8388608 exponent and aarch64 request fields verified',flush=True)

# The main numerical test generated equivalent requests in differently named
# temporary build directories. Rebuilding the smaller request detects embedded
# absolute paths and checks deterministic instance generation without big IR.
if '--reproduce' in sys.argv:
    for major in (18,23):
        work=Path(os.environ['TMPDIR'])/'instances-test'
        request=work/f'request-{major}.json';first=work/f'llvm{major}';second=work/f'llvm{major}-repeat'
        subprocess.run([sys.executable,'-I',str(ROOT/'softfloat/instantiate.py'),str(request),str(second)],check=True,timeout=300)
        for name in ('bennett-arith.bc','manifest.json'):
            assert (first/name).read_bytes()==(second/name).read_bytes(),(major,name)
        print(f'LLVM {major}: bitcode and JCS manifest reproduced byte for byte',flush=True)
