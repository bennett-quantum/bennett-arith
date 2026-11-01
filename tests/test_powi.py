"""Width-preserving repeated-squaring public ABI, including exponents >128 bits."""
import importlib.util,pathlib,sys
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('edge',R/'tests/test_edge.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
for major in map(int,sys.argv[1:] or [18,23]):
    edge=e.Edge(major)
    assert '__bennett_sf_powi_f128_i64' in edge.rows,'RED: missing non-i32 powi'
    for suffix,f in list(e.FORMATS.items())+[('ppcf128',e.FORMATS['f64'])]:
        one=e.encode(e.Q(1),f)[0];two=e.encode(e.Q(2),f)[0]
        def reference(base,n,rm):
            result=one;positive=abs(n)
            while positive:
                if positive&1:result=edge.call('mul_'+suffix+'_rm',result,base,rm)[0]
                positive>>=1
                if positive:base=edge.call('mul_'+suffix+'_rm',base,base,rm)[0]
            return edge.call('div_'+suffix+'_rm',one,result,rm)[0] if n<0 else result
        for width in [1,8,16,32,64,128,192,256,513,1025]:
            for n in [0,1,-1,-(1<<(width-1)),(1<<(width-1))-1]:
                raw=n% (1<<width)
                n=raw-(1<<width) if raw>>(width-1) else raw
                slot=e.Aligned((width+7)//8);slot.put(raw.to_bytes(slot.size,'little'))
                arg=slot.addr if width>128 else raw
                for rm in range(5):
                    edge.check(f'powi_{suffix}_i{width}_rm',[one,arg,rm],reference(one,n,rm))
                edge.check(f'powi_{suffix}_i{width}',[one,arg],reference(one,n,0))
            if width>128:
                for n,want in [(1<<(width-2),e.infinity(f)),(-(1<<(width-2)),0)]:
                    raw=n%(1<<width);slot=e.Aligned((width+7)//8);slot.put(raw.to_bytes(slot.size,'little'))
                    edge.check(f'powi_{suffix}_i{width}',[two,slot.addr],want)
            if width>1:
                for n in [2,-2,3,-3]:
                    if n>=1<<(width-1) or n< -(1<<(width-1)):continue
                    raw=n% (1<<width);slot=e.Aligned((width+7)//8);slot.put(raw.to_bytes(slot.size,'little'))
                    arg=slot.addr if width>128 else raw
                    want=e.encode(e.power(n),f)[0]
                    for rm in range(5):edge.check(f'powi_{suffix}_i{width}_rm',[two,arg,rm],reference(two,n,rm))
                    edge.check(f'powi_{suffix}_i{width}',[two,arg],reference(two,n,0))
    print(f'LLVM {major}: {edge.count} width-preserving powi checks',flush=True)
