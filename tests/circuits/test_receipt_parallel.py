"""Real small publications have identical serial and pooled receipt bytes."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests/circuits")]
import test_objects as objects
from time_guard import test_main


class ReceiptParallel(unittest.TestCase):
    def test_serial_and_pool_receipts_are_byte_identical(self):
        selection = ",".join(entry["root"] for entry in objects.MANIFEST["entries"][:3])
        original = objects.Published._verify_publication
        snapshots = []
        for width in (1, 3):
            threads = []

            def verify(case, *args, **kwargs):
                threads.append(threading.get_ident())
                return original(case, *args, **kwargs)

            with patch.dict(os.environ, BENNETT_ARITH_RECEIPTS=selection,
                            BENNETT_ARITH_RECEIPT_WORKERS=str(width)), \
                    patch.object(objects, "time", SimpleNamespace(monotonic=lambda: 1.0)), \
                    patch.object(objects.Published, "_verify_publication", verify), \
                    redirect_stdout(StringIO()) as output:
                case = objects.Published("test_raw_publications_admitted")
                result = unittest.TestResult()
                case.run(result)
                self.assertTrue(result.wasSuccessful(), (result.errors, result.failures))
                status = objects.report_receipts(objects.RAW_RECEIPTS)
            receipts = [(root, r.state.value, r.detail, r.claims, r.wall_seconds)
                        for root, r in objects.RAW_RECEIPTS.items()]
            snapshots.append((output.getvalue().encode(), json.dumps(receipts).encode(), status))
            self.assertEqual(len(threads), 3)
            if width > 1:
                self.assertTrue(any(t != threading.get_ident() for t in threads),
                                "requested pool still executes publications serially on the caller")
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0][2], 0)


if __name__ == "__main__":
    test_main()
