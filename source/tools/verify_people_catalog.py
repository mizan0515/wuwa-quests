"""Read-only QA of people cards, NPC classification and exact source evidence."""
import argparse
import hashlib
import json
import re
import sys
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
        self.heading = None
        self.ids = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class','').split())
        flags = set()
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
        if tag not in VOID:
            self.stack.append((tag,flags))

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
                break

    def handle_data(self,text):
        self.text.append(text)
        if self.heading is not None: self.heading.append(text)
        if self.quote is not None: self.quote.append(text)


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


def main(dist):
    site = Path(__file__).resolve().parents[2]
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    index, atlas = load(site/'settings/index.json'), load(site/'settings/atlas.json')
    npc = load(site/'settings/npc-people.json')
    people = atlas.get('people',[]) + npc['people']
    records = {}
    for path in (site/'settings').glob('records-*.json'): records.update(load(path))
    entries = {e['id']:e for e in index['entries']}
    aliases = index.get('aliases',{})
    errors, stats, cache = [], Counter(), {}
    def require(condition,error,**context):
        if not condition: errors.append({'error':error,**context})
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
    # Every profile character also has a real destination, not merely a card.
    for p in index['characters']: page('people/'+str(p['id'])+'.html')
    stats.update(profilePeople=len(index['characters']),peopleCards=len(actual),uniqueEvidenceTuples=len(evidence_tuples),htmlPages=len(cache),curatedSources=len(curated))
    print(json.dumps({'status':'PASS' if not errors else 'FAIL',**dict(stats),'errorsTotal':len(errors),'errors':errors[:30]},ensure_ascii=False))
    return bool(errors)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist',type=Path,default=Path(__file__).resolve().parents[1]/'dist')
    raise SystemExit(main(parser.parse_args().dist.resolve()))
