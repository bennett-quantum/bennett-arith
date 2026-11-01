// Test-only reference to the contract's same-major LLVM implementation.
#include "llvm/ADT/APFloat.h"
#include "llvm/ADT/APInt.h"
#include "llvm/ADT/APSInt.h"
#include <iostream>
#include <iomanip>
using namespace llvm;
int main() {
  unsigned op, rm; uint64_t a,b,c,d,e,f;
  APFloat::roundingMode modes[]={APFloat::rmNearestTiesToEven,APFloat::rmTowardNegative,APFloat::rmTowardPositive,APFloat::rmTowardZero,APFloat::rmNearestTiesToAway};
  while(std::cin>>std::dec>>op>>rm>>std::hex>>a>>b>>c>>d>>e>>f) {
    uint64_t x[]={a,b}, y[]={c,d}, z[]={e,f};
    APFloat v(APFloat::PPCDoubleDouble(), APInt(128,x));
    APFloat w(APFloat::PPCDoubleDouble(), APInt(128,y));
    APFloat t(APFloat::PPCDoubleDouble(), APInt(128,z));
    bool lost=false;
    switch(op) {
      case 0:v.add(w,modes[rm]);break;
      case 1:v.subtract(w,modes[rm]);break;
      case 2:v.multiply(w,modes[rm]);break;
      case 3:v.divide(w,modes[rm]);break;
      case 4:v.mod(w);break;
      case 5:v.fusedMultiplyAdd(w,t,modes[rm]);break;
      case 6:v.roundToIntegral(modes[rm]);break;
      case 7:v.convert(APFloat::IEEEquad(),modes[rm],&lost);break;
      case 8:v=APFloat(APFloat::IEEEquad(),APInt(128,x));v.convert(APFloat::PPCDoubleDouble(),modes[rm],&lost);break;
      case 9:std::cout<<std::hex<<unsigned(v.compare(w))<<" 0\n";continue;
      case 10:case 11:v.convertFromAPInt(APInt(128,x),op==10,modes[rm]);break;
      case 12:case 13: {
        APSInt n(128,op==13);bool exact;
        v.convertToInteger(n,APFloat::rmTowardZero,&exact);
        std::cout<<std::hex<<n.getRawData()[0]<<" "<<n.getRawData()[1]<<"\n";continue;
      }
      case 14:std::cout<<std::hex<<unsigned(v.classify())<<" 0\n";continue;
      default:return 2;
    }
    APInt bits=v.bitcastToAPInt();
    if(v.isNaN()) { v=APFloat::getQNaN(v.getSemantics());bits=v.bitcastToAPInt(); }
    std::cout<<std::hex<<bits.getRawData()[0]<<" "<<bits.getRawData()[1]<<"\n";
  }
}
