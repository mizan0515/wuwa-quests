"""Verify that the tracked publication surface matches the current build."""
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify(dist, site):
    errors = []
    files = sorted(path for path in dist.rglob('*') if path.is_file())
    if not (dist / 'index.html').is_file():
        return {'status': 'FAIL', 'files': len(files), 'errors': ['Missing build index.html']}
    forbidden = {'.git', 'docs', 'scripts', 'source'}
    expected = set()
    for path in files:
        relative = path.relative_to(dist)
        if relative.parts[0] in forbidden or relative.parts[0].startswith('.env'):
            errors.append('Unexpected publication path: ' + relative.as_posix())
            continue
        expected.add(relative)
        target = site / relative
        if not target.resolve().is_relative_to(site.resolve()):
            errors.append('Publication path outside site: ' + relative.as_posix())
        elif not target.is_file():
            errors.append('Missing published file: ' + relative.as_posix())
        elif sha256(path) != sha256(target):
            errors.append('Published file differs: ' + relative.as_posix())
    # Only exported directories belong to this check; project documents stay separate.
    for entry in dist.iterdir():
        if entry.is_dir() and entry.name not in forbidden:
            for path in (site / entry.name).rglob('*'):
                if path.is_file() and path.relative_to(site) not in expected:
                    errors.append('Obsolete published file: ' + path.relative_to(site).as_posix())
    return {'status': 'FAIL' if errors else 'PASS', 'files': len(files), 'errors': errors}


if __name__ == '__main__':
    source = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=source / 'dist')
    parser.add_argument('--site', type=Path, default=source.parent)
    args = parser.parse_args()
    result = verify(args.dist.resolve(), args.site.resolve())
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
