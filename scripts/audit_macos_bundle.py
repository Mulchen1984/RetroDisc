"""Read-only Mach-O relocation/signature audit for a built macOS app."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

app=Path(sys.argv[1]).resolve()
files=[];external=[]
for path in sorted(app.rglob('*')):
    if path.is_symlink() or not path.is_file():continue
    with path.open('rb') as f:magic=f.read(4)
    if magic not in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca'):continue
    dependencies=subprocess.run(['otool','-L',str(path)],capture_output=True,text=True,check=True).stdout.splitlines()[1:]
    for line in dependencies:
        dep=line.strip().split(' (',1)[0]
        if dep.startswith('/') and not dep.startswith(('/usr/lib/','/System/Library/')):
            external.append({'file':str(path.relative_to(app)),'dependency':dep})
    files.append(str(path.relative_to(app)))
signature=subprocess.run(['codesign','--verify','--deep','--strict',str(app)],capture_output=True,text=True)
manifest={str(p.relative_to(app)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
          for p in sorted(app.rglob('*')) if p.is_file() and not p.is_symlink()}
result={'app':str(app),'mach_o_files':len(files),'external_dependencies':external,
        'signature_valid':signature.returncode==0,'signature_error':signature.stderr,
        'files_sha256':manifest,'ok':not external and signature.returncode==0}
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
