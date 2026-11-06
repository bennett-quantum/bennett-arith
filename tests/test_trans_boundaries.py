"""Sweep exp/exp2/exp10 across every subnormal-output exponent and overflow."""
import importlib.util,pathlib,sys,decimal
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('trans',R/'tests/test_trans.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t);e=t.e
with decimal.localcontext() as ctx:
    ctx.prec=120
    ln2=e.Q(decimal.Decimal(2).ln());log10two=ln2/e.Q(decimal.Decimal(10).ln())
for major in map(int,sys.argv[1:] or [18,23]):
    edge=e.Edge(major);oracle=t.Oracle()
    for suffix,f in e.FORMATS.items():
        tiny=1-f[3]-(f[1]-1);emin=1-f[3]
        for n in list(range(tiny-3,emin+3))+[f[3]-1,f[3],f[3]+1]:
            for delta in [e.Q(-1,2),e.Q(0),e.Q(1,2)]:
                for op,scale in [('exp',ln2),('exp2',e.Q(1)),('exp10',log10two)]:
                    raw=e.encode((n+delta)*scale,f)[0];a,sa,_=e.decode(raw,f)
                    want,ws=oracle.call(op,a,sa)
                    for rm in range(5):
                        expected=oracle.rounded(op,a,sa,f=f,rm=rm)
                        got=edge.call(op+'_'+suffix+'_rm',raw,rm)[0]
                        assert got==expected,(suffix,op,n,rm,hex(got),hex(expected))
                        edge.count+=1
        # Exact powers, including exact tiny and rounded-underflow cases, flags.
        for n in [tiny-1,tiny,emin,0,1,f[3],f[3]+1]:
            raw=e.encode(e.Q(n),f)[0]
            for rm in range(5):
                expected,flags=e.encode(e.power(n),f,rm)
                edge.check('exp2_'+suffix+'_rm',[raw,rm],expected,flags)
    print(f'LLVM {major}: {edge.count} libm subnormal/overflow boundary checks',flush=True)
