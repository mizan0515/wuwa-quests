"""Observed WuWa handbook schemas and read-only SQLite/Korean joins.

The offset reader reuses the canonical wuwa-quest-dialogue fb_utils.py contract.
Only explicitly listed fields are read. Field numbers are not text-key IDs.
"""
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
import struct


class FB:
    def __init__(self, data):
        self.b = data

    def unpack(self, fmt, pos):
        length = struct.calcsize('<' + fmt)
        if pos < 0 or pos + length > len(self.b):
            raise ValueError(f'FlatBuffers offset out of bounds: {pos}')
        return struct.unpack_from('<' + fmt, self.b, pos)[0]

    def root(self):
        pos = self.unpack('I', 0)
        if pos < 4 or pos >= len(self.b):
            raise ValueError('Invalid FlatBuffers root')
        return pos

    def field(self, pos, n):
        if n < 0:
            raise ValueError('Negative field index')
        vt = pos - self.unpack('i', pos)
        size = self.unpack('H', vt)
        if size < 4 or vt < 0 or vt + size > len(self.b):
            raise ValueError('Invalid FlatBuffers vtable')
        if 4 + 2 * n >= size:
            return None
        delta = self.unpack('H', vt + 4 + 2 * n)
        return pos + delta if delta else None

    def target(self, pos, n):
        at = self.field(pos, n)
        return at + self.unpack('I', at) if at is not None else None

    def string(self, pos, n):
        at = self.target(pos, n)
        if at is None:
            return ''
        length = self.unpack('I', at)
        if at + 4 + length >= len(self.b) or self.b[at + 4 + length] != 0:
            raise ValueError('FlatBuffers string bounds/terminator changed')
        return self.b[at + 4:at + 4 + length].decode('utf-8')

    def scalar(self, pos, n, fmt='i', default=0):
        at = self.field(pos, n)
        return self.unpack(fmt, at) if at is not None else default

    def uint_vector(self, pos, n):
        at = self.target(pos, n)
        if at is None:
            return []
        count = self.unpack('I', at)
        if count > (len(self.b) - at - 4) // 4:
            raise ValueError('FlatBuffers vector out of bounds')
        return [self.unpack('I', at + 4 + 4 * i) for i in range(count)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)


def rows(root, file, table):
    with connect(root / file) as db:
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('Invalid SQLite database: ' + file)
        cur = db.execute(f'SELECT * FROM "{table}" ORDER BY Id')
        names = [c[0] for c in cur.description]
        for row in cur:
            data = dict(zip(names, row))
            fb = FB(data['BinData'])
            pos = fb.root()
            if fb.scalar(pos, 0) != data['Id']:
                raise ValueError('SQL/FB ID mismatch: ' + table + ':' + str(data['Id']))
            yield data, fb, pos


def load_locale(root):
    main, half = 'ko/lang_multi_text.db', 'ko/lang_multi_text_1sthalf.db'
    with connect(root / main) as db:
        data = db.execute('SELECT Id,Content,RedirectDbIndex FROM MultiText').fetchall()
    if {r for _, _, r in data} - {0, 1}:
        raise ValueError('Unsupported Korean redirect')
    redirects = {k: r for k, _, r in data}
    result = {k: (v or '', main) for k, v, r in data}
    with connect(root / half) as db:
        other = db.execute('SELECT Id,Content FROM MultiText').fetchall()
    available = {k for k, _ in other}
    if any(r == 1 and k not in available for k, r in redirects.items()):
        raise ValueError('Missing Korean redirected key')
    for k, v in other:
        if redirects.get(k) == 1 or k not in result:
            result[k] = (v or '', half)
    return result


def clean(raw):
    return html.unescape(re.sub(r'</?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>', '',
                               re.sub(r'<texture\b[^>]*>', '',
                                      re.sub(r'<br\s*/?\s*>', '\n', raw, flags=re.I), flags=re.I)))


def value(locale, key, field, index):
    raw, source = locale.get(key, ('', ''))
    status = 'NO_REFERENCE' if not key else 'MISSING_KEY' if key not in locale else 'EMPTY' if not raw else 'OK'
    return dict(field=field, field_index=index, text_id=key, raw=raw, text=clean(raw),
                status=status, locale_db=source,
                term_ids=sorted(set(re.findall(r'<te\s+href[=\s]+["\']?(\d+)', raw))))


# Database/table/category/chunk/field-index-to-label. No asset/icon fields.
SCHEMAS = [
    ('db_guide_new.db', 'guidetutorialpage', '튜토리얼_페이지', 'tutorials', {2: 'title', 4: 'content'}),
    ('db_help.db', 'helptext', '게임_도움말', 'help', {2: 'title', 4: 'content'}),
    ('db_handbook.db', 'monsterhandbook', '잔상_도감', 'monster-handbook', {3: 'name', 6: 'description'}),
    ('db_handbook.db', 'phantomhandbook', '에코_도감', 'echoes',
     {1: 'name', 2: 'type', 3: 'intensity', 4: 'place', 5: 'heading_1', 6: 'description_1', 7: 'heading_2', 8: 'description_2'}),
    ('db_handbook.db', 'monsterhandbooktype', '도감_분류', 'handbook-types', {1: 'description'}),
    ('db_handbook.db', 'itemhandbooktype', '도감_분류', 'handbook-types', {1: 'description'}),
    ('db_handbook.db', 'nountype', '도감_분류', 'handbook-types', {1: 'description'}),
    ('db_handbook.db', 'geographytype', '도감_분류', 'handbook-types', {1: 'description'}),
    ('db_handbook.db', 'geographytabtype', '도감_분류', 'handbook-types', {1: 'description'}),
]
BODY_FIELDS = {'content', 'description', 'description_1', 'description_2'}


def reading_state(record):
    bodies = [v for v in record['values'] if v['field'] in BODY_FIELDS]
    if not any(v['status'] == 'OK' and v['text'].strip() for v in bodies):
        return 'NO_KOREAN_BODY'
    # These are textual diagnostics, not a claim about runtime activation.
    text = '\n'.join(v['text'] for v in bodies if v['status'] == 'OK').strip()
    if re.fullmatch(r'(?:테스트|测试|test(?:ing)?)[.!。]?', text, re.I):
        return 'TEST_CONTENT_ONLY'
    if re.search(r'(?<![A-Za-z])(?:xx+|XX+)(?![A-Za-z])', text):
        return 'PLACEHOLDER_MARKER'
    return 'READABLE'


def extract(root):
    root = Path(root).resolve()
    required = sorted({s[0] for s in SCHEMAS} | {'db_cook.db', 'db_Term.db',
                     'ko/lang_multi_text.db', 'ko/lang_multi_text_1sthalf.db'})
    before = {p: sha((root / p).read_bytes()) for p in required}
    locale = load_locale(root)
    bundles, chunks = {}, {}
    for file, table, category, chunk, fields in SCHEMAS:
        bundle = bundles.setdefault(chunk, {})
        for data, fb, pos in rows(root, file, table):
            ident = str(data['Id'])
            vals = [value(locale, fb.string(pos, n), field, n) for n, field in fields.items()]
            title = next((v['text'] for v in vals if v['field'] in {'name', 'title'} and v['status'] == 'OK'),
                         next((v['text'] for v in vals if v['field'] == 'description' and v['status'] == 'OK'), category + ' ' + ident))
            record = dict(id=category + ':' + table + ':' + ident, entry_id=ident, category=category,
                          title=title, db=file, table=table, role_id=None, related_item_id=None,
                          sort=None, values=vals, source_bin_sha256=sha(data['BinData']))
            if table == 'helptext':
                group = fb.scalar(pos, 1)
                if group != data['GroupId']:
                    raise ValueError('Help GroupId SQL/FB mismatch')
                record['help_group_id'] = group
            if table == 'monsterhandbook':
                for n, key in [(1, 'MonsterId'), (2, 'Type')]:
                    if fb.scalar(pos, n) != data[key]:
                        raise ValueError('Monster handbook SQL/FB scalar mismatch')
                record['monster_id'] = data['MonsterId']
                record['handbook_type_id'] = data['Type']
            record['reading_state'] = reading_state(record)
            record['diagnostic_markers'] = ['TEST_WORD_PRESENT'] if any(
                re.search(r'테스트|测试|\btest(?:ing)?\b', v['text'], re.I) for v in vals) else []
            bundle[record['id']] = record
            chunks[record['id']] = chunk
    tutorials = []
    for data, fb, pos in rows(root, 'db_guide_new.db', 'guidetutorial'):
        if fb.scalar(pos, 2) != data['TutorialOrder']:
            raise ValueError('Tutorial parent order scalar mismatch')
        tutorials.append(dict(entry_id=str(data['Id']), db='db_guide_new.db', table='guidetutorial',
                              sql_tutorial_type=data['TutorialType'], binary_field_1=fb.scalar(pos, 1),
                              type_semantics='UNVERIFIED', tutorial_order=data['TutorialOrder'],
                              page_ids=fb.uint_vector(pos, 3), pages_field_index=3,
                              title=value(locale, fb.string(pos, 6), 'title', 6),
                              source_bin_sha256=sha(data['BinData'])))
    cooking = []
    for data, fb, pos in rows(root, 'db_cook.db', 'cookformula'):
        for n, key in [(1, 'FormulaItemId'), (2, 'FoodItemId'), (3, 'TypeId')]:
            if fb.scalar(pos, n) != data[key]:
                raise ValueError('Cooking SQL/FB scalar mismatch')
        cooking.append(dict(entry_id=str(data['Id']), db='db_cook.db', table='cookformula',
                            formula_item_id=data['FormulaItemId'], food_item_id=data['FoodItemId'],
                            type_id=data['TypeId'], source_bin_sha256=sha(data['BinData']),
                            field_indices={'formula_item_id': 1, 'food_item_id': 2, 'type_id': 3}))
    item_roster, weapon_roster = [], []
    for data, fb, pos in rows(root, 'db_handbook.db', 'itemhandbook'):
        if fb.scalar(pos, 1) != data['Type']:
            raise ValueError('Item handbook Type SQL/FB mismatch')
        item_roster.append(dict(entry_id=str(data['Id']), db='db_handbook.db', table='itemhandbook',
                                type_id=data['Type'], type_field_index=1,
                                title=value(locale, fb.string(pos, 2), 'title', 2),
                                source_bin_sha256=sha(data['BinData'])))
    for data, fb, pos in rows(root, 'db_handbook.db', 'weaponhandbook'):
        weapon_roster.append(dict(entry_id=str(data['Id']), db='db_handbook.db', table='weaponhandbook',
                                  source_bin_sha256=sha(data['BinData'])))
    # The two observed Term tables contain Chinese literals and optional colors.
    # A string length (e.g. seven bytes for #c79f49) is not a definition vector.
    term_boundary = []
    for table in ['term', 'termconfig']:
        counts, colors = 0, []
        for data, fb, pos in rows(root, 'db_Term.db', table):
            counts += 1
            literal, color = fb.string(pos, 1), fb.string(pos, 2)
            if literal != data['Term'] or (color and not re.fullmatch(r'#[0-9a-fA-F]{6}', color)):
                raise ValueError('Term literal/color schema changed')
            if color:
                colors.append({'entry_id': str(data['Id']), 'field_index': 2, 'literal': color,
                               'source_bin_sha256': sha(data['BinData'])})
        term_boundary.append(dict(table=table, rows=counts, color_fields=colors,
                                  status='NO_KOREAN_DEFINITION_REFERENCE_IN_OBSERVED_FIELDS'))
    after = {p: sha((root / p).read_bytes()) for p in required}
    if after != before:
        raise ValueError('Source database changed while extracting')
    metadata = {}
    for name, keys in [('Misc/BuildInfo.txt', {'Stream', 'Changelist', 'PatchVersion'}),
                       ('Misc/ConfigVersion.txt', {'PublicJsonVersion'})]:
        body = (root / name).read_bytes()
        selected = dict(line.split('=', 1) for line in body.decode('utf-8-sig').splitlines()
                        if '=' in line and line.split('=', 1)[0] in keys)
        metadata[name] = {'sha256': sha(body), 'observed_values': selected}
    return dict(schema='wuwa-handbook-originals.v1', source_sha256=before, cache_metadata=metadata,
                cache_observed_date='2026-10-08', installed_client_match='UNVERIFIED',
                first_release_version='UNVERIFIED', records=bundles, chunks=chunks,
                tutorials=tutorials, cooking=cooking, item_roster=item_roster, weapon_roster=weapon_roster,
                term_boundary=term_boundary)


def write_json(path, data, *, indent=None, trailing_newline=False):
    text = json.dumps(data, ensure_ascii=False, indent=indent,
                      separators=(',', ':') if indent is None else None)
    Path(path).write_text(text + ('\n' if trailing_newline else ''), encoding='utf-8', newline='\n')
