/* PPCDoubleDouble contract adapter. The component algorithms follow LLVM
 * DoubleAPFloat (Apache-2.0 WITH LLVM-exception), using our integer f64 core.
 * High double occupies bits 0..63, low double bits 64..127.
 * Component operations retain APFloat conventions. Exact conversions and
 * integral operations use ppc_sum.h; remaining numerical gaps are explicit.
 */
static U low64(U x) { return x & (((U)1<<64)-1); }
#include "ppc_sum.h"
static U ppc_pack(V a,int rm,int *flags) {
    /* Legacy 106-bit rounding precedes the nearest/even component split. */
    a=unpack(pack(a,formats[7],rm,flags),formats[7]);
    int ignored=0;
    U hi=pack(a,formats[3],0,&ignored),lo=0;
    V h=unpack(hi,formats[3]);
    if(h.kind==FINITE && h.mag) { h.sign^=1; lo=pack(add(a,h,0),formats[3],0,&ignored); }
    if(a.kind==NANV) return nanbits(formats[3]);
    return hi|(lo<<64);
}
static V ppc_unpack(U x) {
    V a=unpack(low64(x),formats[3]);
    if(a.kind==FINITE && a.mag) {
        int ignored=0;
        a=add(a,unpack(x>>64,formats[3]),0);
        a=unpack(pack(a,formats[7],0,&ignored),formats[7]);
    }
    return a;
}
static U ddop(int op,U a,U b,U c,int rm,int *flags) {
    U args[3]={a,b,c},out[3];
    bennett_sf_eval(out,3,op,args,0,rm); *flags|=(int)out[2];return out[0];
}
static int ddcat(U x) {
    V a=unpack(low64(x),formats[3]);
    return a.kind==FINITE && !a.mag ? 3:a.kind;
}
static U ddadd(U x,U y,int rm,int *flags) {
    int xc=ddcat(x),yc=ddcat(y);
    if(xc==NANV || yc==NANV) return nanbits(formats[3]);
    if(xc==3) return y;
    if(yc==3) return x;
    if(xc==INF || yc==INF) {
        if(xc==INF && yc==INF && ((x^y)>>63&1)) { *flags|=1;return nanbits(formats[3]); }
        return xc==INF ? x:y;
    }
    U a=low64(x),aa=x>>64,c=low64(y),cc=y>>64;
    int status=0;
    U z=ddop(ADD,a,c,0,rm,&status),hi,lo;
    if(ddcat(z)!=FINITE && ddcat(z)!=3) {
        if(ddcat(z)==NANV) { *flags|=status;return z; }
        status=0;
        int cmp=magcmp(unpack(a,formats[3]),unpack(c,formats[3]));
        z=ddop(ADD,cc,aa,0,rm,&status);
        z=ddop(ADD,z,cmp>0 ? c:a,0,rm,&status);
        z=ddop(ADD,z,cmp>0 ? a:c,0,rm,&status);
        if(ddcat(z)!=FINITE && ddcat(z)!=3) { *flags|=status;return z; }
        hi=z;
        U zz=ddop(ADD,aa,cc,0,rm,&status);
        lo=ddop(SUB,cmp>0 ? a:c,z,0,rm,&status);
        lo=ddop(ADD,lo,cmp>0 ? c:a,0,rm,&status);
        lo=ddop(ADD,lo,zz,0,rm,&status);
    } else {
        U q=ddop(SUB,a,z,0,rm,&status);
        U zz=ddop(ADD,q,c,0,rm,&status);
        q=ddop(ADD,q,z,0,rm,&status);
        q=ddop(SUB,q,a,0,rm,&status)^((U)1<<63);
        zz=ddop(ADD,zz,q,0,rm,&status);
        zz=ddop(ADD,zz,aa,0,rm,&status);
        zz=ddop(ADD,zz,cc,0,rm,&status);
        if(zz==0) return z; /* APFloat returns opOK here, intentionally. */
        hi=ddop(ADD,z,zz,0,rm,&status);
        if(ddcat(hi)!=FINITE && ddcat(hi)!=3) { *flags|=status;return hi; }
        lo=ddop(SUB,z,hi,0,rm,&status);
        lo=ddop(ADD,lo,zz,0,rm,&status);
    }
    *flags|=status;return hi|(lo<<64);
}
static U ddmul(U x,U y,int rm,int *flags) {
    int xc=ddcat(x),yc=ddcat(y);
    if(xc==NANV || yc==NANV || (xc==3 && yc==INF) || (xc==INF && yc==3)) return nanbits(formats[3]);
    if(xc==3 || xc==INF) return x;
    if(yc==3 || yc==INF) return y;
    U a=low64(x),b=x>>64,c=low64(y),d=y>>64;
    U t=ddop(MUL,a,c,0,rm,flags);
    if(ddcat(t)!=FINITE) return t;
    U tau=ddop(FMA,a,c,t^((U)1<<63),rm,flags);
    U v=ddop(MUL,a,d,0,rm,flags),w=ddop(MUL,b,c,0,rm,flags);
    v=ddop(ADD,v,w,0,rm,flags);tau=ddop(ADD,tau,v,0,rm,flags);
    U hi=ddop(ADD,t,tau,0,rm,flags),lo=0;
    if(ddcat(hi)==FINITE || ddcat(hi)==3) {
        lo=ddop(SUB,t,hi,0,rm,flags);lo=ddop(ADD,lo,tau,0,rm,flags);
    }
    return hi|(lo<<64);
}
static void ppc_eval(U *out,int op,const U *in,int extra,int rm) {
    out[0]=out[1]=out[2]=0;int flags=0;
    U x=in[0],y=in[1],r=0;
    const U neg=((U)1<<63)|((U)1<<127);
    if(op==ADD || op==SUB || op==MUL) {
        r=op==MUL ? ddmul(x,y,rm,&flags):op==ADD ? ddadd(x,y,rm,&flags):ddadd(x^neg,y,rm,&flags)^neg;
        if(ddcat(r)==NANV) r=nanbits(formats[3]);
        out[0]=r;out[2]=flags;return;
    }
    if(op==CONVERT) {
        out[0]=pack(sum_value(sum_read(x)),formats[extra],rm,&flags);out[2]=flags;return;
    }
    if(op==FPTOSI || op==FPTOUI || (op>=LROUND && op<=LLRINT)) {
        int mode=op==FPTOSI || op==FPTOUI ? 3:op<=LLROUND ? 4:rm;
        out[0]=ppc_sum_integer(x,extra,op!=FPTOUI,mode,op!=LROUND && op!=LLROUND,&flags);
        out[2]=flags;return;
    }
    if(op>=FLOOR && op<=NEARBYINT) {
        out[0]=ppc_sum_integral(x,op,rm,&flags);out[2]=flags;return;
    }
    if(op==SQRT) {
        out[0]=ppc_sum_sqrt(x,rm,&flags);out[2]=flags;return;
    }
    if(op==SITOFP || op==UITOFP) {
        unsigned char bytes[16];
        for(int i=0;i<16;++i)bytes[i]=(unsigned char)(x>>(8*i));
        out[0]=ppc_sum_fromwide(bytes,128,op==SITOFP,rm,&flags);out[2]=flags;return;
    }
    if(op==MODF) {
        int cat=ddcat(x);U hi=low64(x),lo=x>>64;
        if(cat==NANV){out[0]=out[1]=nanbits(formats[3]);return;}
        if(cat==INF){out[0]=hi&((U)1<<63);out[1]=hi;return;}
        if(cat==3){out[0]=out[1]=hi;return;}
        int ignored=0;
        U ih=ddop(TRUNC,hi,0,0,0,&ignored),il=ddop(TRUNC,lo,0,0,0,&ignored);
        U fh=ddop(SUB,hi,ih,0,0,&ignored),fl=ddop(SUB,lo,il,0,0,&ignored);
        U fraction=ddadd(fh,fl,0,&ignored),whole=ddadd(ih,il,0,&ignored);
        if(ddcat(fraction)==FINITE && ((fraction^hi)>>63&1)) {
            U unit=0x3ff0000000000000ULL|(hi&((U)1<<63));
            fraction=ddadd(fraction,unit,0,&ignored);
            whole=ddadd(whole,unit^((U)1<<63),0,&ignored);
        }
        if(ddcat(fraction)==3)fraction=hi&((U)1<<63);
        if(ddcat(whole)==3)whole=hi&((U)1<<63);
        out[0]=fraction;out[1]=whole;return;
    }
    if(op==POWI) {
        unsigned n=extra<0 ? 0u-(unsigned)extra:(unsigned)extra;
        r=0x3ff0000000000000ULL;
        while(n) {if(n&1)r=ddmul(r,x,rm,&flags);n>>=1;if(n)x=ddmul(x,x,rm,&flags);}
        if(extra<0) {U args[3]={0x3ff0000000000000ULL,r,0},rr[3];ppc_eval(rr,DIV,args,0,rm);r=rr[0];flags|=(int)rr[2];}
        out[0]=ddcat(r)==NANV ? nanbits(formats[3]):r;out[2]=flags;return;
    }
    if(op==CANONICALIZE) { out[0]=ddcat(x)==NANV ? nanbits(formats[3]):x;return; }
    if(op==CMP) {
        V a=unpack(low64(x),formats[3]),b=unpack(low64(y),formats[3]);
        int u=a.kind==NANV || b.kind==NANV,d=u ? 0:compare(a,b);
        if(!u && d==0) {a=unpack(x>>64,formats[3]);b=unpack(y>>64,formats[3]);u=a.kind==NANV || b.kind==NANV;d=u ? 0:compare(a,b);}
        int p=extra&7;
        int v=p==0 ? 0:p==1 ? d==0:p==2 ? d>0:p==3 ? d>=0:p==4 ? d<0:p==5 ? d<=0:p==6 ? d!=0:1;
        out[0]=u ? extra>=8:extra==15 || v;out[2]=a.snan || b.snan;return;
    }
    if(op==ISFPCLASS) {
        V hi=unpack(low64(x),formats[3]),lo=unpack(x>>64,formats[3]);
        U args[3]={low64(x),0,0};bennett_sf_eval(out,3,op,args,extra,rm);
        if(hi.kind==FINITE && hi.mag) {
            int ignored=0;U sum=ddop(ADD,low64(x),x>>64,0,0,&ignored);
            int denormal=width(hi.mag)<53 || (lo.kind==FINITE && lo.mag && width(lo.mag)<53) || sum!=low64(x);
            int cls=denormal ? (hi.sign ? 4:7):(hi.sign ? 3:8);out[0]=(extra>>cls)&1;
        }
        return;
    }
    if(op>=MINNUM && op<=MAXIMUMNUM) {
        int an=ddcat(x)==NANV,bn=ddcat(y)==NANV;
        if(an || bn) r=(op==MINIMUM || op==MAXIMUM || (an && bn)) ? nanbits(formats[3]):an ? y:x;
        else {
            U cmp[3];ppc_eval(cmp,CMP,in,4,rm);int less=(int)cmp[0];
            if(ddcat(x)==3 && ddcat(y)==3)less=(int)(x>>63)&1;
            r=(op&1) ? (less ? x:y):(less ? y:x);
        }
        out[0]=r;out[2]=unpack(low64(x),formats[3]).snan || unpack(low64(y),formats[3]).snan;return;
    }
    if(op==FREXP || op==LDEXP) {
        V hi=unpack(low64(x),formats[3]);int exponent=0;
        if(hi.kind==FINITE && hi.mag)exponent=width(hi.mag)+hi.exp;
        int scale=op==FREXP ? -exponent:extra>100000 ? 100000:extra< -100000 ? -100000:extra;
        V lo=unpack(x>>64,formats[3]);hi.exp+=scale;lo.exp+=scale;
        if(op==LDEXP && hi.kind==FINITE && hi.mag && width(hi.mag)+hi.exp-1<=-969) {
            out[0]=ppc_pack(add(hi,lo,rm),rm,&flags);out[2]=flags;return;
        }
        U h=pack(hi,formats[3],rm,&flags),l=pack(lo,formats[3],rm,&flags);
        out[0]=ddcat(h)==NANV ? nanbits(formats[3]):h|(l<<64);
        if(op==FREXP)out[1]=(U)(unsigned)exponent;
        out[2]=flags;return;
    }
    U args[3];
    for(int i=0;i<3;++i) args[i]=pack(ppc_unpack(in[i]),formats[7],0,&flags);
    bennett_sf_eval(out,7,op,args,extra,rm);
    out[0]=ppc_pack(unpack(out[0],formats[7]),0,&flags);
    out[2]|=flags;
}
