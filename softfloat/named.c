/* Named LLVM 23 formats. Use the integer core directly, never host FP or
 * APFloat. This translation unit is used by the offline instance generator. */
#include "core.c"
typedef struct { Format f; int behavior; } Named;
enum { NI, NUZ, NFN, NSCALE, NFINITE };
static const Named named[] = {
    {{8,3,5,15,0},NI}, {{8,3,5,16,0},NUZ},
    {{8,4,4,7,0},NI}, {{8,4,4,7,0},NFN},
    {{8,4,4,8,0},NUZ}, {{8,4,4,11,0},NUZ},
    {{8,5,3,3,0},NI}, {{8,1,8,127,0},NSCALE},
    {{6,3,3,3,0},NFINITE}, {{6,4,2,1,0},NFINITE},
    {{4,2,2,1,0},NFINITE}
};
static U named_nan(Named n) {
    return n.behavior==NUZ ? (U)1<<(n.f.bits-1):
           n.behavior==NFN ? mask(n.f.bits-1):
           n.behavior==NSCALE ? 255:n.behavior==NFINITE ? 0:nanbits(n.f);
}
static V named_unpack(U x,Named n) {
    Format f=n.f;int kind=n.behavior;
    if(kind==NI) return unpack(x,f);
    if(kind==NSCALE) return x==255 ? nanv():(V){1,(int)x-127,0,FINITE,0};
    U sign=(U)1<<(f.bits-1),body=x & (sign-1);
    if((kind==NUZ && x==sign) || (kind==NFN && body==sign-1)) return nanv();
    int e=(int)(body>>(f.p-1));
    Big m=body & mask(f.p-1);
    if(e) m|=(Big)1<<(f.p-1);
    return (V){m,(e ? e:1)-f.bias-f.p+1,(int)(x>>(f.bits-1)),FINITE,0};
}
static U named_pack(V a,Named n,int rm,int sat) {
    Format f=n.f;int kind=n.behavior,ignored=0;
    U sign=kind==NSCALE ? 0:(U)a.sign<<(f.bits-1);
    U max=kind==NSCALE ? 254:mask(f.bits-1)-(kind==NFN ? 1:kind==NI ? (1<<(f.p-1)):0);
    if(a.kind==NANV) return named_nan(n);
    /* N1 fixes poison results at zero bits, including unsigned negatives. */
    if(kind==NSCALE && a.sign && (a.mag || a.kind==INF)) return 0;
    int overflow=a.kind==INF;
    if(!overflow) {
        if(!a.mag) return kind==NSCALE || kind==NUZ ? 0:sign;
        int top=width(a.mag)-1+a.exp;
        int target=kind==NSCALE ? (top < -127 ? -127:top):
                   (top < 1-f.bias ? 1-f.bias:top)-(f.p-1);
        a.mag=rounded(a.mag,target-a.exp,a.sign,rm,&ignored);a.exp=target;
        if(width(a.mag)>f.p) {a.mag>>=1;++a.exp;}
        V limit=named_unpack(max,n);limit.sign=a.sign;
        overflow=magcmp(a,limit)>0;
        if(!overflow) {
            if(kind==NSCALE) return (U)(a.exp+127);
            if(!a.mag) return kind==NUZ ? 0:sign;
            if(a.mag<((Big)1<<(f.p-1))) return sign|(U)a.mag;
            return sign|((U)(a.exp+f.p-1+f.bias)<<(f.p-1))|((U)a.mag & (U)mask(f.p-1));
        }
    }
    if(sat) return sign|max;
    return kind==NI ? infbits(f,a.sign):0;
}
void bennett_sf_named(U *out,int fi,int ni,int to,const U *in,int rm,int sat) {
    if(fi<0 || fi>6 || ni<0 || ni>10 || rm<0 || rm>4) __builtin_trap();
    Named n=named[ni];int ignored=0;
    if(to) {
        V a=unpack(fi==6 ? low64(in[0]):in[0],formats[fi==6 ? 3:fi]);
        if(fi==6 && a.kind==FINITE) {
            V lo=unpack(in[0]>>64,formats[3]);
            if(a.mag || lo.mag || lo.kind!=FINITE) a=add(a,lo,0);
        }
        out[0]=named_pack(a,n,rm,sat);
    } else {
        V a=named_unpack(in[0],n);
        /* Every finite named value fits binary64 exactly, so its PPC low is 0. */
        out[0]=pack(a,formats[fi==6 ? 3:fi],0,&ignored);
    }
}
