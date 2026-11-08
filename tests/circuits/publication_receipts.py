"""Selection, reporting and exit status for raw publication receipts."""
from collections import Counter
from enum import Enum
from typing import NamedTuple


class ReceiptState(Enum):
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class Receipt(NamedTuple):
    state: ReceiptState
    detail: str
    claims: int
    wall_seconds: float


def select_publications(entries, selection):
    if selection is None:
        return entries
    requested = set(selection.split(","))
    missing = requested - {entry["root"] for entry in entries}
    if missing:
        raise SystemExit(f"invalid BENNETT_ARITH_RECEIPTS: unknown or empty entry roots {sorted(missing)!r}")
    return [entry for entry in entries if entry["root"] in requested]


def report_receipts(receipts):
    states = Counter(receipt.state for receipt in receipts.values())
    print(f"Raw receipts: selected={len(receipts)} COMPLETE={states[ReceiptState.COMPLETE]} "
          f"UNKNOWN={states[ReceiptState.UNKNOWN]} FAILED={states[ReceiptState.FAILED]}", flush=True)
    print("A gate with any UNKNOWN publication receipt is UNKNOWN, not PASS and not FAIL: it exits 124; "
          "re-run only the UNKNOWN receipts once in a quiet slot; a second UNKNOWN on the same receipt is a bead; "
          "nothing merges or pushes on UNKNOWN.", flush=True)
    print(f"Accepted claims (Proof/Evidence only): {sum(receipt.claims for receipt in receipts.values())}; "
          "UNKNOWN receipts contribute no proofs or evidence", flush=True)
    unknown = []
    for root, receipt in receipts.items():
        if receipt.state is ReceiptState.UNKNOWN:
            print(f"UNKNOWN receipt: {root}: {receipt.detail}", flush=True)
            unknown.append(root)
    if unknown:
        print(f"BENNETT_ARITH_RECEIPTS={','.join(unknown)} tests/circuits/run", flush=True)
    return 1 if states[ReceiptState.FAILED] else 124 if unknown else 0
