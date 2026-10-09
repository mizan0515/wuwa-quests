"""Read-only source and HTML QA for grouped lore directories.

This checker audits authored grouping, canonical CVA consumption and preserved
source fields. Browser layout, filtering and focus need separate real-use QA.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

sys.dont_write_bytecode = True
from verify_people_catalog import Page, gather
from verify_original_rendering import LorePage, paragraph_texts, visible_text, load_curated_sources

BASE = '/wuwa-quests'
CATEGORIES = ('factions', 'cosmology')
IDENTIFIER = re.compile(r'^[a-z][a-z0-9-]+$')
INTERNAL = ('D:/game', 'D:\\game', 'SKILL.md', 'AGENTS.md',
            'wuwa-directory-discovery.v1', 'source_text_sha256')


class AuditPage(Page):
    def handle_data(self, value):
        super().handle_data(value)
        if self.stack and self.stack[-1][0] == 'script':
            node = self.stack[-1][2]
            node.setdefault('script_text', []).append(value)


def classes(node):
    return set(node['attrs'].get('class', '').split())


def node_text(node):
    return ''.join(node['text'])


def descendants(page, parent):
    return [node for node in page.nodes if Page.within(node, parent)]


def ancestor(node, predicate):
    current = node['parent']
    while current is not None:
        if predicate(current):
            return current
        current = current['parent']
    return None


def parse_page(html):
    page = AuditPage()
    page.feed(html)
    page.close()
    return page


def subject_url(url):
    if not isinstance(url, str):
        return False
    split = urlsplit(url)
    path = unquote(split.path)
    return (not split.scheme and not split.netloc and not split.query and
            not split.fragment and path.startswith(BASE + '/') and
            path.endswith('.html') and '\\' not in path and
            not any(part in ('.', '..') for part in path.split('/')))


def resolve_registry(registry, atlas, require):
    require(registry.get('schema') == 'wuwa-directory-discovery.v1', 'directory schema differs')
    entries = registry.get('entries', [])
    require(isinstance(entries, list), 'directory entries are not a list')
    if not isinstance(entries, list):
        entries = []
    require(set(registry.get('pages', {})) == set(CATEGORIES), 'directory categories differ')
    result = {}
    declared = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            require(False, 'directory entry is not an object')
            continue
        category, identifier = entry.get('category'), entry.get('id', '')
        declared[(category, identifier)] += 1
        require(category in CATEGORIES and isinstance(identifier, str) and bool(IDENTIFIER.fullmatch(identifier)),
                'directory entry identity invalid', category=category, id=identifier)
        require(all(isinstance(entry.get(key), str) and entry[key].strip() for key in ('name', 'kind', 'summary')),
                'directory entry text missing', id=identifier)
        require(subject_url(entry.get('url')), 'directory entry body URL invalid', id=identifier)
        require(type(entry.get('reuse')) is bool, 'directory reuse flag missing', id=identifier)
        require(isinstance(entry.get('refs'), list) and bool(entry['refs']), 'directory source evidence missing', id=identifier)
        for key in ('name', 'kind', 'summary'):
            require(not any(value in str(entry.get(key, '')) for value in INTERNAL), 'internal editorial text exposed', id=identifier, field=key)
    require(all(count == 1 for count in declared.values()), 'duplicate directory entry identity')
    for category in CATEGORIES:
        subjects = {item['id']: {'id': item['id'], 'name': item['title'],
                    'kind': '조직 본문' if category == 'factions' else '설정 본문',
                    'summary': item['summary'], 'url': BASE + '/' + category + '/' + item['id'] + '.html',
                    'source': item, 'new': False} for item in atlas.get(category, [])}
        for entry in entries:
            if not isinstance(entry, dict) or entry.get('category') != category:
                continue
            require(entry['id'] not in subjects, 'new entry replaces existing subject', category=category, id=entry['id'])
            subjects[entry['id']] = {**entry, 'source': entry, 'new': True}
        page = registry.get('pages', {}).get(category, {})
        groups = page.get('groups', [])
        require(isinstance(groups, list) and bool(groups), 'directory groups missing', category=category)
        if not isinstance(groups, list):
            groups = []
        seen, group_ids = Counter(), Counter()
        for group in groups:
            identifier = group.get('id', '')
            group_ids[identifier] += 1
            require(isinstance(identifier, str) and bool(IDENTIFIER.fullmatch(identifier)), 'directory group identity invalid', category=category)
            require(all(isinstance(group.get(key), str) and group[key].strip() for key in ('title', 'summary')),
                    'directory group reading purpose missing', category=category, group=identifier)
            ids = group.get('entryIds', [])
            require(isinstance(ids, list) and 1 <= len(ids) <= 24, 'directory group item count invalid', category=category, group=identifier)
            for item in ids:
                seen[item] += 1
                require(item in subjects, 'group references unknown subject', category=category, group=identifier, id=item)
        require(all(count == 1 for count in group_ids.values()), 'duplicate directory group identity', category=category)
        require(Counter(subjects.keys()) == seen, 'directory grouping omits or repeats subjects', category=category,
                missing=list((Counter(subjects.keys()) - seen).elements()), extra=list((seen - Counter(subjects.keys())).elements()))
        membership = {item: group['id'] for group in groups for item in group.get('entryIds', [])}
        result[category] = {'subjects': subjects, 'groups': groups, 'membership': membership, 'page': page}
    return result


def audit_cva(page, require, context):
    modules = [node for node in page.nodes if 'cva-module' in classes(node)]
    models = [node for node in page.nodes if node['tag'] == 'script' and 'data-cva-model' in node['attrs']]
    require(bool(modules) and bool(models), 'body does not consume canonical CVA modules', **context)
    module_ids = Counter(node['attrs'].get('id') for node in modules)
    for model in models:
        try:
            document = json.loads(''.join(model.get('script_text', [])))
            require(document.get('schema') == 'cva.page.v2', 'CVA model schema differs', **context)
            require(bool(document.get('modules')), 'CVA model has no modules', **context)
            for block in document.get('modules', []):
                require(module_ids[block.get('id')] == 1, 'CVA model does not match rendered module', module=block.get('id'), **context)
        except (ValueError, TypeError) as error:
            require(False, 'CVA model JSON invalid', detail=str(error), **context)


def audit_directory(page, resolved, category, require, script_version=None):
    subjects, groups, membership = resolved['subjects'], resolved['groups'], resolved['membership']
    require(len(page.ids) == len(set(page.ids)), 'directory HTML has duplicate heading or element IDs', category=category)
    roots = [node for node in page.nodes if 'data-discovery-directory' in node['attrs']]
    require(len(roots) == 1, 'directory reader boundary differs', category=category)
    metadata = [node for node in page.nodes if 'data-discovery-entry' in node['attrs']]
    actual = Counter(node['attrs']['data-discovery-entry'] for node in metadata)
    require(actual == Counter(subjects.keys()), 'rendered directory omits or repeats subjects', category=category)
    sections = [node for node in page.nodes if 'data-discovery-section' in node['attrs']]
    require(Counter(node['attrs']['data-discovery-section'] for node in sections) == Counter(g['id'] for g in groups),
            'rendered directory groups differ', category=category)
    for group in groups:
        matching = [node for node in sections if node['attrs'].get('data-discovery-section') == group['id']]
        require(len(matching) == 1, 'group section count differs', category=category, group=group['id'])
        if len(matching) != 1:
            continue
        section = matching[0]
        require(section['tag'] == 'section' and section['attrs'].get('id') == 'group-' + group['id'], 'group anchor boundary differs', category=category, group=group['id'])
        require(any(node['tag'] == 'h2' and node_text(node) == group['title'] for node in descendants(page, section)), 'group heading differs', category=category, group=group['id'])
        require('#group-' + group['id'] in page.links, 'group direct navigation missing', category=category, group=group['id'])
    for node in metadata:
        identifier = node['attrs']['data-discovery-entry']
        if identifier not in subjects:
            continue
        entry, expected_group = subjects[identifier], membership.get(identifier)
        context = {'category': category, 'id': identifier}
        require('hidden' in node['attrs'], 'search metadata is visible to readers', **context)
        require(node['attrs'].get('data-discovery-group') == expected_group, 'card metadata group differs', **context)
        require(node['attrs'].get('data-discovery-search') == entry['name'] + ' ' + entry['kind'] + ' ' + entry['summary'], 'card search metadata differs from subject', **context)
        card = ancestor(node, lambda n: 'data-cva-item-index' in n['attrs'])
        section = ancestor(node, lambda n: 'data-discovery-section' in n['attrs'])
        require(card is not None and 'cva-item' in classes(card), 'directory subject is outside canonical CVA card', **context)
        require(section is not None and section['attrs'].get('data-discovery-section') == expected_group, 'card is rendered under another group', **context)
        if card is None:
            continue
        children = descendants(page, card)
        title_links = [n for n in children if n['tag'] == 'a' and 'data-reading-link' in n['attrs'] and ancestor(n, lambda p: 'cva-item-title' in classes(p)) is not None]
        require(len(title_links) == 1 and title_links[0]['attrs'].get('href') == entry['url'] and node_text(title_links[0]).removesuffix(' ↗') == entry['name'], 'card title does not link to its direct body', **context)
        require(any('cva-item-body' in classes(n) and node_text(n) == entry['summary'] for n in children), 'card summary differs from subject', **context)
    controls = {node['attrs'].get('id'): node for node in page.nodes if node['tag'] in ('input', 'select', 'button')}
    require(controls.get('discovery-query', {}).get('attrs', {}).get('type') == 'search' and 'discovery-group' in controls, 'directory search controls missing', category=category)
    if script_version:
        scripts = [urlsplit(value) for value in page.scripts if urlsplit(value).path == BASE + '/lore/directory.js']
        require(len(scripts) == 1 and scripts[0].query == 'v=' + script_version, 'directory filter cache version differs', category=category)
    for node in page.nodes:
        if node['tag'] == 'a':
            require(ancestor(node, lambda n: n['tag'] == 'a') is None, 'nested directory link', category=category)
    audit_cva(page, require, {'category': category})


def audit_quote_boundary(page, identifier, excerpt, evidence_url, require, context):
    boundaries = [node for node in page.nodes if node['attrs'].get('id') == identifier]
    require(len(boundaries) == 1, 'dossier original record boundary missing', record=identifier, **context)
    if len(boundaries) != 1:
        return
    boundary = boundaries[0]
    children = descendants(page, boundary)
    require(any(('cva-body' in classes(node) or node['tag'] == 'blockquote') and node_text(node) == excerpt for node in children), 'dossier exact original quotation differs', record=identifier, **context)
    proofs = [node for node in children if node['tag'] == 'details' and 'rw-proof' in classes(node)]
    require(any(any(n['tag'] == 'a' and n['attrs'].get('href') == evidence_url for n in descendants(page, proof)) and
                any(n['tag'] == 'blockquote' and node_text(n) == excerpt for n in descendants(page, proof)) for proof in proofs),
            'original quotation and correct source URL do not share their proof boundary', record=identifier, **context)


def main(site, dist):
    errors, stats, cache, source_cache = [], Counter(), {}, {}
    def require(condition, error, **context):
        if not condition:
            errors.append({'error': error, **context})
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    registry, atlas, index = (load(site / 'settings' / name) for name in ('directory-discovery.json', 'atlas.json', 'index.json'))
    records = {}
    for path in (site / 'settings').glob('records-*.json'):
        records.update(load(path))
    resolved = resolve_registry(registry, atlas, require)
    curated = load_curated_sources(site, dist, index)
    entries = {entry['id']: entry for entry in index['entries']}
    aliases = index.get('aliases', {})
    graph = load(dist / 'reading-data/graph.json')
    evidence = {(item['sourceId'], item['blockId'], item['quote']): item for item in graph['evidence']}
    script = (site / 'source/public/lore/directory.js').read_text(encoding='utf-8').replace('\r\n', '\n')
    script_version = hashlib.sha256(script.encode()).hexdigest()[:12]
    def page_url(url):
        split = urlsplit(url)
        path = unquote(split.path)
        safe = (not split.scheme and not split.netloc and path.startswith(BASE + '/') and
                path.endswith('.html') and '\\' not in path and
                not any(part in ('.', '..') for part in path.split('/')))
        require(safe, 'source or body URL leaves site', url=url)
        if not safe:
            raise ValueError('Refusing a source or body path outside the site: ' + str(url))
        relative = path.removeprefix(BASE + '/')
        if relative not in cache:
            cache[relative] = parse_page((dist / relative).read_text(encoding='utf-8'))
        page = cache[relative]
        require(not split.fragment or unquote(split.fragment) in page.ids, 'source or body URL anchor missing', url=url)
        return page, relative
    def audit_ref(ref, context):
        if ref.get('quest_id'):
            raw = (site / 'originals' / (ref['quest_id'] + '.txt')).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == ref.get('source_sha256'), 'quest original hash differs', **context)
            text = raw.decode('utf-8')
            starts = list(re.finditer(r'^장면 (\d+):', text, re.M))
            scenes = {int(match[1]): text[match.start():starts[i + 1].start() if i + 1 < len(starts) else len(text)] for i, match in enumerate(starts)}
            require(ref['quote'] in scenes.get(ref['scene'], ''), 'quest original quote or scene differs', **context)
            key = ('quest-' + ref['quest_id'], 'scene-' + str(ref['scene']), ref['quote'])
        else:
            canonical = aliases.get(ref['id'], ref['id'])
            value = next((value for value in records.get(canonical, {}).get('values', []) if value.get('field') == ref['field'] and value.get('status') == 'OK'), None)
            require(value is not None, 'directory original field missing', source=canonical, field=ref['field'], **context)
            if value is None:
                return None
            require(hashlib.sha256(value['raw'].encode()).hexdigest() == ref.get('source_text_sha256'), 'directory original field hash differs', source=canonical, field=ref['field'], **context)
            require(bool(ref.get('excerpt')) and ref['excerpt'] in visible_text(value['raw']), 'directory original excerpt differs', source=canonical, field=ref['field'], **context)
            key = (canonical, ref['field'], ref['excerpt'])
        proof = evidence.get(key)
        require(proof is not None, 'directory reference absent from structured evidence', **context)
        if proof is None:
            return None
        original_page, relative = page_url(proof['url'])
        if not ref.get('quest_id'):
            canonical, field, excerpt = key
            entry = entries[canonical]
            expected_path = '/sources/' + curated[canonical] + '.html' if canonical in curated and entry['page'].startswith('/library.html#') else entry['page']
            require(urlsplit(proof['url']).path == BASE + expected_path and unquote(urlsplit(proof['url']).fragment) == 'field-' + field,
                    'structured evidence points to another original field', **context)
            if relative not in source_cache:
                parser = LorePage()
                parser.feed((dist / relative).read_text(encoding='utf-8'))
                source_cache[relative] = parser
            field_nodes = [node for node in source_cache[relative].fields if 'field-' + field in node['ids']]
            require(len(field_nodes) == 1 and [''.join(p) for p in field_nodes[0]['paragraphs']] == paragraph_texts(value['raw']),
                    'directory original field HTML differs from preserved source', source=canonical, field=field, **context)
        stats['sourceReferences'] += 1
        return proof
    for category, result in resolved.items():
        page, _ = page_url(BASE + '/' + category + '.html')
        audit_directory(page, result, category, require, script_version)
        stats['directoryPages'] += 1
        stats['directoryGroups'] += len(result['groups'])
        stats['directorySubjects'] += len(result['subjects'])
        for identifier, subject in result['subjects'].items():
            context = {'category': category, 'id': identifier}
            body, _ = page_url(subject['url'])
            require(any(node['tag'] == 'h1' and node_text(node).strip() == subject['name'] for node in body.nodes), 'directory body heading differs from subject', **context)
            audit_cva(body, require, context)
            references = list(gather(subject['source']))
            require(bool(references), 'directory subject has no source-backed facts', **context)
            for i, ref in enumerate(references):
                proof = audit_ref(ref, context)
                if subject['new'] and not subject.get('reuse') and proof is not None:
                    audit_quote_boundary(body, 'record-' + str(i), ref.get('excerpt', ref.get('quote')), proof['url'], require, context)
            if subject['new'] and not subject.get('reuse'):
                stats['newDossiers'] += 1
                require('overview' in body.ids and 'evidence' in body.ids, 'new dossier reading boundaries missing', **context)
                visible = ''.join(node_text(node) for node in body.nodes if node['tag'] == 'main')
                require(not any(value in visible for value in INTERNAL), 'new dossier exposes internal development material', **context)
    stats['htmlPages'] = len(cache)
    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'scope': 'static source and HTML; browser layout and behavior separate', **dict(stats),
                      'errorsTotal': len(errors), 'errors': errors[:40]}, ensure_ascii=False))
    return bool(errors)


def self_test():
    atlas = {'factions': [], 'cosmology': []}
    entry = {'id': 'source-one', 'category': 'factions', 'name': '조직', 'kind': '연구 조직', 'summary': '원문에 근거한 소개',
             'url': BASE + '/factions/source-one.html', 'reuse': False, 'refs': [{'id': 'one', 'field': 'content', 'excerpt': '가 > 나'}]}
    registry = {'schema': 'wuwa-directory-discovery.v1', 'entries': [entry], 'pages': {
        'factions': {'groups': [{'id': 'research', 'title': '연구', 'summary': '기록', 'entryIds': ['source-one']}]},
        'cosmology': {'groups': [{'id': 'world', 'title': '세계', 'summary': '기록', 'entryIds': ['old-world']}]} }}
    atlas['cosmology'] = [{'id': 'old-world', 'title': '세계', 'summary': '소개'}]
    def accepted_registry(value):
        errors = []
        resolve_registry(value, atlas, lambda condition, error, **context: errors.append(error) if not condition else None)
        return not errors
    if not accepted_registry(registry):
        raise ValueError('valid grouped registry rejected')
    mutations = {}
    omitted = copy.deepcopy(registry); omitted['pages']['factions']['groups'][0]['entryIds'] = []
    mutations['OMITTED_SUBJECT'] = omitted
    duplicate = copy.deepcopy(registry); duplicate['pages']['factions']['groups'][0]['entryIds'].append('source-one')
    mutations['REPEATED_SUBJECT'] = duplicate
    unknown = copy.deepcopy(registry); unknown['pages']['factions']['groups'][0]['entryIds'] = ['foreign']
    mutations['UNKNOWN_SUBJECT'] = unknown
    foreign = copy.deepcopy(registry); foreign['entries'][0]['url'] = 'https://example.com/other.html'
    mutations['FOREIGN_BODY_URL'] = foreign
    for label, value in mutations.items():
        if accepted_registry(value):
            raise ValueError('contaminated registry accepted: ' + label)
    fixture = ('<div data-discovery-directory><nav><a href="#group-research">연구</a></nav>'
               '<input id="discovery-query" type="search"><select id="discovery-group"></select>'
               '<section id="group-research" data-discovery-section="research"><h2>연구</h2>'
               '<div class="cva-page" data-cva><section class="cva-module" id="directory-module">'
               '<article class="cva-item" data-cva-item-index="0">'
               '<span hidden data-discovery-entry="source-one" data-discovery-group="research" '
               'data-discovery-search="조직 연구 조직 원문에 근거한 소개"></span>'
               '<div class="cva-item-copy"><h3 class="cva-item-title">'
               '<a data-reading-link href="/wuwa-quests/factions/source-one.html">조직 <span>↗</span></a>'
               '</h3><p class="cva-item-body">원문에 근거한 소개</p></div></article></section>'
               '<script type="application/json" data-cva-model>{"schema":"cva.page.v2","modules":[{"id":"directory-module"}]}</script>'
               '</div></section></div>')
    fixture_resolved = resolve_registry(registry, atlas, lambda condition, error, **context: None)['factions']
    def accepted_directory(html):
        errors = []
        audit_directory(parse_page(html), fixture_resolved, 'factions',
                        lambda condition, error, **context: errors.append(error) if not condition else None)
        return not errors
    if not accepted_directory(fixture):
        raise ValueError('valid directory HTML rejected')
    html_mutations = {
        'WRONG_RENDERED_GROUP': fixture.replace('data-discovery-group="research"', 'data-discovery-group="foreign"'),
        'WRONG_GROUP_ANCHOR': fixture.replace('href="#group-research"', 'href="#group-foreign"'),
        'WRONG_CARD_BODY_LINK': fixture.replace('href="/wuwa-quests/factions/source-one.html"', 'href="/wuwa-quests/factions/foreign.html"'),
        'SEARCH_METADATA_CORRUPTION': fixture.replace('data-discovery-search="조직 연구 조직 원문에 근거한 소개"', 'data-discovery-search="다른 인물"'),
        'VISIBLE_SEARCH_METADATA': fixture.replace('<span hidden data-discovery-entry', '<span data-discovery-entry'),
        'CVA_MODEL_MODULE_MISMATCH': fixture.replace('"id":"directory-module"', '"id":"foreign-module"'),
    }
    for label, html in html_mutations.items():
        if accepted_directory(html):
            raise ValueError('contaminated directory HTML accepted: ' + label)
    quoted = '<section id="record-0"><blockquote class="cva-quote"><p class="cva-body">가 &gt; 나</p></blockquote><details class="rw-proof"><summary>원문 근거</summary><blockquote>가 &gt; 나</blockquote><a href="/wuwa-quests/sources/one.html#field-content">원문</a></details></section>'
    def accepted_quote(html):
        errors = []
        audit_quote_boundary(parse_page(html), 'record-0', '가 > 나', '/wuwa-quests/sources/one.html#field-content',
                             lambda condition, error, **context: errors.append(error) if not condition else None, {})
        return not errors
    if not accepted_quote(quoted):
        raise ValueError('valid exact original proof rejected')
    quote_mutations = {'QUOTE_CORRUPTION': quoted.replace('가 &gt; 나', '가 &lt; 나'),
                       'WRONG_SOURCE_LINK': quoted.replace('sources/one.html', 'sources/other.html'),
                       'QUOTE_OUTSIDE_PROOF': quoted.replace('<blockquote>가 &gt; 나</blockquote>', '') + '<blockquote>가 &gt; 나</blockquote>',
                       'WRONG_RECORD_BOUNDARY': quoted.replace('record-0', 'record-1')}
    for label, html in quote_mutations.items():
        if accepted_quote(html):
            raise ValueError('contaminated original proof accepted: ' + label)
    return list(mutations) + list(html_mutations) + list(quote_mutations)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path(__file__).resolve().parents[1] / 'dist')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        canaries = self_test()
        if args.self_test:
            print(json.dumps({'status': 'PASS', 'semanticFailureCanaries': canaries, 'count': len(canaries)}, ensure_ascii=False))
            raise SystemExit(0)
        raise SystemExit(main(Path(__file__).resolve().parents[2], args.dist.resolve()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'FAIL', 'scope': 'static source and HTML', 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
