"""Installed generated Config schemas for separated scalar and serialized Flow references.

The registry records observed accessor hashes and exact field domains. It never
infers relationships from equal integer IDs, file names or display labels.
"""
import hashlib
import json
from pathlib import Path
import struct
from wuwa_handbook import FB, connect

REGISTRY = Path(__file__).with_name('typed_flow_schemas.json')


def registry():
    return json.loads(REGISTRY.read_text(encoding='utf8'))


def read_field(fb, root, spec):
    number, kind = spec['field'], spec['type']
    if spec['vector']:
        if kind != 'Int32':
            raise ValueError('Unsupported declared vector type')
        return fb.uint_vector(root, number)
    if kind == 'string':
        return fb.string(root, number)
    if kind == 'Int32':
        return fb.scalar(root, number)
    raise ValueError('Unsupported declared scalar type')


def references(values, encoding):
    if encoding == 'pair_state_vector':
        parts = values['aftertalk'].split(',')
        if not values['aftertalk']:
            return []
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError('Unknown declared AfterTalk serialization')
        return [dict(FlowListName=parts[0], FlowId=int(parts[1]), StateId=state)
                for state in values['aftertalkstateid']]
    if encoding == 'serialized_triple':
        if not values['plot']:
            return []
        parts = values['plot'].split(',')
        if len(parts) != 3 or not all(part.isdigit() for part in parts[1:]):
            raise ValueError('Unknown declared Plot serialization')
        return [dict(FlowListName=parts[0], FlowId=int(parts[1]), StateId=int(parts[2]))]
    if encoding == 'named_triple':
        if 'plotname' in values:
            name, prefix = 'plotname', ''
        else:
            name = next(key for key in values if key.endswith('flowlistname'))
            prefix = name[:-12]
        return [dict(FlowListName=values[name], FlowId=values[prefix+'flowid'],
                     StateId=values[prefix+'stateid'])] if values[name] else []
    raise ValueError('Unknown declared reference encoding')


def load(root, client_scripts=None):
    root = Path(root)
    output, hashes = {}, {}
    for info in registry()['tables'].values():
        file = root / info['database']
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != info['database_sha256']:
            raise ValueError('Typed reference snapshot changed: '+info['database'])
        hashes[info['database']] = digest
        if client_scripts:
            source = Path(client_scripts) / info['schema_source']
            if hashlib.sha256(source.read_bytes()).hexdigest() != info['schema_sha256']:
                raise ValueError('Installed generated schema changed')
        for spec in info['references']:
            consumer = spec.get('consumer')
            if client_scripts and consumer:
                source = Path(client_scripts) / consumer['file']
                if (hashlib.sha256(source.read_bytes()).hexdigest() != consumer['sha256']
                        or consumer['required_expression'] not in source.read_text(encoding='utf8')):
                    raise ValueError('Installed runtime consumer changed')
        with connect(file) as db:
            for number, blob in db.execute(f'SELECT Id,BinData FROM "{info["table"]}"'):
                fb = FB(blob)
                pos = fb.root()
                if fb.scalar(pos, info['id_field']) != number:
                    raise ValueError('Typed reference SQL/native identity changed')
                for spec in info['references']:
                    fields = spec['field_schema']
                    values = {name: read_field(fb, pos, field) for name, field in fields.items()}
                    refs = references(values, spec['encoding'])
                    if not refs:
                        continue
                    field = next(iter(fields.values()))['field']
                    key = f'config:{info["database"]}/{info["table"]}/{number}/FB{field}'
                    output[key] = dict(value={'references': refs}, metadata=dict(
                        kind='config', database=info['database'], table=info['table'],
                        id=number, field=field, title_key='', title='', encoding='typed_fields',
                        reference_encoding=spec['encoding'], schema_fields=fields,
                        schema_source=info['schema_source'], schema_sha256=info['schema_sha256'],
                        consumer=spec.get('consumer'), native_values=values,
                        blob_sha256=hashlib.sha256(blob).hexdigest()))
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError('Typed source changed during decode')
    return output, hashes


def independent_value(root, owner):
    """Separate manual struct replay; does not invoke FB or exporter decoding."""
    info = registry()['tables'][owner['database']+'/'+owner['table']]
    with connect(Path(root)/owner['database']) as db:
        blob = db.execute(f'SELECT BinData FROM "{owner["table"]}" WHERE Id=?', (owner['id'],)).fetchone()[0]
    if hashlib.sha256(blob).hexdigest() != owner['blob_sha256']:
        raise ValueError('Typed owner byte identity failed')
    def scalar(fmt, at):
        if at < 0 or at+struct.calcsize('<'+fmt) > len(blob):
            raise ValueError('Typed manual bounds')
        return struct.unpack_from('<'+fmt, blob, at)[0]
    pos = scalar('I', 0)
    vt = pos-scalar('i', pos)
    def at(field):
        if 4+field*2 >= scalar('H', vt):
            return None
        off = scalar('H', vt+4+field*2)
        return pos+off if off else None
    identity = at(info['id_field'])
    if identity is None or scalar('i', identity) != owner['id']:
        raise ValueError('Typed manual SQL identity failed')
    expected = next(spec for spec in info['references']
                    if spec['field_schema'] == owner['schema_fields'])
    if expected['encoding'] != owner['reference_encoding']:
        raise ValueError('Declared typed owner encoding failed')
    if owner['schema_sha256'] != info['schema_sha256'] or owner['consumer'] != expected['consumer']:
        raise ValueError('Declared source schema failed')
    values = {}
    for name, spec in expected['field_schema'].items():
        slot = at(spec['field'])
        if slot is None:
            values[name] = [] if spec['vector'] else '' if spec['type']=='string' else 0
        elif spec['vector']:
            target = slot+scalar('I', slot)
            values[name] = [scalar('i', target+4+4*i) for i in range(scalar('I', target))]
        elif spec['type']=='string':
            target = slot+scalar('I', slot)
            length = scalar('I', target)
            if target+4+length >= len(blob) or blob[target+4+length] != 0:
                raise ValueError('Typed manual string bounds')
            values[name] = blob[target+4:target+4+length].decode('utf8')
        else:
            values[name] = scalar('i', slot)
    if values != owner['native_values']:
        raise ValueError('Typed owner native values differ')
    # Domain reconstruction is independent of references() above.
    encoding = expected['encoding']
    if encoding == 'pair_state_vector':
        parts = values['aftertalk'].split(',')
        refs = [dict(FlowListName=parts[0], FlowId=int(parts[1]), StateId=v)
                for v in values['aftertalkstateid']]
    elif encoding == 'serialized_triple':
        parts = values['plot'].split(',')
        refs = [dict(FlowListName=parts[0], FlowId=int(parts[1]), StateId=int(parts[2]))]
    else:
        name = 'plotname' if 'plotname' in values else next(n for n in values if n.endswith('flowlistname'))
        prefix = '' if name=='plotname' else name[:-12]
        refs = [dict(FlowListName=values[name], FlowId=values[prefix+'flowid'], StateId=values[prefix+'stateid'])]
    return {'references': refs}
