"""Only-needed IEEE comparisons must not retain the general arithmetic core.

This measures the producer's actual published bitcode before normalisation.
It does not transform an ISA object or claim equivalent consumer budgets.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
FORMATS=('f64','f16','bf16','f32','f128')

def run(major,root=ROOT):
    work=Path(os.environ['TMPDIR'])/'comparison-closure';work.mkdir(parents=True,exist_ok=True)
    llvm=Path(f'/usr/lib/llvm-{major}/bin')
    largest=0
    for fmt in FORMATS:
        for stem in ('cmp','cmp_rm','cmps_rm'):
            op,tag=('cmp','') if stem=='cmp' else (stem[:-3],'_rm')
            symbol=f'__bennett_sf_{op}_{fmt}{tag}'
            out=work/f'{major}-{stem}-{fmt}.bc'
            subprocess.run([str(llvm/'opt'),'-passes=internalize,globaldce',
                '-internalize-public-api-list='+symbol,
                str(root/f'dist/llvm{major}/bennett-arith.bc'),'-o',str(out)],check=True,timeout=60)
            ir=subprocess.check_output([str(llvm/'llvm-dis'),str(out),'-o','-'],text=True,timeout=60)
            definitions=set(re.findall(r'^define [^@\n]+@([^ (]+)',ir,re.M))
            assert definitions=={symbol},(major,symbol,'retained private arithmetic closure',len(definitions)-1,sorted(definitions-{symbol}))
            assert not re.search(r'\b(call|alloca|fadd|fsub|fmul|fdiv|fcmp)\b',ir),(major,symbol,'unexpected helper, scratch storage or FP instruction')
            if tag:
                assert '@__bennett_rt_fenv' in ir and 'store i32' in ir
            else:
                assert '@__bennett_rt_fenv' not in ir and not re.search(r'\b(load|store)\b',ir)
            largest=max(largest,out.stat().st_size)
    print(f'LLVM {major}: 15 IEEE comparison closures have zero private functions/scratch slots; largest bitcode {largest} bytes',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('majors',type=int,nargs='*',default=[18,23])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    for major in args.majors:run(major,args.root)
