"""Exact exp rounding for every PPC argument with |x| <= 2^-538.

The Taylor bounds give 0 < exp(x)-1-x < x*x <= 2^-1076 for
nonzero x of either sign. PPC inputs lie on the 2^-1074 grid, whereas
binary64 low-field midpoints lie on its half grid. Thus the exact result
rounds as 1 + (x perturbed strictly upward by less than a quarter grid unit).
This proof needs neither MPFR nor an approximate exponential implementation.
The full libm accuracy obligation remains in wvh outside this proven path.
"""
import argparse
import importlib.util
from pathlib import Path
import random
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('oracle',ROOT/'tests/ppc_exact_oracle.py')
o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
e=o.e;F=o.F;U=e.power(-1074);BOUND=e.power(-538)

def expectation(raw,rm):
    x,_,_=o.decode(raw)
    assert not isinstance(x,str) and abs(x)<=BOUND
    if not x:return 0x3ff0000000000000,0
    # The oracle rounds exact rational interval endpoints independently. A
    # small positive rational is not evaluated as an exponential; the bound
    # above proves that it selects exactly the same binary64 rounding cell.
    delta=U/8
    mode=1 if rm==3 else rm
    if mode in (0,4):mode=0 # The strict perturbation makes a tie impossible.
    low=e.encode(x+delta,F,mode)[0]
    if e.decode(low,F)[0]==0:low=0
    return 0x3ff0000000000000|(low<<64),16

def run(major,root=ROOT):
    edge=e.Edge(major,root)
    # Start with the original red witness, before the wider exponent sweep.
    cases=[o.pair(e.power(-700)),0,1<<63]
    for exponent in range(-1074,-537):
        for sign in (-1,1):cases.append(o.pair(sign*e.power(exponent)))
    rng=random.Random(0xE0212)
    for exponent in range(-1020,-537,7):
        h=e.power(exponent)*e.Q(rng.randrange(1<<52,1<<53),1<<52)
        hb=e.encode(h,F)[0]&~1;h=e.decode(hb,F)[0]
        half=e.power(exponent-53)
        for residual in (U,-U,half,-half,half-U,-half+U,
                         e.power(max(-1074,exponent-200))):
            lo=e.encode(residual,F)[0];v=h+e.decode(lo,F)[0]
            assert e.encode(v,F)[0]==hb
            if v<=BOUND:
                raw=hb|(lo<<64);cases.append(raw)
                cases.append(raw^((1<<63)|(1<<127)))
    for raw in (o.pair(BOUND),o.pair(BOUND,-U),o.pair(-BOUND,U)):
        cases.append(raw)
    for raw in cases:
        want,_=expectation(raw,0)
        edge.check('exp_ppcf128',[raw],want,0)
        for rm in range(5):
            want,flags=expectation(raw,rm)
            edge.check('exp_ppcf128_rm',[raw,rm],want,flags)
    print(f'LLVM {major}: {edge.count} exact sparse-PPC exp value/rounding/flag checks',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('majors',type=int,nargs='*',default=[18,23])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    for major in args.majors:run(major,args.root)
