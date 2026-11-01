"""Emit contract ABI wrappers, a machine-readable manifest, and test-only bridge.
C's ABI lowering of _BitInt(80/128) is NOT the dialect's i80/i128 ABI.
Keeping these wrappers in IR avoids accidental aggregate or sret ABI changes.
"""
import json
import pathlib
import sys

FORMATS = [('f16', 16, 'binary16'), ('bf16', 16, 'bfloat16'),
           ('f32', 32, 'binary32'), ('f64', 64, 'binary64'),
           ('f80', 80, 'x86_fp80'), ('f128', 128, 'binary128'),
           ('ppcf128',128,'PPCDoubleDouble')]
OPS = ('add sub mul div rem cmp fptosi fptoui sitofp uitofp sqrt floor ceil trunc '
       'round roundeven rint nearbyint canonicalize minnum maxnum minimum maximum '
       'minimumnum maximumnum fma isfpclass ldexp frexp lround llround lrint llrint '
       'convert powi modf sin cos tan asin acos atan atan2 sinh cosh tanh exp exp2 exp10 log log2 log10 pow sincos sincospi').split()


def entries(formats=FORMATS):
    for fi, (suffix, bits, fmt) in enumerate(formats):
        C = f'i{bits}'
        for op in OPS:
            if op == 'convert':
                continue
            ret, params = C, [C]
            if op in ('add', 'sub', 'mul', 'div', 'rem', 'minnum', 'maxnum',
                      'minimum', 'maximum', 'minimumnum', 'maximumnum', 'atan2', 'pow'):
                params += [C]
            if op == 'fma':
                params += [C, C]
            if op in ('sitofp', 'uitofp'):
                params = ['i128']
            if op in ('cmp', 'isfpclass'):
                ret, params = 'i1', ([C, C, 'i32'] if op == 'cmp' else [C, 'i32'])
            if op in ('fptosi', 'fptoui', 'lround', 'llround', 'lrint', 'llrint'):
                ret, params = 'i128', [C, 'i32']
            if op == 'ldexp' or op == 'powi':
                params += ['i32']
            if op == 'frexp':
                ret = f'{{ {C}, i32 }}'
            if op in ('modf','sincos','sincospi'):
                ret = f'{{ {C}, {C} }}'
            name = f'__bennett_sf_{op}_{suffix}' + ('_i32' if op == 'powi' else '')
            yield dict(name=name, result=ret, params=params, format=fmt, fi=fi, op=op,
                       extra=0, wide=False, constrained=False)
            if op in ('fptosi', 'fptoui', 'lround', 'llround', 'lrint', 'llrint', 'sitofp', 'uitofp'):
                tofp = op in ('sitofp', 'uitofp')
                for constrained in (False, True):
                    yield dict(name=name+'_wide'+('_rm' if constrained else ''), result=C if tofp else 'void',
                               params=(['ptr', 'i32'] if tofp else ['ptr', C, 'i32'])+(['i32'] if constrained else []),
                               format=fmt, fi=fi, op=op, extra=0, wide=True, constrained=constrained)
            # The numeric core also supports explicit rounding and flag accumulation.
            if op not in ('isfpclass', 'canonicalize', 'frexp', 'modf'):
                yield dict(name=name+'_rm', result=ret, params=params+['i32'],
                           format=fmt, fi=fi, op=op, extra=0, wide=False, constrained=True)
        for di, (dest, db, df) in enumerate(formats):
            if di == fi:
                continue
            for op in ('fpext', 'fptrunc'):
                for constrained in (False, True):
                    yield dict(name=f'__bennett_sf_{op}_{suffix}_{dest}'+('_rm' if constrained else ''),
                               result=f'i{db}', params=[C]+(['i32'] if constrained else []),
                               format=f'{fmt} -> {df}', fi=fi, op='convert', extra=di,
                               wide=False, constrained=constrained)


POWI_WIDTHS = [1,8,16,64,128,192,256,513,1025]

def powi_entries(widths):
    for fi,(suffix,bits,fmt) in enumerate(FORMATS):
        for k in widths:
            if k==32:continue
            assert 1<=k<=8388607, 'LLVM integer exponent width out of range'
            for constrained in (False,True):
                yield dict(name=f'__bennett_sf_powi_{suffix}_i{k}'+('_rm' if constrained else ''),
                    result=f'i{bits}',params=[f'i{bits}',f'i{k}']+(['i32'] if constrained else []),
                    format=fmt,fi=fi,op='powi',extra=0,wide=False,constrained=constrained,exponent_bits=k)

def powi_wrapper(e):
    C=e['result'];K=f"i{e['exponent_bits']}";suffix=FORMATS[e['fi']][0]
    rm=', i32 %a2' if e['constrained'] else ''
    tag='_rm' if e['constrained'] else ''
    mul=f'__bennett_sf_mul_{suffix}{tag}';div=f'__bennett_sf_div_{suffix}{tag}'
    one=[0x3c00,0x3f80,0x3f800000,0x3ff0000000000000,0x3fff8000000000000000,0x3fff0000000000000000000000000000,0x3ff0000000000000][e['fi']]
    shift=f'lshr {K} %n, 1' if e['exponent_bits']>1 else 'and i1 %n, 0'
    return f'''define {C} @{e['name']}({', '.join(t+' %a'+str(i) for i,t in enumerate(e['params']))}) {{
entry:
  %neg = icmp slt {K} %a1, 0
  %abs = sub {K} 0, %a1
  %initial = select i1 %neg, {K} %abs, {K} %a1
  %zero = icmp eq {K} %initial, 0
  br i1 %zero, label %empty, label %loop
empty:
  ret {C} {one}
loop:
  %n = phi {K} [ %initial, %entry ], [ %n2, %square ]
  %base = phi {C} [ %a0, %entry ], [ %squared, %square ]
  %result = phi {C} [ {one}, %entry ], [ %next, %square ]
  %bit = trunc {K} %n to i1
  br i1 %bit, label %odd, label %even
odd:
  %product = call {C} @{mul}({C} %result, {C} %base{rm})
  br label %advance
even:
  br label %advance
advance:
  %next = phi {C} [ %product, %odd ], [ %result, %even ]
  %n2 = {shift}
  %done = icmp eq {K} %n2, 0
  br i1 %done, label %finish, label %square
square:
  %squared = call {C} @{mul}({C} %base, {C} %base{rm})
  br label %loop
finish:
  br i1 %neg, label %reciprocal, label %return
reciprocal:
  %recip = call {C} @{div}({C} {one}, {C} %next{rm})
  ret {C} %recip
return:
  ret {C} %next
}}'''.replace('  %bit = trunc i1 %n to i1','  %bit = and i1 %n, true').splitlines()


def generate(dest, widths=POWI_WIDTHS):
    dest.mkdir(parents=True, exist_ok=True)
    rows = list(entries())+list(powi_entries(widths))
    ir = ['; Generated contract ABI; do not use a C ABI for carrier functions.',
          'declare void @bennett_sf_eval(ptr, i32, i32, ptr, i32, i32)',
          'declare void @bennett_sf_wide(ptr, i32, i32, ptr, i32, ptr, i32)',
          '@__bennett_rt_fenv = external global { i32, i32 }']
    bridge = []
    cases = []
    for index, e in enumerate(rows):
        e['id'] = index
        e['signature'] = f"{e['result']} ({', '.join(e['params'])})"
        e['status'] = 'deterministic-integer-libm-v1' if OPS.index(e['op'])>=OPS.index('sin') else 'exact' if e['op'] != 'powi' else 'deterministic-repeated-squaring'
        ret, params, op = e['result'], e['params'], e['op']
        if 'exponent_bits' in e:
            ir += powi_wrapper(e)
        else:
            ir += [f"define {ret} @{e['name']}({', '.join(t+' %a'+str(i) for i,t in enumerate(params))}) {{",
                   '  %in = alloca [3 x i128], align 16', '  %out = alloca [3 x i128], align 16',
                   '  store [3 x i128] zeroinitializer, ptr %in, align 16']
            fps = []
            extra = str(e['extra'])
            slot = 'null'
            for i,t in enumerate(params):
                if e['constrained'] and i == len(params)-1:
                    continue
                if t == 'ptr':
                    slot = f'%a{i}'
                elif t == 'i32' and i == len(params)-1-int(e['constrained']) and (e['wide'] or op in ('cmp','isfpclass','fptosi','fptoui','lround','llround','lrint','llrint','ldexp','powi')):
                    extra = f'%a{i}'
                else:
                    n = len(fps); fps.append(i)
                    ir += [f'  %p{n} = getelementptr i128, ptr %in, i32 {n}']
                    value = f'%a{i}'
                    if t != 'i128':
                        ir += [f'  %z{n} = zext {t} {value} to i128']; value=f'%z{n}'
                    ir += [f'  store i128 {value}, ptr %p{n}, align 16']
            rm = f'%a{len(params)-1}' if e['constrained'] else '0'
            if e['wide']:
                ir += [f'  call void @bennett_sf_wide(ptr %out, i32 {e["fi"]}, i32 {OPS.index(op)}, ptr {slot}, i32 {extra}, ptr %in, i32 {rm})']
            else:
                ir += [f'  call void @bennett_sf_eval(ptr %out, i32 {e["fi"]}, i32 {OPS.index(op)}, ptr %in, i32 {extra}, i32 {rm})']
            if e['constrained']:
                ir += ['  %pf = getelementptr i128, ptr %out, i32 2',
                       '  %fw = load i128, ptr %pf, align 16', '  %fl = trunc i128 %fw to i32',
                       '  %env = getelementptr { i32, i32 }, ptr @__bennett_rt_fenv, i32 0, i32 1',
                       '  %old = load i32, ptr %env', '  %new = or i32 %old, %fl', '  store i32 %new, ptr %env']
            if ret == 'void':
                ir += ['  ret void', '}']
            else:
                ir += ['  %r0 = load i128, ptr %out, align 16']
                if ret.startswith('{'):
                    types = ret[2:-2].split(', ')
                    ir += ['  %p1out = getelementptr i128, ptr %out, i32 1',
                           '  %r1 = load i128, ptr %p1out, align 16']
                    vals = []
                    for j,t in enumerate(types):
                        val = f'%r{j}'
                        if t != 'i128':
                            ir += [f'  %ret{j} = trunc i128 {val} to {t}']; val=f'%ret{j}'
                        vals.append(val)
                    ir += [f'  %pair0 = insertvalue {ret} zeroinitializer, {types[0]} {vals[0]}, 0',
                           f'  %pair1 = insertvalue {ret} %pair0, {types[1]} {vals[1]}, 1', f'  ret {ret} %pair1', '}']
                else:
                    value = '%r0'
                    if ret != 'i128':
                        ir += [f'  %ret = trunc i128 %r0 to {ret}']; value='%ret'
                    ir += [f'  ret {ret} {value}', '}']
        # A separate bridge tests the published wrappers, not a C recompile.
        bridge += [f"declare {ret} @{e['name']}({', '.join(params)})"]
        case = [f'case{index}:']
        args = []
        for j,t in enumerate(params):
            case += [f'  %p{index}_{j} = getelementptr i128, ptr %args, i32 {j}',
                     f'  %v{index}_{j} = load i128, ptr %p{index}_{j}, align 16']
            v = f'%v{index}_{j}'
            if t == 'ptr':
                case += [f'  %x{index}_{j} = inttoptr i128 {v} to ptr']; v=f'%x{index}_{j}'
            elif t.startswith('i') and int(t[1:])>128:
                case += [f'  %ptr{index}_{j} = inttoptr i128 {v} to ptr', f'  %x{index}_{j} = load {t}, ptr %ptr{index}_{j}, align 1']; v=f'%x{index}_{j}'
            elif t != 'i128':
                case += [f'  %x{index}_{j} = trunc i128 {v} to {t}']; v=f'%x{index}_{j}'
            args.append(t+' '+v)
        call = f"call {ret} @{e['name']}({', '.join(args)})"
        case += [f'  %r{index} = '+call if ret!='void' else '  '+call]
        types = ret[2:-2].split(', ') if ret.startswith('{') else ([] if ret=='void' else [ret])
        for j,t in enumerate(types):
            v = f'%r{index}'
            if ret.startswith('{'):
                case += [f'  %el{index}_{j} = extractvalue {ret} {v}, {j}']; v=f'%el{index}_{j}'
            if t != 'i128':
                case += [f'  %wide{index}_{j} = zext {t} {v} to i128']; v=f'%wide{index}_{j}'
            case += [f'  %o{index}_{j} = getelementptr i128, ptr %out, i32 {j}',
                     f'  store i128 {v}, ptr %o{index}_{j}, align 16']
        case += ['  ret void']
        cases += case
    bridge += ['define void @test_call(i32 %id, ptr %args, ptr %out) {',
               '  switch i32 %id, label %bad [']
    bridge += [f'    i32 {i}, label %case{i}' for i in range(len(rows))]
    bridge += ['  ]', 'bad:', '  call void @llvm.trap()', '  unreachable']+cases+['}', 'declare void @llvm.trap()',
                '@__bennett_rt_fenv = global { i32, i32 } zeroinitializer']
    layout='target datalayout = \"e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128\"'
    triple='target triple = \"x86_64-unknown-linux-gnu\"'
    ir=[layout,triple]+ir
    bridge=[layout,triple]+bridge
    for e in rows:
        e['section']='13.4' if e['op'] in ('powi','modf') or OPS.index(e['op'])>=OPS.index('sin') else '13.5' if e['constrained'] else '13.1'
    (dest/'wrappers.ll').write_text('\n'.join(ir)+'\n')
    (dest/'bridge.ll').write_text('\n'.join(bridge)+'\n')
    (dest/'exports.txt').write_text('\n'.join(e['name'] for e in rows)+'\n__bennett_rt_fenv\n')
    manifest = dict(dialect='0.2.10', dialect_commit='023f5a7', isa='0.8',
                    implementation='integer-core-v2-libm1', exports=rows,
                    external_globals=[dict(name='__bennett_rt_fenv', type='{ i32 round, i32 flags }',
                                           owner='bennett-runtimes', used_by='constrained _rm wrappers only')],
                    staged_exports=[], parametric_families=[
                        dict(name='__bennett_sf_powi_B_i<K>', signature='C_B (C_B, iK)',
                             constrained_name='__bennett_sf_powi_B_i<K>_rm', constrained_signature='C_B (C_B, iK, i32 R)',
                             formats='all seven', status='published listed widths; additional LLVM iK widths generated without narrowing', published_widths=[32]+list(widths), generator='scripts/build MAJOR [K ...]',
                             section='13.4', bead='bennett-arith-0he'),
                        dict(name='__bennett_sf_convert_to_<fmt>_B', signature='C_fmt (C_B)',
                             formats='metadata-named APFloat format from each of seven formats',
                             section='13.1', status='staged', bead='bennett-arith-38c'),
                        dict(name='__bennett_sf_convert_from_<fmt>_B', signature='C_B (C_fmt)',
                             formats='each of seven formats from metadata-named APFloat format',
                             section='13.1', status='staged', bead='bennett-arith-38c')])
    implemented={e['name'] for e in rows}
    for e in entries(FORMATS):
        if e['name'] not in implemented:
            e['signature']=f"{e['result']} ({', '.join(e['params'])})"
            e.update(status='staged', bead='bennett-arith-r3d', section='13.1/13.3/13.5')
            manifest['staged_exports'].append(e)
    manifest['numerical_accuracy'] = dict(contract='13.4 explicitly waives correct rounding and specifies no error bound',
        claim='deterministic approximation; no global correct-rounding or ulp-bound proof', working_significand_bits=224,
        payne_hanek_constant_bits=17408, verification='tests/test_trans.py and tests/test_trans_extra.py compare published bitcode with MPFR at 384 bits; <=4 ulp engineering acceptance, exhaustive f16/bf16 sin <=1 ulp')
    manifest['ppc_semantics'] = dict(oracle='same-major LLVM APFloat', high_component_carrier_bits='0..63',
        llvm18='component add/mul and legacy 106-bit fallbacks', llvm23='component integral rounding and integer conversion, otherwise same legacy fallbacks',
        conflicts='b-dialect-spec-dfd; APFloat PPC-to-IEEE conversion uses high component only; sqrt absent in APFloat uses correctly rounded legacy 106-bit result')
    manifest['contract_questions']=[dict(bead='bennett-arith-chn', section='13.1/13.5',
        capability='constrained.fcmps signaling comparison',
        required_change='Distinguish signaling comparison from quiet cmp_B_rm in the published ABI; see bead for exact proposed spelling.')]
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__ == '__main__':
    generate(pathlib.Path(sys.argv[1]), sorted(set(POWI_WIDTHS+[int(k) for k in sys.argv[2:]])))
