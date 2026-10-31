/* Integer-only IEEE core. SPDX-License-Identifier: GPL-3.0-or-later
 * A finite value is (-1)^sign * mag * 2^exp. The largest exact product
 * has 226 bits. Addition aligns into 480 bits with a sticky low bit;
 * at least 253 spare bits remain even after product cancellation.
 * No C floating types, allocation, host math, or compiler division helpers.
 */
typedef unsigned _BitInt(128) U;
typedef unsigned _BitInt(512) Big;
typedef struct { int bits, p, eb, bias, explicit_bit; } Format;
static const Format formats[] = {
    {16,11,5,15,0}, {16,8,8,127,0}, {32,24,8,127,0},
    {64,53,11,1023,0}, {80,64,15,16383,1}, {128,113,15,16383,0}
};
typedef struct { Big mag; int exp, sign, kind, snan; } V;
enum { FINITE, INF, NANV };
enum { ADD,SUB,MUL,DIV,REM,CMP,FPTOSI,FPTOUI,SITOFP,UITOFP,
       SQRT,FLOOR,CEIL,TRUNC,ROUND,ROUNDEVEN,RINT,NEARBYINT,CANONICALIZE,
       MINNUM,MAXNUM,MINIMUM,MAXIMUM,MINIMUMNUM,MAXIMUMNUM,FMA,ISFPCLASS,
       LDEXP,FREXP,LROUND,LLROUND,LRINT,LLRINT,CONVERT,POWI,MODF };
static Big mask(int n) { return n == 512 ? ~(Big)0 : (((Big)1 << n)-1); }
static int width(Big x) { int n=0; while(x) { x>>=1; ++n; } return n; }
static Big jam(Big x, int n) {
    if(n<=0) return x << -n;
    if(n>=512) return x!=0;
    return (x>>n) | ((x & mask(n))!=0);
}
static Big quotient(Big a, Big b, Big *rem) {
    Big q=0, r=0;
    for(int i=width(a)-1;i>=0;--i) {
        r=(r<<1)|((a>>i)&1);
        if(r>=b) { r-=b; q|=(Big)1<<i; }
    }
    *rem=r; return q;
}
static U nanbits(Format f) {
    return (((U)mask(f.eb)) << (f.p-1+f.explicit_bit)) |
           ((U)1<<(f.p-2)) | (f.explicit_bit ? (U)1<<(f.p-1):0);
}
static U infbits(Format f, int sign) {
    return ((U)sign<<(f.bits-1)) | (((U)mask(f.eb))<<(f.p-1+f.explicit_bit)) |
        (f.explicit_bit ? (U)1<<(f.p-1):0);
}
static V unpack(U a, Format f) {
    int e=(int)((a>>(f.p-1+f.explicit_bit)) & (U)mask(f.eb));
    Big m=a & (U)mask(f.p-1+f.explicit_bit);
    V x={m, (e ? e:1)-f.bias-(f.p-1), (int)(a>>(f.bits-1)),FINITE,0};
    if(f.explicit_bit && ((e!=0) != (int)((m>>(f.p-1))&1))) {
        x.kind=NANV; x.snan=1; return x;
    }
    if(e==(int)mask(f.eb)) {
        x.kind=(m & mask(f.p-1)) ? NANV:INF;
        x.snan=x.kind==NANV && !(m & ((Big)1<<(f.p-2)));
    } else if(e && !f.explicit_bit) x.mag|=(Big)1<<(f.p-1);
    return x;
}
/* R=0 nearest/even, 1 down, 2 up, 3 zero, 4 nearest/away. */
static Big rounded(Big m,int shift,int sign,int rm,int *flags) {
    if(shift<=0) return m<<-shift;
    Big q=shift>=512 ? 0:m>>shift;
    Big rem=shift>=512 ? m:m & mask(shift);
    if(!rem) return q;
    *flags|=16;
    int half=shift>512 ? -1 : (rem>((Big)1<<(shift-1)) ? 1 :
                              rem==((Big)1<<(shift-1)) ? 0:-1);
    int up=(rm==1 && sign) || (rm==2 && !sign) ||
        ((rm==0 || rm==4) && (half>0 || (half==0 && (rm==4 || (q&1)))));
    return q+up;
}
static U pack(V x,Format f,int rm,int *flags) {
    if(x.kind==NANV) { if(x.snan) *flags|=1; return nanbits(f); }
    if(x.kind==INF) return infbits(f,x.sign);
    U s=(U)x.sign<<(f.bits-1);
    if(!x.mag) return s;
    int top=width(x.mag)-1+x.exp;
    int emin=1-f.bias, emax=f.bias;
    int target=(top<emin ? emin:top)-(f.p-1);
    Big q=rounded(x.mag,target-x.exp,x.sign,rm,flags);
    if(width(q)>f.p) { q>>=1; ++target; }
    int e=target+f.p-1;
    if(e>emax) {
        *flags|=20;
        if(rm==3 || (rm==1 && !x.sign) || (rm==2 && x.sign))
            return ((U)x.sign<<(f.bits-1)) | ((U)(mask(f.eb)-1)<<(f.p-1+f.explicit_bit)) | (U)mask(f.p-1+f.explicit_bit);
        return infbits(f,x.sign);
    }
    if(q<((Big)1<<(f.p-1))) {
        if(*flags & 16) *flags|=8; /* tininess after rounding */
        return s | (U)q;
    }
    U body=(U)q;
    if(!f.explicit_bit) body &= (U)mask(f.p-1);
    return s | ((U)(e+f.bias)<<(f.p-1+f.explicit_bit)) | body;
}
static int magcmp(V a,V b) {
    if(!a.mag || !b.mag) return (a.mag!=0)-(b.mag!=0);
    int wa=width(a.mag), wb=width(b.mag);
    int d=wa+a.exp-wb-b.exp;
    if(d) return d>0 ? 1:-1;
    Big am=a.mag<<(480-wa), bm=b.mag<<(480-wb);
    return (am>bm)-(am<bm);
}
static int compare(V a,V b) {
    if(!a.mag && !b.mag && a.kind==FINITE && b.kind==FINITE) return 0;
    if(a.sign!=b.sign) return a.sign ? -1:1;
    int c;
    if(a.kind==INF || b.kind==INF) c=(a.kind==INF)-(b.kind==INF);
    else c=magcmp(a,b);
    return a.sign ? -c:c;
}
static V nanv(void) { return (V){0,0,0,NANV,0}; }
static V add(V a,V b,int rm) {
    if(a.kind==NANV || b.kind==NANV) return nanv();
    if(a.kind==INF || b.kind==INF) {
        if(a.kind==INF && b.kind==INF && a.sign!=b.sign) return nanv();
        return a.kind==INF ? a:b;
    }
    if(!a.mag && !b.mag) return (V){0,0,a.sign==b.sign ? a.sign:rm==1,FINITE,0};
    if(!a.mag) return b;
    if(!b.mag) return a;
    int ta=width(a.mag)+a.exp, tb=width(b.mag)+b.exp;
    int base=(ta>tb ? ta:tb)-480;
    Big am=jam(a.mag,base-a.exp), bm=jam(b.mag,base-b.exp);
    if(a.sign==b.sign) return (V){am+bm,base,a.sign,FINITE,0};
    if(am==bm) return (V){0,0,rm==1,FINITE,0};
    return am>bm ? (V){am-bm,base,a.sign,FINITE,0} : (V){bm-am,base,b.sign,FINITE,0};
}
static V mul(V a,V b) {
    int s=a.sign^b.sign;
    if(a.kind==NANV || b.kind==NANV) return nanv();
    if(a.kind==INF || b.kind==INF) {
        if((a.kind==FINITE && !a.mag)||(b.kind==FINITE && !b.mag)) return nanv();
        return (V){0,0,s,INF,0};
    }
    return (V){a.mag*b.mag,a.exp+b.exp,s,FINITE,0};
}
static V integral(V a,int rm,int *flags) {
    if(a.kind!=FINITE || a.exp>=0) return a;
    a.mag=rounded(a.mag,-a.exp,a.sign,rm,flags); a.exp=0; return a;
}
static U toint(V a,int bits,int sign,int rm,int *flags) {
    if(a.kind==NANV) { *flags|=1; return 0; }
    V t=integral(a,rm,flags);
    Big bound=sign ? (Big)1<<(bits-1):((Big)1<<bits)-1;
    if(sign && !a.sign) --bound;
    if(!sign && a.sign) bound=0;
    Big n=t.mag;
    if(a.kind==INF || (n && (t.exp>=128 || width(n)+t.exp>128))) n=bound+1;
    else if(t.exp>0) n<<=t.exp;
    if(n>bound) { n=bound; *flags|=1; }
    U u=(U)n;
    return a.sign ? (U)0-u:u;
}
/* Wide input scans without a size bound. Retain 256 leading bits and sticky. */
static V fromwide(const unsigned char *p,int bits,int sign) {
    int neg=sign && ((p[(bits-1)/8]>>((bits-1)%8))&1);
    Big n=0; int discarded=0, sticky=0;
    /* Complement + 1 for a negative input, carrying from the low end. */
    unsigned carry=neg;
    for(int bit=0;bit<bits;++bit) {
        unsigned v=((p[bit/8]>>(bit%8))&1)^neg;
        unsigned digit=(v+carry)&1; carry=(v+carry)>>1;
        if(digit) {
            if(bit<256) n|=(Big)1<<bit;
            else {
                int shift=bit-255-discarded;
                if(shift>0) { sticky|=(n & mask(shift>512 ? 512:shift))!=0;
                    n=shift>=512 ? 0:n>>shift; discarded+=shift; }
                n|=(Big)1<<255;
            }
        }
    }
    if(sticky) n|=1;
    return (V){n,discarded,neg,FINITE,0};
}
static void towide(unsigned char *p,V a,int bits,int sign,int rm,int *flags) {
    if(a.kind==NANV) { *flags|=1; a=(V){0,0,0,FINITE,0}; }
    a=integral(a,rm,flags);
    int nbits=a.mag ? width(a.mag)+a.exp:0;
    int limit=bits-sign;
    int sat=a.kind==INF || nbits>limit;
    if(sign && a.sign && nbits==bits && a.mag &&
       (a.mag & (a.mag-1))==0) sat=0; /* INT_MIN */
    if(!sign && a.sign && a.mag) sat=1;
    if(sat) *flags|=1;
    unsigned carry=a.sign;
    for(int i=0;i<(bits+7)/8;++i) {
        unsigned byte=0;
        for(int j=0;j<8 && 8*i+j<bits;++j) {
            int k=8*i+j, v;
            if(sat) v=sign ? (a.sign ? k==bits-1:k<bits-1):!a.sign;
            else { int index=k-a.exp; unsigned digit=index>=0 && index<512 ? (unsigned)((a.mag>>index)&1):0;
                unsigned z=(digit^a.sign)+carry; v=z&1; carry=z>>1; }
            byte|=v<<j;
        }
        p[i]=(unsigned char)byte;
    }
    /* Slots have 64-bit limbs; clear padding of the final partial limb. */
    for(int i=(bits+7)/8;i<8*((bits+63)/64);++i) p[i]=0;
}
void bennett_sf_eval(U *out,int fi,int op,const U *in,int extra,int rm) {
    Format f=formats[fi]; V a=unpack(in[0],f), b=unpack(in[1],f), c=unpack(in[2],f), r=a;
    int flags=0; out[0]=out[1]=out[2]=0;
    if(op==SITOFP || op==UITOFP) {
        U x=in[0]; int sign=op==SITOFP && (int)(x>>127);
        r=(V){sign ? (U)0-x:x,0,sign,FINITE,0};
        out[0]=pack(r,f,rm,&flags); out[2]=flags; return;
    } else if(op==FPTOSI || op==FPTOUI || (op>=LROUND && op<=LLRINT)) {
        int mode=op==FPTOSI || op==FPTOUI ? 3:op<=LLROUND ? 4:rm;
        out[0]=toint(a,extra,op!=FPTOUI,mode,&flags); out[2]=flags; return;
    } else if(op==CMP) {
        int u=a.kind==NANV || b.kind==NANV;
        int d=u ? 0:compare(a,b);
        /* Predicate numbers are not a bit-mask of equality/order. */
        int p=extra&7;
        int v=p==0 ? 0:p==1 ? d==0:p==2 ? d>0:p==3 ? d>=0:p==4 ? d<0:p==5 ? d<=0:p==6 ? d!=0:1;
        out[0]=u ? (extra>=8):(extra==15 || v);
        return;
    } else if(op==ISFPCLASS) {
        int cls=a.kind==NANV ? (a.snan ? 0:1):a.kind==INF ? (a.sign?2:9):
            !a.mag ? (a.sign?5:6):width(a.mag)<f.p ? (a.sign?4:7):(a.sign?3:8);
        out[0]=(extra>>cls)&1; return;
    } else if(op==CONVERT) {
        out[0]=pack(a,formats[extra],rm,&flags); out[2]=flags; return;
    } else if(op==CANONICALIZE) {
        out[0]=a.kind==NANV ? nanbits(f):in[0]; return;
    } else if(op>=MINNUM && op<=MAXIMUMNUM) {
        int an=a.kind==NANV,bn=b.kind==NANV;
        if(an || bn) {
            if(op==MINIMUM || op==MAXIMUM || (an && bn)) r=nanv();
            else r=an ? b:a;
        } else {
            int d=compare(a,b);
            if(d==0 && !a.mag && !b.mag && a.kind==FINITE && b.kind==FINITE) d=b.sign-a.sign;
            r=(op&1) ? (d<=0 ? a:b):(d>=0 ? a:b); /* MINNUM=19 */
        }
    } else if(op==ADD || op==SUB) {
        if(op==SUB) b.sign^=1;
        r=add(a,b,rm);
    } else if(op==MUL || op==FMA) {
        r=mul(a,b);
        if(op==FMA) r=add(r,c,rm);
    } else if(op==DIV) {
        int s=a.sign^b.sign;
        if(a.kind==NANV || b.kind==NANV || (a.kind==INF && b.kind==INF) ||
           (a.kind==FINITE && !a.mag && b.kind==FINITE && !b.mag)) r=nanv();
        else if(a.kind==INF || (b.kind==FINITE && !b.mag)) {
            if(a.kind==FINITE) flags|=2;
            r=(V){0,0,s,INF,0};
        } else if(b.kind==INF) r=(V){0,0,s,FINITE,0};
        else {
            Big rem; int shift=256+width(b.mag)-width(a.mag);
            Big q=quotient(a.mag<<shift,b.mag,&rem);
            r=(V){q|(rem!=0),a.exp-b.exp-shift,s,FINITE,0};
        }
    } else if(op==REM) {
        if(a.kind==NANV || b.kind==NANV || a.kind==INF || (b.kind==FINITE && !b.mag)) r=nanv();
        else if(b.kind==INF || !a.mag || magcmp(a,b)<0) r=a;
        else {
            Big rem;
            if(a.exp>=b.exp) {
                quotient(a.mag,b.mag,&rem);
                for(int i=0;i<a.exp-b.exp;++i) { rem<<=1; if(rem>=b.mag) rem-=b.mag; }
                r=(V){rem,b.exp,a.sign,FINITE,0};
            } else {
                Big divisor=b.mag<<(b.exp-a.exp);
                quotient(a.mag,divisor,&rem); r=(V){rem,a.exp,a.sign,FINITE,0};
            }
        }
    } else if(op==SQRT) {
        if(a.kind==NANV || (a.sign && (a.mag || a.kind==INF))) r=nanv();
        else if(a.kind==FINITE && a.mag) {
            int shift=480-width(a.mag); if((a.exp-shift)%2) --shift;
            Big n=a.mag<<shift, root=0, rem=0;
            for(int i=239;i>=0;--i) {
                rem=(rem<<2)|((n>>(2*i))&3);
                Big trial=(root<<2)|1;
                root<<=1; if(rem>=trial) { rem-=trial; ++root; }
            }
            r=(V){root|(rem!=0),(a.exp-shift)/2,0,FINITE,0};
        }
    } else if(op>=FLOOR && op<=NEARBYINT) {
        int mode=op==FLOOR ? 1:op==CEIL ? 2:op==TRUNC ? 3:op==ROUND ? 4:op==ROUNDEVEN ? 0:rm;
        r=integral(a,mode,&flags);
        if(op==NEARBYINT) flags&=~16;
    } else if(op==LDEXP) {
        if(a.kind==FINITE && a.mag) {
            /* Clamp exponent arithmetic, never clamp the numerical result. */
            r.exp+=extra>100000 ? 100000:extra< -100000 ? -100000:extra;
        }
    } else if(op==FREXP) {
        if(a.kind==FINITE && a.mag) { int e=width(a.mag)+a.exp; r.exp-=e; out[1]=(U)(unsigned)e; }
    } else if(op==POWI) {
        /* extra is signed i32; repeated squaring, rounding at every step. */
        unsigned n=extra<0 ? 0u-(unsigned)extra:(unsigned)extra;
        V one={(Big)1,0,0,FINITE,0}; r=one;
        while(n) {
            if(n&1) r=unpack(pack(mul(r,a),f,rm,&flags),f);
            n>>=1;
            if(n) a=unpack(pack(mul(a,a),f,rm,&flags),f);
        }
        if(extra<0) {
            U args[3]={pack(one,f,rm,&flags),pack(r,f,rm,&flags),0}, result[3];
            bennett_sf_eval(result,fi,DIV,args,0,rm); r=unpack(result[0],f); flags|=(int)result[2];
        }
    } else if(op==MODF) {
        V whole=integral(a,3,&flags);
        out[1]=pack(whole,f,rm,&flags);
        if(a.kind==INF) r=(V){0,0,a.sign,FINITE,0};
        else { whole.sign^=1; r=add(a,whole,rm); if(!r.mag) r.sign=a.sign; }
    } else __builtin_trap();
    if(a.snan || ((op<=REM || op==FMA || (op>=MINNUM && op<=MAXIMUMNUM)) && b.snan) || (op==FMA && c.snan)) flags|=1;
    if(r.kind==NANV && a.kind!=NANV &&
       (!(op<=REM || op==FMA || (op>=MINNUM && op<=MAXIMUMNUM)) || b.kind!=NANV) && (op!=FMA || c.kind!=NANV)) flags|=1;
    out[0]=pack(r,f,rm,&flags); out[2]=flags;
}
void bennett_sf_wide(U *out,int fi,int op,void *slot,int bits,const U *in,int rm) {
    int flags=0; out[0]=out[1]=out[2]=0;
    if(op==SITOFP || op==UITOFP) out[0]=pack(fromwide(slot,bits,op==SITOFP),formats[fi],rm,&flags);
    else towide(slot,unpack(in[0],formats[fi]),bits,op!=FPTOUI,
                op==FPTOSI || op==FPTOUI ? 3:op<=LLROUND ? 4:rm,&flags);
    out[2]=flags;
}
