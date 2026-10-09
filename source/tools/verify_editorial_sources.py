"""Read-only verification of every authored evidence quote and source role.

Checks atlas, NPC and editorial references against the exact record field or
quest scene. The semantic canaries retain source-backed corrections and
the distinction between a proposed revival and post-battle jewel handling;
optional self-tests demonstrate that valid quotes with wrong attribution or
relations fail, as do source, scene, and quote corruption.
"""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

GROUPS = ('regions', 'sentinels', 'cosmology', 'factions', 'people')
MEMORY_GUARDIAN = '여우의 별자리의 기억 속 수호신'


def gather(value, pointer=''):
    if isinstance(value, list):
        for i, item in enumerate(value):
            yield from gather(item, pointer + '/' + str(i))
    elif isinstance(value, dict):
        if ('source_text_sha256' in value and 'id' in value) or ('quest_id' in value and 'quote' in value):
            yield pointer, value
        else:
            for key, item in value.items():
                yield from gather(item, pointer + '/' + key)


class SourceAudit:
    def __init__(self, site):
        self.site = site
        settings = site / 'settings'
        self.aliases = json.loads((settings / 'index.json').read_text(encoding='utf-8'))['aliases']
        self.records = {}
        for path in settings.glob('records-*.json'):
            self.records.update(json.loads(path.read_text(encoding='utf-8')))
        self.quest_cache = {}

    def quest(self, ident):
        if ident not in self.quest_cache:
            raw = (self.site / 'originals' / (ident + '.txt')).read_bytes()
            text = raw.decode('utf-8-sig')
            starts = list(re.finditer(r'^장면 (\d+):', text, re.M))
            scenes = {int(m[1]): text[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)]
                      for i, m in enumerate(starts)}
            self.quest_cache[ident] = hashlib.sha256(raw).hexdigest(), scenes
        return self.quest_cache[ident]

    def verify(self, inputs):
        errors, checked = [], []

        def require(condition, message, **context):
            if not condition:
                errors.append({'error': message, **context})

        for filename, data in inputs.items():
            for pointer, ref in gather(data):
                context = {'file': filename, 'pointer': pointer}
                if ref.get('quest_id'):
                    ident = str(ref['quest_id'])
                    context.update(source='quest-' + ident, scene=ref.get('scene'))
                    try:
                        digest, scenes = self.quest(ident)
                    except (OSError, UnicodeError, ValueError) as error:
                        require(False, 'quest source cannot be read', detail=str(error), **context)
                        continue
                    scene = scenes.get(ref.get('scene'), '')
                    quote = ref.get('quote', '')
                    require(digest == ref.get('source_sha256'), 'quest source hash differs', **context)
                    require(bool(quote) and quote in scene, 'quest quote differs from exact scene', **context)
                    # Partial quotes may begin inside a line. Inspect the
                    # actual line's author, rather than forcing the quote to
                    # begin directly after its speaker prefix.
                    speakers = []
                    for line in scene.splitlines():
                        m = re.match(r'^\[대화ID [^\]]+\] (.+?): (.*)$', line)
                        if not m:
                            m = re.match(r'^(화면 문구): (.*)$', line)
                        if m and quote and quote in m[2]:
                            speakers.append(m[1])
                    require(bool(ref.get('speaker')) and ref['speaker'] in speakers,
                            'quest quote attributed to a different source speaker', **context)
                    checked.append((filename, 'quest-' + ident, 'scene-' + str(ref.get('scene')), quote))
                else:
                    ident = self.aliases.get(ref['id'], ref['id'])
                    context.update(source=ident, field=ref.get('field'))
                    record = self.records.get(ident, {})
                    value = next((v for v in record.get('values', [])
                                  if v['field'] == ref.get('field') and v['status'] == 'OK'), None)
                    require(value is not None, 'setting source field cannot be read', **context)
                    if value is None:
                        continue
                    quote = ref.get('excerpt', '')
                    require(hashlib.sha256(value['raw'].encode()).hexdigest() == ref.get('source_text_sha256'),
                            'setting source hash differs', **context)
                    require(bool(quote) and quote in value['text'],
                            'setting quote differs from exact field', **context)
                    checked.append((filename, ident, ref.get('field'), quote))

        atlas = inputs['atlas.json']
        clusters = {g + '/' + c['id']: c for g in GROUPS for c in atlas[g]}

        def cluster(ident):
            require(ident in clusters, 'semantic source cluster missing', cluster=ident)
            return clusters.get(ident, {})

        def matches_setting(item, source, field, literal):
            return any(self.aliases.get(r.get('id'), r.get('id')) == source and r.get('field') == field
                       and literal in r.get('excerpt', '') for r in item.get('refs', []))

        # A proposed mission is conditional in Jiyan's source dialogue.
        for ident in ('regions/jinzhou', 'cosmology/the-axion'):
            edges = cluster(ident).get('edges', [])
            edge = next((e for e in edges if e.get('a') == '기염' and e.get('b') == '더 엑시온'), {})
            require('가능하다면' in edge.get('verb', '') and edge.get('speaker') == '기염'
                    and any(r.get('quest_id') == '140000004' and r.get('scene') == 37
                            and r.get('speaker') == '기염' and '가능하다면' in r.get('quote', '')
                            for r in edge.get('refs', [])),
                    'Jiyan conditional mission or attributed actor changed', cluster=ident)
        axion = cluster('cosmology/the-axion')
        section = next((s for s in axion.get('sections', []) if s.get('title') == '북락 광야의 곡도 전쟁'), {})
        require('가능하다면' in section.get('text', '') and '조건' in section.get('text', ''),
                'Axion mission summary lost the source condition', cluster='cosmology/the-axion')

        # The imitated appearance belongs to a guardian in the fox's memory.
        for ident in ('regions/mongju', 'sentinels/fox', 'cosmology/tianyan'):
            c = cluster(ident)
            edges = [e for e in c.get('edges', []) if e.get('a') == '천연'
                     and ('모습' in e.get('verb', '') or '형상' in e.get('verb', ''))]
            require(len(edges) == 1 and edges[0].get('b') == MEMORY_GUARDIAN
                    and matches_setting(edges[0], '잔상_생태:monsterinfo:340000330', 'discovered_description',
                                        '여우의 별자리의 기억 속에 있는 「수호신」과 흡사한 모습'),
                    'Tianyan remembered form identified as a current guardian', cluster=ident)
            require(any(n.get('name') == MEMORY_GUARDIAN and n.get('kind') == '기억 속 형상'
                        for n in c.get('nodes', [])), 'remembered guardian role missing', cluster=ident)

        # The ring's purpose is explicit; the passive source does not identify
        # a separate installer. Keep the device-to-bound-subject relationship.
        ring_source = '아이템_배경:iteminfo:41400354'
        ring_literal = '천연을 구속하기 위해 설치된 제한 장치'
        for ident in ('sentinels/fox', 'cosmology/tianyan'):
            c = cluster(ident)
            ring = next((e for e in c.get('edges', [])
                         if matches_setting(e, ring_source, 'background', ring_literal)), {})
            require(ring.get('a') == '천연륜' and ring.get('b') == '천연'
                    and '목적으로 설치됐다' in ring.get('verb', '')
                    and '구속하기 위한 제한 장치' in ring.get('reason', ''),
                    'Tianyan ring purpose attributed to an unconfirmed installer', cluster=ident)
        tianyan = cluster('cosmology/tianyan')
        ring_process = next((p for p in tianyan.get('process', [])
                             if p.get('title') == '천연의 구속을 위한 장치'), {})
        ring_section = next((s for s in tianyan.get('sections', [])
                             if s.get('title') == '천연륜의 봉인과 침식'), {})
        for item in (ring_process, ring_section):
            require('구속하기 위한 제한 장치' in item.get('text', '')
                    and '설치했다' not in item.get('text', '')
                    and '설치한 제한 장치' not in item.get('text', '')
                    and matches_setting(item, ring_source, 'background', ring_literal),
                    'Tianyan ring prose invents a confirmed installation actor', cluster='cosmology/tianyan')

        # The order grants permission; the family receives it on two conditions.
        montelli = cluster('factions/montelli')
        permission = next((e for e in montelli.get('edges', []) if '허용' in e.get('verb', '')), {})
        require(permission.get('a') == '깊은 바다 수도회' and permission.get('b') == '몬텔리 가문'
                and all(word in permission.get('verb', '') for word in ('안전성', '세금', '전제', '허용'))
                and matches_setting(permission, '문서_편지_일기:infodisplay:133002007', 'content',
                                    '결국 수도회는 몬텔리 가문의 개인 단말기 지속 개발과 사용을 허용했다'),
                'terminal permission actor target or conditions changed', cluster='factions/montelli')

        # Resource processing supplies two offices; it does not assert a
        # separate manufacturing method or change the recipients' remit.
        topology = cluster('factions/huaxu').get('topology', {})
        resource = next((n for n in topology.get('nodes', []) if n.get('id') == 'resource'), {})
        require('연구 샘플로 처리' in resource.get('kind', '') and '제조' not in resource.get('kind', ''),
                'resource office responsibility exceeds the source', cluster='factions/huaxu')
        for target, recipient in (('experiment', '실험과'), ('safety', '안전과')):
            edge = next((e for e in topology.get('edges', [])
                         if e.get('from') == 'resource' and e.get('to') == target), {})
            require('야외에서 수집한 재료' in edge.get('text', '')
                    and recipient in edge.get('text', '') and '샘플로 처리' in edge.get('text', '')
                    and '제조' not in edge.get('text', '')
                    and matches_setting(edge, '문서_편지_일기:infodisplay:31000021', 'content',
                                        '야외에서 수집한 재료를 실험과와 안전과에서 사용할 수 있는 귀중한 연구 샘플로 처리'),
                    'sample supply source scope or receiver changed', cluster='factions/huaxu', receiver=recipient)

        # Dialogue proposals remain proposals. Later storage is backed by a
        # different scene; delivery to Tethys is still described as a plan.
        leviathan = cluster('cosmology/leviathan')

        def matches_dialogue(item, scene, speaker, literal):
            return any(r.get('quest_id') == '158800019' and r.get('scene') == scene
                       and r.get('speaker') == speaker and literal in r.get('quote', '')
                       for r in item.get('refs', []))

        revival = next((s for s in leviathan.get('sections', [])
                        if s.get('title') == '크리스토포로가 제시한 주파수 융합'), {})
        require(revival.get('speaker') == '크리스토포로'
                and '경우' in revival.get('text', '') and '주장' in revival.get('text', '')
                and matches_dialogue(revival, 51, '크리스토포로', '두 명식 주파수가 서로 부딪히게 된다면')
                and matches_dialogue(revival, 51, '크리스토포로', '자신을 완전히 부활시킬 수 있을 겁니다'),
                'Leviathan revival proposal became an accomplished fact', cluster='cosmology/leviathan')
        phases = leviathan.get('process', [])
        proposal = next((p for p in phases if p.get('title') == '갈브레나의 조건부 임시 보관 제안'), {})
        require('수 있다면' in proposal.get('text', '') and '제안' in proposal.get('text', '')
                and matches_dialogue(proposal, 78, '갈브레나', '「분리」할 수 있다면'),
                'Leviathan pre-battle storage condition removed', cluster='cosmology/leviathan')
        storage = next((p for p in phases if p.get('title') == '핵심 흡수 후의 상태'), {})
        require(matches_dialogue(storage, 82, '갈브레나', '그 핵심을 흡수한 후로')
                and matches_dialogue(storage, 82, '갈브레나', '키메라가 억누르고'),
                'Leviathan post-battle storage uses a proposal as evidence', cluster='cosmology/leviathan')
        delivery = next((p for p in phases if p.get('title') == '테티스로 보내는 다음 조치'), {})
        require('계획' in delivery.get('text', '')
                and matches_dialogue(delivery, 84, '알토', '테티스한테 보내고 나면'),
                'Leviathan Tethys delivery plan became completed transfer', cluster='cosmology/leviathan')
        require('후계자' not in json.dumps(leviathan, ensure_ascii=False),
                'Leviathan successor relation lacks a source', cluster='cosmology/leviathan')

        # Final source review: keep source tense, deictic scope, and the
        # proposal's conditions when the panels are read independently.
        black_tide = cluster('cosmology/black-tide')
        phenomenon = next((s for s in black_tide.get('sections', [])
                           if s.get('title') == '현상과 확산'), {})
        require(all(word in phenomenon.get('text', '') for word in ('하늘', '주변 지역', '무음구역'))
                and not any(word in phenomenon.get('text', '') for word in ('해양으로', '육지로'))
                and matches_setting(phenomenon, '문서_편지_일기:infodisplay:133002012', 'content',
                                    '이 검은 구름은 주변 지역으로 빠르게 확산'),
                'Black Tide summary adds an unsupported sea-to-land route', cluster='cosmology/black-tide')
        king = next((s for s in leviathan.get('sections', [])
                     if s.get('title') == '흑조의 창조물과 융합의 유토피아'), {})
        require('태어날 것' in king.get('text', '')
                and matches_setting(king, '잔상_생태:monsterinfo:340000170', 'discovered_description',
                                    '아이로 다시 태어날 것이다'),
                'False King source future tense became current repeated outcome', cluster='cosmology/leviathan')
        fixed = next((e for e in leviathan.get('topology', {}).get('edges', [])
                      if e.get('id') == 'lev-fixed'), {})
        require('상태' in fixed.get('text', '') and '확인' not in fixed.get('text', '')
                and matches_dialogue(fixed, 34, '갈브레나', '명식의 주파수를 연결해서 고정시켰으니'),
                'Fixed frequency statement invents a separate confirmation act', cluster='cosmology/leviathan')
        comparison = next((s for s in leviathan.get('comparison', [])
                           if s.get('title') == '갈브레나가 제안한 보석의 보관'), {})
        require(all(word in comparison.get('text', '') for word in ('쓰러뜨리고', '분리할 수 있다면', '제안'))
                and matches_dialogue(comparison, 78, '갈브레나', '「분리」할 수 있다면'),
                'Independent jewel storage comparison lost its prerequisites', cluster='cosmology/leviathan')
        alto = next((s for s in leviathan.get('sections', [])
                     if s.get('title') == '검은 해안의 주파수 대조와 잔성회의 남은 힘'), {})
        require('「이 주파수들」' in alto.get('text', '')
                and matches_dialogue(alto, 87, '알토', '이 주파수들은 「명식의 보석」과 일치하지 않아'),
                'Alto pronoun comparison target narrowed by editorial summary', cluster='cosmology/leviathan')
        mind_section = next((s for s in leviathan.get('sections', [])
                             if s.get('title') == '방랑자가 마주한 마음의 바다'), {})
        mind_relation = next((e for e in leviathan.get('edges', []) if e.get('b') == '마음의 바다'), {})
        mind_topology = next((e for e in leviathan.get('topology', {}).get('edges', [])
                              if e.get('id') == 'lev-mind'), {})
        for item, field in ((mind_section, 'text'), (mind_relation, 'reason'), (mind_topology, 'text')):
            require('이 장면에서 방랑자가 마주한' in item.get(field, '')
                    and matches_dialogue(item, 60, '갈브레나', '여긴 「마음의 바다」야.'),
                    'Mind Sea relation generalized beyond the encountered scene',
                    cluster='cosmology/leviathan', editorialField=field)

        return {'status': 'PASS' if not errors else 'FAIL', 'proofOccurrences': len(checked),
                'proofOccurrencesByFile': dict(Counter(r[0] for r in checked)),
                'uniqueQuotes': len({r[1:] for r in checked}),
                'sourceFieldsAndScenes': len({r[1:3] for r in checked}),
                'semanticCorrectionGroups': 6, 'errors': errors}


def self_tests(audit, inputs):
    def c(data, group, ident):
        return next(x for x in data['atlas.json'][group] if x['id'] == ident)

    def quote(data):
        return next(r for _, r in gather(c(data, 'cosmology', 'aleph-one')) if r.get('quest_id') == '121000040'
                    and r.get('scene') == 37 and r.get('speaker') == '엑소스트라이더')

    def remove_condition(data):
        edge = next(e for e in c(data, 'regions', 'jinzhou')['edges'] if e['a'] == '기염' and e['b'] == '더 엑시온')
        edge['verb'] = edge['verb'].replace('가능하다면 ', '')

    def wrong_memory(data):
        edge = next(e for e in c(data, 'sentinels', 'fox')['edges'] if e['a'] == '천연' and e['b'] == MEMORY_GUARDIAN)
        edge['b'] = '여우의 별자리'

    def reverse_permission(data):
        edge = next(e for e in c(data, 'factions', 'montelli')['edges'] if '허용' in e['verb'])
        edge['a'], edge['b'] = edge['b'], edge['a']

    def inflate_sample(data):
        edge = c(data, 'factions', 'huaxu')['topology']['edges'][0]
        edge['text'] = '자원과는 실험과의 비명 현상 연구를 위한 샘플을 채집하고 제조한다.'

    def wrong_setting_quote(data):
        ref = data['editorial.json']['concepts'][0]['ref']
        ref['excerpt'] = ref['excerpt'][:40] + '…'

    def assign_ring_installer(data):
        ring = next(e for e in c(data, 'cosmology', 'tianyan')['edges']
                    if e['a'] == '천연륜' and e['b'] == '천연')
        ring.update(a='여우의 별자리', b='천연륜', verb='천연의 구속을 위해 설치한다')

    def revival_as_fact(data):
        item = next(s for s in c(data, 'cosmology', 'leviathan')['sections']
                    if s['title'] == '크리스토포로가 제시한 주파수 융합')
        item['text'] = item['text'].replace('주장한다', '확인한다')

    def delivery_as_completed(data):
        item = next(p for p in c(data, 'cosmology', 'leviathan')['process']
                    if p['title'] == '테티스로 보내는 다음 조치')
        item['text'] = '알토는 명식의 보석을 테티스로 보냈다.'

    def source_review_mutation(data, kind):
        lev = c(data, 'cosmology', 'leviathan')
        if kind == 'sea_route':
            item = next(s for s in c(data, 'cosmology', 'black-tide')['sections'] if s['title'] == '현상과 확산')
            item['text'] += ' 해양으로 쏟아진 뒤 육지로 흐른다.'
        elif kind == 'future_tense':
            lev['sections'][3]['text'] = lev['sections'][3]['text'].replace('태어날 것이라고', '태어나게 한다고')
        elif kind == 'confirmation_act':
            lev['topology']['edges'][1]['text'] = '갈브레나가 별도로 주파수 고정을 확인했다고 말한다.'
        elif kind == 'comparison_condition':
            lev['comparison'][1]['text'] = '갈브레나는 자신이 보석을 잠깐 보관하겠다고 제안한다.'
        elif kind == 'pronoun_target':
            lev['sections'][10]['text'] = lev['sections'][10]['text'].replace('「이 주파수들」', '유실된 일부 주파수')
        elif kind == 'mind_scope':
            lev['edges'][4]['reason'] = '갈브레나는 모든 사람의 마음의 바다를 레비아탄이 만든다고 설명한다.'

    cases = [
        ('valid_quote_wrong_speaker', lambda d: quote(d).update(speaker='체이스')),
        ('conditional_predicate_removed', remove_condition),
        ('remembered_form_target_replaced', wrong_memory),
        ('permission_direction_reversed', reverse_permission),
        ('sample_remit_inflated', inflate_sample),
        ('editor_added_ellipsis', wrong_setting_quote),
        ('quest_hash_changed', lambda d: quote(d).update(source_sha256='0' * 64)),
        ('valid_quote_wrong_scene', lambda d: quote(d).update(scene=1)),
        ('revival_proposal_as_accomplished_fact', revival_as_fact),
        ('delivery_plan_as_completed_transfer', delivery_as_completed),
        ('unsupported_sea_to_land_route', lambda d: source_review_mutation(d, 'sea_route')),
        ('source_future_tense_as_current_outcome', lambda d: source_review_mutation(d, 'future_tense')),
        ('invented_frequency_confirmation_act', lambda d: source_review_mutation(d, 'confirmation_act')),
        ('storage_comparison_condition_removed', lambda d: source_review_mutation(d, 'comparison_condition')),
        ('ambiguous_pronoun_target_fixed', lambda d: source_review_mutation(d, 'pronoun_target')),
        ('mind_sea_scope_generalized', lambda d: source_review_mutation(d, 'mind_scope')),
        ('passive_ring_purpose_as_confirmed_installer', assign_ring_installer),
    ]
    results = []
    for name, mutate in cases:
        data = copy.deepcopy(inputs)
        mutate(data)
        result = audit.verify(data)
        results.append({'name': name, 'status': 'PASS' if result['status'] == 'FAIL' else 'FAIL',
                        'detectedErrors': [e['error'] for e in result['errors']]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--self-test', action='store_true', help='run in-memory source and semantic corruption canaries')
    args = parser.parse_args()
    inputs = {name: json.loads((args.site / 'settings' / name).read_text(encoding='utf-8'))
              for name in ('atlas.json', 'npc-people.json', 'editorial.json', 'directory-discovery.json')}
    audit = SourceAudit(args.site)
    report = audit.verify(inputs)
    if args.self_test and report['status'] == 'PASS':
        report['selfTests'] = self_tests(audit, inputs)
        if any(test['status'] != 'PASS' for test in report['selfTests']):
            report['status'] = 'FAIL'
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
