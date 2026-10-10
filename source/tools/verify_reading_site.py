import json,hashlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote

class Page(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.links=[];self.duplicates=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if a.get('id'):
   if a['id'] in self.ids:self.duplicates.append(a['id'])
   self.ids.add(a['id'])
  for key in ['href','src']:
   if a.get(key):self.links.append(a[key])

r=Path(__file__).resolve().parents[2];root=r/'source/dist';pages={};errors=[];count=0;routes=0
index=json.loads((r/'settings/index.json').read_text(encoding='utf-8'))
source_ids={e['id'] for e in index['entries']+index.get('diagnostic_entries',[])}|set(index.get('aliases',{}))
for p in root.rglob('*.html'):
 parser=Page();parser.feed(p.read_text(encoding='utf-8'));pages[p.resolve()]=parser
 if parser.duplicates:errors.append([str(p.relative_to(root)),'duplicate ids',parser.duplicates])
for p,parser in pages.items():
 for link in parser.links:
  u=urlsplit(link)
  if u.scheme or u.netloc:continue
  urlpath=unquote(u.path)
  if urlpath.startswith('/wuwa-quests'):target=root/urlpath[len('/wuwa-quests'):].lstrip('/')
  elif urlpath.startswith('/'):errors.append([str(p),link,'wrong base']);continue
  else:target=p.parent/urlpath if urlpath else p
  target=target.resolve()
  if target.is_dir():target=target/'index.html'
  if not target.is_relative_to(root) or not target.exists():errors.append([str(p.relative_to(root)),link,'missing target']);continue
  fragment=unquote(u.fragment)
  if target==root/'library.html' and fragment.startswith('/'):
   route=fragment.split('?')[0].split('/')
   if route[1]=='library':routes+=1
   elif route[1]=='source' and len(route)>2 and route[2] in source_ids:routes+=1
   else:errors.append([str(p.relative_to(root)),link,'unknown library route'])
  elif u.fragment and target in pages and fragment not in pages[target].ids:errors.append([str(p.relative_to(root)),link,'missing anchor'])
  count+=1
records={}
for file in (r/'settings').glob('records-*.json'):records.update(json.loads(file.read_text(encoding='utf-8')));atlas=json.loads((r/'settings/atlas.json').read_text(encoding='utf-8'));references={}
def walk(x):
 if isinstance(x,list):
  for item in x:walk(item)
 elif isinstance(x,dict):
  if x.get('source_text_sha256') and x.get('field'):references[(x['id'],x['field'])]=x
  for v in x.values():walk(v)
walk(atlas)
for (id,field),ref in references.items():
 value=next((v for v in records.get(id,{}).get('values',[]) if v['field']==field),None)
 if not value or hashlib.sha256(value['raw'].encode()).hexdigest()!=ref['source_text_sha256']:errors.append([id,field,'source record hash differs'])
report={'status':'PASS' if not errors else 'FAIL','htmlPages':len(pages),'internalLinksAndAnchors':count,'verifiedLibraryRoutes':routes,'verifiedSettingReferences':len(references),'errors':errors}
manifest=json.loads((r/'content-manifest.json').read_text(encoding='utf-8'))
for quest in manifest:
 if hashlib.sha256((r/'originals'/(quest['id']+'.txt')).read_bytes()).hexdigest()!=quest['source_sha256']:errors.append([quest['id'],'quest original hash differs'])
report.update(status='PASS' if not errors else 'FAIL',questsPreserved=len(manifest),errors=errors)
print(json.dumps({**report,'errors':errors[:12]},ensure_ascii=False));raise SystemExit(bool(errors))
