"""Independent stdlib verification of source-owned readers and same-source links.

Default checks derived model, exact original TXT scene anchors, owner source pages
and original Korean rows. --dist adds every published inverse, source/co-owner
link, local LNB and exact rendered owner row/branch/proof comparison.
"""
import argparse,collections,hashlib,json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urlsplit

def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def anchor(key):return 'state-'+sha(key.encode())[:16]

class Transcript(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.ids=[];self.links=[];self.rows=[];self.branches=[];self.proofs=[];self.in_row=None;self.capture=None;self.depth=0;self.states=[];self.context=False;self.owners=[]
 def handle_starttag(self,tag,pairs):
  a=dict(pairs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='a' and 'href' in a:self.links.append(a['href'])
  if 'data-reading-context' in a:self.context=True
  if 'data-dialogue-state' in a:self.states.append(a['data-dialogue-state'])
  if 'data-quest-source-owner' in a:self.owners.append(a['data-quest-source-owner'])
  if tag=='p' and 'quest-source-line' in a.get('class',''):
   self.in_row={'attrs':a,'speaker':'','text':''};self.rows.append(self.in_row)
  if self.capture:self.depth+=1
  elif self.in_row and tag=='strong':self.capture=('speaker',self.in_row);self.depth=1
  elif self.in_row and tag=='span' and 'quest-speech' in a.get('class',''):self.capture=('text',self.in_row);self.depth=1
  elif tag=='p' and 'quest-branch' in a.get('class',''):self.capture=('branch',[]);self.depth=1
  elif tag=='pre':self.capture=('proof',[]);self.depth=1
 def handle_endtag(self,tag):
  if self.capture:
   self.depth-=1
   if not self.depth:
    kind,obj=self.capture
    if kind=='branch':self.branches.append(''.join(obj))
    elif kind=='proof':
     try:value=json.loads(''.join(obj))
     except (ValueError,TypeError):value=None
     if isinstance(value,dict) and 'owner' in value and 'state' in value:self.proofs.append(value)
    self.capture=None
  if tag=='p':self.in_row=None
 def handle_data(self,text):
  if not self.capture:return
  kind,obj=self.capture
  if kind in ('text','speaker'):obj[kind]+=text
  else:obj.append(text)

def parse(path):
 p=Transcript();p.feed(Path(path).read_text(encoding='utf8'));return p
def has_link(page,url):
 for link in page.links:
  actual=urlsplit(link);expected=urlsplit(url)
  if unquote(actual.path).endswith('/'+expected.path) and unquote(actual.fragment)==expected.fragment:return True
 return False

def source_check(repo):
 repo=Path(repo);source=repo/'source';attribution=load(repo/'settings/dialogue-attribution.json');catalog=load(repo/'content-manifest.json');model=load(source/'src/data/quest-reading-navigation.json')
 need(model['schema']=='wuwa-quest-reading-navigation.v1','navigation model schema')
 published={str(q['id']):q for q in catalog};groups={g['id']:g for g in attribution['groups']};states=attribution['states'];owners=attribution['owners']
 eligible={key:o for key,o in owners.items() if o['kind']=='quest' and o.get('title','').strip() and o['type']!=100 and str(o['id']) not in published}
 need(len(published)==766 and len(groups)==687 and len(eligible)==14,'fixed current navigation corpus')
 need(set(model['quests'])==set(published) and set(model['groups'])==set(groups) and set(model['owners'])==set(eligible),'derived source/root inventories')
 expected_pairs=collections.Counter();scene_edges=0;scene_count=0
 for gid,g in groups.items():
  mg=model['groups'][gid];need(mg['states'] and [n['key'] for n in mg['states']]==g['states'],'source state inventory/order')
  all_keys={o for key in g['states'] for o in states[key]['owners']};search=[owners[k] for k in all_keys if owners[k]['kind']=='quest' and owners[k].get('title','').strip() and owners[k]['type']!=100]
  need(set(mg['ownerTitles'])=={o['title'] for o in search} and set(mg['ownerIds'])=={str(o['id']) for o in search},'all exact owner names searchable')
  need(set(mg['owners'])==all_keys&set(eligible),'all named owner readers')
  for node in mg['states']:
   need(node['anchor']==anchor(node['key']) and node['rowIndices']==[i for i,r in enumerate(states[node['key']]['rows']) if r['status']=='OK'],'source row anchor/index domain')
  related=collections.Counter((q['id'],s['number']) for q in mg['relatedQuests'] for s in q['scenes'])
  need(related==collections.Counter((str(s['quest_id']),s['scene']) for s in g.get('existing_scenes',[])),'all original group->quest scene edges')
  for edge in g.get('existing_scenes',[]):expected_pairs[(str(edge['quest_id']),gid)]+=1;scene_edges+=1
 actual_pairs={}
 for qid,q in model['quests'].items():
  original=published[qid];raw=(repo/'originals'/(qid+'.txt')).read_bytes();need(sha(raw)==original['source_sha256'],'original TXT SHA '+qid)
  titles=re.findall(r'^장면 \d+:[^\n]+',raw.decode('utf-8-sig').replace('\r\n','\n'),re.M)
  scenes=[int(re.match(r'장면 (\d+):',title)[1]) for title in titles];scene_count+=len(scenes)
  need([s['number'] for s in q['scenes']]==scenes and q['title']==original['title'],'original quest TOC/title')
  need([s['title'] for s in q['scenes']]==titles,'actual original scene labels')
  for g in q['relatedSources']:
   need(g['relation']=='SAME_SOURCE_CONTEXT','same source promoted to ownership')
   need(g['url']=='dialogue-sources/'+g['id']+'.html' and g['title']==groups[g['id']]['title'],'same source route/title')
   pair=(qid,g['id']);need(pair not in actual_pairs,'duplicate inverse pair');actual_pairs[pair]=len(g['scenes'])
 need(actual_pairs==dict(expected_pairs) and len(actual_pairs)==781 and scene_edges==8146,'all same source inverse coverage')
 row_count=0;state_count=0;branch_count=0
 for key,o in eligible.items():
  mo=model['owners'][key];need(mo['id']==str(o['id']) and mo['title']==o['title'] and mo['url']=='quest-sources/'+str(o['id'])+'.html','exact named owner metadata')
  expected=[(g['id'],sk) for g in attribution['groups'] for sk in g['states'] if key in states[sk]['owners']]
  need([(n['groupId'],n['key']) for n in mo['states']]==expected,'owner state exact coverage/order')
  p=parse(source/'src/content/docs'/('quest-sources/'+mo['id']+'.md'));rows=[];branches=[]
  need(p.states==[n['key'] for n in mo['states']] and set(p.owners)=={key},'reader selects only exact owner states')
  for node in mo['states']:
   state=states[node['key']];need(node['proof']==state['owners'][key]['proof'] and node['proof'],'owner source chain')
   need(has_link(p,'dialogue-sources/'+node['groupId']+'.html#'+anchor(node['key'])),'owner/source original reciprocal link')
   for i,r in enumerate(state['rows']):
    if r['status']!='OK':continue
    rows.append((anchor(node['key'])+'-row-'+str(i),r['text_id'],r['speaker'],r['text'],'choice' if r['kind']=='선택지' else 'dialogue'))
    if r.get('transition'):branches.append(r['transition'])
   proof=next((v for v in p.proofs if v['state']==node['key']),None)
   need(proof and proof['owner']==key and proof['chain']==node['proof'] and proof['rows']==state['rows'],'whole source/proof projection')
   expected_owners=[{'owner':k,'kind':owners[k]['kind'],'title':owners[k].get('title') or None,'chain':e['proof']} for k,e in state['owners'].items()]
   need(proof['allOwners']==expected_owners,'all multiple direct owner metadata/chains preserved')
   state_count+=1
  actual=[(r['attrs']['id'],r['attrs']['data-dialogue-source-key'],r['speaker'],r['text'],r['attrs']['data-reading-kind']) for r in p.rows]
  need(actual==rows and p.branches==branches,'exact source-owned Korean rows/speakers/choices/branches')
  need(len(p.ids)==len(set(p.ids)),'owner reader duplicate anchors');row_count+=len(rows);branch_count+=len(branches)
 distinct_states={n['key'] for o in model['owners'].values() for n in o['states']};distinct_rows={(k,i) for k in distinct_states for i,r in enumerate(states[k]['rows']) if r['status']=='OK'}
 counts={'quests':766,'sourceGroups':687,'namedOwnerReaders':14,'sameSourcePairs':781,'sameSourceSceneReferences':8146,'originalQuestScenes':scene_count,'ownerStateReferences':state_count,'distinctOwnerStates':len(distinct_states),'ownerRows':row_count,'distinctOwnerSourceRows':len(distinct_rows),'ownerBranches':branch_count}
 need(model['counts']=={'quests':766,'groups':687,'owners':14,'sameSourcePairs':781,'sameSourceSceneReferences':8146},'model counts')
 return model,attribution,counts

def dist_check(dist,model,attribution):
 dist=Path(dist);checked=0
 cards=load(dist/'dialogue-sources/catalog.json');need(len(cards)==len(model['groups']),'all source search cards')
 for card in cards:
  g=model['groups'][card['id']]
  expected=[{'id':model['owners'][k]['id'],'title':model['owners'][k]['title'],'page':'/wuwa-quests/'+model['owners'][k]['url']} for k in g['owners']]
  need(card.get('ownerReaders')==expected,'all exact owner reader names/routes available on search cards')
 for q in model['quests'].values():
  p=parse(dist/q['url']);need(p.context,'quest local LNB missing')
  for s in q['scenes']:need('scene-'+str(s['number']) in p.ids,'original scene anchor missing')
  for g in q['relatedSources']:need(has_link(p,g['url']),'quest same-source inverse absent');checked+=1
 for g in model['groups'].values():
  p=parse(dist/g['url']);need(p.context,'source reader context missing')
  for key in g['owners']:need(has_link(p,model['owners'][key]['url']),'source owner-reader link absent')
  for node in g['states']:need(node['anchor'] in p.ids,'original state anchor absent')
 for o in model['owners'].values():
  p=parse(dist/o['url']);need(p.context,'owner reader context missing');expected=[];branches=[]
  for node in o['states']:
   state=attribution['states'][node['key']]
   for i,r in enumerate(state['rows']):
    if r['status']=='OK':expected.append((anchor(node['key'])+'-row-'+str(i),r['text_id'],r['speaker'],r['text'],'choice' if r['kind']=='선택지' else 'dialogue'))
    if r['status']=='OK' and r.get('transition'):branches.append(r['transition'])
   need(has_link(p,'dialogue-sources/'+node['groupId']+'.html#'+node['anchor']),'rendered owner original link')
  actual=[(r['attrs']['id'],r['attrs']['data-dialogue-source-key'],r['speaker'],r['text'],r['attrs']['data-reading-kind']) for r in p.rows]
  need(actual==expected and p.branches==branches,'rendered owner original text/choice/branch')
  need(len(p.ids)==len(set(p.ids)),'rendered duplicate owner anchors')
 need(checked==781,'rendered inverse census');return {'questPages':766,'sourcePages':687,'ownerPages':14,'sameSourceInverseLinks':checked}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--dist',type=Path);ap.add_argument('--report',type=Path);args=ap.parse_args();model,attribution,counts=source_check(args.repo)
 report={'status':'PASS_SOURCE_DERIVED_READER_AND_NAVIGATION','counts':counts,'roleBoundary':'EXACT_QUEST_OWNER_AND_SAME_SOURCE_CONTEXT_SEPARATE','runtimeVerified':False,'edition':'UNVERIFIED','dist':'NOT_REQUESTED'}
 if args.dist:report['dist']=dist_check(args.dist,model,attribution)
 if args.report:args.report.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
