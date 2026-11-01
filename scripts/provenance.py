"""Path-independent provenance for the linked binary edge (no self-referential HEAD)."""
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
major=sys.argv[1];dist=root/f'dist/llvm{major}';p=dist/'manifest.json'
m=json.loads(p.read_text())
m['llvm_major']=int(major)
m['bitcode_sha256']=hashlib.sha256((dist/'bennett-arith.bc').read_bytes()).hexdigest()
m['tool_versions']={t:subprocess.check_output([f'/usr/lib/llvm-{major}/bin/{t}','--version'],text=True).splitlines()[0] for t in ['clang','llvm-as','llvm-link','opt']}
m['sources']={}
for source in sorted([*root.glob('softfloat/*.c'),*root.glob('softfloat/*.h'),*root.glob('softfloat/*.py'),root/'scripts/build',root/'scripts/provenance.py']):
    data=source.read_bytes()
    m['sources'][str(source.relative_to(root))]={'sha256':hashlib.sha256(data).hexdigest(),'git_blob_sha1':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
p.write_text(json.dumps(m,indent=2)+'\n')
