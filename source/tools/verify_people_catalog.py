"""Read-only QA of people cards, NPC classification and exact source evidence."""
import argparse
import hashlib
import json
import re
import sys
from html import escape
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

sys.dont_write_bytecode = True
from verify_original_rendering import visible_text, load_curated_sources

BASE = '/wuwa-quests'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.links, self.scripts, self.cards, self.quotes, self.text = [], [], [], [], [], []
        self.card = self.quote = None
        self.images, self.figures, self.figure = [], [], None
        self.caption = None
        self.heading = None
        self.ids = []
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class','').split())
        flags = set()
        node = {'tag':tag, 'attrs':a, 'parent':self.stack[-1][2] if self.stack else None,
                'text':[], 'children':[]}
        if node['parent'] is not None:
            node['parent']['children'].append(node)
        self.nodes.append(node)
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'script' and a.get('src'):
            self.scripts.append(a['src'])
        if tag == 'a':
            self.links.append(a.get('href',''))
            if 'lore-person-card' in classes:
                self.card = {'href':a.get('href'), 'name':[]}
                self.cards.append(self.card)
                flags.add('card')
        if tag == 'h3' and self.card is not None:
            self.heading = self.card['name']
            flags.add('heading')
        if tag == 'blockquote':
            self.quote = []
            self.quotes.append(self.quote)
            flags.add('quote')
        if tag == 'figure':
            self.figure = {'images': [], 'caption': [], 'links': []}
            self.figures.append(self.figure)
            flags.add('figure')
        if tag == 'img':
            self.images.append(a)
            if self.figure is not None:
                self.figure['images'].append(a)
        if tag == 'a' and self.figure is not None:
            self.figure['links'].append(a.get('href', ''))
        if tag == 'figcaption' and self.figure is not None:
            self.caption = self.figure['caption']
            flags.add('caption')
        if tag not in VOID:
            self.stack.append((tag,flags,node))

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self,tag):
        for n in range(len(self.stack)-1,-1,-1):
            if self.stack[n][0] == tag:
                flags = set().union(*(x[1] for x in self.stack[n:]))
                del self.stack[n:]
                if 'card' in flags: self.card = None
                if 'heading' in flags: self.heading = None
                if 'quote' in flags: self.quote = None
                if 'caption' in flags: self.caption = None
                if 'figure' in flags: self.figure = None
                break

    def handle_data(self,text):
        self.text.append(text)
        if self.heading is not None: self.heading.append(text)
        if self.quote is not None: self.quote.append(text)
        if self.caption is not None: self.caption.append(text)
        if not any(n[0] in ('script','style') for n in self.stack):
            for _,_,node in self.stack:
                node['text'].append(text)

    @staticmethod
    def within(node,parent):
        while node is not None:
            if node is parent: return True
            node = node['parent']
        return False

    def image_cards(self,url):
        """The image and its original/provenance links share one CVA item.

        Legacy figure is the fallback boundary. A page-wide link or neighbouring
        card cannot satisfy this association, and duplicate rendered images
        remain separate results for the caller's exact-one assertion.
        """
        result = []
        for image in self.nodes:
            if image['tag']!='img' or image['attrs'].get('src')!=url: continue
            parent,figure = image['parent'],None
            while parent is not None and 'data-cva-item-index' not in parent['attrs']:
                if parent['tag']=='figure' and figure is None: figure=parent
                parent=parent['parent']
            boundary=parent or figure
            if boundary is None: continue
            children=[n for n in self.nodes if self.within(n,boundary)]
            captions=[n for n in children if n['tag']=='figcaption' or
                      {'sc-item-title','cva-item-title'} & set(n['attrs'].get('class','').split())]
            result.append({'images':[n['attrs'] for n in children if n['tag']=='img'],
                           'caption':[''.join(n['text']) for n in captions],
                           'links':[n['attrs'].get('href','') for n in children if n['tag']=='a']})
        return result

    def local_role(self,name,kind):
        # Kind and name must be adjacent children of the same endpoint/title,
        # rather than separate occurrences anywhere in the page or JSON model.
        for node in self.nodes:
            if node['tag']!='small' or ''.join(node['text'])!=kind or node['parent'] is None: continue
            siblings=node['parent']['children']
            index=next(i for i,n in enumerate(siblings) if n is node)
            if index+1<len(siblings):
                following=siblings[index+1]
                if following['tag'] in ('a','strong') and ''.join(following['text'])==name:
                    return True
        return False


def gather(value):
    if isinstance(value,list):
        for item in value: yield from gather(item)
    elif isinstance(value,dict):
        if value.get('quest_id') and value.get('quote'):
            yield value
        elif value.get('source_text_sha256') and value.get('id'):
            yield value
        else:
            for item in value.values(): yield from gather(item)


def audit_relation_structures(clusters, records, aliases, quest_cache, require, stats):
    """Check source-audited membership/inclusion, independently of its layout.

    A common endpoint is not sufficient to claim affiliation. Each authored
    structural tag below has a named original clause and preserves the audited
    member-to-group or container-to-contained direction. New tags require a
    corresponding original audit, rather than a geometry or keyword guess.
    """
    setting = lambda ident, field, literal: ('setting', ident, field, literal)
    quest = lambda ident, scene, speaker, literal, context='': ('quest', ident, scene, speaker, literal, context)
    proofs = {
        'jinzhou': setting('로딩_세계관_도움말:loadingtipstext:1009', 'content',
                           '광활한 황룡에는 하나의 수도와 6개의 주(州)가 있다. 금주는 그중 가장 늦게 세워진 주로'),
        'phoebe': setting('인물_프로필_공명기록:favorroleinfo:1506', 'info', '깊은 바다 수도회의 성직자 페비'),
        'capitoline': setting('로딩_세계관_도움말:loadingtipstext:200601', 'content', '리나시타에 속한 일곱 언덕 중심지'),
        'dragon-grave': setting('로딩_세계관_도움말:loadingtipstext:200607', 'content', '이곳은 일곱 언덕의 유명한 시련의 땅'),
        'boundary-mountains': setting('로딩_세계관_도움말:loadingtipstext:200605', 'content', '일곱 언덕 변경 지대에 위치한 높은 산맥'),
        'xuanfang': setting('로딩_세계관_도움말:loadingtipstext:201404', 'content', '몽주의 관할을 받는 공중 기관성'),
        'mongju': setting('인물_프로필_공명기록:favorroleinfo:1307', 'info', '황룡 몽주의 도사'),
        'axion': quest('140000004', 33, '기염', '전쟁을 대표하는 명식, 「더 엑시온」'),
        'leviathan': setting('잔상_생태:monsterinfo:340000200', 'discovered_description', '리나시타의 문명에 뿌리내린 명식'),
        'aleph': setting('잔상_생태:monsterinfo:340000271', 'discovered_description', '명식 알레프-원의 창조물'),
        'scar': setting('잔상_생태:monsterinfo:330000100', 'undiscovered_description', '잔성회 간부의 일원'),
        'phrolova': setting('인물_프로필_공명기록:favorroleinfo:1608', 'info', '잔성회 간부이자'),
        'calcharo': setting('인물_음성대사:favorword:130122', 'content', '유령사냥단의 단장 카카루다'),
        'carlotta': setting('인물_프로필_공명기록:favorroleinfo:1107', 'info', '몬텔리 가문의 둘째 아가씨'),
        'cantarella': setting('인물_프로필_공명기록:favorroleinfo:1607', 'info', '현 피살리아 가문의 가주'),
        'christoforo': quest('121000038', 36, '카르티시아', '잔성회의 극작가 크리스토포로'),
        'fenrico': quest('114000027', 18, '알렉시스 사제', '펜리코 수좌이십니다',
                         '[대화ID 1] 알렉시스 사제: 귀한 손님, 수도회에는 무슨 일이십니까?'),
    }
    audited = (
        ('regions/jinzhou', 'edge:5', 'membership', '금주', '황룡', 'jinzhou'),
        ('regions/rinascita', 'edge:4', 'membership', '페비', '깊은 바다 수도회', 'phoebe'),
        ('regions/seven-hills', 'edge:0', 'membership', '카피톨리누스 언덕 도시', '일곱 언덕', 'capitoline'),
        ('regions/seven-hills', 'edge:1', 'membership', '석룡의 무덤', '일곱 언덕', 'dragon-grave'),
        ('regions/seven-hills', 'edge:2', 'membership', '경계의 산', '일곱 언덕', 'boundary-mountains'),
        ('regions/mongju', 'edge:4', 'membership', '현방성', '몽주', 'xuanfang'),
        ('regions/huanglong', 'edge:0', 'membership', '금주', '황룡', 'jinzhou'),
        ('regions/huanglong', 'edge:1', 'membership', '몽주', '황룡', 'mongju'),
        ('cosmology/threnodians', 'edge:0', 'membership', '더 엑시온', '명식', 'axion'),
        ('cosmology/threnodians', 'edge:1', 'membership', '레비아탄', '명식', 'leviathan'),
        ('cosmology/the-axion', 'edge:0', 'membership', '더 엑시온', '명식', 'axion'),
        ('factions/fractsidus', 'edge:0', 'containment', '잔성회', '스카', 'scar'),
        ('factions/fractsidus', 'edge:1', 'containment', '잔성회', '플로로', 'phrolova'),
        ('factions/ghost-hounds', 'edge:1', 'membership', '카카루', '유령사냥단', 'calcharo'),
        ('factions/montelli', 'edge:0', 'membership', '카를로타', '몬텔리 가문', 'carlotta'),
        ('factions/fisalia', 'edge:0', 'membership', '칸타렐라', '피살리아 가문', 'cantarella'),
        ('people/scar', 'edge:0', 'membership', '스카', '잔성회', 'scar'),
        ('people/christoforo', 'edge:0', 'membership', '크리스토포로', '잔성회', 'christoforo'),
        ('people/fenrico', 'edge:0', 'membership', '펜리코', '깊은 바다 수도회', 'fenrico'),
        ('cosmology/threnodians', 'threnodian-branches/threnodian-axion', 'containment', '명식', '더 엑시온', 'axion'),
        ('cosmology/threnodians', 'threnodian-branches/threnodian-branches-edge-0', 'containment', '명식', '레비아탄', 'leviathan'),
        ('cosmology/threnodians', 'threnodian-branches/threnodian-aleph', 'containment', '명식', '알레프-원', 'aleph'),
        ('factions/fractsidus', 'fractsidus-structure/org-scar', 'containment', '잔성회', '스카', 'scar'),
        ('factions/fractsidus', 'fractsidus-structure/org-flo', 'containment', '잔성회', '플로로', 'phrolova'),
    )
    expected = {(cid, location):(structure, actor, target, proofs[proof])
                for cid, location, structure, actor, target, proof in audited}
    actual = {}
    for cid, cluster in clusters.items():
        names = {n['name'] for n in cluster['nodes']}
        for i, edge in enumerate(cluster.get('edges', [])):
            actual[(cid, 'edge:'+str(i))] = edge, edge['a'], edge['b'], names
        for topology in [cluster.get('topology')]+cluster.get('views', []):
            if not topology: continue
            nodes = {n['id']:n['name'] for n in topology['nodes']}
            for edge in topology['edges']:
                location = topology['id']+'/'+edge['id']
                require((cid, location) not in actual, 'duplicate structural relation location', cluster=cid, location=location)
                actual[(cid, location)] = edge, nodes.get(edge['from']), nodes.get(edge['to']), set(nodes.values())
    for (cid, location), (edge, actor, target, names) in actual.items():
        stats['structureRelationCandidates'] += 1
        if 'structure' not in edge: continue
        structure = edge['structure']
        require(structure in ('membership', 'containment'), 'unknown relation structure', cluster=cid, location=location)
        require(edge.get('kind') not in ('reading', 'inference') and edge.get('claimKind')!='inference',
                'editorial connection has a factual structure', cluster=cid, location=location)
        require(actor in names and target in names and actor!=target,
                'structural relation lacks distinct declared endpoints', cluster=cid, location=location)
        require(bool(edge.get('refs')), 'structural relation lacks original proof', cluster=cid, location=location)
        require((cid, location) in expected, 'structure lacks a source-audited direction and scope', cluster=cid, location=location)
        stats['typedRelationStructures'] += 1
        stats['structure_'+str(structure)] += 1
    for (cid, location), (structure, actor, target, proof) in expected.items():
        edge, actual_actor, actual_target, _ = actual.get((cid, location), ({}, None, None, set()))
        require((edge.get('structure'), actual_actor, actual_target)==(structure, actor, target),
                'source-backed structure or member/group direction differs', cluster=cid, location=location)
        if proof[0]=='setting':
            _, ident, field, literal = proof
            value = next((v for v in records.get(ident, {}).get('values', []) if v['field']==field), None)
            refs = [r for r in edge.get('refs', []) if aliases.get(r.get('id'), r.get('id'))==ident and r.get('field')==field]
            require(value is not None and literal in value['text'] and
                    any(literal in r.get('excerpt', '') and
                        r.get('source_text_sha256')==hashlib.sha256(value['raw'].encode()).hexdigest() for r in refs),
                    'structure lost its exact original membership/inclusion clause', cluster=cid, location=location, source=ident)
        else:
            _, ident, scene, speaker, literal, context = proof
            digest, scenes = quest_cache.get(ident, ('', {}))
            refs = [r for r in edge.get('refs', []) if r.get('quest_id')==ident and r.get('scene')==scene and r.get('speaker')==speaker]
            require(literal in scenes.get(scene, '') and context in scenes.get(scene, '') and
                    any(literal in r.get('quote', '') and r.get('source_sha256')==digest for r in refs),
                    'structure lost its exact attributed scene or institutional context', cluster=cid, location=location, quest=ident)
        stats['structureOriginalCanaries'] += 1


def canonical_topology_urls(index, atlas, npc, book):
    """Reconstruct approved entity destinations from the original registries.

    generate-atlas changes only a topology node's URL after resolving profile,
    dossier, alias, glossary and named-original destinations in this order.
    Expected links must come from these inputs, not from the emitted graph
    whose links this check is intended to verify.
    """
    authored = [(group,c) for group in ('regions','sentinels','cosmology','factions','people')
                for c in atlas[group]] + [('people',c) for c in npc['people']]
    links = {p['name']:'/people/'+str(p['id'])+'.html' for p in index['characters']}
    for group,c in authored:
        links[c['title'].split(' · ')[0]] = '/'+group+'/'+c['id']+'.html'
    for alias in atlas.get('entityAliases',[]):
        if not alias.get('refs') or links.get(alias['targetName'])!=alias['targetUrl']:
            raise ValueError('invalid source-backed topology alias target: '+alias['name'])
        links[alias['name']] = alias['targetUrl']
    for i,concept in enumerate(book['concepts']):
        links.setdefault(concept['name'],'/concepts/'+str(i)+'.html')
    for _,c in authored:
        proofs = list(gather(c))
        for node in c['nodes']:
            name = node['name']
            if name not in links and any(name in (r.get('excerpt') or r.get('quote') or '') or
                                         name in (r.get('label') or r.get('title') or '') for r in proofs):
                links[name] = '/entities/'+hashlib.sha256(name.encode()).hexdigest()[:16]+'.html'
    for _,c in authored:
        for node in c['nodes']:
            if node['name'] not in links:
                links[node['name']] = node.get('url')
    if any(not isinstance(route,str) or not route.startswith('/') or route.startswith('//')
           for route in links.values()):
        raise ValueError('original topology registry has an invalid local entity destination')
    return {name:BASE+route for name,route in links.items()}


def audited_topology_nodes(topology, canonical_urls):
    # All original fields remain exact, including id/name/kind/layer/focus/
    # scale and any additional authored fields. Only the known canonical URL
    # replacement (or addition) is allowed; undeclared subjects retain theirs.
    return [{**node, 'url':canonical_urls[node['name']]} if node['name'] in canonical_urls else dict(node)
            for node in topology['nodes']]


def audit_relation_semantics(site, atlas, npc, records, aliases, require, stats):
    """Source-only regressions for actor/target, modality and editorial links.

    Rendering cannot prove whether a sentence represents an actual relation.
    These canaries retain the specific original clauses found in the full
    registry audit; every source proof is also checked independently below.
    """
    clusters = {group+'/'+c['id']:c for group in ('regions','sentinels','cosmology','factions','people')
                for c in atlas[group]}
    clusters.update({'people/'+c['id']:c for c in npc['people']})
    quest_cache = {}
    for ref in gather([atlas, npc]):
        if ref.get('quest_id'):
            ident = str(ref['quest_id'])
            if ident not in quest_cache:
                raw = (site/'originals'/(ident+'.txt')).read_bytes()
                text = raw.decode('utf-8-sig')
                starts = list(re.finditer(r'^장면 (\d+):',text,re.M))
                scenes = {int(m[1]):text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)]
                          for i,m in enumerate(starts)}
                quest_cache[ident] = hashlib.sha256(raw).hexdigest(), scenes
            digest, scenes = quest_cache[ident]
            require(digest==ref['source_sha256'] and ref['quote'] in scenes.get(ref['scene'],''),
                    'registry quest proof differs from exact scene',quest=ident,scene=ref['scene'])
            stats['registryQuestProofs'] += 1
        else:
            ident = aliases.get(ref['id'],ref['id'])
            record = records.get(ident,{})
            value = next((v for v in record.get('values',[]) if v['field']==ref['field']),None)
            valid = value is not None and hashlib.sha256(value['raw'].encode()).hexdigest()==ref['source_text_sha256']
            require(valid and ref['excerpt'] in (value or {}).get('text',''),
                    'registry setting proof differs from exact field',source=ident,field=ref['field'])
            if valid and ref['excerpt'] in value['text']:
                end = value['text'].index(ref['excerpt'])+len(ref['excerpt'])
                require(end==len(value['text']) or value['text'][end]=='\n' or
                        ref['excerpt'].endswith(('.', '!', '?','。','！','？')),
                        'registry excerpt stops inside a source line',source=ident,field=ref['field'])
            stats['registrySettingProofs'] += 1
    audit_relation_structures(clusters, records, aliases, quest_cache, require, stats)
    for cid, index, actor, verb, target, source, field, literal in (
            ('regions/jinzhou',4,'기염','지휘한다','야귀군','잔상_생태:monsterinfo:310000690','discovered_description',
             '이 모든 부대는 금주 야귀 장군 기염의 지휘 아래 움직인다'),
            ('regions/huanglong',1,'몽주','황룡에 속한다','황룡','인물_프로필_공명기록:favorroleinfo:1307','info',
             '황룡 몽주의 도사'),
            ('cosmology/solaris',0,'로야 빙원','제1차 비명 이후 극점이 되었다','솔라리스','로딩_세계관_도움말:loadingtipstext:201204','content',
             '제1차 비명으로 인해 자극이 변하며, 이곳은 새로운 솔라리스의 극점이 되면서')):
        edge = clusters[cid]['edges'][index]
        require((edge['a'],edge['verb'],edge['b'])==(actor,verb,target) and
                any(aliases.get(r.get('id'),r.get('id'))==source and r.get('field')==field and
                    literal in r.get('excerpt','') for r in edge['refs']),
                'source-backed actor predicate or target regression',cluster=cid,index=index)
        stats['semanticActorCanaries'] += 1
    for cid,index in (('regions/new-federation',1),('factions/huaxu',0),('factions/ghost-hounds',3),
                      ('people/valentina',1)):
        require(clusters[cid]['edges'][index].get('kind')=='reading',
                'editorial record connection presented as an explicit relation',cluster=cid,index=index)
        stats['semanticReadingCanaries'] += 1
    for cid,index,actor,verb,target,quest,scene,speaker,literal in (
            ('people/fractsidus-chairman',0,'잔성회 회장','명식 공명자 확보를 조직의 목표로 제시한다','잔성회',
             '121000040',28,'잔성회 회장','잔성회가 완전하고 제어할 수 있는 명식의 공명자를 손에 넣을 때까지'),
            ('people/fractsidus-chairman',1,'잔성회 회장','잔성회의 창조물이라고 주장한다','데니아',
             '121000040',28,'잔성회 회장','데니아는 원래 잔성회의 창조물이었는걸요'),
            ('people/fractsidus-chairman',3,'잔성회 회장','정신을 그릇에 결합할 대상으로 삼는다','히유키',
             '121000040',28,'잔성회 회장','훌륭한 그릇을 만든 다음, 거기에 타오르는 벚꽃의 무녀의 정신을 더하면'),
            ('people/antonio',0,'안토니오','가문의 개인 단말기 연구를 설명한다','몬텔리 가문',
             '114000027',13,'안토니오','우리 몬텔리 가문은 「개인 단말기」에 대한 연구를 시작한 거고'),
            ('people/alexis',2,'알렉시스 사제','천상의 나라 건설을 조직의 지향으로 설명한다','깊은 바다 수도회',
             '114000027',18,'알렉시스 사제','수호신의 뜻 아래 사람들을 인도하고 단결시키며 천상의 나라, 행복한 땅을 만드는 것')):
        edge = clusters[cid]['edges'][index]
        require((edge['a'],edge['verb'],edge['b'])==(actor,verb,target) and edge.get('kind')!='reading' and
                any(r.get('quest_id')==quest and r.get('scene')==scene and r.get('speaker')==speaker and
                    literal in r.get('quote','') for r in edge['refs']),
                'NPC relation object or attributed speaker regression',cluster=cid,index=index)
        stats['semanticNpcCanaries'] += 1
    investigation = clusters['people/valentina']['edges'][1]
    require(any(r.get('quest_id')=='880000044' and r.get('scene')==1 and r.get('speaker')=='발렌티나' and
                'A팀은 바로 데이터 사전 처리 모드' in r.get('quote','') for r in investigation['refs']) and
            any(r.get('quest_id')=='880000044' and r.get('scene')==1 and r.get('speaker')=='발렌티나' and
                '검은 해안은 이 문제를 최우선 프로젝트로 지정' in r.get('quote','') for r in investigation['refs']),
            'editorial investigation route lost either actor instruction or institutional scope')
    threnodians = clusters['cosmology/threnodians']
    attempt = threnodians['sections'][4]
    require('봉인하려 했다고' in attempt['text'] and '봉인한 재난' not in threnodians['summary'] and
            any(r.get('id')=='로딩_세계관_도움말:loadingtipstext:201206' and
                '재난을 게이트 너머로 봉인하려 했다' in r.get('excerpt','') for r in attempt['refs']),
            'planned seal changed into a completed seal')
    cycle = clusters['cosmology/frequency']['topology']
    require('깊은 바다 실험장' in cycle['title'] and '깊은 바다 실험장 기록' in cycle['edges'][0]['text'],
            'regional frequency cycle generalized into a world law')
    for item in (clusters['regions/jinzhou']['bridge'],clusters['people/scar']['bridge'],
                 clusters['factions/fractsidus']['comparison'][0]):
        require(any(r.get('quest_id')=='139000030' and r.get('scene')==7 and r.get('speaker')=='양양'
                    for r in item['refs']), 'Yangyang attribution has no dialogue proof')
    stats['semanticModalityCanaries'] += 2
    stats['semanticSpeakerCanaries'] += 3



def check_rendered_relation(parsed, claim, evidence, candidate_suffixes):
    """One source proof must retain the reason, every quote and its own URL."""
    expected_reason = re.sub(r'\s+', ' ', visible_text(claim['text'])).strip()
    candidates = [n for n in parsed.nodes if n['tag']=='details' and any(
        n['attrs'].get('id','').endswith('-edge-'+suffix) for suffix in candidate_suffixes)]
    for node in candidates:
        paragraphs = [re.sub(r'\s+', ' ', ''.join(n['text'])).strip() for n in node['children'] if n['tag']=='p']
        descendants = [n for n in parsed.nodes if Page.within(n,node)]
        quotes = [''.join(n['text']) for n in descendants if n['tag']=='blockquote']
        links = [n['attrs'].get('href','') for n in descendants if n['tag']=='a']
        if expected_reason in paragraphs and all(visible_text(e['quote']) in quotes and e['url'] in links for e in evidence):
            return True
    return False



def rendered_relation_self_test():
    claim = {'text':'관계 요약'}
    evidence = [{'quote':'가 > 나, 「원문」','url':'/original.html#row-1'}]
    html = '<details id="supplemental-edge-relation-0"><summary>근거</summary><p>관계 요약</p><blockquote>가 &gt; 나, 「원문」</blockquote><a href="/original.html#row-1">원문</a></details>'
    def accepted(value):
        page = Page()
        page.feed(value)
        try:
            result = check_rendered_relation(page, claim, evidence, ['relation-0'])
        except ValueError:
            return False
        return result is not False
    if not accepted(html):
        raise ValueError('Valid relation disclosure rejected')
    mutations = {
        'HTML_REASON_REMOVED': html.replace('<p>관계 요약</p>', ''),
        'HTML_REASON_CHANGED': html.replace('관계 요약','변형 요약'),
        'HTML_QUOTE_CHANGED': html.replace('가 &gt; 나','가 &lt; 나'),
        'HTML_SOURCE_LINK_CHANGED': html.replace('/original.html#row-1','/foreign.html'),
        'HTML_RELATION_ID_CHANGED': html.replace('edge-relation-0','edge-foreign'),
        'HTML_QUOTE_OUTSIDE_PROOF': html.replace('<blockquote>가 &gt; 나, 「원문」</blockquote>','')+'<blockquote>가 &gt; 나, 「원문」</blockquote>'}
    for name, value in mutations.items():
        if accepted(value):
            raise ValueError('Contaminated relation disclosure accepted: '+name)
    return list(mutations)


def main(dist):
    site = Path(__file__).resolve().parents[2]
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    index, atlas = load(site/'settings/index.json'), load(site/'settings/atlas.json')
    npc = load(site/'settings/npc-people.json')
    book = load(site/'settings/editorial.json')
    canonical_urls = canonical_topology_urls(index,atlas,npc,book)
    people = atlas.get('people',[]) + npc['people']
    records = {}
    for path in (site/'settings').glob('records-*.json'): records.update(load(path))
    entries = {e['id']:e for e in index['entries']}
    aliases = index.get('aliases',{})
    errors, stats, cache = [], Counter(), {}
    stats['relationHtmlMutationRejections'] = len(rendered_relation_self_test())
    def require(condition,error,**context):
        if not condition: errors.append({'error':error,**context})
    audit_relation_semantics(site,atlas,npc,records,aliases,require,stats)
    try:
        curated = load_curated_sources(site,dist,index)
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as error:
        errors.append({'error':'invalid generated curated source routing map','detail':str(error)})
        curated = dict(index['curated_sources'])
    def page(relative):
        if relative not in cache:
            path = dist/relative
            require(path.is_file(),'missing page',page=relative)
            parsed = Page()
            if path.is_file(): parsed.feed(path.read_text(encoding='utf-8'))
            cache[relative] = parsed
        return cache[relative]
    directory = page('people.html')
    # Bind the HTML to its current filter implementation so older cached JS
    # cannot silently interpret the new multi-region card metadata incorrectly.
    filter_bytes = (site/'source/public/lore/people.js').read_bytes()
    filter_bytes = filter_bytes.decode('utf-8').replace('\r\n','\n').encode('utf-8')
    filter_version = hashlib.sha256(filter_bytes).hexdigest()[:12]
    filter_scripts = [urlsplit(src) for src in directory.scripts
                      if urlsplit(src).path == BASE+'/lore/people.js']
    require(len(filter_scripts)==1,'people filter script count differs',actual=len(filter_scripts))
    if len(filter_scripts)==1:
        require(parse_qs(filter_scripts[0].query).get('v')==[filter_version],
                'people filter script cache version differs',expected=filter_version,
                actual=parse_qs(filter_scripts[0].query).get('v'))
    expected = [(p['name'],BASE+'/people/'+str(p['id'])+'.html') for p in index['characters']]
    expected += [(p['title'],BASE+'/people/'+p['id']+'.html') for p in people]
    actual = [(''.join(p['name']),p['href']) for p in directory.cards]
    require(Counter(actual)==Counter(expected),'people cards differ',expected=len(expected),actual=len(actual),
            missing=list((Counter(expected)-Counter(actual)).elements()),extra=list((Counter(actual)-Counter(expected)).elements()))
    require(len({url for _,url in expected})==len(expected),'duplicate person URL in merged inputs')
    require(len({p['id'] for p in people})==len(people),'duplicate atlas NPC ID')
    require(any(p['id']=='scar' for p in people),'scar missing from people')
    require(any(p['id']=='ab' for p in people),'Ab missing from canonical people inputs')
    require(not any(p['id']=='scar' for p in atlas['factions']),'scar remains a faction')
    require(BASE+'/factions/scar.html' not in page('factions.html').links,'scar remains in faction directory')
    old = page('factions/scar.html')
    require(BASE+'/people/scar.html' in old.links,'scar legacy route lacks canonical link')
    old_path = dist/'factions/scar.html'
    old_html = old_path.read_text(encoding='utf-8') if old_path.exists() else ''
    require("location.replace('/wuwa-quests/people/scar.html'+location.search+location.hash)" in old_html,
            'scar legacy route does not preserve query and fragment')
    graph = load(dist/'reading-data/graph.json')
    entities = {e['name']:e for e in graph['entities']}
    clusters = {c['id']:c for c in graph['clusters']}
    quests = {}
    def source_quest(id):
        if id not in quests:
            raw = (site/'originals'/(id+'.txt')).read_bytes()
            text = raw.decode('utf-8')
            starts = list(re.finditer(r'^장면 (\d+):',text,re.M))
            scenes = {int(m[1]):text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)] for i,m in enumerate(starts)}
            quests[id] = (hashlib.sha256(raw).hexdigest(),scenes)
        return quests[id]
    evidence_tuples = set()
    for person in people:
        name = person['title'].split(' · ')[0]
        relative = 'people/'+person['id']+'.html'
        parsed = page(relative)
        if person in npc['people']:
            legacy_slug = hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]
            legacy = page('entities/'+legacy_slug+'.html')
            require(BASE+'/'+relative in legacy.links,'NPC legacy entity route lacks canonical link',person=name)
            legacy_path = dist/'entities'/f'{legacy_slug}.html'
            legacy_html = legacy_path.read_text(encoding='utf-8') if legacy_path.exists() else ''
            require('location.search+location.hash' in legacy_html,'NPC legacy route drops reading state',person=name)
        entity = entities.get(name,{})
        require(entity.get('kind')=='인물' and entity.get('url')==BASE+'/'+relative,
                'NPC graph entity classification or URL differs',person=name,entity=entity)
        require('people/'+person['id'] in clusters,'NPC graph cluster missing',person=name)
        quotes = [''.join(x) for x in parsed.quotes]
        full_text = ''.join(parsed.text)
        refs = list(gather(person))
        require(bool(refs),'NPC has no primary evidence',person=name)
        for group in ('sections','edges','paragraphs','comparison'):
            for item in person.get(group,[]):
                require(bool(item.get('refs')),'NPC claim lacks evidence references',person=name,group=group,
                        title=item.get('title') or item.get('verb'))
                if group=='comparison' and item.get('speaker'):
                    actual_speakers = {r['speaker'] for r in gather(item) if r.get('quest_id') and r.get('speaker')}
                    require(all(s in item['speaker'] for s in actual_speakers),
                            'comparison attribution differs from source speakers',person=name,title=item.get('title'),
                            attribution=item['speaker'],sourceSpeakers=sorted(actual_speakers))
        for item in person.get('timeline',{}).get('items',[]):
            require(bool(item.get('refs')),'NPC event lacks evidence references',person=name,title=item.get('title'))
        qrefs = [r for r in refs if r.get('quest_id')]
        if name=='아브':
            require({'880000013','114000026','140000011','158800019'}.issubset({str(r['quest_id']) for r in qrefs}),
                    'Ab dossier omits major source contexts')
            require(any(r.get('speaker')=='"쪼꼬미"' and '이 이름으로 할래' in r.get('quote','') for r in qrefs),
                    'Ab chosen-name primary evidence missing')
            require(any(r.get('speaker')=='양양' and '공생' in r.get('quote','') for r in qrefs),
                    'Ab symbiosis attribution missing')
            require(any(r.get('speaker')=='크리스토포로' and '될지도' in r.get('quote','') for r in qrefs),
                    'Ab identity possibility attribution missing')
        require(any(r.get('speaker')==name or name in r.get('quote','') for r in qrefs) or
                any(name in r.get('label','') for r in refs),
                'NPC identity has no named primary source',person=name)
        if name=='크리스토포로':
            require(any(r.get('speaker')==name and '극작가' in r.get('quote','') for r in qrefs),
                    'Christoforo playwright identity evidence missing')
            require(any('잔성회' in r.get('quote','') and name in r.get('quote','') for r in qrefs),
                    'Christoforo attributed faction evidence missing')
        if name=='펜리코':
            require(any(name in r.get('quote','') and '수좌' in r.get('quote','') for r in qrefs),
                    'Fenrico prelate identity evidence missing')
            require(any(r.get('speaker')==name and r.get('quest_id')!='168000001' for r in qrefs),
                    'Fenrico evidence consists only of the impersonation encounter')
            # The named battle-handbook record is a separate source view of
            # Fenrico. It supplies the verified icon without inventing an NPC
            # portrait or borrowing an image from a matching-name guess.
            ecology_id = '잔상_생태:monsterinfo:340000150'
            ecology_refs = [r for r in refs if r.get('id')==ecology_id and
                            r.get('field')=='discovered_description']
            require(bool(ecology_refs),'Fenrico handbook evidence missing')
            require(any('생태 기록' in s.get('text','') and
                        any(r.get('id')==ecology_id for r in s.get('refs',[]))
                        for s in person.get('sections',[])),
                    'Fenrico handbook narration lacks its own source-labelled section')
            images = load(site/'source/public/game-images/provenance.json')
            mapped = [m for m in images['monsters'] if m.get('sourceId')==ecology_id]
            require(len(mapped)==1,'Fenrico handbook image source mapping differs')
            if len(mapped)==1:
                monster = mapped[0]
                mapping = monster['mapping']
                require(monster['name']==name and mapping['table']=='monsterinfo' and
                        mapping['id']==340000150 and mapping['nameField']==1,
                        'Fenrico image is not the exact named handbook record')
                image = monster['images']['icon']
                require(image['referenceField']==3,
                        'Fenrico icon reference field differs')
                figures = parsed.image_cards(image['url'])
                require(len(figures)==1,'Fenrico exact handbook icon missing or duplicated',
                        expected=image['url'],actual=len(figures))
                for figure in figures:
                    require('게임 도감 이미지 · '+name in ''.join(figure['caption']),
                            'Fenrico battle-handbook icon is labelled as another image role')
                    require(BASE+'/game-images/provenance.json' in figure['links'],
                            'Fenrico handbook image provenance link missing')
                    ecology_slug = curated.get(ecology_id)
                    require(bool(ecology_slug) and
                            BASE+'/sources/'+str(ecology_slug)+'.html' in figure['links'],
                            'Fenrico handbook image original-body link missing')
                    for rendered in figure['images']:
                        if rendered.get('src')!=image['url']: continue
                        require(rendered.get('alt')==name+'의 게임 도감 이미지' and
                                rendered.get('width')==str(image['width']) and
                                rendered.get('height')==str(image['height']),
                                'Fenrico handbook icon accessibility or dimensions differ')
                stats['fenricoHandbookImages'] += len(figures)
            if any(r.get('quest_id')=='168000001' and r.get('speaker')==name for r in qrefs):
                require(any('펜리코로 변신한 창조물' in r.get('quote','') for r in qrefs),
                        'Fenrico impersonation used without explicit identity evidence')
                require('변신' in full_text and '창조물' in full_text,
                        'Fenrico impersonation distinction missing from HTML')
            impersonation = [r for r in qrefs if r.get('quest_id')=='168000001' and
                             ('변신한 창조물' in r.get('quote','') or '변신한 흑조의 창조물' in r.get('quote',''))]
            if impersonation:
                require(all(r.get('speaker')!='펜리코' for r in impersonation),
                        'impersonation explanation attributed to actual Fenrico')
                require('변신' in full_text and '창조물' in full_text,
                        'Fenrico impersonation comparison missing from HTML')
        for ref in refs:
            if ref.get('quest_id'):
                required = ('quest_id','source_sha256','scene','quote','speaker')
                require(all(k in ref for k in required),'incomplete quest evidence tuple',person=name,ref=ref)
                if not all(k in ref for k in required): continue
                id, scene = str(ref['quest_id']),ref['scene']
                require(isinstance(scene,int) and scene>0,'invalid quest scene',person=name,ref=ref)
                digest, scenes = source_quest(id)
                raw = scenes.get(scene,'')
                require(digest==ref['source_sha256'],'quest evidence SHA differs',person=name,quest=id)
                require(ref['quote'] in raw,'quote absent in exact source scene',person=name,quest=id,scene=scene)
                # Check the actual dialogue attribution, not just that a speaker
                # name happens to occur somewhere in the same scene.
                speakers = [m[1].strip() for line in raw.splitlines()
                            if (m:=re.match(r'^\[대화ID [^\]]+\]\s*([^:：]+):\s*(.*)$',line.strip()))
                            and ref['quote'] in m[2]]
                require(ref['speaker'] in speakers,'quote speaker differs from source utterance',
                        person=name,quest=id,scene=scene,expectedSpeaker=ref['speaker'],actualSpeakers=speakers)
                require(ref['speaker'] in full_text,'source speaker missing in NPC HTML',person=name,speaker=ref['speaker'])
                require(BASE+'/quests/'+id+'.html#scene-'+str(scene) in parsed.links,
                        'quest evidence anchor link missing',person=name,quest=id,scene=scene)
                key = (id,scene,ref['speaker'],ref['quote'],ref['source_sha256'])
                stats['questEvidenceReferences'] += 1
            else:
                id = aliases.get(ref['id'],ref['id'])
                value = next((v for v in records.get(id,{}).get('values',[]) if v['field']==ref.get('field')),None)
                require(value is not None,'setting evidence field missing',person=name,record=id,field=ref.get('field'))
                if value is None: continue
                require(hashlib.sha256(value['raw'].encode()).hexdigest()==ref['source_text_sha256'],
                        'setting evidence SHA differs',person=name,record=id)
                quote = ref.get('quote') or ref.get('excerpt','')
                require(bool(quote) and quote in value['text'],'setting quote absent from source',person=name,record=id)
                entry = entries[id]
                slug = curated.get(id)
                target = '/sources/'+slug+'.html' if slug else entry['page']
                require(BASE+target+'#field-'+ref['field'] in parsed.links,
                        'setting field anchor link missing',person=name,record=id,field=ref['field'])
                key = (id,ref['field'],quote,ref['source_text_sha256'])
                stats['settingEvidenceReferences'] += 1
            quote = ref.get('quote') or ref.get('excerpt','')
            require(visible_text(quote) in quotes,'exact displayed quote absent or punctuation changed in HTML blockquote',person=name,quote=quote)
            evidence_tuples.add(key)
        stats['NPCs'] += 1
    # Families share the faction registry with other organizations. Their
    # introductions and relations must remain attached to named game sources,
    # including the distinction between members' views and the whole family.
    faction_specs = [
        ('montelli', '몬텔리 가문', '카를로타', '둘째 아가씨로 소개된다',
         '문서_편지_일기:infodisplay:133002007', '인물_프로필_공명기록:favorroleinfo:1107'),
        ('fisalia', '피살리아 가문', '칸타렐라', '현 가주',
         '문서_편지_일기:infodisplay:133002008', '인물_프로필_공명기록:favorroleinfo:1607'),
    ]
    for ident, name, member, label, document_id, profile_id in faction_specs:
        faction = next((f for f in atlas['factions'] if f['id']==ident), None)
        require(faction is not None, 'named family missing from faction inputs', faction=name)
        if faction is None: continue
        relative = 'factions/'+ident+'.html'
        parsed = page(relative)
        require(BASE+'/'+relative in page('factions.html').links,
                'family missing from faction directory', faction=name)
        require(BASE+'/'+relative in page('regions/rinascita.html').links,
                'family missing from Rinascita reading route', faction=name)
        entity = entities.get(name,{})
        require(entity.get('kind')=='세력' and entity.get('url')==BASE+'/'+relative,
                'family entity classification or URL differs', faction=name, entity=entity)
        require('factions/'+ident in clusters, 'family reading cluster missing', faction=name)
        legacy_slug = hashlib.sha256(name.encode()).hexdigest()[:16]
        legacy = page('entities/'+legacy_slug+'.html')
        require(BASE+'/'+relative in legacy.links,
                'family legacy entity route lacks canonical link', faction=name)
        legacy_path = dist/'entities'/f'{legacy_slug}.html'
        legacy_html = legacy_path.read_text(encoding='utf-8') if legacy_path.exists() else ''
        require('location.search+location.hash' in legacy_html,
                'family legacy route drops reading state', faction=name)
        refs = list(gather(faction))
        source_ids = {r.get('id') for r in refs if r.get('id')}
        require({document_id, profile_id}.issubset(source_ids),
                'family lacks direct document or member profile evidence', faction=name)
        for group in ('sections','edges','comparison'):
            for item in faction.get(group,[]):
                require(bool(item.get('refs')), 'family claim lacks primary evidence',
                        faction=name, group=group, title=item.get('title') or item.get('verb'))
        quotes = [''.join(x) for x in parsed.quotes]
        for ref in refs:
            quote = ref.get('quote') or ref.get('excerpt','')
            if ref.get('quest_id'):
                digest, scenes = source_quest(str(ref['quest_id']))
                raw = scenes.get(ref['scene'],'')
                require(digest==ref['source_sha256'] and quote in raw,
                        'family quest evidence differs', faction=name, ref=ref)
                speakers = [m[1].strip() for line in raw.splitlines()
                            if (m:=re.match(r'^\[대화ID [^\]]+\]\s*([^:：]+):\s*(.*)$',line.strip()))
                            and quote in m[2]]
                require(ref.get('speaker') in speakers,
                        'family utterance attribution differs', faction=name, ref=ref)
                target = BASE+'/quests/'+str(ref['quest_id'])+'.html#scene-'+str(ref['scene'])
                stats['familyQuestEvidenceReferences'] += 1
            else:
                rid = aliases.get(ref['id'],ref['id'])
                value = next((v for v in records.get(rid,{}).get('values',[])
                              if v['field']==ref.get('field')), None)
                require(value is not None, 'family setting evidence field missing',
                        faction=name, record=rid)
                if value is None: continue
                require(hashlib.sha256(value['raw'].encode()).hexdigest()==ref['source_text_sha256']
                        and bool(quote) and quote in value['text'],
                        'family setting quote or source SHA differs', faction=name, record=rid)
                slug = curated.get(rid)
                target = BASE+('/sources/'+slug+'.html' if slug else entries[rid]['page'])+'#field-'+ref['field']
                stats['familySettingEvidenceReferences'] += 1
            require(target in parsed.links, 'family original source anchor link missing',
                    faction=name, target=target)
            require(visible_text(quote) in quotes, 'family displayed original quote differs',
                    faction=name, quote=quote)
        member_entity = entities.get(member,{})
        require(any(rel['from']==member_entity.get('id') and
                    rel['to']==entity.get('id') and rel['label']==label
                    for rel in graph['relations'] if rel['clusterId']=='factions/'+ident),
                'family membership relation direction or role differs', faction=name, member=member)
        if ident=='fisalia':
            require(any(e['a']==name and e['b']=='몬텔리 가문' and
                        '일부 구성원' in e['verb'] and '무관심' in e['reason']
                        for e in faction['edges']),
                    'Fisalia members viewpoint generalized to the whole family')
            require(any(r.get('id')=='인물_이야기:favorstory:160705' for r in refs),
                    'Fisalia current prelate decision source missing')
        stats['familyFactions'] += 1
    # A former name resolves to the same character only when a profile states
    # that identity. This protects the old entity URL without inventing a
    # separate NPC or discarding its original name in quoted game text.
    for alias in atlas.get('entityAliases',[]):
        name, target_name, target_url = alias['name'], alias['targetName'], BASE+alias['targetUrl']
        target_person = next((p for p in index['characters'] if p['name']==target_name), None)
        require(target_person is not None and target_url==BASE+'/people/'+str(target_person['id'])+'.html',
                'character alias target is not a canonical profile person', alias=name)
        entity, canonical = entities.get(name,{}), entities.get(target_name,{})
        require(entity.get('url')==target_url and entity.get('kind')==canonical.get('kind')=='인물',
                'character alias classification or canonical URL differs', alias=name)
        slug = hashlib.sha256(name.encode()).hexdigest()[:16]
        legacy = page('entities/'+slug+'.html')
        require(target_url in legacy.links, 'character alias legacy route lacks canonical link', alias=name)
        legacy_path = dist/'entities'/f'{slug}.html'
        legacy_html = legacy_path.read_text(encoding='utf-8') if legacy_path.exists() else ''
        require('location.search+location.hash' in legacy_html,
                'character alias legacy route drops reading state', alias=name)
        require(bool(alias.get('relation')) and bool(alias.get('refs')),
                'character alias lacks identity relation or primary evidence', alias=name)
        for ref in gather(alias):
            rid = aliases.get(ref['id'],ref['id'])
            value = next((v for v in records.get(rid,{}).get('values',[])
                          if v['field']==ref.get('field')), None)
            require(value is not None, 'character alias source field missing', alias=name)
            if value is None: continue
            require(hashlib.sha256(value['raw'].encode()).hexdigest()==ref['source_text_sha256'] and
                    ref['excerpt'] in value['text'] and name in ref['excerpt'] and target_name in ref['excerpt'],
                    'character alias identity quote or SHA differs', alias=name)
            relative = alias['targetUrl'].removeprefix('/')
            require(visible_text(ref['excerpt']) in ''.join(page(relative).text),
                    'character alias identity source absent from canonical profile page', alias=name)
        stats['profileIdentityAliases'] += 1
    # Every profile character also has a real destination, not merely a card.
    for p in index['characters']: page('people/'+str(p['id'])+'.html')
    # Validate every authored cluster, not only named NPC canaries. Canonical
    # classes and source-local roles serve different purposes and both survive.
    image_manifest = load(site/'source/public/game-images/provenance.json')
    profiles = {p['name']:p for p in index['characters']}
    relation_index = {r['id']:r for r in graph['relations']}
    relation_claims = {c['id']:c for c in graph['claims']}
    relation_evidence = {e['id']:e for e in graph['evidence']}
    authored = [(group,c) for group in ('regions','sentinels','cosmology','factions','people')
                for c in atlas[group]] + [('people',c) for c in npc['people']]
    for group,c in authored:
        cid = group+'/'+c['id']
        cluster = clusters.get(cid,{})
        expected_roles = [{'name':n['name'],'kind':n['kind']} for n in c['nodes']]
        require(cluster.get('nodeKinds')==expected_roles,
                'whole registry local node roles differ',cluster=cid)
        name = c['title'].split(' · ')[0]
        canonical = entities.get(name,{})
        focus_kind = '수호신' if group=='sentinels' else canonical.get('kind')
        require(cluster.get('focusKind')==focus_kind,
                'cluster focus role differs from its category',cluster=cid)
        if group=='sentinels':
            require(canonical.get('kind')==('인물' if name in profiles else '수호신'),
                    'guardian canonical class differs from profile identity',cluster=cid)
        parsed = page(cid+'.html')
        raw_html = (dist/(cid+'.html')).read_text(encoding='utf-8')
        participating = {edge[end] for edge in c.get('edges',[]) for end in ('a','b')}
        for n in c['nodes']:
            entity = entities.get(n['name'],{})
            require(bool(entity) and entity.get('kind')!='설정 대상',
                    'declared entity class lost in whole registry',cluster=cid,name=n['name'])
            if not c.get('topology') and n['name'] in participating:
                require(parsed.local_role(n['name'],n['kind']),
                        'source-local relation role missing in HTML',cluster=cid,name=n['name'],kind=n['kind'])
        for i,edge in enumerate(c.get('edges',[])):
            actual_edge = relation_index.get(cid+'/relation-'+str(i),{})
            require(actual_edge.get('from')==entities.get(edge['a'],{}).get('id') and
                    actual_edge.get('to')==entities.get(edge['b'],{}).get('id') and
                    actual_edge.get('label')==edge['verb'],
                    'whole registry relationship direction or predicate differs',cluster=cid,index=i)
            expected_kind = 'inference' if edge.get('kind')=='reading' else 'attributed' if (
                    edge.get('speaker') or any(r.get('speaker') for r in edge.get('refs',[]))) else 'explicit'
            require(actual_edge.get('kind')==expected_kind,
                    'whole registry relationship attribution or reading kind differs',cluster=cid,index=i)
            require(actual_edge.get('structure')==edge.get('structure'),
                    'whole registry source-backed relationship structure differs',cluster=cid,index=i)
            relation_claim = relation_claims[actual_edge['reasonClaimId']]
            require(relation_claim['text']==edge['reason'], 'whole registry relation reason differs',cluster=cid,index=i)
            relation_proofs = [relation_evidence[eid] for eid in relation_claim['evidenceIds']]
            suffixes = [actual_edge['id']] + [e['id'] for t in [cluster.get('topology'),*(cluster.get('views') or [])]
                                            if t for e in t['edges'] if e['claimId']==actual_edge['reasonClaimId']]
            require(check_rendered_relation(parsed,relation_claim,relation_proofs,suffixes),
                    'authored relation reason/original quotes/own source links absent from HTML proof',cluster=cid,index=i)
            stats['wholeRegistryRelations'] += 1
        source_topologies = [c.get('topology')]+c.get('views',[])
        emitted_topologies = [cluster.get('topology')]+cluster.get('views',[])
        require(len(source_topologies)==len(emitted_topologies),
                'whole registry authored topology count differs',cluster=cid)
        for source_topology, emitted_topology in zip(source_topologies,emitted_topologies):
            if not source_topology:
                require(emitted_topology is None,'unexpected authored topology',cluster=cid)
                continue
            emitted_topology = emitted_topology or {}
            require(source_topology['id']==emitted_topology.get('id') and
                    audited_topology_nodes(source_topology,canonical_urls)==emitted_topology.get('nodes'),
                    'whole registry authored topology identity or node scope differs',cluster=cid)
            source_edges = source_topology['edges']
            emitted_edges = emitted_topology.get('edges',[])
            require(len(source_edges)==len(emitted_edges),
                    'whole registry authored topology relation count differs',cluster=cid)
            for source_edge, emitted_edge in zip(source_edges,emitted_edges):
                require(all(source_edge.get(key)==emitted_edge.get(key)
                            for key in ('id','from','to','label','kind','structure')),
                        'whole registry topology statement direction or structure differs',cluster=cid,
                        topology=source_topology['id'],edge=source_edge['id'])
                topology_claim = relation_claims[emitted_edge['claimId']]
                require(topology_claim['text']==source_edge['text'],
                        'whole registry topology reason differs',cluster=cid,edge=source_edge['id'])
                require(check_rendered_relation(parsed,topology_claim,
                            [relation_evidence[eid] for eid in topology_claim['evidenceIds']], [emitted_edge['id']]),
                        'authored topology reason/original quotes/own source links absent from HTML proof',
                        cluster=cid,topology=source_topology['id'],edge=source_edge['id'])
                stats['wholeRegistryTopologyRelations'] += 1
        person = profiles.get(name)
        if person:
            profile_id = '인물_프로필_공명기록:favorroleinfo:'+str(person['id'])
            source_refs = [ref for ref in gather(c) if aliases.get(ref.get('id'),ref.get('id'))==profile_id]
            asset = next((im for im in image_manifest['people'] if str(im['id'])==str(person['id'])),None)
            if source_refs and asset and asset['images'].get('portrait'):
                image = asset['images']['portrait']
                profile = records.get(profile_id,{})
                require(str(profile.get('role_id'))==str(person['id']) and asset['name']==name and
                        asset['mapping']['table']=='roleinfo' and str(asset['mapping']['id'])==str(person['id']),
                        'whole registry focus image identity differs',cluster=cid)
                figures = parsed.image_cards(image['url'])
                require(len(figures)==1,'exact focus profile image missing or duplicated',cluster=cid,url=image['url'])
                for figure in figures:
                    require('게임 인물 이미지 · '+name in ''.join(figure['caption']) and
                            BASE+'/people/'+str(person['id'])+'.html#field-info' in figure['links'] and
                            BASE+'/game-images/provenance.json' in figure['links'],
                            'focus profile image role or original link differs',cluster=cid)
                    rendered=[im for im in figure['images'] if im.get('src')==image['url']]
                    require(len(rendered)==1 and rendered[0].get('alt')==name+'의 게임 인물 이미지' and
                            rendered[0].get('width')==str(image['width']) and
                            rendered[0].get('height')==str(image['height']),
                            'focus profile image accessibility or actual dimensions differ',cluster=cid)
                for ref in source_refs:
                    value = next((v for v in profile.get('values',[]) if v['field']==ref['field']),None)
                    require(value is not None and hashlib.sha256(value['raw'].encode()).hexdigest()==ref['source_text_sha256']
                            and ref['excerpt'] in value['text'],
                            'focus image profile reference differs from original',cluster=cid)
                stats['wholeRegistryFocusProfileImages'] += 1
        stats['wholeRegistryClusters'] += 1
    stats['wholeRegistryEntities'] = len(entities)
    declared_names = {n['name'] for _,c in authored for n in c['nodes']}
    for concept in book['concepts']:
        entity = entities.get(concept['name'],{})
        require(bool(entity) and entity.get('kind')!='설정 대상',
                'glossary concept classification missing',name=concept['name'])
        if concept['name'] not in declared_names:
            require(entity.get('kind')=='개념',
                    'glossary-only entity classification differs',name=concept['name'])
    for entity in graph['entities']:
        require(entity.get('kind') and entity['kind']!='설정 대상',
                'registered graph entity lacks its source registry class',name=entity['name'])
    stats.update(profilePeople=len(index['characters']),peopleCards=len(actual),uniqueEvidenceTuples=len(evidence_tuples),htmlPages=len(cache),curatedSources=len(curated))
    print(json.dumps({'status':'PASS' if not errors else 'FAIL',**dict(stats),'errorsTotal':len(errors),'errors':errors[:30]},ensure_ascii=False))
    return bool(errors)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',type=Path,default=Path(__file__).resolve().parents[1]/'dist')
    raise SystemExit(main(parser.parse_args().dist.resolve()))
