#!/usr/bin/env python3
"""Generate circuit objects: the published set, or any one instance for a consumer's build.

  python3 -I adders/generate.py publish            write objects and the manifest
  python3 -I adders/generate.py check              fail unless the tree matches a fresh build
  python3 -I adders/generate.py one FAMILY ARG...  print one object (table words: comma-separated)
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adders import constructions as A  # noqa: E402
from adders.circuits import OracleFn, QinplaceAction, census, jcs  # noqa: E402
from multipliers import constructions as M  # noqa: E402
from qrom import constructions as Q  # noqa: E402

ISA_SPEC_COMMIT = "ecaaac060c44e317d1181345fa6b8e38c096c099"
CERTIFICATE_EXTENSION_SPEC_COMMIT = "be109bd27889ea91e3c0ad78a30e5e4d71d3d0d3"
MANIFEST = ROOT / "adders/objects/manifest.json"
SOURCES = ["adders/circuits.py", "adders/constructions.py", "adders/generate.py", "adders/target-unit.json",
           "multipliers/constructions.py", "qrom/constructions.py"]

FAMILIES = {
    "add.cuccaro": A.cuccaro, "add.cuccaro_carry": A.cuccaro_carry, "add.ripple": A.ripple,
    "add.gidney": A.gidney, "add.qcla": A.qcla,
    "bij.add": A.add_in, "bij.addk": A.add_const, "bij.xor": A.xor_in, "bij.xork": A.xor_const,
    "bij.rotl": A.rotl_const, "bij.neg": A.negate, "bij.bswap": A.bswap,
    "bij.addmodk": A.addmod_const, "bij.addmod": A.addmod_in, "bij.mulmodk": A.mulmod_const,
    "muladd.school": M.muladd_school, "mul.school": M.mul_school,
    "muladd.karatsuba": M.muladd_karatsuba, "mul.karatsuba": M.mul_karatsuba, "mul.tree": M.mul_tree,
    "qrom": Q.qrom, "qrom.select_swap": Q.select_swap, "qrom.select_swap_dirty": Q.select_swap_dirty,
}
SAMPLE_4X8 = (0x13, 0xa7, 0x00, 0xff, 0x5c, 0x21, 0x9e, 0x74, 0x0b, 0xd2, 0x38, 0x66, 0xc1, 0x4f, 0x8a, 0xe9)
SAMPLE_3X2 = (2, 0, 3, 1, 1, 3, 0, 2)


def published():
    """(directory, family, args). Other instances come from `one`; they are deterministic."""
    small = (1, 2, 3, 4)
    words = (8, 16, 32, 64)
    out = []
    for family, widths in (("add.cuccaro", small + words + (128,)), ("add.cuccaro_carry", small + words + (128,)),
                           ("add.gidney", small + words + (128,)), ("add.ripple", (1, 2, 3) + words),
                           ("add.qcla", (1, 2, 3) + words),
                           ("bij.add", small + words + (128,)), ("bij.xor", small + words + (128,)),
                           ("bij.neg", small + words + (128,)), ("bij.bswap", (16, 32, 64, 128))):
        out += [("adders", family, (w,)) for w in widths]
    out += [("adders", "bij.addk", (8, 1)), ("adders", "bij.addk", (32, 1)), ("adders", "bij.addk", (64, 1)),
            ("adders", "bij.xork", (8, 0xff)), ("adders", "bij.rotl", (8, 3)), ("adders", "bij.rotl", (32, 7)),
            ("adders", "bij.addmodk", (4, 5, 11)), ("adders", "bij.addmodk", (8, 100, 251)),
            ("adders", "bij.addmod", (4, 11)), ("adders", "bij.addmod", (8, 251)),
            ("adders", "bij.mulmodk", (4, 5, 11)), ("adders", "bij.mulmodk", (8, 17, 251))]
    for W in (1, 2, 3, 4, 8, 16, 32):
        for family in ("muladd.school", "mul.school"):
            out.append(("multipliers", family, (W, 2 * W)))
            if W > 1:
                out.append(("multipliers", family, (W, W)))
    for W in (2, 4, 8, 16, 32):
        out += [("multipliers", "muladd.karatsuba", (W, 2 * W)), ("multipliers", "mul.karatsuba", (W, 2 * W))]
    for W in (2, 4, 8, 16):
        out.append(("multipliers", "mul.tree", (W,)))
    out += [("qrom", "qrom", (SAMPLE_3X2, 3, 2)), ("qrom", "qrom", (SAMPLE_4X8, 4, 8)),
            ("qrom", "qrom.select_swap", (SAMPLE_4X8, 4, 8, 2)),
            ("qrom", "qrom.select_swap_dirty", (SAMPLE_3X2, 3, 2, 1)),
            ("qrom", "qrom.select_swap_dirty", (SAMPLE_4X8, 4, 8, 2))]
    return out


def build():
    """Every published file's bytes and the manifest."""
    files = {}
    entries = []
    for directory, family, args in published():
        obj = FAMILIES[family](*args)
        text = obj.text()
        path = f"{directory}/objects/{obj.root}.bisa"
        if path in files:
            raise AssertionError(f"duplicate {path}")
        files[path] = text
        hashes = obj.hashes()
        symbols = {}
        cert = json.loads(text.rpartition("section certificate\n")[2])
        for c in obj.circuits:
            row = {"closure_hash": hashes[c.name], "kind": c.kind, "signature": c.signature()}
            if not isinstance(c, (OracleFn, QinplaceAction)):
                row["census"] = census(c)
            if not isinstance(c, OracleFn):
                row["claims"] = [claim.get("label", "unlabelled") + ":" + claim["kind"]
                                 for claim in cert["regions"][hashes[c.name]]["claims"]]
            symbols[c.name] = row
        entries.append({"args": [list(a) if isinstance(a, tuple) else a for a in args], "family": family,
                        "file": path, "inverse": obj.inverse, "root": obj.root,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(), "symbols": symbols})
    manifest = {"entries": entries, "isa": "0.9", "isa_spec_commit": ISA_SPEC_COMMIT,
                "certificate_extensions": {"K91": CERTIFICATE_EXTENSION_SPEC_COMMIT},
                "sources": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in SOURCES},
                "target_sha256": hashlib.sha256((ROOT / "adders/target-unit.json").read_bytes()).hexdigest()}
    files[str(MANIFEST.relative_to(ROOT))] = jcs(manifest) + "\n"
    return files


def main(argv):
    if len(argv) < 2 or argv[1] not in {"publish", "check", "one"}:
        raise SystemExit(__doc__)
    if argv[1] == "one":
        if len(argv) < 3 or argv[2] not in FAMILIES:
            raise SystemExit(f"family must be one of {sorted(FAMILIES)}")
        args = [tuple(int(w, 0) for w in a.split(","))
                if i == 0 and argv[2] in {"qrom", "qrom.select_swap", "qrom.select_swap_dirty"}
                else int(a, 0) for i, a in enumerate(argv[3:])]
        sys.stdout.write(FAMILIES[argv[2]](*args).text())
        return
    files = build()
    existing = {str(p.relative_to(ROOT)) for d in ("adders", "multipliers", "qrom")
                for p in (ROOT / d / "objects").glob("*") if p.is_file()}
    if argv[1] == "publish":
        for stale in existing - set(files):
            (ROOT / stale).unlink()
        for path, text in files.items():
            (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
            (ROOT / path).write_text(text)
        print(f"published {len(files)} files, {sum(len(t) for t in files.values())} bytes")
        return
    extra, missing = existing - set(files), set(files) - existing
    if extra or missing:
        raise SystemExit(f"published tree differs: extra {sorted(extra)} missing {sorted(missing)}")
    for path, text in files.items():
        if (ROOT / path).read_text() != text:
            raise SystemExit(f"{path} differs from a fresh build")
    print(f"reproduced {len(files)} files")


if __name__ == "__main__":
    main(sys.argv)
