"""Fraction oracles for 0.2.12 exact-sum conversions and integral operations.

No arithmetic implementation source is imported. Pair results here are exact
integer decompositions; this module does not choose an ambiguous pair midpoint.
"""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',ROOT/'tests/test_edge.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
F=e.FORMATS['f64'];MASK64=(1<<64)-1

def decode(raw):
    h,sign,sn=e.decode(raw&MASK64,F);l,_,lsn=e.decode(raw>>64,F)
    if h=='nan' or l=='nan': return 'nan',sign,sn or lsn
    if isinstance(h,str): return h,sign,sn or lsn
    if isinstance(l,str): return l,(raw>>127)&1,sn or lsn
    return h+l,sign,sn or lsn

def pair(h,l=0,zero_sign=0):
    hi=e.encode(h,F,zero_sign=zero_sign)[0];lo=e.encode(l,F)[0]
    raw=hi|(lo<<64)
    if not isinstance(h,str):
        assert e.decode(hi,F)[0]==h and e.decode(lo,F)[0]==l
        assert e.encode(h+l,F,zero_sign=zero_sign)[0]==hi
    return raw

def integer_pair(n,zero_sign=0):
    hi=e.encode(e.Q(n),F,zero_sign=zero_sign)[0]
    h=e.decode(hi,F)[0]
    assert not isinstance(h,str), 'integer decomposition requires an in-range result'
    residual=e.Q(n)-h;lo=e.encode(residual,F)[0]
    assert e.decode(lo,F)[0]==residual, 'exact integral result must fit two components'
    raw=hi|(lo<<64)
    assert decode(raw)[0]==n
    return raw

def integral(raw,op,rm=0):
    v,sign,sn=decode(raw)
    if isinstance(v,str):
        return e.nan(F) if v=='nan' else (raw&MASK64),int(sn)
    mode={'floor':1,'ceil':2,'trunc':3,'round':4,'roundeven':0}.get(op,rm)
    n,flags=e.roundedq(abs(v),sign,mode)
    if sign:n=-n
    return integer_pair(n,sign),flags if op=='rint' else 0

def to_integer(raw,bits,signed,mode,signal_inexact=True):
    v,sign,_=decode(raw)
    lower=-(1<<(bits-1)) if signed else 0;upper=(1<<(bits-int(signed)))-1
    if v=='nan': return 0,1
    if v=='inf': return (lower if sign else upper),1
    n,flags=e.roundedq(abs(v),sign,mode)
    if sign:n=-n
    if not signal_inexact:flags=0
    if n<lower or n>upper:flags|=1
    return max(lower,min(upper,n)),flags

def convert(raw,dest,rm=0):
    v,sign,sn=decode(raw)
    value,flags=e.encode(v,dest,rm,sign)
    return value,flags|int(sn)
