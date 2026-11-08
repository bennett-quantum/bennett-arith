"""Exact exp rounding for PPC arguments with |x| <= 2^-112.

Independent rational Taylor bounds enclose exp(x)-1 between
x+x*x/2+x*x*x/6 and that value plus x**4. The low component must
round identically at both endpoints, proving the expected result without MPFR.
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
e=o.e;F=o.F;U=e.power(-1074);BOUND=e.power(-112)

def expectation(raw,rm):
    x,_,_=o.decode(raw)
    assert not isinstance(x,str) and abs(x)<=BOUND
    if not x:return 0x3ff0000000000000,0
    # Taylor's fourth-order remainder is strictly positive for either sign,
    # and bounded by exp(|x|)*x**4/24 < x**4 for these arguments.
    lower=x+x*x/2+x*x*x/6;upper=lower+x**4
    mode=1 if rm==3 else rm
    if mode in (0,4):mode=0 # The strict perturbation makes a tie impossible.
    low=e.encode(lower,F,mode)[0]
    assert low==e.encode(upper,F,mode)[0],(raw,rm,'Taylor interval does not prove this case')
    if e.decode(low,F)[0]==0:low=0
    return 0x3ff0000000000000|(low<<64),16

def run(major,root=ROOT):
    edge=e.Edge(major,root)
    # Start with the original red witness, before the wider exponent sweep.
    cases=[o.pair(e.power(-700)),0,1<<63]
    # Finite input fields may overlap or cancel before canonical output is
    # formed. Their exact sum is still the mathematical argument.
    for h,l in ((U,U),(e.power(-200),e.power(-200)),
                (e.power(-60),-e.power(-60)+BOUND),
                (-e.power(-60)+BOUND,e.power(-60))):
        raw=e.encode(h,F)[0]|(e.encode(l,F)[0]<<64)
        assert o.decode(raw)[0]==h+l
        cases.append(raw)
        cases.append(raw^((1<<63)|(1<<127)))
    for exponent in range(-1074,-111):
        for sign in (-1,1):cases.append(o.pair(sign*e.power(exponent)))
    rng=random.Random(0xE0212)
    for exponent in range(-1020,-111,7):
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
    # Directed rounding depends on which side of an input high component the
    # exponential residual falls. Probe exact quadratic cancellation and its
    # adjacent low encodings, with cubic terms settling the exact equality.
    for exponent in sorted(set(range(-536,-112,11))|{-113}):
        for sign in (-1,1):
            h=sign*e.power(exponent);lb=e.encode(-h*h/2,F)[0]
            for lowbits in (lb-1,lb,lb+1):
                cases.append(o.pair(h,e.decode(lowbits,F)[0]))
        h=e.power(exponent)*e.Q(0x15555555555555,1<<52)
        for mode in (1,2):
            low=e.encode(-h*h/2,F,mode)[0]
            cases.append(o.pair(h,e.decode(low,F)[0]))
            cases.append(o.pair(-h,e.decode(low,F)[0]))
    for raw in (o.pair(BOUND),o.pair(BOUND,-U),o.pair(-BOUND,U)):
        cases.append(raw)
    lb=e.encode(-BOUND*BOUND/2,F)[0]
    for lowbits in (lb-1,lb,lb+1):cases.append(o.pair(BOUND,e.decode(lowbits,F)[0]))
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
    from pathlib import Path as ProfilePath
    import sys as profile_sys
    profile_sys.path.insert(0, str(ProfilePath(__file__).resolve().parents[1] / "scripts"))
    from machine_profile import majors as machine_majors
    for major in machine_majors(args.majors, script=__file__):run(major,args.root)
