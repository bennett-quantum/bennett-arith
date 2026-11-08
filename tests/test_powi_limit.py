"""The generator accepts LLVM's inclusive i8388608 maximum without narrowing."""
import importlib.util,pathlib,subprocess,sys
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('generator',R/'softfloat/generate.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
rows=list(g.powi_entries([8388608]));assert len(rows)==14
row=next(r for r in rows if r['fi']==5 and r['constrained'])
ir='declare i128 @__bennett_sf_mul_f128_rm(i128,i128,i32)\ndeclare i128 @__bennett_sf_div_f128_rm(i128,i128,i32)\n'+'\n'.join(g.powi_wrapper(row))+'\n'
assert 'i8388608 %a1' in ir and 'lshr i8388608 %n, 1' in ir
p=R/'.tmp/powi-limit.ll'
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(ir)
for major in [18,23]:
    bc=R/f'.tmp/powi-limit-{major}.bc'
    subprocess.run([f'/usr/lib/llvm-{major}/bin/llvm-as',str(p),'-o',str(bc)],check=True)
    subprocess.run([f'/usr/lib/llvm-{major}/bin/opt','-passes=verify',str(bc),'-disable-output'],check=True)
    print(f'LLVM {major}: inclusive i8388608 powi carrier verifies')
