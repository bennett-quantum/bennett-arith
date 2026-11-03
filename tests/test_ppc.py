"""PPC component operations vs APFloat; explicit exact guarantees vs Fraction."""
import argparse, importlib.util, pathlib, subprocess, sys, random
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',R/'tests/test_edge.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
spec=importlib.util.spec_from_file_location('ppc_exact',R/'tests/test_ppc_exact.py');exact=importlib.util.module_from_spec(spec);spec.loader.exec_module(exact)
spec=importlib.util.spec_from_file_location('comparison_closure',R/'tests/test_compare_closure.py');closure=importlib.util.module_from_spec(spec);spec.loader.exec_module(closure)
o=exact.o
parser=argparse.ArgumentParser()
parser.add_argument('majors',type=int,nargs='*',default=[18,23])
parser.add_argument('--root',type=pathlib.Path,default=R)
options=parser.parse_args()
for major in options.majors:
    edge=e.Edge(major,options.root)
    assert '__bennett_sf_add_ppcf128' in edge.rows, 'RED: missing PPCDoubleDouble publication'
    llvm=f'/usr/lib/llvm-{major}/bin/'
    flags=subprocess.check_output([llvm+'llvm-config','--cxxflags','--ldflags','--libs','support','--system-libs'],text=True).split()
    exe=options.root/f'.tmp/llvm{major}/ppc-oracle'
    subprocess.run([llvm+'clang++',str(R/'tests/ppc_oracle.cpp'),*flags,'-o',str(exe)],check=True)
    rng=random.Random(0xDD128)
    # Canonical pairs, subnormals, sparse tails, ties, cancellation, overflow.
    hi=[0,1,0x8000000000000000,0x0010000000000000,0x0360000000000000,0x3ff0000000000000,0xbff0000000000000,0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001]
    vals=list(hi)
    for h in hi[3:8]:
        for l in [1,0x8000000000000001,0x3c90000000000000,0xbc90000000000000]:
            # Only normalized nonoverlapping high/low pairs are valid inputs.
            hv=e.decode(h,e.FORMATS['f64'])[0];lv=e.decode(l,e.FORMATS['f64'])[0]
            if e.encode(hv+lv,e.FORMATS['f64'])[0]==h: vals.append(h|(l<<64))
    for _ in range(120):
        h=rng.getrandbits(64)
        if (h>>52)&2047 in (0,2047):continue
        he=((h>>52)&2047)-1023
        le=max(-1074,he-54-rng.randrange(0,140))
        l=e.encode(e.power(le)*rng.choice([-1,1]),e.FORMATS['f64'])[0]
        vals.append(h|(l<<64))
    jobs=[]
    for i,a in enumerate(vals):
        for b in vals[:len(hi)]+[vals[(i+17)%len(vals)],vals[(i+37)%len(vals)]]:
            for op in range(6):
                for rm in range(5):
                    if op==4 and rm:continue # APFloat mod has no rounding operand
                    jobs.append((op,rm,a,b,vals[(i+5)%len(vals)]))
        for rm in range(5):jobs += [(6,rm,a,0,0),(7,rm,a,0,0)]
    for i,a in enumerate(vals):
        for b in vals:jobs.append((9,0,a,b,0))
    for a in vals:jobs.append((14,0,a,0,0))
    for _ in range(250):
        a=rng.getrandbits(128)
        for rm in range(5):jobs.append((8,rm,a,0,0))
    # All 65,536 half encodings exercise exact small/NaN PPC conversion routes.
    for a in range(65536):
        v,s,_=e.decode(a,e.FORMATS['f16']);q=e.encode(v,e.FORMATS['f128'],zero_sign=s)[0]
        jobs.append((8,0,q,0,0))
    for _ in range(100):
        a=rng.getrandbits(128)
        for rm in range(5):jobs += [(10,rm,a,0,0),(11,rm,a,0,0)]
    for a in vals:jobs += [(12,0,a,0,0),(13,0,a,0,0)]
    payload=''.join(f'{op} {rm} {a&((1<<64)-1):x} {a>>64:x} {b&((1<<64)-1):x} {b>>64:x} {c&((1<<64)-1):x} {c>>64:x}\n' for op,rm,a,b,c in jobs)
    proc=subprocess.run([str(exe)],input=payload,text=True,capture_output=True,check=True)
    answers=proc.stdout.splitlines();assert len(answers)==len(jobs)
    ops=['add','sub','mul','div','rem','fma','rint','fpext_ppcf128_f128','fptrunc_f128_ppcf128',None,'sitofp','uitofp','fptosi','fptoui']
    overrides=0
    for (op,rm,a,b,c),line in zip(jobs,answers):
        lo,hi=map(lambda s:int(s,16),line.split());expected=lo|(hi<<64)
        apfloat=expected;flags=None
        # 0.2.12 explicitly overrides APFloat for these operations. Keep every
        # existing input and use an independent mathematical oracle instead.
        if op==5:expected,flags=o.fma(a,b,c,rm)
        elif op==6:expected,flags=o.integral(a,'rint',rm)
        elif op==7:expected,flags=o.convert(a,e.FORMATS['f128'],rm)
        elif op==8:expected,flags=o.incoming(a,e.FORMATS['f128'],rm)
        elif op in (10,11):
            n=a-(1<<128) if op==10 and a>>127 else a
            expected,flags=o.integer_to_pair(n,rm)
        elif op in (12,13):
            expected,_=o.to_integer(a,128,op==12,3)
            expected&=e.MASK128
            flags=0 # These existing jobs exercise the plain, fenv-free ABI.
        overrides+=int(expected!=apfloat)
        if op==14:
            for cls in range(10):edge.check('isfpclass_ppcf128',[a,1<<cls],int(bool(lo&(1<<cls))))
            continue
        if op==9:
            for pred in range(16):
                p=pred&7;u=lo==3;d=-1 if lo==0 else 0 if lo==1 else 1
                value=[False,d==0,d>0,d>=0,d<0,d<=0,d!=0,True][p]
                want=int(pred>=8 if u else pred==15 or value)
                edge.check('cmp_ppcf128',[a,b,pred],want)
                edge.check('cmp_ppcf128_rm',[a,b,pred,pred%5],want)
            continue
        name=ops[op]+('_ppcf128' if op<7 or op>=10 else '')
        args=[a,b,c] if op==5 else [a,b] if op<5 else [a]
        if op in (12,13):args+=[128]
        elif op!=4:name+='_rm';args+=[rm]
        edge.check(name,args,expected,flags)
    print(f'LLVM {major}: {edge.count} PPC component/exact-value checks; {overrides} explicit-guarantee differences from APFloat',flush=True)
    exact.run(major,options.root)
    closure.run(major,options.root)
