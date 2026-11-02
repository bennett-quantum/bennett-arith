"""Exact witness for the 0.2.12 zero-low tie-parity question.

A successful exit verifies the witness, not arithmetic conformance. All expected
values use Fraction/integer arithmetic. The native result is evidence only.
"""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',ROOT/'tests/test_edge.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
f=e.FORMATS['f64'];mask=(1<<64)-1

def value(pair):
    return e.decode(pair&mask,f)[0]+e.decode(pair>>64,f)[0]

def canonical(pair):
    high=pair&mask;low=pair>>64
    h=e.decode(high,f)[0];v=value(pair)
    return e.encode(v,f)[0]==high and e.decode(low,f)[0]==v-h and (low!=1<<63)

hbits=0x3ff0000000000001
h=e.decode(hbits,f)[0];u=e.power(-1074)
a=hbits|(1<<64);b=0x3fe0000000000000;c=0x3fe0000000000001
assert all(canonical(p) for p in (a,b,c))
exact=value(a)*value(b)+value(c)
lower=hbits;upper=a
assert canonical(lower) and canonical(upper)
assert exact==h+u/2
assert exact-value(lower)==value(upper)-exact==u/2
# Every finite binary64 is an integer multiple of u, so every pair sum is too.
# Therefore there can be no pair sum strictly between these two neighbours.
assert (value(lower)/u).denominator==(value(upper)/u).denominator==1
assert (value(upper)-value(lower))/u==1
parity=lambda p:((p>>64) if p>>64 else p&mask)&1
assert parity(lower)==parity(upper)==1
print('Exact FMA is h + 2^-1075, h = 1 + 2^-52; its two adjacent canonical neighbours are equidistant.')
print(f'Lower = {lower:032x}; upper = {upper:032x}; literal zero-low fallback gives odd/odd parity.')
# The same ambiguity is reachable by a binary128 conversion, independently of
# FMA: scale the odd high component into a small normal binary64 high bin.
chbits=(3<<52)|1;ch=e.decode(chbits,f)[0]
clower=chbits;cupper=chbits|(1<<64);cv=ch+u/2
assert canonical(clower) and canonical(cupper)
assert cv-value(clower)==value(cupper)-cv==u/2
assert parity(clower)==parity(cupper)==1
cbits=e.encode(cv,e.FORMATS['f128'])[0]
assert e.decode(cbits,e.FORMATS['f128'])[0]==cv
assert e.encode(cv,f)[0]==chbits
print(f'Exact binary128 input {cbits:032x} is also a zero-low odd/odd canonical-pair midpoint.')
for major in map(int,sys.argv[1:] or (18,23)):
    edge=e.Edge(major);edge.env[1]=0
    actual=edge.call('fma_ppcf128_rm',a,b,c,0)[0]
    print(f'LLVM {major} current result {actual:032x}, flags={edge.env[1]}; every nearest result must be inexact (16).')
    edge.env[1]=0
    actual=edge.call('fptrunc_f128_ppcf128_rm',cbits,0)[0]
    print(f'LLVM {major} current conversion {actual:032x}, flags={edge.env[1]}; every nearest result must be inexact (16), without underflow.')
print('Witness verified; the nearest-even tie rule requires a contract decision. This is not a conformance pass.')
