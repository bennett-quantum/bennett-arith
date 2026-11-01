# adders

Ripple-carry, Cuccaro in-place, Gidney AND-ancilla and QCLA adders, plus the library bijections of
dialect 8.7 (add, sub, xor, rotate, negate, bswap, modular add, modular multiply by a unit), as ISA 0.9
objects with certificates in `objects/`. `generate.py` builds them and every other instance.

Plan, formulas, consumers and contract gaps: [`docs/circuits-port.md`](../docs/circuits-port.md). Tests: `tests/circuits/run`.
