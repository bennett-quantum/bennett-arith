"""All constrained elementary operations against exact MPFR bracket rounding."""
import importlib.util
from pathlib import Path
import sys
import os

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("trans",ROOT/"tests/test_trans.py")
t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
e=t.e

def run(major, quick=False):
    edge=e.Edge(major);oracle=t.Oracle()
    formats=list(e.FORMATS.items())
    if os.environ.get("BENNETT_ARITH_PROMISED"):
        formats.append(("ppcf128",None))
    else:
        print("PPC exact sweep: BENNETT_ARITH_PROMISED=1 (bennett-arith-wvh)",flush=True)
    for suffix,f in formats:
        def enc(v):
            return oracle.pairs.to_pair(v)[0] if f is None else e.encode(v,f)[0]
        if f is None:
            oracle.rounded("exp",e.Q(0),0)
        tiny=-1074 if f is None else 1-f[3]-(f[1]-1)
        exponents=(-169,-300) if quick else (tiny,tiny+1,-300,-169,-113,-112,-111,-20)
        values=[sign*e.power(k) for k in exponents for sign in (-1,1)]
        values += [e.Q(x) for x in (64,78,80,100,136,161,255,256,512,-64,-100,-255)]
        values += [e.Q(1)+d*e.power(-52 if f is None else 1-f[1]) for d in (-2,-1,0,1,2)]
        for v in values:
            raw=enc(v)
            a,sa=(oracle.pairs.decode(raw)[:2] if f is None else e.decode(raw,f)[:2])
            if isinstance(a,str):continue
            for op in t.ops:
                b=e.Q(3,2) if op=="pow" else e.Q(-3,4)
                args=[raw,enc(b)] if op in ("pow","atan2") else [raw]
                for rm in range(5):
                    expected=oracle.rounded(op,a,sa,b,f=f,rm=rm)
                    edge.check(op+"_"+suffix+"_rm",[*args,rm],expected)
        print(f"LLVM {major} {suffix}: {edge.count} exact directed checks",flush=True)
    assert not oracle.inconclusive

if __name__=="__main__":
    for major in map(int,[a for a in sys.argv[1:] if a!="--quick"] or [18,23]):
        run(major,"--quick" in sys.argv)
