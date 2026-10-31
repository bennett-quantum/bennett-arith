"""Independent required-family audit of the public manifest and build scripts."""
import json
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
for major in map(int,sys.argv[1:] or (18,23)):
    data=json.loads((root/f'dist/llvm{major}/manifest.json').read_text())
    exports={row['name']:row for row in data['exports']}
    staged={row['name']:row for row in data['staged_exports']}
    assert not set(exports)&set(staged)
    allrows=exports|staged
    expected={}
    for f,c in formats.items():
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
            if op not in ('cmp','isfpclass','canonicalize','frexp','modf','powi'):
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
    assert set(expected)==set(allrows),(set(expected)-set(allrows),set(allrows)-set(expected))
    for name,signature in expected.items():
        row=allrows[name]
        assert row['signature']==signature,(name,signature,row['signature'])
        assert row['format'] and row['section']
        if name in staged:
            assert row['bead'].startswith('bennett-arith-') and row['status']=='staged'
    assert len(data['parametric_families'])==3
    print(f'LLVM {major}: manifest accounts for {len(expected)} concrete signatures and 3 parametric families')
