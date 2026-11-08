"""Exercise scripts/test preparation with real publications and a focused probe.

The fixture replaces the suite body with one exact rounding assertion to avoid
recursion. The runner, generators, bitcode, bridge and compiler are real.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from time_guard import run as guarded_run, output as guarded_output
LLVM = Path("/usr/lib/llvm-18/bin")
PROBE = '''import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tests"))
from test_edge import Edge
actual = Edge(18, root).call("tanh_f16_rm", 0x54e0, 1)
print(f"observed {actual[0]:#06x}", flush=True)
assert actual == (0x3bff, 0), actual
'''


class DefaultPreparation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("scripts/test", "scripts/time_guard.py", "tests/timeouts.toml", "softfloat/generate.py", "softfloat/constants.py",
                     "dist/llvm18/bennett-arith.bc", "dist/llvm18/manifest.json",
                     "tests/test_edge.py"):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        (self.root / "tests/test_default.py").write_text(PROBE)
        self.work = self.root / ".tmp/llvm18"

    def default_run(self):
        return guarded_run([str(self.root / "scripts/test")], capture_output=True,
                              text=True, guard_class="moderate")

    def test_changed_publication_cannot_pass_with_previous_bridge(self):
        first = self.default_run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        bc = self.root / "dist/llvm18/bennett-arith.bc"
        ir = guarded_output([str(LLVM / "llvm-dis"), str(bc), "-o", "-"],
                                     text=True, guard_class="moderate")
        # Deliberately return 1 instead of its predecessor for this downward
        # tanh case, retaining the ABI and every other published definition.
        pattern = r"(define i16 @__bennett_sf_tanh_f16_rm\([^\n]*\) \{\n).*?^}"
        broken, count = re.subn(pattern, r"\g<1>  ret i16 15360\n}", ir, flags=re.M | re.S)
        self.assertEqual(count, 1)
        guarded_run([str(LLVM / "llvm-as"), "-o", str(bc)], input=broken,
                       text=True, check=True, guard_class="moderate")
        dist = bc.parent
        manifest = dist / "manifest.json"
        data = json.loads(manifest.read_text())
        data["bitcode_sha256"] = hashlib.sha256(bc.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        (dist / "SHA256SUMS").write_text("".join(
            hashlib.sha256((dist / name).read_bytes()).hexdigest() + "  " + name + "\n"
            for name in ("bennett-arith.bc", "manifest.json")))
        second = self.default_run()
        self.assertNotEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("observed 0x3c00", second.stdout)

    def test_support_sources_and_missing_outputs_are_refreshed(self):
        first = self.default_run()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        for source, output, marker in (("generate.py", "bridge.ll", "; fresh bridge"),
                                       ("constants.py", "constants.h", "/* fresh constants */")):
            path = self.root / "softfloat" / source
            with path.open("a") as stream:
                stream.write(f'\nwith open(pathlib.Path(sys.argv[1]) / {output!r}, "a") as out:\n'
                             f'    out.write({marker!r} + "\\n")\n')
        (self.work / "bridge.ll").write_text("invalid cached IR\n")
        (self.work / "constants.h").unlink()
        second = self.default_run()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("; fresh bridge", (self.work / "bridge.ll").read_text())
        self.assertIn("/* fresh constants */", (self.work / "constants.h").read_text())
        # A failed rebuild must stop before the old, still-loadable library
        # reaches the suite body.
        (self.root / "dist/llvm18/bennett-arith.bc").write_bytes(b"invalid bitcode\n")
        failed = self.default_run()
        self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
        self.assertNotIn("observed", failed.stdout)
        self.assertIn("error:", failed.stderr)


if __name__ == "__main__":
    from time_guard import test_main
    test_main()
