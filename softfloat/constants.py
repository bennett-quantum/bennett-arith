"""Generate integer constants, without host floating point (Chudnovsky pi)."""
import decimal,pathlib,sys
D=decimal.Decimal
def constants(dest):
    with decimal.localcontext() as ctx:
        ctx.prec=5400
        m=1;l=13591409;x=1;s=D(l);k=6
        for i in range(1,390):
            m=m*(k*k*k-16*k)//(i*i*i);l+=545140134;x*= -262537412640768000
            s+=D(m*l)/D(x);k+=12
        pi=426880*D(10005).sqrt()/s
        out=['/* Generated from integer Chudnovsky and Decimal, 5400 digits. */']
        for name,v in [('pi',pi),('ln2',D(2).ln()),('ln10',D(10).ln())]:
            n=int(v*D(2)**220)
            limbs=[(n>>(64*i))&((1<<64)-1) for i in range(4)]
            expr=' | '.join(f'((Big)0x{v:016x}ULL << {64*i})' for i,v in enumerate(limbs))
            out.append(f'static V tc_{name}(void) {{ return (V){{{expr},-220,0,FINITE,0}}; }}')
        n=int((D(2)/pi)*D(2)**17408)
        out+=['static const unsigned long long two_over_pi[272] = {']
        out += [f'0x{(n>>(64*i))&((1<<64)-1):016x}ULL,' for i in range(272)]
        out+=['};']
        pathlib.Path(dest,'constants.h').write_text('\n'.join(out)+'\n')
if __name__=='__main__':constants(sys.argv[1])
