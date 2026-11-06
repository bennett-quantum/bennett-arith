"""Independent audit of the 0.2.13 offline generator's publication metadata."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for major in (18,23):
    dist=ROOT/f'dist/llvm{major}'
    m=json.loads((dist/'manifest.json').read_text())
    assert m['dialect']=='0.2.13'
    assert m['bitcode_sha256']==hashlib.sha256((dist/'bennett-arith.bc').read_bytes()).hexdigest()
    generator=m['instance_generator']
    assert generator['command']=='python3 -I softfloat/instantiate.py REQUEST.json OUTPUT_DIRECTORY'
    assert generator['request_schema']=='bennett-arith-instantiations-1'
    assert generator['manifest_schema']=='bennett-arith-instances-1'
    families={f['name']:f for f in m['parametric_families']}
    to=families['__bennett_sf_convert_to_<fmt>_B']
    fr=families['__bennett_sf_convert_from_<fmt>_B']
    assert to['signature']=='iN (C_B, i32 R, i1 Sat)'
    assert fr['signature']=='C_B (iN)'
    assert to['status']==fr['status']=='available-offline'
    assert {'bennett-arith-4yg','bennett-arith-wvh'}<=set(m['conformance_pending'])
    assert m['numerical_accuracy']['pending_bead']=='bennett-arith-wvh'
    print(f'LLVM {major}: 0.2.13 request protocol, exact signatures and pending numerical obligations recorded')
