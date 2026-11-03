"""Exact identities and strict bounds from the arithmetic review."""
import argparse
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('oracle',ROOT/'tests/ppc_exact_oracle.py')
o=importlib.util.module_from_spec(s);s.loader.exec_module(o);e=o.e

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
    if case in ('all','exact'):
        for name,f in [*e.FORMATS.items(),('ppcf128',e.FORMATS['f64'])]:
            enc=lambda q:e.encode(e.Q(q),f)[0]
            for rm in range(5):
                for a,b,c in ((2,3,8),(4,e.Q(1,2),2),(2,-3,e.Q(1,8)),(-2,3,-8)):
                    edge.check(f'pow_{name}_rm',[enc(a),enc(b),rm],enc(c),0)
                for n in (0,1,2):
                    edge.check(f'exp10_{name}_rm',[enc(n),rm],enc(10**n),0)
                    edge.check(f'log10_{name}_rm',[enc(10**n),rm],enc(n),0)
    print(f'LLVM {major}: {edge.count} review {case} exact identity/bound checks',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('majors',type=int,nargs='*',default=[18,23]);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--case',choices=('all','ppc','limits','exact'),default='all');a=p.parse_args()
    for major in a.majors:run(major,a.root,a.case)
