"""Reject literal clock budgets in test, runner and configuration sources."""
import ast
from pathlib import Path
import re

TIME_NAME = re.compile(r"(?:timeout|deadline|hang_guard|wall_s|sleep|alarm)", re.I)
ALLOW = {"tests/timeouts.toml", "tests/test_time_literals.py"}
TEXT_TIME = re.compile(
    r"\b(?:timeout|sleep)\s+(?:--[\w-]+(?:=\S+)?\s+)*(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)[smhd]?\b"
    r"|(?:timeout(?:_s|_ms)?|deadline|hang_guard|wall_seconds)[\"']?\s*[:=]\s*[0-9]"
    r"|(?:sleep|alarm|timeout|from_secs|from_millis)\s*\(\s*[0-9]"
    r"|(?:timeout|deadline)\s*=\s*[0-9]", re.I)


def bare_times(name, text):
    if name in ALLOW:
        return []
    if not name.endswith(".py"):
        return [i for i, line in enumerate(text.splitlines(), 1)
                if not line.lstrip().startswith("#") and TEXT_TIME.search(line)]
    tree = ast.parse(text)
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arguments):
            defaults = list(zip(node.args[-len(node.defaults):], node.defaults))
            defaults += list(zip(node.kwonlyargs, node.kw_defaults))
            lines.update(value.lineno for arg, value in defaults if value is not None
                         and TIME_NAME.search(arg.arg) and isinstance(value, ast.Constant)
                         and type(value.value) in (int, float))
        if isinstance(node, ast.keyword) and node.arg and TIME_NAME.search(node.arg):
            if any(isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                   for v in ast.walk(node.value)):
                lines.add(node.value.lineno)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(TIME_NAME.search(ast.unparse(t)) for t in targets):
                if any(isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                       for v in ast.walk(node.value)):
                    lines.add(node.lineno)
        if isinstance(node, ast.Call):
            callee = ast.unparse(node.func).split(".")[-1]
            if callee in {"sleep", "alarm", "setitimer", "from_secs", "from_millis", "TimeoutExpired"}:
                if any(isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                       for arg in node.args for v in ast.walk(arg)):
                    lines.add(node.lineno)
        if isinstance(node, ast.Compare) and re.search(r"monotonic|perf_counter|process_time|time\.time", ast.unparse(node)):
            if any(isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) for v in ast.walk(node)):
                lines.add(node.lineno)
    return sorted(lines)


def inventory(root, paths):
    selected = (n for n in paths if n.startswith(("tests/", "scripts/", "configs/"))
                or n == "softfloat/instantiate.py" or Path(n).name.startswith("test_")
                or Path(n).suffix in {".toml", ".yaml", ".yml", ".ini", ".cfg", ".json"})
    return [f"{name}:{line}: bare time literal" for name in selected
            if (root / name).is_file() and (root / name).suffix not in {".bc", ".bisa", ".pyc"}
            for line in bare_times(name, (root / name).read_text())]
