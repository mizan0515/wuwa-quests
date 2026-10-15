"""Build conditional bubble references from pinned read-only client inputs."""
import argparse
import hashlib
import json
from pathlib import Path
from recover_quest_sources import walk
from wuwa_handbook import FB, connect

WITNESSES = {
    'Core/Define/Config/Flow.js': 'GetStatesAt(t){return this.states(t)}',
    'Game/Module/Plot/Flow/FlowConfig.js': 'l=(l=i?this.GetFlowStateActions(t,e,i):l)||this.YXi(t,e,o)',
    'Game/NewWorld/Character/Common/Component/Flow/CharacterFlowComponent.js': 'getComponent)(t.ComponentsData,"BubbleComponent")',
    'Game/NewWorld/Character/Common/Component/Flow/CharacterFlowLogic.js': 'GetRandomFlow(t.FlowListName,t.FlowId,this.ActorComp.Owner.GetName(),i)',
    'Game/NewWorld/Character/Npc/Component/CommonNpcPerformComponent.js': 'getComponent)(t.ComponentsData,"NpcPerformComponent")',
    'Game/NewWorld/Character/Npc/StateMachine/NpcPerformUnderAttackState.js': 'this.qtr=e.NpcHitShow.HitBubble',
    'Game/NewWorld/Character/Npc/StateMachine/NpcPerformMonsterNearbyState.js': 'this.qtr=e.NpcMonsterClosePerform.Bubble',
    'Game/NewWorld/Character/Npc/StateMachine/Common/NpcPerceptionReactionUtil.js': 'GetRandomFlow(r.FlowListName,r.FlowId,e.GetComponent(2).Actor.ActorLabel,r.StateId)',
    'Game/LevelGamePlay/LevelEvents/LevelEventPlayBubble.js': 'EntityIds:[e],Flow:r.Flow,WaitTime:0',
    'Game/LevelGamePlay/LevelAi/Tasks/LevelAiTaskPlayBubble.js': 'EntityIds:[e],Flow:r.Flow,WaitTime:0',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def consumer(pointer, ancestors):
    if pointer.startswith('/BubbleComponent/Flows/') and pointer.endswith('/Flow/FlowIndex'):
        return 'ambient'
    if pointer == '/NpcPerformComponent/NpcHitShow/HitBubble':
        return 'hit'
    if pointer == '/NpcPerformComponent/NpcMonsterClosePerform/Bubble':
        return 'monster'
    if pointer.endswith('/Params/Flow') and any(v.get('Name') == 'PlayBubble' for v, _ in ancestors if isinstance(v, dict)):
        return 'action'
    return None


def build(repo, configdb, javascript):
    original_raw = (repo / 'settings/dialogue-attribution.json').read_bytes()
    original = json.loads(original_raw)
    for name in ['db_flowState.db', 'db_level_entity.db']:
        if sha((configdb / name).read_bytes()) != original['source_databases'][name]:
            raise ValueError('Original source snapshot differs: ' + name)
    scope = {key for key, value in original['states'].items() if value['classification'] == 'unreferenced'}
    witnesses = {}
    for resource, expression in WITNESSES.items():
        raw = (javascript / resource).read_bytes()
        if expression not in raw.decode('utf8'):
            raise ValueError('Typed consumer expression absent: ' + resource)
        witnesses[resource] = {'sha256': sha(raw), 'expression': expression}
    flows = {}
    with connect(configdb / 'db_flow.db') as db:
        for pair, blob in db.execute('SELECT Id,BinData FROM flow'):
            fb = FB(blob)
            assert fb.string(fb.root(), 0) == pair
            flows[pair] = (fb.uint_vector(fb.root(), 2), sha(blob))
    references = {}
    states = {}
    condition_keys = {'Condition', 'Conditions', 'WorldState', 'MaxTriggerTimes', 'EnterRange', 'LeaveRange',
                      'TriggerCylinderConfig', 'WaitTime', 'BubbleRate', 'Rate', 'LoopTime'}
    with connect(configdb / 'db_level_entity.db') as db:
        for row_id, map_id, entity_id, blob in db.execute('SELECT Id,MapId,EntityId,BinData FROM levelentityconfig'):
            fb = FB(blob)
            assert (fb.scalar(fb.root(), 1), fb.scalar(fb.root(), 2)) == (map_id, entity_id)
            raw = fb.string(fb.root(), 10)
            if not raw:
                continue
            payload = json.loads(raw)
            for value, pointer in walk(payload):
                if not value.get('FlowListName') or 'FlowId' not in value or value.get('StateId'):
                    continue
                ancestors = []
                current = payload
                at = ''
                for token in pointer.split('/')[1:]:
                    ancestors.append((current, at))
                    current = current[int(token)] if isinstance(current, list) else current[token]
                    at += '/' + token
                kind = consumer(pointer, ancestors)
                pair = f"{value['FlowListName']}_{value['FlowId']}"
                if not kind or pair not in flows:
                    continue
                state_ids, flow_hash = flows[pair]
                targets = [pair + '_' + str(s) for s in state_ids if pair + '_' + str(s) in scope]
                if not targets:
                    continue
                recipient_ids = [entity_id]
                if kind == 'ambient':
                    recipient_ids = payload['BubbleComponent'].get('NpcIds', []) or [entity_id]
                elif kind == 'action':
                    params = ancestors[-1][0]
                    recipient_ids = [params.get('EntityId') or entity_id]
                conditions = [{'pointer': at + '/' + key, 'value': obj[key]}
                              for obj, at in ancestors if isinstance(obj, dict)
                              for key in sorted(condition_keys.intersection(obj))]
                reference = {'source': {'database': 'db_level_entity.db', 'rowId': row_id, 'mapId': map_id,
                                        'entityId': entity_id, 'blobSha256': sha(blob), 'pointer': pointer},
                             'consumer': kind, 'input': value, 'recipientEntityIds': recipient_ids,
                             'conditions': conditions,
                             'selection': {'mode': 'random-state', 'pair': pair, 'requestedStateId': value.get('StateId'),
                                           'stateIds': state_ids, 'flowBlobSha256': flow_hash},
                             'targets': targets, 'runtimeObserved': False}
                key = sha(canonical(reference))
                references[key] = reference
                for target in targets:
                    states.setdefault(target, []).append(key)
    for values in states.values():
        values.sort()
    result = {'schema': 'wuwa-random-flow-references.v1',
              'sourceHashes': {'dialogueAttribution': sha(original_raw), **{name: sha((configdb / name).read_bytes())
                                                                       for name in ['db_flow.db', 'db_flowState.db', 'db_level_entity.db']}},
              'consumerSources': witnesses, 'references': dict(sorted(references.items())), 'states': dict(sorted(states.items()))}
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--configdb', required=True, type=Path)
    p.add_argument('--javascript', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.output.resolve() != (a.repo / 'settings/random-flow-references.json').resolve():
        raise ValueError('Output must be the owned conditional reference overlay')
    result = build(a.repo, a.configdb, a.javascript)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': 'PASS', 'references': len(result['references']), 'states': len(result['states']),
                      'sha256': sha(a.output.read_bytes())}))
