"""Independent, read-only verification of existing Flow/native corroboration.

Only Python's standard library is used. No producer imports, native script
execution, owner inference or original text generation. The observed cooked
package profile is bounded; unsupported field bodies retain their limits.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
from html.parser import HTMLParser
from html import escape
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

SCHEMA = 'wuwa-native-sequence-references.v1'
EXPECTED_COUNTS = {'states': 23, 'references': 1002, 'proofs': 1030,
                   'newKoreanRows': 0, 'newOwnerAttributions': 0}
HASH = re.compile(r'^[0-9a-f]{64}$')
ASSET = re.compile(r'^Client/Content/Aki/Sequence/(?:[^/\\.][^/\\]*/)*[^/\\]+\.uasset$')
GAME_ASSET = re.compile(r'^/Game/Aki/Sequence/[^\\]+\.[^/\\]+$')
STATE_FIELDS = {'classification', 'externalOwnerStatus', 'sequenceDataAsset',
                'sourceActionPointer', 'sourceFieldPointer', 'flowBlobSha256',
                'nativeSequenceReferences'}
REF_FIELDS = {'kind', 'talkItemPointer', 'talkId', 'speakerId', 'textId',
              'rawKoreanSha256', 'nativeSectionProof', 'nativeObjectPointerChain'}
SECTION_CLASS = '/Script/SequenceDialogue.MovieSceneDialogueSection'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf8')


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def pointer(value, path):
    require(isinstance(path, str) and path.startswith('/'), 'JSON pointer domain')
    for part in path.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def virtual_asset(game):
    require(isinstance(game, str) and GAME_ASSET.fullmatch(game), 'Game asset domain')
    require('/../' not in game and '/./' not in game, 'Game asset traversal')
    return 'Client/Content/' + game[6:].split('.', 1)[0] + '.uasset'


def public_asset(value):
    require(isinstance(value, str) and ASSET.fullmatch(value), 'Native source domain')
    require('/../' not in value and '/./' not in value, 'Native source traversal')


def sanitized(value):
    if isinstance(value, str):
        require(not re.search(r'(?i)(?:[a-z]:[/\\]|file://|\\\\|/(?:home|users)/)', value),
                'Private filesystem path in public corroboration')
    elif isinstance(value, dict):
        for key, child in value.items():
            sanitized(key)
            sanitized(child)
    elif isinstance(value, list):
        for child in value:
            sanitized(child)


class Bytes:
    """Bounded primitives used by the independent byte verifier."""
    def __init__(self, raw, start=0, end=None):
        self.raw = raw
        self.at = start
        self.end = len(raw) if end is None else end
        require(0 <= start <= self.end <= len(raw), 'Byte cursor domain')

    def take(self, size):
        require(isinstance(size, int) and 0 <= size <= self.end - self.at,
                'Native byte bounds')
        result = self.raw[self.at:self.at + size]
        self.at += size
        return result

    def num(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))[0]

    def string(self):
        count = self.num('i')
        require(abs(count) <= 10000000, 'FString length domain')
        raw = self.take(count if count >= 0 else -count * 2)
        if not count:
            return ''
        terminator = b'\0' if count > 0 else b'\0\0'
        require(raw.endswith(terminator), 'FString missing terminator')
        return raw[:-len(terminator)].decode('utf8' if count > 0 else 'utf-16-le')

    def eof(self):
        require(self.at == self.end, 'Native body trailing or missing bytes')


def native_ftext(raw):
    reader = Bytes(raw)
    flags, history = reader.num('I'), reader.num('b')
    require(history == 0, 'FText history domain')
    result = {'flags': flags, 'history_type': history,
              'namespace': reader.string(), 'key': reader.string(),
              'source_string': reader.string()}
    reader.eof()
    return result


def native_range(raw):
    reader = Bytes(raw)
    result = {}
    for name in ('LowerBound', 'UpperBound'):
        kind, value = reader.num('B'), reader.num('i')
        require(kind in (0, 1, 2), 'Frame range bound enum')
        result[name] = {'type': ('Exclusive', 'Inclusive', 'Open')[kind], 'value': value}
    reader.eof()
    return result


def field_bytes(field):
    start, end = field['uexpSpan']
    require(type(start) is int and type(end) is int and 0 <= start < end,
            'Native field span domain')
    raw = bytes.fromhex(field['nativeBytesHex'])
    require(end - start == len(raw), 'Native field span size differs')
    require(sha(raw) == field['nativeBytesSha256'], 'Native field byte hash differs')
    return raw


def triple(ref, fields):
    require(type(ref['talkId']) is int and type(ref['speakerId']) is int,
            'Talk/speaker ID primitive domain')
    require(str(ref['talkId']) == fields['DialogueID']['value']['source_string'],
            'Native DialogueID differs from Flow TalkItem.Id')
    require(ref['speakerId'] == fields['SpeakerID']['value'],
            'Native SpeakerID differs from Flow WhoId')
    require(ref['textId'] == fields['DialogueInfo']['value']['source_string'],
            'Native DialogueInfo differs from Flow TidTalk')


def validate_payload(data, originals):
    sanitized(data)
    require(data['schema'] == SCHEMA, 'Corroboration schema')
    require(data['counts'] == EXPECTED_COUNTS, 'Corroboration declared cohort differs')
    require(len(data['states']) == 23 and len(data['proofs']) == 1030,
            'Corroboration state/proof partition differs')
    require(HASH.fullmatch(data['sourceHashes']['flowDB']), 'Flow database hash domain')
    proofs = data['proofs']
    for key, proof in proofs.items():
        require(HASH.fullmatch(key) and sha(canonical(proof)) == key,
                'Native proof content hash differs')
        public_asset(proof['source'])
        if proof['kind'] == 'WHOLE_NATIVE_DIALOGUE_SECTION_EOF':
            require(proof['class'] == SECTION_CLASS and proof['wholeExportEOF'] is True
                    and proof['independentFTextEOF'] is True, 'Native section class/EOF')
            require(type(proof['exportIndex']) is int and proof['exportIndex'] > 0,
                    'Native section export domain')
            require(HASH.fullmatch(proof['uassetSha256']) and HASH.fullmatch(proof['uexpSha256'])
                    and HASH.fullmatch(proof['exportNativeBytesSha256']), 'Native source hash domain')
            fields = proof['fields']
            require(set(fields) == {'DialogueInfo', 'DialogueID', 'SpeakerID', 'SectionRange'},
                    'Native dialogue field/domain partition differs')
            start, end = proof['exportUexpSpan']
            require(type(start) is int and type(end) is int and 0 <= start < end,
                    'Native export span')
            for name, field in fields.items():
                raw = field_bytes(field)
                require(start <= field['uexpSpan'][0] < field['uexpSpan'][1] <= end,
                        'Native field outside declared export')
                if name in ('DialogueInfo', 'DialogueID'):
                    require(field['type'] == 'TextProperty' and native_ftext(raw) == field['value'],
                            'Native FText value/byte identity differs')
                elif name == 'SpeakerID':
                    require(field['type'] == 'IntProperty' and len(raw) == 4
                            and struct.unpack('<i', raw)[0] == field['value'], 'Native SpeakerID bytes')
                else:
                    require(field['type'] == 'StructProperty' and native_range(raw) == field['value'],
                            'Native frame range byte identity differs')
        elif proof['kind'] == 'EXACT_TYPED_NATIVE_OBJECT_POINTER':
            require(proof['field'] in ('剧情资源', 'GeneratedData', 'SubSequence'),
                    'Unsupported native pointer field domain')
            require(proof['sourceExportWholeEOF'] is True
                    and proof['sourceExportUnsupportedFields'] == 0, 'Native pointer source not closed')
            require(type(proof['sourceExportIndex']) is int and proof['sourceExportIndex'] > 0,
                    'Native pointer export domain')
            require(HASH.fullmatch(proof['sourceUassetSha256'])
                    and HASH.fullmatch(proof['sourceUexpSha256']), 'Native pointer source hash')
            public_asset(proof['targetPackage'])
            require(virtual_asset(proof['target']) == proof['targetPackage'], 'Native pointer target domain')
            start, end = proof['fieldUexpSpan']
            raw = bytes.fromhex(proof['nativeBytesHex'])
            require(type(start) is int and type(end) is int and 0 <= start < end
                    and end - start == len(raw) and sha(raw) == proof['nativeBytesSha256'],
                    'Native pointer field span/hash')
            if len(raw) != 4:
                require(len(raw) >= 4 and struct.unpack_from('<i', raw)[0] >= 0
                        and len(raw) == 4 + 4 * struct.unpack_from('<i', raw)[0],
                        'Native object array framing')
        else:
            raise ValueError('Unsupported public native proof kind')
    references = 0
    unique = set()
    used = set()
    for state_key, state in data['states'].items():
        require(set(state) == STATE_FIELDS, 'Unexpected state metadata/owner field')
        original = originals['states'][state_key]
        require(state['classification'] == original['classification'] == 'unreferenced'
                and state['externalOwnerStatus'] == 'UNPROVEN' and not original['owners'],
                'Native corroboration changed external owner/classification')
        require(HASH.fullmatch(state['flowBlobSha256']), 'Flow state source hash')
        require(state['sourceFieldPointer'] == state['sourceActionPointer'] + '/Params/SequenceDataAsset',
                'Native source action/field pointer differs')
        root = virtual_asset(state['sequenceDataAsset'])
        require(state['nativeSequenceReferences'], 'Native state has no strict reference')
        signatures = set()
        for ref in state['nativeSequenceReferences']:
            require(set(ref) == REF_FIELDS and ref['kind'] == 'EXISTING_FLOW_ORIGINAL_NATIVE_CORROBORATION',
                    'Unexpected reference metadata/body/owner')
            section = proofs[ref['nativeSectionProof']]
            require(section['kind'] == 'WHOLE_NATIVE_DIALOGUE_SECTION_EOF', 'Reference section domain')
            triple(ref, section['fields'])
            require(ref['talkItemPointer'].startswith(state['sourceActionPointer'] + '/Params/TalkItems/'),
                    'Original ShowTalk item pointer outside declared action')
            require(re.fullmatch(re.escape(state['sourceActionPointer']) + r'/Params/TalkItems/\d+',
                                 ref['talkItemPointer']), 'Original TalkItems pointer domain')
            matches = [row for row in original['rows'] if row['status'] == 'OK' and row['kind'] == '대사'
                       and row['action_path'] == state['sourceActionPointer'] and row['talk_id'] == ref['talkId']
                       and row['speaker_id'] == ref['speakerId'] and row['text_id'] == ref['textId']]
            require(len(matches) == 1 and sha(matches[0]['raw'].encode('utf8')) == ref['rawKoreanSha256'],
                    'Native corroboration is not an equal existing Korean original')
            here = root
            chain = ref['nativeObjectPointerChain']
            require(isinstance(chain, list) and len(chain) <= 32 and len(chain) == len(set(chain)),
                    'Native pointer chain domain/cycle')
            for key in chain:
                edge = proofs[key]
                require(edge['kind'] == 'EXACT_TYPED_NATIVE_OBJECT_POINTER' and edge['source'] == here,
                        'Native pointer chain discontinuity')
                here = edge['targetPackage']
                used.add(key)
            require(here == section['source'], 'Native pointer chain does not reach section')
            used.add(ref['nativeSectionProof'])
            signature = (ref['talkItemPointer'], ref['nativeSectionProof'], tuple(chain))
            require(signature not in signatures, 'Duplicate native corroboration occurrence')
            signatures.add(signature)
            unique.add((state_key, ref['talkItemPointer']))
            references += 1
    require(references == 1002 and len(unique) == 261 and used == set(proofs),
            'Native references/items/proofs do not preserve closed cohort')
    return {'states': 23, 'references': references, 'existingOriginalItems': len(unique), 'proofs': len(proofs)}


def fb_string(raw, index):
    reader = Bytes(raw)
    root = reader.num('I')
    vtable = root - Bytes(raw, root, root + 4).num('i')
    vr = Bytes(raw, vtable)
    length, object_size = vr.num('H'), vr.num('H')
    require(4 + 2 * index + 2 <= length and vtable + length <= len(raw)
            and root + object_size <= len(raw), 'FlatBuffer table/vtable bounds')
    slot = root + Bytes(raw, vtable + 4 + 2 * index, vtable + 6 + 2 * index).num('H')
    require(slot != root and root <= slot < root + object_size, 'FlatBuffer field domain')
    at = slot + Bytes(raw, slot, slot + 4).num('I')
    sr = Bytes(raw, at)
    size = sr.num('I')
    text = sr.take(size)
    require(sr.num('B') == 0, 'FlatBuffer string terminator')
    return text.decode('utf8')


def configdb_replay(data, originals, configdb):
    root = configdb if configdb.is_dir() else configdb.parent
    flow = root / 'db_flowState.db' if configdb.is_dir() else configdb
    require(sha(flow.read_bytes()) == data['sourceHashes']['flowDB'], 'Actual Flow database hash differs')
    sql = sqlite3.connect(flow.resolve().as_uri() + '?mode=ro', uri=True)
    count = 0
    try:
        for state_key, state in data['states'].items():
            rows = sql.execute('SELECT StateKey,BinData FROM flowstate WHERE StateKey=?', (state_key,)).fetchall()
            require(len(rows) == 1 and rows[0][0] == state_key, 'Actual Flow SQL state absence/identity')
            blob = bytes(rows[0][1])
            require(sha(blob) == state['flowBlobSha256'] and fb_string(blob, 0) == state_key,
                    'Actual Flow state bytes/FlatBuffer identity')
            actions = json.loads(fb_string(blob, 6))
            action = pointer(actions, state['sourceActionPointer'])
            require(action['Name'] == 'ShowTalk' and pointer(actions, state['sourceFieldPointer'])
                    == state['sequenceDataAsset'], 'Actual typed ShowTalk SequenceDataAsset differs')
            for ref in state['nativeSequenceReferences']:
                item = pointer(actions, ref['talkItemPointer'])
                require(item['Id'] == ref['talkId'] and item.get('WhoId') == ref['speakerId']
                        and item.get('TidTalk') == ref['textId'], 'Actual Flow item/native triple differs')
                count += 1
    finally:
        sql.close()
    keys = sorted({ref['textId'] for state in data['states'].values() for ref in state['nativeSequenceReferences']})
    locales = {}
    for name, digest in data['sourceHashes']['localeDBs'].items():
        require(name in ('lang_multi_text.db', 'lang_multi_text_1sthalf.db'), 'Locale source domain')
        path = root / 'ko' / name
        require(sha(path.read_bytes()) == digest, 'Actual locale database hash differs')
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
            columns = 'Id,Content,RedirectDbIndex' if name == 'lang_multi_text.db' else 'Id,Content'
            found = conn.execute('SELECT ' + columns + ' FROM MultiText WHERE Id IN ('
                                 + ','.join('?' for _ in keys) + ')', keys).fetchall()
            locales[name] = {row[0]: row[1:] for row in found}
    for state_key, state in data['states'].items():
        for ref in state['nativeSequenceReferences']:
            key = ref['textId']
            main = locales['lang_multi_text.db'].get(key)
            half = locales['lang_multi_text_1sthalf.db'].get(key)
            raw = half[0] if half and (main is None or main[1] == 1) else main[0] if main else None
            require(raw is not None and sha(raw.encode('utf8')) == ref['rawKoreanSha256'],
                    'Actual locale redirect/original text differs')
    return {'actualFlowNativeReferences': count, 'actualKoreanTextKeys': len(keys)}


class NativePackage:
    """Independent observed header/import/export and tagged-field identity reader.

    Reads metadata and property framing only. Opaque field bodies are skipped
    by their declared lengths for verification, never interpreted as IDs/text.
    The caller requires full known dialogue/pointer export framing and hashes.
    """
    def __init__(self, path):
        self.uasset = path.read_bytes()
        self.uexp = path.with_suffix('.uexp').read_bytes()
        reader = Bytes(self.uasset)
        require(reader.num('I') == 0x9e2a83c1 and reader.num('i') == -7,
                'Unsupported native package magic/profile')
        for _ in range(3):
            reader.num('i')
        require(reader.num('i') == 0, 'Unsupported native custom-version profile')
        self.header = reader.num('i')
        reader.string()
        reader.num('I')
        name_count, name_at = reader.num('i'), reader.num('i')
        reader.num('i'); reader.num('i')
        export_count, export_at = reader.num('i'), reader.num('i')
        import_count, import_at = reader.num('i'), reader.num('i')
        depends_at = reader.num('i')
        require(0 <= name_count <= 100000 and 0 <= import_count <= 100000
                and 0 <= export_count <= 100000, 'Native table count domain')
        nr = Bytes(self.uasset, name_at)
        self.names = []
        for _ in range(name_count):
            self.names.append(nr.string())
            nr.num('I')
        self.imports = []
        ir = Bytes(self.uasset, import_at, export_at)
        for _ in range(import_count):
            self.imports.append((self.name(ir), self.name(ir), ir.num('i'), self.name(ir)))
        ir.eof()
        require(export_count == 0 or depends_at - export_at == 104 * export_count,
                'Unsupported native export stride')
        self.exports = []
        er = Bytes(self.uasset, export_at, depends_at)
        for _ in range(export_count):
            start = er.at
            class_index = er.num('i')
            er.num('i'); er.num('i')
            outer = er.num('i')
            name = self.name(er)
            flags, size, offset = er.num('I'), er.num('q'), er.num('q')
            self.exports.append({'classIndex': class_index, 'outer': outer, 'name': name,
                                 'flags': flags, 'size': size, 'start': offset - self.header})
            er.take(start + 104 - er.at)
        er.eof()

    def name(self, reader):
        index, number = reader.num('i'), reader.num('i')
        require(0 <= index < len(self.names) and number >= 0, 'Native FName domain')
        return self.names[index] + ('_' + str(number - 1) if number else '')

    def resolve(self, index, seen=None):
        if not index:
            return None
        seen = set() if seen is None else seen
        require(index not in seen, 'Native import outer cycle')
        seen = seen | {index}
        require(-len(self.imports) <= index <= len(self.exports), 'Native object-index domain')
        if index > 0:
            return self.exports[index - 1]['name']
        _, _, outer, name = self.imports[-index - 1]
        return str(self.resolve(outer, seen)) + '.' + name if outer else name

    def properties(self, start, end, prefix=''):
        reader = Bytes(self.uexp, start, end)
        result = {}
        number = 0
        while reader.at < end:
            name = self.name(reader)
            if name == 'None':
                return result, reader.at
            kind = self.name(reader)
            size, array_index = reader.num('i'), reader.num('i')
            require(size >= 0 and array_index >= 0, 'Native property size/index')
            meta = {}
            if kind == 'StructProperty':
                meta['structType'] = self.name(reader)
                reader.take(16)
            elif kind in ('ByteProperty', 'EnumProperty'):
                self.name(reader)
            elif kind == 'BoolProperty':
                require(reader.num('B') in (0, 1), 'Native tagged boolean')
            elif kind in ('ArrayProperty', 'SetProperty'):
                meta['innerType'] = self.name(reader)
            elif kind == 'MapProperty':
                self.name(reader); self.name(reader)
            guid = reader.num('B')
            require(guid in (0, 1), 'Native property GUID domain')
            if guid:
                reader.take(16)
            at = reader.at
            raw = reader.take(size)
            result[prefix + '/' + str(number)] = {'name': name, 'type': kind, 'start': at,
                                                 'end': reader.at, 'raw': raw, **meta}
            number += 1
        raise ValueError('Native tagged property None terminator absent')

    def export_fields(self, index):
        require(type(index) is int and 1 <= index <= len(self.exports), 'Native export index domain')
        ex = self.exports[index - 1]
        start, end = ex['start'], ex['start'] + ex['size']
        props, stop = self.properties(start, end)
        remainder = self.uexp[stop:end]
        require(remainder == b'\0\0\0\0' or (not remainder and ex['flags'] & 0x10),
                'Unsupported native object tail; whole export identity not closed')
        return ex, props, start, end


def native_replay(data, native_root):
    sources = {p['source'] for p in data['proofs'].values()}
    cache = {}
    for path in native_root.rglob('*.uasset'):
        normalized = path.as_posix()
        marker = 'Client/Content/'
        if marker not in normalized:
            continue
        virtual = marker + normalized.split(marker, 1)[1]
        if virtual in sources:
            if virtual in cache:
                require(sha(path.read_bytes()) == sha(cache[virtual].read_bytes()),
                        'Ambiguous native package cache identity')
            else:
                cache[virtual] = path
    require(set(cache) == sources, 'Exact native source package absent from supplied cache')
    packages = {}
    export_cache = {}
    fields_verified = pointers_verified = 0
    for proof in data['proofs'].values():
        source = proof['source']
        if source not in packages:
            packages[source] = NativePackage(cache[source])
        pkg = packages[source]
        section = proof['kind'] == 'WHOLE_NATIVE_DIALOGUE_SECTION_EOF'
        require(sha(pkg.uasset) == proof['uassetSha256' if section else 'sourceUassetSha256']
                and sha(pkg.uexp) == proof['uexpSha256' if section else 'sourceUexpSha256'],
                'Actual native package hash differs')
        index = proof['exportIndex' if section else 'sourceExportIndex']
        key = (source, index)
        if key not in export_cache:
            export_cache[key] = pkg.export_fields(index)
        ex, props, start, end = export_cache[key]
        require(ex['name'] == proof['exportName' if section else 'sourceExportName']
                and pkg.resolve(ex['classIndex']) == proof['class' if section else 'sourceClass'],
                'Actual native export/class identity differs')
        if section:
            require([start, end] == proof['exportUexpSpan']
                    and sha(pkg.uexp[start:end]) == proof['exportNativeBytesSha256'],
                    'Actual native dialogue export bytes differ')
            byname = {p['name']: p for p in props.values()}
            require(len(byname) == len(props), 'Repeated native dialogue field name')
            for name, field in proof['fields'].items():
                actual = byname[name]
                require(actual['type'] == field['type'] and [actual['start'], actual['end']]
                        == field['uexpSpan'] and actual['raw'] == field_bytes(field),
                        'Actual native dialogue property tag/span/body differs')
                if name == 'SectionRange':
                    require(actual['structType'] == 'MovieSceneFrameRange', 'Actual frame struct domain')
                fields_verified += 1
        else:
            require(proof['fieldPointer'] in props, 'Actual native pointer property absent')
            actual = props[proof['fieldPointer']]
            require(actual['name'] == proof['field'] and [actual['start'], actual['end']]
                    == proof['fieldUexpSpan'] and actual['raw'].hex() == proof['nativeBytesHex'],
                    'Actual native object field pointer/span/body differs')
            reader = Bytes(actual['raw'])
            if actual['type'] == 'ObjectProperty':
                targets = [pkg.resolve(reader.num('i'))]
            else:
                require(actual['type'] == 'ArrayProperty' and actual['innerType'] == 'ObjectProperty',
                        'Actual native pointer field type differs')
                count = reader.num('i')
                require(0 <= count <= (reader.end - reader.at) // 4, 'Native pointer array bounds')
                targets = [pkg.resolve(reader.num('i')) for _ in range(count)]
            reader.eof()
            require(proof['target'] in targets, 'Actual native direct import target differs')
            pointers_verified += 1
    return {'actualNativePackages': len(packages), 'actualNativeSectionFields': fields_verified,
            'actualNativePointerFields': pointers_verified, 'actualNativeExportEnvelopes': len(export_cache)}


class GroupHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.states = {}
        self.native = {}
        self.disclosures = Counter()
        self.ids = Counter()
        self.row = None
        self.in_speech = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        parent = self.stack[-1] if self.stack else (None, None, False)
        state = attrs.get('data-dialogue-state', parent[1])
        native = 'data-native-sequence-state' in attrs or parent[2]
        if 'id' in attrs:
            self.ids[attrs['id']] += 1
        if 'data-dialogue-state' in attrs:
            require(state not in self.states, 'Duplicate rendered state section')
            self.states[state] = []
        if 'data-native-sequence-state' in attrs:
            require(attrs['data-native-sequence-state'] == state, 'Rendered native disclosure state differs')
            self.disclosures[state] += 1
        if 'data-native-section' in attrs:
            require(native and state is not None, 'Rendered native reference outside state disclosure')
            self.native.setdefault(state, []).append((attrs['data-native-section'],
                                                      attrs.get('data-native-flow-talk'),
                                                      attrs.get('data-native-flow-text')))
        if 'data-dialogue-source-key' in attrs:
            require(state is not None and self.row is None, 'Rendered original row outside state or nested')
            self.row = {'key': attrs['data-dialogue-source-key'], 'id': attrs.get('id'),
                        'state': state, 'depth': len(self.stack), 'text': ''}
        if self.row and 'rw-source-body' in attrs.get('class', '').split():
            self.in_speech = True
            self.speech_depth = len(self.stack)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append((tag, state, native))

    def handle_endtag(self, tag):
        if not self.stack:
            return
        # Built HTML is well-formed; tolerate only implicit end tags in surrounding site chrome.
        positions = [i for i, item in enumerate(self.stack) if item[0] == tag]
        if not positions:
            return
        at = positions[-1]
        if self.row and self.in_speech and at == self.speech_depth:
            self.in_speech = False
        if self.row and at == self.row['depth']:
            self.states[self.row['state']].append((self.row['id'], self.row['key'], self.row['text']))
            self.row = None
        del self.stack[at:]

    def handle_data(self, value):
        if self.row and self.in_speech:
            self.row['text'] += value


def dist_replay(data, originals, dist):
    state_count = row_count = native_count = 0
    for group in originals['groups']:
        path = dist / 'dialogue-sources' / (group['id'] + '.html')
        require(path.is_file(), 'Rendered original group absent: ' + group['id'])
        parser = GroupHTML()
        parser.feed(path.read_text(encoding='utf8'))
        parser.close()
        require(set(parser.states) == set(group['states']), 'Rendered original state partition differs')
        for state_key in group['states']:
            anchor = 'state-' + sha(state_key.encode('utf8'))[:16]
            require(parser.ids[anchor] == 1, 'Original state anchor absent/duplicated')
            rows = originals['states'][state_key]['rows']
            expected = [(anchor + '-row-' + str(i), row['text_id'], row['text'])
                        for i, row in enumerate(rows) if row['status'] == 'OK']
            require(parser.states[state_key] == expected, 'Original row body/order/key/anchor differs')
            require(all(parser.ids[row[0]] == 1 for row in expected), 'Original row anchor duplicated')
            if state_key in data['states']:
                refs = data['states'][state_key]['nativeSequenceReferences']
                markers = [(r['nativeSectionProof'], str(r['talkId']), r['textId']) for r in refs]
                require(parser.disclosures[state_key] == 1 and parser.native.get(state_key) == markers,
                        'Rendered native disclosure/reference absence or domain/order differs')
                native_count += len(markers)
            else:
                require(not parser.native.get(state_key) and not parser.disclosures[state_key],
                        'Rendered native disclosure on an unproved state')
            state_count += 1
            row_count += len(expected)
    require(native_count == 1002, 'Rendered native corroboration cohort differs')
    return {'renderedOriginalStates': state_count, 'renderedOriginalRows': row_count,
            'renderedNativeReferences': native_count}


def html_state_check(parser, data, originals, state_key):
    """Small shared assertion used by semantic HTML mutation canaries."""
    anchor = 'state-' + sha(state_key.encode('utf8'))[:16]
    require(parser.ids[anchor] == 1, 'HTML canary original state anchor')
    expected = [(anchor + '-row-' + str(i), row['text_id'], row['text'])
                for i, row in enumerate(originals['states'][state_key]['rows']) if row['status'] == 'OK']
    require(parser.states.get(state_key) == expected, 'HTML canary original body/order/anchors')
    refs = data['states'][state_key]['nativeSequenceReferences']
    markers = [(r['nativeSectionProof'], str(r['talkId']), r['textId']) for r in refs]
    require(parser.disclosures[state_key] == 1 and parser.native.get(state_key) == markers,
            'HTML canary native absence/domain/order')


def rekey(data, key):
    proof = data['proofs'].pop(key)
    replacement = sha(canonical(proof))
    data['proofs'][replacement] = proof
    for state in data['states'].values():
        for ref in state['nativeSequenceReferences']:
            if ref['nativeSectionProof'] == key:
                ref['nativeSectionProof'] = replacement
            ref['nativeObjectPointerChain'] = [replacement if item == key else item
                                               for item in ref['nativeObjectPointerChain']]


def self_test(data, originals):
    tests = []
    def reject(label, fn):
        try:
            fn()
        except (ValueError, KeyError, IndexError, UnicodeError, struct.error):
            tests.append(label)
            return
        raise ValueError('Semantic negative self-test accepted: ' + label)
    def mutate(label, change):
        bad = copy.deepcopy(data)
        change(bad)
        reject(label, lambda: validate_payload(bad, originals))
    state_key = next(iter(data['states']))
    key = data['states'][state_key]['nativeSequenceReferences'][0]['nativeSectionProof']
    def ref_change(field, value):
        return lambda bad: bad['states'][state_key]['nativeSequenceReferences'][0].__setitem__(field, value)
    ref = data['states'][state_key]['nativeSequenceReferences'][0]
    mutate('TalkItem.Id mismatch', ref_change('talkId', ref['talkId'] + 1))
    mutate('WhoId mismatch', ref_change('speakerId', ref['speakerId'] + 1))
    mutate('TidTalk mismatch', ref_change('textId', ref['textId'] + '_invalid'))
    mutate('original Korean hash mismatch', ref_change('rawKoreanSha256', '0' * 64))
    mutate('typed native pointer chain absence', ref_change('nativeObjectPointerChain', []))
    mutate('explicit native source action mismatch', lambda bad: bad['states'][state_key].__setitem__('sourceActionPointer', '/999'))
    mutate('unproved owner injection', lambda bad: bad['states'][state_key].__setitem__('owners', ['quest:1']))
    mutate('classification promotion', lambda bad: bad['states'][state_key].__setitem__('classification', 'quest'))
    mutate('missing state cohort', lambda bad: bad['states'].pop(state_key))
    mutate('private path injection', lambda bad: bad['states'][state_key].__setitem__('sequenceDataAsset', 'Q:/private/game.uasset'))
    def frame(bad):
        bad['proofs'][key]['fields']['SectionRange']['value']['LowerBound']['value'] += 1
        rekey(bad, key)
    mutate('frame value vs native bytes (rehash proof)', frame)
    def source(bad):
        bad['proofs'][key]['source'] = 'Client/Content/Aki/Sequence/Unknown/Unknown.uasset'
        rekey(bad, key)
    mutate('native source mismatch (rehash proof)', source)
    mutate('proof hash mismatch', lambda bad: bad['proofs'][key].__setitem__('exportName', 'Invalid'))
    def pointer_bytes(bad):
        edge = ref['nativeObjectPointerChain'][0]
        bad['proofs'][edge]['nativeBytesHex'] += '00'
        rekey(bad, edge)
    mutate('native pointer byte/span mismatch (rehash proof)', pointer_bytes)
    def ftext_bytes(bad):
        field = bad['proofs'][key]['fields']['DialogueInfo']
        field['nativeBytesHex'] = field['nativeBytesHex'][:-2] + '01'
        field['nativeBytesSha256'] = sha(bytes.fromhex(field['nativeBytesHex']))
        rekey(bad, key)
    mutate('FText terminator mismatch with matching byte/proof hashes', ftext_bytes)
    # Known four-key mismatch fixture: native editor IDs 3..6 vs actual Flow IDs 2..5.
    # This does not add these keys to the closed public cohort or infer an owner.
    for number, tid in enumerate(('DYHD_28_3', 'DYHD_28_4', 'DYHD_28_5', 'DYHD_28_6'), 3):
        fake_ref = {'talkId': number - 1, 'speakerId': 100040, 'textId': tid}
        fields = {'DialogueID': {'value': {'source_string': str(number)}},
                  'SpeakerID': {'value': 100040}, 'DialogueInfo': {'value': {'source_string': tid}}}
        reject('excluded native DialogueID fixture ' + tid, lambda: triple(fake_ref, fields))
    sample = next(p for p in data['proofs'].values() if p['kind'] == 'WHOLE_NATIVE_DIALOGUE_SECTION_EOF')
    raw = field_bytes(sample['fields']['DialogueInfo'])
    reject('native FText trailing bytes', lambda: native_ftext(raw + b'\0'))
    reject('native FText truncated bytes', lambda: native_ftext(raw[:-1]))
    reject('native frame enum domain', lambda: native_range(b'\xff' + b'\0' * 9))
    anchor = 'state-' + sha(state_key.encode('utf8'))[:16]
    transcript = ''.join('<p id="' + anchor + '-row-' + str(i)
                         + '" data-dialogue-source-key="' + escape(row['text_id'], quote=True)
                         + '"><span class="rw-source-body">' + escape(row['text']) + '</span></p>'
                         for i, row in enumerate(originals['states'][state_key]['rows']) if row['status'] == 'OK')
    markers = ''.join('<li data-native-section="' + r['nativeSectionProof']
                      + '" data-native-flow-talk="' + str(r['talkId'])
                      + '" data-native-flow-text="' + escape(r['textId'], quote=True) + '"></li>'
                      for r in data['states'][state_key]['nativeSequenceReferences'])
    body = '<div id="' + anchor + '"></div><section data-dialogue-state="' + escape(state_key, quote=True)
    body += '">' + transcript + '<details data-native-sequence-state="' + escape(state_key, quote=True)
    body += '"><ul>' + markers + '</ul></details></section>'
    def parse_check(raw):
        parser = GroupHTML()
        parser.feed(raw)
        parser.close()
        html_state_check(parser, data, originals, state_key)
    parse_check(body)
    reject('HTML native reference absent', lambda: parse_check(body.replace(markers, '')))
    reject('HTML native DialogueID differs', lambda: parse_check(body.replace('data-native-flow-talk="', 'data-native-flow-talk="999')))
    reject('HTML native TidTalk differs', lambda: parse_check(body.replace('data-native-flow-text="', 'data-native-flow-text="invalid')))
    reject('HTML original row anchor differs', lambda: parse_check(body.replace(anchor + '-row-0', anchor + '-row-999')))
    reject('HTML original source body mutated', lambda: parse_check(body.replace('class="rw-source-body">', 'class="rw-source-body">extra')))
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--configdb', type=Path)
    parser.add_argument('--native-root', type=Path)
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--report', type=Path, help='Optional caller-chosen verification JSON output')
    args = parser.parse_args()
    repo = args.repo.resolve()
    settings = repo / 'settings'
    raw = (settings / 'native-sequence-references.json').read_bytes()
    manifest = load(settings / 'manifest.json')
    require(manifest['files'].get('native-sequence-references.json') == sha(raw),
            'Public corroboration manifest byte pin absent/different')
    original_raw = (settings / 'dialogue-attribution.json').read_bytes()
    require(manifest['files']['dialogue-attribution.json'] == sha(original_raw),
            'Original attribution manifest byte pin differs')
    data, originals = json.loads(raw), json.loads(original_raw)
    counts = validate_payload(data, originals)
    if args.configdb:
        counts.update(configdb_replay(data, originals, args.configdb.resolve()))
    if args.native_root:
        counts.update(native_replay(data, args.native_root.resolve()))
    if args.dist:
        counts.update(dist_replay(data, originals, args.dist.resolve()))
    tests = self_test(data, originals) if args.self_test else []
    report = {'schema': 'wuwa-native-sequence-verification.v1', 'status': 'PASS',
              'sourceCorroborationSha256': sha(raw), 'originalAttributionSha256': sha(original_raw),
              'counts': counts, 'negativeSelfTests': tests,
              'verifiedSurfaces': {'publicPayload': True, 'actualSQL': bool(args.configdb),
                                   'actualNativeBytes': bool(args.native_root), 'renderedHTML': bool(args.dist)},
              'limits': ['Existing originals and native source corroboration only; no new Korean body or owner.',
                         'Opaque native field bodies remain unsupported; export envelope checks do not close all native graphs.',
                         'No game-script execution or runtime reachability inference.']}
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, IndexError, UnicodeError, struct.error, OSError, sqlite3.Error) as error:
        print('Native sequence verification FAIL: ' + str(error), file=sys.stderr)
        sys.exit(1)
