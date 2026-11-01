"""QROM by unary iteration and SELECT-SWAP, as flat ISA 0.9 permutation actions.

t ^= data[idx]. Babbush, Gidney, Berry, Wiebe, McClean, Paler, Fowler, Neven 2018
(arXiv:1805.03662, section III) for unary iteration; Low, Kliuchnikov, Schaeffer 2018
(arXiv:1812.00954) and Berry, Gidney, Motta, McClean, Babbush 2019 (arXiv:1902.02134) for
SELECT-SWAP with clean and with dirty wires. Tables are fixed classically, so a table is
part of the object identity (t<hash> in the symbol).
"""
import hashlib

from adders.circuits import Circuit, Object, cached


def _check(data, n, W):
    if n < 0 or W < 1:
        raise ValueError("qrom needs n >= 0 and W >= 1")
    if len(data) > (1 << n):
        raise ValueError(f"table of {len(data)} words needs more than {n} address bits")
    if not data:
        raise ValueError("empty table")
    for word in data:
        if not 0 <= word < (1 << W):
            raise ValueError(f"table word {word} does not fit {W} bits")
    return list(data) + [0] * ((1 << n) - len(data))     # Short tables pad with zero words.


def _tag(data, n, W):
    digest = hashlib.sha256(",".join(map(str, data)).encode()).hexdigest()[:16]
    return f"n{n}.w{W}.t{digest}"


def unary_iteration(c, idx, target, data):
    """target ^= data[idx]; flags are nested compute/uncompute pairs, one wire per level."""
    n = len(idx)
    W = len(target)

    def leaf(flag, word):
        for i in range(W):
            if (word >> i) & 1:
                c.cx(flag, target[i])

    def walk(flag, level, lo):
        if level == 0:
            leaf(flag, data[lo])
            return
        f = c.alloc(1)[0]
        half = 1 << (level - 1)
        c.ccx(flag, idx[level - 1], f)      # f = flag AND bit
        c.cx(flag, f)                       # f = flag AND NOT bit
        walk(f, level - 1, lo)
        c.cx(flag, f)                       # f = flag AND bit
        walk(f, level - 1, lo + half)
        c.ccx(flag, idx[level - 1], f)
        c.release([f])

    if n == 0:
        for i in range(W):
            if (data[0] >> i) & 1:
                c.x(target[i])
        return
    # The root AND is unnecessary: the top address bit, copied, is the first flag.
    r = c.alloc(1)[0]
    half = 1 << (n - 1)
    c.cx(idx[n - 1], r)
    c.x(r)
    walk(r, n - 1, 0)
    c.x(r)
    walk(r, n - 1, half)
    c.cx(idx[n - 1], r)
    c.release([r])


def _nonempty(c, target):
    if not c.gates:
        # An all-zero table is the identity; a self-cancelling pair keeps the block nonempty.
        c.x(target); c.x(target)


@cached
def qrom(data, n, W):
    full = _check(data, n, W)
    ins = [("idx", n)] if n else []
    c = Circuit(f"arith.qrom.{_tag(full, n, W)}", [("t", W)], ins)
    idx = c.wires("idx") if n else []
    unary_iteration(c, idx, c.wires("t"), full)
    _nonempty(c, "t[0]")
    c.spec = lambda v: {"t": v["t"] ^ full[v.get("idx", 0)]}
    return Object([c])


def swap_network(c, low, regs):
    """Move register low-value to regs[0]; (len(regs)-1)*W controlled swaps."""
    lam = len(regs)
    for j, bit in enumerate(low):
        step = 1 << j
        for r in range(0, lam, 2 * step):
            for x, y in zip(regs[r], regs[r + step]):
                c.cx(y, x); c.ccx(bit, x, y); c.cx(y, x)


def _blocks(full, k, W):
    """Per high address, one word concatenating the 2^k table words of that block."""
    lam = 1 << k
    out = []
    for block in range(len(full) >> k):
        word = 0
        for j in range(lam):
            word |= full[(block << k) + j] << (j * W)
        out.append(word)
    return out


def _split(n, k):
    if not 0 <= k <= n:
        raise ValueError("select-swap needs 0 <= k <= n")


@cached
def select_swap(data, n, W, k):
    """Clean workspace: load a 2^k-word block, swap the word to the front, XOR, literal reverse."""
    full = _check(data, n, W)
    _split(n, k)
    ins = [("idx", n)] if n else []
    c = Circuit(f"arith.qrom_ss.k{k}.{_tag(full, n, W)}", [("t", W)], ins)
    idx = c.wires("idx") if n else []
    t = c.wires("t")
    lam = 1 << k
    y = c.alloc(lam * W)
    regs = [y[i * W:(i + 1) * W] for i in range(lam)]
    start = len(c.gates)
    unary_iteration(c, idx[k:], y, _blocks(full, k, W))
    swap_network(c, idx[:k], regs)
    body = c.gates[start:]
    for s, d in zip(regs[0], t):
        c.cx(s, d)
    c.gates.extend(reversed(body))
    _nonempty(c, "t[0]")
    c.release(y)
    c.spec = lambda v: {"t": v["t"] ^ full[v.get("idx", 0)]}
    return Object([c])


@cached
def select_swap_dirty(data, n, W, k):
    """Borrowed y: S; XOR; S^-1; U; S; XOR; S^-1; U leaves y restored and t ^= data[idx]."""
    full = _check(data, n, W)
    _split(n, k)
    if n < 1:
        raise ValueError("the dirty form needs at least one address bit; use qrom for a constant")
    lam = 1 << k
    c = Circuit(f"arith.qrom_ssd.k{k}.{_tag(full, n, W)}", [("t", W)], [("idx", n)], dirty=[("y", lam * W)])
    idx, t, y = c.wires("idx"), c.wires("t"), c.wires("y")
    regs = [y[i * W:(i + 1) * W] for i in range(lam)]
    blocks = _blocks(full, k, W)

    def sandwich():
        start = len(c.gates)
        swap_network(c, idx[:k], regs)
        body = c.gates[start:]
        for s, d in zip(regs[0], t):
            c.cx(s, d)
        c.gates.extend(reversed(body))
    sandwich()
    unary_iteration(c, idx[k:], y, blocks)
    sandwich()
    unary_iteration(c, idx[k:], y, blocks)
    c.spec = lambda v: {"t": v["t"] ^ full[v["idx"]]}
    return Object([c])
