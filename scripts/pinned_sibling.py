"""Resolve this repo's gate.toml pins without consulting live sibling contents."""
import os
from pathlib import Path
import subprocess
import tomllib
from time_guard import run as guarded_run

ROOT = Path(__file__).resolve().parents[1]


def _head(path):
    if not (path / ".git").exists():
        return "unavailable"
    try:
        done = guarded_run(
            ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
            text=True, guard_class="short", env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        )
        return done.stdout.strip() if done.returncode == 0 else "unavailable"
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def resolve_sibling(name):
    with (ROOT / "gate.toml").open("rb") as stream:
        config = tomllib.load(stream)
    sha = config["siblings"][name]["sha"]
    layout = os.environ.get("BENNETT_GATE_LAYOUT")
    path = (Path(layout) / name if layout else
            ROOT / ".tmp/gate/cache" / f"{name}@{sha[:12]}" / name)
    actual = _head(path)
    if actual != sha:
        raise SystemExit(
            f"pinned sibling {name}@{sha}: {path} HEAD={actual}; "
            f"live ../{name} HEAD={_head(ROOT.parent / name)}; "
            f"materialise with gate_run.py verify --repo {config['repo']} --sha HEAD"
        )
    return path
