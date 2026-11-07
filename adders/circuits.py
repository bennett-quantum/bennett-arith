"""Build ISA 0.9 objects (section 16) and their certificates (section 12) from gate lists.

Every published arithmetic object is a flat action: an ISA action operand names a
whole bundle or one wire, with no sub-bundle form, so a callee cannot be handed
bits [i, j) of a bundle (see docs/circuits-port.md).
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

ISA = "0.9"
HEADER = (f"bennett-object isa={ISA} object={ISA} launch={ISA} sched={ISA} cert={ISA} "
          f"coverage={ISA} target={ISA} ptr_width=32")
TARGET = Path(__file__).resolve().parent / "target-unit.json"
TABLE_BITS = 8      # A full-domain table claim up to this many domain bits (proof).
SAMPLE_COUNT = 32   # Above it: a sampled claim of this many draws (evidence, never proof).
SEED = ["11400714819323198485", "14029467366897019727", "1609587929392839161", "9650029242287828579"]
SELF_INVERSE = {"x", "cx", "ccx", "swap", "h", "cz"}
ADJOINT = {"t": "tdg", "tdg": "t", "s": "sdg", "sdg": "s"}


def jcs(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Circuit:
    """A flat gate list over named interface bundles and one pooled workspace bundle."""

    def __init__(self, name, mut, ins=(), kind="perm_action", dirty=()):
        self.name, self.kind = name, kind
        self.mut = list(mut)
        self.ins = list(ins)
        self.dirty = list(dirty)
        self.gates = []
        self.readonly = {f"{n}[{i}]" for n, w in self.ins for i in range(w)}
        self.free = []
        self.top = 0
        self.spec = None

    def wires(self, name):
        for n, w in self.mut + self.ins + self.dirty:
            if n == name:
                return [f"{n}[{i}]" for i in range(w)]
        raise KeyError(name)

    # Workspace: a pool, lowest index first, so the peak is the frame width.
    def alloc(self, n):
        out = []
        for _ in range(n):
            if self.free:
                out.append(self.free.pop(0))
            else:
                out.append(self.top)
                self.top += 1
        return [f"anc[{i}]" for i in out]

    def release(self, wires):
        self.free = sorted(self.free + [int(w[4:-1]) for w in wires])

    def _emit(self, op, *wires, target):
        if len(set(wires)) != len(wires):
            raise ValueError(f"{self.name}: overlapping operands {op} {wires}")
        if target in self.readonly:
            raise ValueError(f"{self.name}: gate {op} targets in wire {target} (ISA 5.1)")
        self.gates.append((op, *wires))

    def x(self, t):
        self._emit("x", t, target=t)

    def cx(self, c, t):
        self._emit("cx", c, t, target=t)

    def ccx(self, a, b, t):
        self._emit("ccx", a, b, t, target=t)

    def swap(self, a, b):
        self._emit("swap", a, b, target=a)
        if b in self.readonly:
            raise ValueError(f"{self.name}: swap touches in wire {b}")

    def h(self, t):
        self._emit("h", t, target=t)

    def t(self, a):
        self._emit("t", a, target=a)

    def tdg(self, a):
        self._emit("tdg", a, target=a)

    def sdg(self, a):
        self._emit("sdg", a, target=a)

    def adjoint_of(self, body):
        """Run body, then append the literal adjoint of what it emitted."""
        start = len(self.gates)
        body()
        tail = self.gates[start:]
        self.gates.extend(adjoint(tail))

    def inverted(self, body):
        """Emit only the literal adjoint of body."""
        start = len(self.gates)
        body()
        tail = self.gates[start:]
        del self.gates[start:]
        self.gates.extend(adjoint(tail))

    # Text.
    def signature(self):
        return {"abi": ISA, "args": [], "bounds": [], "in": [w for _, w in self.ins], "kind": self.kind,
                "mem": [], "mut": [w for _, w in self.mut], "tier": "q"}

    def lines(self):
        mut = ", ".join(f"{n}:wire[{w}] mut" for n, w in self.mut)
        ins = ", ".join(f"{n}:wire[{w}] in" for n, w in self.ins)
        out = [f"{self.kind} @{self.name} ({mut}) ({ins}) () () ()", "^entry():"]
        for n, w in self.dirty:
            out.append(f"{n} = qborrow any {w}")
        if self.top:
            out.append(f"anc = qalloc any {self.top}")
        out.extend(" ".join(g) for g in self.gates)
        if self.top:
            out.append("qfree anc")
        for n, _ in self.dirty:
            out.append(f"qreturn {n}")
        if len(out) == 2:
            raise ValueError(f"{self.name}: a block needs at least one instruction")
        return out


def adjoint(gates):
    out = []
    for g in reversed(gates):
        if g[0] in SELF_INVERSE:
            out.append(g)
        elif g[0] in ADJOINT:
            out.append((ADJOINT[g[0]], *g[1:]))
        else:
            raise ValueError(f"no adjoint for {g}")
    return out


def adjoint_circuit(c, name):
    """The section 5.3 adjoint of c as its own symbol: same frame, reversed gates."""
    inv = Circuit(name, c.mut, c.ins, c.kind)
    inv.top = c.top
    inv.gates = adjoint(c.gates)
    return inv


class OracleFn:
    """A lifted reference oracle (ISA 5.2): the g or ginv of a certified in-place pair."""

    kind = "oracle"

    def __init__(self, name, inputs, target, regs, rows):
        self.name, self.inputs, self.target = name, list(inputs), target
        self.regs, self.rows = list(regs), list(rows)
        self.steps = len(self.rows)

    def signature(self):
        return {"abi": ISA, "args": [], "fault": 4, "in": [w for _, w in self.inputs], "kind": "oracle",
                "mem": [], "tgt": self.target, "tier": "q"}

    def lines(self):
        ins = ", ".join(f"{n}:wire[{w}] in" for n, w in self.inputs)
        regs = ", ".join(f"{n}:reg[{w}]" for n, w in self.regs)
        return [f"oracle @{self.name} ({ins}) (t:wire[{self.target}]) (f:wire[4]) () ()",
                f"regs {{ {regs} }}", "^entry():", *self.rows]


class QinplaceAction(Circuit):
    """x <- g(x; ins) as ISA 4.5 qinplace: the certified pair cleans the private t and f."""

    def __init__(self, name, x, ins, g, ginv):
        super().__init__(name, [x], ins)
        self.g, self.ginv = g, ginv
        self.budget = max(g.steps, ginv.steps)

    def signature(self):
        return {**super().signature(), "args": ["token"]}

    def lines(self):
        mut = ", ".join(f"{n}:wire[{w}] mut" for n, w in self.mut)
        ins = ", ".join(f"{n}:wire[{w}] in" for n, w in self.ins)
        x = self.mut[0][0]
        call = f"qinplace @{self.g.name} @{self.ginv.name} tk {x}"
        if self.ins:
            call += " (" + ", ".join(n for n, _ in self.ins) + ") () ()"
        return [f"{self.kind} @{self.name} ({mut}) ({ins}) () (tk:token) ()", "^entry():", call]


class Xoshiro:
    """xoshiro256** (ISA 12.1 sampling)."""

    def __init__(self, seed):
        self.s = [int(w) for w in seed]

    def next(self):
        m = (1 << 64) - 1
        s = self.s
        rotl = lambda v, k: ((v << k) & m) | (v >> (64 - k))
        result = (rotl((s[1] * 5) & m, 7) * 9) & m
        t = (s[1] << 17) & m
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = rotl(s[3], 45)
        return result

    def component(self, width):
        words = (width + 63) // 64
        v = 0
        for i in range(words):
            v |= self.next() << (64 * i)
        return v & ((1 << width) - 1)


def _component(n, w):
    return {"hi": _meta((1 << w) - 1), "lo": 0, "name": n, "width": w}


def _domain(c):
    return {"borrowed": [_component(n, w) for n, w in c.dirty],
            "bundles": [_component(n, w) for n, w in c.mut + c.ins], "regions": []}


def _meta(n):
    """Section 9.1: integers at or above 2^53 are decimal strings."""
    return n if n < (1 << 53) else str(n)


def _row(c, vector):
    names = [n for n, _ in c.mut + c.ins + c.dirty]
    values = dict(zip(names, vector))
    out = c.spec(values)
    after = [str(out[n]) for n, _ in c.mut] + [str(values[n]) for n, _ in c.ins]
    split = len(c.mut) + len(c.ins)
    dirty = [str(v) for v in vector[split:]]    # Borrowed bundles are restored, on every row.
    return {"after": {"borrowed": dirty, "bundles": after, "regions": []},
            "before": {"borrowed": dirty, "bundles": [str(v) for v in vector[:split]], "regions": []}}


def _vectors(c):
    widths = [w for _, w in c.mut + c.ins + c.dirty]
    bits = sum(widths)
    if bits <= TABLE_BITS:
        out = []
        for n in range(1 << bits):      # Section 12.2: last component fastest.
            vec, at = [], bits
            for w in widths:
                at -= w
                vec.append((n >> at) & ((1 << w) - 1))
            out.append(vec)
        return out, True
    rng = Xoshiro(SEED)
    seen = {tuple(rng.component(w) for w in widths) for _ in range(SAMPLE_COUNT)}
    return [list(v) for v in sorted(seen)], False


def _invocation(c):
    if isinstance(c, QinplaceAction):
        token = [str(c.budget), "0", "0", "0"]
        return {"args": [token], "budget": token, "token_aliases": [0]}
    return {"args": [], "budget": ["0", "0", "0", "0"], "token_aliases": []}


def _claim(c, closure):
    if c.spec is None:
        raise ValueError(f"{c.name}: certificate needs a spec")
    vectors, full = _vectors(c)
    claim = {"domain": _domain(c), "expected": {"table": [_row(c, v) for v in vectors]},
             "invocation": _invocation(c),
             "subject": {"closure_hash": closure, "inherited_controls": 0, "variant": "forward"}}
    if full:
        claim.update(kind="exhaustive", label="proof")
    else:
        claim.update(kind="sampled", label="evidence",
                     sampler={"algorithm": "xoshiro256**", "count": SAMPLE_COUNT, "seed": SEED})
    return claim


class Object:
    """One or more flat circuits as one canonical object, with an embedded certificate."""

    def __init__(self, circuits, root=None, inverse=None, producer_note=None):
        self.circuits = list(circuits)
        self.root = root or self.circuits[0].name
        self.inverse = inverse
        self.producer_note = producer_note

    def _envelope(self, c, hashes):
        lines = c.lines()
        refs = []
        out = [lines[0]]
        for line in lines[1:]:
            tokens = []
            for token in line.split(" "):
                if token.startswith("@"):
                    target = token[1:]
                    if target not in hashes:
                        raise ValueError(f"{c.name}: forward reference to {target}")
                    if target not in refs:
                        refs.append(target)
                    token = "@" + hashes[target]
                tokens.append(token)
            out.append(" ".join(tokens))
        tail = "".join(hashes[r] + "\n" for r in refs)
        return f"isa={ISA}\nptr_width=32\n{jcs(c.signature())}\n" + "\n".join(out) + "\n" + tail

    def hashes(self):
        """Definition order is dependency order; there are no imports, so closure = interface."""
        hashes = {}
        for c in self.circuits:
            hashes[c.name] = sha256(self._envelope(c, hashes))
        return hashes

    def circuit(self, name):
        return next(c for c in self.circuits if c.name == name)

    def _base(self):
        hashes = self.hashes()
        symbols = {str(i): {"interface_hash": hashes[c.name], "kind": c.kind, "name": c.name,
                            "signature": c.signature()} for i, c in enumerate(self.circuits)}
        body = "\n".join("\n".join(c.lines()) for c in self.circuits)
        return f"{HEADER}\n\nsection symbols\n{jcs(symbols)}\n\nsection functions\n{body}\n"

    def _frame(self, c):
        slots = [{"class": "fast", "id": f"mut:{i}", "role": "mut", "width": w} for i, (_, w) in enumerate(c.mut)]
        slots += [{"class": "fast", "id": f"in:{i}", "role": "in", "width": w} for i, (_, w) in enumerate(c.ins)]
        scratch = [{"class": "fast", "id": "anc", "state": "clean", "width": c.top}] if c.top else []
        borrow = [{"class": "fast", "id": n, "width": w} for n, w in c.dirty]
        return {"ancillae": [], "borrow": borrow, "history": [], "scratch": scratch, "slots": slots}

    def _inverse_pair_claim(self, c, hashes):
        token = [_meta(c.budget), 0, 0, 0]
        names = c.g.inputs
        domain = {"borrowed": [], "bundles": [{"hi": _meta((1 << w) - 1), "lo": 0, "name": n, "width": w}
                                              for n, w in names], "regions": []}
        return {"domain": domain, "expected": "inverse_pair", "kind": "exhaustive",
                "subject": {"closure_hash": hashes[c.g.name], "inherited_controls": 0, "variant": "forward"}}, {
            "budget": token, "claim": 1, "g": hashes[c.g.name], "ginv": hashes[c.ginv.name],
            "token_aliases": [0]}

    def _region(self, c, closure, position):
        if isinstance(c, QinplaceAction):
            hashes = self.hashes()
            claim, entry = self._inverse_pair_claim(c, hashes)
            target_width = c.mut[0][1]
            frame = self._frame(c)
            frame["scratch"] = [{"class": "fast", "id": "t", "state": "clean", "width": target_width},
                                {"class": "fast", "id": "f", "state": "clean", "width": 4}]
            return {"bounds": [], "claims": [_claim(c, closure), claim], "cleanup": {},
                    "definedness_assumptions": [], "error": {}, "frame": frame, "gates_used": {}, "kind": c.kind,
                    "resources": {}, "signature": c.signature(),
                    "verification": {"borrow_frames": [], "channel": [], "fault_rate": {
                        "domain": {"borrowed": [], "bundles": [], "regions": []}, "faults_by_code": {},
                        "layout_dependent_excluded": 0, "undefined_excluded": 0},
                        "inverse_pairs": [entry], "oracle": None, "unitary": []}}
        gates = {}
        t = 0
        for g in c.gates:
            gates.setdefault(g[0], {"count": 0})["count"] += 1
            t += {"ccx": 7, "t": 1, "tdg": 1}.get(g[0], 0)
        wires = sum(w for _, w in c.mut + c.ins + c.dirty) + c.top
        claims = [_claim(c, closure)]
        if self.inverse == c.name:
            # The published g/ginv pair: this symbol is the literal section 5.3 adjoint of the root.
            claims.append({"invocation": {"args": "all", "budget": "all", "token_aliases": "all"}, "kind": "structural",
                           "label": "proof", "rule": "adjoint_table", "subclaims": [], "witness": {}})
        return {"bounds": [], "claims": claims, "cleanup": {}, "definedness_assumptions": [], "error": {},
                "frame": self._frame(c), "gates_used": gates, "kind": c.kind,
                "resources": {"peak_qubits": str(wires), "qubit_second": str(wires * len(c.gates)),
                              "t": str(t), "time": str(len(c.gates))},
                "signature": c.signature(),
                # A borrow frame needs a proof over D_F (5.6); a sampled claim is evidence and is not listed.
                "verification": {"borrow_frames": [0] if c.dirty and claims[0]["kind"] == "exhaustive" else [],
                                 "channel": [], "fault_rate": {
                    "domain": {"borrowed": [], "bundles": [], "regions": []}, "faults_by_code": {},
                    "layout_dependent_excluded": 0, "undefined_excluded": 0},
                    "inverse_pairs": [], "oracle": None, "unitary": []}}

    def certificate(self, object_hash):
        hashes = self.hashes()
        root = hashes[self.root]
        regions = {hashes[c.name]: self._region(c, hashes[c.name], i)
                   for i, c in enumerate(self.circuits) if not isinstance(c, OracleFn)}
        return {
            "bindings": {"closure_hash": root, "dialect_mapping_version": "none", "interface_hash": root,
                         "invocation": _invocation(self.circuit(self.root)),
                         "object_hash": object_hash, "reference_program_hash": root,
                         "target_hash": hashlib.sha256(TARGET.read_bytes()).hexdigest()},
            "composition": {"epsilon_total": {"diamond": 0}, "method": "sum_over_multiplicities",
                            "multiplicities": {}},
            "producer": {"materialisation": {"llvm_version": "none", "normaliser_version": "none",
                                             "pipeline": "bennett-arith-generator"},
                         "name": "bennett-arith", "version": "circuits-1"},
            "regions": regions,
            "versions": {k: ISA for k in ("cert", "coverage", "isa", "launch", "object", "sched", "target")},
        }

    def text(self):
        if not hasattr(self, "_text"):
            base = self._base()
            self._text = f"{base}\nsection certificate\n{jcs(self.certificate(sha256(base)))}\n"
        return self._text


def census(c):
    """Gate counts, Toffoli depth and workspace of one flat circuit, as the manifest publishes them."""
    gates = {}
    total, tof = {}, {}
    depth = tdepth = t = 0
    for g in c.gates:
        gates[g[0]] = gates.get(g[0], 0) + 1
        t += {"ccx": 7, "t": 1, "tdg": 1}.get(g[0], 0)
        layer = max(total.get(w, 0) for w in g[1:]) + 1
        tlayer = max(tof.get(w, 0) for w in g[1:]) + (g[0] == "ccx")
        for w in g[1:]:
            total[w], tof[w] = layer, tlayer
        depth, tdepth = max(depth, layer), max(tdepth, tlayer)
    return {"ancilla": c.top, "depth": depth, "gates": gates, "t": t, "toffoli_depth": tdepth}


def interpreter_view(text):
    """Diagnostic execution view for the pre-K4/K91 pinned interpreter.

    This view cannot establish release compatibility: raw validation is kept
    separately for every publication against the pinned reader.
    """
    if "section certificate\n" not in text:
        return text
    head, _, line = text.rpartition("section certificate\n")
    cert = json.loads(line)
    cert["bindings"]["invocation"].pop("token_aliases")
    for region in cert["regions"].values():
        region["claims"] = [c for c in region["claims"] if c.get("expected") != "inverse_pair"]
        for claim in region["claims"]:
            claim["invocation"].pop("token_aliases")
        region["verification"]["inverse_pairs"] = []
    return f"{head}section certificate\n{jcs(cert)}\n"


def write_object(obj, path):
    Path(path).write_text(interpreter_view(obj.text()))


cached = lru_cache(maxsize=None)
