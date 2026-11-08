"""Independent verification harness for bennett-arith circuit objects.

Nothing here imports a generator: it reads the emitted canonical text, so a bug
in a generator's builder cannot hide behind the builder's own bookkeeping.

* parse()/gates_of(): ISA 0.9 section 16 text to a gate list.
* simulate(): bit-sliced simulation, one Python big integer per wire with one
  bit per input vector, so 2^n inputs cost one pass over the gates.
* RefInterp: the reference interpreter binary as a differential oracle.
"""
import json
import os
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VECTOR_ABOVE = 1 << 17  # Specs run per lane up to here, as numpy expressions above it.
sys.path.insert(0, str(ROOT / "scripts"))
from pinned_sibling import resolve_sibling  # noqa: E402
from time_guard import run as guarded_run  # noqa: E402


def ref_binary():
    """Use the debug build materialised from the gate.toml ISA pin."""
    path = resolve_sibling("bennett-isa-spec") / "reference-interpreter/target/debug/bennett-isa-ref"
    if not path.is_file():
        raise SystemExit(f"reference interpreter binary not found at {path}; "
                         "materialise with gate_run.py verify --repo bennett-arith --sha HEAD")
    return path


# ---- text form ------------------------------------------------------------

BUNDLE = re.compile(r"(\w[\w.]*):wire\[(\d+)\]")
OPERAND = re.compile(r"^([A-Za-z_][\w.]*)\[(\d+)\]$")
GATES = {"x", "cx", "ccx", "swap", "h", "t", "tdg", "s", "sdg", "cz"}


class Function:
    def __init__(self, kind, name, groups):
        self.kind, self.name, self.groups = kind, name, groups
        self.mut = groups[0]
        self.ins = groups[1]
        self.ops = []

    def gates(self):
        return [op for op in self.ops if op[0] in GATES]

    def borrowed(self):
        return [(op[1], int(op[3])) for op in self.ops if op[0] == "qborrow"]


def parse(text):
    """Return ({name: Function}, sections) from canonical object text."""
    assert text.endswith("\n") and "\n\n\n" not in text, "section 16.1 blank-line rule"
    assert not any(line != line.rstrip(" ") for line in text.split("\n")), "section 16.1 trailing space"
    sections = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("section "):
            current = line.split(" ", 1)[1]
            assert current not in sections, f"duplicate section {current}"
            sections[current] = []
        elif current is not None and line:
            sections[current].append(line)
    functions = {}
    fn = None
    for line in sections.get("functions", []):
        head = re.match(r"(perm_action|action) @(\S+) (.*)$", line)
        if head:
            groups = [
                [(m.group(1), int(m.group(2))) for m in BUNDLE.finditer(g)]
                for g in re.findall(r"\(([^()]*)\)", head.group(3))
            ]
            assert len(groups) == 5, line
            fn = Function(head.group(1), head.group(2), groups)
            functions[fn.name] = fn
            continue
        if re.match(r"oracle @|lproc @", line):
            fn = None
            continue
        if fn is None or line.startswith("^") or line.startswith("regs "):
            continue
        tokens = line.split(" ")
        if len(tokens) >= 3 and tokens[1] == "=":
            fn.ops.append((tokens[2], tokens[0], *tokens[3:]))
        else:
            fn.ops.append(tuple(tokens))
    return functions, sections


def counts(fn):
    """Gate census read from the text, plus peak clean workspace."""
    census = {}
    live = peak = 0
    widths = {}
    for op in fn.ops:
        if op[0] == "qalloc":
            widths[op[1]] = int(op[3])
            live += int(op[3])
            peak = max(peak, live)
        elif op[0] == "qfree":
            live -= widths.pop(op[1])
        elif op[0] in GATES:
            census[op[0]] = census.get(op[0], 0) + 1
        elif op[0] not in {"qborrow", "qreturn"}:
            raise AssertionError(f"unexpected op {op}")
    assert live == 0 and not widths, "workspace leak in text"
    census["t_total"] = census.get("t", 0) + census.get("tdg", 0) + 7 * census.get("ccx", 0)
    census["ancilla"] = peak
    return census


def depths(fn):
    """ASAP-layered total depth and Toffoli depth."""
    total = {}
    tof = {}
    d = td = 0
    for op in fn.gates():
        wires = op[1:]
        layer = max((total.get(w, 0) for w in wires), default=0) + 1
        tlayer = max((tof.get(w, 0) for w in wires), default=0) + (op[0] == "ccx")
        for w in wires:
            total[w] = layer
            tof[w] = tlayer
        d, td = max(d, layer), max(td, tlayer)
    return d, td


# ---- bit-sliced simulation ------------------------------------------------

def pack(mask):
    """Bool ndarray to an integer whose bit i is mask[i]."""
    return int.from_bytes(np.packbits(np.asarray(mask, dtype=bool), bitorder="little").tobytes(), "little")


def simulate(fn, values, lanes, control=None):
    """Run fn on every lane. values maps bundle name to a list of per-bit ints.

    control: an optional lane mask standing in for one inherited control (ISA
    5.3 ctl): workspace lifetimes stay unconditional, every gate is controlled.
    Returns the final wire store; raises if qfree sees a nonzero lane.
    """
    full = (1 << lanes) - 1
    ctl = full if control is None else control
    store = {}
    for name, bits in values.items():
        for i, v in enumerate(bits):
            store[f"{name}[{i}]"] = v
    dirty = {}
    for op in fn.ops:
        code = op[0]
        if code == "cx":
            store[op[2]] ^= store[op[1]] & ctl
        elif code == "ccx":
            store[op[3]] ^= store[op[1]] & store[op[2]] & ctl
        elif code == "x":
            store[op[1]] ^= ctl
        elif code == "swap":
            d = (store[op[1]] ^ store[op[2]]) & ctl
            store[op[1]] ^= d
            store[op[2]] ^= d
        elif code == "qalloc":
            for i in range(int(op[3])):
                store[f"{op[1]}[{i}]"] = 0
            dirty[op[1]] = int(op[3])
        elif code == "qfree":
            for i in range(dirty.pop(op[1])):
                assert store.pop(f"{op[1]}[{i}]") == 0, f"{fn.name}: {op[1]}[{i}] not clean at qfree"
        elif code == "qborrow":
            assert op[1] in values, f"{fn.name}: dirty bundle {op[1]} needs values"
        elif code == "qreturn":
            pass
        else:
            raise AssertionError(f"simulator: unsupported op {op}")
    return store


def pack_word(array, width):
    """A uint64 lane array to per-bit integers."""
    array = np.asarray(array, dtype=np.uint64)
    return [pack((array >> np.uint64(i)) & np.uint64(1)) for i in range(width)]


def word(store, name, width):
    """Read a bundle as a per-bit list."""
    return [store[f"{name}[{i}]"] for i in range(width)]


class Lanes:
    """Input vectors over named bundles, with numeric views for computing specs."""

    def __init__(self, widths, exhaustive=True, count=None, seed=1):
        self.widths = dict(widths)
        total = sum(self.widths.values())
        if exhaustive:
            assert total <= 28, f"exhaustive domain of {total} bits exceeds this harness's guard"
            self.count = 1 << total
            self.bits = {}
            at = 0
            for name, w in self.widths.items():
                self.bits[name] = [self._pattern(at + i) for i in range(w)]
                at += w
        else:
            self.count = count
            rng = random.Random(seed)
            self.bits = {
                name: [rng.getrandbits(count) for _ in range(w)] for name, w in self.widths.items()
            }

    def _pattern(self, bit):
        lanes = self.count
        period = 1 << (bit + 1)
        half = 1 << bit
        unit = ((1 << half) - 1) << half
        # Doubling replication of the block.
        out = unit
        size = period
        while size < lanes:
            out |= out << size
            size *= 2
        return out & ((1 << lanes) - 1)

    def array(self, name):
        """uint64 lanes of an exhaustive bundle (widths at most 64)."""
        out = np.zeros(self.count, dtype=np.uint64)
        for i, v in enumerate(self.bits[name]):
            raw = np.unpackbits(
                np.frombuffer(v.to_bytes((self.count + 7) // 8, "little"), dtype=np.uint8),
                bitorder="little", count=self.count,
            )
            out |= raw.astype(np.uint64) << np.uint64(i)
        return out

    def values(self, name):
        """Python ints per lane for a bundle (wide widths included)."""
        return unbits(self.bits[name], self.count)


def unbits(bits, lanes):
    out = [0] * lanes
    for i, v in enumerate(bits):
        raw = np.unpackbits(
            np.frombuffer(v.to_bytes((lanes + 7) // 8, "little"), dtype=np.uint8),
            bitorder="little", count=lanes,
        )
        for lane in np.flatnonzero(raw):
            out[lane] |= 1 << i
    return out


def tobits(words, width, lanes):
    bits = [0] * width
    for lane, w in enumerate(words):
        while w:
            low = w & -w
            bits[low.bit_length() - 1] |= 1 << lane
            w ^= low
    return bits


# ---- reference interpreter ------------------------------------------------

class RefInterp:
    def __init__(self):
        self.binary = str(ref_binary())

    def _run(self, *args, guard_class="long"):
        env = {k: v for k, v in os.environ.items() if k not in
               {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "BROWSER"}}
        return guarded_run([self.binary, *map(str, args)], capture_output=True, text=True, env=env, guard_class=guard_class)

    def check(self, path, *, guard_class="long"):
        done = self._run("check", path, guard_class=guard_class)
        if done.returncode:
            raise AssertionError(f"{path}: {done.stderr.strip()}")
        return json.loads(done.stdout)

    def rejected(self, path):
        done = self._run("check", path)
        return None if done.returncode == 0 else done.stderr.strip()

    def action(self, path, symbol, mut, ins, *extra):
        args = ["run-action", path, symbol, "--mut", ",".join(map(str, mut))]
        if ins:
            args += ["--in", ",".join(map(str, ins))]
        done = self._run(*args, *extra)
        if done.returncode:
            raise AssertionError(f"{path} {symbol} mut={mut} in={ins}: {done.stderr.strip()}")
        result = json.loads(done.stdout)
        amplitudes = list(result["state"].values())
        assert len(amplitudes) == 1, f"{symbol}: output is not a basis state: {result['state']}"
        assert amplitudes[0] == [1, 0], f"{symbol}: phase is not exactly +1: {amplitudes}"
        return [int(v) for v in result["mut"]], [int(v) for v in result["in"]]

    def oracle(self, path, symbol, inputs, budget):
        done = self._run("run-oracle", path, symbol, "--input", ",".join(map(str, inputs)), "--budget", budget)
        if done.returncode:
            raise AssertionError(f"{path} {symbol} {inputs}: {done.stderr.strip()}")
        result = json.loads(done.stdout)
        assert result["code"] == 0, f"{symbol} {inputs}: fault {result}"
        return int(result["payload"])

    def many(self, path, symbol, cases, *extra):
        with ThreadPoolExecutor(int(os.environ.get("BENNETT_TEST_WORKERS", "4"))) as pool:
            return list(pool.map(lambda c: self.action(path, symbol, c[0], c[1], *extra), cases))
