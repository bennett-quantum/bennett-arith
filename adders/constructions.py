"""Adders and the dialect's library bijections as flat ISA 0.9 actions.

Design inputs: Cuccaro et al. 2004 (quant-ph/0410184), Draper-Kutin-Rains-Svore 2004
(quant-ph/0406142), Gidney 2018 (arXiv:1709.06648). Formulas: docs/circuits-port.md.
"""
import math

from adders.circuits import Circuit, Object, OracleFn, QinplaceAction, adjoint_circuit, cached


# ---- blocks (wire lists; every workspace wire returns to zero) --------------

def cuccaro_block(c, a, b):
    """b += a mod 2^|b|; a is written and restored; one clean ancilla from W >= 2."""
    W = len(a)
    if W != len(b):
        raise ValueError("cuccaro: unequal widths")
    if W == 0:
        return
    if W == 1:
        c.cx(a[0], b[0])
        return
    X = c.alloc(1)[0]
    if W == 2:
        c.cx(a[0], b[0]); c.cx(a[0], X)
        c.cx(a[1], b[1]); c.cx(a[0], b[1])
        c.ccx(X, b[0], b[1])
        c.cx(a[0], X); c.cx(X, b[0])
        c.release([X])
        return
    c.cx(a[0], b[0]); c.cx(a[0], X); c.ccx(X, b[0], a[0])
    for i in range(1, W - 2):
        c.cx(a[i], b[i]); c.cx(a[i], a[i - 1]); c.ccx(a[i - 1], b[i], a[i])
    c.cx(a[W - 2], b[W - 2]); c.cx(a[W - 2], a[W - 3])
    c.cx(a[W - 1], b[W - 1]); c.cx(a[W - 2], b[W - 1]); c.ccx(a[W - 3], b[W - 2], b[W - 1])
    c.cx(a[W - 2], a[W - 3]); c.cx(a[W - 3], b[W - 2])
    for i in range(W - 3, 0, -1):
        c.ccx(a[i - 1], b[i], a[i]); c.cx(a[i], a[i - 1]); c.cx(a[i - 1], b[i])
    c.ccx(X, b[0], a[0]); c.cx(a[0], X); c.cx(X, b[0])
    c.release([X])


def cuccaro_carry_block(c, a, b, z):
    """b += a, z ^= carry-out: full MAJ/UMA chain (2W Toffoli, one ancilla)."""
    W = len(a)
    X = c.alloc(1)[0]
    prev = X
    for i in range(W):
        c.cx(a[i], b[i]); c.cx(a[i], prev); c.ccx(prev, b[i], a[i])
        prev = a[i]
    c.cx(a[W - 1], z)
    for i in range(W - 1, -1, -1):
        prev = a[i - 1] if i else X
        c.ccx(prev, b[i], a[i]); c.cx(a[i], prev); c.cx(prev, b[i])
    c.release([X])


def add_padded(c, src, dst):
    """dst += src, with src shorter or equal: zero pad wires take carries and return clean."""
    if len(src) > len(dst):
        src = src[:len(dst)]
    pad = c.alloc(len(dst) - len(src))
    cuccaro_block(c, src + pad, dst)
    c.release(pad)


def add_const_block(c, X, k, ctrl=None, sub=False):
    """X += k (or -= k) under an optional control: load k, add, unload."""
    K = c.alloc(len(X))

    def load():
        for i in range(len(X)):
            if (k >> i) & 1:
                if ctrl is None:
                    c.x(K[i])
                else:
                    c.cx(ctrl, K[i])
    load()
    if sub:
        c.inverted(lambda: cuccaro_block(c, K, X))
    else:
        cuccaro_block(c, K, X)
    load()
    c.release(K)


def ripple_block(c, a, b, s):
    """s ^= a + b over |a|+1 bits, a and b only read; carries and propagates in workspace."""
    W = len(a)
    p = c.alloc(W)
    carry = c.alloc(W)

    def compute():
        for i in range(W):
            c.cx(a[i], p[i]); c.cx(b[i], p[i])
            c.ccx(a[i], b[i], carry[i])
            if i:
                c.ccx(p[i], carry[i - 1], carry[i])
    compute()
    c.cx(p[0], s[0])
    for i in range(1, W):
        c.cx(p[i], s[i]); c.cx(carry[i - 1], s[i])
    c.cx(carry[W - 1], s[W])
    c.inverted(compute)
    c.release(p + carry)


def and_compute(c, x, y, t):
    """t = x AND y on clean t: 4 T, exact on every basis input with t = 0 (Gidney 2018 Fig. 3)."""
    c.h(t); c.t(t); c.cx(y, t); c.tdg(t); c.cx(x, t); c.t(t); c.cx(y, t); c.tdg(t); c.h(t); c.sdg(t)


def gidney_block(c, a, b, and_gate):
    """b += a with W-1 AND ancillas; a is written and restored."""
    W = len(a)
    if W == 1:
        c.cx(a[0], b[0])
        return
    carries = c.alloc(W - 1)
    prev = None
    for i in range(W - 1):
        if prev is not None:
            c.cx(prev, a[i]); c.cx(prev, b[i])
        and_gate(a[i], b[i], carries[i])
        if prev is not None:
            c.cx(prev, carries[i])
        prev = carries[i]
    c.cx(prev, b[W - 1]); c.cx(a[W - 1], b[W - 1])
    for i in range(W - 2, -1, -1):
        prev = carries[i - 1] if i else None
        if prev is not None:
            c.cx(prev, carries[i])
        c.inverted(lambda i=i: and_gate(a[i], b[i], carries[i]))
        if prev is not None:
            c.cx(prev, a[i])
        c.cx(a[i], b[i])
    c.release(carries)


def qcla_clean_block(c, a, b, Z, keep_flat=False):
    """Draper et al. section 4.1: Z = a + b on clean Z; b written and restored, a only read.

    keep_flat holds the internal lookahead wires (clean again on return) out of the pool, so
    adders running side by side in a tree do not serialise on shared wires.
    """
    W = len(a)
    T = int(math.log2(W)) if W >= 2 else 0
    n_anc = W - bin(W).count("1") - T
    flat = c.alloc(n_anc)
    offsets = {}
    at = 0
    for t in range(1, T):
        offsets[t] = at
        at += (W >> t) - 1
    if at != n_anc:
        raise AssertionError((W, at, n_anc))
    A = lambda k: a[k - 1]          # 1-based, as in the paper.
    B = lambda k: b[k - 1]
    Zw = lambda k: Z[k - 1]
    P = lambda t, m: flat[offsets[t] + m - 1]
    for k in range(1, W + 1):
        c.ccx(A(k), B(k), Zw(k + 1))
    for k in range(2, W + 1):
        c.cx(A(k), B(k))

    def p_rounds():
        for t in range(1, T):
            for m in range(1, (W >> t)):
                c1 = B(2 * m + 1) if t == 1 else P(t - 1, 2 * m)
                c2 = B(2 * m + 2) if t == 1 else P(t - 1, 2 * m + 1)
                c.ccx(c1, c2, P(t, m))
    p_rounds()
    for t in range(1, T + 1):
        for m in range(0, W >> t):
            ctrl = B(2 * m + 2) if t == 1 else P(t - 1, 2 * m + 1)
            c.ccx(Zw((m << t) + (1 << (t - 1)) + 1), ctrl, Zw((m << t) + (1 << t) + 1))
    T_C = int(math.log2((2 * W) // 3)) if W >= 3 else 0
    for t in range(T_C, 0, -1):
        for m in range(1, ((W - (1 << (t - 1))) >> t) + 1):
            ctrl = B(2 * m + 1) if t == 1 else P(t - 1, 2 * m)
            c.ccx(Zw((m << t) + 1), ctrl, Zw((m << t) + (1 << (t - 1)) + 1))
    c.inverted(p_rounds)
    for k in range(1, W + 1):
        c.cx(B(k), Zw(k))
    c.cx(A(1), Zw(1))
    for k in range(2, W + 1):
        c.cx(A(k), B(k))
    if not keep_flat:
        c.release(flat)


# ---- single-direction adders -----------------------------------------------

@cached
def cuccaro(W):
    c = Circuit(f"arith.add.cuccaro.w{W}", [("a", W), ("b", W)])
    cuccaro_block(c, c.wires("a"), c.wires("b"))
    c.spec = lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W)}
    return Object([c])


@cached
def cuccaro_carry(W):
    c = Circuit(f"arith.add.cuccaro_carry.w{W}", [("a", W), ("b", W), ("z", 1)])
    cuccaro_carry_block(c, c.wires("a"), c.wires("b"), "z[0]")
    c.spec = lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W), "z": v["z"] ^ ((v["a"] + v["b"]) >> W)}
    return Object([c])


@cached
def ripple(W):
    c = Circuit(f"arith.add.ripple.w{W}", [("s", W + 1)], [("a", W), ("b", W)])
    ripple_block(c, c.wires("a"), c.wires("b"), c.wires("s"))
    c.spec = lambda v: {"s": v["s"] ^ (v["a"] + v["b"])}
    return Object([c])


@cached
def gidney(W):
    c = Circuit(f"arith.add.gidney.w{W}", [("a", W), ("b", W)])
    gidney_block(c, c.wires("a"), c.wires("b"), c.ccx)
    c.spec = lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W)}
    return Object([c])


@cached
def gidney_t(W):
    c = Circuit(f"arith.add.gidney_t.w{W}", [("a", W), ("b", W)], kind="action")
    gidney_block(c, c.wires("a"), c.wires("b"), lambda x, y, t: and_compute(c, x, y, t))
    c.spec = lambda v: {"a": v["a"], "b": (v["a"] + v["b"]) % (1 << W)}
    return Object([c])


@cached
def qcla(W):
    c = Circuit(f"arith.add.qcla.w{W}", [("z", W + 1)], [("a", W), ("b", W)])
    a, b, z = c.wires("a"), c.wires("b"), c.wires("z")
    G = c.alloc(W + 1)
    p = c.alloc(W)

    def compute():
        for i in range(W):
            c.cx(b[i], p[i])
        qcla_clean_block(c, a, p, G)
    compute()
    for i in range(W + 1):
        c.cx(G[i], z[i])
    c.inverted(compute)
    c.release(G + p)
    c.spec = lambda v: {"z": v["z"] ^ (v["a"] + v["b"])}
    return Object([c])


# ---- library bijections (dialect 8.7, TDL-5(b)): g plus its literal adjoint ----

def pair(c, inverse_name, inverse_spec):
    inv = adjoint_circuit(c, inverse_name)
    inv.spec = inverse_spec
    return Object([c, inv], root=c.name, inverse=inv.name)


@cached
def add_in(W):
    mask = (1 << W) - 1
    c = Circuit(f"arith.bij.add.w{W}", [("x", W)], [("k", W)])
    x, k = c.wires("x"), c.wires("k")
    copy = c.alloc(W)
    for i in range(W):
        c.cx(k[i], copy[i])
    cuccaro_block(c, copy, x)
    for i in range(W):
        c.cx(k[i], copy[i])
    c.release(copy)
    c.spec = lambda v: {"x": (v["x"] + v["k"]) & mask}
    return pair(c, f"arith.bij.sub.w{W}", lambda v: {"x": (v["x"] - v["k"]) & mask})


@cached
def add_const(W, k):
    mask = (1 << W) - 1
    k &= mask
    c = Circuit(f"arith.bij.addk.w{W}.k{k:x}", [("x", W)])
    add_const_block(c, c.wires("x"), k)
    c.spec = lambda v: {"x": (v["x"] + k) & mask}
    return pair(c, f"arith.bij.subk.w{W}.k{k:x}", lambda v: {"x": (v["x"] - k) & mask})


@cached
def xor_in(W):
    c = Circuit(f"arith.bij.xor.w{W}", [("x", W)], [("k", W)])
    for s, t in zip(c.wires("k"), c.wires("x")):
        c.cx(s, t)
    c.spec = lambda v: {"x": v["x"] ^ v["k"]}
    return pair(c, f"arith.bij.xor_inv.w{W}", c.spec)


@cached
def xor_const(W, k):
    c = Circuit(f"arith.bij.xork.w{W}.k{k:x}", [("x", W)])
    for i, t in enumerate(c.wires("x")):
        if (k >> i) & 1:
            c.x(t)
    if not k:
        # The identity is still a callable symbol; a self-cancelling pair keeps the block nonempty.
        c.x("x[0]"); c.x("x[0]")
    c.spec = lambda v: {"x": v["x"] ^ k}
    return pair(c, f"arith.bij.xork_inv.w{W}.k{k:x}", c.spec)


def _permute(c, wires, position):
    """Realise wire i moving to position(i) by swaps along the cycles."""
    W = len(wires)
    seen = [False] * W
    for start in range(W):
        if seen[start]:
            continue
        cycle = []
        i = start
        while not seen[i]:
            seen[i] = True
            cycle.append(i)
            i = position(i)
        # Walk the cycle: the value at cycle[0] travels forward by exchanges.
        for j in range(1, len(cycle)):
            c.swap(wires[cycle[0]], wires[cycle[j]])


@cached
def rotl_const(W, r):
    if not 0 <= r < W:
        raise ValueError("rotate amount outside [0, W)")
    mask = (1 << W) - 1
    c = Circuit(f"arith.bij.rotl.w{W}.r{r}", [("x", W)])
    if r == 0:
        # A rotate by zero is the identity; one self-cancelling pair keeps the block nonempty.
        c.x("x[0]"); c.x("x[0]")
    else:
        _permute(c, c.wires("x"), lambda i: (i + r) % W)
    c.spec = lambda v: {"x": ((v["x"] << r) | (v["x"] >> (W - r))) & mask}
    return pair(c, f"arith.bij.rotr.w{W}.r{r}",
                lambda v: {"x": ((v["x"] >> r) | (v["x"] << (W - r))) & mask})


@cached
def negate(W):
    mask = (1 << W) - 1
    c = Circuit(f"arith.bij.neg.w{W}", [("x", W)])
    x = c.wires("x")
    for t in x:
        c.x(t)
    add_const_block(c, x, 1)
    c.spec = lambda v: {"x": -v["x"] & mask}
    return pair(c, f"arith.bij.neg_inv.w{W}", c.spec)


@cached
def bswap(W):
    if W % 16:
        raise ValueError("bswap needs a width that is a multiple of 16 (LLVM bswap)")
    c = Circuit(f"arith.bij.bswap.w{W}", [("x", W)])
    x = c.wires("x")
    n = W // 8
    for byte in range(n // 2):
        for bit in range(8):
            c.swap(x[byte * 8 + bit], x[(n - 1 - byte) * 8 + bit])
    c.spec = lambda v: {"x": int.from_bytes(v["x"].to_bytes(n, "little"), "big")}
    return pair(c, f"arith.bij.bswap_inv.w{W}", c.spec)


def _check_modulus(W, m):
    if not 1 <= m <= (1 << W):
        raise ValueError(f"modulus {m} outside [1, 2^{W}]")


def _below(c, X, m, flag, ctrl=None):
    """flag ^= (X < m) [and ctrl]; X, with its clear top bit, is restored."""
    add_const_block(c, X, m, sub=True)
    if ctrl is None:
        c.cx(X[-1], flag)
    else:
        c.ccx(ctrl, X[-1], flag)
    add_const_block(c, X, m)


def _addmod_core(c, X, m, v, load):
    """Under v, with X < m: X = (X + k) mod m; load(K) XORs k into clean K under v."""
    f = c.alloc(1)[0]

    def add_k(sub=False):
        K = c.alloc(len(X))
        load(K)
        if sub:
            c.inverted(lambda: cuccaro_block(c, K, X))
        else:
            cuccaro_block(c, K, X)
        load(K)
        c.release(K)
    add_k()
    add_const_block(c, X, m, ctrl=v, sub=True)
    c.cx(X[-1], f)
    add_const_block(c, X, m, ctrl=f)
    # f = v AND (new >= k): subtract k under v, read the sign, add back.
    add_k(sub=True)
    c.cx(v, f)
    c.cx(X[-1], f)
    add_k()
    c.release([f])


@cached
def addmod_const_gates(W, k, m):
    """Not admitted by ISA 6.2 (flags are cleaned algebraically); see docs/circuits-port.md.

    x < m: (x + k) mod m; x >= m: identity. Needs 1 <= m <= 2^W and 0 <= k < m."""
    _check_modulus(W, m)
    if not 0 <= k < m:
        raise ValueError("addmod needs 0 <= k < m")
    c = Circuit(f"arith.bij.addmodk.w{W}.k{k:x}.m{m:x}", [("x", W)])
    e, v = c.alloc(2)
    X = c.wires("x") + [e]
    _below(c, X, m, v)

    def load(K):
        for i in range(len(K)):
            if (k >> i) & 1:
                c.cx(v, K[i])
    _addmod_core(c, X, m, v, load)
    _below(c, X, m, v)
    c.release([e, v])
    c.spec = lambda a: {"x": (a["x"] + k) % m if a["x"] < m else a["x"]}
    return pair(c, f"arith.bij.submodk.w{W}.k{k:x}.m{m:x}",
                lambda a: {"x": (a["x"] - k) % m if a["x"] < m else a["x"]})


@cached
def addmod_in_gates(W, m):
    """Not admitted by ISA 6.2 (flags are cleaned algebraically); see docs/circuits-port.md.

    x, k < m: (x + k) mod m; otherwise identity (the unused encodings stay fixed)."""
    _check_modulus(W, m)
    c = Circuit(f"arith.bij.addmod.w{W}.m{m:x}", [("x", W)], [("k", W)])
    e, v, kv, ke = c.alloc(4)
    X = c.wires("x") + [e]
    k = c.wires("k")
    copy = c.alloc(W)

    def k_valid():
        for s, t in zip(k, copy):
            c.cx(s, t)
        _below(c, copy + [ke], m, kv)
        for s, t in zip(k, copy):
            c.cx(s, t)
    k_valid()
    _below(c, X, m, v, ctrl=kv)

    def load(K):
        for i in range(W):
            c.ccx(v, k[i], K[i])
    _addmod_core(c, X, m, v, load)
    _below(c, X, m, v, ctrl=kv)
    k_valid()
    c.release([e, v, kv, ke] + copy)
    c.spec = lambda a: {"x": (a["x"] + a["k"]) % m if a["x"] < m and a["k"] < m else a["x"]}
    return pair(c, f"arith.bij.submod.w{W}.m{m:x}",
                lambda a: {"x": (a["x"] - a["k"]) % m if a["x"] < m and a["k"] < m else a["x"]})


@cached
def mulmod_const_gates(W, k, m):
    """Not admitted by ISA 6.2 (flags are cleaned algebraically); see docs/circuits-port.md.

    x < m: k*x mod m; x >= m: identity. Needs gcd(k, m) = 1 (dialect TDL-5(b))."""
    _check_modulus(W, m)
    if math.gcd(k, m) != 1:
        raise ValueError(f"mulmod needs gcd(k, m) = 1, got k={k} m={m}")
    kinv = pow(k, -1, m) if m > 1 else 0
    c = Circuit(f"arith.bij.mulmodk.w{W}.k{k:x}.m{m:x}", [("x", W)])
    x = c.wires("x")
    e, te, v, w = c.alloc(4)
    t = c.alloc(W)
    T = t + [te]
    _below(c, x + [e], m, v)

    def step(value):
        """Under w = v AND x[i]: T += value*2^i mod m, for every i."""
        for i in range(W):
            c.ccx(v, x[i], w)
            amount = (value << i) % m

            def load(K, amount=amount):
                for j in range(len(K)):
                    if (amount >> j) & 1:
                        c.cx(w, K[j])
            _addmod_core(c, T, m, w, load)
            c.ccx(v, x[i], w)
    step(k)
    for a, b in zip(x, t):
        c.cx(b, a); c.ccx(v, a, b); c.cx(b, a)
    c.inverted(lambda: step(kinv))
    _below(c, x + [e], m, v)
    c.release([e, te, v, w] + t)
    c.spec = lambda a: {"x": (a["x"] * k) % m if a["x"] < m else a["x"]}
    return pair(c, f"arith.bij.mulmodk_inv.w{W}.k{k:x}.m{m:x}",
                lambda a: {"x": (a["x"] * kinv) % m if a["x"] < m else a["x"]})


# ---- modular bijections as ISA 4.5 qinplace pairs: the admitted form today -----

def _addmod_oracle(name, W, m, k):
    w1 = W + 1
    return OracleFn(name, [("x", W)], W,
                    [("x1", w1), ("mm", w1), ("kk", w1), ("lt", 1), ("s", w1), ("wrap", w1), ("ns", 1),
                     ("r1", w1), ("r2", w1), ("r", W)],
                    [f"x1 = lift.zext.i{w1} x", f"mm = lift.const.i{w1} {m}", f"kk = lift.const.i{w1} {k}",
                     "lt = lift.icmp.ult x1 mm", "s = lift.add x1 kk", "wrap = lift.sub s mm",
                     "ns = lift.icmp.ult s mm", "r1 = lift.select ns s wrap", "r2 = lift.select lt r1 x1",
                     f"r = lift.trunc.i{W} r2", "lift.retval r"])


def _named_pair(g, ginv, base, inv_base, x, ins, spec, inv_spec):
    a = QinplaceAction(base, x, ins, g, ginv)
    a.spec = spec
    b = QinplaceAction(inv_base, x, ins, ginv, g)
    b.spec = inv_spec
    return Object([g, ginv, a, b], root=a.name, inverse=b.name)


@cached
def addmod_const(W, k, m):
    """x < m: (x + k) mod m; x >= m: identity. Needs 1 <= m <= 2^W and 0 <= k < m."""
    _check_modulus(W, m)
    if not 0 <= k < m:
        raise ValueError("addmod needs 0 <= k < m")
    tag = f"w{W}.k{k:x}.m{m:x}"
    return _named_pair(_addmod_oracle(f"arith.ref.addmodk.{tag}", W, m, k),
                       _addmod_oracle(f"arith.ref.submodk.{tag}", W, m, (m - k) % m),
                       f"arith.bij.addmodk.{tag}", f"arith.bij.submodk.{tag}", ("x", W), [],
                       lambda a: {"x": (a["x"] + k) % m if a["x"] < m else a["x"]},
                       lambda a: {"x": (a["x"] - k) % m if a["x"] < m else a["x"]})


def _addmod_in_oracle(name, W, m, negate):
    w1 = W + 1
    amount = ["n = lift.sub mm k1", "kk = lift.urem n mm"] if negate else ["kk = lift.mov k1"]
    regs = [("x1", w1), ("k1", w1), ("mm", w1), ("ltx", 1), ("ltk", 1), ("ok", 1), ("kk", w1), ("s", w1),
            ("wrap", w1), ("ns", 1), ("r1", w1), ("r2", w1), ("r", W)]
    if negate:
        regs.append(("n", w1))
    return OracleFn(name, [("x", W), ("k", W)], W, regs,
                    [f"x1 = lift.zext.i{w1} x", f"k1 = lift.zext.i{w1} k", f"mm = lift.const.i{w1} {m}",
                     "ltx = lift.icmp.ult x1 mm", "ltk = lift.icmp.ult k1 mm", "ok = lift.and ltx ltk", *amount,
                     "s = lift.add x1 kk", "wrap = lift.sub s mm", "ns = lift.icmp.ult s mm",
                     "r1 = lift.select ns s wrap", "r2 = lift.select ok r1 x1",
                     f"r = lift.trunc.i{W} r2", "lift.retval r"])


@cached
def addmod_in(W, m):
    """x, k < m: (x + k) mod m; otherwise identity (the unused encodings stay fixed)."""
    _check_modulus(W, m)
    tag = f"w{W}.m{m:x}"
    return _named_pair(_addmod_in_oracle(f"arith.ref.addmod.{tag}", W, m, False),
                       _addmod_in_oracle(f"arith.ref.submod.{tag}", W, m, True),
                       f"arith.bij.addmod.{tag}", f"arith.bij.submod.{tag}", ("x", W), [("k", W)],
                       lambda a: {"x": (a["x"] + a["k"]) % m if a["x"] < m and a["k"] < m else a["x"]},
                       lambda a: {"x": (a["x"] - a["k"]) % m if a["x"] < m and a["k"] < m else a["x"]})


def _mulmod_oracle(name, W, m, k):
    w2 = 2 * W
    return OracleFn(name, [("x", W)], W,
                    [("x2", w2), ("mm", w2), ("kk", w2), ("lt", 1), ("p", w2), ("rr", w2), ("r2", w2), ("r", W)],
                    [f"x2 = lift.zext.i{w2} x", f"mm = lift.const.i{w2} {m}", f"kk = lift.const.i{w2} {k}",
                     "lt = lift.icmp.ult x2 mm", "p = lift.mul x2 kk", "rr = lift.urem p mm",
                     "r2 = lift.select lt rr x2", f"r = lift.trunc.i{W} r2", "lift.retval r"])


@cached
def mulmod_const(W, k, m):
    """x < m: k*x mod m; x >= m: identity. Needs gcd(k, m) = 1 (dialect TDL-5(b))."""
    _check_modulus(W, m)
    if math.gcd(k, m) != 1:
        raise ValueError(f"mulmod needs gcd(k, m) = 1, got k={k} m={m}")
    k %= m
    kinv = pow(k, -1, m) if m > 1 else 0
    tag = f"w{W}.k{k:x}.m{m:x}"
    return _named_pair(_mulmod_oracle(f"arith.ref.mulmodk.{tag}", W, m, k),
                       _mulmod_oracle(f"arith.ref.mulmodk_inv.{tag}", W, m, kinv),
                       f"arith.bij.mulmodk.{tag}", f"arith.bij.mulmodk_inv.{tag}", ("x", W), [],
                       lambda a: {"x": (a["x"] * k) % m if a["x"] < m else a["x"]},
                       lambda a: {"x": (a["x"] * kinv) % m if a["x"] < m else a["x"]})
