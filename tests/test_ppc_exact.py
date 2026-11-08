"""Exact-sum PPC conversions, integral operations and canonical-pair sqrt.

Independent Fraction expectations; actual calls use the published bitcode.
FMA's zero-low midpoint ambiguity remains separately tracked by 4yg.1.
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
    odd_integer=(1<<52)+1
    assert o.integer_to_pair(odd_integer)==(e.encode(e.Q(odd_integer),F)[0],0)
    witness=o.pair(e.Q(1),e.power(-60))
    edge.check('fpext_ppcf128_f80_rm',[witness,0],*o.convert(witness,e.FORMATS['f80']))
    values=[o.pair(e.Q(h),e.power(ex)*sign) for h in (1,-1) for ex in (-60,-200,-1074) for sign in (1,-1)]
    values += [o.pair(e.power(100),e.Q(-1)),o.pair(e.power(1023),e.Q(1)),
               o.pair(e.Q(1,2),e.power(-1074)),o.pair(e.Q(-1,2),-e.power(-1074)),
               o.pair(e.Q(0)),o.pair(e.Q(0),zero_sign=1),1,(1<<63)|1,
               e.infinity(F),e.infinity(F,1),e.nan(F),e.infinity(F)|1]
    values += [o.pair(e.Q(1)),o.pair(e.power(1022)),o.pair(e.power(-1022))]
    # Roots lie just below/above 2^511 + 2^-1075. Squared-midpoint comparison
    # must retain the unit at bit zero of a 3173-bit integer.
    near=e.encode(e.power(-563),F)[0]
    values += [o.pair(e.power(1022),e.decode(near,F)[0]),
               o.pair(e.power(1022),e.decode(near+1,F)[0])]
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
    for raw in values:
        v,sign,sn=o.decode(raw);nearest=None
        for rm in range(5):
            edge.env[1]=32
            actual=edge.call('sqrt_ppcf128_rm',raw,rm)[0]
            if v=='nan' or v=='inf' or not v or v<0:
                want=e.nan(F) if v=='nan' or sign and (v=='inf' or v) else e.infinity(F) if v=='inf' else sign<<63
                flags=int(sn or sign and (v=='inf' or not isinstance(v,str) and v<0))
                assert actual==want,(major,'sqrt special',raw,rm,actual,want)
            else:
                y,_,_=o.decode(actual)
                assert not isinstance(y,str) and y>0
                assert e.encode(y,F)[0]==actual&o.MASK64 and actual>>64!=1<<63
                (prev,_),(nxt,_)=o.neighbours(actual)
                if rm in (1,3):assert y*y<=v<nxt*nxt,(major,'sqrt down',raw,rm)
                elif rm==2:assert prev*prev<v<=y*y,(major,'sqrt up',raw,rm)
                else:
                    left=((prev+y)/2)**2;right=((y+nxt)/2)**2
                    assert left<=v<=right,(major,'sqrt nearest',raw,rm)
                    if rm==4:assert v!=right
                    elif v in (left,right):assert not (((actual>>64) or (actual&o.MASK64))&1)
                flags=int(y*y!=v)*16
                if flags and y<e.power(-1022):flags|=8
            assert edge.env[1]==32|flags,(major,'sqrt flags',raw,rm,edge.env[1],flags)
            if rm==0:nearest=actual
            edge.count+=1
        edge.check('sqrt_ppcf128',[raw],nearest,0)
    for bits in (1,8,64,128,129,193,257,513,1025):
        numbers=[0,1,(1<<(bits-1))-1,1<<(bits-1),(1<<bits)-1]
        if bits>110:
            numbers += [(1<<(bits-2))+1,(1<<(bits-2))-(1<<(bits-70))-1]
        if bits>=123:
            exponent=min(bits-2,1023)
            numbers += [(1<<exponent)-(1<<(exponent-68))-3*(1<<(exponent-121))]
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
    print(f'LLVM {major}: {edge.count} exact-sum conversion/integral/integer/sqrt checks',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('majors',type=int,nargs='*',default=[18,23])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    from pathlib import Path as ProfilePath
    import sys as profile_sys
    profile_sys.path.insert(0, str(ProfilePath(__file__).resolve().parents[1] / "scripts"))
    from machine_profile import majors as machine_majors
    for major in machine_majors(args.majors, script=__file__):run(major,args.root)
