"""Black-box tests of the offline 0.2.12 request and actual LLVM carrier ABI.

Run with python3 -I softfloat/test_instances.py. Expected numbers use Fraction;
the implementation is invoked only as a separate generator and linked bitcode.
"""
import ctypes
from fractions import Fraction as Q
from functools import cache, lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ['TMPDIR']) / 'instances-test'
WORK.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('edge', ROOT/'tests/test_edge.py')
edge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edge)
FORMATS = {
    # bits, precision, exponent bits, bias, nonfinite encoding
    'Float8E5M2': (8,3,5,15,'ieee'),
    'Float8E5M2FNUZ': (8,3,5,16,'uz'),
    'Float8E4M3': (8,4,4,7,'ieee'),
    'Float8E4M3FN': (8,4,4,7,'fn'),
    'Float8E4M3FNUZ': (8,4,4,8,'uz'),
    'Float8E4M3B11FNUZ': (8,4,4,11,'uz'),
    'Float8E3M4': (8,5,3,3,'ieee'),
    'Float8E8M0FNU': (8,1,8,127,'scale'),
    'Float6E3M2FN': (6,3,3,3,'finite'),
    'Float6E2M3FN': (6,4,2,1,'finite'),
    'Float4E2M1FN': (4,2,2,1,'finite'),
}

def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()

def decode(x, f):
    n,p,eb,bias,kind = f
    if kind == 'scale':
        return 'nan' if x == 255 else edge.power(x-127)
    sign=x>>(n-1); body=x & ((1<<(n-1))-1)
    exponent=body>>(p-1); fraction=body & ((1<<(p-1))-1)
    if kind == 'uz' and x == 1<<(n-1): return 'nan'
    if kind == 'fn' and body == (1<<(n-1))-1: return 'nan'
    if kind == 'ieee' and exponent == (1<<eb)-1:
        return 'nan' if fraction else ('-inf' if sign else 'inf')
    v=(fraction+((1<<(p-1)) if exponent else 0))*edge.power((exponent or 1)-bias-p+1)
    return -v if sign else v

@cache
def finite_values(f):
    n,p,eb,bias,kind=f
    return {decode(i,f):i for i in range(1<<(n if kind=='scale' else n-1)) if isinstance(decode(i,f),Q)}

@cache
def limits(f):
    values=finite_values(f)
    return min(values),max(values),values[max(values)]

@lru_cache(maxsize=32768)
def expected_to(value, sign, f, rm, sat):
    n,p,eb,bias,kind=f
    nan = {'ieee': (((1<<eb)-1)<<(p-1)) | (1<<max(0,p-2)),
           'uz': 1<<(n-1), 'fn': (1<<(n-1))-1, 'finite': 0, 'scale': 255}[kind]
    if value == 'nan': return nan
    values=finite_values(f)
    minimum,maximum,maxbits=limits(f)
    if kind == 'scale' and sign and value != 0: return 0
    if isinstance(value,str):
        if not sat and kind!='ieee': return 0
        result=maxbits if sat else (((1<<eb)-1)<<(p-1) if kind=='ieee' else 0)
    else:
        v=abs(value)
        if kind == 'scale':
            if v < minimum: return 0
            step=edge.log2q(v)
        else:
            step=max(edge.log2q(v) if v else 1-bias, 1-bias)-p+1
        units,_=edge.roundedq(v/edge.power(step),sign,rm)
        rounded=units*edge.power(step)
        if rounded>maximum:
            if not sat and kind!='ieee': return 0
            result=maxbits if sat else (((1<<eb)-1)<<(p-1) if kind=='ieee' else 0)
        else:
            result=values[rounded]
            if not result and kind=='uz': return 0
    return result | ((sign<<(n-1)) if kind!='scale' and (result or kind in ('ieee','finite','fn')) else 0)

count=0
# Invalid requests must fail before creating a publication. This also guards
# Python's bool-is-an-int behavior and JSON's otherwise permissive parser.
valid=dict(schema='bennett-arith-instantiations-1',llvm_major=23,
           target_triple='x86_64-unknown-linux-gnu',data_layout='e',entries=[])
bad=[{**valid,'schema':'unknown'}, {**valid,'extra':0},
     {**valid,'llvm_major':True}, {**valid,'entries':{}},
     {**valid,'target_triple':'x86_64\n'}]
bad += [{**valid,'entries':[dict(op='powi',base='f32',exponent_bits=k)]}
        for k in (0,8388609,True,1.0)]
bad += [{**valid,'entries':[dict(op='convert_to',base='f32',format='made-up')]},
        {**valid,'llvm_major':18,'entries':[dict(op='convert_from',base='f16',format='Float8E4M3')]},
        {**valid,'entries':[dict(op='powi',base='f32',exponent_bits=7,extra=1)]}]
for i,body in enumerate([json.dumps(x) for x in bad]+['{"schema":"a","schema":"b"}','{"llvm_major":NaN}']):
    req=WORK/'invalid.json';req.write_text(body)
    out=WORK/f'invalid-{i}'
    proc=subprocess.run([sys.executable,'-I',str(ROOT/'softfloat/instantiate.py'),str(req),str(out)],capture_output=True,text=True)
    assert proc.returncode!=0 and not (out/'bennett-arith.bc').exists(),body
print(f'{len(bad)+2} invalid requests rejected before publication')
for major in (18,23):
    llvm=Path(f'/usr/lib/llvm-{major}/bin')
    layout='e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128'
    bases={**edge.FORMATS,'ppcf128': (128,106,11,1023,False)}
    entries=[dict(op='powi',base=b,exponent_bits=k) for b in bases for k in (1,7,32,193)]
    if major==23:
        entries += [dict(op=op,base=b,format=f) for b in bases for f in FORMATS for op in ('convert_to','convert_from')]
    request=dict(schema='bennett-arith-instantiations-1',llvm_major=major,
                 target_triple='x86_64-unknown-linux-gnu',data_layout=layout,entries=entries[::-1]+entries[:2])
    req=WORK/f'request-{major}.json';req.write_text(json.dumps(request))
    out=WORK/f'llvm{major}'
    if '--reuse' not in sys.argv:
        subprocess.run([sys.executable,'-I',str(ROOT/'softfloat/instantiate.py'),str(req),str(out)],check=True)
    mbytes=(out/'manifest.json').read_bytes();m=json.loads(mbytes)
    assert mbytes==canonical(m), 'manifest must be JCS without trailing newline'
    request['entries']=sorted(entries,key=lambda e:(e['op'],e['base'],e.get('format',''),e.get('exponent_bits',0)))
    assert m['request_sha256']==hashlib.sha256(canonical(request)).hexdigest()
    bc=out/'bennett-arith.bc'
    assert m['bitcode_sha256']==hashlib.sha256(bc.read_bytes()).hexdigest()
    assert m['schema']=='bennett-arith-instances-1'
    assert m['exports']==sorted(m['exports'],key=lambda e:e['symbol'])
    expected={}
    for entry in request['entries']:
        base=entry['base'];c=f'i{bases[base][0]}'
        if entry['op']=='powi':
            k=entry['exponent_bits'];name=f'__bennett_sf_powi_{base}_i{k}'
            expected[name]=f'{c} ({c}, i{k})'
            expected[name+'_rm']=f'{c} ({c}, i{k}, i32)'
        else:
            fmt=entry['format'];n=f'i{FORMATS[fmt][0]}'
            expected[f'__bennett_sf_{entry["op"]}_{fmt}_{base}']=f'{n} ({c}, i32, i1)' if entry['op']=='convert_to' else f'{c} ({n})'
    assert {e['symbol']:e['function_type'] for e in m['exports']}==expected
    ir=subprocess.check_output([str(llvm/'llvm-dis'),str(bc),'-o','-'],text=True)
    assert f'target datalayout = "{layout}"' in ir
    assert 'target triple = "x86_64-unknown-linux-gnu"' in ir
    assert not re.search(r'\b(?:fadd|fsub|fmul|fdiv|frem|fcmp|fptrunc|fpext|sitofp|uitofp)\b',ir)
    definitions=set(re.findall(r'^define (?!internal)[^@\n]+@([^ (]+)',ir,re.M))
    assert definitions=={e['symbol'] for e in m['exports']}
    signatures={name:f'{ret} ({", ".join(p.split()[0] for p in params.split(", "))})'
                for ret,name,params in re.findall(r'^define (i[0-9]+) @([^ (]+)\(([^)]*)\)',ir,re.M)}
    assert signatures==expected
    assert not re.findall(r'^declare .*@(?!llvm\.)[^ (]+',ir,re.M)
    bridge=['@__bennett_rt_fenv = global {i32, i32} zeroinitializer']
    for i,row in enumerate(m['exports']):
        ret,params=row['function_type'].split(' (');params=params[:-1].split(', ')
        bridge += [f'declare {ret} @{row["symbol"]}({", ".join(params)})',f'define void @call{i}(ptr %in, ptr %out) {{']
        args=[]
        for j,t in enumerate(params):
            bridge += [f'%p{j} = getelementptr i256, ptr %in, i32 {j}',f'%v{j} = load {t}, ptr %p{j}, align 1']
            args.append(f'{t} %v{j}')
        bridge += [f'%r = call {ret} @{row["symbol"]}({", ".join(args)})',f'store {ret} %r, ptr %out, align 1','ret void','}']
    bridgepath=out/'test.ll';bridgepath.write_text('\n'.join(bridge))
    so=out/'test.so'
    subprocess.run([str(llvm/'clang'),'-shared','-fPIC',str(bc),str(bridgepath),'-o',str(so)],check=True)
    lib=ctypes.CDLL(str(so));env=(ctypes.c_int*2).in_dll(lib,'__bennett_rt_fenv')
    def check(i,args,want,flags=0):
        global count
        fn=getattr(lib,f'call{i}');fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        src=ctypes.create_string_buffer(b''.join(x.to_bytes(32,'little') for x in args))
        dst=ctypes.create_string_buffer(16);env[0]=4;env[1]=32
        fn(src,dst);actual=int.from_bytes(dst.raw,'little')
        assert actual==want,(m['exports'][i]['symbol'],args,hex(actual),hex(want))
        assert env[0]==4 and env[1]==32|flags,(m['exports'][i]['symbol'],list(env),flags)
        count+=1
    for i,row in enumerate(m['exports']):
        name=row['symbol'];b=next(b for b in bases if f'_{b}_i' in name or name.endswith('_'+b))
        f=bases[b]
        if 'powi' in name:
            one=edge.encode(Q(1),edge.FORMATS['f64'] if b=='ppcf128' else f)[0]
            k=int(re.search(r'_i(\d+)',name)[1]);exponent=(1<<k)-1
            check(i,[one,exponent]+([0] if name.endswith('_rm') else []),one)
            if k==193 and b=='f64':
                constrained=name.endswith('_rm');rm=[0] if constrained else []
                two=edge.encode(Q(2),f)[0]
                for exponent,want in [(1<<180,edge.infinity(f)),((1<<k)-(1<<180),0)]:
                    check(i,[two,exponent]+rm,want,20 if constrained else 0)
            continue
        fmt=next(fmt for fmt in FORMATS if f'_{fmt}_' in name);nf=FORMATS[fmt]
        if 'convert_from' in name:
            for bits in range(1<<nf[0]):
                value=decode(bits,nf);sign=bits>>(nf[0]-1) if nf[4]!='scale' else 0
                if value=='-inf': value='inf'
                want=edge.encode(value,edge.FORMATS['f64'] if b=='ppcf128' else f,zero_sign=sign)[0]
                check(i,[bits],want)
        else:
            values=[Q(0),Q(1),Q(-1),edge.power(-140),edge.power(130),'inf','nan']
            positives=sorted({decode(x,nf) for x in range(1<<(nf[0] if nf[4]=='scale' else nf[0]-1)) if isinstance(decode(x,nf),Q)})
            for a,z in zip(positives,positives[1:]):
                values += [(a+z)/2, (a+z)/2-edge.power(-150), (a+z)/2+edge.power(-150)]
            values += [-v for v in values if isinstance(v,Q)]
            values += [positives[-1]*2,positives[-1]+(positives[-1]-positives[-2])/2]
            for value in values:
                bits=edge.encode(value,edge.FORMATS['f64'] if b=='ppcf128' else f)[0]
                actualvalue,sign,_=edge.decode(bits,edge.FORMATS['f64'] if b=='ppcf128' else f)
                for rm in range(5):
                    for sat in (0,1): check(i,[bits,rm,sat],expected_to(actualvalue,sign,nf,rm,sat))
            bf=edge.FORMATS['f64'] if b=='ppcf128' else f
            for bits in [1<<(bf[0]-1),edge.infinity(bf,1),edge.nan(bf)|1]:
                value,sign,_=edge.decode(bits,bf)
                for rm in range(5):
                    for sat in (0,1): check(i,[bits,rm,sat],expected_to(value,sign,nf,rm,sat))
            if b=='ppcf128':
                # A sparse low component on either side of a target midpoint
                # must determine rounding even across a gap exceeding 512 bits.
                for a,z in zip(positives,positives[1:]):
                    high=(a+z)/2
                    h=edge.encode(high,bf)[0]
                    for low in (-edge.power(-700),edge.power(-700)):
                        lowbits=edge.encode(low,bf)[0]|0x12345
                        bits=h|(lowbits<<64)
                        value=high+edge.decode(lowbits,bf)[0]
                        for rm in range(5):
                            for sat in (0,1): check(i,[bits,rm,sat],expected_to(value,int(value<0),nf,rm,sat))
    print(f'LLVM {major}: request hash, exact exports, integer closure and carrier values verified ({count} checks)')
print('offline instantiation tests passed')
