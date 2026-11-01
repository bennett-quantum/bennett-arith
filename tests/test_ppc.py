"""Published PPC carrier operations vs the contract's LLVM-major APFloat oracle."""
import importlib.util, pathlib, subprocess, sys, random
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',R/'tests/test_edge.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
for major in map(int,sys.argv[1:] or [18,23]):
    edge=e.Edge(major)
    assert '__bennett_sf_add_ppcf128' in edge.rows, 'RED: missing PPCDoubleDouble publication'
    llvm=f'/usr/lib/llvm-{major}/bin/'
    flags=subprocess.check_output([llvm+'llvm-config','--cxxflags','--ldflags','--libs','support','--system-libs'],text=True).split()
    exe=R/f'.tmp/llvm{major}/ppc-oracle'
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
    # All 65,536 half encodings exercise exact small/NaN PPC conversion routes.
    for a in range(65536):
        v,s,_=e.decode(a,e.FORMATS['f16']);q=e.encode(v,e.FORMATS['f128'],zero_sign=s)[0]
        jobs.append((8,0,q,0,0))
    payload=''.join(f'{op} {rm} {a&((1<<64)-1):x} {a>>64:x} {b&((1<<64)-1):x} {b>>64:x} {c&((1<<64)-1):x} {c>>64:x}\n' for op,rm,a,b,c in jobs)
    proc=subprocess.run([str(exe)],input=payload,text=True,capture_output=True,check=True)
    answers=proc.stdout.splitlines();assert len(answers)==len(jobs)
    ops=['add','sub','mul','div','rem','fma','rint','fpext_ppcf128_f128','fptrunc_f128_ppcf128']
    for (op,rm,a,b,c),line in zip(jobs,answers):
        lo,hi=map(lambda s:int(s,16),line.split());expected=lo|(hi<<64)
        name=ops[op]+('_ppcf128' if op<7 else '')
        args=[a,b,c] if op==5 else [a,b] if op<5 else [a]
        if op!=4:name+='_rm';args+=[rm]
        edge.check(name,args,expected)
    print(f'LLVM {major}: {edge.count} PPCDoubleDouble/APFloat checks')
