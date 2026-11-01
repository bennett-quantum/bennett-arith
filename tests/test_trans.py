"""Independent MPFR oracle against the actual published carrier functions.
MPFR is test-only. Production bitcode has no external numerical dependency.
"""
import ctypes as C,importlib.util,pathlib,sys,random
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',R/'tests/test_edge.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
class MP(C.Structure):
    _fields_=[('prec',C.c_long),('sign',C.c_int),('exp',C.c_long),('limbs',C.c_void_p)]
m=C.CDLL('libmpfr.so.6')
for name,args,ret in [('init2',[C.POINTER(MP),C.c_long],None),('clear',[C.POINTER(MP)],None),('set_str',[C.POINTER(MP),C.c_char_p,C.c_int,C.c_int],C.c_int),('mul_2si',[C.POINTER(MP),C.POINTER(MP),C.c_long,C.c_int],C.c_int),('get_str',[C.c_void_p,C.POINTER(C.c_long),C.c_int,C.c_size_t,C.POINTER(MP),C.c_int],C.c_void_p),('free_str',[C.c_void_p],None)]:
    f=getattr(m,'mpfr_'+name);f.argtypes=args;f.restype=ret
ops='sin cos tan asin acos atan sinh cosh tanh exp exp2 exp10 log log2 log10 atan2 pow'.split()
for op in ops:
    fn=getattr(m,'mpfr_'+op);fn.argtypes=[C.POINTER(MP)]*(4 if op in ('atan2','pow') else 3) # last is rounding, corrected below
    fn.argtypes=[C.POINTER(MP)]*(3 if op in ('atan2','pow') else 2)+[C.c_int]
    fn.restype=C.c_int
class Oracle:
    def __init__(self):
        self.a=MP();self.b=MP();self.r=MP()
        for x in (self.a,self.b,self.r):m.mpfr_init2(C.byref(x),384)
    def put(self,x,v,sign=0):
        if isinstance(v,str):s=('-' if sign else '')+('nan' if v=='nan' else 'inf');m.mpfr_set_str(C.byref(x),s.encode(),10,0);return
        n=v.numerator;d=v.denominator
        s=('-' if n<0 or not n and sign else '')+bin(abs(n))[2:]
        assert m.mpfr_set_str(C.byref(x),s.encode(),2,0)==0
        m.mpfr_mul_2si(C.byref(x),C.byref(x),-(d.bit_length()-1),0)
    def get(self):
        exp=C.c_long();p=m.mpfr_get_str(None,C.byref(exp),2,384,C.byref(self.r),0)
        s=C.string_at(p).decode();m.mpfr_free_str(p)
        if '@NaN@' in s:return 'nan',0
        if '@Inf@' in s:return 'inf',int(s.startswith('-'))
        sign=int(s.startswith('-'));s=s.lstrip('-')
        if abs(exp.value)>20000:return (-1 if sign else 1)*e.power(20000 if exp.value>0 else -20000),sign
        return (-1 if sign else 1)*int(s,2)*e.power(exp.value-len(s)),sign
    def call(self,op,a,sa,b=0,sb=0):
        self.put(self.a,a,sa);self.put(self.b,b,sb)
        fn=getattr(m,'mpfr_'+op)
        if op in ('atan2','pow'):fn(C.byref(self.r),C.byref(self.a),C.byref(self.b),0)
        else:fn(C.byref(self.r),C.byref(self.a),0)
        return self.get()
if __name__=='__main__':
    for major in map(int,sys.argv[1:] or [18,23]):
        edge=e.Edge(major)
        assert '__bennett_sf_sin_f128' in edge.rows,'RED: missing own-format binary128 sin'
        oracle=Oracle();rng=random.Random(0x12851);worst={}
        for suffix,f in e.FORMATS.items():
            bits,p,eb,bias,_=f
            values=[0,1,1<<(bits-1),e.infinity(f),e.infinity(f,1),e.nan(f)]
            for q in [e.Q(1),e.Q(-1),e.Q(1,2),e.Q(-1,2),e.Q(2),e.Q(-2),e.Q(10),e.Q(-10)]:values.append(e.encode(q,f)[0])
            for exp in list(range(1,(1<<eb)-1,max(1,((1<<eb)-2)//160)))+[1,2,bias,bias+1,(1<<eb)-2]:
                for frac in [0,1,(1<<(p-1))-1]:
                    # Explicit x87 significand.
                    raw=(exp<<(p-1+f[4]))|frac|((1<<(p-1)) if f[4] else 0)
                    values += [raw,raw^(1<<(bits-1))]
            one=e.encode(e.Q(1),f)[0]
            values += [one-1,one+1,one-2,one+2]
            for text in ['3.1415926535897932384626433832795028841971','1.5707963267948966192313216916397514420986','11356.523406294143949491931077970763']:
                center=e.encode(e.Q(text),f)[0]
                if center!=e.infinity(f):values += [center+d for d in range(-2,3)]
            for _ in range(64):values.append(rng.getrandbits(bits))
            for _ in range(50):values.append(e.encode(e.Q(rng.randrange(-10000,10000),1024),f)[0])
            for raw in values:
                a,sa,_=e.decode(raw,f)
                for op in ops:
                    b=e.Q(3,2) if op=='pow' else e.Q(-3,4)
                    rb=e.encode(b,f)[0]
                    want,ws=oracle.call(op,a,sa,b)
                    args=[raw,rb] if op in ('pow','atan2') else [raw]
                    expected=e.encode(want,f,zero_sign=ws)[0]
                    actual=edge.call(op+'_'+suffix,*args)[0]
                    av,_,_=e.decode(actual,f)
                    if isinstance(want,str) or isinstance(av,str) or not want or not av:
                        assert actual==expected,(major,suffix,op,hex(raw),hex(actual),hex(expected))
                    else:
                        step=max(e.log2q(abs(want)),1-bias)-(p-1)
                        ulps=abs(av-want)/e.power(step)
                        assert ulps<=4,(major,suffix,op,hex(raw),float(ulps))
                        worst[op]=max(worst.get(op,e.Q(0)),ulps)
                    edge.count+=1
                # Pair order and scalar consistency, including signed zeros/NaNs.
                edge.check('sincos_'+suffix,[raw],(edge.call('sin_'+suffix,raw)[0],edge.call('cos_'+suffix,raw)[0]))
            print(f'LLVM {major} {suffix}: {edge.count} checks so far',flush=True)
        print(f'LLVM {major}: {edge.count} own-format MPFR/pair checks; max observed ulp '+str({k:round(float(v),5) for k,v in worst.items()}),flush=True)
