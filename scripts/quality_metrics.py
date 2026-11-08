#!/usr/bin/env python3
"""Local syntax metrics and a monotone ratchet against docs/quality.md."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from time_literals import inventory

ROOT=Path(__file__).resolve().parents[1]
SOURCE_DIRS={"adders","multipliers","qrom","softfloat","scripts","tests"}
PROCESS=re.compile(r"\bbennett-arith-[a-z0-9]{3}(?:\.[0-9]+)?\b|\bjob[/]|\b(?:shift|round) +[0-9]+")
LITTER=re.compile(r"(^|/)(__pycache__|PROGRESS[^/]*|LAST-RUN[^/]*|LOCK)(/|$)|\.(?:pyc|log|darc|lock)$")
BOUNDS=(25,50,100,200,300)
START="<!-- quality-baseline -->"
END="<!-- /quality-baseline -->"

def python_functions(text):
    tree=ast.parse(text)
    def mass(node,depth=0):
        decision=isinstance(node,(ast.If,ast.For,ast.AsyncFor,ast.While,ast.ExceptHandler,ast.IfExp,ast.Match,ast.comprehension))
        score=(1+depth) if decision else 0
        if isinstance(node,ast.BoolOp):score+=len(node.values)-1
        return score+sum(mass(child,depth+int(decision)) for child in ast.iter_child_nodes(node))
    result=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            body=node.body
            only=body[0] if len(body)==1 else None
            value=only.value if isinstance(only,(ast.Return,ast.Expr)) else None
            result.append((node.end_lineno-node.lineno+1,mass(node),int(isinstance(value,ast.Call))))
    return result

def c_functions(text):
    # Keep newlines so physical lengths remain comparable across revisions.
    text=re.sub(r"/\*.*?\*/|//[^\n]*",lambda m:"\n"*m[0].count("\n"),text,flags=re.S)
    text=re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    head=re.compile(r"^[ \t]*(?:[A-Za-z_]\w*[ \t*]+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{",re.M)
    result=[]
    for match in head.finditer(text):
        start=match.end()-1;level=1;end=start+1
        while level and end<len(text):
            level+=(text[end]=="{")-(text[end]=="}");end+=1
        if level:raise ValueError("unbalanced C function "+match[1])
        body=text[start+1:end-1];depth=0;score=0
        for token in re.findall(r"\b(?:if|for|while|switch|case|catch)\b|&&|\|\||[?{}]",body):
            if token=="{":depth+=1
            elif token=="}":depth-=1
            else:score+=1+(depth if token not in ("&&","||") else 0)
        wrapper=bool(re.fullmatch(r"\s*(?:return\s+)?[A-Za-z_]\w*\([^;{}]*\);\s*",body))
        result.append((text[match.start():end].count("\n")+1,score,int(wrapper)))
    return result

def measure():
    paths=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z"],cwd=ROOT).decode().split("\0")
    files={};litter=[];identifiers=[]
    for name in sorted(set(paths)-{""}):
        path=ROOT/name
        if not path.is_file():continue
        if LITTER.search(name):litter.append(name)
        if Path(name).parts[0] not in SOURCE_DIRS or path.suffix not in (".py",".c",".h",".cpp"):continue
        text=path.read_text()
        if not name.startswith("tests/") and not path.name.startswith("test_"):
            identifiers.extend(f"{name}:{text.count(chr(10),0,m.start())+1}" for m in PROCESS.finditer(text))
        rows=python_functions(text) if path.suffix==".py" else c_functions(text)
        files[name]={"functions":len(rows),"max_lines":max((r[0] for r in rows),default=0),
                     **{f"over_{n}":sum(r[0]>n for r in rows) for n in BOUNDS},
                     "cognitive_mass":sum(r[1] for r in rows),"trivial_wrappers":sum(r[2] for r in rows)}
    return {"files":files,"litter":litter,"process_identifiers":identifiers,
            "bare_time_literals":inventory(ROOT, sorted(set(paths)-{""}))}

def regressions(current,baseline):
    failures=[]
    for name,row in current["files"].items():
        old=baseline["files"].get(name,{})
        for key,value in row.items():
            if value>old.get(key,0):failures.append(f"{name} {key}: {value} > {old.get(key,0)}")
    for key in ("litter","process_identifiers"):
        if len(current[key])>len(baseline[key]):failures.append(f"{key}: {current[key]}")
    return failures

def main():
    current=measure()
    if sys.argv[1:]==["--report"]:
        print(json.dumps(current,sort_keys=True,indent=2));return
    if sys.argv[1:]:raise SystemExit("usage: quality_metrics.py [--report]")
    doc=(ROOT/"docs/quality.md").read_text()
    if START not in doc or END not in doc:raise SystemExit("missing quality baseline in docs/quality.md")
    block=doc.split(START,1)[1].split(END,1)[0].strip()
    baseline=json.loads(block.removeprefix("```json").removesuffix("```").strip())
    failures=regressions(current,baseline)+current["bare_time_literals"]
    if failures:raise SystemExit("\n".join(failures))
    print(f"quality ratchet: {len(current['files'])} source files, no baseline regression")

if __name__=="__main__":main()
