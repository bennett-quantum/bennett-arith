"""Directed named-format overflow, checked against LLVM APFloat 23."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ["TMPDIR"])/"named-overflow"
WORK.mkdir(parents=True,exist_ok=True)
LLVM=Path("/usr/lib/llvm-23/bin")

def run():
    flags=subprocess.check_output([str(LLVM/"llvm-config"),"--cxxflags","--ldflags","--libs","support","--system-libs"],text=True).split()
    subprocess.run([str(LLVM/"clang++"),str(ROOT/"tests/named_oracle.cpp"),*flags,"-o",str(WORK/"oracle")],check=True,timeout=60)
    subprocess.run([str(LLVM/"clang"),"-std=c2x","-O0","-shared","-fPIC","-DBENNETT_LLVM_MAJOR=23",
                    "-I",str(ROOT/".tmp/llvm18"),str(ROOT/"softfloat/named.c"),"-o",str(WORK/"named.so")],check=True,timeout=90)
    lib=ctypes.CDLL(str(WORK/"named.so"))
    call=lib.bennett_sf_named
    call.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    # Finite overflow and values just beyond each maximal representable bin.
    cases=[(raw,fmt,rm) for raw in (0x501502f9,0xd01502f9,0x43fffffe,0xc3fffffe,
                                   0x47800000,0xc7800000,0x7f7fffff,0xff7fffff)
           for fmt in range(7) for rm in (1,2,3)
           if rm==3 or (rm==1 and raw>>31==0) or (rm==2 and raw>>31==1)]
    data="".join(f"{raw} {fmt} {rm}\n" for raw,fmt,rm in cases)
    expected=list(map(int,subprocess.check_output([str(WORK/"oracle")],input=data,text=True).split()))
    assert len(expected)==len(cases)
    for (raw,fmt,rm),want in zip(cases,expected):
        src=(ctypes.c_uint64*2)(raw,0);out=(ctypes.c_uint64*2)()
        call(out,2,fmt,1,src,rm,0)
        assert out[0]==want,(hex(raw),fmt,rm,hex(out[0]),hex(want))
    print(f"{len(cases)} named directed-overflow APFloat comparisons")

if __name__=="__main__":run()
