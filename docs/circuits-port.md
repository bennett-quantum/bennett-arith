# Circuits port: adders, multipliers, QROM as ISA 0.9 library objects

Status: implemented and verified as stated in each row; open items are listed under "Contract gaps".
Contract: ISA 0.9 (`bennett-isa-spec/spec/Bennett-ISA-Spec-0.9.md`, commit pinned in
`adders/objects/manifest.json`), dialect section 8.7 and TDL-5(b). The v1 sources in Bennett.jl were
ideas, not contract. North star: section 3.1 (library bijections and their certificates), section 6
(arithmetic is library code), section 8 (ladder).

## Output format

- **Language.** Python generators, like `softfloat/generate.py`. C is unnecessary because the output
  is text; simulation is bit-sliced in Python big integers.
- **Object.** One canonical `.bisa` per instance (section 16), no imports, embedded `certificate`.
  `python3 -I adders/generate.py publish` writes `{adders,multipliers,qrom}/objects/` and
  `adders/objects/manifest.json`. `... one FAMILY ARG...` prints any other instance deterministically.
- **Flat bodies.** An action operand names a whole bundle or one wire; there is no sub-bundle form, so
  a callee cannot be handed bits `[i, j)` of a bundle. Every construction is therefore one flat action
  with one pooled workspace bundle `anc`. Composition happens by generating, not by `action_call`.
- **Certificate (section 12).** `bindings.target_hash` is `adders/target-unit.json`: a published unit
  target with resource `t`, ccx = 7 T, t/tdg = 1 T, every gate one time step. Each region has `frame`,
  `gates_used`, `resources`, and claim 0:
  - domain at most 8 bits: `exhaustive`, explicit full-tuple table, label `proof`;
  - larger: `sampled` xoshiro256** table of 32 draws, label `evidence`. Never `proof`.
  - inverse symbols also carry `structural adjoint_table` (universal, `args`/`budget` `"all"`).
  - `qinplace` actions also carry an `exhaustive` `expected: "inverse_pair"` claim, with no requested label:
    a checker that cannot enumerate 2^W reports unchecked (host limit), section 12.2.
- **Evidence labels.** A published W = 64 adder is `evidence` in its certificate although the test suite
  also covers it at random. Exhaustive coverage above 8 bits is test evidence (below), not a certificate
  claim; a table at W = 8 would be 6 MB per object.

## How consumers resolve these

| Consumer | Route | State |
|---|---|---|
| `bennett-plugin`, dialect 8.7 "library bijections" and TDL-5(b) | ISA 9.3 import by name and signature with `pinned_closure_hash`; link the object; `action_call @arith.bij.* (x) (k) () ()`, or `qinplace` for the modular forms | **Names are this repo's proposal**: the dialect names no symbols (gap G3) |
| `lift` oracle bodies | `lift.perm_call` of a permutation action (ISA 4.2): `mul.*`, `qrom*`, `add.ripple`, `add.qcla` XOR into a `mut` target, as a tgt needs | Available by ISA text; no plugin use yet |
| `bennett-sched` | Sees flat actions; chooses realisations by target (§11). A permutation action's `ccx` is exact (4.4) | No arith-specific contract needed |
| `bennett-estimate` | Reads `resources` and `gates_used` from the certificate, or the manifest `census`, or expands under its own target | `bennett-estimate` is a skeleton today; the fields are published |
| `bennett-conformance` | Replays claims (section 12) | Certificates are checker input |
| Soft-float / `dist/` | Unrelated: LLVM bitcode, another job | Not touched |

Publication of the `args` form: dialect TDL-5(b) allows k "as `in` or `args`". A gate cannot depend on a
classical argument, so a run-time classical k binds through a clean register as `in` (CC loads it), or
a compile-time k through the constant-specialised family (`addk`, `xork`, `addmodk`, `mulmodk`),
matching dialect 8.7's "pair specialised to those constants".

## Constructions

W = operand bits, R = target bits, w(W) = popcount, lg = floor(log2). T = 7 x Toffoli under the unit
target. Ancilla is the peak clean workspace. Depth is ASAP-layered and published per instance in the
manifest census. Every formula below is asserted against a census read from the emitted text.

### Adders (`adders/`)

| Family (`arith.add.*`) | Effect | Toffoli | Ancilla | Toffoli depth | Rung |
|---|---|---|---|---|---|
| `cuccaro.wW` (a, b mut) | b += a; a written, restored | 2W-3 (W>=2), else 0 | 1 (W>=2), else 0 | linear | 1, 8: smallest workspace |
| `cuccaro_carry.wW` (a, b, z mut) | also z ^= carry | 2W | 1 | linear | comparison, carries |
| `gidney.wW` (a, b mut) | b += a with AND ancillas | 2(W-1) | W-1 | linear | T-optimal once G1 lands |
| `ripple.wW` (s mut; a, b in) | s ^= a+b on W+1 bits | 4W-2 | 2W | linear | oracle targets |
| `qcla.wW` (z mut; a, b in) | z ^= a+b on W+1 bits | 2(5W-3w(W)-3lg W-1) | 2W+1 + (W-w(W)-lg W) | 2(lg W + lg(W/3) + 4), W>=4 | depth-bound targets, rung 4 estimate |

`qcla` XORs a clean Draper section 4.1 sum into the target, then runs the literal adjoint: the ISA domain
of a `mut` wire is every value, so v1's "Z must be clean" is not a legal contract here. That is why its
Toffoli count is twice Draper's.

### Library bijections (`arith.bij.*`, NS 3.1, dialect 8.7, TDL-5(b))

Each object holds g and its inverse, certified by `adjoint_table`.

| Family | Effect, stated conditions | Toffoli | Ancilla |
|---|---|---|---|
| `add.wW`, `sub.wW` (x mut; k in) | x +/-= k mod 2^W | 2W-3 (W>=2) | W+1 (W>=2), W at W=1 |
| `addk`, `subk` .wW.k | x +/-= constant | 2W-3 | W+1 |
| `xor`, `xork` | x ^= k | 0 | 0 |
| `rotl`, `rotr` .wW.r, 0<=r<W | rotate | 0 | 0 |
| `neg.wW` | x = -x mod 2^W | 2W-3 | W+1 |
| `bswap.wW` (16 divides W) | LLVM bswap | 0 | 0 |
| `addmodk`, `submodk` .wW.k.m | x<m: (x+-k) mod m; **x>=m: identity**; 1<=m<=2^W, 0<=k<m | `qinplace`: see below | t, f |
| `addmod`, `submod` .wW.m (k in) | x,k<m: (x+-k) mod m; **else identity** | `qinplace` | t, f |
| `mulmodk`, `mulmodk_inv` .wW.k.m | x<m: k^(+-1) x mod m; **x>=m: identity**; gcd(k,m)=1 | `qinplace` | t, f |

Modular forms are `qinplace @arith.ref.* @arith.ref.* tk x` with lifted reference oracles (`addmodk` 11 rows,
`addmod` 14 and 15, `mulmodk` 9), because ISA 6.2 admits no other cleanup of flags that depend on x (gap G2). Their realised
cost comes from the §11 expansion of the rows, not from a formula here. Gate-level candidates exist,
exhaustively verified, and are rejected by the interpreter with `§6.2`, pinned by a test:
`addmod_const_gates` 9(2W-1) Toffoli, W+5 ancilla; `mulmod_const_gates` 20W^2+3W-4 Toffoli, 2W+7 ancilla.

### Multipliers (`multipliers/`)

muladd: z += a*b mod 2^R. mul: z ^= a*b mod 2^R (an oracle target). R = W and R = 2W are both exercised.

| Family (`arith.*`) | Toffoli | Ancilla | Notes |
|---|---|---|---|
| `muladd.school.wW.rR` | sum over i<min(W,R) of 2min(W,R-i) + C(R-i), C(n)=2n-3 for n>=2 else 0 | R+1 | no reversal needed |
| `mul.school.wW.rR` | twice the above | 2R+1 | accumulator, XOR, adjoint |
| `muladd.karatsuba.wW.rR` | 2F(W)+C(R) | recurrence `karatsuba_ancilla` | F(n)=F(h)+F(n-h)+F(h+1)+2C(h+1)+3C(2n-h), h=ceil(n/2), schoolbook at n<=4 |
| `mul.karatsuba.wW.rR` | 2F(W) | same recurrence | beats `mul.school` above a width the test bounds by 2^12 |
| `mul.tree.wW` (R=2W) | 2(W^2 + sum over levels of adders x Q(pad)), Q = Draper count | `tree_ancilla`, Theta(W^2) | Sun-Borissov: depth / log^2 W is checked non-increasing to W=128 |

Karatsuba, a design decision: Gidney 2019's in-place recursion needs padded pieces whose carries are
cleaned algebraically, which ISA 6.2 refuses, and a recursion into the whole target costs O(R) per leaf.
Each sub-product is therefore retained in a clean register and the whole tree is reversed once at the top:
F is Theta(W^1.58) Toffoli and ancilla Theta(W^1.58), palindromic, so 6.2 admits it. v1 removed Karatsuba
as never profitable at W <= 64, and the crossover here is also beyond 64; `karatsuba_forward_toffoli`
publishes it. It stays because the north-star scope names it and estimates beyond 64 bits need it.

### QROM (`qrom/`): t ^= data[idx]; a table is part of the identity

| Family (`arith.*`) | Toffoli (L=2^n) | Ancilla | Rung |
|---|---|---|---|
| `qrom.nN.wW.t<hash>` unary iteration | 2(L-2), independent of W (T = 14(L-2)) | n | 4: read-only tables |
| `qrom_ss.kK...` SELECT-SWAP, clean | 2(2 max(2^(n-k)-2,0) + (2^k-1)W) | 2^k W + n-k | 4(c): resource estimates at N = 2^20 |
| `qrom_ssd.kK...` SELECT-SWAP, `qborrow y` | 4 max(2^(n-k)-2,0) + 4(2^k-1)W | n-k clean, 2^k W dirty | when idle wires exist |

No root AND: the copied top address bit is the first flag. Tables shorter than 2^n pad with zero words,
stated in the object's spec. The dirty form's frame proof needs `exhaustive` over D_F, so it is only
listed in `borrow_frames` at table-claim size; wider instances are `evidence` (gap G5). QROM against QRAM is the
scheduler's choice (NS section 5); these objects are the QROM side.

## Test strategy (`tests/circuits/`, run by `tests/circuits/run`)

All tests read the emitted canonical text through an independent parser (`harness.py`), never the builder.

- **Exhaustive, bit-sliced.** `Lanes` holds one big integer per wire, so all 2^n inputs take one pass.
  Adders: W <= 10 with every a, b (ripple, qcla: W <= 7 with every target value too). Multipliers: every
  operand pair at W = 8 and 10 on two target values, every target value to W = 5 or 6. QROM: every address and
  target to n = 8. All modes run with and without one inherited control (workspace unconditional, every
  gate controlled, ISA 5.3), checking `qfree` clean and `in`/borrowed restored. Bijections: every (k, m)
  at W <= 4 for the modular families.
- **Randomised.** 4096 or more lanes at W up to 256; 512 for wide Karatsuba.
- **Cost.** Every formula above is asserted over ranges of W, from text.
- **Differential.** `bennett-isa-ref` debug build: `check` for identities, schema and §6 (published objects
  of at most 1500 gates; out of band with a release build, 127 of the 129 objects passed, the two `addmod`
  in-form objects being unparsable until G4 lands), `run-action` with exact +1 phase, adjoint
  checks, `run-oracle` for wide modular pairs. Negative controls: a tampered hash, a dropped uncompute.
- **Certificates.** `test_objects.py` re-derives census and frame, re-draws xoshiro independently and replays
  every table row bit-sliced; a subset through `run-action`.
- **Reproducibility.** `generate.py check` compares every published byte.

## Contract gaps (beads in this repo)

- **G1: T-optimal AND.** ISA 6.2 refuses a 4-T AND's value once it has a lasting reader (`h` makes it `other`), and
  6.4 reserves measurement-based cleanup. `gidney` therefore costs 14(W-1) T, not Gidney's 4(W-1).
- **G2: gate-level modular arithmetic.** ISA 6.2 admits only matched cleanups; flags clean on every basis
  input are refused. Only `qinplace` (4.5) has a certified exception, and it runs through oracle rows.
- **G3: resolution of library bijections.** Dialect 8.7 names the operations but no symbols or signatures.
- **G4: interpreter behind ISA 0.9.** Its schema has no `expected: "inverse_pair"`, no entry `budget`, and its
  parser no `qinplace (ins)`. Tests use `interpreter_view` and replay oracles; nothing is skipped silently.
- **G5: proofs above host limits.** cert 0.9 has no width-uniform rule beyond `adjoint_table`, so W >= 16
  correctness stays `evidence` and wide dirty frames lack a proof.
- **G6: pins.** `SPEC_VERSIONS.toml` and the root README are outside this stream's paths and still say ISA 0.8.
