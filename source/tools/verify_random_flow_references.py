"""Independently replay conditional bubble targets, conditions and rendered proof."""
import argparse
from collections import Counter
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from recover_quest_sources import walk
from wuwa_handbook import FB, connect

SCHEMA = 'wuwa-random-flow-references.v1'
CONDITIONS = {'Condition', 'Conditions', 'WorldState', 'MaxTriggerTimes', 'EnterRange', 'LeaveRange',
              'TriggerCylinderConfig', 'WaitTime', 'BubbleRate', 'Rate', 'LoopTime'}
KINDS = {'ambient', 'action', 'hit', 'monster'}
REQUIRED_WITNESSES = {
    'Core/Define/Config/Flow.js': ['GetStatesAt(t){return this.states(t)}'],
    'Game/Module/Plot/Flow/FlowConfig.js': ['l=(l=i?this.GetFlowStateActions(t,e,i):l)||this.YXi(t,e,o)',
                                        'ObjectUtils_1.ObjectUtils.GetRandomArrayItem(l.States)',
                                        't=t+`_${e}_`+o'],
    'Game/NewWorld/Character/Common/Component/Flow/CharacterFlowComponent.js': ['getComponent)(t.ComponentsData,"BubbleComponent")'],
    'Game/NewWorld/Character/Common/Component/Flow/CharacterFlowLogic.js': ['GetRandomFlow(t.FlowListName,t.FlowId,this.ActorComp.Owner.GetName(),i)'],
    'Game/NewWorld/Character/Npc/Component/CommonNpcPerformComponent.js': ['getComponent)(t.ComponentsData,"NpcPerformComponent")'],
    'Game/NewWorld/Character/Npc/StateMachine/NpcPerformUnderAttackState.js': ['this.qtr=e.NpcHitShow.HitBubble'],
    'Game/NewWorld/Character/Npc/StateMachine/NpcPerformMonsterNearbyState.js': ['this.qtr=e.NpcMonsterClosePerform.Bubble'],
    'Game/NewWorld/Character/Npc/StateMachine/Common/NpcPerceptionReactionUtil.js': ['GetRandomFlow(r.FlowListName,r.FlowId,e.GetComponent(2).Actor.ActorLabel,r.StateId)'],
    'Game/LevelGamePlay/LevelEvents/LevelEventPlayBubble.js': ['EntityIds:[e],Flow:r.Flow,WaitTime:0'],
    'Game/LevelGamePlay/LevelAi/Tasks/LevelAiTaskPlayBubble.js': ['EntityIds:[e],Flow:r.Flow,WaitTime:0'],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(test, message):
    if not test:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def at(value, pointer):
    ancestors = []
    current = ''
    for token in pointer.split('/')[1:]:
        ancestors.append((value, current))
        value = value[int(token)] if isinstance(value, list) else value[token]
        current += '/' + token
    return value, ancestors


def kind_for(pointer, payload):
    if re.fullmatch(r'/BubbleComponent/Flows/\d+/Flow/FlowIndex', pointer):
        return 'ambient'
    if pointer == '/NpcPerformComponent/NpcHitShow/HitBubble':
        return 'hit'
    if pointer == '/NpcPerformComponent/NpcMonsterClosePerform/Bubble':
        return 'monster'
    action = re.fullmatch(r'/(?:SplineComponent/Option/Points/\d+|LevelAiComponent/States/\d+/Behaviour|TriggerComponent)/Actions/\d+/Params/Flow', pointer)
    if action and at(payload, pointer[:-len('/Params/Flow')])[0].get('Name') == 'PlayBubble':
        return 'action'
    return None


def validate(data, original):
    require(data['schema'] == SCHEMA, 'Conditional schema differs')
    for name in ['db_flowState.db', 'db_level_entity.db']:
        require(data['sourceHashes'][name] == original['source_databases'][name], 'Original source snapshot pin differs: ' + name)
    require(len(data['states']) == 73 and len(data['references']) == 222, 'Fixed conditional cohort differs')
    inverse = {}
    for key, r in data['references'].items():
        require(sha(canonical(r)) == key, 'Conditional reference content hash differs')
        require(set(r) == {'source', 'consumer', 'input', 'recipientEntityIds', 'conditions', 'selection', 'targets', 'runtimeObserved'}, 'Unexpected conditional role')
        require(r['consumer'] in KINDS and r['runtimeObserved'] is False, 'Unverified execution promoted')
        require(r['source']['database'] == 'db_level_entity.db', 'Wrong source domain')
        require(r['selection']['mode'] == 'random-state' and not r['input'].get('StateId'), 'Exact state promoted to random')
        require(r['selection']['requestedStateId'] == r['input'].get('StateId'), 'Requested state differs')
        pair = r['input']['FlowListName'] + '_' + str(r['input']['FlowId'])
        require(r['selection']['pair'] == pair, 'Flow pair differs')
        expected = [pair + '_' + str(s) for s in r['selection']['stateIds']
                    if original['states'].get(pair + '_' + str(s), {}).get('classification') == 'unreferenced']
        require(r['targets'] == expected and expected, 'Random target inverse differs')
        require(all(original['states'][s]['readable'] for s in expected), 'Target original absent')
        for state in expected:
            inverse.setdefault(state, []).append(key)
    require({k: sorted(v) for k, v in inverse.items()} == data['states'], 'Conditional state membership differs')
    return {'references': len(data['references']), 'states': len(data['states']),
            'originalRows': sum(len(original['states'][s]['rows']) for s in data['states'])}


def replay_reference(r, entity, flow, original):
    blob, map_id, entity_id, payload = entity
    require(r['source']['mapId'] == map_id and r['source']['entityId'] == entity_id and sha(blob) == r['source']['blobSha256'], 'Actual source entity identity differs')
    value, ancestors = at(payload, r['source']['pointer'])
    require(value == r['input'], 'Actual source tuple differs')
    kind = kind_for(r['source']['pointer'], payload)
    require(kind == r['consumer'] and kind in KINDS, 'Unconfirmed consumer path')
    state_ids, flow_blob = flow
    require(r['selection']['stateIds'] == state_ids and r['selection']['flowBlobSha256'] == sha(flow_blob), 'Actual random state list differs')
    conditions = [{'pointer': pointer + '/' + key, 'value': obj[key]}
                  for obj, pointer in ancestors if isinstance(obj, dict)
                  for key in sorted(CONDITIONS.intersection(obj))]
    require(r['conditions'] == conditions, 'Actual source conditions differ')
    recipients = [entity_id]
    if kind == 'ambient':
        recipients = payload['BubbleComponent'].get('NpcIds', []) or [entity_id]
    elif kind == 'action':
        recipients = [ancestors[-1][0].get('EntityId') or entity_id]
    require(r['recipientEntityIds'] == recipients, 'Runtime recipient confused with original speaker or source entity')


def source_replay(data, original, configdb, javascript):
    for name, digest in data['sourceHashes'].items():
        if name != 'dialogueAttribution':
            require(sha((configdb / name).read_bytes()) == digest, 'Actual source DB hash differs: ' + name)
    require(set(data['consumerSources']) == set(REQUIRED_WITNESSES), 'Typed consumer witness inventory differs')
    for resource, witness in data['consumerSources'].items():
        raw = (javascript / resource).read_bytes()
        require(sha(raw) == witness['sha256'] and witness['expression'] in raw.decode('utf8'), 'Actual typed consumer changed: ' + resource)
        require(all(expression in raw.decode('utf8') for expression in REQUIRED_WITNESSES[resource]), 'Typed random-selection semantics changed: ' + resource)
    require(len(data['consumerSources']) == 10, 'Consumer witness inventory differs')
    flows = {}
    with connect(configdb / 'db_flow.db') as db:
        for pair, blob in db.execute('SELECT Id,BinData FROM flow'):
            fb = FB(blob)
            require(fb.string(fb.root(), 0) == pair, 'Flow SQL/native key differs')
            flows[pair] = (fb.uint_vector(fb.root(), 2), blob)
    wanted = {r['source']['rowId'] for r in data['references'].values()}
    entities = {}
    census = set()
    with connect(configdb / 'db_level_entity.db') as db:
        for row_id, map_id, entity_id, blob in db.execute('SELECT Id,MapId,EntityId,BinData FROM levelentityconfig'):
            fb = FB(blob)
            require((fb.scalar(fb.root(), 1), fb.scalar(fb.root(), 2)) == (map_id, entity_id), 'Entity SQL/native key differs')
            text = fb.string(fb.root(), 10)
            if not text:
                continue
            payload = json.loads(text)
            if row_id in wanted:
                entities[row_id] = (blob, map_id, entity_id, payload)
            for value, pointer in walk(payload):
                if not value.get('FlowListName') or 'FlowId' not in value or value.get('StateId'):
                    continue
                kind = kind_for(pointer, payload)
                pair = value['FlowListName'] + '_' + str(value['FlowId'])
                if not kind or pair not in flows:
                    continue
                if any(original['states'].get(pair + '_' + str(s), {}).get('classification') == 'unreferenced' for s in flows[pair][0]):
                    census.add((row_id, pointer, kind))
    require(census == {(r['source']['rowId'], r['source']['pointer'], r['consumer']) for r in data['references'].values()}, 'Whole typed consumer census differs')
    for r in data['references'].values():
        replay_reference(r, entities[r['source']['rowId']], flows[r['selection']['pair']], original)
    # Existing SQL actions, including an empty array, are truthy in JavaScript.
    branch_cases = 0
    with connect(configdb / 'db_flowState.db') as db:
        for pair in {r['selection']['pair'] for r in data['references'].values()}:
            state_ids = flows[pair][0]
            row = db.execute('SELECT BinData FROM flowstate WHERE StateKey=?', (pair + '_' + str(state_ids[0]),)).fetchone()
            require(row is not None, 'Random candidate state absent from SQL')
            fb = FB(row[0]);actions = json.loads(fb.string(fb.root(), 6))
            require(isinstance(actions, list), 'State Actions domain differs')
            require(potential_states(state_ids[0], actions, state_ids) == [state_ids[0]], 'Valid exact state expanded')
            require(potential_states(0, actions, state_ids) == state_ids, 'Falsy state lost random targets')
            absent = max(state_ids) + 1
            while db.execute('SELECT 1 FROM flowstate WHERE StateKey=?', (pair + '_' + str(absent),)).fetchone():
                absent += 1
            require(potential_states(absent, None, state_ids) == state_ids, 'Missing exact lookup lost fallback')
            branch_cases += 3
    # Mutations retain plausible types; replay must reject semantic mismatches.
    r = next(iter(data['references'].values()))
    rejected = []
    for name, change in [('recipient', lambda r: r.__setitem__('recipientEntityIds', [r['recipientEntityIds'][0] + 1])),
                         ('stateList', lambda r: r['selection'].__setitem__('stateIds', r['selection']['stateIds'][:-1])),
                         ('tuple', lambda r: r['input'].__setitem__('FlowId', r['input']['FlowId'] + 1)),
                         ('condition', lambda r: r['conditions'].append({'pointer': '/invented', 'value': True})),
                         ('unconfirmedConsumer', lambda r: r['source'].__setitem__('pointer', '/NpcPerformComponent/NpcBumpShow/BumpBubble/Bubble'))]:
        changed = copy.deepcopy(r);change(changed)
        try:
            replay_reference(changed, entities[r['source']['rowId']], flows[r['selection']['pair']], original)
        except (ValueError, KeyError, IndexError):
            rejected.append(name)
        else:
            raise ValueError('Semantic mutation accepted: ' + name)
    return {'sourceReferencesReplayed': len(data['references']), 'typedConsumerCensus': len(census),
            'sourceWitnesses': len(data['consumerSources']), 'exactAndFallbackCases': branch_cases,
            'semanticMutationsRejected': rejected}


def potential_states(requested, actions, state_ids):
    return [requested] if requested and actions is not None else state_ids


class Rendered(HTMLParser):
    def __init__(self, data):
        super().__init__(convert_charrefs=True)
        self.data = data;self.stack = [];self.context = ('', '', False);self.capture = None;self.seen = Counter()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs);state, random_state, ignored = self.context
        before = self.context
        state = a.get('data-dialogue-state', state)
        random_state = a.get('data-random-flow-state', random_state)
        ignored = ignored or 'data-pagefind-ignore' in a
        self.context = (state, random_state, ignored)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, before))
        else:
            self.context = before
        if 'data-random-flow-proof' in a:
            key = a['data-random-flow-proof']
            require(state == random_state and key in self.data['states'].get(state, []) and ignored, 'Conditional proof outside matching original or indexed as prose')
            self.capture = (state, key, [])

    def handle_data(self, text):
        if self.capture:
            self.capture[2].append(text)

    def handle_endtag(self, tag):
        if tag == 'pre' and self.capture:
            state, key, text = self.capture
            require(json.loads(''.join(text)) == self.data['references'][key], 'Rendered conditional conditions or recipient differs')
            self.seen[(state, key)] += 1;self.capture = None
        positions = [i for i, value in enumerate(self.stack) if value[0] == tag]
        if positions:
            i = positions[-1];self.context = self.stack[i][1];del self.stack[i:]


def rendered_replay(data, original, dist):
    parser = Rendered(data)
    groups = [g for g in original['groups'] if any(s in data['states'] for s in g['states'])]
    for group in groups:
        parser.feed((dist / 'dialogue-sources' / (group['id'] + '.html')).read_text(encoding='utf8'))
    parser.close()
    expected = Counter((state, key) for state, refs in data['states'].items() for key in refs)
    require(parser.seen == expected, 'Rendered conditional source membership absent, duplicated or changed')
    return {'renderedGroups': len(groups), 'renderedConditionalOccurrences': sum(expected.values())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--configdb', type=Path);p.add_argument('--javascript', type=Path)
    p.add_argument('--public-only', action='store_true');p.add_argument('--dist', type=Path);p.add_argument('--report', type=Path)
    a = p.parse_args()
    require(a.public_only or (a.configdb and a.javascript), 'Source replay requires --configdb and --javascript; portable mode must be explicit')
    require(not a.public_only or not (a.configdb or a.javascript), 'Source inputs require source replay mode')
    root = a.repo.resolve();raw = (root / 'settings/random-flow-references.json').read_bytes()
    original_raw = (root / 'settings/dialogue-attribution.json').read_bytes();original = json.loads(original_raw)
    manifest = json.loads((root / 'settings/manifest.json').read_text(encoding='utf8'));data = json.loads(raw)
    require(manifest['files'].get('random-flow-references.json') == sha(raw), 'Conditional overlay byte pin differs')
    require(data['sourceHashes']['dialogueAttribution'] == sha(original_raw) == manifest['files']['dialogue-attribution.json'], 'Original byte pin differs')
    counts = validate(data, original)
    require(potential_states(1, [], [1, 2]) == [1] and potential_states(1, None, [1, 2]) == [1, 2], 'Empty Actions versus missing exact-state fallback regressed')
    if not a.public_only:
        counts.update(source_replay(data, original, a.configdb.resolve(), a.javascript.resolve()))
    if a.dist:
        counts.update(rendered_replay(data, original, a.dist.resolve()))
    report = {'schema': 'wuwa-random-flow-reference-verification.v1', 'status': 'PASS', 'overlaySha256': sha(raw), 'counts': counts,
              'verifiedSurfaces': {'publicPayload': True, 'actualSQLAndConsumerBytes': not a.public_only, 'renderedHTML': bool(a.dist)},
              'limits': ['Conditional configured target relations; live event execution and quest/geographic ownership remain unverified.',
                         'Original dialogue text and speaker remain in the immutable attribution inventory.']}
    if a.report:
        target = a.report.resolve()
        require(target.suffix == '.json' and not target.is_relative_to(root / 'settings') and not (a.configdb and target.is_relative_to(a.configdb.resolve())) and not (a.javascript and target.is_relative_to(a.javascript.resolve())), 'Report may not overwrite source inputs')
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
