/* Phase invariants for the integer elementary evaluator. */
#include <assert.h>
#include BENNETT_CORE

static U raw(int n) {
    int flags=0;
    return pack(ti(n),formats[3],0,&flags);
}
static void test_domain(void) {
    U in[3]={raw(3),0,0};
    assert(trans_domain(3,EXP2,in).path==TRANS_EXACT);
    in[0]=raw(100);
    assert(trans_domain(3,TANH,in).path==TRANS_TANH_LIMIT);
    in[0]=raw(0);
    assert(trans_domain(6,EXP,in).path==TRANS_PPC_EXP);
    in[0]=((U)854<<52); /* binary64 2^-169 */
    assert(trans_domain(3,TAN,in).path==TRANS_LINEAR);
    in[0]=raw(2);
    assert(trans_domain(3,ASIN,in).path==TRANS_CORE);
}
static void test_core(void) {
    U in[3]={0};
    TransState state=trans_domain(3,SINCOS,in);
    trans_core(&state,SINCOS);
    assert(state.r.kind==FINITE && !state.r.mag);
    assert(compare(state.c,ti(1))==0);
    in[0]=raw(2);state=trans_domain(3,ASIN,in);
    trans_core(&state,ASIN);
    assert(state.r.kind==NANV);
}
static void test_pack(void) {
    U in[3]={raw(1),0,0},out[3];
    TransState state=trans_domain(3,LOG,in);
    trans_core(&state,LOG);trans_pack(out,3,LOG,0,state);
    assert(out[0]==0 && out[1]==0 && out[2]==0);
    in[0]=0;state=trans_domain(3,ACOS,in);
    trans_core(&state,ACOS);trans_pack(out,3,ACOS,0,state);
    assert(out[0]!=0 && out[2]==16);
    in[0]=raw(2);state=trans_domain(3,ASIN,in);
    trans_core(&state,ASIN);trans_pack(out,3,ASIN,0,state);
    assert(out[0]==nanbits(formats[3]) && out[2]==1);
    in[0]=raw(-100000);state=trans_domain(3,EXP,in);
    trans_core(&state,EXP);trans_pack(out,3,EXP,2,state);
    assert(out[0]==1 && out[2]==24);
}
static void test_exactness_table(void) {
    int zero_ops[]={SIN,COS,TAN,ASIN,ATAN,SINH,COSH,TANH,EXP,SINCOS};
    for(unsigned i=0;i<sizeof(zero_ops)/sizeof(*zero_ops);++i)
        assert(trans_is_exact(zero_ops[i],ti(0),ti(0),ti(0)));
    assert(trans_is_exact(LOG,ti(1),ti(0),ti(0)));
    assert(trans_is_exact(ACOS,ti(1),ti(0),ti(0)));
    assert(!trans_is_exact(ACOS,ti(0),ti(0),tc_pi()));
    V inf={0,0,0,INF,0};
    assert(trans_is_exact(TANH,inf,ti(0),ti(1)));
    assert(!trans_is_exact(ATAN,inf,ti(0),tc_pi()));
    assert(trans_is_exact(POW,ti(2),inf,inf));
}
int main(void) {
    test_domain();test_core();test_pack();test_exactness_table();
}
