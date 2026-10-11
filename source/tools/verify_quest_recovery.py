"""Independently check recovery IDs/raw strings, preserved prefixes and coverage.

Without --configdb, check the committed source records and original hashes.
With --configdb, decode source action fields independently of the exporter and
verify every supported text reference in every added state, including captions.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from wuwa_handbook import FB, clean, connect, load_locale


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def verify(repo, configdb=None):
    repo = Path(repo)
    report = json.loads((repo / 'settings/quest-supplements.json').read_text(encoding='utf-8'))
    manifest = json.loads((repo / 'content-manifest.json').read_text(encoding='utf-8'))
    source_quests = report['quests']
    errors, stats = [], Counter()
    if set(source_quests) != {q['id'] for q in manifest}:
        errors.append('Recovery quest inventory differs')
    locale, states, captions = None, {}, {}
    if configdb:
        configdb = Path(configdb)
        for name, expected in report['source_databases'].items():
            if sha((configdb / name).read_bytes()) != expected:
                errors.append('Source hash differs: ' + name)
        locale = load_locale(configdb)
        with connect(configdb / 'db_flowState.db') as db:
            for key, blob in db.execute('SELECT StateKey,BinData FROM flowstate'):
                fb = FB(blob)
                states[key] = json.loads(fb.string(fb.root(), 6))
        with connect(configdb / 'db_cgVedio.db') as db:
            for key, video, blob in db.execute('SELECT CaptionId,CgName,BinData FROM videocaption'):
                fb = FB(blob)
                captions.setdefault(video, []).append(fb.string(fb.root(), 4))
    for quest in manifest:
        qid = quest['id']
        data = (repo / 'originals' / (qid + '.txt')).read_bytes()
        entry = source_quests[qid]
        baseline = data[:entry['baseline_bytes']]
        if sha(baseline) != entry['baseline_sha256']:
            errors.append(qid + ': original prefix changed')
        if sha(data) != quest['source_sha256'] or sha(data) != entry['result_sha256']:
            errors.append(qid + ': original hash differs')
        normalized = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
        blocks = list(re.finditer(r'^장면 (\d+): (.+)$', normalized, re.M))
        ids = [int(block[1]) for block in blocks]
        if ids != list(range(1, len(blocks) + 1)):
            errors.append(qid + ': scene sequence changed')
        if len(blocks) != entry['baseline_scenes'] + len(entry['scenes']):
            errors.append(qid + ': scene inventory differs')
        by_scene = {int(b[1]): normalized[b.start():blocks[i+1].start() if i+1 < len(blocks) else len(normalized)] for i, b in enumerate(blocks)}
        supplemental_states = [scene['state_key'] for scene in entry['scenes']]
        if len(set(supplemental_states)) != len(supplemental_states) or set(supplemental_states) & set(entry['baseline_states']):
            errors.append(qid + ': duplicated baseline/supplement state')
        if configdb:
            for key in set(entry['reachable_states']) - set(entry['baseline_states']) - set(supplemental_states):
                tids = []
                for obj in dictionaries(states[key]):
                    if obj.get('Name') == 'ShowTalk':
                        for item in obj.get('Params', {}).get('TalkItems', []):
                            tids.append(item.get('TidTalk'))
                            tids.extend(o.get('TidTalkOption') for o in item.get('Options', []))
                    elif obj.get('Name') == 'ShowCenterText':
                        tids.append(obj.get('Params', {}).get('TidCenterText'))
                    elif obj.get('Name') == 'PlayMovie':
                        tids.extend(captions.get(obj.get('Params', {}).get('VideoName'), []))
                if any(locale.get(tid, ('', ''))[0].strip() for tid in tids):
                    errors.append(qid + ': reachable Korean scene omitted: ' + key)
        for scene in entry['scenes']:
            key = scene['state_key']
            text = by_scene.get(scene['scene'], '')
            if key not in entry['reachable_states'] or not scene['proof']:
                errors.append(qid + ': source ownership proof missing: ' + key)
            if '대화 ID: ' + key not in text:
                errors.append(qid + ': state missing from original')
            for row in scene['rows']:
                if clean(row['raw']) != row['text']:
                    errors.append(qid + ': raw/reading text differs: ' + row['text_id'])
                if locale is not None and (row['raw'], row['source']) != locale.get(row['text_id'], ('', '')):
                    errors.append(qid + ': Korean source string differs: ' + row['text_id'])
                if row['status'] == 'OK' and row['text'] not in text:
                    errors.append(qid + ': text missing from original: ' + row['text_id'])
                stats['rows'] += 1
                stats[row['kind']] += 1
            if configdb:
                expected = []
                for obj in dictionaries(states[key]):
                    if obj.get('Name') == 'ShowTalk':
                        for item in obj.get('Params', {}).get('TalkItems', []):
                            if item.get('TidTalk'):
                                expected.append(item['TidTalk'])
                            for option in item.get('Options', []):
                                if option.get('TidTalkOption'):
                                    expected.append(option['TidTalkOption'])
                    elif obj.get('Name') == 'ShowCenterText' and obj.get('Params', {}).get('TidCenterText'):
                        expected.append(obj['Params']['TidCenterText'])
                    elif obj.get('Name') == 'PlayMovie':
                        expected.extend(captions.get(obj.get('Params', {}).get('VideoName'), []))
                if Counter(expected) != Counter(row['text_id'] for row in scene['rows']):
                    errors.append(qid + ': source text reference coverage differs: ' + key)
            stats['scenes'] += 1
        stats['quests'] += 1
        stats['changed_quests'] += bool(entry['scenes'])
    for key in ('rows', 'scenes', 'quests', 'changed_quests'):
        if stats[key] != report['summary'].get(key, 0):
            errors.append('Summary differs: ' + key)
    return {'status': 'FAIL' if errors else 'PASS', 'sourceDbChecked': bool(configdb), 'stats': dict(stats), 'errors': errors[:30]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--configdb', type=Path)
    args = parser.parse_args()
    result = verify(args.repo, args.configdb)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(result['status'] != 'PASS')
