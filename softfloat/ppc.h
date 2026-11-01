/* PPCDoubleDouble contract adapter. The component algorithms follow LLVM
 * DoubleAPFloat (Apache-2.0 WITH LLVM-exception), using our integer f64 core.
 * High double occupies bits 0..63, low double bits 64..127.
 * Legacy fallbacks deliberately match APFloat, including sparse-tail loss.
 */
static U low64(U x) { return x & (((U)1<<64)-1); }
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
        U args[3]={low64(x),0,0};bennett_sf_eval(out,3,op,args,extra,rm);return;
    }
#if BENNETT_LLVM_MAJOR >= 23
    if(op>=FLOOR && op<=NEARBYINT) {
        int mode=op==FLOOR ? 1:op==CEIL ? 2:op==TRUNC ? 3:op==ROUND ? 4:op==ROUNDEVEN ? 0:rm;
        U hi=low64(x),lo=x>>64, rh=ddop(RINT,hi,0,0,mode,&flags),rl=0;
        if(ddcat(hi)==FINITE && (lo & (((U)1<<63)-1))) {
            if(rh!=hi) {
                if(mode==0 || mode==4) {
                    int ignored=0;
                    U err=ddop(SUB,rh,hi,0,0,&ignored);
                    if(low64(err & ~((U)1<<63))==0x3fe0000000000000ULL && ((err^lo)>>63&1))
                        rh=ddop(ADD,rh,0x3ff0000000000000ULL|(lo&((U)1<<63)),0,0,&ignored);
                }
            } else {
                flags=0;int lm=mode==3 ? ((hi>>63) ? 2:1):mode;
                rl=ddop(RINT,lo,0,0,lm,&flags);
                if(lm==4) {
                    int ignored=0;U err=ddop(SUB,rl,lo,0,0,&ignored);
                    if((err & ~((U)1<<63))==0x3fe0000000000000ULL && ((err^hi)>>63&1))
                        rl=ddop(ADD,rl,0x3ff0000000000000ULL|(hi&((U)1<<63)),0,0,&ignored);
                }
                int ignored=0;U sum=ddop(ADD,rh,rl,0,0,&ignored);
                rl=ddop(SUB,rl,ddop(SUB,sum,rh,0,0,&ignored),0,0,&ignored);rh=sum;
            }
        }
        out[0]=ddcat(rh)==NANV ? nanbits(formats[3]):rh|(rl<<64);
        out[2]=op==NEARBYINT ? flags&~16:flags;return;
    }
#endif
    V a=ppc_unpack(x);
    if(op==CONVERT) {out[0]=pack(unpack(low64(x),formats[3]),formats[extra],rm,&flags);out[2]=flags;return;}
    U args[3];
    for(int i=0;i<3;++i) args[i]=pack(ppc_unpack(in[i]),formats[7],0,&flags);
    if(op==SITOFP || op==UITOFP) args[0]=x;
    bennett_sf_eval(out,7,op,args,extra,rm);
    if(!(op==FPTOSI || op==FPTOUI || (op>=LROUND && op<=LLRINT))) {
        out[0]=ppc_pack(unpack(out[0],formats[7]),0,&flags);
        if(op==MODF) out[1]=ppc_pack(unpack(out[1],formats[7]),0,&flags);
    }
    out[2]|=flags;
}
