"""Exact-bound diagnostic for wvh.1, not a libm conformance pass.

For 0<x<1/2 the Taylor series gives 1+x < exp(x) < 1+x+x*x:
sum(x**k/k!, k>=2) < x*x/(2*(1-x)) < x*x.
Only rational arithmetic is needed to prove the canonical result neighbours.
The native results are printed as implementation evidence, without accepting
their error as a test tolerance.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('oracle',ROOT/'tests/ppc_exact_oracle.py')
o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
e=o.e;F=o.F
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('majors',type=int,nargs='*',default=[18,23])
parser.add_argument('--root',type=Path,default=ROOT)
args=parser.parse_args()

x=e.power(-700);step=e.power(-752)
assert 0<x<e.Q(1,2) and x*x<step/2
lower=o.pair(e.Q(1),x);upper=o.pair(e.Q(1),x+step)
assert upper>>64==(lower>>64)+1
assert e.encode(1+x,F)[0]==e.encode(1+x+step,F)[0]==0x3ff0000000000000
# All canonical sums inside this high bin have high=1, so adjacent low fields
# prove adjacency of the pair values as well. The series bounds put exp(x)
# above lower, below upper, and strictly below their midpoint.
assert 1+x<1+x+x*x<1+x+step/2<o.decode(upper)[0]
print('Exact bound: 1+2^-700 < exp(2^-700) < 1+2^-700+2^-1400.')
print(f'Canonical neighbours: {lower:032x}, {upper:032x}; local ulp = 2^-752.')
print('Nearest/down/towardzero select the lower pair; upward selects the upper; final flags=16.')
differences=0
for major in args.majors:
    edge=e.Edge(major,args.root)
    edge.env[1]=32
    plain=edge.call('exp_ppcf128',o.pair(x))[0]
    assert edge.env[1]==32, 'plain exp must not touch fenv'
    v=o.decode(plain)[0]
    outside=isinstance(v,str) or v<1+x-step or v>1+x+x*x+step
    print(f'LLVM {major}: plain {plain:032x}; provably outside one-ulp envelope={outside}')
    differences+=outside
    for mode in range(5):
        edge.env[1]=32
        actual=edge.call('exp_ppcf128_rm',o.pair(x),mode)[0]
        expected=upper if mode==2 else lower
        correct=actual==expected and edge.env[1]==48
        differences+=not correct
        print(f'LLVM {major}: R={mode}, actual={actual:032x}, flags={edge.env[1]&31}, exact selection agrees={correct}')
print(f'Exact witness verified; {differences} native disagreements. This is not a conformance pass.')
