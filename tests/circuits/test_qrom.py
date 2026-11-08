"""QROM and SELECT-SWAP: every address, every target value, costed, differential."""
import random
import sys
import unittest
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import RefInterp, counts, depths, parse, simulate, word  # noqa: E402
from test_adders import verify  # noqa: E402
from adders.circuits import write_object  # noqa: E402
from qrom import constructions as Q  # noqa: E402

REF = RefInterp()
DIR = Path(__file__).resolve().parents[2] / ".tmp/opus-arith-circuits/objects"


def table(n, W, seed=1):
    rng = random.Random(seed + n * 1000 + W)
    return [rng.getrandbits(W) for _ in range(1 << n)]


def spec(data):
    return lambda v: {"t": v["t"] ^ data[v.get("idx", 0)]}


def sizes(obj):
    return counts(parse(obj.text())[0][obj.root])


class Qrom(unittest.TestCase):
    def test_cli_single_word_table(self):
        for family, n, extra in (("qrom", 0, []), ("qrom.select_swap", 0, ["0"]),
                                 ("qrom.select_swap_dirty", 1, ["0"])):
            result = subprocess.run([sys.executable, "-B", "-I",
                                     str(Path(__file__).resolve().parents[2] / "adders/generate.py"),
                                     "one", family, "1", str(n), "1", *extra],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            fn = next(iter(parse(result.stdout)[0].values()))
            values = {name: [0] * width for name, width in fn.mut + fn.ins + fn.borrowed()}
            store = simulate(fn, values, 1)
            self.assertEqual(word(store, "t", 1), [1])

    def test_every_address_every_target(self):
        for n in range(0, 9):
            for W in (1, 3, 8):
                data = table(n, W)
                obj = Q.qrom(tuple(data), n, W)
                verify(self, parse(obj.text())[0][obj.root], spec(data), None)

    def test_edge_tables(self):
        for data in ((0, 0, 0, 0), (1, 1, 1, 1), (1, 0, 0, 0), (0, 0, 0, 1), (0, 1, 2, 3)):
            obj = Q.qrom(data, 2, 2)
            verify(self, parse(obj.text())[0][obj.root], spec(data), None)

    def test_wide_words_random(self):
        for n, W in ((6, 64), (10, 32), (12, 16), (8, 256)):
            data = table(n, W)
            obj = Q.qrom(tuple(data), n, W)
            verify(self, parse(obj.text())[0][obj.root], spec(data), None, exhaustive=False, lanes=1 << 12)

    def test_short_table_pads_with_zero(self):
        data = (5, 7, 2)
        obj = Q.qrom(data, 2, 3)
        verify(self, parse(obj.text())[0][obj.root], spec(data + (0,)), None)
        with self.assertRaises(ValueError):
            Q.qrom((1, 2, 3, 4, 5), 2, 3)
        with self.assertRaises(ValueError):
            Q.qrom((8,), 1, 3)

    def test_cost_independent_of_word_width(self):
        """Babbush et al.: 2(L-2) Toffoli without the root AND, n clean flags, T independent of W."""
        for n in range(1, 13):
            L = 1 << n
            for W in (1, 8, 64):
                got = sizes(Q.qrom(tuple(table(n, W)), n, W))
                self.assertEqual(got.get("ccx", 0), 2 * (L - 2), (n, W))
                self.assertEqual(got["t_total"], 14 * (L - 2), (n, W))
                self.assertEqual(got["ancilla"], n, (n, W))
        self.assertEqual(sizes(Q.qrom((3,), 0, 2)).get("ccx", 0), 0)


class SelectSwapClean(unittest.TestCase):
    def test_every_split(self):
        for n in range(1, 7):
            for k in range(0, n + 1):
                for W in (1, 3):
                    data = table(n, W, seed=2)
                    obj = Q.select_swap(tuple(data), n, W, k)
                    verify(self, parse(obj.text())[0][obj.root], spec(data), None)

    def test_wide(self):
        for n, W, k in ((8, 16, 2), (10, 32, 3), (12, 8, 4)):
            data = table(n, W, seed=3)
            obj = Q.select_swap(tuple(data), n, W, k)
            verify(self, parse(obj.text())[0][obj.root], spec(data), None, exhaustive=False, lanes=1 << 12)

    def test_cost_and_tradeoff(self):
        for n, W, k in ((4, 8, 0), (4, 8, 2), (8, 16, 2), (10, 32, 3), (12, 8, 4), (6, 2, 6), (6, 2, 5)):
            got = sizes(Q.select_swap(tuple(table(n, W, seed=3)), n, W, k))
            blocks = 1 << (n - k)
            lam = 1 << k
            want = 2 * (2 * max(blocks - 2, 0) + (lam - 1) * W)
            self.assertEqual(got.get("ccx", 0), want, (n, W, k))
            self.assertEqual(got["ancilla"], lam * W + (n - k), (n, W, k))
        # The published point of the trade-off: fewer Toffoli than plain QROM for small W, more workspace.
        n, W = 12, 2
        plain = sizes(Q.qrom(tuple(table(n, W)), n, W))
        best = sizes(Q.select_swap(tuple(table(n, W)), n, W, 5))
        self.assertLess(best["ccx"], plain["ccx"] / 3)
        self.assertGreater(best["ancilla"], plain["ancilla"])


class SelectSwapDirty(unittest.TestCase):
    def test_every_dirty_value(self):
        for n, W, k in ((1, 1, 1), (2, 1, 1), (2, 2, 1), (3, 1, 2), (3, 2, 1), (4, 1, 2), (4, 2, 2)):
            data = table(n, W, seed=4)
            obj = Q.select_swap_dirty(tuple(data), n, W, k)
            verify(self, parse(obj.text())[0][obj.root], spec(data), None)

    def test_wide(self):
        for n, W, k in ((8, 16, 2), (10, 8, 3)):
            data = table(n, W, seed=5)
            obj = Q.select_swap_dirty(tuple(data), n, W, k)
            verify(self, parse(obj.text())[0][obj.root], spec(data), None, exhaustive=False, lanes=1 << 12)

    def test_cost(self):
        for n, W, k in ((4, 2, 2), (8, 16, 2), (10, 8, 3)):
            obj = Q.select_swap_dirty(tuple(table(n, W, seed=5)), n, W, k)
            got = sizes(obj)
            blocks, lam = 1 << (n - k), 1 << k
            want = 2 * 2 * max(blocks - 2, 0) + 4 * (lam - 1) * W
            self.assertEqual(got.get("ccx", 0), want, (n, W, k))
            self.assertEqual(got["ancilla"], n - k, (n, W, k))
            self.assertEqual(parse(obj.text())[0][obj.root].borrowed(), [("y", lam * W)])


class Differential(unittest.TestCase):
    def test_interpreter_agrees(self):
        DIR.mkdir(parents=True, exist_ok=True)
        rng = random.Random(4)
        objects = []
        for n, W in ((0, 3), (1, 2), (2, 4), (3, 8), (5, 8), (8, 16)):
            data = table(n, W)
            objects.append((Q.qrom(tuple(data), n, W), data, n, W, 32))
        for n, W, k in ((3, 2, 1), (4, 4, 2), (5, 3, 3)):
            data = table(n, W, seed=2)
            objects.append((Q.select_swap(tuple(data), n, W, k), data, n, W, 16))
        for obj, data, n, W, budget in objects:
            path = DIR / f"{obj.root}.bisa"
            write_object(obj, path)
            runs = []
            for _ in range(budget):
                runs.append(([rng.getrandbits(W)], [rng.getrandbits(n)] if n else []))
            for (mut, ins), got in zip(runs, REF.many(path, obj.root, runs)):
                self.assertEqual(got[0], [mut[0] ^ data[ins[0] if ins else 0]], (obj.root, mut, ins))

    def test_dirty_form(self):
        """Borrowed wires are returned; the interpreter's own frame decision is reported as it stands."""
        DIR.mkdir(parents=True, exist_ok=True)
        data = table(3, 2, seed=4)
        obj = Q.select_swap_dirty(tuple(data), 3, 2, 1)
        path = DIR / f"{obj.root}.bisa"
        write_object(obj, path)
        for idx in range(8):
            got = REF.action(path, obj.root, [1], [idx])
            self.assertEqual(got[0], [1 ^ data[idx]], idx)


if __name__ == "__main__":
    unittest.main()
