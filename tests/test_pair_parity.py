"""Dialect 13.1 parity at both zero-low transitions, from exact dyadic midpoints."""
import importlib.util
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("pair",ROOT/"tests/ppc_exact_oracle.py")
o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
e=o.e

def run(major):
    edge=e.Edge(major);u=e.power(-1074);f=e.FORMATS["f64"]
    for hb in (0x3ff0000000000001,0x0030000000000001):
        h=e.decode(hb,f)[0]
        for sign in (-1,1):
            expected=hb ^ ((1<<63) if sign<0 else 0)
            for direction in (-1,1):
                # FMA is exactly sign*(h +/- u/2); the zero-low neighbour
                # has even low significand and must win either midpoint.
                a=o.pair(sign*h,sign*direction*u)
                half=o.pair(e.Q(1,2));c=o.pair(sign*h/2)
                edge.check("fma_ppcf128_rm",[a,half,c,0],expected,16)
                if hb==0x0030000000000001:
                    value=sign*(h+direction*u/2)
                    raw,flags=e.encode(value,e.FORMATS["f128"])
                    assert flags==0
                    edge.check("fptrunc_f128_ppcf128_rm",[raw,0],expected,16)
                assert o.to_pair(sign*(h+direction*u/2))==(expected,16)
    print(f"LLVM {major}: {edge.count} exact zero-low parity/flag checks")

if __name__=="__main__":
    for major in map(int,sys.argv[1:] or [18,23]):run(major)
