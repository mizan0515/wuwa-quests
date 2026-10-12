"""Verify the fixed inventory, source strings, call proofs and rendered readers.

Call proofs are replayed from the recorded JSON locations, without invoking the
exporter's graph traversal. Local inputs are optional for portable build QA.
"""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from recover_quest_sources import Sources, sha
from verify_quest_recovery import dictionaries
from wuwa_handbook import FB, clean, connect
from typed_flow_references import independent_value as independent_typed_value


def location(pointer):
    if pointer.startswith('config:'):
        match=re.match(r'(config:[^/]+/[^/]+/\d+/FB\d+)(.*)',pointer)
        return match[1],match[2]
    root,_,tail=pointer.partition('/')
    return root,('/'+tail if tail else '')


def identity(root):
    kind,key=root.split(':',1)
    if kind in ('quest_node','level_node'):
        return kind.removesuffix('_node')+':'+key.split('_')[0]
    if kind in ('recall','quest-dungeon'):return 'quest:'+key
    return root


class Transcript(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.state=None;self.row=None;self.capture=None;self.rows={};self.links=set();self.branches={};self.branch=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='section' and 'data-dialogue-state' in a:self.state=a['data-dialogue-state'];self.rows[self.state]=[];self.branches[self.state]=[]
        if tag=='p' and 'quest-branch' in a.get('class','').split():self.branch=''
        if tag=='p' and 'data-dialogue-source-key' in a:
            self.row={'text_id':a['data-dialogue-source-key'],'text':'','speaker':''};self.rows[self.state].append(self.row)
        if self.row and tag in ('span','strong'):
            self.capture='text' if 'quest-speech' in a.get('class','').split() else 'speaker' if 'quest-speaker' in a.get('class','').split() else None
        if tag=='a':self.links.add(a.get('href',''))
    def handle_endtag(self,tag):
        if tag in ('span','strong'):self.capture=None
        if tag=='p':
            self.row=None
            if self.branch is not None:self.branches[self.state].append(self.branch);self.branch=None
        if tag=='section':self.state=None
    def handle_data(self,text):
        if self.row and self.capture:self.row[self.capture]+=text
        if self.branch is not None:self.branch+=text


def verify(repo,configdb=None,flowlists=None,dist=None):
    repo=Path(repo);raw=(repo/'settings/dialogue-attribution.json').read_bytes();data=json.loads(raw)
    previous=json.loads((repo/'settings/quest-supplements.json').read_text(encoding='utf8'))
    manifest=json.loads((repo/'settings/manifest.json').read_text(encoding='utf8'))
    assert manifest['files']['dialogue-attribution.json']==sha(raw),'Audit content hash'
    assert data['baseline_states']==previous['unassigned_states'],'Fixed baseline inventory'
    assert len(data['states'])==len(set(data['baseline_states']))==9331,'All 9331 distinct states'
    assert set(data['states'])==set(data['baseline_states']),'Audit state inventory'
    sources=Sources(configdb,flowlists) if configdb and flowlists else None
    extra={};cache={};checked=set();stats=Counter();unique=set()
    if sources:
        assert sources.flow_hashes==data['flowlist_hashes'],'FlowList source hashes'
        for name,digest in data['source_databases'].items():assert sha((Path(configdb)/name).read_bytes())==digest,'Source hash '+name
        for name,table,field in (('db_template.db','templateconfig',3),('db_GiantResponse.db','giantresponse',3),('db_LoopTeleportVolumeFunction.db','loopteleportvolumefunction',4),('db_RandomPlot.db','plotreference',1)):
            with connect(Path(configdb)/name) as db:
                for number,blob in db.execute(f'SELECT Id,BinData FROM "{table}"'):
                    fb=FB(blob);pos=fb.root();assert fb.scalar(pos,0)==number
                    text=fb.string(pos,field)
                    if text:extra[f'config:{name}/{table}/{number}/FB{field}']=text if name=='db_RandomPlot.db' else json.loads(text)

    def source_value(root):
        if root in cache:return cache[root]
        kind,key=root.split(':',1)
        if kind=='config':
            owner=data['owners'][root]
            value=independent_typed_value(configdb,owner) if owner.get('encoding')=='typed_fields' else extra[root]
        elif kind=='entity':
            ids=tuple(map(int,key.split(':')));fb=FB(sources.entities[ids]);pos=fb.root()
            assert (fb.scalar(pos,1),fb.scalar(pos,2))==ids,'Entity identity'
            value=json.loads(fb.string(pos,10))
        elif kind=='quest-dungeon':value={'Type':'EnterDungeon','DungeonId':sources.tables['quest'][key]['DungeonId']}
        else:value=sources.tables[kind][key]
        cache[root]=value;return value

    def replay(pointer,target):
        if (pointer,target) in checked:return
        root,path=location(pointer);kind,key=root.split(':',1)
        if kind=='dungeon':
            match=re.fullmatch(r'/MapConfigId/(\d+)/LevelPlay/(\d+)',path);assert match,'Dungeon proof syntax'
            map_id=int(match[1]);level=match[2]
            assert sources.dungeons.get(key)==map_id and sources.tables['level'][level]['LevelId']==map_id and sources.tables['level'][level]['Type']=='Dungeon' and target=='level:'+level,'Dedicated dungeon ownership'
        else:
            value=source_value(root)
            for token in path.split('/')[1:] if path else []:value=value[int(token)] if isinstance(value,list) else value[token]
            destinations=set()
            if isinstance(value,str):
                match=re.fullmatch(r'f_(\d+)_(\d+)',value)
                if match and int(match[1]) in sources.flow_ids:
                    destinations.update('flow:'+st for st in sources.states_by_flow.get(sources.flow_ids[int(match[1])]+'_'+match[2],[]))
                match=re.fullmatch(r'e_(\d+)_(\d+)',value)
                if match:destinations.add('entity:'+match[1]+':'+match[2])
                match=re.fullmatch(r'l_(\d+)_(\d+)',value)
                if match and sources.tables['level'].get(match[2],{}).get('LevelId')==int(match[1]):destinations.add('level:'+match[2])
                if kind=='config' and key.startswith('db_RandomPlot.db/'):
                    match=re.fullmatch(r'(.+),(\d+),(\d+)',value)
                    if match:destinations.add('flow:'+'_'.join(match.groups()))
            elif isinstance(value,dict):
                if value.get('FlowListName') and 'FlowId' in value:destinations.add(f"flow:{value['FlowListName']}_{value['FlowId']}_{value.get('StateId',1)}")
                if kind=='flow' and value.get('Name')=='ChangeState':destinations.add('flow:'+key.rsplit('_',1)[0]+'_'+str(value.get('Params',{}).get('StateId')))
                if value.get('Name')=='TeleportDungeon':destinations.add('dungeon:'+str(value.get('Params',{}).get('DungeonId')))
                if value.get('Type')=='EnterDungeon':destinations.add('dungeon:'+str(value.get('DungeonId')))
                if value.get('LevelPlayId') is not None:destinations.add('level:'+str(value['LevelPlayId']))
            assert target in destinations,'Unproved call '+pointer+' -> '+target
        checked.add((pointer,target))

    for key,state in data['states'].items():
        readable=any(r['status']=='OK' for r in state['rows']);assert readable==state['readable']
        owners=state['owners'];kinds={data['owners'][o]['kind'] for o in owners}
        expected='no_korean' if not readable else next((k for k in ('quest','level','entity','config') if k in kinds),'unreferenced')
        assert state['classification']==expected,'Ownership classification '+key
        stats[expected]+=1
        for owner,evidence in owners.items():
            chain=evidence['proof'];assert chain and identity(location(chain[0])[0])==owner,'Owner root proof'
            for i,pointer in enumerate(chain):
                target=identity(location(chain[i+1])[0]) if i+1<len(chain) else 'flow:'+key
                if sources:replay(pointer,target)
        for row in state['rows']:
            assert clean(row['raw'])==row['text'],'Raw reading preservation'
            if sources:
                assert (row['raw'],row['source'])==sources.locale.get(row['text_id'],('','')),'Locale source '+row['text_id']
                item_type='Screen'
                if row['kind']=='대사':
                    action=sources.tables['flow'][key]
                    for token in row['action_path'].split('/')[1:]:action=action[int(token)] if isinstance(action,list) else action[token]
                    item=next(item for item in action['Params']['TalkItems'] if item['Id']==row['talk_id'])
                    assert item.get('WhoId')==row['speaker_id'],'Speaker identity'
                    item_type=item.get('Type','Talk')
                assert row['speaker']==('플레이어 선택지' if row['kind']=='선택지' else sources.speaker(row['speaker_id'],item_type)),'Speaker preservation'
            if row['status']=='OK':stats['readable_rows']+=1;unique.add(row['text_id'])
        if sources:
            expected=[]
            for obj in dictionaries(sources.tables['flow'][key]):
                params=obj.get('Params',{})
                if obj.get('Name')=='ShowTalk':
                    for item in params.get('TalkItems',[]):
                        if item.get('TidTalk'):expected.append(item['TidTalk'])
                        expected.extend(o['TidTalkOption'] for o in item.get('Options',[]) if o.get('TidTalkOption'))
                elif obj.get('Name')=='ShowCenterText' and params.get('TidCenterText'):expected.append(params['TidCenterText'])
                elif obj.get('Name')=='PlayMovie':expected.extend(tid for _,_,tid in sources.captions.get(params.get('VideoName'),[]))
            assert Counter(expected)==Counter(r['text_id'] for r in state['rows']),'Whole source text reference inventory '+key
    groups=data['groups'];group_states=[key for group in groups for key in group['states']]
    assert len(group_states)==len(set(group_states)) and set(group_states)=={key for key,state in data['states'].items() if state['readable']},'All readable states in readers'
    for group in groups:
        assert group['id']==sha(group['source'].encode())[:16]
        assert all(key.rsplit('_',2)[0]==group['source'] for key in group['states'])
        assert group['regions']==[],'Unverified cross-table geographic mapping'
        if dist:
            page=Transcript();page.feed((Path(dist)/'dialogue-sources'/(group['id']+'.html')).read_text(encoding='utf8'))
            assert set(page.rows)==set(group['states']),'Rendered state inventory'
            for key in group['states']:
                expected=[{field:r[field] for field in ('text_id','text','speaker')} for r in data['states'][key]['rows'] if r['status']=='OK']
                assert page.rows[key]==expected,'Rendered original order/text/speaker '+key
                assert page.branches[key]==[r['transition'] for r in data['states'][key]['rows'] if r['status']=='OK' and r['transition']],'Rendered branch transitions '+key
            for scene in group.get('existing_scenes',[]):assert f"/wuwa-quests/quests/{scene['quest_id']}.html#scene-{scene['scene']}" in page.links,'Existing context link'
    stats.update(unique_readable_keys=len(unique),groups=len(groups),review_groups=sum(g['review'] for g in groups))
    assert dict(stats)==data['summary'],'Summary inventory'
    return dict(status='PASS',sourceDbChecked=bool(sources),renderedChecked=bool(dist),callEdgesReplayed=len(checked),stats=dict(stats))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--configdb',type=Path);parser.add_argument('--flowlists',type=Path);parser.add_argument('--dist',type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.repo,args.configdb,args.flowlists,args.dist),ensure_ascii=False))
