"""Offline bennett-arith-instantiations-1 -> ordinary LLVM bitcode + JCS manifest.

Usage: python3 -I softfloat/instantiate.py REQUEST.json OUTPUT_DIRECTORY
No tool downloads, host FP, host libm or consumer source dependency is required.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
NAMES = ['Float8E5M2','Float8E5M2FNUZ','Float8E4M3','Float8E4M3FN',
         'Float8E4M3FNUZ','Float8E4M3B11FNUZ','Float8E3M4','Float8E8M0FNU',
         'Float6E3M2FN','Float6E2M3FN','Float4E2M1FN']

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/f'softfloat/{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def jcs(obj):
    # The schema contains only bounded integers, strings, arrays and ASCII keys.
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

def unique_object(pairs):
    d={}
    for key,value in pairs:
        if key in d: raise ValueError(f'duplicate JSON key: {key}')
        d[key]=value
    return d

def keys(obj,expected):
    if not isinstance(obj,dict) or set(obj)!=set(expected):
        raise ValueError(f'expected exactly the keys {expected}, got {obj!r}')

def validate(request):
    keys(request,['schema','llvm_major','target_triple','data_layout','entries'])
    if request['schema']!='bennett-arith-instantiations-1': raise ValueError('unknown request schema')
    major=request['llvm_major']
    if type(major)!=int or major not in (18,23): raise ValueError('installed LLVM major must be 18 or 23')
    for field in ('target_triple','data_layout'):
        if not isinstance(request[field],str) or not request[field] or any(ord(c)<32 for c in request[field]):
            raise ValueError(f'invalid {field}')
    if not isinstance(request['entries'],list): raise ValueError('entries must be an array')
    g=module('generate');bases={f[0] for f in g.FORMATS}
    unique={}
    for e in request['entries']:
        if not isinstance(e,dict): raise ValueError('entry must be an object')
        if e.get('op')=='powi':
            keys(e,['op','base','exponent_bits']);k=e['exponent_bits']
            if type(k)!=int or not 1<=k<=8388608: raise ValueError('exponent_bits must be in 1..8388608')
        elif e.get('op') in ('convert_to','convert_from'):
            keys(e,['op','base','format'])
            if major!=23 or e['format'] not in NAMES: raise ValueError('format is not in the LLVM-major published name set')
        else: raise ValueError(f'unknown instance operation: {e.get("op")}')
        if e['base'] not in bases: raise ValueError(f'unknown base: {e["base"]}')
        unique[jcs(e)]=e
    result=dict(request)
    result['entries']=sorted(unique.values(),key=lambda e:(e['op'],e['base'],e.get('format',''),e.get('exponent_bits',0)))
    return result

def run(args):
    subprocess.run([str(a) for a in args],check=True,timeout=300)

def instantiate(request,destination):
    request=validate(request);g=module('generate');major=request['llvm_major']
    llvm=Path(f'/usr/lib/llvm-{major}/bin')
    destination.mkdir(parents=True,exist_ok=True)
    # Keep build products private; publish the complete result only after verify.
    with tempfile.TemporaryDirectory(prefix='arith-instances-',dir=os.environ['TMPDIR']) as td:
        work=Path(td)
        widths=sorted({e['exponent_bits'] for e in request['entries'] if e['op']=='powi'})
        g.generate(work,widths)
        module('constants').constants(work)
        wrappers=(work/'wrappers.ll').read_text()
        exports=[]
        for e in request['entries']:
            fi=next(i for i,f in enumerate(g.FORMATS) if f[0]==e['base'])
            c=f'i{g.FORMATS[fi][1]}';op=e['op']
            if op=='powi':
                k=e['exponent_bits']
                for rm in (False,True):
                    name=f'__bennett_sf_powi_{e["base"]}_i{k}'+('_rm' if rm else '')
                    exports.append(dict(symbol=name,function_type=f'{c} ({c}, i{k}'+(', i32)' if rm else ')')))
                continue
            ni=NAMES.index(e['format']);n=f'i{8 if ni<8 else 6 if ni<10 else 4}'
            ret,params=(n,[c,'i32','i1']) if op=='convert_to' else (c,[n])
            symbol=f'__bennett_sf_{op}_{e["format"]}_{e["base"]}'
            exports.append(dict(symbol=symbol,function_type=f'{ret} ({", ".join(params)})'))
            source=params[0]
            ir=[f'define {ret} @{symbol}({", ".join(t+" %a"+str(i) for i,t in enumerate(params))}) {{',
                '%in = alloca i128, align 16','%out = alloca i128, align 16']
            v='%a0'
            if source!='i128': ir+= [f'%v = zext {source} %a0 to i128'];v='%v'
            ir += [f'store i128 {v}, ptr %in, align 16']
            if op=='convert_to': ir+=['%sat = zext i1 %a2 to i32']
            ir += [f'call void @bennett_sf_named(ptr %out, i32 {fi}, i32 {ni}, i32 {int(op=="convert_to")}, ptr %in, i32 '+('%a1, i32 %sat)' if op=='convert_to' else '0, i32 0)'),
                   '%r = load i128, ptr %out, align 16']
            v='%r'
            if ret!='i128': ir += [f'%result = trunc i128 %r to {ret}'];v='%result'
            ir += [f'ret {ret} {v}','}']
            wrappers+='\n'+'\n'.join(ir)+'\n'
        wrappers+='declare void @bennett_sf_named(ptr, i32, i32, i32, ptr, i32, i32)\n'
        # LLVM's quoted strings use byte escapes, not JSON escapes.
        def quoted(s):
            return ''.join(chr(b) if 32<=b<127 and b not in (34,92) else f'\\{b:02X}' for b in s.encode())
        def target(ir):
            ir=re.sub(r'^target datalayout = .*$',f'target datalayout = "{quoted(request["data_layout"])}"',ir,flags=re.M)
            return re.sub(r'^target triple = .*$',f'target triple = "{quoted(request["target_triple"])}"',ir,flags=re.M)
        (work/'wrappers.ll').write_text(target(wrappers))
        # LLVM 18's AArch64 C frontend rejects _BitInt(512), even though LLVM
        # integer IR supports it. Emit the portable integer implementation using
        # the pinned frontend that supports these types, then assign the request
        # layout/triple. Only pointer/i32 core calls cross the wrapper boundary;
        # private C aggregate conventions remain consistent inside this module.
        run([llvm/'clang','-I',work,'-target','x86_64-unknown-linux-gnu','-std=c2x',f'-DBENNETT_LLVM_MAJOR={major}',
             '-O1','-ffreestanding','-fno-builtin','-fno-vectorize','-fno-slp-vectorize','-fno-ident','-S','-emit-llvm',ROOT/'softfloat/named.c','-o',work/'core.ll'])
        ir=(work/'core.ll').read_text()
        if re.search(r'\basm\b|@llvm\.(?:x86|aarch64)\.',ir):
            raise ValueError('integer implementation contains a target-specific operation')
        ir=re.sub(r'"(?:target-cpu|target-features|tune-cpu|target-abi)"="[^"]*"','',ir)
        ir=re.sub(r'^source_filename = .*','source_filename = "softfloat/named.c"',ir,flags=re.M)
        (work/'core.ll').write_text(target(ir))
        for name in ('core','wrappers'): run([llvm/'llvm-as',work/f'{name}.ll','-o',work/f'{name}.bc'])
        run([llvm/'llvm-link',work/'core.bc',work/'wrappers.bc','-o',work/'linked.bc'])
        exports.sort(key=lambda e:e['symbol'])
        (work/'exports.txt').write_text('\n'.join(e['symbol'] for e in exports))
        run([llvm/'opt','-passes=internalize,globaldce',f'-internalize-public-api-file={work/"exports.txt"}',work/'linked.bc','-o',work/'bennett-arith.bc'])
        run([llvm/'opt','-passes=verify','-disable-output',work/'bennett-arith.bc'])
        # LLVM may upgrade historical data-layout spellings (notably AArch64
        # on LLVM 23). Compare with the same major's interpretation of a tiny
        # reference module containing only the requested target fields.
        (work/'target.ll').write_text(target('target datalayout = ""\ntarget triple = ""\n'))
        run([llvm/'llvm-as',work/'target.ll','-o',work/'target.bc'])
        def disassemble(path):
            return subprocess.check_output([str(llvm/'llvm-dis'),str(path),'-o','-'],text=True,timeout=60)
        actual=disassemble(work/'bennett-arith.bc');reference=disassemble(work/'target.bc')
        for field in ('datalayout','triple'):
            pattern=rf'^target {field} = .*'
            if re.findall(pattern,actual,re.M)!=re.findall(pattern,reference,re.M):
                raise ValueError(f'output {field} does not match the LLVM-major request interpretation')
        definitions={name:f'{ret} ({", ".join(p.split()[0] for p in params.split(", "))})'
                     for ret,name,params in re.findall(r'^define (i[0-9]+) @([^ (]+)\(([^)]*)\)',actual,re.M)}
        if definitions!={e['symbol']:e['function_type'] for e in exports}:
            raise ValueError('output LLVM definitions do not match requested function types')
        data=(work/'bennett-arith.bc').read_bytes()
        manifest=dict(schema='bennett-arith-instances-1',llvm_major=major,
                      target_triple=request['target_triple'],data_layout=request['data_layout'],
                      request_sha256=hashlib.sha256(jcs(request)).hexdigest(),
                      bitcode_sha256=hashlib.sha256(data).hexdigest(),exports=exports)
        (destination/'bennett-arith.bc').write_bytes(data)
        (destination/'manifest.json').write_bytes(jcs(manifest))

if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit(__doc__)
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'),object_pairs_hook=unique_object,
                       parse_constant=lambda s: (_ for _ in ()).throw(ValueError(f'invalid JSON number {s}')))
    instantiate(request,Path(sys.argv[2]))
