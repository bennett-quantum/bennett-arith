"""0.2.12 quiet/signaling comparison ABI and flags in published bitcode.

Expected truth values use independent Fraction decoding, never host FP.
"""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('edge',ROOT/'tests/test_edge.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

def decoded(bits,suffix):
    if suffix!='ppcf128': return e.decode(bits,e.FORMATS[suffix])
    high,sign,snan=e.decode(bits&((1<<64)-1),e.FORMATS['f64'])
    if isinstance(high,str): return high,sign,snan
    low,_,_=e.decode(bits>>64,e.FORMATS['f64'])
    return high+low,sign,False

def expected(a,b,suffix,pred):
    av,sa,_=decoded(a,suffix);bv,sb,_=decoded(b,suffix)
    if av=='nan' or bv=='nan': return int(pred>=8)
    av=(-1 if sa else 1)*e.power(50000) if av=='inf' else av
    bv=(-1 if sb else 1)*e.power(50000) if bv=='inf' else bv
    d=(av>bv)-(av<bv)
    return int((False,d==0,d>0,d>=0,d<0,d<=0,d!=0,True)[pred&7])

for major in map(int,sys.argv[1:] or (18,23)):
    edge=e.Edge(major)
    suffixes=[*e.FORMATS,'ppcf128']
    missing={f'__bennett_sf_cmps_{s}_rm' for s in suffixes}-set(edge.rows)
    assert not missing, f'RED: missing signaling comparison definitions: {sorted(missing)}'
    edge.env[0]=4 # comparison R is always zero, independent of the fenv mode
    for suffix in suffixes:
        f=e.FORMATS['f64'] if suffix=='ppcf128' else e.FORMATS[suffix]
        bits,p,eb,bias,explicit=f
        c=f'i{128 if suffix=="ppcf128" else bits}'
        row=edge.rows[f'__bennett_sf_cmps_{suffix}_rm']
        assert row['signature']==f'i1 ({c}, {c}, i32, i32)'
        assert row['section']=='13.5' and row['status']=='exact'
        sign=1<<(bits-1);one=e.encode(e.Q(1),f)[0]
        inf=e.infinity(f);qnan=e.nan(f);snan=inf|1
        maximum=e.encode((2-e.power(1-p))*e.power(bias),f)[0]
        values=[0,sign,1,sign|1,one,one|sign,one-1,one+1,
                maximum,maximum|sign,inf,inf|sign,qnan,qnan|sign,qnan|37,snan,snan|sign]
        if explicit: values += [1<<63,(1<<64)|1,((1<<15)-1)<<64]
        if suffix=='ppcf128':
            low=e.encode(e.power(-60),f)[0]|0x12345
            values += [one|(low<<64),one|((low|sign)<<64)]
        for a in values:
            av,_,asn=decoded(a,suffix)
            for b in values:
                bv,_,bsn=decoded(b,suffix)
                quiet=int(asn or bsn);signaling=int(av=='nan' or bv=='nan')
                for pred in range(16):
                    want=expected(a,b,suffix,pred)
                    edge.check('cmp_'+suffix,[a,b,pred],want,0)
                    edge.check('cmp_'+suffix+'_rm',[a,b,pred,0],want,quiet)
                    edge.check('cmps_'+suffix+'_rm',[a,b,pred,0],want,signaling)
        # Exhaust every half/bfloat NaN payload, in either operand, including
        # false/true, which still have to record signaling exceptions.
        if suffix in ('f16','bf16'):
            for a in range(65536):
                value,_,sn=decoded(a,suffix)
                if value!='nan': continue
                for x,y in ((a,one),(one,a)):
                    for pred in (0,15):
                        want=int(pred==15)
                        edge.check('cmp_'+suffix,[x,y,pred],want,0)
                        edge.check('cmp_'+suffix+'_rm',[x,y,pred,0],want,int(sn))
                        edge.check('cmps_'+suffix+'_rm',[x,y,pred,0],want,1)
        # All combinations of existing IEEE flags must survive. No other flag
        # may be introduced, and qNaNs differ from sNaNs only for quiet cmp.
        for old in range(32):
            for a in (one,qnan,snan):
                _,_,sn=decoded(a,suffix)
                for op,flags in (('cmp',0),('cmp_rm',int(sn)),('cmps_rm',int(a in (qnan,snan)))):
                    name=('cmp_'+suffix if op=='cmp' else ('cmp_' if op=='cmp_rm' else 'cmps_')+suffix+'_rm')
                    edge.env[1]=old
                    edge.call(name,a,one,0,*([] if op=='cmp' else [0]))
                    assert edge.env[1]==old|flags,(major,name,old,a,list(edge.env))
                    edge.count+=1
        # A vector producer scalarises lanes. Verify truth and accumulated
        # flags for a mixed lane sequence with an existing divide-by-zero flag.
        lanes=[(one,one),(qnan,one),(one,snan),(sign,0)]
        edge.env[1]=2
        got=[edge.call('cmps_'+suffix+'_rm',a,b,1,0)[0] for a,b in lanes]
        assert got==[expected(a,b,suffix,1) for a,b in lanes]
        assert edge.env[1]==3 and edge.env[0]==4
        edge.count+=len(lanes)
    print(f'LLVM {major}: {edge.count} quiet/signaling truth, NaN-payload, sticky-flag and lane checks',flush=True)
