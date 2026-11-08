"""All constrained elementary operations against exact MPFR bracket rounding."""
import importlib.util
from pathlib import Path
import sys
import os
from itertools import product

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("trans",ROOT/"tests/test_trans.py")
t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
e=t.e

TINY_PPC_FIELDS = (
    ("sincos",("sin","cos")), ("sincospi",("sinpi","cospi")),
    ("sin",("sin",)), ("cos",("cos",)), ("sinh",("sinh",)),
    ("tan",("tan",)), ("atan",("atan",)), ("asin",("asin",)), ("tanh",("tanh",)),
)
TINY_PPC_SPARSE = (
    e.power(-359)+e.power(-1074), e.power(-358)-e.power(-1074),
    e.power(-538)+e.power(-1074), e.power(-538)-e.power(-1074),
)

def tiny_ppc(edge, oracle, quick):
    """MPFR brackets resolve corrections below the binary64 low quantum.

    2^-358 through 2^-1074 covers the entire power-of-two underflow band
    for every cubic correction, including both sides of the normal boundary.
    """
    exponents = ((700,358,359,360,537,538,539,540,1021,1022,1023,1073,1074)
                 if quick else range(358,1075))
    values = tuple(map(lambda k: e.power(-k), exponents)) + TINY_PPC_SPARSE
    for v, sign, (op, components), rm in product(values, (-1,1), TINY_PPC_FIELDS, range(5)):
        value = sign * v
        expected = tuple(map(lambda field: oracle.rounded(field,value,int(sign<0),rm=rm), components))
        raw = oracle.pairs.to_pair(value)[0]
        rounded = oracle.pairs.decode(expected[0])[0]
        flags = 16 | (8 if abs(rounded)<e.power(-1022) else 0)
        edge.check(op+"_ppcf128_rm", [raw,rm], (expected+(0,))[:2], flags)
    for sign, rm in product((-1,1), range(5)):
        value = sign * e.power(-700)
        expected = oracle.rounded("exp", value, int(sign<0), rm=rm)
        edge.check("exp_ppcf128_rm", [oracle.pairs.to_pair(value)[0],rm], expected, 16)
    assert not oracle.inconclusive
    print(f"sparse PPC tiny family: {edge.count} checks passed", flush=True)


def run(major, quick=False):
    edge=e.Edge(major);oracle=t.Oracle()
    tiny_ppc(edge,oracle,quick)
    formats=list(e.FORMATS.items())
    if os.environ.get("BENNETT_ARITH_PROMISED"):
        formats.append(("ppcf128",None))
    else:
        print("PPC exact sweep: BENNETT_ARITH_PROMISED=1 (bennett-arith-wvh)",flush=True)
    for suffix,f in formats:
        enc=lambda v: oracle.pairs.to_pair(v)[0] if f is None else e.encode(v,f)[0]
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
            for op, rm in product(t.ops, range(5)):
                b=e.Q(3,2) if op=="pow" else e.Q(-3,4)
                args=[raw,enc(b)] if op in ("pow","atan2") else [raw]
                expected=oracle.rounded(op,a,sa,b,f=f,rm=rm)
                edge.check(op+"_"+suffix+"_rm",[*args,rm],expected)
            for pair, components in (("sincos",("sin","cos")),
                                     ("sincospi",("sinpi","cospi"))):
                for rm in range(5):
                    expected=tuple(oracle.rounded(op,a,sa,f=f,rm=rm) for op in components)
                    edge.check(pair+"_"+suffix+"_rm",[raw,rm],expected)
        print(f"LLVM {major} {suffix}: {edge.count} exact directed checks",flush=True)
    assert not oracle.inconclusive

if __name__=="__main__":
    for major in map(int,[a for a in sys.argv[1:] if a not in ("--quick","--tiny-only")] or [18,23]):
        if "--tiny-only" in sys.argv:
            tiny_ppc(e.Edge(major),t.Oracle(),"--quick" in sys.argv)
        else:
            run(major,"--quick" in sys.argv)
