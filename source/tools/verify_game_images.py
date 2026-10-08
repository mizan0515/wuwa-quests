"""Validate the local-game image manifest and published lossless WebP files.

PNG-to-WebP decoded RGBA parity is recorded by the extraction-stage verifier.
This repository check uses only the Python standard library.
"""
import hashlib
import json
import re
from pathlib import Path

import argparse
from html.parser import HTMLParser
from urllib.parse import urlsplit

source = Path(__file__).resolve().parents[1]
image_root = source / 'public/game-images'
manifest = json.loads((image_root / 'provenance.json').read_text(encoding='utf8'))
index = json.loads((source.parent / 'settings/index.json').read_text(encoding='utf8'))
expected = {str(person['id']): person['name'] for person in index['characters']}
hexhash = re.compile(r'[0-9a-f]{64}')
BASE = '/wuwa-quests/'


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def compact_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def no_local_paths(value):
    if isinstance(value, dict):
        assert 'originalPath' not in value
        for child in value.values(): no_local_paths(child)
    elif isinstance(value, list):
        for child in value: no_local_paths(child)
    elif isinstance(value, str):
        assert not re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]|(?:^|/)(?:Users|home)/|\.codex-work|\.game-work', value), value


def dimensions(data):
    assert data[:4] == b'RIFF' and data[8:12] == b'WEBP'
    assert int.from_bytes(data[4:8], 'little') + 8 == len(data)
    pos = 12
    size = None
    lossless = False
    while pos + 8 <= len(data):
        kind = data[pos:pos + 4]
        length = int.from_bytes(data[pos + 4:pos + 8], 'little')
        body = data[pos + 8:pos + 8 + length]
        assert len(body) == length
        if kind == b'VP8X':
            assert len(body) == 10
            size = (1 + int.from_bytes(body[4:7], 'little'),
                    1 + int.from_bytes(body[7:10], 'little'))
        if kind == b'VP8L':
            assert len(body) >= 5 and body[0] == 0x2f
            packed = int.from_bytes(body[1:5], 'little')
            lossless_size = (1 + (packed & 0x3fff),
                             1 + ((packed >> 14) & 0x3fff))
            assert size is None or size == lossless_size
            size = lossless_size
            lossless = True
        pos += 8 + length + (length & 1)
    assert pos == len(data) and size and lossless
    return size


def verify_image(item, kind, image, prefix, reference_field, expected_files):
    filename = f'{prefix}-{item["id"]}-{kind}.webp'
    assert image['url'] == BASE + 'game-images/' + filename
    assert image['referenceField'] == reference_field
    assert image['format'] in ('webp', 'image/webp')
    assert image['assetPath'].startswith('Client/Content/Aki/UI/') and image['assetPath'].endswith('.uasset')
    assert image['reference'].startswith('/Game/Aki/UI/')
    package, object_name = image['reference'].rsplit('.', 1)
    assert image['assetPath'] == 'Client/Content/' + package.removeprefix('/Game/') + '.uasset'
    assert object_name == Path(image['assetPath']).stem
    png_hash = image.get('pngSha256', image.get('sourcePngSha256'))
    assert hexhash.fullmatch(png_hash)
    assert all(hexhash.fullmatch(image[key]) for key in ('sha256', 'rgbaSha256'))
    data = (image_root / filename).read_bytes()
    assert hashlib.sha256(data).hexdigest() == image['sha256']
    assert dimensions(data) == (image['width'], image['height'])
    assert image['sourceParts']
    parts = image['sourceParts']
    assert len({part['assetPath'] for part in parts}) == len(parts)
    # Unreal package references are case-insensitive; preserve each recorded spelling.
    assert any(part['assetPath'].casefold() == image['assetPath'].casefold() for part in parts)
    for part in parts:
        assert part['assetPath'].rsplit('.', 1)[0].casefold() == image['assetPath'].rsplit('.', 1)[0].casefold()
        assert part['assetPath'].endswith(('.uasset', '.uexp', '.ubulk'))
        assert isinstance(part['bytes'], int) and part['bytes'] > 0
        assert hexhash.fullmatch(part['sourceSha256']) and hexhash.fullmatch(part['sourceBundleSha256'])
        assert part['sourceBundleSha256'] == manifest['bundles'][part['bundle']]['sha256']
    assert filename not in expected_files
    expected_files.add(filename)
    return len(data)


def internal_parity(item, internal):
    # Internal SQL extraction proves exact mapping fields and source textures.
    assert item['mapping'] == internal['mapping']
    assert item['name'] == internal['name']
    assert set(item['images']) == set(internal['images'])
    for kind, image in item['images'].items():
        original = internal['images'][kind]
        for key in ('assetPath', 'reference', 'referenceField', 'width', 'height', 'rgbaSha256', 'sourceParts'):
            assert image[key] == original[key], (item['id'], kind, key)
        assert image.get('pngSha256', image.get('sourcePngSha256')) == original['sha256']


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.images = []; self.figures = []; self.figure = None; self.caption = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'figure': self.figure = {'images': [], 'caption': '', 'links': []}
        if tag == 'figcaption': self.caption += 1
        if tag == 'img':
            self.images.append(attrs)
            if self.figure is not None: self.figure['images'].append(attrs)
        if tag == 'a' and self.figure is not None and self.caption: self.figure['links'].append(attrs.get('href', ''))
    def handle_data(self, data):
        if self.figure is not None and self.caption: self.figure['caption'] += data
    def handle_endtag(self, tag):
        if tag == 'figcaption': self.caption -= 1
        if tag == 'figure' and self.figure is not None: self.figures.append(self.figure); self.figure = None


def verify_page(dist, relative, image):
    path = dist / relative
    assert path.is_file(), relative
    page = Page(); page.feed(path.read_text(encoding='utf8'))
    candidates = [figure for figure in page.figures if any(im.get('src') == image['url'] for im in figure['images'])]
    assert candidates, (relative, image['url'])
    for figure in candidates:
        assert figure['caption'].strip()
        assert BASE + 'game-images/provenance.json' in figure['links']
        for im in figure['images']:
            if im.get('src') != image['url']: continue
            assert im.get('alt', '').strip()
            assert int(im['width']) == image['width'] and int(im['height']) == image['height']
    return len(candidates)


def main(dist=None, extraction_map_root=None):
    no_local_paths(manifest)
    assert len(manifest['people']) == len(expected) == 64
    assert {p['id'] for p in manifest['people']} == set(expected)
    expected_files = {'provenance.json'}; count = total = 0; group_counts = {}
    groups = [
        ('people', 'role', 'roleinfo', 4, {'icon': 16, 'portrait': 19}, None, None),
        ('monsters', 'monster', 'monsterinfo', 1, {'icon': 3, 'bossBanner': 4}, 'records-monsters.json', 'extra-monster-map.json'),
        ('npcPeople', 'npc', 'springresource', 3, {'icon': 6}, None, 'extra-npc-map.json'),
        ('geography', 'geography', 'geographyhandbook', 3, {'geography': 4}, 'records-geography.json', 'extra-geography-map.json'),
    ]
    assert len(manifest['monsters']) == 283 and sum(len(p['images']) for p in manifest['monsters']) == 304
    assert len(manifest['npcPeople']) == 1 and len(manifest['geography']) == 48
    for group, prefix, table, name_field, fields, records_file, internal_file in groups:
        items = manifest[group]; assert len({p['id'] for p in items}) == len(items)
        records = read(source.parent / 'settings' / records_file) if records_file else None
        internal = read(extraction_map_root / internal_file) if internal_file and extraction_map_root else None
        internal_items = internal.get('people' if group == 'npcPeople' else group, []) if internal else []
        by_id = {str(p['id']): p for p in internal_items}
        n = 0
        for item in items:
            ident = item['id']; mapping = item['mapping']
            assert mapping['table'] == table and mapping['nameField'] == name_field
            assert hexhash.fullmatch(mapping['dbSha256'])
            assert item['images'] and set(item['images']) <= set(fields)
            if group == 'people':
                assert re.fullmatch(r'\d+', ident) and item['name'] == expected[ident]
                assert str(mapping['id']) == ident and set(item['images']) == {'icon', 'portrait'}
            elif group == 'npcPeople':
                assert ident == 'ab' and item['name'] == '아브' and mapping['id'] == 4 and mapping['referenceField'] == 6
                assert set(item['images']) == {'icon'}
                if internal: internal_parity(item, by_id['abu'])
            else:
                assert re.fullmatch(r'\d+', ident) and str(mapping['id']) == ident
                if internal: internal_parity(item, by_id[ident])
                record = records[item['sourceId']]
                assert record['entry_id'] == ident and record['table'] == table and record['db'] == mapping['db']
                record_name = item.get('sourceRecordName', item['name'])
                assert record_name == record['title']
                name = next(v for v in record['values'] if v['field_index'] == name_field)
                assert name['text_id'] == mapping['nameTextId']
                # Original raw rich text and blank names are preserved in the record;
                # the record's display title is the separately checked public label.
                assert not name['text'] or name['text'] == record_name
                if group == 'monsters':
                    assert item['sourceRecordPresent'] is True and item['sourceRecordSha256'] == compact_sha(record)
                elif 'sourceRecordSha256' in item: assert item['sourceRecordSha256'] == compact_sha(record)
            if group != 'people': assert hexhash.fullmatch(mapping['blobSha256'])
            for kind, image in item['images'].items():
                total += verify_image(item, kind, image, prefix, fields[kind], expected_files); count += 1; n += 1
        group_counts[group] = {'entries': len(items), 'images': n}
    assert {p.relative_to(image_root).as_posix() for p in image_root.rglob('*') if p.is_file()} == expected_files
    checked = 0
    if dist:
        dist = dist.resolve(); curated = read(dist / 'settings/curated-sources.json')['sources']
        assert curated == read(source / 'public/settings/curated-sources.json')['sources']
        for group in ('monsters', 'geography'):
            for item in manifest[group]:
                assert item['sourceId'] in curated
                images = item['images']; image = images.get('geography') or images.get('bossBanner') or images['icon']
                checked += verify_page(dist, 'sources/' + curated[item['sourceId']] + '.html', image)
        for person in manifest['people']: checked += verify_page(dist, 'people/' + person['id'] + '.html', person['images']['portrait'])
        ab = manifest['npcPeople'][0]; checked += verify_page(dist, 'people/ab.html', ab['images']['icon'])
        scar = [item for item in manifest['monsters'] if item['id'] in ('340000050', '330000100')]
        assert len(scar) == 2 and len({p['images']['icon']['url'] for p in scar}) == 2
        for item in scar: checked += verify_page(dist, 'people/scar.html', item['images']['icon'])
        for filename in expected_files:
            assert (dist / 'game-images' / filename).read_bytes() == (image_root / filename).read_bytes()
    print(json.dumps({'status': 'PASS', 'groups': group_counts, 'images': count, 'bytes': total,
        'encoding': 'lossless WebP', 'htmlFiguresChecked': checked, 'distVerified': bool(dist),
        'extractionMapsVerified': bool(extraction_map_root),
        'checks': 'original records; image/source hashes; RIFF/VP8L dimensions; full file inventory; no local paths; optional SQL extraction metadata and HTML figures/captions',
        'limitation': 'Decoded RGBA parity is extraction-stage evidence; this standard-library check verifies its exact recorded hash, not pixel decoding.'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--dist', type=Path)
    parser.add_argument('--extraction-map-root', type=Path, help='Optional private extraction receipts; repository checks run without them.')
    args = parser.parse_args()
    main(args.dist, args.extraction_map_root)
