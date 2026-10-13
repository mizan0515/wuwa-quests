"""Publish common UI once. Original reading HTML and document data stay static.

Generated, same-origin classic frame scripts run in their parser position.
Behavior modules retain their original type/order; SVG shapes use one sprite.
The receipt reconstructs every input HTML byte exactly and verifies all assets.
"""
import argparse, hashlib, json, re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

SCRIPT=re.compile(r'<script([^>]*)>([\s\S]*?)</script>')
SVG=re.compile(r'(<svg\b[^>]*>)([\s\S]*?)(</svg>)')
VOID=set('area base br col embed hr img input link meta param source track wbr'.split())
PROTECTED=re.compile(r'original-body|original-row|original-paragraph|quest-source-line|data-reading-template="(?:row|reader)"|data-origin-model')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def total(root):return sum(p.stat().st_size for p in root.rglob('*')if p.is_file())
class Frames(HTMLParser):
 def __init__(self,text):
  super().__init__(convert_charrefs=False);self.text=text;self.lines=[0];self.stack=[];self.ranges=[]
  self.lines.extend(m.end()for m in re.finditer('\n',text))
 def at(self):line,col=self.getpos();return self.lines[line-1]+col
 def handle_starttag(self,tag,items):
  d=dict(items);cl=d.get('class','')or'';chosen=(tag=='header'and'header'in cl.split())or(tag=='footer'and('quest-footer'in cl.split()or'sl-flex'in cl.split()))or(tag in ('div','sl-sidebar-pane')and d.get('id')=='starlight__sidebar')
  if tag not in VOID:self.stack.append((tag,self.at(),chosen))
 def handle_startendtag(self,tag,items):pass
 def handle_endtag(self,tag):
  i=next((i for i in range(len(self.stack)-1,-1,-1)if self.stack[i][0]==tag),None)
  if i is None:return
  _,start,chosen=self.stack[i];del self.stack[i:]
  if chosen:
   end=self.text.index('>',self.at())+1;body=self.text[start:end]
   if not PROTECTED.search(body):self.ranges.append((start,end))
def frames(text):
 parser=Frames(text);parser.feed(text)
 ranges=[]
 for start,end in sorted(parser.ranges,key=lambda x:(x[0],-x[1])):
  if not ranges or start>=ranges[-1][1]:ranges.append((start,end))
 # Native guide landmarks stay balanced and usable without JavaScript.
 # Their layout and behavior are shared CSS/JS; only complete UI trees move.
 return sorted(ranges)
def optimize(root,base,receipt):
 target=root/'_shared-ui'
 if target.exists():verify(root,receipt);return
 files=sorted(root.rglob('*.html'));inputs={p.relative_to(root).as_posix():p.read_bytes()for p in files}
 originals={k:sha(v)for k,v in inputs.items()};before=total(root);assets={};replacements={};counts=Counter();target.mkdir()
 def asset(body,suffix,kind):
  raw=body.encode('utf8');name=sha(raw)[:20]+suffix
  (target/name).write_bytes(raw);assets[name]={'sha256':sha(raw),'bytes':len(raw),'kind':kind};return base+'/_shared-ui/'+name
 def remember(replacement,original):
  if replacement in replacements and replacements[replacement]!=original:raise ValueError('Conflicting UI replacement')
  replacements[replacement]=original;return replacement
 census=Counter((m[1],m[2])for raw in inputs.values()for m in SCRIPT.finditer(raw.decode())if 'src='not in m[1])
 changed={}
 for name,raw in inputs.items():
  text=raw.decode();modules=Counter((m[1],m[2])for m in SCRIPT.finditer(text)if 'type="module"'in m[1])
  def share_script(m):
   attrs,body=m.groups()
   if 'src='in attrs or 'application/'in attrs or len(body)<128 or census[(attrs,body)]<2:return m[0]
   if 'type="module"'in attrs and(modules[(attrs,body)]>1 or re.search(r'(?:from\s*|import\s*\(?)[\x27"`]\.',body)):return m[0]
   url=asset(body,'.js','behavior');counts['behaviorOccurrences']+=1
   return remember(f'<script{attrs} src="{url}" data-wj></script>',m[0])
  changed[name]=SCRIPT.sub(share_script,text)
 shape_counts=Counter(m[2]for text in changed.values()for m in SVG.finditer(text))
 shapes={body:sha(body.encode())[:16]for body,n in shape_counts.items()if n>=2 and len(body)>150 and not re.search(r'<(?:title|desc|script|style|text|use)\b|\bid=',body)}
 if shapes:
  sprite='<svg xmlns="http://www.w3.org/2000/svg">'+''.join(f'<g id="s{key}">{body}</g>'for body,key in sorted(shapes.items(),key=lambda x:x[1]))+'</svg>'
  sprite_url=asset(sprite,'.svg','icons')
  def icon(m):
   if m[2]not in shapes:return m[0]
   replacement=m[1]+f'<use href="{sprite_url}#s{shapes[m[2]]}"/>'+m[3];counts['iconOccurrences']+=1
   return remember(replacement,m[0])
  changed={k:SVG.sub(icon,v)for k,v in changed.items()}
 candidates=Counter(text[a:b]for text in changed.values()for a,b in frames(text))
 for name,text in changed.items():
  pieces=[];at=0
  for start,end in frames(text):
   body=text[start:end]
   if candidates[body]<2 or len(body.encode())<200:continue
   encoded=json.dumps(body,ensure_ascii=False).replace('<','\\u003c');url=asset('document.write('+encoded+');\n','.js','frame')
   replacement=f'<script src="{url}" data-wf></script>'
   if body.startswith('<header')or'id="starlight__sidebar"'in body:
    replacement+=f'<noscript><nav aria-label="자료집 탐색"><a href="{base}/index.html">퀘스트 목록</a> · <a href="{base}/library.html">원문 보관함</a></nav></noscript>'
   if body.startswith('<footer'):replacement+='<noscript><small>비공식 자료집 · 게임 콘텐츠 권리: Kuro Games 등 해당 권리자</small></noscript>'
   pieces.extend((text[at:start],remember(replacement,body)));at=end;counts['frameOccurrences']+=1
  pieces.append(text[at:]);(root/name).write_text(''.join(pieces),encoding='utf8',newline='')
 report={'schema':'wuwa-shared-publication-ui.v1','base':base,'beforeBytes':before,'afterBytes':total(root),'originals':originals,'assets':assets,'replacements':replacements,'counts':counts}
 receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')),encoding='utf8');verify(root,receipt)
 print(json.dumps({k:report[k]for k in ('beforeBytes','afterBytes','counts')},ensure_ascii=False))
def expand(text,report):
 replacements=report['replacements'];pattern=re.compile('|'.join(re.escape(k)for k in sorted(replacements,key=len,reverse=True)))
 for _ in range(12):
  changed=pattern.sub(lambda m:replacements[m[0]],text)
  if changed==text:return text
  text=changed
 raise ValueError('Shared UI inverse nesting exceeded')
def verify(root,receipt):
 report=json.loads(receipt.read_text('utf8'))
 for name,record in report['assets'].items():
  raw=(root/'_shared-ui'/name).read_bytes()
  if sha(raw)!=record['sha256']:raise ValueError('Shared asset differs '+name)
 for name,expected in report['originals'].items():
  raw=(root/name).read_text('utf8');restored=expand(raw,report)
  if sha(restored.encode())!=expected:raise ValueError('Exact original HTML inverse differs '+name)
 if total(root)!=report['afterBytes']:raise ValueError('Publication size differs')
 print(json.dumps({'status':'PASS','exactHtmlFiles':len(report['originals']),'sharedAssets':len(report['assets']),'staticOriginalHtml':True,'bytes':report['afterBytes']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('dist'));p.add_argument('--base',default='/wuwa-quests');p.add_argument('--receipt',type=Path,default=Path('.codex-work/shared-publication-ui.json'));p.add_argument('--verify',action='store_true');a=p.parse_args()
 (verify(a.root,a.receipt)if a.verify else optimize(a.root,a.base,a.receipt))
