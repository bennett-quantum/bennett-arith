"""Adders and the dialect's library bijections: exhaustive, randomised, costed, differential."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import Lanes, RefInterp, VECTOR_ABOVE, counts, depths, pack_word, parse, simulate, tobits, word  # noqa: E402
from adders import constructions as C  # noqa: E402
from adders.circuits import Circuit, Object, write_object  # noqa: E402

EXHAUSTIVE = range(1, 11)
RANDOM = (11, 16, 32, 64, 128, 256)
REF = RefInterp()


def popcount(n):
    return bin(n).count("1")


def verify(case, fn, spec, W_of, exhaustive=True, lanes=4096, controls=(False, True)):
    """Check every bundle after fn against spec on all inputs, with and without ctl."""
    widths = dict(fn.mut + fn.ins)
    if exhaustive and sum(widths.values()) > 24:
        exhaustive = False
    domain = Lanes(widths, exhaustive=exhaustive, count=lanes)
    n = domain.count
    if n > VECTOR_ABOVE:
        # Numpy-vectorised specs (arithmetic operators only) on uint64 lanes.
        arrays = {name: domain.array(name) for name in widths}
        out = spec(arrays)
        expected = {name: pack_word(out[name], w) for name, w in fn.mut}
    else:
        named = {name: domain.values(name) for name in widths}
        rows = {name: [] for name, _ in fn.mut}
        for i in range(n):
            out = spec({name: named[name][i] for name in widths})
            for name in rows:
                rows[name].append(out[name])
        expected = {name: tobits(rows[name], w, n) for name, w in fn.mut}
    for ctl in controls:
        mask = None
        values = {k: list(v) for k, v in domain.bits.items()}
        if ctl:
            # One extra inherited control: half of the lanes off (exhaustive), random otherwise.
            from random import Random
            mask = Random(7).getrandbits(n)
        store = simulate(fn, values, n, control=mask)
        full = (1 << n) - 1
        for name, w in fn.ins:
            case.assertEqual(word(store, name, w), domain.bits[name], f"{fn.name}: in {name} changed")
        for name, w in fn.mut:
            want = expected[name]
            if mask is not None:
                want = [(a & mask) | (b & (full ^ mask)) for a, b in zip(want, domain.bits[name])]
            case.assertEqual(word(store, name, w), want, f"{fn.name}: mut {name} wrong ctl={ctl}")


class AdderFamilies(unittest.TestCase):
    def check_family(self, make, spec, widths=EXHAUSTIVE, random=RANDOM):
        for W in widths:
            obj = make(W)
            fns, _ = parse(obj.text())
            verify(self, fns[obj.root], spec(W), W, exhaustive=True)
        for W in random:
            obj = make(W)
            fns, _ = parse(obj.text())
            verify(self, fns[obj.root], spec(W), W, exhaustive=False)

    def test_cuccaro(self):
        def spec(W):
            return lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W)}
        self.check_family(C.cuccaro, spec)

    def test_cuccaro_cost(self):
        for W in range(1, 65):
            obj = C.cuccaro(W)
            got = counts(parse(obj.text())[0][obj.root])
            self.assertEqual(got.get("ccx", 0), 2 * W - 3 if W >= 2 else 0, W)
            self.assertEqual(got["t_total"], 7 * (2 * W - 3) if W >= 2 else 0, W)
            self.assertEqual(got["ancilla"], 1 if W >= 2 else 0, W)
            self.assertEqual(got.get("cx", 0), 4 * W - 2 if W >= 2 else 1, W)

    def test_cuccaro_carry(self):
        def spec(W):
            return lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W),
                              "z": v["z"] ^ ((v["a"] + v["b"]) >> W)}
        self.check_family(C.cuccaro_carry, spec, widths=range(1, 11))
        for W in range(1, 65):
            obj = C.cuccaro_carry(W)
            got = counts(parse(obj.text())[0][obj.root])
            self.assertEqual((got.get("ccx", 0), got["ancilla"]), (2 * W, 1), W)

    def test_ripple_out_of_place(self):
        def spec(W):
            return lambda v: {"s": v["s"] ^ (v["a"] + v["b"])}
        self.check_family(C.ripple, spec, widths=range(1, 8))
        for W in range(1, 65):
            obj = C.ripple(W)
            got = counts(parse(obj.text())[0][obj.root])
            self.assertEqual((got.get("ccx", 0), got["ancilla"]), (4 * W - 2, 2 * W), W)

    def test_gidney(self):
        def spec(W):
            return lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W)}
        self.check_family(C.gidney, spec)
        for W in range(1, 65):
            obj = C.gidney(W)
            got = counts(parse(obj.text())[0][obj.root])
            self.assertEqual((got.get("ccx", 0), got["ancilla"]), (2 * (W - 1), W - 1), W)

    def test_gidney_explicit_t_counts(self):
        for W in range(1, 33):
            obj = C.gidney_t(W)
            got = counts(parse(obj.text())[0][obj.root])
            self.assertEqual(got.get("ccx", 0), 0)
            self.assertEqual(got["t_total"], 8 * (W - 1), W)
            self.assertEqual(got["ancilla"], W - 1, W)

    def test_qcla(self):
        def spec(W):
            return lambda v: {"z": v["z"] ^ (v["a"] + v["b"])}
        self.check_family(C.qcla, spec, widths=range(1, 8), random=(8, 16, 32, 64, 128, 256))

    def test_qcla_cost_and_depth(self):
        for W in range(1, 130):
            obj = C.qcla(W)
            fn = parse(obj.text())[0][obj.root]
            got = counts(fn)
            T = 5 * W - 3 * popcount(W) - 3 * int(math.log2(W)) - 1
            self.assertEqual(got.get("ccx", 0), 2 * T, W)
            self.assertEqual(got["ancilla"], (W + 1) + W + (W - popcount(W) - int(math.log2(W))), W)
            total, tof = depths(fn)
            if W >= 4:
                # Draper et al. Toffoli depth for each direction; polylog at every width.
                self.assertEqual(tof, 2 * (int(math.log2(W)) + int(math.log2(W // 3)) + 4), W)

    def test_qcla_beats_ripple_depth(self):
        for W in (32, 64, 128):
            fast = depths(parse(C.qcla(W).text())[0][C.qcla(W).root])[1]
            slow = depths(parse(C.ripple(W).text())[0][C.ripple(W).root])[1]
            self.assertLess(fast * 2, slow)


class Bijections(unittest.TestCase):
    """The table of dialect section 8.7 / TDL-5(b), each with its stated conditions."""

    def run_pair(self, obj, g_spec, ginv_spec, exhaustive=True, lanes=4096):
        fns, _ = parse(obj.text())
        verify(self, fns[obj.root], g_spec, None, exhaustive=exhaustive, lanes=lanes)
        verify(self, fns[obj.inverse], ginv_spec, None, exhaustive=exhaustive, lanes=lanes)

    def test_add_sub_in(self):
        for W in list(EXHAUSTIVE) + list(RANDOM):
            mask = (1 << W) - 1
            self.run_pair(C.add_in(W),
                          lambda v: {"x": (v["x"] + v["k"]) & mask},
                          lambda v: {"x": (v["x"] - v["k"]) & mask}, exhaustive=W <= 10)
            got = counts(parse(C.add_in(W).text())[0][C.add_in(W).root])
            self.assertEqual((got.get("ccx", 0), got["ancilla"]),
                             ((2 * W - 3 if W >= 2 else 0), (W + 1 if W >= 2 else W)), W)

    def test_add_sub_const(self):
        for W in range(1, 7):
            mask = (1 << W) - 1
            for k in range(1 << W):
                self.run_pair(C.add_const(W, k),
                              lambda v, k=k: {"x": (v["x"] + k) & mask},
                              lambda v, k=k: {"x": (v["x"] - k) & mask})
        for W, k in ((32, 0xdeadbeef), (64, 0x123456789abcdef1), (128, (1 << 127) | 5)):
            mask = (1 << W) - 1
            self.run_pair(C.add_const(W, k),
                          lambda v: {"x": (v["x"] + k) & mask},
                          lambda v: {"x": (v["x"] - k) & mask}, exhaustive=False)

    def test_xor(self):
        for W in (1, 2, 8, 64):
            obj = C.xor_in(W)
            self.run_pair(obj, lambda v: {"x": v["x"] ^ v["k"]}, lambda v: {"x": v["x"] ^ v["k"]},
                          exhaustive=W <= 8)
            self.assertEqual(counts(parse(obj.text())[0][obj.root]).get("ccx", 0), 0)
            k = 0x5a5a5a5a5a5a5a5a & ((1 << W) - 1)
            self.run_pair(C.xor_const(W, k), lambda v: {"x": v["x"] ^ k}, lambda v: {"x": v["x"] ^ k},
                          exhaustive=W <= 8)

    def test_rotate(self):
        for W in (1, 2, 3, 8, 13, 16, 32, 64):
            mask = (1 << W) - 1
            for r in sorted({0, 1 % W, W // 2, W - 1}):
                obj = C.rotl_const(W, r)
                self.run_pair(obj,
                              lambda v, r=r: {"x": ((v["x"] << r) | (v["x"] >> (W - r))) & mask},
                              lambda v, r=r: {"x": ((v["x"] >> r) | (v["x"] << (W - r))) & mask},
                              exhaustive=W <= 16)
                got = counts(parse(obj.text())[0][obj.root])
                self.assertEqual((got.get("ccx", 0), got["ancilla"]), (0, 0))

    def test_negate(self):
        for W in list(range(1, 17)) + [32, 64, 128]:
            mask = (1 << W) - 1
            obj = C.negate(W)
            self.run_pair(obj, lambda v: {"x": -v["x"] & mask}, lambda v: {"x": -v["x"] & mask},
                          exhaustive=W <= 16)

    def test_bswap(self):
        for W in (16, 32, 64, 128):
            def spec(v):
                return {"x": int.from_bytes(v["x"].to_bytes(W // 8, "little"), "big")}
            self.run_pair(C.bswap(W), spec, spec, exhaustive=W <= 16)
        with self.assertRaises(ValueError):
            C.bswap(12)

    def test_gates_addmod_const_every_small_case(self):
        for W in range(1, 5):
            for m in range(1, (1 << W) + 1):
                for k in range(m):
                    def g(v, m=m, k=k):
                        return {"x": (v["x"] + k) % m if v["x"] < m else v["x"]}

                    def ginv(v, m=m, k=k):
                        return {"x": (v["x"] - k) % m if v["x"] < m else v["x"]}
                    self.run_pair(C.addmod_const_gates(W, k, m), g, ginv)

    def test_gates_addmod_const_larger(self):
        for W, m, k in ((8, 251, 100), (8, 256, 255), (16, 65521, 12345), (32, 4294967291, 3000000000),
                        (64, (1 << 61) - 1, 123456789123456789)):
            def g(v, m=m, k=k):
                return {"x": (v["x"] + k) % m if v["x"] < m else v["x"]}

            def ginv(v, m=m, k=k):
                return {"x": (v["x"] - k) % m if v["x"] < m else v["x"]}
            self.run_pair(C.addmod_const_gates(W, k, m), g, ginv, exhaustive=W <= 16)
            got = counts(parse(C.addmod_const_gates(W, k, m).text())[0][C.addmod_const_gates(W, k, m).root])
            self.assertEqual(got.get("ccx", 0), 9 * (2 * W - 1), (W, m, k))
            self.assertEqual(got["ancilla"], W + 5, (W, m, k))

    def test_gates_addmod_in(self):
        for W in range(1, 5):
            for m in range(1, (1 << W) + 1):
                def g(v, m=m):
                    return {"x": (v["x"] + v["k"]) % m if v["x"] < m and v["k"] < m else v["x"]}

                def ginv(v, m=m):
                    return {"x": (v["x"] - v["k"]) % m if v["x"] < m and v["k"] < m else v["x"]}
                self.run_pair(C.addmod_in_gates(W, m), g, ginv)
        m = (1 << 61) - 1

        def g(v):
            return {"x": (v["x"] + v["k"]) % m if v["x"] < m and v["k"] < m else v["x"]}
        self.run_pair(C.addmod_in_gates(64, m), g, lambda v: {"x": (v["x"] - v["k"]) % m if v["x"] < m and v["k"] < m else v["x"]},
                      exhaustive=False)

    def test_gates_mulmod_const_every_small_case(self):
        for W in range(1, 5):
            for m in range(1, (1 << W) + 1):
                for k in range(m):
                    if math.gcd(k, m) != 1:
                        with self.assertRaises(ValueError):
                            C.mulmod_const_gates(W, k, m)
                        continue

                    def g(v, m=m, k=k):
                        return {"x": (v["x"] * k) % m if v["x"] < m else v["x"]}
                    inv = pow(k, -1, m) if m > 1 else 0

                    def ginv(v, m=m, inv=inv):
                        return {"x": (v["x"] * inv) % m if v["x"] < m else v["x"]}
                    self.run_pair(C.mulmod_const_gates(W, k, m), g, ginv)

    def test_gates_mulmod_const_larger(self):
        for W, m, k in ((8, 251, 17), (8, 255, 2), (12, 4093, 1000), (32, 4294967291, 7),
                        (64, (1 << 61) - 1, 3)):
            inv = pow(k, -1, m)

            def g(v, m=m, k=k):
                return {"x": (v["x"] * k) % m if v["x"] < m else v["x"]}

            def ginv(v, m=m, inv=inv):
                return {"x": (v["x"] * inv) % m if v["x"] < m else v["x"]}
            self.run_pair(C.mulmod_const_gates(W, k, m), g, ginv, exhaustive=W <= 12, lanes=256)
            got = counts(parse(C.mulmod_const_gates(W, k, m).text())[0][C.mulmod_const_gates(W, k, m).root])
            self.assertEqual(got.get("ccx", 0), 20 * W * W + 3 * W - 4, (W, m, k))
            self.assertEqual(got["ancilla"], 2 * W + 7, (W, m, k))


class Differential(unittest.TestCase):
    """The reference interpreter must agree on the emitted object, full tuples and +1 phase."""

    def setUp(self):
        self.dir = Path(__file__).resolve().parents[2] / ".tmp/opus-arith-circuits/objects"
        self.dir.mkdir(parents=True, exist_ok=True)

    def place(self, obj):
        path = self.dir / f"{obj.root}.bisa"
        write_object(obj, path)
        return path

    def diff(self, obj, symbol, spec, budget=256, seed=3):
        from random import Random
        fn = parse(obj.text())[0][symbol]
        rng = Random(seed)
        bits = sum(w for _, w in fn.mut + fn.ins)
        if (1 << bits) <= budget:
            cases = []
            for n in range(1 << bits):
                vals, at = [], 0
                for _, w in fn.mut + fn.ins:
                    vals.append((n >> at) & ((1 << w) - 1))
                    at += w
                cases.append(vals)
        else:
            cases = [[rng.getrandbits(w) for _, w in fn.mut + fn.ins] for _ in range(budget)]
        path = self.place(obj)
        split = len(fn.mut)
        names = [n for n, _ in fn.mut + fn.ins]
        args = [(c[:split], c[split:]) for c in cases]
        for (mut, ins), got in zip(args, REF.many(path, symbol, args)):
            want = spec(dict(zip(names, mut + ins)))
            self.assertEqual(got[0], [want[n] for n, _ in fn.mut], (symbol, mut, ins))
            self.assertEqual(got[1], ins, (symbol, mut, ins))

    def test_adders_agree(self):
        for make in (C.cuccaro, C.gidney):
            for W, budget in ((1, 16), (2, 16), (3, 64), (4, 256), (8, 64), (64, 4)):
                obj = make(W)
                mask = (1 << W) - 1
                self.diff(obj, obj.root, lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) & mask}, budget=budget)
        for make, target in ((C.ripple, "s"), (C.qcla, "z")):
            for W, budget in ((1, 8), (2, 32), (3, 128), (8, 32), (32, 4)):
                obj = make(W)
                self.diff(obj, obj.root,
                          lambda v, t=target: {t: v[t] ^ (v["a"] + v["b"])}, budget=budget)

    def test_explicit_t_and_is_exact_on_clean_target(self):
        """Gidney's 4-T AND computes x AND y with exact +1 phase on a clean target."""
        c = Circuit("arith.test.temp_and", [("t", 1)], [("x", 1), ("y", 1)], kind="action")
        C.and_compute(c, "x[0]", "y[0]", "t[0]")
        c.spec = lambda v: {"t": v["t"] ^ (v["x"] & v["y"])}
        obj = Object([c])
        obj._text = obj._base()
        path = self.place(obj)
        for x in (0, 1):
            for y in (0, 1):
                got = REF.action(path, c.name, [0], [x, y])
                self.assertEqual(got, ([x & y], [x, y]))

    def test_explicit_t_gidney_is_rejected_by_isa_6_2(self):
        """Contract gap pinned, bead filed: a 4-T AND's h makes t an `other` value, so section
        6.2 refuses its release once the carry has a lasting reader. The T-optimal adder needs
        the ISA change named in the bead; until then the exact ccx form is the published one."""
        obj = C.gidney_t(3)
        path = self.place(obj)
        self.assertIn("6.2", REF.rejected(path) or "")

    def test_bijections_agree_both_directions(self):
        W = 8
        mask = 255
        obj = C.add_in(W)
        self.diff(obj, obj.root, lambda v: {"x": (v["x"] + v["k"]) & mask}, budget=64)
        self.diff(obj, obj.inverse, lambda v: {"x": (v["x"] - v["k"]) & mask}, budget=64)

    def test_gate_level_modular_candidates_are_rejected_by_isa_6_2(self):
        """Contract gap pinned, bead filed: their flags are clean on every basis input (the
        exhaustive tests above), but ISA 6.2 admits only matched cleanups."""
        for obj in (C.addmod_const_gates(4, 5, 11), C.addmod_in_gates(4, 11), C.mulmod_const_gates(4, 5, 11)):
            self.assertIn("6.2", REF.rejected(self.place(obj)) or "", obj.root)

    def token(self, obj, symbol):
        return f"token:{obj.circuit(symbol).budget},0,0,0"

    def test_modular_qinplace_every_input(self):
        """The admitted form: every x (and k) of a small width, both directions, exact phase."""
        for W, k, m in ((1, 0, 1), (1, 1, 2), (3, 5, 7), (4, 5, 11), (4, 15, 16)):
            obj = C.addmod_const(W, k, m)
            path = self.place(obj)
            for symbol, sign in ((obj.root, 1), (obj.inverse, -1)):
                token = self.token(obj, symbol)
                cases = [([x], []) for x in range(1 << W)]
                for (mut, _), got in zip(cases, REF.many(path, symbol, cases, "--arg", token)):
                    x = mut[0]
                    self.assertEqual(got[0], [(x + sign * k) % m if x < m else x], (obj.root, x))
        for W, k, m in ((1, 1, 1), (3, 3, 7), (4, 5, 11), (4, 7, 16)):
            if math.gcd(k, m) != 1:
                continue
            obj = C.mulmod_const(W, k, m)
            path = self.place(obj)
            inv = pow(k, -1, m) if m > 1 else 0
            for symbol, factor in ((obj.root, k), (obj.inverse, inv)):
                token = self.token(obj, symbol)
                cases = [([x], []) for x in range(1 << W)]
                for (mut, _), got in zip(cases, REF.many(path, symbol, cases, "--arg", token)):
                    x = mut[0]
                    self.assertEqual(got[0], [(x * factor) % m if x < m else x], (obj.root, x))

    def test_modular_oracles_beyond_interpreter_exhaustive_width(self):
        """Run-time qinplace re-checks 2^n inputs, so wide pairs replay g and ginv directly."""
        from random import Random
        rng = Random(5)
        for obj, W, k, m, make in (
                (C.addmod_const(32, 3000000000, 4294967291), 32, 3000000000, 4294967291, "add"),
                (C.addmod_const(64, 123456789123456789, (1 << 61) - 1), 64, 123456789123456789, (1 << 61) - 1, "add"),
                (C.mulmod_const(32, 7, 4294967291), 32, 7, 4294967291, "mul"),
                (C.mulmod_const(64, 3, (1 << 61) - 1), 64, 3, (1 << 61) - 1, "mul")):
            path = self.place(obj)
            act = obj.circuit(obj.root)
            for _ in range(16):
                x = rng.getrandbits(W) if rng.random() < 0.5 else rng.randrange(m)
                want = ((x + k) % m if make == "add" else (x * k) % m) if x < m else x
                y = REF.oracle(path, act.g.name, [x], act.budget)
                self.assertEqual(y, want, (obj.root, x))
                self.assertEqual(REF.oracle(path, act.ginv.name, [y], act.budget), x, (obj.root, x))

    def test_modular_in_form_refreshes_qinplace_ins(self):
        """qinplace with a preserved in operand, x and k each below and above m."""
        W, m = 3, 5
        obj = C.addmod_in(W, m)
        act = obj.circuit(obj.root)
        # The interpreter's text parser does not take qinplace's (ins) list yet (ISA 0.9 K-form,
        # bead filed), so this replays the pair's two oracles; the action is checked as text.
        self.assertIn(f"qinplace @{act.g.name} @{act.ginv.name} tk x (k) () ()", obj.text())
        only = Object([act.g, act.ginv], root=act.g.name)
        only._text = only._base()
        path = self.place(only)
        for x in range(1 << W):
            for k in range(1 << W):
                want = (x + k) % m if x < m and k < m else x
                self.assertEqual(REF.oracle(path, act.g.name, [x, k], act.budget), want, (x, k))
                self.assertEqual(REF.oracle(path, act.ginv.name, [want, k], act.budget), x, (x, k))

    def test_wrong_circuit_is_caught(self):
        """The oracle is real: a dropped uncompute must fail, not pass silently."""
        obj = C.ripple(3)
        text = obj.text()
        broken = text.replace("cx a[0] anc[0]\n", "", 1)
        self.assertNotEqual(broken, text)
        path = self.dir / "broken.bisa"
        path.write_text(broken)
        self.assertIsNotNone(REF.rejected(path), "a tampered function must break its stored hash")
        # Same defect with hashes recomputed: only the execution or the validation can see it.
        c = Circuit("arith.test.broken", [("s", 4)], [("a", 3), ("b", 3)])
        C.ripple_block(c, c.wires("a"), c.wires("b"), c.wires("s"))
        c.gates.pop()
        c.spec = lambda v: v
        bad = Object([c])
        bad._text = bad._base()
        path = self.place(bad)
        self.assertIn("6.2", REF.rejected(path) or "")


if __name__ == "__main__":
    unittest.main()
