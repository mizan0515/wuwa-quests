"""Validate the local-game image manifest and published lossless WebP files.

PNG-to-WebP decoded RGBA parity is recorded by the extraction-stage verifier.
This repository check uses only the Python standard library.
"""
import hashlib
import json
import re
from pathlib import Path

source = Path(__file__).resolve().parents[1]
image_root = source / 'public/game-images'
manifest = json.loads((image_root / 'provenance.json').read_text(encoding='utf8'))
index = json.loads((source.parent / 'settings/index.json').read_text(encoding='utf8'))
expected = {str(person['id']): person['name'] for person in index['characters']}
people = manifest['people']
assert len(people) == len(expected)
assert {p['id'] for p in people} == set(expected)
hexhash = re.compile(r'[0-9a-f]{64}')


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


count = total = 0
expected_files = {'provenance.json'}
for person in people:
    id = person['id']
    assert re.fullmatch(r'\d+', id)
    assert person['name'] == expected[id]
    assert set(person['images']) == {'icon', 'portrait'}
    mapping = person['mapping']
    assert mapping['table'] == 'roleinfo' and str(mapping['id']) == id
    assert mapping['nameField'] == 4 and hexhash.fullmatch(mapping['dbSha256'])
    for kind, image in person['images'].items():
        filename = f'role-{id}-{kind}.webp'
        assert image['url'] == '/wuwa-quests/game-images/' + filename
        assert image['referenceField'] == (16 if kind == 'icon' else 19)
        assert image['format'] == 'webp'
        assert image['assetPath'].startswith('Client/Content/Aki/UI/')
        assert image['assetPath'].endswith('.uasset')
        assert all(hexhash.fullmatch(image[key])
                   for key in ('sha256', 'pngSha256', 'rgbaSha256'))
        data = (image_root / filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == image['sha256']
        assert dimensions(data) == (image['width'], image['height'])
        assert image['sourceParts']
        for part in image['sourceParts']:
            assert hexhash.fullmatch(part['sourceSha256'])
            assert hexhash.fullmatch(part['sourceBundleSha256'])
            assert part['sourceBundleSha256'] == manifest['bundles'][part['bundle']]['sha256']
        expected_files.add(filename)
        count += 1
        total += len(data)
assert {p.name for p in image_root.iterdir() if p.is_file()} == expected_files
print(json.dumps({'status': 'PASS', 'people': len(people), 'images': count,
                  'bytes': total, 'encoding': 'lossless WebP',
                  'checks': 'site IDs/names; roleinfo image fields; file and source hashes; RIFF/VP8L dimensions'},
                 ensure_ascii=False))
