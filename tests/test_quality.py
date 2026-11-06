"""Quality measurement and rejection of source regressions."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("quality",ROOT/"scripts/quality_metrics.py")
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

class Quality(unittest.TestCase):
    def test_product_has_no_process_identifiers(self):
        self.assertEqual(q.measure()["process_identifiers"],[])
    def test_no_tracked_litter(self):
        self.assertEqual(q.measure()["litter"],[])
    def test_nested_branch_and_wrapper_are_detected(self):
        baseline={"files":{"a.py":{"cognitive_mass":0,"trivial_wrappers":0}},"litter":[],"process_identifiers":[]}
        current={"files":{"a.py":{"cognitive_mass":2,"trivial_wrappers":1}},"litter":[],"process_identifiers":[]}
        errors=q.regressions(current,baseline)
        self.assertTrue(any("cognitive_mass" in e for e in errors))
        self.assertTrue(any("trivial_wrappers" in e for e in errors))
    def test_new_file_and_litter_are_detected(self):
        baseline={"files":{},"litter":[],"process_identifiers":[]}
        current={"files":{"new.py":{"functions":1}},"litter":["cache.pyc"],"process_identifiers":["new.py:1"]}
        self.assertEqual(len(q.regressions(current,baseline)),3)
    def test_python_decisions_and_forwarder(self):
        rows=q.python_functions("def f(x):\n    if x:\n        while x:\n            x-=1\n    return x\ndef g(x):\n    return f(x)\n")
        self.assertGreater(rows[0][1],1)
        self.assertEqual(rows[1][2],1)
    def test_c_decisions_ignore_comments_and_strings(self):
        rows=q.c_functions('static int f(int x) { /* if while */ if(x) { while(x) --x; } return x; }\n'
                           'static char *g(void) { return "if for"; }\n')
        self.assertEqual(len(rows),2)
        self.assertGreater(rows[0][1],1)
        self.assertEqual(rows[1][1],0)

if __name__=="__main__":unittest.main()
