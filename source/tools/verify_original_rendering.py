"""Compare built lore HTML with preserved settings, including exact punctuation/spacing.

Read-only QA. HTMLParser collects DOM text through inline links and spans; it does
not normalize whitespace, quotes, line endings, or punctuation. Rendering rules
below mirror the intentional game-markup removal, independently of Markdown.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr'}
EXCLUDED = {'name', 'title', 'type', 'birthday', 'sex'}
PROFILE = {'info', 'talent_name', 'talent_document', 'talent_certification'}
EXTRACTION_SEQUENCE_NOTE = '원본 대화 순서가 없는 대화 항목을 참조합니다. 실제 항목만 수록했으며 누락 참조는 대화순서_참조누락.csv에 기록했습니다.'
EXTRACTION_READING_NOTE = '이 장면에는 순서 정보가 확인되지 않은 대화 항목이 포함되어 있다.'


class ReadingTemplatePage(HTMLParser):
    """Check custom-reader boundaries independently of source-text collection."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.errors=[];self.disclosures=[];self.summary=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);classes=set(a.get('class','').split());kind=a.get('data-reading-template')
        boundary=kind=='reader' and {'rw-reader','not-content'}<=classes
        inside=boundary or any(x['boundary'] for x in self.stack)
        if kind=='reader' and not boundary:self.errors.append('reader boundary classes missing')
        if classes & {'original-row','quest-source-line'}:
            if kind!='row' or 'rw-source-row' not in classes:self.errors.append('source row common template missing')
            if not inside:self.errors.append('source row outside isolated reader boundary')
        if 'source-section' in classes and not boundary:self.errors.append('source scene common reader boundary missing')
        technical=bool(classes & {'source-details','mission-scene-index','mission-reference-scenes','quest-info','quest-scene-info'})
        disclosure=None
        if kind=='disclosure' or technical:
            if tag!='details' or kind!='disclosure' or 'rw-disclosure' not in classes:self.errors.append('disclosure common template missing')
            disclosure={'summaries':0};self.disclosures.append(disclosure)
        summary=None
        if tag=='summary' and self.stack and self.stack[-1]['disclosure'] is not None:
            self.stack[-1]['disclosure']['summaries']+=1;summary=[];self.summary=summary
        if tag not in VOID:self.stack.append({'tag':tag,'boundary':boundary,'disclosure':disclosure,'summary':summary})
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_data(self,text):
        if self.summary is not None:self.summary.append(text)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i]['tag']==tag:
                removed=self.stack[i:];del self.stack[i:]
                for element in removed:
                    if element['summary'] is not None:
                        if re.match(r'^\s*[>›▶▸▹▷→]', ''.join(element['summary'])):self.errors.append('disclosure summary has literal leading arrow')
                        self.summary=None
                break
    def finish(self):
        for disclosure in self.disclosures:
            if disclosure['summaries']!=1:self.errors.append('disclosure must have one immediate summary')
        return self.errors


class LorePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = []
        self.field = None
        self.pre = None
        self.paragraph = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        if tag == 'section' and 'lore-field' in classes:
            if self.field is not None:
                raise ValueError('Nested lore-field section')
            self.field = {'ids': [a.get('id')], 'raw': [], 'paragraphs': []}
            self.fields.append(self.field)
        elif self.field is not None and a.get('id', '').startswith('field-'):
            self.field['ids'].append(a['id'])
        if self.field is not None and tag == 'pre':
            self.pre = []
            self.field['raw'].append(self.pre)
        visible = ('lore-source-text' in classes and 'rw-original' in classes)
        if self.field is not None and tag == 'p' and any(v[2] for v in self.stack):
            self.paragraph = []
            self.field['paragraphs'].append(self.paragraph)
        if tag not in VOID:
            self.stack.append((tag, self.field if tag == 'section' and 'lore-field' in classes else None, visible))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.pre = None
        if tag == 'p':
            self.paragraph = None
        # Built HTML must have matching structural tags; recover only to report
        # resulting text differences rather than silently ignoring later fields.
        for n in range(len(self.stack) - 1, -1, -1):
            if self.stack[n][0] == tag:
                removed = self.stack[n:]
                del self.stack[n:]
                if any(v[1] is not None for v in removed):
                    self.field = None
                break

    def handle_data(self, data):
        if self.pre is not None:
            self.pre.append(data)
        if self.paragraph is not None:
            self.paragraph.append(data)


def clean(value):
    value = re.sub(r'<br\s*/?\s*>', '\n', value, flags=re.I)
    return re.sub(r'</?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>', '', value)


def visible_text(raw):
    # The generator turns recognized te hyperlinks into anchors. Their visible
    # text is cleaned independently, while all other literal markup is escaped.
    out, last = [], 0
    for m in re.finditer(r'<te\s+href[=\s]+["\']?(\d+)["\']?\s*>(.*?)</te>', raw, re.S):
        out.extend((clean(raw[last:m.start()]), clean(m[2])))
        last = m.end()
    return ''.join(out) + clean(raw[last:])


def paragraph_texts(raw):
    return [visible_text(s) for s in re.split(r'(\n\s*\n)', raw)[::2]]


def mismatch(actual, expected):
    offset = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected)))
    return {'actualLength': len(actual), 'expectedLength': len(expected),
            'firstDifference': offset, 'actualContext': actual[max(0, offset-24):offset+40],
            'expectedContext': expected[max(0, offset-24):offset+40]}


def load_curated_sources(site, dist, index):
    """Validate the generated routing map against the preserved index hash.

    The generator extends curated_sources in memory. settings/index.json remains
    the preserved input, so it cannot identify all generated full-text pages.
    """
    manifest = json.loads((site/'settings/manifest.json').read_text(encoding='utf-8'))
    index_bytes = (site/'settings/index.json').read_bytes()
    if manifest.get('hash_normalization', {}).get('index.json') == 'lf':
        index_bytes = index_bytes.decode('utf-8').replace('\r\n','\n').encode('utf-8')
    digest = hashlib.sha256(index_bytes).hexdigest()
    if digest != manifest['files']['index.json']:
        raise ValueError('preserved index SHA differs from manifest')
    artifact = json.loads((dist/'settings/curated-sources.json').read_text(encoding='utf-8'))
    if artifact.get('schema') != 'wuwa-curated-sources.v1':
        raise ValueError('unknown curated routing schema')
    if artifact.get('inputIndexSha256') != digest:
        raise ValueError('curated routing map input index SHA differs')
    mapping = artifact.get('sources')
    if not isinstance(mapping, dict):
        raise ValueError('curated routing map sources must be an object')
    known = {e['id'] for e in index['entries']}
    aliases = index.get('aliases', {})
    for id, slug in mapping.items():
        canonical = aliases.get(id,id)
        if canonical not in known:
            raise ValueError('unknown curated source ID: '+id)
        if not isinstance(slug,str) or not re.fullmatch(r'[0-9a-f]{16}',slug):
            raise ValueError('invalid curated source slug: '+id)
        if hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16] != slug:
            raise ValueError('curated source ID and slug differ: '+id)
    for id, slug in index['curated_sources'].items():
        if mapping.get(id) != slug:
            raise ValueError('preserved curated mapping changed or missing: '+id)
    return {**index['curated_sources'],**mapping}


class QuestPage(HTMLParser):
    """Collect quest-only DOM text, preserving every visible character."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.intros = []
        self.scenes = []
        self.scene = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get('class', '').split())
        if 'quest-section-anchor' in classes:
            self.scene = {'id': a.get('id'), 'lines': [], 'metadata': [], 'notes': []}
            self.scenes.append(self.scene)
        own_capture = False
        if tag == 'p' and 'quest-reading-note' in classes:
            if self.scene is None:
                raise ValueError('Quest reading note outside scene')
            text = []
            self.scene['notes'].append({'text': text, 'ignored': 'data-pagefind-ignore' in a,
                                        'classes': classes})
            self.capture = text
            own_capture = True
        elif tag == 'p' and 'quest-source-line' in classes:
            text = []
            if self.scene is None:
                raise ValueError('Quest line outside scene')
            self.scene['lines'].append({'text': text, 'classes': classes})
            self.capture = text
            own_capture = True
        elif tag == 'pre':
            ancestors = set().union(*(v[1] for v in self.stack)) if self.stack else set()
            if 'quest-info' in ancestors:
                self.capture = []
                self.intros.append(self.capture)
                own_capture = True
            elif 'quest-scene-info' in ancestors:
                if self.scene is None:
                    raise ValueError('Quest metadata outside scene')
                self.capture = []
                self.scene['metadata'].append(self.capture)
                own_capture = True
        if tag not in VOID:
            self.stack.append((tag, classes, own_capture))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for n in range(len(self.stack) - 1, -1, -1):
            if self.stack[n][0] == tag:
                removed = self.stack[n:]
                del self.stack[n:]
                if any(v[2] for v in removed):
                    self.capture = None
                break

    def handle_data(self, data):
        if self.capture is not None:
            self.capture.append(data)


def quest_expected(text):
    # These are the documented source-to-reader transformations in generate.mjs:
    # BOM/CRLF normalization, metadata separation, game-format tag removal, and
    # line trimming. Number, speaker and speech spans contribute literal spaces.
    text = re.sub(r'^\ufeff', '', text)
    text = re.sub(r'\r\n?', '\n', text)
    matches = list(re.finditer(r'^장면 \d+: [^\n]+', text, re.M))
    intro = text[:matches[0].start()] if matches else text
    scenes = []
    for i, match in enumerate(matches):
        segment = text[match.end():matches[i+1].start() if i+1 < len(matches) else len(text)]
        metadata, lines, extraction_note = [], [], False
        for raw in segment.split('\n'):
            if not raw.strip():
                continue
            if raw.strip() == EXTRACTION_SEQUENCE_NOTE:
                extraction_note = True
                continue
            if re.match(r'^(순서 근거:|대화 ID:|대화 묶음)', raw.strip()) or re.fullmatch(r'─+', raw.strip()):
                metadata.append(raw)
                continue
            line = re.sub(r'</?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>', '', raw).strip()
            cls = 'quest-choice' if line.startswith('선택 ') else 'quest-branch' if line.startswith('→') else 'quest-utterance'
            m = re.match(r'^(\[대화ID [^\]]+\])\s*([^:：]+):\s*(.*)$', line)
            if m:
                line = m[1] + ' ' + m[2] + ': ' + m[3]
            lines.append((line, cls))
        scenes.append({'id': 'scene-'+str(i+1), 'metadata': '\n'.join(metadata), 'lines': lines,
                       'extractionNote': extraction_note})
    return intro, scenes


def quest_note_errors(actual, expected):
    errors = []
    notes = actual['notes']
    if len(notes) != int(expected['extractionNote']):
        errors.append('quest extraction status note count differs')
    for note in notes:
        if ''.join(note['text']) != EXTRACTION_READING_NOTE:
            errors.append('quest extraction status note text differs')
        if not note['ignored'] or 'quest-source-line' in note['classes']:
            errors.append('quest extraction status note mixed with indexed game dialogue')
    if any(''.join(line['text']) == EXTRACTION_SEQUENCE_NOTE for line in actual['lines']):
        errors.append('quest extraction memo exposed as a game line')
    return errors


def quest_note_self_tests():
    # Source classification and DOM checks are independent of JS generation.
    from html import escape
    text = ('Title\n장면 1: Test\n순서 근거: Test\n' + EXTRACTION_SEQUENCE_NOTE + '\n'
            '[대화ID 1] 화자: 실제 게임 대사\n화면 문구: 실제 화면 문구\n'
            '  선택 1: 실제 선택\n    → 대화 종료\n게임 편지의 다음 줄\n'
            '[대화ID 2] 화자: ' + EXTRACTION_SEQUENCE_NOTE + '\n')
    expected = quest_expected(text)[1][0]
    preserved = [line for line, _ in expected['lines']]
    if len(preserved) != 6 or '게임 편지의 다음 줄' not in preserved or preserved[-1] != '[대화ID 2] 화자: ' + EXTRACTION_SEQUENCE_NOTE:
        return [{'name': 'game_and_prefixed_lines_preserved', 'status': 'FAIL'}]
    anchor = '<div class="quest-section-anchor" id="scene-1"></div>'
    note = '<p class="quest-reading-note" data-pagefind-ignore>' + EXTRACTION_READING_NOTE + '</p>'
    rows = ''.join('<p class="quest-source-line">' + escape(line) + '</p>' for line in preserved)
    results = [{'name': 'game_and_prefixed_lines_preserved', 'status': 'PASS'}]
    for name, html, corrupt in [('valid_status_note', anchor + note + rows, False),
                                ('missing_status_note_rejected', anchor + rows, True),
                                ('memo_reinserted_as_dialogue_rejected', anchor + note + rows + '<p class="quest-source-line">' + EXTRACTION_SEQUENCE_NOTE + '</p>', True),
                                ('indexed_status_note_rejected', anchor + note.replace(' data-pagefind-ignore', '') + rows, True)]:
        parser = QuestPage(); parser.feed(html)
        errors = quest_note_errors(parser.scenes[0], expected)
        results.append({'name': name, 'status': 'PASS' if bool(errors) == corrupt else 'FAIL'})
    return results


def check_quests(site, dist, stats, errors):
    manifest = json.loads((site/'content-manifest.json').read_text(encoding='utf-8'))
    for quest in manifest:
        relative = 'quests/'+quest['id']+'.html'
        source = (site/'originals'/(quest['id']+'.txt')).read_bytes()
        if hashlib.sha256(source).hexdigest() != quest['source_sha256']:
            errors.append({'page': relative, 'error': 'quest source hash differs'})
            continue
        copied = dist/'originals'/(quest['id']+'.txt')
        if not copied.is_file() or copied.read_bytes() != source:
            errors.append({'page': relative, 'error': 'quest downloadable original bytes differ'})
        path = dist/relative
        if not path.is_file():
            errors.append({'page': relative, 'error': 'missing built quest page'})
            continue
        html = path.read_text(encoding='utf-8')
        template = ReadingTemplatePage(); template.feed(html)
        errors.extend({'page': relative, 'error': error} for error in template.finish())
        parser = QuestPage()
        parser.feed(html)
        intro, scenes = quest_expected(source.decode('utf-8'))
        actual_intros = [''.join(x) for x in parser.intros]
        if actual_intros != [intro]:
            errors.append({'page': relative, 'error': 'quest intro pre differs',
                           **mismatch(actual_intros[0] if actual_intros else '', intro)})
        if len(parser.scenes) != len(scenes):
            errors.append({'page': relative, 'error': 'quest scene count differs',
                           'actualScenes': len(parser.scenes), 'expectedScenes': len(scenes)})
        for n, expected in enumerate(scenes):
            if n >= len(parser.scenes):
                break
            actual = parser.scenes[n]
            if actual['id'] != expected['id']:
                errors.append({'page': relative, 'error': 'quest scene anchor differs', 'scene': n+1})
            errors.extend({'page': relative, 'scene': n+1, 'error': error}
                          for error in quest_note_errors(actual, expected))
            meta = [''.join(x) for x in actual['metadata']]
            expected_meta = [expected['metadata']] if expected['metadata'] else []
            if meta != expected_meta:
                errors.append({'page': relative, 'scene': n+1, 'error': 'quest scene metadata pre differs',
                               **mismatch(meta[0] if meta else '', expected['metadata'])})
            lines = [(''.join(x['text']), next((c for c in ('quest-choice','quest-branch','quest-utterance') if c in x['classes']), None)) for x in actual['lines']]
            if lines != expected['lines']:
                pos = next((i for i,(a,b) in enumerate(zip(lines,expected['lines'])) if a != b), min(len(lines),len(expected['lines'])))
                a = lines[pos] if pos < len(lines) else ('', None)
                b = expected['lines'][pos] if pos < len(expected['lines']) else ('', None)
                errors.append({'page': relative, 'scene': n+1, 'line': pos+1, 'error': 'quest visible line or branch class differs',
                               'actualLines': len(lines), 'expectedLines': len(expected['lines']),
                               'actualClass': a[1], 'expectedClass': b[1], **mismatch(a[0],b[0])})
            stats['questScenes'] += 1
            stats['questVisibleLines'] += len(expected['lines'])
            stats['questMetadataBlocks'] += bool(expected_meta)
            stats['questChoices'] += sum(c == 'quest-choice' for _,c in expected['lines'])
            stats['questBranches'] += sum(c == 'quest-branch' for _,c in expected['lines'])
            stats['questExtractionNotes'] += int(expected['extractionNote'])
        stats['quests'] += 1


def main(dist):
    site = Path(__file__).resolve().parents[2]
    index = json.loads((site/'settings/index.json').read_text(encoding='utf-8'))
    records = {}
    for p in (site/'settings').glob('records-*.json'):
        records.update(json.loads(p.read_text(encoding='utf-8')))
    aliases = index.get('aliases', {})
    entries = {e['id']: e for e in index['entries']}
    canonical = lambda id: aliases.get(id, id)
    errors, stats, cache = [], Counter(), {}

    def check(relative, record_id, only=None, prefix='', scope='sources'):
        row = records.get(canonical(record_id))
        if row is None:
            errors.append({'page': relative, 'record': record_id, 'error': 'missing source record'})
            return
        path = dist/relative
        if path not in cache:
            if not path.is_file():
                errors.append({'page': relative, 'error': 'missing built page'})
                cache[path] = None
            else:
                page = LorePage()
                page.feed(path.read_text(encoding='utf-8'))
                cache[path] = page
        page = cache[path]
        if page is None:
            return
        lookup = {}
        for f in page.fields:
            for id in f['ids']:
                if id in lookup:
                    errors.append({'page': relative, 'field': id, 'error': 'duplicate field anchor'})
                lookup[id] = f
        values = [v for v in row['values'] if v['field'] not in EXCLUDED and (only is None or v['field'] in only)]
        for value in values:
            anchor = 'field-' + prefix + value['field']
            f = lookup.get(anchor)
            stats[scope+'Fields'] += 1
            if f is None:
                errors.append({'page': relative, 'field': anchor, 'error': 'missing field anchor or alias'})
                continue
            raw = value.get('raw') or ''
            actual_raws = [''.join(x) for x in f['raw']]
            if len(actual_raws) != 1 or actual_raws[0] != raw:
                errors.append({'page': relative, 'record': record_id, 'field': anchor,
                               'error': 'raw pre text differs', **mismatch(actual_raws[0] if actual_raws else '', raw)})
            if value['status'] == 'OK':
                expected = paragraph_texts(raw)
                actual = [''.join(x) for x in f['paragraphs']]
                stats['visibleParagraphs'] += len(expected)
                if actual != expected:
                    different = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual),len(expected)))
                    errors.append({'page': relative, 'record': record_id, 'field': anchor,
                                   'error': 'visible original paragraphs differ', 'paragraph': different,
                                   'actualParagraphs': len(actual), 'expectedParagraphs': len(expected),
                                   **mismatch(actual[different] if different < len(actual) else '', expected[different] if different < len(expected) else '')})
            elif f['paragraphs']:
                errors.append({'page': relative, 'field': anchor, 'error': 'non-OK field displays original paragraphs'})

    for person in index['characters']:
        rows = [e for e in index['entries'] if str(e.get('role_id')) == str(person['id'])]
        profile = next((e for e in rows if e['chunk'] == 'profile'), None)
        page = 'people/'+str(person['id'])+'.html'
        if profile:
            check(page, profile['id'], PROFILE, scope='profile')
        for e in rows:
            if e['chunk'] in ('stories', 'goods'):
                row = records[canonical(e['id'])]
                check(page, e['id'], prefix=e['chunk']+'-'+str(row['entry_id'])+'-', scope=e['chunk'])
        stats['people'] += 1
    try:
        curated = load_curated_sources(site, dist, index)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        errors.append({'error': 'invalid generated curated source routing map', 'detail': str(error)})
        curated = dict(index['curated_sources'])
    for id, slug in curated.items():
        if canonical(id) not in entries:
            errors.append({'record': id, 'error': 'unknown generated curated source'})
            continue
        check('sources/'+slug+'.html', id)
        stats['curatedSources'] += 1
    check_quests(site, dist, stats, errors)
    note_tests = quest_note_self_tests()
    errors.extend({'error': 'quest extraction note self-test failed', 'name': test['name']}
                  for test in note_tests if test['status'] != 'PASS')
    report = {'status': 'PASS' if not errors else 'FAIL', 'scope': 'built-lore-and-quest-original-raw-and-visible-text',
              **dict(stats), 'htmlPages': len(cache)+stats['quests'], 'errorsTotal': len(errors),
              'errorsByKind': dict(Counter(e['error'] for e in errors)), 'errors': errors[:30],
              'questNoteSelfTests': note_tests}
    print(json.dumps(report, ensure_ascii=False))
    return bool(errors)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dist', type=Path, default=Path(__file__).resolve().parents[1]/'dist')
    raise SystemExit(main(p.parse_args().dist.resolve()))
