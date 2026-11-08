"""Exact identities and strict bounds from the arithmetic review."""
import argparse
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('oracle',ROOT/'tests/ppc_exact_oracle.py')
o=importlib.util.module_from_spec(s);s.loader.exec_module(o);e=o.e

def tanh_bounds(x):
    spec=importlib.util.spec_from_file_location('mpfr',ROOT/'tests/test_trans.py')
    t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
    oracle=t.Oracle(2048)
    return [oracle.call("tanh",x,0,direction=direction)[0] for direction in (3,2)]

def run(major,root,case):
    edge=e.Edge(major,root);f=e.FORMATS['f64'];one=e.encode(e.Q(1),f)[0]
    if case in ('all','ppc'):
        for exponent in (-60,-110,-200,-1074):
            for sign in (1,-1):
                raw=o.pair(e.Q(sign),sign*e.power(exponent))
                for rm in range(5):edge.check('fma_ppcf128_rm',[raw,one,0,rm],raw,0)
                edge.check('fma_ppcf128',[raw,one,0],raw,0)
        for name,p in (('f80',-63),('f128',-110)):
            for sign in (1,-1):
                x=sign*(1+e.power(p));raw=e.encode(x,e.FORMATS[name])[0]
                want=o.pair(e.Q(sign),sign*e.power(p))
                for rm in range(5):edge.check(f'fptrunc_{name}_ppcf128_rm',[raw,rm],want,0)
        for x in (e.power(-16494),e.power(-1075),-e.power(-1075),e.power(1024)):
            raw=e.encode(x,e.FORMATS['f128'])[0]
            for rm in range(5):edge.check('fptrunc_f128_ppcf128_rm',[raw,rm],*o.incoming(raw,e.FORMATS['f128'],rm))
        triples=[(o.pair(e.Q(1),e.power(-200)),o.pair(e.Q(1),-e.power(-200)),o.pair(e.Q(-1))),
                 (o.pair(e.power(1023)),o.pair(e.Q(2)),o.pair(-e.decode(0x7fefffffffffffff,f)[0])),
                 (1,1,0),((1<<63)|1,1,0),
                 (0,e.infinity(f),e.nan(f)),(0,e.infinity(f),e.infinity(f)|1)]
        for a,b,c in triples:
            for rm in range(5):edge.check('fma_ppcf128_rm',[a,b,c,rm],*o.fma(a,b,c,rm))
    if case in ('all','limits'):
        for name,f in [*e.FORMATS.items(),('ppcf128',e.FORMATS['f64'])]:
            x=e.encode(e.Q(-65504 if name=='f16' else -100000),f)[0]
            for op in ('exp','exp2','exp10'):
                for rm in range(5):edge.check(f'{op}_{name}_rm',[x,rm],int(rm==2),24)
            for sign in (1,-1):
                # At 1024 the tail is smaller than half even the PPC quantum.
                x=e.encode(e.Q(sign*1024),f)[0]
                unit=e.power(-1074) if name=='ppcf128' else e.power(-f[1])
                near=o.pair(e.Q(sign),-sign*unit) if name=='ppcf128' else e.encode(sign*(1-unit),f)[0]
                far=e.encode(e.Q(sign),f)[0]
                for rm in range(5):
                    inward=rm==3 or rm==(1 if sign>0 else 2)
                    edge.check(f'tanh_{name}_rm',[x,rm],near if inward else far,16)
                if name!='ppcf128':
                    x=e.encode(e.Q(sign*256),f)[0]
                    for rm in range(5):
                        inward=rm==3 or rm==(1 if sign>0 else 2)
                        edge.check(f'tanh_{name}_rm',[x,rm],near if inward else far,16)
        for sign in (1,-1):
            lo,hi=tanh_bounds(e.Q(sign*256))
            for rm in range(5):
                want,_=o.to_pair(lo,rm)
                assert want==o.to_pair(hi,rm)[0],'MPFR interval must prove canonical selection'
                edge.check('tanh_ppcf128_rm',[e.encode(e.Q(sign*256),e.FORMATS['f64'])[0],rm],want,16)
    if case in ('all','exact'):
        for sign in (1,-1):
            odd=o.pair(sign*e.power(1000),e.Q(sign))
            for rm in range(5):
                edge.check('sincospi_ppcf128_rm',[odd,rm],((1<<63) if sign<0 else 0,e.encode(e.Q(-1),e.FORMATS['f64'])[0]),0)
        for name,f in [*e.FORMATS.items(),('ppcf128',e.FORMATS['f64'])]:
            enc=lambda q:e.encode(e.Q(q),f)[0]
            for rm in range(5):
                one=enc(1);qnan=e.nan(f);snan=e.infinity(f)|1;negativezero=1<<(f[0]-1)
                for x,sv,cv in ((e.Q(1,2),1,0),(1,0,-1),(e.Q(3,2),-1,0),(2,0,1),
                                (e.Q(-1,2),-1,0),(-1,0,-1),(e.Q(-3,2),1,0),(-2,0,1)):
                    sine=negativezero if not sv and x<0 else enc(sv)
                    edge.check(f'sincospi_{name}_rm',[enc(x),rm],(sine,enc(cv)),0)
                for a,b,want,flags in ((qnan,0,one,0),(snan,0,one,1),
                    (one,qnan,one,0),(one,snan,one,1),
                    (negativezero,enc(3),negativezero,0),(negativezero,enc(2),0,0),
                    (0,enc(-3),e.infinity(f),2)):
                    edge.check(f'pow_{name}_rm',[a,b,rm],want,flags)
                for a,b,c in ((2,3,8),(4,e.Q(1,2),2),(2,-3,e.Q(1,8)),(-2,3,-8),
                              (9,e.Q(1,2),3),(81,e.Q(1,4),3),(-1,16384,1)):
                    edge.check(f'pow_{name}_rm',[enc(a),enc(b),rm],enc(c),0)
                for n in (0,1,2):
                    edge.check(f'exp10_{name}_rm',[enc(n),rm],enc(10**n),0)
                    edge.check(f'log10_{name}_rm',[enc(10**n),rm],enc(n),0)
            for base in (e.Q(3,2),e.Q(5,4),e.Q(-3,2)):
                for n in range(-4,9):
                    for rm in range(5):
                        exact=base**n
                        want,flags=o.to_pair(exact,rm) if name=='ppcf128' else e.encode(exact,f,rm)
                        edge.check(f'pow_{name}_rm',[enc(base),enc(n),rm],want,flags)
    print(f'LLVM {major}: {edge.count} review {case} exact identity/bound checks',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('majors',type=int,nargs='*',default=[18,23]);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--case',choices=('all','ppc','limits','exact'),default='all');a=p.parse_args()
    from pathlib import Path as ProfilePath
    import sys as profile_sys
    profile_sys.path.insert(0, str(ProfilePath(__file__).resolve().parents[1] / "scripts"))
    from machine_profile import majors as machine_majors
    for major in machine_majors(a.majors, script=__file__):run(major,a.root,a.case)
