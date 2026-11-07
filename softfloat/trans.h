/* Versioned integer libm v1. 240 significant working bits; no host FP.
 * Payne-Hanek reduction uses 17408 bits of 2/pi over the full binary128 range.
 * Results are deterministic approximations, NOT claimed correctly rounded.
 */
#include "constants.h"
/* Two 113-bit input significands plus guard bits for near-one powers;
 * twice this precision still fits the 512-bit product accumulator. */
enum { TRANS_BITS = 240, PPC_TINY_SUM_BIT = 716, PPC_TINY_EXP = -1076 };
static V tn(V a) {
    if(a.kind==FINITE && width(a.mag)>TRANS_BITS) {int s=width(a.mag)-TRANS_BITS;a.mag=jam(a.mag,s);a.exp+=s;}
    return a;
}
static V ti(int n) { return (V){n<0 ? (Big)(0u-(unsigned)n):(Big)n,0,n<0,FINITE,0}; }
static int tinyterm(V term,V sum) {return !term.mag || (sum.mag && width(term.mag)+term.exp < width(sum.mag)+sum.exp-240);}
static V tneg(V a) {a.sign^=1;return a;}
static V ta(V a,V b) {return tn(add(a,b,0));}
static V tm(V a,V b) {return tn(mul(tn(a),tn(b)));}
static V td(V a,V b) {
    a=tn(a);b=tn(b);int sign=a.sign^b.sign;
    if(a.kind==NANV || b.kind==NANV || (a.kind==INF && b.kind==INF) || (!a.mag && a.kind==FINITE && !b.mag && b.kind==FINITE))return nanv();
    if(a.kind==INF || (b.kind==FINITE && !b.mag))return (V){0,0,sign,INF,0};
    if(b.kind==INF || !a.mag)return (V){0,0,sign,FINITE,0};
    int shift=256+width(b.mag)-width(a.mag);Big rem;
    Big q=quotient(a.mag<<shift,b.mag,&rem);
    return tn((V){q|(rem!=0),a.exp-b.exp-shift,sign,FINITE,0});
}
static V tsqrt(V a) {
    if(a.kind==NANV || (a.sign && (a.mag || a.kind==INF)))return nanv();
    if(a.kind==INF || !a.mag)return a;
    int shift=480-width(a.mag);if((a.exp-shift)%2)--shift;
    Big n=a.mag<<shift,root=0,rem=0;
    for(int i=239;i>=0;--i) {rem=(rem<<2)|((n>>(2*i))&3);Big trial=(root<<2)|1;root<<=1;if(rem>=trial){rem-=trial;++root;}}
    return tn((V){root|(rem!=0),(a.exp-shift)/2,0,FINITE,0});
}
static V tred(V a,int *quadrant) {
    if(width(a.mag)+a.exp<=-1) {*quadrant=0;return a;}
    a=tn(a);int start=17408-a.exp-320-192;
    typedef unsigned _BitInt(1024) Product;
    Product window=0;
    for(int i=0;i<9;++i) {
        int pos=start+64*i,index=pos/64,offset=pos%64;
        unsigned long long limb=index>=0 && index<272 ? two_over_pi[index]>>offset:0;
        if(offset && index+1>=0 && index+1<272)limb|=two_over_pi[index+1]<<(64-offset);
        window|=(Product)limb<<(64*i);
    }
    Big y=(Big)(((Product)window*(Product)a.mag)>>192)&mask(322);
    int q=(int)(y>>320);Big fraction=y&mask(320);
    V r={fraction,-320,0,FINITE,0};
    if(fraction>=((Big)1<<319)) {r.mag=((Big)1<<320)-fraction;r.sign=1;++q;}
    V p=tc_pi();--p.exp;r=tm(tn(r),p);
    if(a.sign){r.sign^=1;q=-q;}
    *quadrant=q&3;return r;
}
static void tsc(V a,int piarg,V *s,V *c) {
    if(a.kind!=FINITE) {*s=*c=nanv();return;}
    if(!a.mag) {*s=a;*c=ti(1);return;}
    int q;V x;
    if(piarg) {
        /* Reduce 2*x exactly before multiplying by pi/2 (integer arguments). */
        V twice=a;++twice.exp;int ignored=0;
        V whole=integral(twice,0,&ignored),frac=ta(twice,tneg(whole));
        Big n=whole.exp>=0 ? (whole.exp<2 ? whole.mag<<whole.exp:0):whole.mag>>-whole.exp;
        q=(int)(n&3);if(whole.sign)q=(-q)&3;
        V p=tc_pi();--p.exp;x=tm(frac,p);
    } else x=tred(a,&q);
    V xx=tneg(tm(x,x)),st=x,ct=ti(1),ss=st,cc=ct;
    for(int n=1;n<=90;++n) {
        st=td(tm(st,xx),ti((2*n)*(2*n+1)));ss=ta(ss,st);
        ct=td(tm(ct,xx),ti((2*n-1)*(2*n)));cc=ta(cc,ct);
        if(tinyterm(st,ss) && tinyterm(ct,cc))break;
    }
    if(!x.mag) {ss=x;cc=ti(1);}
    if(q==0){*s=ss;*c=cc;}else if(q==1){*s=cc;*c=tneg(ss);}else if(q==2){*s=tneg(ss);*c=tneg(cc);}else{*s=tneg(cc);*c=ss;}
    if(piarg && !s->mag)s->sign=a.sign;
    if(piarg && !c->mag)c->sign=0;
}
static V tlog(V a) {
    if(a.kind==NANV || (a.sign && a.mag))return nanv();
    if(a.kind==INF)return a.sign ? nanv():a;
    if(!a.mag)return (V){0,0,1,INF,0};
    int e=width(a.mag)+a.exp-1;a.exp-=e;
    /* Keep the significand around 1, avoiding log(2-eps)-ln2 cancellation. */
    if(compare(a,(V){3,-1,0,FINITE,0})>0){--a.exp;++e;}
    V z=td(ta(a,ti(-1)),ta(a,ti(1))),zz=tm(z,z),term=z,sum=z;
    for(int n=3;n<501;n+=2){term=tm(term,zz);sum=ta(sum,td(term,ti(n)));if(tinyterm(term,sum))break;}
    ++sum.exp;return ta(sum,tm(ti(e),tc_ln2()));
}
static V texp(V a) {
    if(a.kind==NANV)return nanv();
    if(a.kind==INF)return a.sign ? ti(0):a;
    /* Preserve strict positivity below every carrier's half-minimum quantum;
     * final packing must still select the upward neighbour and raise flags. */
    if(a.mag && width(a.mag)+a.exp>16)return (V){1,a.sign ? -100000:100000,0,FINITE,0};
    V v=td(a,tc_ln2());int ignored=0;V rounded=integral(v,0,&ignored);
    int n=(int)toint(rounded,32,1,3,&ignored);
    V r=ta(a,tneg(tm(ti(n),tc_ln2()))),term=ti(1),sum=term;
    for(int k=1;k<=150;++k){term=td(tm(term,r),ti(k));sum=ta(sum,term);if(tinyterm(term,sum))break;}
    sum.exp+=n;return sum;
}
static V tatan(V a) {
    if(a.kind==NANV)return nanv();
    int sign=a.sign;a.sign=0;
    V halfpi=tc_pi();--halfpi.exp;
    if(a.kind==INF){halfpi.sign=sign;return halfpi;}
    int inv=compare(a,ti(1))>0;if(inv)a=td(ti(1),a);
    int offset=compare(a,(V){1,-1,0,FINITE,0})>0;
    if(offset)a=td(ta(a,ti(-1)),ta(a,ti(1)));
    V term=a,sum=a,xx=tneg(tm(a,a));
    for(int k=3;k<601;k+=2){term=tm(term,xx);sum=ta(sum,td(term,ti(k)));if(tinyterm(term,sum))break;}
    if(offset){V p=tc_pi();p.exp-=2;sum=ta(sum,p);}
    if(inv)sum=ta(halfpi,tneg(sum));sum.sign^=sign;return sum;
}
static V tatan2(V y,V x) {
    if(x.kind==NANV || y.kind==NANV)return nanv();
    V p=tc_pi();
    if(!y.mag && y.kind==FINITE){if(x.sign){p.sign=y.sign;return p;}return y;}
    if(!x.mag && x.kind==FINITE){--p.exp;p.sign=y.sign;return p;}
    if(x.kind==INF && y.kind==INF){p.exp-=2;if(x.sign)p=tm(p,ti(3));p.sign=y.sign;return p;}
    V r=tatan(td(y,x));
    if(x.sign){p.sign=y.sign;r=ta(r,p);}return r;
}
static V tpow(V a,V b) {
    if(b.kind==FINITE && !b.mag)return ti(1);
    if(compare(a,ti(1))==0 && a.kind==FINITE)return ti(1);
    if(a.kind==NANV || b.kind==NANV)return nanv();
    int ignored=0;V bi=integral(b,3,&ignored);
    int integer=b.kind==FINITE && compare(b,bi)==0;
    int odd=integer && bi.mag && bi.exp<=0 && (bi.mag>>-bi.exp&1);
    if(b.kind==INF){V aa=a;aa.sign=0;int d=compare(aa,ti(1));if(!d)return ti(1);return (d>0)^b.sign ? (V){0,0,0,INF,0}:ti(0);}
    if(a.kind==INF || !a.mag){int inf=(a.kind==INF)^b.sign;return (V){0,0,a.sign&&odd,inf ? INF:FINITE,0};}
    if(a.sign && !integer)return nanv();
    int sign=a.sign&&odd;a.sign=0;V r=texp(tm(b,tlog(a)));r.sign=sign;return r;
}
/* Canonicalise the exact two-component input sum x=h+l first, so overlapping
 * or cancelling input fields have the same result. With |x|<=2^-112, exp(x)
 * has high=1.
 * Nearest rounding of its low differs from rounding x only at exact binary64
 * midpoints: the positive correction exp(x)-1-x < x*x is smaller than the
 * smallest nonzero midpoint gap of a two-binary64 input (>=2^(E-107)).
 * Directed rounding also needs to know whether exp(x)-1 crosses h. Compare
 * x with log(1+h), whose residual is -h*h/2 + h*h*h/3 - ... . A nonzero
 * quadratic comparison gap is at least 2^(2*h.exp-1), or much larger when l
 * is tiny; the cubic remainder is smaller by >=32. At exact quadratic
 * equality its sign is the sign of h, settling the side without approximation.
 * All comparisons below are exact integers at quantum 2^-2149. A nonzero
 * rational input has non-dyadic exp(x), so the normal result raises only
 * inexact. This retains sparse tails that the 224/106-bit paths lose.
 */
static U ppc_exp_near_zero(PairSum a,int rm,int *flags) {
    const U one=0x3ff0000000000000ULL;
    if(!a.mag)return one;
    int ignored=0;V v=sum_value(a);
    U hb=pack(v,formats[3],0,&ignored),lo;V h=unpack(hb,formats[3]);
    PairSum tail=sum_difference(a,sum_scalar(h));
    if(rm==1 || rm==2 || rm==3) {
        int above=1;
        if(tail.sign && tail.mag) {
            SquareBits low=(SquareBits)tail.mag<<1075;
            SquareBits high=(SquareBits)sum_scalar(h).mag,quadratic=high*high;
            above=low<quadratic || (low==quadratic && h.sign);
        }
        U previous=(hb>>63) ? hb+1:hb-1,following=(hb>>63) ? hb-1:hb+1;
        lo=rm==2 ? (above ? following:hb):(above ? hb:previous);
    } else {
        U lower=pack(v,formats[3],1,&ignored),upper=pack(v,formats[3],2,&ignored);
        PairSum down=sum_difference(a,sum_scalar(unpack(lower,formats[3])));
        PairSum up=sum_difference(sum_scalar(unpack(upper,formats[3])),a);
        lo=down.mag<up.mag ? lower:upper; /* An exact midpoint moves upward. */
    }
    if(lo==((U)1<<63))lo=0; /* Canonical residual zero is positive. */
    *flags|=16;
    return one|(lo<<64);
}
static V trans_unpack(U x,int fi) {
    if(fi!=6)return unpack(x,formats[fi]);
    V hi=unpack(low64(x),formats[3]);
    if(hi.kind!=FINITE || !hi.mag)return hi;
    return ta(hi,unpack(x>>64,formats[3]));
}
#include "trans_exact.h"
enum TransPath { TRANS_CORE, TRANS_EXACT, TRANS_PPC_EXP, TRANS_TANH_LIMIT, TRANS_LINEAR };
typedef struct {
    enum TransPath path;
    V a, b, r, c;
    ExactReal exact[2];
    PairSum sum;
    int flags, pair;
} TransState;

/* For 0<|x|<=2^-358 all these cubic corrections have magnitude <2^-1075.
 * Their strict signs settle directed rounding even below the low quantum.
 * Dialect 13.4 requires neighbours in the exact canonical-pair ordering. */
static const int trans_odd_correction[SINCOSPI+1]={
    [SIN]=-1, [SINH]=1, [TAN]=1, [ATAN]=-1, [ASIN]=1, [TANH]=-1
};
static const unsigned char trans_exact_math_ops[SINCOSPI+1]={
    [POW]=1, [EXP2]=1, [EXP10]=1, [LOG2]=1, [LOG10]=1
};
static const unsigned char trans_binary_ops[SINCOSPI+1]={[ATAN2]=1, [POW]=1};
static TransState trans_domain(int fi,int op,const U *in) {
    TransState s={.path=TRANS_CORE,.pair=op==SINCOS || op==SINCOSPI};
    if(op==SINCOSPI) {
        ExactReal a=trans_input(in[0],fi);
        if(trans_exact_sincospi(a,&s.exact[0],&s.exact[1])) {
            s.path=TRANS_EXACT;
            return s;
        }
    }
    if(trans_exact_math_ops[op]) {
        ExactReal a=trans_input(in[0],fi),b=trans_input(in[1],fi);
        if(trans_exact_math(op,a,b,&s.exact[0])) {
            s.path=TRANS_EXACT;
            s.flags=a.snan || (op==POW && b.snan);
            return s;
        }
    }
    if(fi==6 && op==EXP) {
        s.sum=sum_read(in[0]);
        if(s.sum.kind==FINITE && s.sum.mag<=((SumBits)1<<962)) {
            s.path=TRANS_PPC_EXP;
            return s;
        }
    }
    s.a=trans_unpack(in[0],fi);
    s.b=trans_unpack(in[1],fi);
    s.r=nanv();s.c=ti(0);
    s.flags=s.a.snan || (trans_binary_ops[op] && s.b.snan);
    if(op==TANH && s.a.kind==FINITE && s.a.mag && width(s.a.mag)+s.a.exp>6) {
        s.path=TRANS_TANH_LIMIT;
        return s;
    }
    int correction=trans_odd_correction[op];
    if(fi==6) {
        s.sum=sum_read(in[0]);
        if(correction && s.sum.kind==FINITE && s.sum.mag &&
           s.sum.mag<=((SumBits)1<<PPC_TINY_SUM_BIT))s.path=TRANS_LINEAR;
    } else if(correction && s.a.kind==FINITE && s.a.mag &&
              width(s.a.mag)+s.a.exp<=-112) {
        int shift=480-width(s.a.mag);
        s.r=s.a;s.r.mag=(s.r.mag<<shift)+correction;s.r.exp-=shift;
        s.path=TRANS_LINEAR;
    }
    return s;
}

static void trans_core(TransState *s,int op) {
    V a=s->a,b=s->b,r=nanv(),c=ti(0);
    switch(op) {
    case SIN: case COS: case TAN: case SINCOS: case SINCOSPI: {
        V sine;tsc(a,op==SINCOSPI,&sine,&c);
        r=op==COS ? c:op==TAN ? td(sine,c):sine;
        break;
    }
    case ATAN: r=tatan(a);break;
    case ATAN2: r=tatan2(a,b);break;
    case ASIN: case ACOS: {
        V x=a;x.sign=0;
        if(a.kind!=NANV && compare(x,ti(1))<=0) {
            V root=tsqrt(tm(ta(ti(1),tneg(x)),ta(ti(1),x)));
            r=op==ASIN ? tatan2(a,root):tatan2(root,a);
        }
        break;
    }
    case LOG: case LOG2: case LOG10:
        r=tlog(a);
        if(op!=LOG)r=td(r,op==LOG2 ? tc_ln2():tc_ln10());
        break;
    case EXP: case EXP2: case EXP10:
        r=texp(op==EXP ? a:tm(a,op==EXP2 ? tc_ln2():tc_ln10()));
        break;
    case POW: r=tpow(a,b);break;
    case SINH: case COSH: case TANH: {
        V x=a;x.sign=0;
        if(op==TANH && x.kind==INF)r=ti(a.sign ? -1:1);
        else if(x.kind==FINITE && (!x.mag || width(x.mag)+x.exp< -4)) {
            V term=op==COSH ? ti(1):a,sum=term,xx=tm(a,a);
            for(int n=1;n<=90;++n) {
                term=td(tm(term,xx),ti(op==COSH ? (2*n-1)*(2*n):(2*n)*(2*n+1)));
                sum=ta(sum,term);
                if(tinyterm(term,sum))break;
            }
            if(op==TANH) {
                V sh=sum,ch=ti(1),t=ch;
                for(int n=1;n<=90;++n) {
                    t=td(tm(t,xx),ti((2*n-1)*(2*n)));
                    ch=ta(ch,t);
                }
                sum=td(sh,ch);
            }
            r=sum;
        } else {
            V ex=texp(x),inv=td(ti(1),ex);
            r=op==COSH ? ta(ex,inv):ta(ex,tneg(inv));
            if(op==TANH)r=td(r,ta(ex,inv));else --r.exp;
            if(op!=COSH)r.sign=a.sign;
        }
        break;
    }
    default: __builtin_trap();
    }
    s->r=r;s->c=c;
}

enum ExactDomain { EXACT_ZERO=1, EXACT_ONE=2, EXACT_INFINITY=4,
                   EXACT_OTHER_INFINITY=8, EXACT_ZERO_RESULT=16 };
static const unsigned trans_exact_domains[SINCOSPI+1]={
    [SIN]=EXACT_ZERO, [COS]=EXACT_ZERO, [TAN]=EXACT_ZERO,
    [ASIN]=EXACT_ZERO, [ACOS]=EXACT_ONE, [ATAN]=EXACT_ZERO,
    [ATAN2]=EXACT_ZERO_RESULT, [SINH]=EXACT_ZERO, [COSH]=EXACT_ZERO,
    [TANH]=EXACT_ZERO|EXACT_INFINITY, [EXP]=EXACT_ZERO|EXACT_INFINITY,
    [EXP2]=EXACT_INFINITY, [EXP10]=EXACT_INFINITY, [LOG]=EXACT_ONE,
    [POW]=EXACT_INFINITY|EXACT_OTHER_INFINITY, [SINCOS]=EXACT_ZERO
};

static int trans_is_exact(int op,V a,V b,V r) {
    unsigned domains=trans_exact_domains[op];
    return ((domains&EXACT_ZERO) && a.kind==FINITE && !a.mag) ||
           ((domains&EXACT_ONE) && a.kind==FINITE && compare(a,ti(1))==0) ||
           ((domains&EXACT_INFINITY) && a.kind==INF) ||
           ((domains&EXACT_OTHER_INFINITY) && b.kind==INF) ||
           ((domains&EXACT_ZERO_RESULT) && r.kind==FINITE && !r.mag);
}

static U trans_tanh_limit(V a,int fi,int rm,int *flags) {
    /* The finite limit is strict. IEEE formats cannot resolve the tail at
     * |x|>=64; PPC can until it falls below half its least quantum. */
    if(fi!=6)return pack((V){mask(480),-480,a.sign,FINITE,0},formats[fi],rm,flags);
    V x=a;x.sign=0;
    /* e^3>16 bounds this tail below half a PPC quantum. */
    if(compare(x,ti(512))>=0)
        return ppc_round_exact(((SquareBits)1<<2148)-1,-2148,a.sign,rm,flags);
    ++x.exp;x.sign=1;
    V q=texp(x),tail=td(tm(ti(2),q),ta(ti(1),q));
    SquareBits value=((SquareBits)1<<-tail.exp)-(SquareBits)tail.mag;
    return ppc_round_exact(value,tail.exp,a.sign,rm,flags);
}

static void trans_pack(U *out,int fi,int op,int rm,TransState s) {
    switch(s.path) {
    case TRANS_EXACT:
        out[0]=trans_pack_exact(s.exact[0],fi,rm,&s.flags);
        out[1]=s.pair ? trans_pack_exact(s.exact[1],fi,rm,&s.flags):0;
        out[2]=s.flags;
        return;
    case TRANS_PPC_EXP:
        out[0]=ppc_exp_near_zero(s.sum,rm,&s.flags);
        out[1]=0;out[2]=s.flags;
        return;
    case TRANS_TANH_LIMIT:
        out[0]=trans_tanh_limit(s.a,fi,rm,&s.flags);
        out[1]=0;out[2]=s.flags|16;
        return;
    case TRANS_LINEAR:
        if(fi==6) {
            /* Exact input sums and all canonical midpoints are on the 2^-1075
             * grid. A signed quarter-quantum perturbation selects precisely
             * the same neighbours as the nonzero analytic residual (<2^-1075),
             * including when a noncanonical input lies on a midpoint. */
            SquareBits mag=(SquareBits)s.sum.mag<<2;
            mag=trans_odd_correction[op]>0 ? mag+1:mag-1;
            out[0]=ppc_round_exact(mag,PPC_TINY_EXP,s.sum.sign,rm,&s.flags);
            out[1]=0;out[2]=s.flags;
            return;
        }
        break;
    case TRANS_CORE: break;
    }
    V a=s.a,b=s.b,r=s.r,c=s.c;
    if(r.kind==NANV && a.kind!=NANV && (!trans_binary_ops[op] || b.kind!=NANV))s.flags|=1;
    if((op==LOG || op==LOG2 || op==LOG10) && a.kind==FINITE && !a.mag)s.flags|=2;
    if(op==POW && a.kind==FINITE && !a.mag && b.sign && (b.mag || b.kind==INF))s.flags|=2;
    int exact=trans_is_exact(op,a,b,r);
    if(r.kind==FINITE && !exact)s.flags|=16;
    if((op==EXP || op==EXP2 || op==EXP10 || op==POW) && !r.mag &&
       r.kind==FINITE && a.kind==FINITE && a.mag && !exact)s.flags|=24;
    out[0]=fi==6 ? ppc_round(r,rm,&s.flags):pack(r,formats[fi],rm,&s.flags);
    out[1]=s.pair ? (fi==6 ? ppc_round(c,rm,&s.flags):pack(c,formats[fi],rm,&s.flags)):0;
    out[2]=s.flags;
}

static void trans_eval(U *out,int fi,int op,const U *in,int rm) {
    TransState s=trans_domain(fi,op,in);
    if(s.path==TRANS_CORE)trans_core(&s,op);
    trans_pack(out,fi,op,rm,s);
}
