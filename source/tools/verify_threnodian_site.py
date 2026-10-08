"""Read-only source and built-HTML QA for the Threnodian reading experience.

Checks preserved evidence independently of the generator, including the actual
utterance speaker, rendered quotations, destinations and the two Axion views.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
from verify_people_catalog import BASE, Page, gather
from verify_original_rendering import visible_text, load_curated_sources


class LinkedTextPage(Page):
    """Keep anchor ranges in DOM text to detect links inside longer words."""
    def __init__(self):
        super().__init__()
        self.linked_text, self.active_link, self.text_length = [], None, 0

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == 'a':
            self.active_link = {'href': dict(attrs).get('href', ''),
                                'start': self.text_length, 'end': self.text_length}
            self.linked_text.append(self.active_link)

    def handle_data(self, text):
        super().handle_data(text)
        self.text_length += len(text)
        if self.active_link is not None:
            self.active_link['end'] = self.text_length

    def handle_endtag(self, tag):
        if tag == 'a':
            self.active_link = None
        super().handle_endtag(tag)


def source_speakers(scene, quote):
    """Use the people QA's utterance pattern; also accept named screen text."""
    result = set()
    for line in scene.splitlines():
        match = re.match(r'^\[대화ID [^\]]+\]\s*([^:：]+):\s*(.*)$', line.strip())
        if match and quote in match[2]:
            result.add(match[1].strip())
        elif line.startswith('화면 문구: ') and quote in line[len('화면 문구: '):]:
            result.add('화면 문구')
    return result


def main(dist):
    site = Path(__file__).resolve().parents[2]
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    atlas, index = load(site/'settings/atlas.json'), load(site/'settings/index.json')
    errors, stats, pages, quests = [], Counter(), {}, {}
    records = {}
    for path in (site/'settings').glob('records-*.json'):
        records.update(load(path))
    aliases = index.get('aliases', {})
    entries = {entry['id']: entry for entry in index['entries']}

    def require(condition, message, **context):
        if not condition:
            errors.append({'error': message, **context})

    def page(relative):
        if relative not in pages:
            target = dist/relative
            require(target.is_file(), 'missing HTML destination', page=relative)
            parsed = LinkedTextPage()
            if target.is_file():
                parsed.feed(target.read_text(encoding='utf-8'))
            pages[relative] = parsed
        return pages[relative]

    def quest(identifier):
        if identifier not in quests:
            raw = (site/'originals'/(identifier+'.txt')).read_bytes()
            text = raw.decode('utf-8')
            starts = list(re.finditer(r'^장면 (\d+):', text, re.M))
            quests[identifier] = (hashlib.sha256(raw).hexdigest(), {
                int(m[1]): text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)]
                for i, m in enumerate(starts)
            })
        return quests[identifier]

    try:
        curated = load_curated_sources(site, dist, index)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        require(False, 'curated routing map unavailable', detail=str(exc))
        curated = {}

    def source_target(ref):
        if ref.get('quest_id'):
            return BASE+'/quests/'+str(ref['quest_id'])+'.html#scene-'+str(ref['scene'])
        identifier = aliases.get(ref['id'], ref['id'])
        entry = entries.get(identifier, {})
        target = '/sources/'+curated[identifier]+'.html' if identifier in curated else entry.get('page', '')
        return BASE+target+'#field-'+ref['field']

    # This walks every atlas claim, not merely the selected new page. A quote
    # appearing elsewhere in the file cannot excuse a wrong scene or speaker.
    unique = {}
    for ref in gather(atlas):
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
        unique[key] = ref
    for ref in unique.values():
        if ref.get('quest_id'):
            required = ('quest_id', 'scene', 'speaker', 'quote', 'source_sha256')
            require(all(k in ref for k in required), 'incomplete quest evidence', reference=ref)
            if not all(k in ref for k in required):
                continue
            try:
                digest, scenes = quest(str(ref['quest_id']))
            except OSError as exc:
                require(False, 'missing preserved quest', quest=ref['quest_id'], detail=str(exc))
                continue
            scene = scenes.get(ref['scene'], '')
            require(digest == ref['source_sha256'], 'quest SHA differs', quest=ref['quest_id'])
            require(bool(ref['quote']) and ref['quote'] in scene, 'quote missing from exact scene',
                    quest=ref['quest_id'], scene=ref['scene'])
            speakers = source_speakers(scene, ref['quote'])
            require(ref['speaker'] in speakers, 'quote speaker differs from source utterance',
                    quest=ref['quest_id'], scene=ref['scene'], expected=ref['speaker'], actual=sorted(speakers))
            stats['questReferences'] += 1
        else:
            identifier = aliases.get(ref['id'], ref['id'])
            value = next((v for v in records.get(identifier, {}).get('values', [])
                          if v['field'] == ref.get('field')), None)
            require(value is not None, 'missing record field', record=identifier, field=ref.get('field'))
            if value:
                require(hashlib.sha256(value['raw'].encode('utf-8')).hexdigest() == ref['source_text_sha256'],
                        'record field SHA differs', record=identifier, field=ref['field'])
                require(bool(ref.get('excerpt')) and ref['excerpt'] in value['text'],
                        'excerpt missing from original field', record=identifier, field=ref['field'])
            stats['settingReferences'] += 1

    cosmology = {c['id']: c for c in atlas['cosmology']}
    axion = cosmology.get('the-axion')
    require(axion is not None, 'Axion independent body input missing')
    if axion is None:
        print(json.dumps({'status': 'FAIL', 'errorsTotal': len(errors), 'errors': errors}, ensure_ascii=False))
        return 1
    target_url = BASE+'/cosmology/the-axion.html'
    built = page('cosmology/the-axion.html')
    facts = dict(axion.get('facts', []))
    require('명식' in facts.get('분류', '') and '전쟁' in facts.get('분류', ''),
            'Axion classification does not state war Threnodian', facts=facts)
    html_path = dist/'cosmology/the-axion.html'
    html = html_path.read_text(encoding='utf-8') if html_path.is_file() else ''
    fact_blocks = re.findall(r'<dl\b[^>]*class="[^"]*setting-facts[^"]*"[^>]*>(.*?)</dl>', html, re.S)
    require(any('전쟁' in block and '명식' in block for block in fact_blocks),
            'war Threnodian classification absent from rendered facts')
    full_text = ''.join(built.text)
    require('크리스토포로' in full_text and '가능성' in full_text,
            'Leviathan fusion possibility or speaker absent from visible body')

    # Claims based on speech must retain attribution in the editorial input.
    # A game synopsis has an internal numeric speaker ID, so its reader-facing
    # attribution is allowed to identify the synopsis rather than that ID.
    for item in axion.get('sections', [])+axion.get('edges', []):
        refs = list(gather(item))
        require(bool(refs), 'Axion claim has no source evidence', title=item.get('title') or item.get('verb'))
        attribution = item.get('speaker', '')
        for ref in refs:
            speaker = ref.get('speaker', '')
            if not speaker:
                continue
            allowed = speaker in attribution or (speaker.startswith('화자ID ') and '게임 줄거리 요약' in attribution)
            require(allowed, 'editorial speech attribution missing or mismatched',
                    title=item.get('title') or item.get('verb'), speaker=speaker, attribution=attribution)

    selected = [('cosmology', axion), ('cosmology', cosmology['threnodians'])]
    selected += [('regions', c) for c in atlas['regions'] if c['id'] in ('jinzhou', 'mongju')]
    for group, cluster in selected:
        relative = group+'/'+cluster['id']+'.html'
        parsed = page(relative)
        quotes = [''.join(x) for x in parsed.quotes]
        for ref in gather(cluster):
            quote = ref.get('quote') or ref.get('excerpt', '')
            require(visible_text(quote) in quotes, 'exact quote absent or transformed in HTML',
                    page=relative, source=ref.get('quest_id') or ref.get('id'), quote=quote)
            require(source_target(ref) in parsed.links, 'evidence does not link to its original body anchor',
                    page=relative, target=source_target(ref))
            stats['renderedEvidenceChecks'] += 1

    # Check the reader's actual entry paths, including the individual character
    # and playwright bodies. A directory card or an unrelated source page is
    # insufficient to make these references discoverable from their context.
    for relative in ('world.html', 'cosmology.html', 'cosmology/threnodians.html',
                     'regions/jinzhou.html', 'regions/mongju.html',
                     'people/1404.html', 'people/1413.html', 'people/christoforo.html'):
        require(target_url in page(relative).links, 'Axion body not discoverable from related page', page=relative)
    for target in ('people/1404.html', 'people/1413.html', 'people/christoforo.html', 'cosmology/threnodians.html'):
        require(BASE+'/'+target in built.links, 'Axion lacks related canonical body link', target=target)

    try:
        graph = load(dist/'reading-data/graph.json')
    except (OSError, ValueError) as exc:
        require(False, 'built reading graph unavailable', detail=str(exc))
        graph = {'clusters': [], 'claims': [], 'entities': []}
    generated = next((c for c in graph['clusters'] if c['id']=='cosmology/the-axion'), {})
    claims = {c['id']: c for c in graph['claims']}
    topologies = [generated.get('topology')]+generated.get('views', [])
    topologies = [t for t in topologies if t]
    require(len(topologies)>=2, 'two separate Axion relation views missing from built graph')
    for topology in topologies:
        require(topology['id'] in built.ids, 'relation view absent from rendered HTML', view=topology['id'])
        for edge in topology['edges']:
            claim = claims.get(edge.get('claimId'), {})
            require(bool(claim.get('evidenceIds')), 'rendered topology edge has no evidence', edge=edge.get('id'))
            require(topology['id']+'-edge-'+edge['id'] in built.ids,
                    'topology edge lacks visible explanation destination', view=topology['id'], edge=edge['id'])
    cycle = generated.get('topology') or {}
    return_edges = [e for e in cycle.get('edges', []) if e.get('kind')=='return']
    require(bool(return_edges), 'war and power cycle has no evidenced return relation')
    for edge in return_edges:
        claim = claims.get(edge.get('claimId'), {})
        require(claim.get('speaker')=='기염' and '될 수' in claim.get('text', ''),
                'cycle return is not attributed or loses its possibility scope', claim=claim)
    outcome_views = generated.get('views', [])
    require(any(sum(e.get('from')==n['id'] for e in v['edges'])>=2
                for v in outcome_views for n in v['nodes']), 'outcome view loses the two separate branches')

    # These are real lore words, not annotation fixtures. Compare the link's
    # DOM range with the complete word even when HTML splits the word between
    # an anchor and adjacent text. Keep the normal faction member discoverable.
    canary_pages = ('cosmology/threnodians.html', 'cosmology/civilization.html',
                    'regions/raha.html', 'sentinels.html', 'relationships.html',
                    'events.html', 'factions/fractsidus.html')
    observed = Counter()
    for relative in canary_pages:
        parsed = page(relative)
        rendered = ''.join(parsed.text)
        for match in re.finditer(r'스카우트|스카라베', rendered):
            observed[match[0]] += 1
            for anchor in parsed.linked_text:
                target = urlsplit(anchor['href']).path
                if target not in (BASE+'/people/scar.html', BASE+'/factions/scar.html'):
                    continue
                overlap = anchor['start'] < match.end() and anchor['end'] > match.start()
                require(not overlap, 'longer lore word incorrectly linked to the person Scar',
                        page=relative, word=match[0], link=anchor['href'],
                        linkedText=rendered[anchor['start']:anchor['end']])
    require(observed['스카우트'] > 0, 'scout canary absent from actual rendered lore')
    faction_page = page('factions/fractsidus.html')
    faction_text = ''.join(faction_page.text)
    require(any(urlsplit(anchor['href']).path==BASE+'/people/scar.html'
                and faction_text[anchor['start']:anchor['end']].strip()=='스카'
                for anchor in faction_page.linked_text),
            'actual Fractsidus member Scar lost his canonical person link')
    stats['scoutCanaryOccurrences'] = observed['스카우트']
    stats['scarabCanaryOccurrences'] = observed['스카라베']
    # Zero reports lack of a current scarab example, rather than fabricating a
    # public source. The same overlap assertion applies when one is present.
    stats['scarabCanaryObserved'] = bool(observed['스카라베'])

    # Resolve every local anchor on the checked reader pages against actual
    # output. Include links inside maps and proof disclosures, not just cards.
    queue = list(pages)
    for relative in queue:
        parsed = pages[relative]
        for link in parsed.links:
            u = urlsplit(link)
            if u.scheme or u.netloc:
                continue
            raw_path = unquote(u.path)
            if raw_path.startswith(BASE+'/'):
                target = dist/raw_path[len(BASE)+1:]
            elif raw_path.startswith('/'):
                require(False, 'local link uses the wrong site base', page=relative, link=link)
                continue
            else:
                target = (dist/relative).parent/raw_path if raw_path else dist/relative
            target = target.resolve()
            if target.is_dir():
                target /= 'index.html'
            require(target.is_relative_to(dist) and target.is_file(), 'local link destination missing', page=relative, link=link)
            if not target.is_relative_to(dist) or not target.is_file():
                continue
            fragment = unquote(u.fragment)
            if target==dist/'library.html' and fragment.startswith('/'):
                if fragment.startswith('/source/'):
                    identifier = fragment[len('/source/'):].split('?')[0]
                    require(identifier in entries or identifier in aliases, 'unknown original library route', link=link)
                else:
                    require(fragment.split('?')[0]=='/library', 'unknown library route', link=link)
            elif fragment and target.suffix=='.html':
                require(fragment in page(str(target.relative_to(dist))).ids, 'local link anchor missing', page=relative, link=link)
            stats['localLinks'] += 1
    stats['htmlPages'] = len(pages)
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', **dict(stats),
                      'errorsTotal': len(errors), 'errors': errors[:40]}, ensure_ascii=False))
    return int(bool(errors))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path(__file__).resolve().parents[1]/'dist')
    args = parser.parse_args()
    raise SystemExit(main(args.dist.resolve()))
