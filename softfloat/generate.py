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
       'convert powi modf sin cos tan asin acos atan atan2 sinh cosh tanh exp exp2 exp10 log log2 log10 pow sincos sincospi cmps').split()


def entries(formats=FORMATS):
    for fi, (suffix, bits, fmt) in enumerate(formats):
        C = f'i{bits}'
        for op in OPS:
            if op == 'cmps':
                yield dict(name=f'__bennett_sf_cmps_{suffix}_rm', result='i1', params=[C,C,'i32','i32'],
                           format=fmt, fi=fi, op=op, extra=0, wide=False, constrained=True)
                continue
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
IEEE_COMPARE = {0:10,1:7,2:23,3:52,5:112}

def ieee_compare_wrapper(e):
    """Compare the format's integer fields without retaining the evaluator.

    Ordered positive encodings increase numerically; negative encodings run
    in reverse. Collapse signed zeros for equality, then select the predicate
    truth mask. NaN classification and invalid differ only for cmp/cmps.
    """
    bits=FORMATS[e['fi']][1];C=f'i{bits}';fraction=IEEE_COMPARE[e['fi']]
    magnitude=(1<<(bits-1))-1;infinity=magnitude^((1<<fraction)-1)
    ir=[f"define i1 @{e['name']}({', '.join(t+' %a'+str(i) for i,t in enumerate(e['params']))}) {{"]
    for i in (0,1):
        ir += [f'  %mag{i} = and {C} %a{i}, {magnitude}',
               f'  %nan{i} = icmp ugt {C} %mag{i}, {infinity}',
               f'  %zero{i} = icmp eq {C} %mag{i}, 0']
    ir += ['  %unordered = or i1 %nan0, %nan1',
           '  %bothzero = and i1 %zero0, %zero1',
           f'  %samebits = icmp eq {C} %a0, %a1',
           '  %equal = or i1 %samebits, %bothzero',
           '  %unequal = xor i1 %equal, true',
           f'  %negative = icmp slt {C} %a0, 0',
           f'  %different = xor {C} %a0, %a1',
           f'  %differentsigns = icmp slt {C} %different, 0',
           f'  %ascending = icmp ult {C} %a0, %a1',
           f'  %descending = icmp ugt {C} %a0, %a1',
           '  %samesignless = select i1 %negative, i1 %descending, i1 %ascending',
           '  %rawless = select i1 %differentsigns, i1 %negative, i1 %samesignless',
           '  %less = and i1 %rawless, %unequal',
           '  %eqgtmask = select i1 %equal, i32 170, i32 204',
           '  %mask = select i1 %less, i32 240, i32 %eqgtmask',
           '  %predicate = and i32 %a2, 7',
           '  %shifted = lshr i32 %mask, %predicate',
           '  %ordered = trunc i32 %shifted to i1',
           '  %unorderedtruth = icmp uge i32 %a2, 8',
           '  %result = select i1 %unordered, i1 %unorderedtruth, i1 %ordered']
    if e['constrained']:
        invalid='%unordered'
        if e['op']=='cmp':
            for i in (0,1):
                ir += [f'  %quiet{i} = and {C} %a{i}, {1<<(fraction-1)}',
                       f'  %quietclear{i} = icmp eq {C} %quiet{i}, 0',
                       f'  %snan{i} = and i1 %nan{i}, %quietclear{i}']
            ir += ['  %invalid = or i1 %snan0, %snan1'];invalid='%invalid'
        ir += [f'  %flags = zext i1 {invalid} to i32',
               '  %env = getelementptr { i32, i32 }, ptr @__bennett_rt_fenv, i32 0, i32 1',
               '  %old = load i32, ptr %env, align 4',
               '  %new = or i32 %old, %flags',
               '  store i32 %new, ptr %env, align 4']
    return ir+['  ret i1 %result','}']

def powi_entries(widths):
    for fi,(suffix,bits,fmt) in enumerate(FORMATS):
        for k in widths:
            if k==32:continue
            assert 1<=k<=8388608, 'LLVM integer exponent width out of range'
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
        e['status'] = 'deterministic-integer-libm-v1' if e['op']!='cmps' and OPS.index(e['op'])>=OPS.index('sin') else 'exact' if e['op'] != 'powi' else 'deterministic-repeated-squaring'
        if (e['fi']==6 and e['op']=='fma') or (e['op']=='convert' and e['extra']==6):
            e.update(status='canonical-pair-exact',bead='bennett-arith-4yg')
        ret, params, op = e['result'], e['params'], e['op']
        if op in ('cmp','cmps') and e['fi'] in IEEE_COMPARE:
            e['comparison_implementation']='format-specific-integer-ir'
            ir += ieee_compare_wrapper(e)
        elif 'exponent_bits' in e:
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
                elif t == 'i32' and i == len(params)-1-int(e['constrained']) and (e['wide'] or op in ('cmp','cmps','isfpclass','fptosi','fptoui','lround','llround','lrint','llrint','ldexp','powi')):
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
        e['section']='13.4' if e['op'] in ('powi','modf') or (e['op']!='cmps' and OPS.index(e['op'])>=OPS.index('sin')) else '13.5' if e['constrained'] else '13.1'
    (dest/'wrappers.ll').write_text('\n'.join(ir)+'\n')
    (dest/'bridge.ll').write_text('\n'.join(bridge)+'\n')
    (dest/'exports.txt').write_text('\n'.join(e['name'] for e in rows)+'\n__bennett_rt_fenv\n')
    manifest = dict(dialect='0.2.13', isa='0.8',
                    conformance_pending=['bennett-arith-4yg','bennett-arith-wvh'],
                    instance_generator=dict(command='python3 -I softfloat/instantiate.py REQUEST.json OUTPUT_DIRECTORY',
                        request_schema='bennett-arith-instantiations-1',manifest_schema='bennett-arith-instances-1'),
                    implementation='integer-core-v2-libm1', exports=rows,
                    external_globals=[dict(name='__bennett_rt_fenv', type='{ i32 round, i32 flags }',
                                           owner='bennett-runtimes', used_by='constrained _rm wrappers only')],
                    staged_exports=[], parametric_families=[
                        dict(name='__bennett_sf_powi_B_i<K>', signature='C_B (C_B, iK)',
                             constrained_name='__bennett_sf_powi_B_i<K>_rm', constrained_signature='C_B (C_B, iK, i32 R)',
                             formats='all seven', status='published listed widths; arbitrary LLVM iK widths available offline', published_widths=[32]+list(widths), generator='softfloat/instantiate.py',
                             section='13.4', bead='bennett-arith-0he'),
                        dict(name='__bennett_sf_convert_to_<fmt>_B', signature='iN (C_B, i32 R, i1 Sat)',
                             formats='all eleven LLVM23 interpretation names from each of seven bases; no names on LLVM18',
                             generator='softfloat/instantiate.py',section='13.1', status='available-offline', bead='bennett-arith-38c'),
                        dict(name='__bennett_sf_convert_from_<fmt>_B', signature='C_B (iN)',
                             formats='each of seven bases from all eleven LLVM23 interpretation names; no names on LLVM18',
                             generator='softfloat/instantiate.py',section='13.1', status='available-offline', bead='bennett-arith-38c')])
    implemented={e['name'] for e in rows}
    for e in entries(FORMATS):
        if e['name'] not in implemented:
            e['signature']=f"{e['result']} ({', '.join(e['params'])})"
            e.update(status='staged', bead='bennett-arith-r3d', section='13.1/13.3/13.5')
            manifest['staged_exports'].append(e)
    manifest['numerical_accuracy'] = dict(contract='0.2.13 13.4: full-domain one-local-ulp; constrained correctly rounded selection and exact flags',
        pending_bead='bennett-arith-wvh',
        claim='deterministic approximation; no global correct-rounding or ulp-bound proof', working_significand_bits=240,
        exact_dyadic_families=['pow','exp2','exp10','log2','log10','half-integer sincospi'],
        exact_dyadic_method='normalized integer significands, perfect roots/powers and one final target rounding',
        proven_paths=[dict(operation='exp_ppcf128',domain='finite |x| <= 2^-112',
            method='exact high+low midpoint comparison; quadratic/cubic log(1+h) comparison for directed sides',
            guarantee='correct canonical pair in all five modes; zero is exact, otherwise only inexact',
            test='tests/test_ppc_exp.py',bead='bennett-arith-wvh.1')],
        payne_hanek_constant_bits=17408, verification='tests/test_trans.py and tests/test_trans_extra.py compare published bitcode with adaptive directed MPFR brackets and exact carrier selection; unresolved PPC cases use BENNETT_ARITH_PROMISED')
    manifest['ppc_semantics'] = dict(oracle='independent exact rational arithmetic for explicit guarantees; same-major LLVM APFloat for component operations', high_component_carrier_bits='0..63',
        both_majors='exact high+low conversions, full-width integer inputs, canonical-pair integral rounding, sqrt and one-rounding exact FMA',
        exact_sum_quantum='2^-1074',exact_sum_bits=2176,sqrt_comparison_bits=4352,
        llvm18='component add/mul; legacy 106-bit divide/remainder operation conventions',
        llvm23='same operations as LLVM18, including explicit 0.2.12 exact-value overrides',
        pending_bead='bennett-arith-4yg',
        implementation_gaps='legacy component add/mul and divide/remainder conventions remain versioned')
    manifest['contract_questions']=[]
    manifest['comparison_semantics']=dict(quiet='cmp_B_rm: invalid only on signaling NaN',
        signaling='cmps_B_rm: invalid on any NaN, including false/true predicates',
        specialized_formats=[FORMATS[i][0] for i in IEEE_COMPARE],
        specialization='direct integer IR; no arithmetic evaluator, private helpers or scratch slots',
        predicate_range=[0,15],rounding_operand=0,flags='sticky invalid only; plain cmp_B has no fenv access')
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__ == '__main__':
    generate(pathlib.Path(sys.argv[1]), sorted(set(POWI_WIDTHS+[int(k) for k in sys.argv[2:]])))
