"""Bounded default checks; exhaustive and both-major suites live in scripts/gate."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests/circuits")]
from harness import parse
from test_adders import verify
from test_objects import Published
from test_pins import Pins
from test_qrom import Qrom
from adders import constructions as A
from multipliers import constructions as M
from qrom import constructions as Q

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tests"/(name+".py"))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

class SmallCircuits(unittest.TestCase):
    def test_adders(self):
        for make in (A.cuccaro,A.gidney,A.ripple,A.qcla):
            for w in range(1,5):
                obj=make(w);fn=parse(obj.text())[0][obj.root];mask=(1<<w)-1
                target=fn.mut[-1][0]
                def expected(v):
                    if target=="b":return {"a":v["a"],"b":(v["a"]+v["b"])&mask}
                    return {target:v[target] ^ (v["a"]+v["b"])}
                verify(self,fn,expected,None)
    def test_multipliers(self):
        for make in (M.muladd_school,M.mul_school,M.muladd_karatsuba,M.mul_karatsuba):
            for w in (2,3,4):
                obj=make(w,2*w);fn=parse(obj.text())[0][obj.root]
                target=fn.mut[0][0]
                def expected(v):
                    product=v["a"]*v["b"]
                    return {target:(v[target]+product)%(1<<(2*w)) if "muladd" in fn.name else v[target]^product}
                verify(self,fn,expected,None)
    def test_qrom(self):
        for make,args in ((Q.qrom,()),(Q.select_swap,(1,)),(Q.select_swap_dirty,(1,))):
            data=(1,0,3,2);obj=make(data,2,2,*args)
            verify(self,parse(obj.text())[0][obj.root],lambda v:{"t":v["t"]^data[v["idx"]]},None)

class Numeric(unittest.TestCase):
    def test_basic_operations(self):
        e=module("test_edge");edge=e.Edge(18)
        for suffix,f in e.FORMATS.items():
            for op in ("add","sub","mul","div","sqrt","fma"):
                for a,b in ((e.Q(1),e.Q(3)),(e.power(1-f[3]),e.Q(2)),(e.Q(-3,2),e.Q(1,2))):
                    raw=[e.encode(a,f)[0]]
                    if op!="sqrt":raw.append(e.encode(b,f)[0])
                    if op=="fma":raw.append(e.encode(-a,f)[0])
                    for rm in range(5):
                        expected,flags=e.oracle(op,raw,f,rm)
                        edge.check(op+"_"+suffix+"_rm",[*raw,rm],expected,flags)
        self.assertEqual(edge.count,540)
    def test_directed(self):
        module("test_directed").run(18,quick=True)
    def test_review(self):
        module("test_review_numeric").run(18,ROOT,"all")
    def test_pair_parity(self):
        module("test_pair_parity").run(18)
    def test_named_overflow(self):
        module("test_named_overflow").run()
    def test_contract(self):
        # The script validates both publications, signatures and provenance.
        import runpy
        runpy.run_path(str(ROOT/"tests/test_contract.py"),run_name="__main__")

def suite():
    out=unittest.TestSuite()
    for cls in (SmallCircuits,Numeric,Pins):
        out.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    for name in ("test_manifest_is_current","test_reproduces_byte_for_byte",
                 "test_inverse_pair_obligation_is_published","test_token_aliases"):
        out.addTest(Published(name))
    out.addTest(Qrom("test_cli_single_word_table"))
    return out

if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(suite())
    raise SystemExit(not result.wasSuccessful())
