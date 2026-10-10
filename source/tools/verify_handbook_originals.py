"""Independently replay every exported handbook field against read-only inputs.

Uses its own offset traversal and per-key Korean SQL lookups, not the extractor.
Checks all original bundles, IDs, aliases, URLs, vector order and public metadata.
Mutations operate on in-memory copies; neither sources nor settings are changed.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
SPECS = [
    ('db_guide_new.db', 'guidetutorialpage', 'tutorials', '튜토리얼_페이지', [(2, 'title'), (4, 'content')]),
    ('db_help.db', 'helptext', 'help', '게임_도움말', [(2, 'title'), (4, 'content')]),
    ('db_handbook.db', 'monsterhandbook', 'monster-handbook', '잔상_도감', [(3, 'name'), (6, 'description')]),
    ('db_handbook.db', 'phantomhandbook', 'echoes', '에코_도감',
     [(1, 'name'), (2, 'type'), (3, 'intensity'), (4, 'place'), (5, 'heading_1'), (6, 'description_1'), (7, 'heading_2'), (8, 'description_2')]),
    *[('db_handbook.db', t, 'handbook-types', '도감_분류', [(1, 'description')]) for t in
      ['monsterhandbooktype', 'itemhandbooktype', 'nountype', 'geographytype', 'geographytabtype']],
]


def digest(b):
    return hashlib.sha256(b).hexdigest()


def db(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def read_json(path):
    return json.loads(path.read_text('utf-8'))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(blob, location, fmt):
    check(0 <= location <= len(blob) - struct.calcsize('<' + fmt), 'Offset outside source blob')
    return struct.unpack_from('<' + fmt, blob, location)[0]


def location(blob, field):
    root = scalar(blob, 0, 'I')
    vt = root - scalar(blob, root, 'i')
    length = scalar(blob, vt, 'H')
    check(4 <= length <= len(blob) - vt, 'Invalid source vtable')
    if 4 + 2 * field >= length:
        return None
    delta = scalar(blob, vt + 4 + 2 * field, 'H')
    return root + delta if delta else None


def number(blob, field):
    at = location(blob, field)
    return scalar(blob, at, 'i') if at is not None else 0


def string(blob, field):
    at = location(blob, field)
    if at is None:
        return ''
    start = at + scalar(blob, at, 'I')
    length = scalar(blob, start, 'I')
    check(start + 4 + length < len(blob), 'String outside source blob')
    check(blob[start + 4 + length] == 0, 'Source string terminator changed')
    return blob[start + 4:start + 4 + length].decode('utf-8')


def vector(blob, field):
    at = location(blob, field)
    if at is None:
        return []
    start = at + scalar(blob, at, 'I')
    count = scalar(blob, start, 'I')
    check(count <= (len(blob) - start - 4) // 4, 'Vector outside source blob')
    return [scalar(blob, start + 4 + n * 4, 'I') for n in range(count)]


def display(raw):
    text = re.sub(r'<texture\b[^>]*>', '', raw, flags=re.I)
    text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.I)
    return html.unescape(re.sub(r'</?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>', '', text))


def verify(args):
    root, site, snapshot = args.configdb.resolve(), args.site.resolve(), args.snapshot.resolve()
    evidence, receipt = read_json(snapshot / 'originals.json'), read_json(snapshot / 'receipt.json')
    settings = site / 'settings'
    index = read_json(settings / 'index.json')
    baseline = read_json(snapshot / 'baseline-index.json')
    original_manifest = read_json(snapshot / 'baseline-manifest.json')
    for name, expected in evidence['source_sha256'].items():
        check(digest((root / name).read_bytes()) == expected, 'Input hash mismatch: ' + name)
    for name, item in evidence['cache_metadata'].items():
        check(digest((root / name).read_bytes()) == item['sha256'], 'Cache metadata hash mismatch')
    for name, expected in receipt['baseline_records_sha256'].items():
        check(digest((settings / name).read_bytes()) == expected, 'Preserved record changed: ' + name)
    check(index['aliases'] == baseline['aliases'], 'Existing aliases changed')
    check(index['curated_sources'] == baseline['curated_sources'], 'Existing source URLs changed')
    actual_entries = {e['id']: e for e in index['entries']}
    for old in baseline['entries']:
        check({k: v for k, v in actual_entries[old['id']].items() if k != 'source_relations'} == old,
              'Existing reading entry changed: ' + old['id'])
    main_name, half_name = 'ko/lang_multi_text.db', 'ko/lang_multi_text_1sthalf.db'
    main, half = db(root / main_name), db(root / half_name)

    @lru_cache(maxsize=None)
    def lookup(key):
        if not key:
            return '', '', 'NO_REFERENCE'
        row = main.execute('SELECT Content,RedirectDbIndex FROM MultiText WHERE Id=?', (key,)).fetchone()
        other = half.execute('SELECT Content FROM MultiText WHERE Id=?', (key,)).fetchone()
        if row is None:
            return ((other[0] or '', half_name, 'OK' if other[0] else 'EMPTY') if other else ('', '', 'MISSING_KEY'))
        check(row[1] in {0, 1}, 'Unsupported Korean redirect')
        if row[1] == 1:
            check(other is not None, 'Korean redirect missing')
            content, source = other[0] or '', half_name
        else:
            content, source = row[0] or '', main_name
        return content, source, 'OK' if content else 'EMPTY'

    field_checks = 0
    seen = set()
    bundles = {chunk: read_json(settings / ('records-' + chunk + '.json')) for chunk in evidence['records']}

    def verify_value(actual, blob, field, label):
        nonlocal field_checks
        key = string(blob, field)
        raw, source, status = lookup(key)
        expected = dict(field=label, field_index=field, text_id=key, raw=raw, text=display(raw),
                        status=status, locale_db=source,
                        term_ids=sorted(set(re.findall(r'<te\s+href[=\s]+["\']?(\d+)', raw))))
        check(actual == expected, 'Korean field differs: ' + key + '/' + label)
        field_checks += 1

    for file, table, chunk, category, fields in SPECS:
        with db(root / file) as source:
            check(source.execute('PRAGMA quick_check').fetchone() == ('ok',), 'SQLite integrity failed')
            cur = source.execute('SELECT * FROM "' + table + '" ORDER BY Id')
            cols = [c[0] for c in cur.description]
            for row in cur:
                data = dict(zip(cols, row))
                blob, ident = data['BinData'], category + ':' + table + ':' + str(data['Id'])
                check(number(blob, 0) == data['Id'], 'SQL/FB ID mismatch')
                record = bundles[chunk].get(ident)
                check(record is not None, 'Omitted source record: ' + ident)
                check(record == evidence['records'][chunk][ident], 'Public/private record differs')
                check(record['source_bin_sha256'] == digest(blob), 'Row blob hash changed')
                check(record['entry_id'] == str(data['Id']) and record['db'] == file and record['table'] == table,
                      'Record identity changed')
                check(len(record['values']) == len(fields), 'Source field omitted/added')
                for (field, label), actual in zip(fields, record['values']):
                    verify_value(actual, blob, field, label)
                if table == 'helptext':
                    check(number(blob, 1) == data['GroupId'] == record['help_group_id'], 'Help group differs')
                if table == 'monsterhandbook':
                    check(number(blob, 1) == data['MonsterId'] == record['monster_id'], 'Monster reference differs')
                    check(number(blob, 2) == data['Type'] == record['handbook_type_id'], 'Monster type differs')
                seen.add(ident)
    check(seen == {k for bundle in bundles.values() for k in bundle}, 'Extra or missing original record')
    eligible = {k for bundle in bundles.values() for k, r in bundle.items() if r['reading_state'] == 'READABLE'}
    diagnostic = {e['id'] for e in index.get('diagnostic_entries', [])}
    check(set(actual_entries) - {e['id'] for e in baseline['entries']} == eligible, 'Reading inclusion differs')
    check(diagnostic == seen - eligible, 'Diagnostic source route omitted')
    parent_checks = 0
    source_parents = {p['entry_id']: p for p in evidence['tutorials']}
    with db(root / 'db_guide_new.db') as source:
        for ident, tutorial_type, tutorial_order, blob in source.execute('SELECT Id,TutorialType,TutorialOrder,BinData FROM guidetutorial ORDER BY Id'):
            item = source_parents[str(ident)]
            check(number(blob, 0) == ident and item['source_bin_sha256'] == digest(blob), 'Parent identity differs')
            check(item['page_ids'] == vector(blob, 3), 'Parent vector order/member differs')
            check(item['tutorial_order'] == tutorial_order == number(blob, 2), 'Parent order differs')
            check(item['sql_tutorial_type'] == tutorial_type and item['binary_field_1'] == number(blob, 1), 'Type observations differ')
            check(item['type_semantics'] == 'UNVERIFIED', 'Inferred runtime type adopted')
            verify_value(item['title'], blob, 6, 'title')
            parent_checks += 1
    check(parent_checks == len(source_parents), 'Parent omitted/added')
    recipes = {r['entry_id']: r for r in evidence['cooking']}
    with db(root / 'db_cook.db') as source:
        for ident, formula, food, type_id, blob in source.execute('SELECT Id,FormulaItemId,FoodItemId,TypeId,BinData FROM cookformula ORDER BY Id'):
            item = recipes[str(ident)]
            check(number(blob, 0) == ident and item['source_bin_sha256'] == digest(blob), 'Cooking row differs')
            check([number(blob, n) for n in [1, 2, 3]] == [formula, food, type_id], 'Cooking SQL/FB references differ')
            check([item['formula_item_id'], item['food_item_id'], item['type_id']] == [formula, food, type_id], 'Cooking projection differs')
    for table, key in [('itemhandbook', 'item_roster'), ('weaponhandbook', 'weapon_roster')]:
        roster = {r['entry_id']: r for r in evidence[key]}
        with db(root / 'db_handbook.db') as source:
            cur = source.execute('SELECT * FROM ' + table + ' ORDER BY Id')
            cols = [c[0] for c in cur.description]
            checked = 0
            for row in cur:
                data = dict(zip(cols, row)); blob = data['BinData']; item = roster[str(data['Id'])]
                check(number(blob, 0) == data['Id'] and item['source_bin_sha256'] == digest(blob), 'Roster source differs')
                if key == 'item_roster':
                    check(number(blob, 1) == item['type_id'] == data['Type'], 'Item roster type differs')
                    verify_value(item['title'], blob, 2, 'title')
                checked += 1
            check(checked == len(roster), 'Roster source omitted')
    relations = read_json(settings / 'source-relations.json')
    check(relations == read_json(snapshot / 'source-relations.json'), 'Relation snapshot differs')
    tutorial_relations = [r for r in relations['relations'] if r['kind'] == 'tutorial_pages']
    for rel in tutorial_relations:
        parent = source_parents[rel['source']['entry_id']]
        check(rel['source'] == parent, 'Relation source differs')
        check([int(p['id'].rsplit(':', 1)[1]) for p in rel['pages']] == parent['page_ids'], 'Relation page IDs inferred')
        check([p['order'] for p in rel['pages']] == list(range(len(parent['page_ids']))), 'Relation order differs')
        for page in rel['pages']:
            if page['id'] in eligible | diagnostic:
                target = actual_entries.get(page['id']) or next(e for e in index['diagnostic_entries'] if e['id'] == page['id'])
                check(rel in target.get('source_relations', []), 'Parent relation omitted from page')
    check(len(tutorial_relations) == parent_checks, 'Parent relationship omitted')
    check(index['reading_entries'] == len(index['entries']), 'Reading total differs')
    check(index['source_records'] == baseline['source_records'] + len(seen), 'Original total differs')
    for p in settings.glob('*.json'):
        raw = p.read_text('utf8')
        check(not re.search(r'[A-Za-z]:[\\/]|(?:/Users/|/home/|AppData[\\/])', raw), 'Host path in public input: ' + p.name)
    # Exact raw is allowed to contain intrinsic game rich-text texture tokens.
    texture = bundles['help']['게임_도움말:helptext:503']['values'][1]
    check('<texture=/Game/' in texture['raw'] and '<texture' not in texture['text'], 'Texture raw/display preservation failed')
    for ident in ['튜토리얼_페이지:guidetutorialpage:50002', '튜토리얼_페이지:guidetutorialpage:3601802', '게임_도움말:helptext:91']:
        check(ident in eligible, 'Normal test wording excluded')
    check('게임_도움말:helptext:1' in diagnostic and '게임_도움말:helptext:16' in diagnostic, 'Explicit diagnostic wording lost')
    # The numeric key 1000001 is not the actual page ID 1.
    parent = source_parents['30001']
    check(parent['page_ids'] == [1, 3000102], 'Literal page canary differs')
    mutations = 0
    def rejects(action, label):
        nonlocal mutations
        try:
            action()
        except (ValueError, UnicodeDecodeError, struct.error):
            mutations += 1
            return
        raise ValueError('Mutation survived: ' + label)
    def changed_value(field):
        with db(root / 'db_guide_new.db') as source:
            blob = source.execute('SELECT BinData FROM guidetutorialpage WHERE Id=1').fetchone()[0]
        actual = dict(bundles['tutorials']['튜토리얼_페이지:guidetutorialpage:1']['values'][1])
        actual[field] = 'mutated'
        verify_value(actual, blob, 4, 'content')
    for field in ['text_id', 'raw', 'locale_db', 'status']:
        rejects(lambda field=field: changed_value(field), field)
    rejects(lambda: check(parent['page_ids'] == [3000102, 1], 'Swapped vector'), 'parent order')
    rejects(lambda: check(parent['page_ids'] == [1000001, 3000102], 'Key-derived page ID'), 'key-derived ID')
    rejects(lambda: check(index['aliases'] == {**baseline['aliases'], 'fake': 'fake'}, 'Alias mutation'), 'old alias')
    rejects(lambda: check(eligible == eligible - {'게임_도움말:helptext:91'}, 'False test exclusion'), 'normal test text')
    rejects(lambda: check('<texture' not in texture['raw'], 'Raw texture stripped'), 'stripped raw asset token')
    rejects(lambda: check(not re.search(r'[A-Za-z]:[\\/]', 'D:/private/input'), 'Host path'), 'host path')
    main.close(); half.close()
    manifest = read_json(settings / 'manifest.json')
    check(manifest['client_version'] == original_manifest['client_version'], 'Unsupported installed version change')
    for name, expected in manifest['files'].items():
        content = (settings / name).read_bytes()
        if manifest.get('hash_normalization', {}).get(name) == 'lf':
            content = content.decode('utf8').replace('\r\n', '\n').encode('utf8')
        check(digest(content) == expected, 'Manifest hash differs: ' + name)
    return dict(verification='PASS', original_records=len(seen), raw_field_checks=field_checks,
                tutorial_parents=parent_checks, recipes=len(recipes), eligible=len(eligible),
                diagnostic_routes=len(diagnostic), preserved_original_files=len(receipt['baseline_records_sha256']),
                preserved_existing_entries=len(baseline['entries']), mutations_rejected=mutations,
                limits=['Observed field projection; not full FlatBuffers object-schema EOF',
                        'Cache build metadata does not prove currently installed client match',
                        'Runtime activation, ingredient arrays and first release are unverified'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--configdb', type=Path, required=True)
    p.add_argument('--site', type=Path, required=True)
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    try:
        result = verify(a)
        if a.output:
            check(not a.output.exists(), 'Use a fresh verification output')
            a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, sqlite3.Error, KeyError) as e:
        p.exit(2, str(e) + '\n')
