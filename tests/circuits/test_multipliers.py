"""Multipliers: exhaustive to W = 5 (every operand pair and target), random beyond, costed."""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import RefInterp, counts, depths, parse  # noqa: E402
from test_adders import verify  # noqa: E402
from multipliers import constructions as M  # noqa: E402

REF = RefInterp()
DIR = Path(__file__).resolve().parents[2] / ".tmp/opus-arith-circuits/objects"


def mul_spec(R):
    return lambda v: {"z": v["z"] ^ ((v["a"] * v["b"]) % (1 << R))}


def muladd_spec(R):
    return lambda v: {"z": (v["z"] + v["a"] * v["b"]) % (1 << R)}


def sizes(obj):
    return counts(parse(obj.text())[0][obj.root])


class Schoolbook(unittest.TestCase):
    def test_muladd_exhaustive_and_random(self):
        # 3W-bit domains with a full target; W=8 covers every operand pair at a sampled target.
        for W in range(1, 7):
            for R in (W, 2 * W):
                obj = M.muladd_school(W, R)
                verify(self, parse(obj.text())[0][obj.root], muladd_spec(R), None)
        for W in (8, 10):
            obj = M.muladd_school(W, 2 * W)
            verify(self, parse(obj.text())[0][obj.root], muladd_spec(2 * W), None, exhaustive=False, lanes=1 << 16)
        for W in (16, 32, 64):
            obj = M.muladd_school(W, 2 * W)
            verify(self, parse(obj.text())[0][obj.root], muladd_spec(2 * W), None, exhaustive=False)

    def test_every_pair_at_zero_target(self):
        """Every operand pair up to 10 bits on a clean and on one fixed dirty target, both ctl values."""
        for make in (M.mul_school, M.muladd_school):
            for W in (8, 10):
                R = 2 * W
                fn = parse(make(W, R).text())[0][make(W, R).root]
                check_pairs(self, fn, W, R, xor=make is M.mul_school)

    def test_mul_xor(self):
        for W in range(1, 6):
            for R in (W, 2 * W):
                obj = M.mul_school(W, R)
                verify(self, parse(obj.text())[0][obj.root], mul_spec(R), None)
        for W in (16, 32, 64):
            obj = M.mul_school(W, 2 * W)
            verify(self, parse(obj.text())[0][obj.root], mul_spec(2 * W), None, exhaustive=False)

    def test_cost(self):
        for W in range(1, 33):
            for R in (W, 2 * W):
                got = sizes(M.muladd_school(W, R))
                cuccaro = lambda n: 2 * n - 3 if n >= 2 else 0
                want = sum(2 * min(W, R - i) + cuccaro(R - i) for i in range(min(W, R)))
                self.assertEqual(got.get("ccx", 0), want, (W, R))
                self.assertEqual(got["t_total"], 7 * want, (W, R))
                self.assertEqual(sizes(M.mul_school(W, R)).get("ccx", 0), 2 * want, (W, R))
                self.assertEqual(got["ancilla"], R + (1 if R >= 2 else 0), (W, R))
                self.assertEqual(sizes(M.mul_school(W, R))["ancilla"], 2 * R + (1 if R >= 2 else 0), (W, R))


def check_pairs(case, fn, W, R, xor):
    """All 2^(2W) operand pairs by bit-slicing, at two target values, with ctl on half the lanes."""
    from harness import Lanes, VECTOR_ABOVE, pack_word, simulate, word  # noqa: F401
    import numpy as np
    operands = Lanes({"a": W, "b": W})
    a, b = operands.array("a"), operands.array("b")
    n = operands.count
    full = (1 << n) - 1
    for start in (0, 0x5a5a5a5a5 & ((1 << R) - 1)):
        tv = [full if (start >> i) & 1 else 0 for i in range(R)]
        product = a * b
        if R < 64:
            product &= (np.uint64(1) << np.uint64(R)) - np.uint64(1)
        value = (np.uint64(start) ^ product) if xor else (np.uint64(start) + product)
        if R < 64:
            value &= (np.uint64(1) << np.uint64(R)) - np.uint64(1)
        want = pack_word(value, R)
        mask = random.Random(11).getrandbits(n)
        store = simulate(fn, {"a": operands.bits["a"], "b": operands.bits["b"], "z": list(tv)}, n)
        case.assertEqual(word(store, "z", R), want, f"{fn.name}: start {start}")
        store = simulate(fn, {"a": operands.bits["a"], "b": operands.bits["b"], "z": list(tv)}, n, control=mask)
        case.assertEqual(word(store, "z", R),
                         [(w & mask) | (t & (full ^ mask)) for w, t in zip(want, tv)], f"{fn.name}: ctl")
        case.assertEqual(word(store, "a", W), operands.bits["a"])
        case.assertEqual(word(store, "b", W), operands.bits["b"])


class Karatsuba(unittest.TestCase):
    def test_small_exhaustive(self):
        for W in range(1, 7):
            for R in (W, 2 * W):
                obj = M.muladd_karatsuba(W, R)
                verify(self, parse(obj.text())[0][obj.root], muladd_spec(R), None)

    def test_every_pair_to_ten_bits(self):
        for W in (8, 10):
            fn = parse(M.muladd_karatsuba(W, 2 * W).text())[0][M.muladd_karatsuba(W, 2 * W).root]
            check_pairs(self, fn, W, 2 * W, xor=False)

    def test_random_wide_and_truncated(self):
        for W, R in ((16, 32), (32, 64), (32, 32), (64, 128), (64, 64)):
            obj = M.muladd_karatsuba(W, R)
            verify(self, parse(obj.text())[0][obj.root], muladd_spec(R), None, exhaustive=False, lanes=512)

    def test_xor_form(self):
        for W in (1, 2, 3, 4):
            obj = M.mul_karatsuba(W, 2 * W)
            verify(self, parse(obj.text())[0][obj.root], mul_spec(2 * W), None)
        obj = M.mul_karatsuba(32, 64)
        verify(self, parse(obj.text())[0][obj.root], mul_spec(64), None, exhaustive=False, lanes=512)

    def test_cost_recurrence(self):
        for W in (1, 2, 3, 4, 5, 6, 7, 8, 9, 16, 32, 64):
            for R in (W, 2 * W):
                got = sizes(M.muladd_karatsuba(W, R))
                self.assertEqual(got.get("ccx", 0), M.karatsuba_toffoli(W, R), (W, R))
                self.assertEqual(got["ancilla"], M.karatsuba_ancilla(W, R), (W, R))
                forms = sizes(M.mul_karatsuba(W, R))
                self.assertEqual(forms.get("ccx", 0), 2 * M.karatsuba_forward_toffoli(W), (W, R))

    def test_subquadratic_growth(self):
        """F(2W)/F(W) tends to 3 (Karatsuba), not 4 (schoolbook); and it overtakes schoolbook."""
        ratio = M.karatsuba_forward_toffoli(1 << 20) / M.karatsuba_forward_toffoli(1 << 19)
        self.assertLess(ratio, 3.2)
        school = lambda W: 2 * sum(2 * W + 2 * (2 * W - i) - 3 for i in range(W))
        crossover = next(W for W in (2 ** k for k in range(3, 24))
                         if 2 * M.karatsuba_forward_toffoli(W) < school(W))
        self.assertLessEqual(crossover, 1 << 12, "schoolbook never beaten by this width")


class QclaTree(unittest.TestCase):
    def test_exhaustive(self):
        for W in range(1, 6):
            obj = M.mul_tree(W)
            verify(self, parse(obj.text())[0][obj.root], mul_spec(2 * W), None)

    def test_every_pair_to_ten_bits(self):
        for W in (8, 10):
            obj = M.mul_tree(W)
            check_pairs(self, parse(obj.text())[0][obj.root], W, 2 * W, xor=True)

    def test_random(self):
        for W in (16, 32, 64):
            obj = M.mul_tree(W)
            verify(self, parse(obj.text())[0][obj.root], mul_spec(2 * W), None, exhaustive=False, lanes=256)

    def test_polylog_toffoli_depth_and_cost(self):
        for W in (1, 2, 3, 4, 5, 8, 16, 32, 64):
            fn = parse(M.mul_tree(W).text())[0][M.mul_tree(W).root]
            got = counts(fn)
            self.assertEqual(got.get("ccx", 0), M.tree_toffoli(W), W)
            self.assertEqual(got["ancilla"], M.tree_ancilla(W), W)
            total, tof = depths(fn)
            self.assertLessEqual(tof, M.tree_toffoli_depth_bound(W), W)
        # O(log^2 W): depth / log^2 W may not grow with W; and far below schoolbook.
        measured = {}
        ratio = float("inf")
        for W in (8, 16, 32, 64, 128):
            measured[W] = depths(parse(M.mul_tree(W).text())[0][M.mul_tree(W).root])[1]
            now = measured[W] / math.log2(W) ** 2
            self.assertLessEqual(now, ratio, measured)
            ratio = now
        school = depths(parse(M.mul_school(64, 128).text())[0][M.mul_school(64, 128).root])[1]
        self.assertLess(measured[64] * 10, school)


class Differential(unittest.TestCase):
    def test_interpreter_agrees(self):
        DIR.mkdir(parents=True, exist_ok=True)
        rng = random.Random(9)
        cases = [(M.mul_school(W, 2 * W), False, W, 2 * W, b) for W, b in ((1, 16), (2, 64), (3, 64), (4, 32))]
        cases += [(M.muladd_school(W, 2 * W), True, W, 2 * W, b) for W, b in ((2, 64), (4, 32), (8, 8))]
        cases += [(M.muladd_karatsuba(W, 2 * W), True, W, 2 * W, b) for W, b in ((2, 64), (3, 32), (5, 8))]
        cases += [(M.mul_karatsuba(5, 10), False, 5, 10, 8)]
        cases += [(M.mul_tree(W), False, W, 2 * W, b) for W, b in ((1, 16), (2, 64), (3, 16), (4, 8))]
        for obj, add, W, R, budget in cases:
            path = DIR / f"{obj.root}.bisa"
            path.write_text(obj.text())
            runs = [([rng.getrandbits(R)], [rng.getrandbits(W), rng.getrandbits(W)]) for _ in range(budget)]
            for (mut, ins), got in zip(runs, REF.many(path, obj.root, runs)):
                product = ins[0] * ins[1]
                want = (mut[0] + product) % (1 << R) if add else mut[0] ^ (product % (1 << R))
                self.assertEqual(got, ([want], ins), (obj.root, mut, ins))


if __name__ == "__main__":
    from time_guard import test_main
    test_main()
