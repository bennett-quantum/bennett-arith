"""Black-box the published bitcode, using Fraction/integer-only IEEE oracles.
Python -I isolates imports. No host FP, libm, APFloat, or implementation sources
are used to compute expected answers. Counts include numerical assertions only.
"""
import ctypes
from fractions import Fraction as Q
from math import isqrt
import json
import pathlib
import random
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMATS = dict(f16=(16,11,5,15,False), bf16=(16,8,8,127,False),
               f32=(32,24,8,127,False), f64=(64,53,11,1023,False),
               f80=(80,64,15,16383,True), f128=(128,113,15,16383,False))
MASK128 = (1<<128)-1

def power(e):
    return Q(1<<e) if e>=0 else Q(1,1<<-e)

def decode(x, f):
    bits,p,eb,bias,explicit = f
    sign = x>>(bits-1)
    exp = (x>>(p-1+explicit)) & ((1<<eb)-1)
    mant = x & ((1<<(p-1+explicit))-1)
    if explicit and bool(exp) != bool(mant>>(p-1)):
        return 'nan',sign,True
    if exp == (1<<eb)-1:
        if mant & ((1<<(p-1))-1):
            return 'nan',sign,not bool(mant & (1<<(p-2)))
        return 'inf',sign,False
    if exp and not explicit:
        mant += 1<<(p-1)
    value = mant * power((exp or 1)-bias-(p-1))
    return -value if sign else value, sign, False

def nan(f):
    bits,p,eb,bias,explicit=f
    return (((1<<eb)-1)<<(p-1+explicit)) | (1<<(p-2)) | ((1<<(p-1)) if explicit else 0)

def infinity(f,sign=0):
    bits,p,eb,bias,explicit=f
    return (sign<<(bits-1)) | (((1<<eb)-1)<<(p-1+explicit)) | ((1<<(p-1)) if explicit else 0)

def log2q(v):
    n=v.numerator.bit_length()-v.denominator.bit_length()
    return n-1 if v<power(n) else n

def roundedq(v, sign, mode):
    q,r=divmod(v.numerator,v.denominator)
    if not r:
        return q,0
    up=(mode==1 and sign) or (mode==2 and not sign)
    if mode in (0,4):
        twice=2*r
        up=twice>v.denominator or (twice==v.denominator and (mode==4 or q&1))
    return q+bool(up),16

def encode(value,f,mode=0,zero_sign=0):
    bits,p,eb,bias,explicit=f
    if value=='nan':
        return nan(f),0
    if value=='inf':
        return infinity(f,zero_sign),0
    if not value:
        return zero_sign<<(bits-1),0
    sign=int(value<0); v=abs(value)
    top=log2q(v)
    step=max(top,1-bias)-(p-1)
    q,flags=roundedq(v/power(step),sign,mode)
    if q>=1<<p:
        q>>=1; step+=1
    exponent=step+p-1
    if exponent>bias:
        flags|=20
        if mode==3 or (mode==1 and not sign) or (mode==2 and sign):
            return ((sign<<(bits-1)) | (((1<<eb)-2)<<(p-1+explicit)) |
                    ((1<<(p-1+explicit))-1)),flags
        return infinity(f,sign),flags
    if q<1<<(p-1):
        return (sign<<(bits-1))|q, flags | (8 if flags&16 else 0)
    return ((sign<<(bits-1))|((exponent+bias)<<(p-1+explicit))|
            (q if explicit else q & ((1<<(p-1))-1))), flags

def oracle(op,values,f,mode=0):
    decoded=[decode(x,f) for x in values]
    a,sa,sna=decoded[0]
    b,sb,snb=decoded[1] if len(decoded)>1 else (Q(0),0,False)
    c,sc,snc=decoded[2] if len(decoded)>2 else (Q(0),0,False)
    flags=int(sna or snb or snc)
    if op=='sub':
        sb^=1
        if not isinstance(b,str): b=-b
        op='add'
    if op=='fma':
        if a=='nan' or b=='nan' or c=='nan': return nan(f),flags
        if (a=='inf' and b==0) or (b=='inf' and a==0): return nan(f),1
        if a=='inf' or b=='inf':
            if c=='inf' and sa^sb!=sc: return nan(f),1
            return infinity(f,sa^sb),flags
        if c=='inf': return infinity(f,sc),flags
        v=a*b+c
        z=(sa^sb) if a*b==0 and c==0 and (sa^sb)==sc else int(mode==1)
    elif op=='add':
        if a=='nan' or b=='nan': return nan(f),flags
        if a=='inf' or b=='inf':
            if a==b=='inf' and sa!=sb: return nan(f),1
            return infinity(f,sa if a=='inf' else sb),flags
        v=a+b; z=sa if sa==sb else int(mode==1)
    elif op=='mul':
        if a=='nan' or b=='nan': return nan(f),flags
        if (a=='inf' and b==0) or (b=='inf' and a==0): return nan(f),1
        if a=='inf' or b=='inf': return infinity(f,sa^sb),flags
        v=a*b; z=sa^sb
    elif op=='div':
        if a=='nan' or b=='nan': return nan(f),flags
        if a==b=='inf' or a==b==0: return nan(f),1
        if a=='inf': return infinity(f,sa^sb),flags
        if b==0: return infinity(f,sa^sb),flags|2
        if b=='inf': return (sa^sb)<<(f[0]-1),flags
        v=a/b; z=sa^sb
    elif op=='rem':
        if a=='nan' or b=='nan': return nan(f),flags
        if a=='inf' or b==0: return nan(f),1
        if b=='inf': return encode(a,f,mode,sa)
        v=a-int(a/b)*b; z=sa
    elif op=='sqrt':
        if a=='nan': return nan(f),flags
        if sa and (a=='inf' or a!=0): return nan(f),1
        if a=='inf': return infinity(f),flags
        if not a: return sa<<(f[0]-1),flags
        bits,p,eb,bias,explicit=f
        top=log2q(a)//2; step=max(top,1-bias)-(p-1)
        scaled=a/power(2*step)
        q=isqrt(scaled.numerator//scaled.denominator)
        exact=q*q*scaled.denominator==scaled.numerator
        if not exact:
            cmp=4*scaled.numerator-scaled.denominator*(2*q+1)**2
            if mode==2 or (mode in (0,4) and (cmp>0 or (cmp==0 and (mode==4 or q&1)))):
                q+=1
        v=q*power(step); z=0; flags|=0 if exact else 16
    else:
        raise AssertionError(op)
    out,more=encode(v,f,mode,z)
    return out,flags|more

class Aligned:
    def __init__(self,size):
        self.buf=ctypes.create_string_buffer(size+15)
        self.addr=(ctypes.addressof(self.buf)+15)&~15
        self.size=size
    def put(self, data): ctypes.memmove(self.addr,data,len(data))
    def read(self): return ctypes.string_at(self.addr,self.size)

class Edge:
    def __init__(self,major):
        self.major=major
        self.path=ROOT/f'.tmp/llvm{major}'
        self.manifest=json.loads((ROOT/f'dist/llvm{major}/manifest.json').read_text())
        self.rows={x['name']:x for x in self.manifest['exports']}
        self.lib=ctypes.CDLL(str(self.path/'oracle.so'))
        self.fn=self.lib.test_call
        self.fn.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p]
        self.env=(ctypes.c_int*2).in_dll(self.lib,'__bennett_rt_fenv')
        self.args=Aligned(96); self.out=Aligned(32)
        self.count=0; self.seen=set()
    def call(self,name,*args):
        row=self.rows['__bennett_sf_'+name]
        self.seen.add(row['name'])
        self.args.put(b''.join((x&MASK128).to_bytes(16,'little') for x in args))
        self.out.put(bytes(32))
        self.fn(row['id'],self.args.addr,self.out.addr)
        data=self.out.read()
        return int.from_bytes(data[:16],'little'),int.from_bytes(data[16:],'little')
    def check(self,name,args,expected,flags=None):
        self.env[1]=32  # unrelated sticky bits must survive
        actual=self.call(name,*args)
        want=expected if isinstance(expected,tuple) else (expected,0)
        assert actual==want,(self.major,name,[hex(a) for a in args],tuple(hex(x) for x in actual),tuple(hex(x) for x in want))
        if flags is not None:
            assert self.env[1]==32|flags,(name,args,'flags',self.env[1],flags)
        self.count+=1


def run(major):
    edge=Edge(major)
    rng=random.Random(0x023F5A7)
    # Audit the REAL published module, not the source used to build it.
    ir=(edge.path/'published.ll').read_text()
    assert not re.search(r'\b(fadd|fsub|fmul|fdiv|frem|fcmp|fptosi|fptoui|sitofp|uitofp|fpext|fptrunc)\b',ir)
    all_defs=set(re.findall(r'^define [^@\n]+@([^ (]+)',ir,re.M))
    called=set(re.findall(r'call[^\n]*@([\w.]+)',ir))
    assert all(n in all_defs or n.startswith('llvm.') for n in called), called-all_defs
    definitions=set(re.findall(r'^define (?!internal)[^@\n]+@([^ (]+)',ir,re.M))
    assert definitions==set(edge.rows),(definitions-set(edge.rows),set(edge.rows)-definitions)
    assert 'external global' in ir and '@__bennett_rt_fenv' in ir
    for suffix,f in FORMATS.items():
        bits,p,eb,bias,explicit=f
        inf=infinity(f); one=encode(Q(1),f)[0]; sign=1<<(bits-1)
        maxfinite=encode(power(bias)*(2-power(1-p)),f)[0]
        specials=[0,sign,1,sign|1, (1<<(p-1))-1,1<<(p-1),
                  one,one|sign,one+1,one-1,maxfinite,maxfinite|sign,
                  inf,inf|sign,nan(f),nan(f)|sign,nan(f)|37,
                  inf|(1<<(p-3)), inf|1]
        if explicit: specials += [1<<63, (1<<64)|1, ((1<<15)-1)<<64]
        pairs=[(a,b) for a in specials for b in specials]
        pairs += [(rng.getrandbits(bits),rng.getrandbits(bits)) for _ in range(140)]
        for op in ('add','sub','mul','div','rem'):
            for a,b in pairs:
                expected,flags=oracle(op,[a,b],f)
                edge.check(op+'_'+suffix,[a,b],expected,0)
            for mode in range(5):
                for a,b in pairs[::7]:
                    expected,flags=oracle(op,[a,b],f,mode)
                    edge.check(op+'_'+suffix+'_rm',[a,b,mode],expected,flags)
        triples=[(a,b,c) for a,b,c in zip(specials,specials[::-1],specials[2:]+specials[:2])]
        triples += [(rng.getrandbits(bits),rng.getrandbits(bits),rng.getrandbits(bits)) for _ in range(150)]
        # Cancellation after an exact product, including a fused/unfused witness.
        eps=power(1-p)
        triples += [(encode(1+eps,f)[0],encode(1-eps,f)[0],encode(Q(-1),f)[0])]
        for a,b,c in triples:
            for mode in range(5):
                expected,flags=oracle('fma',[a,b,c],f,mode)
                edge.check('fma_'+suffix+'_rm',[a,b,c,mode],expected,flags)
            edge.check('fma_'+suffix,[a,b,c],oracle('fma',[a,b,c],f)[0],0)
        vals=specials+[rng.getrandbits(bits) for _ in range(200)]
        for a in vals:
            v,s,snan=decode(a,f)
            for mode in range(5):
                result,flags=oracle('sqrt',[a],f,mode)
                edge.check('sqrt_'+suffix+'_rm',[a,mode],result,flags)
            edge.check('sqrt_'+suffix,[a],oracle('sqrt',[a],f)[0],0)
            edge.check('canonicalize_'+suffix,[a],nan(f) if v=='nan' else a,0)
            cls=0 if snan else 1 if v=='nan' else (2 if s else 9) if v=='inf' else (5 if s else 6) if not v else (4 if s else 7) if abs(v)<power(1-bias) else (3 if s else 8)
            for mask in (0,1<<cls,1023^(1<<cls),1023):
                edge.check('isfpclass_'+suffix,[a,mask],int(bool(mask&(1<<cls))),0)
            for op,mode in [('floor',1),('ceil',2),('trunc',3),('round',4),('roundeven',0),('rint',0),('nearbyint',0)]:
                if isinstance(v,str): result=nan(f) if v=='nan' else a; flags=int(snan)
                else:
                    n,flags=roundedq(abs(v),s,mode)
                    result=encode(-Q(n) if s else Q(n),f,zero_sign=s)[0]
                edge.check(op+'_'+suffix,[a],result,0)
                edge.check(op+'_'+suffix+'_rm',[a,3],result,(flags if op!='nearbyint' else flags&~16)|int(snan))
            for op,mode,signed in [('fptosi',3,True),('fptoui',3,False),('lround',4,True),('llround',4,True),('lrint',0,True),('llrint',0,True)]:
                for width in (1,8,64,128):
                    lo=-(1<<(width-1)) if signed else 0
                    hi=(1<<(width-int(signed)))-1
                    flags=0
                    if v=='nan': n=0; flags=1
                    elif v=='inf': n=lo if s else hi; flags=1
                    else:
                        n,flags=roundedq(abs(v),s,mode); n=-n if s else n
                        if n<lo or n>hi: flags|=1
                        n=max(lo,min(hi,n))
                    edge.check(op+'_'+suffix,[a,width],n&MASK128,0)
                    edge.check(op+'_'+suffix+'_rm',[a,width,0],n&MASK128,flags)
            # frexp and modf use literal aggregate ABI and field order.
            if isinstance(v,str): fract,whole=nan(f) if v=='nan' else s<<(bits-1),nan(f) if v=='nan' else a
            else:
                whole=encode(Q(int(v)),f,zero_sign=s)[0]
                fract=encode(v-int(v),f,zero_sign=s)[0]
            edge.check('modf_'+suffix,[a],(fract,whole),0)
            if isinstance(v,str) or not v: fraction,exponent=(nan(f) if v=='nan' else a),0
            else:
                exponent=log2q(abs(v))+1; fraction=encode(v/power(exponent),f)[0]
            edge.check('frexp_'+suffix,[a],(fraction,exponent&0xffffffff),0)
            for exp in (-2147483648,-20000,-1,0,1,20000,2147483647):
                if isinstance(v,str) or not v: result=nan(f) if v=='nan' else a; flags=int(snan)
                elif exp < -40000: result,flags=encode(-power(-50000) if s else power(-50000),f)
                elif exp > 40000: result,flags=encode(-power(50000) if s else power(50000),f)
                else: result,flags=encode(v*power(exp),f)
                edge.check('ldexp_'+suffix,[a,exp],result,0)
                edge.check('ldexp_'+suffix+'_rm',[a,exp,0],result,flags)
        for a,b in pairs[::4]:
            av,sa,_=decode(a,f); bv,sb,_=decode(b,f)
            unordered=av=='nan' or bv=='nan'
            def key(v,s): return (-1 if s else 1)*power(50000) if v=='inf' else v
            if not unordered: cmp=(key(av,sa)>key(bv,sb))-(key(av,sa)<key(bv,sb))
            for pred in range(16):
                result=int(pred>=8) if unordered else [False,cmp==0,cmp>0,cmp>=0,cmp<0,cmp<=0,cmp!=0,True][pred&7]
                edge.check('cmp_'+suffix,[a,b,pred],int(result),0)
            for op in ('minnum','maxnum','minimum','maximum','minimumnum','maximumnum'):
                if unordered:
                    result=nan(f) if (av==bv=='nan' or op in ('minimum','maximum')) else (b if av=='nan' else a)
                else:
                    less=cmp<0 or (cmp==0 and sa>sb)
                    result=(a if less else b) if op.startswith('min') else (b if less else a)
                edge.check(op+'_'+suffix,[a,b],result,0)
                # flags: signaling NaN raises invalid; quiet NaN does not.
                invalid=int(decode(a,f)[2] or decode(b,f)[2])
                edge.check(op+'_'+suffix+'_rm',[a,b,0],result,invalid)
        ints=[0,1,-1,1<<63,-(1<<127),(1<<127)-1,(1<<128)-1]+[rng.getrandbits(128) for _ in range(60)]
        for n in ints:
            u=n&MASK128
            for op in ('sitofp','uitofp'):
                value=u-(1<<128) if op=='sitofp' and u>>127 else u
                result,_=encode(Q(value),f)
                edge.check(op+'_'+suffix,[u],result,0)
                for mode in range(5):
                    result,flags=encode(Q(value),f,mode)
                    edge.check(op+'_'+suffix+'_rm',[u,mode],result,flags)
        # All pairwise format routes, canonical NaNs and directed rounding.
        for dest,df in FORMATS.items():
            if dest==suffix: continue
            for a in vals[::4]:
                v,s,sn=decode(a,f)
                for op in ('fpext','fptrunc'):
                    result,_=encode(v,df,zero_sign=s)
                    edge.check(op+'_'+suffix+'_'+dest,[a],result,0)
                    for mode in range(5):
                        result,flags=encode(v,df,mode,s)
                        edge.check(op+'_'+suffix+'_'+dest+'_rm',[a,mode],result,flags|int(sn))
        # Wide slots test non-byte and non-limb widths, both integer directions.
        for width in (129,193,257,513,1025):
            slot=Aligned(8*((width+63)//64))
            for n in (0,1,(1<<(width-1)),(1<<width)-1,(1<<(width-1))+12345):
                slot.put(n.to_bytes(slot.size,'little'))
                for op in ('sitofp','uitofp'):
                    v=n-(1<<width) if op=='sitofp' and n>>(width-1) else n
                    edge.check(op+'_'+suffix+'_wide',[slot.addr,width],encode(Q(v),f)[0],0)
            for a in specials:
                v,s,_=decode(a,f)
                for op in ('fptosi','fptoui','lround','llround','lrint','llrint'):
                    signed=op!='fptoui'; mode=3 if op.startswith('fpto') else 4 if op in ('lround','llround') else 0
                    lo=-(1<<(width-1)) if signed else 0; hi=(1<<(width-int(signed)))-1
                    if v=='nan': n=0
                    elif v=='inf': n=lo if s else hi
                    else:
                        n,_=roundedq(abs(v),s,mode); n=-n if s else n; n=max(lo,min(hi,n))
                    slot.put(bytes([0xaa])*slot.size)
                    edge.check(op+'_'+suffix+'_wide',[slot.addr,a,width],0,0)
                    assert int.from_bytes(slot.read(),'little')==n% (1<<width),(suffix,width,op,hex(a),'wide output')
                    edge.count+=1
        for exponent in (-2147483648,-7,-1,0,1,2,13,2147483647):
            # Own-format powi: independently compose rounded scalar operations.
            for a in (one,one|sign,0,sign,encode(Q(3,2),f)[0],nan(f)):
                n=abs(exponent); acc=one; base=a
                while n:
                    if n&1: acc=oracle('mul',[acc,base],f)[0]
                    n>>=1
                    if n: base=oracle('mul',[base,base],f)[0]
                if exponent<0: acc=oracle('div',[one,acc],f)[0]
                edge.check('powi_'+suffix+'_i32',[a,exponent],acc,0)
    # Exhaustive small-format encodings: canonicalization, classes, fpext/fptrunc
    # round trip, and sqrt independently rounded by squared midpoint comparison.
    for suffix in ('f16','bf16'):
        f=FORMATS[suffix]
        for a in range(65536):
            v,s,sn=decode(a,f)
            edge.check('canonicalize_'+suffix,[a],nan(f) if v=='nan' else a,0)
            ext=encode(v,FORMATS['f32'],zero_sign=s)[0]
            edge.check('fpext_'+suffix+'_f32',[a],ext,0)
            edge.check('fptrunc_f32_'+suffix,[ext],nan(f) if v=='nan' else a,0)
            edge.check('sqrt_'+suffix,[a],oracle('sqrt',[a],f)[0],0)
    # Spec n-fmuladd: unfused +0 versus fused 2^-54; no host FMA.
    a,b,c=0x3fb999999999999a,0x4024000000000000,0xbff0000000000000
    product=edge.call('mul_f64',a,b)[0]
    edge.check('add_f64',[product,c],0,0)
    edge.check('fma_f64',[a,b,c],0x3c90000000000000,0)
    # Rotation/reassociation input: sitofp i128, ordered left fold, no reassoc.
    n=(1<<100)+3
    edge.check('sitofp_f64',[n],encode(Q(n),FORMATS['f64'])[0],0)
    a,b,c=encode(power(100),FORMATS['f64'])[0],encode(-power(100),FORMATS['f64'])[0],encode(Q(1),FORMATS['f64'])[0]
    left=edge.call('add_f64',edge.call('add_f64',a,b)[0],c)[0]
    right=edge.call('add_f64',a,edge.call('add_f64',b,c)[0])[0]
    assert left==0x3ff0000000000000 and right==0
    edge.count+=2
    assert edge.seen==set(edge.rows),sorted(set(edge.rows)-edge.seen)
    print(f'LLVM {major}: {edge.count} numerical checks; {len(edge.seen)} exported signatures exercised',flush=True)
    return dict(major=major, numerical_checks=edge.count, exports_exercised=len(edge.seen))

if __name__=='__main__':
    results=[]
    for major in map(int,sys.argv[1:] or (18,23)):
        results.append(run(major))
    (ROOT/'.tmp/test-results.json').write_text(json.dumps(results,indent=2)+'\n')
