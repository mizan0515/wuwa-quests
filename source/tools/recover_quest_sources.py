"""Append explicitly connected client originals while preserving published scenes.

SQLite/FlatBuffers inputs are read-only. No filename/title similarity or q_
dependency is used to attribute dialogue. A closure follows quest references,
entities, LevelPlay nodes, private dungeon maps and nested Flow invocations.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import re

from wuwa_handbook import FB, clean, connect, load_locale

DATABASES = {
    'quest': ('db_QuestData.db', 'questdata', 'QuestId', 1),
    'quest_node': ('db_QuestNodeData.db', 'questnodedata', 'Key', 1),
    'recall': ('db_PlotHandBook.db', 'plothandbookconfig', 'QuestId', 1),
    'flow': ('db_flowState.db', 'flowstate', 'StateKey', 6),
    'level': ('db_LevelPlayData.db', 'levelplaydata', 'LevelPlayId', 1),
    'level_node': ('db_LevelPlayNodeData.db', 'levelplaynodedata', 'Key', 1),
}
EXTRA_DATABASES = ['db_level_entity.db', 'db_instance_dungeon.db',
                   'db_cgVedio.db', 'db_speaker.db', 'ko/lang_speaker.db',
                   'ko/lang_multi_text.db', 'ko/lang_multi_text_1sthalf.db']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def walk(value, path=''):
    if isinstance(value, dict):
        yield value, path
        for key, child in value.items():
            yield from walk(child, path + '/' + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + '/' + str(index))


def edge(item):
    out = []
    for action in item.get('Actions', []):
        params = action.get('Params', {})
        if action.get('Name') == 'JumpTalk':
            out.append('대화ID ' + str(params.get('TalkId')) + '로 이동')
        elif action.get('Name') == 'FinishTalk':
            out.append('대화 종료')
    return '; '.join(out)


def ordered_items(params):
    items = params.get('TalkItems', [])
    by_id = {item['Id']: item for item in items}
    if len(by_id) != len(items):
        raise ValueError('Duplicate TalkItem ID')
    result, visited = [], set()
    for segment, sequence in enumerate(params.get('TalkSequence', [])):
        for item_id in sequence:
            if item_id in by_id and item_id not in visited:
                result.append((segment, by_id[item_id]))
                visited.add(item_id)
    for item in items:
        if item['Id'] not in visited:
            result.append(('자료순서', item))
    return result


def dedicated_dungeon_maps(levels):
    """A mixed world/quest inventory does not establish dungeon ownership."""
    types = defaultdict(set)
    for value in levels.values():
        types[value.get('LevelId')].add(value.get('Type'))
    return {map_id for map_id, kinds in types.items() if kinds == {'Dungeon'}}


class Sources:
    def __init__(self, root, flowlists):
        self.root = Path(root)
        self.hashes = {name: sha((self.root / name).read_bytes()) for name in
                       sorted({v[0] for v in DATABASES.values()} | set(EXTRA_DATABASES))}
        self.tables = {}
        for kind, (file, table, column, field) in DATABASES.items():
            data = {}
            with connect(self.root / file) as db:
                for key, blob in db.execute(f'SELECT "{column}",BinData FROM "{table}"'):
                    fb = FB(blob)
                    serialized = fb.scalar(fb.root(), 0) if column in ('QuestId', 'LevelPlayId') else fb.string(fb.root(), 0)
                    if str(serialized) != str(key):
                        raise ValueError('SQL/FlatBuffers key mismatch: ' + kind + ':' + str(key))
                    data[str(key)] = json.loads(fb.string(fb.root(), field))
            self.tables[kind] = data
        self.node_groups = {kind: defaultdict(list) for kind in ('quest', 'level')}
        for kind in self.node_groups:
            for key, value in self.tables[kind + '_node'].items():
                self.node_groups[kind][key.split('_')[0]].append((key, value))
        self.locale = load_locale(self.root)
        with connect(self.root / 'ko/lang_speaker.db') as db:
            self.speaker_text = dict(db.execute('SELECT Id,Content FROM Speaker'))
        with connect(self.root / 'db_speaker.db') as db:
            self.speaker_key = dict(db.execute('SELECT Id,NameStringKey FROM speaker'))
        self.flow_ids, self.flow_hashes = {}, {}
        for path in sorted(Path(flowlists).glob('*.bytes')):
            data = path.read_bytes()
            fb = FB(data)
            number = fb.scalar(fb.root(), 0)
            if number in self.flow_ids:
                raise ValueError('Duplicate numeric FlowList ID')
            self.flow_ids[number] = path.stem
            self.flow_hashes[path.name] = sha(data)
        self.states_by_flow = defaultdict(list)
        for key in self.tables['flow']:
            self.states_by_flow[key.rsplit('_', 1)[0]].append(key)
        for values in self.states_by_flow.values():
            values.sort(key=lambda key: int(key.rsplit('_', 1)[1]))
        self.entities = {}
        with connect(self.root / 'db_level_entity.db') as db:
            for map_id, entity_id, blob in db.execute('SELECT MapId,EntityId,BinData FROM levelentityconfig'):
                key = (map_id, entity_id)
                if key in self.entities:
                    raise ValueError('Duplicate map/entity identity')
                self.entities[key] = blob
        self.entity_cache = {}
        self.dungeons = {}
        shared_maps = set()
        with connect(self.root / 'db_instance_dungeon.db') as db:
            for number, map_id, blob in db.execute('SELECT Id,MapConfigId,BinData FROM instancedungeon'):
                fb = FB(blob)
                if fb.scalar(fb.root(), 0) != number or fb.scalar(fb.root(), 1) != map_id:
                    raise ValueError('Dungeon SQL/FlatBuffers mismatch')
                # Observed types: 1 is shared overworld, 2 is a private instance.
                # Visiting an overworld must never attach its entire world tree.
                if fb.scalar(fb.root(), 3) == 2:
                    self.dungeons[str(number)] = map_id
                elif fb.scalar(fb.root(), 3) == 1:
                    shared_maps.add(map_id)
        # Private variants can reuse the entire shared-world map (for example
        # map 8). Its LevelPlay inventory still belongs to the whole world.
        dedicated = dedicated_dungeon_maps(self.tables['level'])
        self.dungeons = {key: map_id for key, map_id in self.dungeons.items()
                         if map_id not in shared_maps and map_id in dedicated}
        self.levels_by_map = defaultdict(list)
        for key, value in self.tables['level'].items():
            if value.get('Type') == 'Dungeon':
                self.levels_by_map[value.get('LevelId')].append(key)
        self.captions = defaultdict(list)
        with connect(self.root / 'db_cgVedio.db') as db:
            for number, video, blob in db.execute('SELECT CaptionId,CgName,BinData FROM videocaption'):
                fb = FB(blob)
                if fb.scalar(fb.root(), 0) != number or fb.string(fb.root(), 1) != video:
                    raise ValueError('Caption SQL/FlatBuffers mismatch')
                self.captions[video].append((fb.scalar(fb.root(), 2), number, fb.string(fb.root(), 4)))
        for caps in self.captions.values():
            caps.sort()
        self.row_cache = {}

    def speaker(self, number, kind):
        if number is None:
            return '화면 문구' if kind in ('CenterText', 'Screen', 'AvgCenterText') else '화자 미지정'
        return clean(self.locale.get(f'Speaker_{number}_Name', ('', ''))[0] or
                     self.speaker_text.get(number) or
                     self.speaker_text.get(self.speaker_key.get(number)) or f'화자ID {number}')

    def rows(self, key):
        if key in self.row_cache:
            return self.row_cache[key]
        result = []

        def add(tid, kind, speaker_id, item_type, action_path, segment='', talk_id='', option='', transition='', moment=''):
            if not tid:
                return
            raw, source = self.locale.get(tid, ('', ''))
            result.append(dict(text_id=tid, kind=kind, raw=raw, text=clean(raw),
                               source=source, status='OK' if raw.strip() else 'EMPTY' if tid in self.locale else 'MISSING_KEY',
                               speaker='플레이어 선택지' if kind == '선택지' else self.speaker(speaker_id, item_type),
                               speaker_id=speaker_id, action_path=action_path, segment=segment,
                               talk_id=talk_id, option=option, transition=transition, caption_moment=moment))

        for action, path in walk(self.tables['flow'][key]):
            params = action.get('Params', {})
            if action.get('Name') == 'ShowTalk':
                for segment, item in ordered_items(params):
                    add(item.get('TidTalk'), '대사', item.get('WhoId'), item.get('Type', 'Talk'), path, segment, item['Id'], transition=edge(item))
                    for number, option in enumerate(item.get('Options', []), 1):
                        transition = edge(option)
                        for tr in params.get('SequenceTransitions', {}).get(str(segment), []):
                            if tr.get('OptionTextKey') in (option.get('PlotLineKey'), option.get('TidTalkOption')) and tr.get('OptionTextKey'):
                                transition += '; 구간 ' + str(tr.get('NextSequenceIndex')) + '로 이동'
                        add(option.get('TidTalkOption'), '선택지', None, 'Choice', path, segment, item['Id'], number, transition.strip('; '))
                    for tr in params.get('SequenceTransitions', {}).get(str(segment), []):
                        seqs = params.get('TalkSequence', [])
                        if not tr.get('OptionTextKey') and isinstance(segment, int) and seqs and item['Id'] == seqs[segment][-1] and result:
                            result[-1]['transition'] += '; 구간 ' + str(tr.get('NextSequenceIndex')) + '로 이동'
            elif action.get('Name') == 'ShowCenterText':
                add(params.get('TidCenterText'), '화면 문구', None, 'Screen', path)
            elif action.get('Name') == 'PlayMovie':
                video = params.get('VideoName')
                for moment, number, tid in self.captions.get(video, []):
                    add(tid, '영상 자막', None, 'Screen', path, video, number, moment=moment)
        self.row_cache[key] = result
        return result

    def object_edges(self, value, owner, relative_flow=None):
        for obj, path in walk(value):
            if obj.get('FlowListName') and 'FlowId' in obj:
                key = f"{obj['FlowListName']}_{obj['FlowId']}_{obj.get('StateId', 1)}"
                yield ('flow', key), owner + path
            if obj.get('Name') == 'ChangeState' and relative_flow:
                yield ('flow', relative_flow + '_' + str(obj.get('Params', {}).get('StateId'))), owner + path
            if obj.get('Name') == 'TeleportDungeon':
                yield ('dungeon', str(obj.get('Params', {}).get('DungeonId'))), owner + path
            if obj.get('Type') == 'EnterDungeon' and obj.get('DungeonId'):
                yield ('dungeon', str(obj['DungeonId'])), owner + path
            if obj.get('LevelPlayId') is not None:
                yield ('level', str(obj['LevelPlayId'])), owner + path
            # Reference tokens explicitly identify objects. q_ points to another
            # quest or prerequisite and is intentionally not an ownership edge.
            for field in ('Reference', 'WeakReference', 'Children'):
                tokens = obj.get(field, [])
                if not isinstance(tokens, list):
                    continue
                for index, token in enumerate(tokens):
                    if not isinstance(token, str):
                        continue
                    match = re.fullmatch(r'f_(\d+)_(\d+)', token)
                    at = owner + path + '/' + field + '/' + str(index)
                    if match and int(match[1]) in self.flow_ids:
                        prefix = self.flow_ids[int(match[1])] + '_' + match[2]
                        for state in self.states_by_flow.get(prefix, []):
                            yield ('flow', state), at
                    match = re.fullmatch(r'e_(\d+)_(\d+)', token)
                    if match:
                        yield ('entity', (int(match[1]), int(match[2]))), at
                    match = re.fullmatch(r'l_(\d+)_(\d+)', token)
                    if match and self.tables['level'].get(match[2], {}).get('LevelId') == int(match[1]):
                        yield ('level', match[2]), at

    def closure(self, quest_id, baseline):
        first = ('quest', quest_id)
        parents = {first: None}
        queue = deque([first])
        for key in baseline:
            node = ('flow', key)
            parents[node] = (first, 'published scene')
            queue.append(node)
        missing = []
        while queue:
            node = queue.popleft()
            kind, key = node
            values = []
            if kind in ('quest', 'level'):
                data = self.tables[kind].get(key)
                if data is not None:
                    values = [(kind + ':' + key, data), *self.node_groups[kind].get(key, [])]
                    if kind == 'quest':
                        values.append(('recall:' + key, self.tables['recall'].get(key, [])))
                        if str(data.get('DungeonId')) in self.dungeons:
                            values.append(('quest-dungeon:' + key, {'Type': 'EnterDungeon', 'DungeonId': data['DungeonId']}))
            elif kind == 'flow':
                if key in self.tables['flow']:
                    values = [('flow:' + key, self.tables['flow'][key])]
                else:
                    missing.append({'kind': kind, 'key': key})
            elif kind == 'entity':
                if key in self.entities:
                    if key not in self.entity_cache:
                        fb = FB(self.entities[key])
                        self.entity_cache[key] = json.loads(fb.string(fb.root(), 10))
                    values = [(f'entity:{key[0]}:{key[1]}', self.entity_cache[key])]
            elif kind == 'dungeon' and key in self.dungeons:
                for level in sorted(self.levels_by_map[self.dungeons[key]], key=int):
                    dst = ('level', level)
                    if dst not in parents:
                        parents[dst] = (node, f'dungeon:{key}/MapConfigId/{self.dungeons[key]}/LevelPlay/{level}')
                        queue.append(dst)
            for owner, value in values:
                for dst, source in self.object_edges(value, owner, key.rsplit('_', 1)[0] if kind == 'flow' else None):
                    if dst not in parents:
                        parents[dst] = (node, source)
                        queue.append(dst)
        flows = [key for kind, key in parents if kind == 'flow' and key in self.tables['flow']]

        def proof(key):
            node, chain = ('flow', key), []
            while parents[node] is not None:
                node, source = parents[node]
                chain.append(source)
            return list(reversed(chain))

        return flows, proof, missing

    def unchanged(self):
        return all(sha((self.root / name).read_bytes()) == digest for name, digest in self.hashes.items())


def scene_text(number, state, rows, proof):
    speakers = list(dict.fromkeys(row['speaker'] for row in rows if row['kind'] == '대사' and row['speaker'] not in ('화면 문구', '화자 미지정')))
    title = ' · '.join(speakers[:2]) if speakers else '화면 문구와 기록'
    lines = ['', '─' * 55, f'장면 {number}: 추가 원문 · {title}',
             '순서 근거: 연결 자료의 수록 순서 · 실제 진행 순서 미확인', '대화 ID: ' + state,
             '대화 묶음 연결 근거: ' + ' → '.join(proof), '']
    unavailable = sum(row['status'] != 'OK' for row in rows)
    if unavailable:
        lines.insert(-1, f'대화 묶음 한국어 미확인: {unavailable}개 항목')
    for row in rows:
        if row['status'] != 'OK':
            continue
        value = row['text']
        if row['kind'] == '선택지':
            prefix = f"  선택 {row['option']}: "
        else:
            prefix = (f"[대화ID {row['talk_id']}] " if row['kind'] == '대사' else '') + row['speaker'] + ': '
        lines.append(prefix + value)
        if row['transition']:
            lines.append('    → ' + row['transition'].strip('; '))
    return '\n'.join(lines) + '\n'


def refresh_preserved_citations(repo, quests, previous_hashes):
    """Advance file hashes only after the cited baseline scene still matches."""
    manifest_path = repo / 'settings/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for name in ('atlas.json', 'npc-people.json', 'editorial.json'):
        path = repo / 'settings' / name
        data = path.read_bytes()
        normalized = data.decode('utf-8').replace('\r\n', '\n').encode('utf-8') if manifest.get('hash_normalization', {}).get(name) == 'lf' else data
        if sha(normalized) != manifest['files'][name]:
            raise ValueError('Editorial input hash mismatch: ' + name)
        doc = json.loads(data)
        changed = False
        for ref, _ in walk(doc):
            if not ref.get('quest_id') or not ref.get('source_sha256'):
                continue
            qid = str(ref['quest_id'])
            entry = quests[qid]
            if ref['source_sha256'] not in (entry['baseline_sha256'], entry['result_sha256'], previous_hashes[qid]):
                raise ValueError('Citation baseline hash mismatch: ' + qid)
            baseline = (repo / 'originals' / (qid + '.txt')).read_bytes()[:entry['baseline_bytes']]
            if sha(baseline) != entry['baseline_sha256']:
                raise ValueError('Citation baseline bytes changed: ' + qid)
            raw = baseline.decode('utf-8-sig')
            blocks = list(re.finditer(r'^장면 (\d+):', raw, re.M))
            pos = next((i for i, block in enumerate(blocks) if int(block[1]) == ref['scene']), None)
            scene = raw[blocks[pos].start():blocks[pos+1].start() if pos+1 < len(blocks) else len(raw)] if pos is not None else ''
            if not ref.get('quote') or ref['quote'] not in scene:
                raise ValueError('Preserved citation quote/scene differs: ' + qid)
            if ref['source_sha256'] != entry['result_sha256']:
                ref['source_sha256'] = entry['result_sha256']
                changed = True
        if changed:
            data = (json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            path.write_bytes(data)
            manifest['files'][name] = sha(data)
    report_data = (repo / 'settings/quest-supplements.json').read_bytes()
    manifest['files']['quest-supplements.json'] = sha(report_data.replace(b'\r\n', b'\n'))
    manifest.setdefault('hash_normalization', {})['quest-supplements.json'] = 'lf'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def recover(sources, repo, apply=False):
    repo = Path(repo)
    manifest_path = repo / 'content-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    quests, summary, reached, previous_hashes = {}, Counter(), set(), {}
    for quest in manifest:
        path = repo / 'originals' / (quest['id'] + '.txt')
        current = path.read_bytes()
        previous_hashes[quest['id']] = sha(current)
        if sha(current) != quest['source_sha256']:
            raise ValueError('Published original hash mismatch: ' + quest['id'])
        base = current[:quest.get('recovery_base_bytes', len(current))]
        base_sha = quest.get('recovery_base_sha256', quest['source_sha256'])
        if sha(base) != base_sha:
            raise ValueError('Recovery baseline changed: ' + quest['id'])
        text = base.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        baseline = re.findall(r'^대화 ID: (.+)$', text, re.M)
        flows, proof, missing = sources.closure(quest['id'], baseline)
        reached.update(flows)
        extra = [key for key in flows if key not in set(baseline)
                 and any(row['status'] == 'OK' for row in sources.rows(key))]
        scenes, additions = [], []
        old_count = len(re.findall(r'^장면 \d+: ', text, re.M))
        for number, key in enumerate(extra, old_count + 1):
            rows = sources.rows(key)
            scenes.append({'scene': number, 'state_key': key, 'proof': proof(key), 'rows': rows})
            additions.append(scene_text(number, key, rows, proof(key)))
            summary.update({'rows': len(rows), 'scenes': 1})
        result = base + ''.join(additions).encode('utf-8')
        quests[quest['id']] = dict(baseline_sha256=base_sha, baseline_bytes=len(base),
                                   baseline_scenes=old_count, baseline_states=baseline,
                                   reachable_states=flows, missing_state_references=missing,
                                   scenes=scenes, result_sha256=sha(result))
        if scenes:
            summary['changed_quests'] += 1
        if apply:
            path.write_bytes(result)
            quest.update(source_sha256=sha(result), recovery_base_bytes=len(base),
                         recovery_base_sha256=base_sha, baseline_scenes=old_count,
                         recovered_scenes=len(scenes), recovered_lines=sum(len(s['rows']) for s in scenes))
    unassigned = [key for key in sources.tables['flow'] if key not in reached and sources.rows(key)]
    summary['quests'] = len(manifest)
    summary['unique_text_ids'] = len({r['text_id'] for q in quests.values() for s in q['scenes'] for r in s['rows']})
    summary['unassigned_states'] = len(unassigned)
    report = dict(schema='wuwa-quest-source-recovery.v1', observed_snapshot='2026-10-08; client version unverified',
                  source_databases=sources.hashes, flowlist_hashes=sources.flow_hashes,
                  summary=dict(summary), quests=quests, unassigned_states=unassigned,
                  order_note='Supplementary source order does not establish gameplay chronology.')
    if not sources.unchanged():
        raise ValueError('Source inputs changed during recovery')
    if apply:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (repo / 'settings' / 'quest-supplements.json').write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        refresh_preserved_citations(repo, quests, previous_hashes)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configdb', required=True, type=Path)
    parser.add_argument('--flowlists', required=True, type=Path)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    data = recover(Sources(args.configdb, args.flowlists), args.repo, args.apply)
    if args.report:
        args.report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(data['summary'], ensure_ascii=False))
