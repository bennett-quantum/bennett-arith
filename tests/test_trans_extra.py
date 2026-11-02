"""Exhaustive small-format sin, PPC libm, sincospi, and constrained flags."""
import ctypes,importlib.util,pathlib,sys,random
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('trans',R/'tests/test_trans.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
s=importlib.util.spec_from_file_location('ppc_exp',R/'tests/test_ppc_exp.py');ppc_exp=importlib.util.module_from_spec(s);s.loader.exec_module(ppc_exp)
e=t.e;m=t.m;C=t.C;MP=t.MP
for op in ['sinpi','cospi']:
    fn=getattr(m,'mpfr_'+op);fn.argtypes=[C.POINTER(MP),C.POINTER(MP),C.c_int];fn.restype=C.c_int

def dd(v,sign=0,rm=0):
    f=e.FORMATS['f64']
    if isinstance(v,str):return (e.nan(f) if v=='nan' else e.infinity(f,sign))
    if not v:return sign<<63
    step=max(e.log2q(abs(v)),-969)-105
    n,_=e.roundedq(abs(v)/e.power(step),v<0,rm);v=(-1 if v<0 else 1)*n*e.power(step)
    hi=e.encode(v,f)[0];h,_,_=e.decode(hi,f)
    if isinstance(h,str):return hi
    return hi|(e.encode(v-h,f)[0]<<64)
def undd(raw):
    h,s,_=e.decode(raw&((1<<64)-1),e.FORMATS['f64'])
    if isinstance(h,str):return h,s
    l,_,_=e.decode(raw>>64,e.FORMATS['f64']);return h+l,s
for major in map(int,sys.argv[1:] or [18,23]):
    edge=e.Edge(major);oracle=t.Oracle();worst=e.Q(0)
    for suffix in ('f16','bf16'):
        f=e.FORMATS[suffix]
        for raw in range(65536):
            v,sign,_=e.decode(raw,f);want,ws=oracle.call('sin',v,sign)
            actual=edge.call('sin_'+suffix,raw)[0];av,_,_=e.decode(actual,f)
            expected=e.encode(want,f,zero_sign=ws)[0]
            if isinstance(want,str) or isinstance(av,str) or not want or not av:assert actual==expected,(suffix,raw,actual,expected)
            else:
                step=max(e.log2q(abs(want)),1-f[3])-(f[1]-1)
                err=abs(av-want)/e.power(step);assert err<=1,(suffix,raw,float(err));worst=max(worst,err)
            edge.count+=1
        print(f'LLVM {major} exhaustive sin {suffix}: 65536 encodings',flush=True)
    values=[0,1,1<<63,e.infinity(e.FORMATS['f64']),e.infinity(e.FORMATS['f64'],1),e.nan(e.FORMATS['f64'])]
    for exp in range(-1074,1024,29):
        for sign in [1,-1]:
            values.append(dd(sign*e.power(exp)))
            if exp> -1000 and exp<1000:values.append(dd(sign*(e.power(exp)+e.power(exp-60))))
    for raw in values:
        v,sign=undd(raw)
        for op in t.ops:
            b=e.Q(3,2) if op=='pow' else e.Q(-3,4);br=dd(b)
            want,ws=oracle.call(op,v,sign,b);actual=edge.call(op+'_ppcf128',raw,*([br] if op in ('atan2','pow') else []))[0]
            av,_=undd(actual);expected=dd(want,ws)
            if isinstance(want,str) or isinstance(av,str) or not want or not av:assert actual==expected,(major,op,hex(raw),hex(actual),hex(expected))
            else:
                step=max(e.log2q(abs(want)),-969)-105;err=abs(av-want)/e.power(step)
                assert err<=4,(major,op,hex(raw),float(err));worst=max(worst,err)
            edge.count+=1
        edge.check('sincos_ppcf128',[raw],(edge.call('sin_ppcf128',raw)[0],edge.call('cos_ppcf128',raw)[0]))
    # All _rm signatures, with a nontrivial finite point and unchanged sticky bits.
    for suffix,f in list(e.FORMATS.items())+[('ppcf128',None)]:
        enc=(lambda v,s=0:dd(v,s)) if f is None else (lambda v,s=0:e.encode(v,f,zero_sign=s)[0])
        dec=(lambda r:undd(r)[0]) if f is None else (lambda r:e.decode(r,f)[0])
        for op in t.ops:
            a=e.Q(1,2);b=e.Q(3,2) if op=='pow' else e.Q(-3,4)
            want,ws=oracle.call(op,a,0,b)
            for rm in range(5):
                edge.env[1]=32
                got=edge.call(op+'_'+suffix+'_rm',enc(a),*([enc(b)] if op in ('atan2','pow') else []),rm)[0]
                av=dec(got);step=max(e.log2q(abs(want)),-969 if f is None else 1-f[3])-(105 if f is None else f[1]-1)
                assert abs(av-want)<=4*e.power(step),(suffix,op,rm)
                assert edge.env[1]&32
                edge.count+=1
        for v in [e.Q(0),e.Q(-0),e.Q(1,2),e.Q(-1,2),e.Q(1),e.Q(-1),e.Q(3,2),e.Q(1024),e.power(100)]:
            source=enc(v);vv=dec(source)
            sv,ss=oracle.call('sinpi',vv,0);cv,cs=oracle.call('cospi',vv,0)
            expected=(enc(sv,ss),enc(cv,cs))
            # Approximate finite outputs may differ at a rounding boundary.
            actual=edge.call('sincospi_'+suffix,enc(v))
            for got,want in zip(actual,expected):
                gv,wv=dec(got),dec(want)
                if isinstance(wv,str) or not wv:assert got==want,(suffix,'sincospi',v,hex(got),hex(want))
                else:assert abs(gv-wv)<=e.power(e.log2q(abs(wv))-(104 if f is None else f[1]-2))
            for rm in range(5):
                pair=edge.call('sincospi_'+suffix+'_rm',enc(v),rm);assert len(pair)==2;edge.count+=1
            for rm in range(5):
                pair=edge.call('sincos_'+suffix+'_rm',enc(v),rm)
                assert pair==(edge.call('sin_'+suffix+'_rm',enc(v),rm)[0],edge.call('cos_'+suffix+'_rm',enc(v),rm)[0]);edge.count+=1
            edge.count+=1
        for op,v,want,flags in [('sin',0,0,0),('exp',0,1,0),('exp2',3,8,0),('log',1,0,0),('log2',8,3,0),('acos',1,0,0)]:
            for rm in range(5):edge.check(op+'_'+suffix+'_rm',[enc(e.Q(v)),rm],enc(e.Q(want)),flags)
        inf=enc('inf');nan=enc('nan')
        for rm in range(5):
            edge.check('sin_'+suffix+'_rm',[inf,rm],nan,1)
            edge.check('log_'+suffix+'_rm',[enc(e.Q(0)),rm],enc('inf',1),2)
    print(f'LLVM {major}: {edge.count} exhaustive/PPC/libm-rounding checks; max observed ulp {float(worst):.9f}',flush=True)
    ppc_exp.run(major)
