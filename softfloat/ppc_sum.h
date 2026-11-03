/* Exact sums of two binary64 components. Every finite component is an integer
 * multiple of 2^-1074; 2176 bits cover both full exponent ranges plus a carry.
 * These helpers never round an intermediate component or use host FP. */
typedef unsigned _BitInt(2176) SumBits;
typedef struct { SumBits mag; int sign,kind,snan; } PairSum;
static SumBits sum_mask(int n) { return n==2176 ? ~(SumBits)0:((SumBits)1<<n)-1; }
static int sum_width(SumBits x) {
    int n=0;
    if(x>>2048){x>>=2048;n+=2048;}
    if(x>>1024){x>>=1024;n+=1024;}
    if(x>>512){x>>=512;n+=512;}
    return n+width((Big)x);
}
static PairSum sum_scalar(V a) {
    return (PairSum){a.kind==FINITE ? (SumBits)a.mag<<(a.exp+1074):0,a.sign,a.kind,a.snan};
}
static PairSum sum_add(PairSum a,PairSum b) {
    if(!a.mag && !b.mag) return (PairSum){0,a.sign==b.sign ? a.sign:0,FINITE,0};
    if(!a.mag)return b;
    if(!b.mag)return a;
    if(a.sign==b.sign)return (PairSum){a.mag+b.mag,a.sign,FINITE,0};
    if(a.mag==b.mag)return (PairSum){0,0,FINITE,0};
    return a.mag>b.mag ? (PairSum){a.mag-b.mag,a.sign,FINITE,0}:(PairSum){b.mag-a.mag,b.sign,FINITE,0};
}
static PairSum sum_read(U x) {
    V h=unpack(low64(x),formats[3]),l=unpack(x>>64,formats[3]);
    int sn=h.snan || l.snan;
    if(h.kind==NANV || l.kind==NANV)return (PairSum){0,0,NANV,sn};
    if(h.kind==INF || l.kind==INF) {
        if(h.kind==INF && l.kind==INF && h.sign!=l.sign)return (PairSum){0,0,NANV,1};
        return (PairSum){0,h.kind==INF ? h.sign:l.sign,INF,0};
    }
    if(!h.mag && !l.mag)return (PairSum){0,h.sign,FINITE,0};
    return sum_add(sum_scalar(h),sum_scalar(l));
}
static V sum_value(PairSum a) {
    if(a.kind!=FINITE || !a.mag)return (V){0,0,a.sign,a.kind,a.snan};
    int shift=sum_width(a.mag)-480;if(shift<0)shift=0;
    Big m=(Big)(a.mag>>shift);
    if(shift && (a.mag&sum_mask(shift)))m|=1;
    return (V){m,shift-1074,a.sign,FINITE,0};
}
static SumBits sum_integral(PairSum a,int mode,int record_inexact,int *flags) {
    SumBits q=a.mag>>1074,rem=a.mag&sum_mask(1074),half=(SumBits)1<<1073;
    if(!rem)return q;
    if(record_inexact)*flags|=16;
    int up=(mode==1 && a.sign) || (mode==2 && !a.sign) ||
        ((mode==0 || mode==4) && (rem>half || (rem==half && (mode==4 || (q&1)))));
    return q+up;
}
static U sum_overflow(int sign,int mode,int *flags) {
    *flags|=20;
    if(mode==3 || (mode==1 && !sign) || (mode==2 && sign)) {
        U s=(U)sign<<63;
        return (s|0x7fefffffffffffffULL)|((s|0x7c8fffffffffffffULL)<<64);
    }
    return infbits(formats[3],sign);
}
static PairSum sum_difference(PairSum a,PairSum b) { b.sign^=1;return sum_add(a,b); }
static U sum_round_pair(PairSum exact,int mode,int *flags) {
    if(!exact.mag)return (U)exact.sign<<63;
    int ignored=0;
    U hi=pack(sum_value(exact),formats[3],0,&ignored);
    V h=unpack(hi,formats[3]);
    if(h.kind==INF)return sum_overflow(exact.sign,mode,flags);
    h.sign^=1;
    PairSum residual=sum_add(exact,sum_scalar(h));
    V rv=sum_value(residual);U lo;
    if(mode==4) {
        U down=pack(rv,formats[3],1,&ignored),up=pack(rv,formats[3],2,&ignored);
        PairSum de=sum_difference(residual,sum_scalar(unpack(down,formats[3])));
        PairSum ue=sum_difference(sum_scalar(unpack(up,formats[3])),residual);
        lo=de.mag<ue.mag ? down:de.mag>ue.mag ? up:exact.sign ? down:up;
    } else {
        int lm=mode==3 ? (exact.sign ? 2:1):mode;
        lo=pack(rv,formats[3],lm,&ignored);
    }
    if(!residual.mag)lo=0;
    PairSum rounded=sum_add(sum_scalar(unpack(hi,formats[3])),sum_scalar(unpack(lo,formats[3])));
    hi=pack(sum_value(rounded),formats[3],0,&ignored);h=unpack(hi,formats[3]);
    if(h.kind==INF)return sum_overflow(exact.sign,mode,flags);
    PairSum tail=sum_difference(rounded,sum_scalar(h));
    lo=tail.mag ? pack(sum_value(tail),formats[3],0,&ignored):0;
    U result=hi|(lo<<64);
    PairSum actual=sum_read(result);
    if(actual.mag!=exact.mag || actual.sign!=exact.sign) {
        *flags|=16;
        if(actual.mag<((SumBits)1<<52))*flags|=8;
    }
    return result;
}
static U sum_integer_pair(SumBits n,int sign,int mode,int *flags) {
    return sum_round_pair((PairSum){n<<1074,sign,FINITE,0},mode,flags);
}
static U ppc_sum_fromwide(const unsigned char *src,int bits,int sign,int rm,int *flags) {
    if(bits<1)__builtin_trap();
    V leading=fromwide(src,bits,sign);
    if(leading.mag && width(leading.mag)+leading.exp>1024)return sum_overflow(leading.sign,rm,flags);
    SumBits n=0;unsigned carry=leading.sign;
    for(int i=0;i<(bits+7)/8;++i) {
        unsigned v=(src[i]^(leading.sign ? 255:0))+carry;carry=v>>8;v&=255;
        if(bits-8*i<8)v&=(1u<<(bits-8*i))-1;
        if(8*i<2176)n|=(SumBits)v<<(8*i);
    }
    return sum_integer_pair(n,leading.sign,rm,flags);
}
static U ppc_sum_integral(U x,int op,int rm,int *flags) {
    PairSum a=sum_read(x);
    if(a.kind==NANV){if(a.snan)*flags|=1;return nanbits(formats[3]);}
    if(a.kind==INF)return infbits(formats[3],a.sign);
    int mode=op==FLOOR ? 1:op==CEIL ? 2:op==TRUNC ? 3:op==ROUND ? 4:op==ROUNDEVEN ? 0:rm;
    SumBits n=sum_integral(a,mode,op==RINT,flags);
    return sum_integer_pair(n,a.sign,rm,flags);
}
/* sqrt(x)/2^-1074 = sqrt(M*2^1074), where x=M*2^-1074 exactly.
 * The radicand has at most 3173 bits, and squared pair midpoints at most 3176.
 * Every canonical pair lies on the 2^-1074 grid. Its neighbours are therefore
 * found by directed rounding of floor(root) and floor(root)+1, without an
 * approximate real square root. Only final comparisons affect IEEE flags. */
typedef unsigned _BitInt(4352) SquareBits;
static int square_width(SquareBits x) {
    int n=0;
    if(x>>4096){x>>=4096;n+=4096;}
    if(x>>2048){x>>=2048;n+=2048;}
    if(x>>1024){x>>=1024;n+=1024;}
    if(x>>512){x>>=512;n+=512;}
    return n+width((Big)x);
}
#include "ppc_round.h"
static U ppc_sum_sqrt(U x,int rm,int *flags) {
    PairSum a=sum_read(x);
    if(a.kind==NANV){if(a.snan)*flags|=1;return nanbits(formats[3]);}
    if(a.sign && (a.mag || a.kind==INF)){*flags|=1;return nanbits(formats[3]);}
    if(a.kind==INF)return infbits(formats[3],0);
    if(!a.mag)return (U)a.sign<<63;
    SquareBits rad=(SquareBits)a.mag<<1074,root=0,rem=0;
    for(int i=(square_width(rad)+1)/2-1;i>=0;--i) {
        rem=(rem<<2)|((rad>>(2*i))&3);
        SquareBits trial=(root<<2)|1;
        root<<=1;
        if(rem>=trial){rem-=trial;++root;}
    }
    int ignored=0;
    U lower=sum_round_pair((PairSum){(SumBits)root,0,FINITE,0},1,&ignored);
    PairSum ls=sum_read(lower);
    if((SquareBits)ls.mag*ls.mag==rad)return lower;
    U upper=sum_round_pair((PairSum){(SumBits)(root+1),0,FINITE,0},2,&ignored);
    PairSum us=sum_read(upper);U result;
    if(rm==1 || rm==3)result=lower;
    else if(rm==2)result=upper;
    else {
        SquareBits mid=(SquareBits)ls.mag+us.mag;
        SquareBits squared=mid*mid,scaled=rad<<2;
        if(scaled<squared)result=lower;
        else if(scaled>squared || rm==4)result=upper;
        else {
            U low=lower>>64;
            /* At a zero-low transition an odd/odd pair midpoint has a half
             * grid unit, whose square cannot be a binary64-pair input. Thus
             * the unresolved 4yg.1 FMA tie is unreachable for sqrt. */
            result=!((low ? low:low64(lower))&1) ? lower:upper;
        }
    }
    PairSum r=sum_read(result);
    if((SquareBits)r.mag*r.mag!=rad) {
        *flags|=16;
        if(r.mag<((SumBits)1<<52))*flags|=8;
    }
    return result;
}
static U ppc_sum_integer(U x,int bits,int sign,int mode,int record_inexact,int *flags) {
    if(bits<1 || bits>128)__builtin_trap();
    PairSum a=sum_read(x);
    if(a.kind==NANV){*flags|=1;return 0;}
    SumBits n=sum_integral(a,mode,record_inexact,flags);
    SumBits bound=sign ? (SumBits)1<<(bits-1):sum_mask(bits);
    if(sign && !a.sign)--bound;
    if(!sign && a.sign)bound=0;
    if(a.kind==INF || n>bound){n=bound;*flags|=1;}
    return a.sign ? (U)0-(U)n:(U)n;
}
static void ppc_sum_towide(unsigned char *slot,U x,int bits,int sign,int mode,int record_inexact,int *flags) {
    if(bits<1)__builtin_trap();
    PairSum a=sum_read(x);
    if(a.kind==NANV){*flags|=1;a=(PairSum){0,0,FINITE,0};}
    SumBits n=sum_integral(a,mode,record_inexact,flags);
    int nb=sum_width(n),sat=a.kind==INF || nb>bits-sign;
    if(sign && a.sign && nb==bits && n && !(n&(n-1)))sat=0;
    if(!sign && a.sign && n)sat=1;
    if(sat)*flags|=1;
    unsigned carry=a.sign;
    for(int i=0;i<(bits+7)/8;++i) {
        unsigned byte=0;
        if(sat) {
            for(int j=0;j<8 && 8*i+j<bits;++j) {
                int k=8*i+j;
                unsigned bit=sign ? (a.sign ? k==bits-1:k<bits-1):!a.sign;
                byte|=bit<<j;
            }
        } else {
            unsigned digit=8*i<2176 ? (unsigned)(n>>(8*i))&255:0;
            unsigned v=(digit^(a.sign ? 255:0))+carry;carry=v>>8;byte=v&255;
            if(bits-8*i<8)byte&=(1u<<(bits-8*i))-1;
        }
        slot[i]=(unsigned char)byte;
    }
    for(int i=(bits+7)/8;i<8*((bits+63)/64);++i)slot[i]=0;
}
