"""Sibling resolution uses gate.toml even when the live sibling is unusable."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from time_guard import run as guarded_run
SIBLING = "bennett-isa-spec"
PIN = "1" * 40
OTHER = "2" * 40
BINARY = Path("reference-interpreter/target/debug/bennett-isa-ref")


def checkout(path, sha):
    """Minimal local HEAD metadata; no git mutation or sibling worktree needed."""
    (path / ".git/objects").mkdir(parents=True)
    (path / ".git/refs").mkdir()
    (path / ".git/HEAD").write_text(sha + "\n")
    return path


class Pins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        workspace = Path(self.tmp.name)
        self.repo = checkout(workspace / "bennett-arith", OTHER)
        self.live = workspace / SIBLING
        self.live.mkdir()
        (self.repo / "tests/circuits").mkdir(parents=True)
        shutil.copyfile(ROOT / "tests/circuits/harness.py", self.repo / "tests/circuits/harness.py")
        shutil.copytree(ROOT / "scripts", self.repo / "scripts")
        shutil.copyfile(ROOT / "tests/timeouts.toml", self.repo / "tests/timeouts.toml")
        (self.repo / "gate.toml").write_text(
            f'repo = "bennett-arith"\n[siblings."{SIBLING}"]\nsha = "{PIN}"\n'
        )
        self.cache = self.repo / f".tmp/gate/cache/{SIBLING}@{PIN[:12]}/{SIBLING}"
        self.layout = workspace / "layout"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("BENNETT_", "GIT_"))}
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"

    def pinned(self, path, sha=PIN, binary=True):
        checkout(path, sha)
        if binary:
            (path / BINARY).parent.mkdir(parents=True)
            (path / BINARY).write_text("fixture binary\n")
        return path / BINARY

    def resolve(self, **env):
        code = (
            f"import sys; sys.path.insert(0, {str(self.repo / 'tests/circuits')!r}); "
            "from harness import ref_binary; print(ref_binary())"
        )
        done = guarded_run([sys.executable, "-I", "-B", "-c", code],
                              env=self.env | env, capture_output=True, text=True, guard_class="short")
        done.stderr = re.sub(r'(?m)^(?:\{"argv":|hang guard class warning:).*\n?', '', done.stderr)
        return done

    def assert_binary(self, done, expected):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(Path(done.stdout.strip()), expected)

    def assert_failure(self, done, live_head="unavailable", detail=""):
        self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
        self.assertIn(SIBLING, done.stderr)
        self.assertIn(PIN, done.stderr)
        self.assertIn(f"live ../{SIBLING} HEAD={live_head}", done.stderr)
        self.assertIn("gate_run.py verify --repo bennett-arith --sha HEAD", done.stderr)
        self.assertIn(detail, done.stderr)

    def test_cache_with_empty_live_sibling(self):
        expected = self.pinned(self.cache)
        self.assert_binary(self.resolve(), expected)

    def test_layout_precedes_cache(self):
        self.pinned(self.cache, OTHER)
        expected = self.pinned(self.layout / SIBLING)
        self.assert_binary(self.resolve(BENNETT_GATE_LAYOUT=str(self.layout)), expected)

    def test_layout_symlink_to_pinned_checkout(self):
        self.pinned(self.cache)
        self.layout.mkdir()
        (self.layout / SIBLING).symlink_to(self.cache, target_is_directory=True)
        self.assert_binary(self.resolve(BENNETT_GATE_LAYOUT=str(self.layout)),
                           self.layout / SIBLING / BINARY)

    def test_missing_layout_does_not_fall_back_to_cache(self):
        self.pinned(self.cache)
        self.assert_failure(self.resolve(BENNETT_GATE_LAYOUT=str(self.layout)))

    def test_mismatched_layout_does_not_fall_back_to_cache(self):
        self.pinned(self.cache)
        self.pinned(self.layout / SIBLING, OTHER)
        self.assert_failure(self.resolve(BENNETT_GATE_LAYOUT=str(self.layout)), detail=OTHER)

    def test_missing_cache_reports_pin_and_live_head(self):
        self.live.rmdir()
        checkout(self.live, OTHER)
        self.assert_failure(self.resolve(), live_head=OTHER)

    def test_missing_cache_with_empty_live_sibling(self):
        self.assert_failure(self.resolve())

    def test_cache_head_mismatch_is_fatal(self):
        self.pinned(self.cache, OTHER)
        self.assert_failure(self.resolve(), detail=OTHER)

    def test_directory_without_its_own_git_metadata_is_rejected(self):
        # Git would otherwise walk up and return the enclosing repo's HEAD.
        (self.repo / ".git/HEAD").write_text(PIN + "\n")
        self.cache.mkdir(parents=True)
        (self.cache / BINARY).parent.mkdir(parents=True)
        (self.cache / BINARY).write_text("unverified binary\n")
        self.assert_failure(self.resolve())

    def test_worktree_git_file(self):
        expected = self.pinned(self.cache)
        metadata = self.cache.parent / "metadata"
        (self.cache / ".git").rename(metadata)
        (self.cache / ".git").write_text("gitdir: ../metadata\n")
        self.assert_binary(self.resolve(), expected)

    def test_inherited_git_environment_cannot_redirect_head_check(self):
        expected = self.pinned(self.cache)
        self.assert_binary(self.resolve(GIT_DIR=str(self.repo / ".git"),
                                        GIT_WORK_TREE=str(self.repo)), expected)

    def test_live_binary_environment_override_cannot_bypass_pin(self):
        expected = self.pinned(self.cache)
        poison = self.live / BINARY
        poison.parent.mkdir(parents=True)
        poison.write_text("live binary must not be used\n")
        self.assert_binary(self.resolve(BENNETT_ISA_REF=str(poison)), expected)

    def test_missing_binary_names_pinned_path(self):
        self.pinned(self.cache, binary=False)
        done = self.resolve()
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(len(done.stderr.splitlines()), 1, done.stderr)
        self.assertIn(str(self.cache / BINARY), done.stderr)


if __name__ == "__main__":
    from time_guard import test_main
    test_main()
