"""Outgoing PPC conversions and integral operations use the exact high+low.

Independent Fraction expectations; actual calls use the published bitcode.
Sqrt/FMA/canonical pair midpoint selection remain separately tracked by 4yg.
"""
import importlib.util
import argparse
from pathlib import Path
import random
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('pxoracle',ROOT/'tests/ppc_exact_oracle.py')
o=importlib.util.module_from_spec(s);s.loader.exec_module(o)
e=o.e;F=o.F

def run(major,root=ROOT):
    edge=e.Edge(major,root)
    witness=o.pair(e.Q(1),e.power(-60))
    edge.check('fpext_ppcf128_f80_rm',[witness,0],*o.convert(witness,e.FORMATS['f80']))
    values=[o.pair(e.Q(h),e.power(ex)*sign) for h in (1,-1) for ex in (-60,-200,-1074) for sign in (1,-1)]
    values += [o.pair(e.power(100),e.Q(-1)),o.pair(e.power(1023),e.Q(1)),
               o.pair(e.Q(1,2),e.power(-1074)),o.pair(e.Q(-1,2),-e.power(-1074)),
               o.pair(e.Q(0)),o.pair(e.Q(0),zero_sign=1),1,(1<<63)|1,
               e.infinity(F),e.infinity(F,1),e.nan(F),e.infinity(F)|1]
    maximum=e.decode(0x7fefffffffffffff,F)[0]
    values += [o.pair(maximum,e.power(970)-e.power(917))]
    rng=random.Random(0x02124)
    for _ in range(70):
        exponent=rng.randrange(-1020,1023)
        h=e.encode(e.power(exponent)*e.Q(rng.randrange(1<<52,1<<53),1<<52),F)[0]
        if rng.randrange(2):h|=1<<63
        low=e.encode(e.power(max(-1074,exponent-rng.randrange(54,1100)))*rng.choice((-1,1)),F)[0]
        raw=h|(low<<64)
        assert e.encode(o.decode(raw)[0],F)[0]==h
        values.append(raw)
    for raw in values:
        for dest,f in e.FORMATS.items():
            for op in ('fpext','fptrunc'):
                want,_=o.convert(raw,f)
                edge.check(f'{op}_ppcf128_{dest}',[raw],want,0)
                for rm in range(5):
                    want,flags=o.convert(raw,f,rm)
                    edge.check(f'{op}_ppcf128_{dest}_rm',[raw,rm],want,flags)
        for op in ('floor','ceil','trunc','round','roundeven','rint','nearbyint'):
            want,_=o.integral(raw,op)
            edge.check(op+'_ppcf128',[raw],want,0)
            for rm in range(5):
                want,flags=o.integral(raw,op,rm)
                edge.check(op+'_ppcf128_rm',[raw,rm],want,flags)
        for op in ('fptosi','fptoui','lround','llround','lrint','llrint'):
            signed=op!='fptoui'
            for bits in (1,8,64,128):
                for rm in range(5):
                    mode=3 if op in ('fptosi','fptoui') else 4 if op in ('lround','llround') else rm
                    want,flags=o.to_integer(raw,bits,signed,mode,op not in ('lround','llround'))
                    edge.check(op+'_ppcf128_rm',[raw,bits,rm],want&e.MASK128,flags)
    for bits in (129,193,257,513,1025):
        high=e.power(min(bits-2,1023))
        for low in (-e.Q(1),e.Q(1),e.power(-200),-e.power(-200)):
            raw=o.pair(high,low)
            for op in ('fptosi','fptoui','lround','llround','lrint','llrint'):
                for rm in range(5):
                    mode=3 if op in ('fptosi','fptoui') else 4 if op in ('lround','llround') else rm
                    want,flags=o.to_integer(raw,bits,op!='fptoui',mode,op not in ('lround','llround'))
                    slot=e.Aligned(8*((bits+63)//64));slot.put(bytes([0xa5])*slot.size)
                    edge.env[1]=32
                    edge.call(op+'_ppcf128_wide_rm',slot.addr,raw,bits,rm)
                    assert int.from_bytes(slot.read(),'little')==want%(1<<bits),(major,op,bits,rm)
                    assert edge.env[1]==32|flags,(major,op,bits,rm,'flags',edge.env[1],flags)
                    edge.count+=1
    for bits in (1,8,64,128,129,193,257,513,1025):
        numbers=[0,1,(1<<(bits-1))-1,1<<(bits-1),(1<<bits)-1]
        if bits>110:
            numbers += [(1<<(bits-2))+1,(1<<(bits-2))-(1<<(bits-70))-1]
        if bits==1025:
            maximum=o.decode(0x7fefffffffffffff|(0x7c8fffffffffffff<<64))[0]
            numbers += [int(maximum),int(maximum)+1,int(maximum)+int(e.power(916))]
        for unsigned in numbers:
            slot=e.Aligned(8*((bits+63)//64));slot.put(unsigned.to_bytes(slot.size,'little'))
            for signed,op in ((False,'uitofp'),(True,'sitofp')):
                n=unsigned-(1<<bits) if signed and unsigned>>(bits-1) else unsigned
                for rm in range(5):
                    want,flags=o.integer_to_pair(n,rm)
                    edge.check(op+'_ppcf128_wide_rm',[slot.addr,bits,rm],want,flags)
                    if bits<=128:
                        carrier=n&e.MASK128 if signed else unsigned
                        edge.check(op+'_ppcf128_rm',[carrier,rm],want,flags)
    print(f'LLVM {major}: {edge.count} exact-sum conversion/integral/narrow/wide checks',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('majors',type=int,nargs='*',default=[18,23])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    for major in args.majors:run(major,args.root)
