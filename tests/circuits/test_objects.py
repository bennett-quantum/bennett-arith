"""Published objects and certificates: reproducible, accepted, every claim independently replayed."""
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import RefInterp, counts, parse, simulate, word  # noqa: E402
from adders.circuits import interpreter_view  # noqa: E402

REF = RefInterp()
DIR = ROOT / ".tmp/opus-arith-circuits/objects/published"
CHECK_GATE_LIMIT = 1500     # The debug binary's validation is quadratic in the body; larger
REPLAY_GATE_LIMIT = 200     # objects are checked out of band with a release build (progress file).
MANIFEST = json.loads((ROOT / "adders/objects/manifest.json").read_text())


def certificate(text):
    return json.loads(text.rpartition("section certificate\n")[2])


def xoshiro(seed):
    """Independent of the generator's: section 12.1's xoshiro256** and component draw."""
    s = [int(w) for w in seed]
    m = (1 << 64) - 1

    def rotl(v, k):
        return ((v << k) & m) | (v >> (64 - k))

    def word_():
        out = (rotl((s[1] * 5) & m, 7) * 9) & m
        t = (s[1] << 17) & m
        s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t
        s[3] = rotl(s[3], 45)
        return out

    def draw(width):
        v = 0
        for i in range((width + 63) // 64):
            v |= word_() << (64 * i)
        return v % (1 << width)
    return draw


class Published(unittest.TestCase):
    def test_token_aliases(self):
        from adders import constructions as c
        for obj, aliases in ((c.cuccaro(2), []), (c.mulmod_const(4, 5, 11), [0])):
            cert = certificate(obj.text())
            self.assertEqual(cert["bindings"]["invocation"]["token_aliases"], aliases)
            for closure, region in cert["regions"].items():
                for claim in region["claims"]:
                    if "invocation" in claim:
                        inv = claim["invocation"]
                        self.assertEqual(inv["token_aliases"], "all" if inv["args"] == "all" else aliases)
                for entry in region["verification"]["inverse_pairs"]:
                    self.assertEqual(entry["token_aliases"], [0])
                    self.assertEqual(region["claims"][entry["claim"]]["subject"]["closure_hash"], closure)

    def test_reproduces_byte_for_byte(self):
        done = subprocess.run([sys.executable, "-I", str(ROOT / "adders/generate.py"), "check"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_manifest_is_current(self):
        m = MANIFEST
        for source, digest in m["sources"].items():
            self.assertEqual(hashlib.sha256((ROOT / source).read_bytes()).hexdigest(), digest, source)
        for e in m["entries"]:
            self.assertEqual(hashlib.sha256((ROOT / e["file"]).read_bytes()).hexdigest(), e["sha256"], e["file"])

    def test_pinned_interpreter_diagnostic_view(self):
        DIR.mkdir(parents=True, exist_ok=True)
        checked = 0
        for e in MANIFEST["entries"]:
            text = (ROOT / e["file"]).read_text()
            if "qinplace" in text:
                continue    # The unconditional raw admission test validates these certificates.
            if sum(row.get("census", {}).get("gates", {}).get(g, 0) for row in e["symbols"].values()
                   for g in ("x", "cx", "ccx", "swap")) > CHECK_GATE_LIMIT:
                continue
            path = DIR / f"{e['root']}.bisa"
            path.write_text(interpreter_view(text))
            got = REF.check(path)
            self.assertEqual(got["status"], "ok", e["file"])
            cert = certificate(text)
            self.assertEqual(got["object_hash"], cert["bindings"]["object_hash"], e["file"])
            for name, row in e["symbols"].items():
                self.assertEqual(got["symbols"][name]["closure_hash"], row["closure_hash"], (e["file"], name))
            if e["root"] == "arith.add.cuccaro.w1":
                cases = [([0,0],[]),([0,1],[]),([1,0],[]),([1,1],[])]
                self.assertEqual(REF.many(path, e["root"], cases),
                                 [([0,0],[]),([0,1],[]),([1,1],[]),([1,0],[])])
            checked += 1
        self.assertGreater(checked, 80)

    def test_raw_publications_admitted(self):
        """Admit raw bytes and replay every claim/table with the pinned reader."""
        deps = Path(REF.binary).parent / "deps"
        libraries = list(deps.glob("libbennett_isa_ref-*.rlib"))
        self.assertEqual(len(libraries), 1, f"expected one pinned ISA reader library in {deps}")
        verifier = Path(os.environ["TMPDIR"]) / "verify-certificate"
        subprocess.run(["rustc", "--edition=2021", str(Path(__file__).with_name("verify_certificate.rs")),
                        "--extern", f"bennett_isa_ref={libraries[0]}", "-L", f"dependency={deps}",
                        "-o", str(verifier)], check=True, timeout=60)
        for entry in MANIFEST["entries"]:
            with self.subTest(publication=entry["file"]):
                self._verify_publication(verifier, entry)

    def _verify_publication(self, verifier, entry):
        path = ROOT / entry["file"]
        stage = "admission"
        started = time.monotonic()
        print(f"START: {entry['file']}", flush=True)
        try:
            got = REF.check(path)
            self.assertEqual(got["status"], "ok", entry["file"])
            self.assertEqual(got["object_hash"], certificate(path.read_text())["bindings"]["object_hash"])
            if entry["root"] == "arith.add.cuccaro.w1":
                self.assertEqual(got["symbols"][entry["root"]]["interface_hash"],
                                 "0e350e9c21db62e93d801271076c0f77424fb2ca4f0986a856a8312102036dae")
            stage = "certificate replay"
            claims = sum(len(r["claims"]) for r in certificate(path.read_text())["regions"].values())
            subprocess.run([str(verifier), str(path), str(claims)], check=True, timeout=600)
        except subprocess.TimeoutExpired as error:
            message = (f"INCOMPLETE: {entry['file']}: {stage} timed out at {error.timeout}s; "
                       f"{time.monotonic() - started:.2f}s wall; no complete receipt")
            print(message, flush=True)
            self.fail(message)

    def test_inverse_pair_obligation_is_published(self):
        checked = 0
        for entry in MANIFEST["entries"]:
            text = (ROOT / entry["file"]).read_text()
            if "qinplace" not in text:
                continue
            for region in certificate(text)["regions"].values():
                for pair in region["verification"]["inverse_pairs"]:
                    self.assertEqual(region["claims"][pair["claim"]]["expected"], "inverse_pair")
                    self.assertTrue(all(isinstance(n, int) for n in pair["budget"]))
                    checked += 1
        self.assertGreater(checked, 0)

    def test_certificates_tell_the_truth(self):
        """Census, frame, labels and every table row, replayed on the emitted text, not the builder."""
        m = MANIFEST
        target = hashlib.sha256((ROOT / "adders/target-unit.json").read_bytes()).hexdigest()
        proofs = evidence = rows = 0
        for e in m["entries"]:
            text = (ROOT / e["file"]).read_text()
            cert = certificate(text)
            self.assertEqual(cert["bindings"]["target_hash"], target)
            base = text.partition("\n\nsection certificate\n")[0] + "\n"
            self.assertEqual(hashlib.sha256(base.encode()).hexdigest(), cert["bindings"]["object_hash"], e["file"])
            fns, _ = parse(text)
            for name, row in e["symbols"].items():
                if row["kind"] == "oracle":
                    continue
                region = cert["regions"][row["closure_hash"]]
                fn = fns[name]
                self.assertEqual(region["signature"], row["signature"])
                if "qinplace" not in text:
                    got = counts(fn)
                    self.assertEqual(int(region["resources"]["t"]), got["t_total"], name)
                    self.assertEqual(sum(s["width"] for s in region["frame"]["scratch"]), got["ancilla"], name)
                    for gate, usage in region["gates_used"].items():
                        self.assertEqual(usage["count"], got[gate], (name, gate))
                claim = region["claims"][0]
                bits = sum(c["width"] for c in claim["domain"]["bundles"] + claim["domain"]["borrowed"])
                table = claim["expected"]["table"]
                if claim["kind"] == "exhaustive":
                    self.assertEqual(claim["label"], "proof", name)
                    self.assertEqual(len(table), 1 << bits, name)
                    proofs += 1
                else:
                    self.assertEqual(claim["kind"], "sampled")
                    self.assertEqual(claim["label"], "evidence", name)
                    self.assertLess(claim["sampler"]["count"], 1 << bits)
                    draw = xoshiro(claim["sampler"]["seed"])
                    widths = [c["width"] for c in claim["domain"]["bundles"] + claim["domain"]["borrowed"]]
                    drawn = {tuple(draw(w) for w in widths) for _ in range(claim["sampler"]["count"])}
                    listed = [tuple(int(v) for v in r["before"]["bundles"] + r["before"]["borrowed"]) for r in table]
                    self.assertEqual(listed, sorted(drawn), name)
                    evidence += 1
                if "qinplace" in text:
                    continue
                rows += self._replay(fn, claim, name)
        self.assertGreater(proofs, 40)
        self.assertGreater(evidence, 60)
        self.assertGreater(rows, 4000)

    def _replay(self, fn, claim, name):
        table = claim["expected"]["table"]
        lanes = len(table)
        components = [(c["name"], c["width"]) for c in claim["domain"]["bundles"]]
        dirty = [(c["name"], c["width"]) for c in claim["domain"]["borrowed"]]
        self.assertEqual(components, fn.mut + fn.ins, name)

        def column(values, width):
            out = [0] * width
            for lane, v in enumerate(values):
                for i in range(width):
                    out[i] |= ((v >> i) & 1) << lane
            return out
        values = {}
        for j, (n, w) in enumerate(components):
            values[n] = column([int(r["before"]["bundles"][j]) for r in table], w)
        for j, (n, w) in enumerate(dirty):
            values[n] = column([int(r["before"]["borrowed"][j]) for r in table], w)
        store = simulate(fn, values, lanes)
        for j, (n, w) in enumerate(components):
            self.assertEqual(word(store, n, w), column([int(r["after"]["bundles"][j]) for r in table], w), (name, n))
        for j, (n, w) in enumerate(dirty):
            self.assertEqual(word(store, n, w), column([int(r["after"]["borrowed"][j]) for r in table], w), (name, n))
        return lanes

    def test_interpreter_replays_table_rows(self):
        """Diagnostic compatibility replay; raw admission is independently mandatory."""
        m = MANIFEST
        replayed = 0
        for e in m["entries"]:
            text = (ROOT / e["file"]).read_text()
            if "qinplace" in text or "qborrow" in text:
                continue
            cert = certificate(text)
            fns, _ = parse(text)
            for name, row in e["symbols"].items():
                fn = fns[name]
                if len(fn.gates()) > REPLAY_GATE_LIMIT:
                    continue
                path = DIR / f"{e['root']}.bisa"
                path.write_text(interpreter_view(text))
                table = cert["regions"][row["closure_hash"]]["claims"][0]["expected"]["table"][:8]
                split = len(fn.mut)
                cases = [([int(v) for v in r["before"]["bundles"][:split]],
                          [int(v) for v in r["before"]["bundles"][split:]]) for r in table]
                for r, got in zip(table, REF.many(path, name, cases)):
                    self.assertEqual([str(v) for v in got[0] + got[1]], r["after"]["bundles"], name)
                replayed += len(cases)
        self.assertGreater(replayed, 300)


if __name__ == "__main__":
    unittest.main()
