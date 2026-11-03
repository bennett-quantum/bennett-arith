/* Exact dyadic cases of exp2/exp10/log2/log10/pow. An odd significand
 * wider than 2176 bits cannot be an exact finite value of any carrier:
 * IEEE has at most 113 significant bits; a PPC sum spans at most 2098.
 * Cases exceeding that bound are necessarily inexact, and retain the
 * general numerical path. No argument or operation is rejected. */
typedef struct { SquareBits mag; int exp,sign,kind,snan; } ExactReal;
static ExactReal trans_input(U raw,int fi) {
    if(fi==6){PairSum x=sum_read(raw);return (ExactReal){x.mag,-1074,x.sign,x.kind,x.snan};}
    V x=unpack(raw,formats[fi]);return (ExactReal){x.mag,x.exp,x.sign,x.kind,x.snan};
}
static void exact_normalize(ExactReal *x) {
    if(!x->mag)return;
    for(int s=2048;s;s>>=1)if(!(x->mag&(((SquareBits)1<<s)-1))) {x->mag>>=s;x->exp+=s;}
}
static SquareBits exact_divide_small(SquareBits x,unsigned d,unsigned *remainder) {
    SquareBits q=0;unsigned rem=0;
    for(int i=(square_width(x)+31)/32-1;i>=0;--i) {
        unsigned long long v=((unsigned long long)rem<<32)|(unsigned)(x>>(32*i));
        q|=(SquareBits)(v/d)<<(32*i);rem=(unsigned)(v%d);
    }
    *remainder=rem;return q;
}
static int exact_square_root(SquareBits *x) {
    SquareBits root=0,rem=0;
    for(int i=(square_width(*x)+1)/2-1;i>=0;--i) {
        rem=(rem<<2)|((*x>>(2*i))&3);SquareBits trial=(root<<2)|1;
        root<<=1;if(rem>=trial){rem-=trial;++root;}
    }
    if(rem)return 0;*x=root;return 1;
}
static int exact_power(SquareBits base,unsigned n,SquareBits *result) {
    SquareBits p=1;
    while(n) {
        if(n&1){p*=base;if(square_width(p)>2176)return 0;}
        n>>=1;
        if(n){base*=base;if(square_width(base)>2176)return 0;}
    }
    *result=p;return 1;
}
static int trans_exact_math(int op,ExactReal a,ExactReal b,ExactReal *r) {
    *r=(ExactReal){1,0,0,FINITE,0};
    if(op==POW && b.kind==FINITE && !b.mag)return 1;
    if(op==POW && a.kind==FINITE && !a.sign &&
       dyadic_compare(a.mag,a.exp,1,0)==0)return 1;
    if(a.kind!=FINITE)return 0;
    exact_normalize(&a);
    if(op==LOG2 || op==LOG10) {
        if(a.sign || !a.mag)return 0;
        int n=0;
        if(op==LOG10) {
            while(a.mag>1) {
                unsigned rem;SquareBits q=exact_divide_small(a.mag,5,&rem);
                if(rem)return 0;a.mag=q;++n;
            }
            if(a.exp!=n)return 0;
        } else {if(a.mag!=1)return 0;n=a.exp;}
        *r=(ExactReal){n<0 ? -n:n,0,n<0,FINITE,0};return 1;
    }
    if(op==EXP2 || op==EXP10) {
        if(!a.mag)return 1;
        if(a.exp<0)return 0;
        if(op==EXP2) {
            int n=square_width(a.mag)+a.exp>16 ? 100000:(int)(a.mag<<a.exp);
            r->exp=a.sign ? -n:n;return 1;
        }
        if(a.sign || square_width(a.mag)+a.exp>12)return 0;
        unsigned n=(unsigned)(a.mag<<a.exp);
        if(!exact_power(5,n,&r->mag))return 0;
        r->exp=(int)n;return 1;
    }
    if(op!=POW || b.kind==NANV)return 0;
    if(b.kind==INF && a.mag) {
        int d=dyadic_compare(a.mag,a.exp,1,0);
        if(d) {if((d>0)^b.sign)r->kind=INF;else r->mag=0;}
        return 1;
    }
    if(b.kind==INF && !a.mag && !b.sign){r->mag=0;return 1;}
    if(b.kind!=FINITE)return 0;
    exact_normalize(&b);
    if(!a.mag) {
        if(b.sign)return 0;
        r->mag=0;r->sign=a.sign && b.exp==0 && (b.mag&1);return 1;
    }
    if(a.sign && b.exp<0)return 0;
    int fractional=b.exp<0 ? -b.exp:0;
    /* Each exact square root removes one factor of two from the exponent's
     * denominator. A failed integer root proves a nondyadic result. */
    for(int i=0;i<fractional;++i) {
        if(a.exp%2 || !exact_square_root(&a.mag))return 0;
        a.exp/=2;
        if(a.mag==1 && a.exp==0)break;
    }
    r->sign=a.sign && b.exp==0 && (b.mag&1);
    int shift=b.exp>0 ? b.exp:0;
    if(a.mag==1) {
        if(!a.exp)return 1;
        long long n=square_width(b.mag)+shift>30 ? 1000000000LL:(long long)(b.mag<<shift);
        long long exponent=(long long)a.exp*n*(b.sign ? -1:1);
        r->exp=exponent>100000 ? 100000:exponent< -100000 ? -100000:(int)exponent;
        return 1;
    }
    if(b.sign || square_width(b.mag)+shift>12)return 0;
    unsigned n=(unsigned)(b.mag<<shift);
    if(!exact_power(a.mag,n,&r->mag))return 0;
    r->exp=a.exp*(int)n;return 1;
}
static U trans_pack_exact(ExactReal x,int fi,int rm,int *flags) {
    if(x.kind==INF)return infbits(formats[fi==6 ? 3:fi],x.sign);
    if(fi==6)return ppc_round_exact(x.mag,x.exp,x.sign,rm,flags);
    int shift=square_width(x.mag)-480;if(shift<0)shift=0;
    Big mag=(Big)(x.mag>>shift);
    if(shift && (x.mag&(((SquareBits)1<<shift)-1)))mag|=1;
    return pack((V){mag,x.exp+shift,x.sign,FINITE,0},formats[fi],rm,flags);
}
static int trans_exact_sincospi(ExactReal a,ExactReal *s,ExactReal *c) {
    if(a.kind!=FINITE)return 0;
    exact_normalize(&a);
    if(a.mag && a.exp< -1)return 0;
    int shift=a.exp+1;
    unsigned q=!a.mag || shift>=2 ? 0:(unsigned)(a.mag<<shift)&3;
    if(a.sign)q=(-q)&3;
    *s=(ExactReal){q&1,0,(q&1) ? q==3:a.sign,FINITE,0};
    *c=(ExactReal){!(q&1),0,q==2,FINITE,0};
    return 1;
}
