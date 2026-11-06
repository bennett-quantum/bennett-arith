"""Fraction oracles for 0.2.13 exact-sum conversions and integral operations.

No arithmetic implementation source is imported. Pair results here are exact
rational selections, including the total nearest-even pair midpoint selector.
"""
import importlib.util
from functools import lru_cache
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

def _near_low(bits):
    if not bits or bits==1<<63:return (0,1,(1<<63)|1)
    return (bits-1,bits,bits+1)

def canonical_candidates(v):
    """Enumerate local fields and high-bin boundaries, filtering by definition."""
    high=e.encode(v,F)[0];candidates={}
    for hb in (high-1,high,high+1):
        if hb<0:continue
        hv=e.decode(hb,F)[0]
        if isinstance(hv,str):continue
        previous=e.decode(hb-1,F)[0] if hb else -e.power(-1074)
        following=e.decode(hb+1,F)[0]
        if following=='inf':following=e.power(1024)
        probes=[v-hv,(previous-hv)/2,(following-hv)/2]
        for probe in probes:
            for direction in (1,2):
                for lb in _near_low(e.encode(probe,F,direction)[0]):
                    lv=e.decode(lb,F)[0]
                    if isinstance(lv,str):continue
                    total=hv+lv
                    if total<0 or e.encode(total,F)[0]!=hb:continue
                    raw=hb|((lb if lv else 0)<<64)
                    candidates[raw]=total
    return candidates

@lru_cache(maxsize=8192)
def neighbours(raw):
    v=decode(raw)[0];candidates=canonical_candidates(v)
    return (max((x,b) for b,x in candidates.items() if x<v),
            min((x,b) for b,x in candidates.items() if x>v))

@lru_cache(maxsize=8192)
def to_pair(n,rm=0,zero_sign=0):
    """Search canonical neighbours and compare exact rational distances."""
    if not n:return zero_sign<<63,0
    negative=n<0;v=e.Q(abs(n));mode=({1:2,2:1}.get(rm,rm) if negative else rm)
    hmax=e.decode(0x7fefffffffffffff,F)[0]
    lmax=e.decode(0x7c8fffffffffffff,F)[0];maximum=hmax+lmax
    boundary=hmax+e.power(970)
    overflow=(v>=(maximum+boundary)/2 if mode in (0,4) else v>maximum if mode==2 else v>=boundary)
    maxbits=0x7fefffffffffffff|(0x7c8fffffffffffff<<64)
    def signed(bits):
        return bits^((1<<63)|((1<<127) if bits>>64 else 0)) if negative else bits
    if overflow:
        return signed(e.infinity(F) if mode in (0,2,4) else maxbits),20
    if v>maximum:return signed(maxbits),16
    candidates=canonical_candidates(v)
    below=[(x,b) for b,x in candidates.items() if x<=v]
    above=[(x,b) for b,x in candidates.items() if x>=v]
    low,lb=max(below);up,ub=min(above)
    if low==up:chosen,raw=low,lb
    elif mode in (1,3):chosen,raw=low,lb
    elif mode==2:chosen,raw=up,ub
    elif v-low<up-v:chosen,raw=low,lb
    elif v-low>up-v:chosen,raw=up,ub
    elif mode==4:chosen,raw=up,ub
    else:
        use_low=bool((lb>>64) or (ub>>64))
        even=lambda b:not (((b>>64) if use_low else b&MASK64)&1)
        chosen,raw=(low,lb) if even(lb) or not even(ub) else (up,ub)
    flags=int(chosen!=v)*16
    if flags and chosen<e.power(-1022):flags|=8
    return signed(raw),flags

def integer_to_pair(n,rm=0):return to_pair(n,rm)

def incoming(raw,fmt,rm=0):
    value,sign,sn=e.decode(raw,fmt)
    if isinstance(value,str):return (e.nan(F) if value=='nan' else e.infinity(F,sign)),int(sn)
    return to_pair(value,rm,sign)

def fma(a,b,c,rm=0):
    av,sa,an=decode(a);bv,sb,bn=decode(b);cv,sc,cn=decode(c)
    flags=int(an or bn or cn)
    if 'nan' in (av,bv,cv):return e.nan(F),flags
    invalid=(av=='inf' and bv==0) or (bv=='inf' and av==0)
    if invalid:return e.nan(F),1
    sign=sa^sb
    if av=='inf' or bv=='inf':
        if cv=='inf' and sc!=sign:return e.nan(F),1
        return e.infinity(F,sign),flags
    if cv=='inf':return e.infinity(F,sc),flags
    exact=av*bv+cv
    zero_sign=sign if (av==0 or bv==0) and cv==0 and sign==sc else int(rm==1)
    value,raised=to_pair(exact,rm,zero_sign)
    return value,flags|raised
