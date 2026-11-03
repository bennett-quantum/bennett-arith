/* Round an exact dyadic value once to adjacent canonical binary64 pairs.
 * FMA uses quantum 2^-2148 and at most 4197 bits, including cancellation.
 * Incoming IEEE values retain their original exponent, even below that grid.
 */
static int dyadic_compare(SquareBits a,int ae,SquareBits b,int be) {
    if(!a || !b)return !!a-!!b;
    int aw=square_width(a),bw=square_width(b);
    if(aw+ae!=bw+be)return aw+ae>bw+be ? 1:-1;
    if(ae>be)a<<=ae-be;else b<<=be-ae;
    return a>b ? 1:a<b ? -1:0;
}
static U pair_sign(U x,int sign) {
    return sign ? x^((U)1<<63)^(x>>64 ? (U)1<<127:0):x;
}
static U ppc_round_exact(SquareBits mag,int exp,int sign,int rm,int *flags) {
    if(!mag)return (U)sign<<63;
    int mode=sign ? (rm==1 ? 2:rm==2 ? 1:rm):rm;
    if(square_width(mag)+exp>1024)return sum_overflow(sign,rm,flags);
    U maxbits=(U)0x7fefffffffffffffULL|((U)0x7c8fffffffffffffULL<<64);
    PairSum maximum=sum_read(maxbits);
    int mc=dyadic_compare(mag,exp,(SquareBits)maximum.mag,-1074);
    if(mc>=0) {
        if(!mc)return pair_sign(maxbits,sign);
        SumBits boundary=sum_scalar(unpack(0x7fefffffffffffffULL,formats[3])).mag+((SumBits)1<<2044);
        int overflow=mode==2 || ((mode==0 || mode==4) ?
            dyadic_compare(mag,exp+1,(SquareBits)maximum.mag+boundary,-1074)>=0:
            dyadic_compare(mag,exp,(SquareBits)boundary,-1074)>=0);
        if(overflow)return sum_overflow(sign,rm,flags);
        *flags|=16;return pair_sign(maxbits,sign);
    }
    int shift=exp+1074,fractional=0;SumBits n;
    if(shift>=0)n=(SumBits)mag<<shift;
    else {
        int s=-shift;
        n=s>=4352 ? 0:(SumBits)(mag>>s);
        fractional=s>=4352 ? !!mag:!!(mag&(((SquareBits)1<<s)-1));
    }
    int ignored=0;
    U lower=sum_round_pair((PairSum){n,0,FINITE,0},1,&ignored);
    U upper=sum_round_pair((PairSum){n+fractional,0,FINITE,0},2,&ignored),result;
    PairSum l=sum_read(lower),u=sum_read(upper);
    if(mode==1 || mode==3)result=lower;
    else if(mode==2)result=upper;
    else {
        int midpoint=dyadic_compare(mag,exp+1,(SquareBits)l.mag+u.mag,-1074);
        if(midpoint<0)result=lower;
        else if(midpoint>0 || mode==4)result=upper;
        else {
            U ll=lower>>64,ul=upper>>64;
            int le=!((ll ? ll:low64(lower))&1),ue=!((ul ? ul:low64(upper))&1);
            result=le || !ue ? lower:upper;
        }
    }
    PairSum rounded=sum_read(result);
    if(dyadic_compare(mag,exp,(SquareBits)rounded.mag,-1074)) {
        *flags|=16;if(rounded.mag<((SumBits)1<<52))*flags|=8;
    }
    return pair_sign(result,sign);
}
static U ppc_round(V a,int rm,int *flags) {
    if(a.kind==NANV){if(a.snan)*flags|=1;return nanbits(formats[3]);}
    if(a.kind==INF)return infbits(formats[3],a.sign);
    return ppc_round_exact((SquareBits)a.mag,a.exp,a.sign,rm,flags);
}
static U ppc_fma(U x,U y,U z,int rm,int *flags) {
    PairSum a=sum_read(x),b=sum_read(y),c=sum_read(z);
    if(a.snan || b.snan || c.snan)*flags|=1;
    int invalid=(a.kind==INF && b.kind==FINITE && !b.mag) ||
                (b.kind==INF && a.kind==FINITE && !a.mag);
    if(invalid)*flags|=1;
    if(invalid || a.kind==NANV || b.kind==NANV || c.kind==NANV)return nanbits(formats[3]);
    int sign=a.sign^b.sign;
    if(a.kind==INF || b.kind==INF) {
        if(c.kind==INF && c.sign!=sign){*flags|=1;return nanbits(formats[3]);}
        return infbits(formats[3],sign);
    }
    if(c.kind==INF)return infbits(formats[3],c.sign);
    SquareBits product=(SquareBits)a.mag*b.mag,addend=(SquareBits)c.mag<<1074,mag;
    if(sign==c.sign)mag=product+addend;
    else if(product>=addend){mag=product-addend;if(!mag)sign=rm==1;}
    else {mag=addend-product;sign=c.sign;}
    return ppc_round_exact(mag,-2148,sign,rm,flags);
}
