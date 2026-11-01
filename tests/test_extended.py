"""Boundary and full-signature coverage for added PPC, libm and rounding entries."""
import ctypes,importlib.util,pathlib,sys
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('edge',R/'tests/test_edge.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
f=e.FORMATS['f64'];mask=(1<<128)-1

def ddinteger(n,rm,major):
    if major==18:
        legacy=(128,106,11,1023,False);raw=e.encode(e.Q(n),legacy,rm)[0];v,sign,_=e.decode(raw,legacy)
        if isinstance(v,str):return e.infinity(f,sign)
        hi=e.encode(v,f)[0];h=e.decode(hi,f)[0];return hi|(e.encode(v-h,f)[0]<<64)
    neg=n<0;n=abs(n);hi=e.encode(e.Q(n),f)[0];h=e.decode(hi,f)[0]
    if isinstance(h,str):return e.infinity(f,neg)
    error=n-h;lm=rm
    if error<0 and rm==3:lm=1
    if error<0 and rm==4:
        step=e.log2q(-error)-52
        if (-error/e.power(step))%1==e.Q(1,2):lm=2
    lo=e.encode(error,f,lm)[0];lv=e.decode(lo,f)[0];total=h+lv
    newhi=e.encode(total,f)[0];newh=e.decode(newhi,f)[0]
    newlo=e.encode(lv-(newh-h),f,zero_sign=(lo>>63) if lv==0 and newh==h else 0)[0]
    r=newhi|(newlo<<64)
    return r^((1<<63)|(1<<127)) if neg else r
for major in map(int,sys.argv[1:] or [18,23]):
    edge=e.Edge(major)
    for bits in [129,193,257,513,1025]:
        for n in [0,1,-1,(1<<(bits-2))+1,-(1<<(bits-2))-1,(1<<(bits-2))-(1<<(bits-70))-1]:
            buf=e.Aligned(8*((bits+63)//64));buf.put((n% (1<<bits)).to_bytes(buf.size,'little'))
            for rm in range(5):
                want=ddinteger(n,rm,major)
                edge.check('sitofp_ppcf128_wide_rm',[buf.addr,bits,rm],want)
                if n>=0:edge.check('uitofp_ppcf128_wide_rm',[buf.addr,bits,rm],want)
    sparse=0x7e70000000000000|(0x3ff0000000000000<<64)
    edge.check('modf_ppcf128',[sparse],(0,sparse))
    belowone=0x3ff0000000000000|(0x8000000000000001<<64)
    edge.check('modf_ppcf128',[belowone],(belowone,0))
    for rm in range(5):
        # Exact combined value is 2^-1023 + 0.625 * 2^-1074.
        want=0x8000000000000+(rm in (0,2,4))
        edge.check('ldexp_ppcf128_rm',[0x0030000000000001|(1<<64),-3,rm],want,24)
    if major==23:
        buf=e.Aligned(32)
        edge.call('fptoui_ppcf128_wide',buf.addr,0x43b0000000000000|(0xbff0000000000000<<64),193)
        assert int.from_bytes(buf.read(),'little')==(1<<193)-1
        edge.count+=1
        for bits in [193,513,1025]:
            for n in [(1<<(bits-2))+1,-(1<<(bits-2))-1]:
                raw=ddinteger(n,0,major);buf=e.Aligned(8*((bits+63)//64))
                edge.call('fptosi_ppcf128_wide',buf.addr,raw,bits)
                assert int.from_bytes(buf.read(),'little')==n%(1<<bits),(major,bits,'sparse wide result')
                edge.count+=1
    # Check every added signature at a simple exact numerical point. APFloat and
    # MPFR suites separately cover nontrivial numerical values.
    one=0x3ff0000000000000
    for name,row in edge.rows.items():
        if 'exponent_bits' in row:continue
        if row['fi']!=6 and row['op']!='convert':continue
        if row['op']=='convert':
            si=row['fi'];di=row['extra'];src=list(e.FORMATS.values())[si] if si<6 else f;dst=list(e.FORMATS.values())[di] if di<6 else f
            v=e.encode(e.Q(3,2),src)[0];want=e.encode(e.Q(3,2),dst)[0]
            edge.check(name[13:],[v]+([0] if row['constrained'] else []),want);continue
        op=row['op'];args=[];want=one
        if op in ('sin','cos','tan','asin','acos','atan','atan2','sinh','cosh','tanh','exp','exp2','exp10','log','log2','log10','pow','sincos','sincospi'):continue
        if row['wide']:
            buf=e.Aligned(32);buf.put((1).to_bytes(32,'little'))
            if op in ('sitofp','uitofp'):args=[buf.addr,193];want=one
            else:args=[buf.addr,one,193];want=0
        elif op in ('sitofp','uitofp'):args=[1]
        elif op in ('fptosi','fptoui','lround','llround','lrint','llrint'):args=[one,128];want=1
        elif op=='cmp':args=[one,one,1];want=1
        elif op=='isfpclass':args=[one,1<<8];want=1
        elif op=='fma':args=[one,one,one];want=0x4000000000000000
        elif op in ('add','sub','mul','div','rem','minnum','maxnum','minimum','maximum','minimumnum','maximumnum'):
            args=[one,one];want=0x4000000000000000 if op=='add' else ((1<<63)|(1<<127)) if op=='sub' else 0 if op=='rem' else one
        elif op=='ldexp':args=[one,0]
        elif op=='powi':args=[one,-3]
        elif op=='frexp':args=[one];want=(0x3fe0000000000000,1)
        elif op=='modf':args=[one];want=(0,one)
        else:args=[one]
        if row['constrained']:args+=[0]
        edge.check(name[13:],args,want)
        if row['wide'] and op not in ('sitofp','uitofp'):assert int.from_bytes(buf.read(),'little')==1;edge.count+=1
    print(f'LLVM {major}: {edge.count} additional boundary/signature checks',flush=True)
