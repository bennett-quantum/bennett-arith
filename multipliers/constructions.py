"""Multipliers as flat ISA 0.9 permutation actions.

muladd: z += a*b (mod 2^R). mul: z ^= a*b (mod 2^R), which also fits an oracle target.
Schoolbook, Karatsuba (three retained sub-products, one Bennett reversal at the top) and the
Sun-Borissov 2026 polylog-depth QCLA tree (arXiv:2604.09847). Everything is palindromic, so
ISA 6.2's matched cleanup admits it; see docs/circuits-port.md for why that shapes Karatsuba.
"""
import math

from adders.circuits import Circuit, Object, cached
from adders.constructions import add_padded, qcla_clean_block

KARATSUBA_BASE = 4


def muladd_school_block(c, a, b, z):
    """z += a*b; a and b only read."""
    R = len(z)
    for i in range(min(len(b), R)):
        L = min(len(a), R - i)
        pp = c.alloc(L)

        def load(i=i, L=L, pp=pp):
            for k in range(L):
                c.ccx(a[k], b[i], pp[k])
        load()
        add_padded(c, pp, z[i:])
        load()
        c.release(pp)


def _xor_form(name, W, R, block):
    """z ^= a*b via a clean accumulator: compute, XOR out, literal adjoint."""
    c = Circuit(name, [("z", R)], [("a", W), ("b", W)])
    a, b, z = c.wires("a"), c.wires("b"), c.wires("z")
    acc = c.alloc(R)
    start = len(c.gates)
    block(c, a, b, acc)
    body = c.gates[start:]
    for s, t in zip(acc, z):
        c.cx(s, t)
    c.gates.extend(reversed(body))     # Only self-inverse gates.
    c.release(acc)
    c.spec = lambda v: {"z": v["z"] ^ ((v["a"] * v["b"]) % (1 << R))}
    return Object([c])


@cached
def muladd_school(W, R):
    c = Circuit(f"arith.muladd.school.w{W}.r{R}", [("z", R)], [("a", W), ("b", W)])
    muladd_school_block(c, c.wires("a"), c.wires("b"), c.wires("z"))
    c.spec = lambda v: {"z": (v["z"] + v["a"] * v["b"]) % (1 << R)}
    return Object([c])


@cached
def mul_school(W, R):
    return _xor_form(f"arith.mul.school.w{W}.r{R}", W, R, muladd_school_block)


# ---- Karatsuba: ab = P0 + (P1 - P0 - P2) B + P2 B^2, B = 2^h ------------------------

def _sum_register(c, lo, hi):
    """A clean register holding lo + hi, h + 1 bits; hi's temporary copy is returned clean."""
    out = c.alloc(len(lo) + 1)
    for s, t in zip(lo, out):
        c.cx(s, t)
    copy = c.alloc(len(hi))
    for s, t in zip(hi, copy):
        c.cx(s, t)
    add_padded(c, copy, out)
    for s, t in zip(hi, copy):
        c.cx(s, t)
    c.release(copy)
    return out


def karatsuba_product(c, a, b):
    """A retained clean register holding a*b on 2|a| bits; every sub-product stays live."""
    n = len(a)
    if n <= KARATSUBA_BASE:
        P = c.alloc(2 * n)
        muladd_school_block(c, a, b, P)
        return P
    h = (n + 1) // 2
    P0 = karatsuba_product(c, a[:h], b[:h])
    P2 = karatsuba_product(c, a[h:], b[h:])
    sa = _sum_register(c, a[:h], a[h:])
    sb = _sum_register(c, b[:h], b[h:])
    P1 = karatsuba_product(c, sa, sb)
    P = c.alloc(2 * n)
    for s, t in zip(P0, P):
        c.cx(s, t)
    for s, t in zip(P2, P[2 * h:]):
        c.cx(s, t)
    add_padded(c, P1, P[h:])
    c.inverted(lambda: add_padded(c, P0, P[h:]))
    c.inverted(lambda: add_padded(c, P2, P[h:]))
    return P


def _karatsuba_compute(c, a, b):
    start = len(c.gates)
    P = karatsuba_product(c, a, b)
    return P, c.gates[start:]


@cached
def muladd_karatsuba(W, R):
    c = Circuit(f"arith.muladd.karatsuba.w{W}.r{R}", [("z", R)], [("a", W), ("b", W)])
    P, body = _karatsuba_compute(c, c.wires("a"), c.wires("b"))
    add_padded(c, P, c.wires("z"))
    c.gates.extend(reversed(body))
    c.spec = lambda v: {"z": (v["z"] + v["a"] * v["b"]) % (1 << R)}
    return Object([c])


@cached
def mul_karatsuba(W, R):
    c = Circuit(f"arith.mul.karatsuba.w{W}.r{R}", [("z", R)], [("a", W), ("b", W)])
    P, body = _karatsuba_compute(c, c.wires("a"), c.wires("b"))
    for s, t in zip(P, c.wires("z")):
        c.cx(s, t)
    c.gates.extend(reversed(body))
    c.spec = lambda v: {"z": v["z"] ^ ((v["a"] * v["b"]) % (1 << R))}
    return Object([c])


def _cuccaro(n):
    return 2 * n - 3 if n >= 2 else 0


@cached
def karatsuba_forward_toffoli(n):
    if n <= KARATSUBA_BASE:
        return sum(2 * n + _cuccaro(2 * n - i) for i in range(n))
    h = (n + 1) // 2
    return (karatsuba_forward_toffoli(h) + karatsuba_forward_toffoli(n - h) + karatsuba_forward_toffoli(h + 1)
            + 2 * _cuccaro(h + 1) + 3 * _cuccaro(2 * n - h))


def karatsuba_toffoli(W, R):
    """muladd form: compute, one adder into z, literal reversal. The mul form omits the adder."""
    return 2 * karatsuba_forward_toffoli(W) + _cuccaro(R)


@cached
def _k_retained(n):
    if n <= KARATSUBA_BASE:
        return 2 * n
    h = (n + 1) // 2
    return _k_retained(h) + _k_retained(n - h) + 2 * (h + 1) + _k_retained(h + 1) + 2 * n


@cached
def _k_peak(n):
    """Pool peak above what the caller holds when karatsuba_product(n) starts."""
    if n <= KARATSUBA_BASE:
        return 2 * n + 2 * n + 1    # P, a partial product plus pad filling P's width, one Cuccaro ancilla.
    h = (n + 1) // 2
    held = 0
    peak = _k_peak(h)
    held += _k_retained(h)
    peak = max(peak, held + _k_peak(n - h))
    held += _k_retained(n - h)
    # Two sum registers, each with a transient copy, pad and Cuccaro ancilla.
    for _ in range(2):
        peak = max(peak, held + (h + 1) + (n - h) + (h + 1 - (n - h)) + 1)
        held += h + 1
    peak = max(peak, held + _k_peak(h + 1))
    held += _k_retained(h + 1) + 2 * n
    # Sign-corrections: the widest pad is for the shortest source.
    t = 2 * n - h
    pad = max(t - min(2 * h + 2, t), t - min(2 * h, t), t - min(2 * (n - h), t))
    return max(peak, held + pad + 1)


def karatsuba_ancilla(W, R):
    final = max(0, R - 2 * W) + (1 if R >= 2 else 0)    # The adder into z (muladd form).
    return max(_k_peak(W), _k_retained(W) + final)


# ---- Sun-Borissov polylog-depth tree --------------------------------------------

def fast_copy(c, src, n_copies):
    """n_copies registers holding src (the first is src itself): doubling CX layers."""
    populated = [list(src)]
    while len(populated) < n_copies:
        fresh = []
        for reg in populated:
            if len(populated) + len(fresh) >= n_copies:
                break
            tgt = c.alloc(len(src))
            for s, t in zip(reg, tgt):
                c.cx(s, t)
            fresh.append(tgt)
        populated += fresh
    return populated


def tree_block(c, a, b, z):
    """z ^= a*b with |z| = 2|a|: broadcast, one Toffoli layer, QCLA tree, XOR out, reverse."""
    W = len(a)
    start = len(c.gates)
    xs = fast_copy(c, a, W)
    ys = []
    for i in range(W):
        first = c.alloc(W)
        c.cx(b[i], first[0])
        filled = 1
        while filled < W:
            for k in range(min(filled, W - filled)):
                c.cx(first[k], first[filled + k])
            filled += min(filled, W - filled)
        ys.append(first)
    pps = []
    for i in range(W):
        pp = c.alloc(W)
        for k in range(W):
            c.ccx(ys[i][k], xs[i][k], pp[k])
        pps.append(pp)
    current = pps
    width = W
    level = 0
    while len(current) > 1:
        shift = 1 << level
        pad_w = width + shift
        nxt = []
        for r in range(len(current) // 2):
            left, right = current[2 * r], current[2 * r + 1]
            lp, rp = c.alloc(pad_w), c.alloc(pad_w)
            for k in range(width):
                c.cx(left[k], lp[k])
            for k in range(width):
                c.cx(right[k], rp[k + shift])
            out = c.alloc(pad_w + 1)
            qcla_clean_block(c, lp, rp, out, keep_flat=True)
            nxt.append(out)
        if len(current) % 2:
            leftover = current[-1]
            out = c.alloc(pad_w + 1)
            for k in range(width):
                c.cx(leftover[k], out[k])
            nxt.append(out)
        current = nxt
        width = pad_w + 1
        level += 1
    body = c.gates[start:]
    root = current[0]
    for k in range(min(len(root), len(z))):
        c.cx(root[k], z[k])
    c.gates.extend(reversed(body))


@cached
def mul_tree(W):
    R = 2 * W
    c = Circuit(f"arith.mul.tree.w{W}", [("z", R)], [("a", W), ("b", W)])
    tree_block(c, c.wires("a"), c.wires("b"), c.wires("z"))
    c.spec = lambda v: {"z": v["z"] ^ (v["a"] * v["b"])}
    return Object([c])


def _qcla_toffoli(W):
    return 5 * W - 3 * bin(W).count("1") - 3 * int(math.log2(W)) - 1


@cached
def tree_shape(W):
    """Per level: (adders, pad width, leftover). Levels are ceil(log2 W)."""
    out = []
    count, width, level = W, W, 0
    while count > 1:
        pad = width + (1 << level)
        out.append((count // 2, pad, count % 2))
        count = count // 2 + count % 2
        width = pad + 1
        level += 1
    return out


def tree_toffoli(W):
    total = W * W
    for adders, pad, _ in tree_shape(W):
        total += adders * _qcla_toffoli(pad)
    return 2 * total


def tree_ancilla(W):
    """The pool peak, walked in emission order: nothing is released before the reversal."""
    held = (W - 1) * W + W * W + W * W     # xs beyond a itself, ys, partial products.
    for adders, pad, left in tree_shape(W):
        flat = pad - bin(pad).count("1") - int(math.log2(pad))
        for _ in range(adders):
            held += 2 * pad + pad + 1 + flat
        held += left * (pad + 1)
    return held


def tree_toffoli_depth_bound(W):
    """Partial-product layer plus one QCLA per level, each direction; ASAP may overlap them."""
    if W == 1:
        return 2
    return 2 * (1 + sum(_qcla_single_depth(pad) for _, pad, _ in tree_shape(W)))


@cached
def _qcla_single_depth(W):
    """Toffoli depth of qcla_clean_block on W bits, by layering the block itself."""
    c = Circuit("depth", [("a", W), ("b", W), ("z", W + 1)])
    qcla_clean_block(c, c.wires("a"), c.wires("b"), c.wires("z"))
    layers = {}
    deepest = 0
    for g in c.gates:
        wires = g[1:]
        layer = max((layers.get(w, 0) for w in wires), default=0) + (g[0] == "ccx")
        for w in wires:
            layers[w] = layer
        deepest = max(deepest, layer)
    return deepest
