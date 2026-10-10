"""Extract a fresh handbook snapshot and optionally extend existing settings.

Inputs remain read-only. Existing record bundles and source URLs are preserved.
Use a fresh private --output directory; public settings contain no host paths.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from wuwa_handbook import extract, sha, write_json

LABELS = {'튜토리얼_페이지': '튜토리얼', '게임_도움말': '게임 도움말', '잔상_도감': '잔상 도감',
          '에코_도감': '에코 도감', '도감_분류': '도감 분류'}


def projection(snapshot, original_index):
    index = copy.deepcopy(original_index)
    flat = {k: v for bundle in snapshot['records'].values() for k, v in bundle.items()}
    if set(flat) & {e['id'] for e in index['entries']}:
        raise ValueError('Expansion already applied; verify the existing snapshot instead')
    new_entries, diagnostics = [], []
    for ident, record in flat.items():
        body = [v for v in record['values'] if v['status'] == 'OK' and v['field'] not in {'name', 'title', 'type'}]
        terms = sorted({t for v in record['values'] for t in v['term_ids']})
        target = new_entries if record['reading_state'] == 'READABLE' else diagnostics
        target.append(dict(id=ident, entry_id=record['entry_id'], title=record['title'],
                                category=record['category'], category_label=LABELS[record['category']],
                                group='guides' if record['category'] in {'튜토리얼_페이지', '게임_도움말'} else 'world',
                                chunk=snapshot['chunks'][ident], role_id=None, role_name='', term_ids=terms,
                                excerpt=(body[0]['text'] if body else '').replace('\n', ' ')[:100],
                                alias_ids=[ident], chapters=[], related_item=None, duplicate_count=1,
                                page='/library.html#/source/' + ident,
                                reading_state=record['reading_state']))
    index['entries'].extend(new_entries)
    index['diagnostic_entries'] = diagnostics
    indexed = {e['id']: e for e in index['entries'] + diagnostics}
    canonical = lambda ident: index['aliases'].get(ident, ident)
    relations = []
    unresolved = []
    for parent in snapshot['tutorials']:
        pages = []
        for order, page_id in enumerate(parent['page_ids']):
            ident = '튜토리얼_페이지:guidetutorialpage:' + str(page_id)
            source = flat.get(ident)
            pages.append(dict(id=ident, order=order, title=source['title'] if source else str(page_id),
                              reading_state=source['reading_state'] if source else 'MISSING_PAGE_RECORD'))
            if not source:
                unresolved.append(dict(kind='tutorial_page', parent_id=parent['entry_id'], page_id=page_id, order=order))
        # Preserve all vector members and their original indices, including diagnostics.
        title = parent['title']['text'] if parent['title']['status'] == 'OK' else '튜토리얼 ' + parent['entry_id']
        rel = dict(kind='tutorial_pages', title=title, source=parent, pages=pages)
        relations.append(rel)
        for page in pages:
            if page['id'] in indexed:
                indexed[page['id']].setdefault('source_relations', []).append(rel)
    for recipe in snapshot['cooking']:
        formula = canonical('아이템_배경:iteminfo:' + str(recipe['formula_item_id']))
        food = canonical('아이템_배경:iteminfo:' + str(recipe['food_item_id']))
        rel = dict(kind='cooking_formula', source=recipe, formula_id=formula, food_id=food)
        relations.append(rel)
        if formula not in indexed or food not in indexed:
            unresolved.append(dict(kind='cooking_item', source=recipe['entry_id'], formula_id=formula,
                                   food_id=food, missing=[x for x in [formula, food] if x not in indexed]))
            continue
        indexed[formula].setdefault('source_relations', []).append(rel)
        indexed[food].setdefault('source_relations', []).append(rel)
    for record in snapshot['records'].get('monster-handbook', {}).values():
        target = '도감_분류:monsterhandbooktype:' + str(record['handbook_type_id'])
        rel = dict(kind='handbook_classification', source_id=record['id'], classification_id=target,
                   source=dict(db=record['db'], table=record['table'], entry_id=record['entry_id'],
                               field_index=2, literal_value=record['handbook_type_id'],
                               source_bin_sha256=record['source_bin_sha256']))
        relations.append(rel)
        if record['id'] in indexed and target in indexed:
            indexed[record['id']].setdefault('source_relations', []).append(rel)
    for source in snapshot['item_roster']:
        ident = canonical('아이템_배경:iteminfo:' + source['entry_id'])
        target = '도감_분류:itemhandbooktype:' + str(source['type_id'])
        rel = dict(kind='item_handbook', item_id=ident, classification_id=target, source=source)
        relations.append(rel)
        if ident in indexed and target in indexed:
            indexed[ident].setdefault('source_relations', []).append(rel)
        else:
            unresolved.append(dict(kind='item_handbook', item_id=ident, classification_id=target))
    for source in snapshot['weapon_roster']:
        ident = canonical('무기_배경:weaponconf:' + source['entry_id'])
        rel = dict(kind='weapon_handbook', weapon_id=ident, source=source)
        relations.append(rel)
        if ident in indexed:
            indexed[ident].setdefault('source_relations', []).append(rel)
        else:
            unresolved.append(dict(kind='weapon_handbook', weapon_id=ident))
    for category, label in LABELS.items():
        index['categories'].append(dict(id=category, label=label,
                                        group='guides' if category in {'튜토리얼_페이지', '게임_도움말'} else 'world'))
    for e in new_entries:
        for term in e['term_ids']:
            index['term_counts'][term] = index['term_counts'].get(term, 0) + 1
    index['source_records'] += len(flat)
    index['reading_entries'] = len(index['entries'])
    index['handbook_expansion'] = dict(schema=snapshot['schema'], added_records=len(flat),
                                      added_reading_entries=len(new_entries),
                                      source_sha256=snapshot['source_sha256'])
    return index, dict(schema='wuwa-source-relations.v1', relations=relations, unresolved=unresolved)


def main(args):
    root, site, output = args.configdb.resolve(), args.site.resolve(), args.output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Use a fresh private output directory')
    if output.is_relative_to(root) or root.is_relative_to(output) or output.is_relative_to(site):
        raise ValueError('Keep private output outside input and public site')
    settings = site / 'settings'
    baseline = args.baseline.resolve() if args.baseline else None
    original_index_bytes = (baseline / 'baseline-index.json' if baseline else settings / 'index.json').read_bytes()
    original_manifest_bytes = (baseline / 'baseline-manifest.json' if baseline else settings / 'manifest.json').read_bytes()
    original_index = json.loads(original_index_bytes)
    manifest = json.loads(original_manifest_bytes)
    old_files = {name: sha((settings / name).read_bytes()) for name in manifest['files'] if name.startswith('records-')}
    for name, digest in old_files.items():
        if digest != manifest['files'][name]:
            raise ValueError('Preserved original record changed: ' + name)
    snapshot = extract(root)
    index, relations = projection(snapshot, original_index)
    output.mkdir(parents=True)
    (output / 'baseline-index.json').write_bytes(original_index_bytes)
    (output / 'baseline-manifest.json').write_bytes(original_manifest_bytes)
    write_json(output / 'originals.json', snapshot)
    write_json(output / 'proposed-index.json', index)
    write_json(output / 'source-relations.json', relations)
    diagnostics = {chunk: dict(Counter(r['reading_state'] for r in bundle.values()))
                   for chunk, bundle in snapshot['records'].items()}
    receipt = dict(schema='wuwa-handbook-expansion-receipt.v1', baseline_records_sha256=old_files,
                   baseline_index_sha256=sha(original_index_bytes),
                   baseline_manifest_sha256=sha(original_manifest_bytes),
                   added_records=sum(len(b) for b in snapshot['records'].values()),
                   added_reading_entries=index['reading_entries'] - original_index['reading_entries'],
                   diagnostics=diagnostics, relation_count=len(relations['relations']),
                   unresolved_relations=relations['unresolved'], source_sha256=snapshot['source_sha256'],
                   source_configdb=str(root), applied=args.apply)
    if args.apply:
        for chunk, bundle in snapshot['records'].items():
            target = settings / ('records-' + chunk + '.json')
            if target.exists() and not baseline:
                raise ValueError('New record bundle already exists: ' + target.name)
            write_json(target, bundle)
            manifest['files'][target.name] = sha(target.read_bytes())
        write_json(settings / 'index.json', index, indent=2, trailing_newline=original_index_bytes.endswith(b'\n'))
        write_json(settings / 'source-relations.json', relations)
        provenance = {k: v for k, v in snapshot.items() if k in {
            'schema', 'source_sha256', 'cache_metadata', 'cache_observed_date',
            'installed_client_match', 'first_release_version', 'term_boundary'}}
        provenance.update(diagnostics=diagnostics, added_records=receipt['added_records'],
                          added_reading_entries=receipt['added_reading_entries'],
                          preservation=dict(record_files_sha256=old_files,
                            baseline_reading_entries=len(original_index['entries']),
                            baseline_source_records=original_index['source_records'],
                            entries_sha256=sha(json.dumps(original_index['entries'], ensure_ascii=False,
                                                        separators=(',', ':')).encode('utf8')),
                            aliases_sha256=sha(json.dumps(original_index['aliases'], ensure_ascii=False,
                                                        separators=(',', ':')).encode('utf8')),
                            curated_sources_sha256=sha(json.dumps(original_index['curated_sources'], ensure_ascii=False,
                                                        separators=(',', ':')).encode('utf8'))))
        write_json(settings / 'handbook-provenance.json', provenance)
        for name in ['index.json', 'source-relations.json', 'handbook-provenance.json']:
            manifest['files'][name] = sha((settings / name).read_bytes())
        manifest['original_records'] = index['source_records']
        manifest['reading_entries'] = index['reading_entries']
        manifest['handbook_expansion'] = provenance
        write_json(settings / 'manifest.json', manifest, indent=2, trailing_newline=original_manifest_bytes.endswith(b'\n'))
    if {p.name: sha(p.read_bytes()) for p in settings.glob('records-*.json') if p.name in old_files} != old_files:
        raise ValueError('Existing original record bundle changed')
    write_json(output / 'receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ['added_records', 'added_reading_entries', 'diagnostics', 'relation_count', 'applied']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--configdb', type=Path, required=True)
    p.add_argument('--site', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--baseline', type=Path, help='Saved baseline directory for an owned expansion rebuild')
    a = p.parse_args()
    try:
        main(a)
    except (ValueError, OSError) as e:
        p.exit(2, str(e) + '\n')
