"""Audit the fixed unassigned state inventory using exact client call edges."""
import argparse
from collections import Counter, defaultdict, deque
import json
from pathlib import Path
import re
from recover_quest_sources import Sources, sha
from wuwa_handbook import FB, clean, connect
from typed_flow_references import load as load_typed_references


def node_name(node):
    kind, key = node
    return kind + ':' + (':'.join(map(str, key)) if isinstance(key, tuple) else key)


def audit(sources, previous, client_scripts=None):
    reverse, metadata = defaultdict(list), {}
    published = set(previous['quests'])
    def insert(source, value, location, relative=None):
        for target, pointer in sources.object_edges(value, location, relative):
            reverse[node_name(target)].append((source, pointer))

    for kind in ('quest', 'level'):
        for key, value in sources.tables[kind].items():
            source = kind + ':' + key
            title_key = value.get('TidName', '')
            metadata[source] = dict(kind=kind, id=key, type=value.get('Type'),
                title_key=title_key, title=clean(sources.locale.get(title_key, ('',''))[0]),
                config_label=value.get('Key', ''), map_id=value.get('LevelId'),
                region_id=value.get('RegionId'), published=kind=='quest' and key in published)
            insert(source, value, source)
            for node_key, node in sources.node_groups[kind].get(key, []):
                insert(source, node, kind + '_node:' + node_key)
            if kind == 'quest':
                insert(source, sources.tables['recall'].get(key, []), 'recall:' + key)
                if str(value.get('DungeonId')) in sources.dungeons:
                    insert(source, {'Type':'EnterDungeon','DungeonId':value['DungeonId']}, 'quest-dungeon:'+key)
    for key, value in sources.tables['flow'].items():
        insert('flow:'+key, value, 'flow:'+key, key.rsplit('_',1)[0])
    for (map_id, entity_id), blob in sources.entities.items():
        fb=FB(blob); pos=fb.root()
        if (fb.scalar(pos,1), fb.scalar(pos,2)) != (map_id,entity_id):
            raise ValueError('Entity map/id identity changed')
        value=json.loads(fb.string(pos,10))
        source=f'entity:{map_id}:{entity_id}'
        insert(source,value,source)
        title_key=value.get('BaseInfoComponent',{}).get('TidName','')
        metadata[source]=dict(kind='entity',map_id=map_id,entity_id=entity_id,
            title_key=title_key,title=clean(sources.locale.get(title_key,('',''))[0]))
    for key,map_id in sources.dungeons.items():
        for level in sources.levels_by_map[map_id]:
            reverse['level:'+level].append(('dungeon:'+key,f'dungeon:{key}/MapConfigId/{map_id}/LevelPlay/{level}'))
    extra_hashes={}
    for file,table,field,encoding in (
            ('db_template.db','templateconfig',3,'json'),
            ('db_GiantResponse.db','giantresponse',3,'json'),
            ('db_LoopTeleportVolumeFunction.db','loopteleportvolumefunction',4,'json'),
            ('db_RandomPlot.db','plotreference',1,'triple')):
        extra_hashes[file]=sha((sources.root/file).read_bytes())
        with connect(sources.root/file) as db:
            for number,blob in db.execute(f'SELECT Id,BinData FROM "{table}"'):
                fb=FB(blob);pos=fb.root()
                if fb.scalar(pos,0)!=number:raise ValueError('Configuration SQL identity changed')
                text=fb.string(pos,field)
                if not text:continue
                key=f'config:{file}/{table}/{number}/FB{field}'
                if encoding=='json':
                    value=json.loads(text);insert(key,value,key)
                else:
                    match=re.fullmatch(r'(.+),(\d+),(\d+)',text)
                    if not match:raise ValueError('Unsupported plot reference serialization')
                    state='_'.join(match.groups())
                    reverse['flow:'+state].append((key,key));value={}
                title_key=value.get('BaseInfoComponent',{}).get('TidName','') if isinstance(value,dict) else ''
                metadata[key]=dict(kind='config',database=file,table=table,id=number,field=field,
                    title_key=title_key,title=clean(sources.locale.get(title_key,('',''))[0]),encoding=encoding)
    typed,typed_hashes=load_typed_references(sources.root,client_scripts)
    extra_hashes.update(typed_hashes)
    for key,record in typed.items():
        if key in metadata:raise ValueError('Typed configuration owner collision')
        insert(key,record['value'],key)
        metadata[key]=record['metadata']
    states={};counts=Counter();used=set()
    for key in previous['unassigned_states']:
        first='flow:'+key;parents={first:None};queue=deque([first]);owners={}
        while queue:
            current=queue.popleft()
            for caller,pointer in reverse.get(current,[]):
                if caller in parents:continue
                parents[caller]=(current,pointer);queue.append(caller)
                if caller in metadata:owners[caller]=None
        for owner in owners:
            current=owner;chain=[]
            while parents[current] is not None:
                current,pointer=parents[current];chain.append(pointer)
            owners[owner]={'proof':chain}
        used.update(owners)
        readable=any(r['status']=='OK' for r in sources.rows(key))
        kind='no_korean' if not readable else 'quest' if any(o.startswith('quest:') for o in owners) else 'level' if any(o.startswith('level:') for o in owners) else 'entity' if any(o.startswith('entity:') for o in owners) else 'config' if owners else 'unreferenced'
        counts[kind]+=1
        states[key]=dict(classification=kind,readable=readable,owners=owners,rows=sources.rows(key))
    areas={}
    area_file=sources.root/'db_area.db'
    with connect(area_file) as db:
        for area_id,blob in db.execute('SELECT AreaId,BinData FROM area'):
            fb=FB(blob);pos=fb.root()
            if fb.scalar(pos,0)!=area_id:raise ValueError('Area SQL identity changed')
            tid=fb.string(pos,7)
            areas[str(area_id)]={'title_key':tid,'title':clean(sources.locale.get(tid,('',''))[0])}
    result=dict(schema='wuwa-dialogue-attribution.v1',snapshot=previous['observed_snapshot'],
        baseline_states=previous['unassigned_states'],summary=dict(counts),states=states,
        owners={key:metadata[key] for key in sorted(used)},areas=areas,
        source_databases={**sources.hashes,**extra_hashes,'db_area.db':sha(area_file.read_bytes())},
        flowlist_hashes=sources.flow_hashes)
    if not sources.unchanged() or any(sha((sources.root/file).read_bytes())!=digest for file,digest in extra_hashes.items()):raise ValueError('Inputs changed during audit')
    return result


def reading_groups(data, repo=None):
    groups=defaultdict(list)
    for key,state in data['states'].items():
        if state['readable']:groups[key.rsplit('_',2)[0]].append((key,state))
    output=[]
    for source,states in sorted(groups.items()):
        states.sort(key=lambda item:tuple(map(int,item[0].rsplit('_',2)[1:])))
        owner_keys=sorted({key for _,state in states for key in state['owners']})
        titles=[]
        for key in owner_keys:
            owner=data['owners'][key]
            if owner['kind']=='quest' and owner['title'] and owner['type']!=100 and owner['title'] not in titles:titles.append(owner['title'])
        speakers=list(dict.fromkeys(row['speaker'] for _,state in states for row in state['rows'] if row['status']=='OK' and row['kind']=='대사' and row['speaker'] not in ('화자 미지정','화면 문구') and not row['speaker'].startswith('화자ID ')))
        rows=[row for _,state in states for row in state['rows'] if row['status']=='OK']
        config_titles=list(dict.fromkeys(data['owners'][key]['title'] for key in owner_keys if data['owners'][key]['kind']=='config' and data['owners'][key]['title']))
        title=' · '.join(titles[:2]) if titles else ' · '.join(config_titles[:2]) if config_titles else ' · '.join(speakers[:2]) if speakers else '화면 문구와 기록'
        kinds=sorted({state['classification'] for _,state in states})
        # Quest RegionId and area AreaId are different identities. No direct
        # mapping is established by equal numeric values.
        regions=[]
        review='测试' in source or any('测试' in data['owners'][key].get('config_label','') for key in owner_keys)
        output.append(dict(id=sha(source.encode('utf8'))[:16],source=source,title=title,
            excerpt=rows[0]['text'][:180],kinds=kinds,regions=regions,speakers=speakers,
            review=review,states=[key for key,_ in states],rows=len(rows)))
    data['groups']=output
    if repo:
        by_source={group['source']:group for group in output}
        for quest in json.loads((repo/'content-manifest.json').read_text(encoding='utf8')):
            raw=(repo/'originals'/f"{quest['id']}.txt").read_text(encoding='utf-8-sig')
            blocks=list(re.finditer(r'^장면 (\d+):',raw,re.M))
            for index,block in enumerate(blocks):
                body=raw[block.start():blocks[index+1].start() if index+1<len(blocks) else len(raw)]
                for state in re.findall(r'^대화 ID: (.+)$',body,re.M):
                    group=by_source.get(state.strip().rsplit('_',2)[0])
                    if group is not None:
                        group.setdefault('existing_scenes',[]).append(dict(quest_id=quest['id'],title=quest['title'],scene=int(block[1]),state_key=state.strip()))
    data['summary'].update(readable_rows=sum(g['rows'] for g in output),
        unique_readable_keys=len({r['text_id'] for st in data['states'].values() for r in st['rows'] if r['status']=='OK'}),
        groups=len(output),review_groups=sum(g['review'] for g in output))
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configdb',required=True,type=Path)
    parser.add_argument('--flowlists',required=True,type=Path)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--client-scripts-root',type=Path)
    args=parser.parse_args()
    previous=json.loads((args.repo/'settings/quest-supplements.json').read_text(encoding='utf8'))
    sources=Sources(args.configdb,args.flowlists)
    if sources.hashes!=previous['source_databases']:raise ValueError('Fixed snapshot differs from prior audit')
    data=reading_groups(audit(sources,previous,args.client_scripts_root),args.repo)
    target=args.repo/'settings/dialogue-attribution.json'
    raw=(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf8')
    target.write_bytes(raw)
    manifest_path=args.repo/'settings/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    manifest['files'][target.name]=sha(raw)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(data['summary'],ensure_ascii=False))
