"""Restore the delivered archive and its exact upstream commit without model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


HERE = Path(__file__).resolve().parent
COMMIT = 'a1f3d61967a3fcab870379c8c8f1d7197a779d7a'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(archive_path, destination, prefix):
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        for member in members:
            if member.isdir():
                continue
            if not member.isfile() or not member.name.startswith(prefix):
                raise ValueError(f'unsupported archive member: {member.name}')
            relative = PurePosixPath(member.name[len(prefix):])
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise ValueError('unsafe archive path')
            path = destination.joinpath(*relative.parts)
            content = archive.extractfile(member).read()
            if path.exists():
                if path.read_bytes() != content:
                    raise ValueError(f'existing imported file differs: {path}')
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', type=Path, required=True)
    args = parser.parse_args()
    bundle = HERE/'handoff'
    source = HERE/'source'
    handoff_archive = HERE.parent/'prob003_handoff_20261013(1).tar.gz'
    restore(handoff_archive, bundle, 'prob003_handoff_20261013/')
    manifest = json.loads((bundle/'handoff_manifest.json').read_text())
    for relative, digest in manifest['files_sha256'].items():
        if sha(bundle/relative) != digest:
            raise ValueError(f'handoff checksum mismatch: {relative}')
    restore(args.source_archive, source, f'R3E-{COMMIT}/')
    code = json.loads((bundle/'plan/code_snapshot_manifest.json').read_text())['files_sha256']
    for relative, digest in code.items():
        if sha(source/relative) != digest:
            raise ValueError(f'upstream differs from the delivered code: {relative}')
    report = {'upstream_commit': COMMIT, 'verified_frozen_files': len(code),
              'handoff_archive_sha256': sha(handoff_archive),
              'upstream_archive_sha256': sha(args.source_archive), 'model_calls': 0}
    path = HERE/'import_identity.json'
    text = json.dumps(report, indent=2)+'\n'
    if path.exists() and path.read_text() != text:
        raise ValueError('import identity changed')
    path.write_text(text)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
