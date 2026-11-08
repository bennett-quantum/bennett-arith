"""Independent required-family audit of the public manifest and build scripts."""
import json
import hashlib
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
assert (root/'scripts/gate').is_file(), 'missing dual-major gate'
assert (root/'scripts/pre-push').is_file(), 'missing pushed-SHA gate'
formats=dict(f16='i16',bf16='i16',f32='i32',f64='i64',f80='i80',f128='i128',ppcf128='i128')
binary='add sub mul div rem minnum maxnum minimum maximum minimumnum maximumnum'.split()
unary='sqrt floor ceil trunc round roundeven rint nearbyint canonicalize'.split()
integer='fptosi fptoui lround llround lrint llrint'.split()
trans='sin cos tan asin acos atan sinh cosh tanh exp exp2 exp10 log log2 log10'.split()
from pathlib import Path as ProfilePath
import sys as profile_sys
profile_sys.path.insert(0, str(ProfilePath(__file__).resolve().parents[1] / "scripts"))
from machine_profile import majors as machine_majors
for major in machine_majors(map(int,sys.argv[1:] or (18,23)), script=__file__):
    data=json.loads((root/f'dist/llvm{major}/manifest.json').read_text())
    assert data['llvm_major']==major
    assert data['bitcode_sha256']==hashlib.sha256((root/f'dist/llvm{major}/bennett-arith.bc').read_bytes()).hexdigest()
    assert all(data['tool_versions'].values())
    for source,hashes in data['sources'].items():
        assert hashlib.sha256((root/source).read_bytes()).hexdigest()==hashes['sha256'],source
    assert not data['staged_exports'], 'all concrete signatures must be published'
    exports={row['name']:row for row in data['exports']}
    staged={row['name']:row for row in data['staged_exports']}
    assert not set(exports)&set(staged)
    allrows=exports|staged
    expected={}
    for f,c in formats.items():
        expected[f'__bennett_sf_cmps_{f}_rm']=f'i1 ({c}, {c}, i32, i32)'
        specs={op:(c,[c,c]) for op in binary}
        specs.update({op:(c,[c]) for op in unary})
        specs.update({op:('i128',[c,'i32']) for op in integer})
        specs.update(cmp=('i1',[c,c,'i32']),sitofp=(c,['i128']),uitofp=(c,['i128']),
                     fma=(c,[c,c,c]),isfpclass=('i1',[c,'i32']),ldexp=(c,[c,'i32']),
                     frexp=(f'{{ {c}, i32 }}',[c]),modf=(f'{{ {c}, {c} }}',[c]),
                     powi=(c,[c,'i32']))
        for op,(ret,params) in specs.items():
            name=f'__bennett_sf_{op}_{f}'+('_i32' if op=='powi' else '')
            expected[name]=f'{ret} ({", ".join(params)})'
            if op not in ('isfpclass','canonicalize','frexp','modf'):
                expected[name+'_rm']=f'{ret} ({", ".join(params+["i32"])})'
            if op in integer+['sitofp','uitofp']:
                ret,params=(c,['ptr','i32']) if op in ('sitofp','uitofp') else ('void',['ptr',c,'i32'])
                expected[name+'_wide']=f'{ret} ({", ".join(params)})'
                expected[name+'_wide_rm']=f'{ret} ({", ".join(params+["i32"])})'
        for d,dc in formats.items():
            if d==f: continue
            for op in ('fpext','fptrunc'):
                expected[f'__bennett_sf_{op}_{f}_{d}']=f'{dc} ({c})'
                expected[f'__bennett_sf_{op}_{f}_{d}_rm']=f'{dc} ({c}, i32)'
        for op in trans+['atan2','pow','sincos','sincospi']:
            ret=f'{{ {c}, {c} }}' if op in ('sincos','sincospi') else c
            params=[c,c] if op in ('atan2','pow') else [c]
            expected[f'__bennett_sf_{op}_{f}']=f'{ret} ({", ".join(params)})'
            expected[f'__bennett_sf_{op}_{f}_rm']=f'{ret} ({", ".join(params+["i32"])})'
    for f,c in formats.items():
        for k in [1,8,16,64,128,192,256,513,1025]:
            expected[f'__bennett_sf_powi_{f}_i{k}']=f'{c} ({c}, i{k})'
            expected[f'__bennett_sf_powi_{f}_i{k}_rm']=f'{c} ({c}, i{k}, i32)'
    assert set(expected)==set(allrows),(set(expected)-set(allrows),set(allrows)-set(expected))
    for name,signature in expected.items():
        row=allrows[name]
        assert row['signature']==signature,(name,signature,row['signature'])
        assert row['format'] and row['section']
        if name in staged:
            assert row['status']=='staged'
    assert len(data['parametric_families'])==3
    assert data['contract_questions']==[]
    assert {'ppc-full-domain-arithmetic','elementary-full-domain-accuracy'}<=set(data['conformance_pending'])
    assert 'bennett-arith-chn.1' not in data['conformance_pending']
    for row in allrows.values():
        if (row['fi']==6 and row['op']=='fma') or (row['op']=='convert' and row['extra']==6):
            assert row['status']=='canonical-pair-exact'
    assert data['comparison_semantics']['predicate_range']==[0,15]
    assert data['comparison_semantics']['rounding_operand']==0
    print(f'LLVM {major}: manifest accounts for {len(expected)} concrete signatures and 3 parametric families')
