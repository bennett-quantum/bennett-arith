// LLVM APFloat is an independent oracle for named-format overflow.
#include <llvm/ADT/APFloat.h>
#include <llvm/ADT/APInt.h>
#include <iostream>
using llvm::APFloat;
int main() {
    const llvm::fltSemantics *formats[] = {
        &APFloat::Float8E5M2(), &APFloat::Float8E5M2FNUZ(),
        &APFloat::Float8E4M3(), &APFloat::Float8E4M3FN(),
        &APFloat::Float8E4M3FNUZ(), &APFloat::Float8E4M3B11FNUZ(),
        &APFloat::Float8E3M4()
    };
    const APFloat::roundingMode modes[] = {
        APFloat::rmNearestTiesToEven, APFloat::rmTowardNegative,
        APFloat::rmTowardPositive, APFloat::rmTowardZero,
        APFloat::rmNearestTiesToAway
    };
    unsigned raw, fmt, mode;
    while (std::cin >> raw >> fmt >> mode) {
        if (fmt >= 7 || mode >= 5) return 2;
        APFloat value(APFloat::IEEEsingle(), llvm::APInt(32, raw));
        bool loses;
        value.convert(*formats[fmt], modes[mode], &loses);
        std::cout << value.bitcastToAPInt().getZExtValue() << '\n';
    }
}
