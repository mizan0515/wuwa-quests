"""Check the actual Pages tar against every committed reader build output.

No extraction or links are followed. Development files and unexpected generated
HTML fail; original pages, exports and shared assets must retain their Git bytes.
"""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path,PurePosixPath

FORBIDDEN={'source','docs','scripts','tools','.runtime','.codex-work','.nojekyll'}
def blob_digest(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def expected_files(repo,revision,dist):
 tree={}
 for row in subprocess.check_output(['git','-C',str(repo),'ls-tree','-rz',revision]).split(b'\0'):
  if not row:continue
  meta,path=row.split(b'\t',1);mode,kind,digest=meta.split()
  if kind==b'blob':tree[path.decode('utf8')]=digest.decode()
 paths={p.relative_to(dist).as_posix()for p in dist.rglob('*')if p.is_file()and p.name!='_config.yml'}
 paths.update(name for name in ('content-manifest.json','THIRD_PARTY_NOTICES.md')if name in tree)
 if any(p not in tree for p in paths):raise ValueError('Build has uncommitted publication files')
 return {p:tree[p]for p in paths}
def verify(artifact,expected):
 errors=[];seen=set();extras=[];total=0;html_count=0
 with tarfile.open(artifact)as archive:
  for item in archive:
   if item.isdir():continue
   name=item.name.removeprefix('./');path=PurePosixPath(name)
   if not item.isfile()or path.is_absolute()or'..'in path.parts or name in seen:
    errors.append('Unsafe or duplicate artifact entry: '+name);continue
   seen.add(name);total+=item.size;html_count+=name.endswith('.html')
   if path.parts[0]in FORBIDDEN:errors.append('Development content published: '+name)
   if name not in expected:
    extras.append(name)
    if name.endswith('.html'):errors.append('Unexpected generated HTML: '+name)
    continue
   digest=hashlib.sha1();digest.update(b'blob '+str(item.size).encode()+b'\0');stream=archive.extractfile(item)
   while block:=stream.read(1024*1024):digest.update(block)
   if digest.hexdigest()!=expected[name]:errors.append('Published bytes differ: '+name)
 for name in sorted(set(expected)-seen):errors.append('Missing original publication file: '+name)
 return {'status':'FAIL'if errors else'PASS','payloadBytes':total,'files':len(seen),'htmlFiles':html_count,'expectedFiles':len(expected),'extras':extras,'errors':errors}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--artifact',required=True,type=Path);p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--revision',default='HEAD');p.add_argument('--dist',type=Path,default=Path(__file__).resolve().parents[1]/'dist');p.add_argument('--output',type=Path);a=p.parse_args()
 result=verify(a.artifact,expected_files(a.repo,a.revision,a.dist))
 if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in result.items()if k!='errors'},ensure_ascii=False));print(json.dumps({'errorCount':len(result['errors']),'firstErrors':result['errors'][:8]},ensure_ascii=False));raise SystemExit(result['status']!='PASS')
