"""Published objects and certificates: reproducible, accepted, every claim independently replayed."""
import hashlib
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import ANY, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import (RefInterp,
                     counts, parse, simulate, word)  # noqa: E402
from time_guard import run as guarded_run, seconds  # noqa: E402
from publication_receipts import Receipt, ReceiptState, report_receipts, select_publications  # noqa: E402
from adders.circuits import interpreter_view  # noqa: E402

REF = RefInterp()
DIR = ROOT / ".tmp/opus-arith-circuits/objects/published"
CHECK_GATE_LIMIT = 1500     # The debug binary's validation is quadratic in the body; larger
REPLAY_GATE_LIMIT = 200     # objects are checked out of band with a release build (progress file).
MANIFEST = json.loads((ROOT / "adders/objects/manifest.json").read_text())


RAW_RECEIPTS = {}


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
        fixtures = [(c.cuccaro(2).text(), [], None), (c.mulmod_const(4, 5, 11).text(), [0], None)]
        for entry in MANIFEST["entries"]:
            text = (ROOT / entry["file"]).read_text()
            fixtures.append((text, [0] if "qinplace" in text else [], entry["file"]))
        checked = 0
        for text, aliases, publication in fixtures:
            cert = certificate(text)
            self.assertEqual(cert["bindings"]["invocation"]["token_aliases"], aliases)
            for closure, region in cert["regions"].items():
                for claim in filter(lambda claim: "invocation" in claim, region["claims"]):
                    inv = claim["invocation"]
                    self.assertEqual(inv["token_aliases"], "all" if inv["args"] == "all" else aliases)
                for entry in region["verification"]["inverse_pairs"]:
                    self.assertEqual(entry["token_aliases"], [0])
                    self.assertEqual(region["claims"][entry["claim"]]["subject"]["closure_hash"], closure)
                    self.assertEqual(region["claims"][entry["claim"]]["expected"], "inverse_pair")
                    self.assertLessEqual(set(map(type, entry["budget"])), {int})
                    checked += publication is not None
        self.assertGreater(checked, 0, "published inverse-pair obligations must be nonempty")

    def test_receipt_guards(self):
        with redirect_stdout(StringIO()):
            entry = MANIFEST["entries"][0]
            admitted = REF.check(ROOT / entry["file"])
            verifier = Path("verifier")
            for stage in ("admission", "certificate replay"):
                error = subprocess.TimeoutExpired("synthetic guard", seconds("short"))
                with redirect_stdout(StringIO()) as output, patch.object(REF, "check", return_value=admitted,
                        side_effect=error if stage == "admission" else None), patch(__name__ + ".guarded_run", side_effect=error):
                    receipt = self._verify_publication(verifier, entry)
                self.assertEqual((receipt.state, receipt.claims), (ReceiptState.UNKNOWN, 0))
                self.assertIn("UNKNOWN:", output.getvalue())
                self.assertIn(stage, receipt.detail)
            with patch.object(REF, "check", return_value={"status": "invalid"}), self.assertRaises(AssertionError):
                self._verify_publication(verifier, entry)
            with patch.object(REF, "check", return_value=admitted), patch(__name__ + ".guarded_run") as replay:
                receipt = self._verify_publication(verifier, entry)
            self.assertEqual((receipt.state, receipt.claims), (ReceiptState.COMPLETE, 1))
            replay.assert_called_once_with([str(verifier), str(ROOT / entry["file"]), "1"], check=True, guard_class="long")
            for verdict in ("Rejected", "Unverified"):
                with patch.object(REF, "check", return_value=admitted), patch(__name__ + ".guarded_run",
                        side_effect=subprocess.CalledProcessError(1, "verifier", stderr=verdict)), self.assertRaises(subprocess.CalledProcessError):
                    self._verify_publication(verifier, entry)
            with patch.dict(MANIFEST, {"entries": []}), self.assertRaises(AssertionError):
                self.test_token_aliases()

    def test_manifest_is_current(self):
        done = subprocess.run([sys.executable, "-I", str(ROOT / "adders/generate.py"), "check"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
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
        RAW_RECEIPTS.clear()
        entries = select_publications(MANIFEST["entries"], os.environ.get("BENNETT_ARITH_RECEIPTS"))
        deps = Path(REF.binary).parent / "deps"
        libraries = list(deps.glob("libbennett_isa_ref-*.rlib"))
        self.assertEqual(len(libraries), 1, f"expected one pinned ISA reader library in {deps}")
        verifier = Path(os.environ["TMPDIR"]) / "verify-certificate"
        try:
            guarded_run(["rustc", "--edition=2021", str(Path(__file__).with_name("verify_certificate.rs")),
                        "--extern", f"bennett_isa_ref={libraries[0]}", "-L", f"dependency={deps}",
                        "-o", str(verifier)], check=True, guard_class="short")
        except subprocess.TimeoutExpired as error:
            message = f"UNKNOWN: certificate bridge compilation hang guard {error.timeout:.2f}s expired"
            print(message, flush=True)
            RAW_RECEIPTS.update((entry["root"], Receipt(ReceiptState.UNKNOWN, message, 0, 0.0))
                                for entry in entries)
            raise
        for entry in entries:
            RAW_RECEIPTS[entry["root"]] = Receipt(ReceiptState.FAILED, "validation did not complete", 0, 0.0)
            with self.subTest(publication=entry["file"]):
                RAW_RECEIPTS[entry["root"]] = self._verify_publication(verifier, entry)
        if any(receipt.state is ReceiptState.UNKNOWN for receipt in RAW_RECEIPTS.values()):
            raise subprocess.TimeoutExpired("publication receipts incomplete", seconds("long"))

    def _verify_publication(self, verifier, entry):
        path = ROOT / entry["file"]
        stage = "admission"
        started = time.monotonic()
        print(f"START: {entry['file']}", flush=True)
        try:
            got = REF.check(path, guard_class="long")
            self.assertEqual(got["status"], "ok", entry["file"])
            self.assertEqual(got["object_hash"], certificate(path.read_text())["bindings"]["object_hash"])
            if entry["root"] == "arith.add.cuccaro.w1":
                self.assertEqual(got["symbols"][entry["root"]]["interface_hash"],
                                 "0e350e9c21db62e93d801271076c0f77424fb2ca4f0986a856a8312102036dae")
            admission_end = time.monotonic()
            stage = "certificate replay"
            claims = sum(len(r["claims"]) for r in certificate(path.read_text())["regions"].values())
            guarded_run([str(verifier), str(path), str(claims)], check=True, guard_class="long")
        except subprocess.TimeoutExpired as error:
            message = (f"UNKNOWN: {entry['file']}: {stage} hang guard {error.timeout:.2f}s expired; "
                       f"{time.monotonic() - started:.2f}s wall; no complete receipt")
            print(message, flush=True)
            return Receipt(ReceiptState.UNKNOWN, message, 0, time.monotonic() - started)
        print(f"COMPLETE receipt: {entry['file']}: {claims} accepted claims; {time.monotonic() - started:.2f}s wall; "
              f"admission {admission_end - started:.2f}s; replay {time.monotonic() - admission_end:.2f}s", flush=True)
        return Receipt(ReceiptState.COMPLETE, entry["file"], claims, time.monotonic() - started)

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
        DIR.mkdir(parents=True, exist_ok=True)
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
    from time_guard import test_main
    try:
        program = test_main(exit=False, defaultTest="Published.test_raw_publications_admitted"
                            if "BENNETT_ARITH_RECEIPTS" in os.environ else None)
    finally:
        receipt_status = report_receipts(RAW_RECEIPTS)
    raise SystemExit(1 if not program.result.wasSuccessful() else receipt_status)
