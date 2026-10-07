from pathlib import Path
from competition.arena.evidence import read
from r3e.protocol.hashing import atomic_write_json, utc_now


def update(state, **fields):
    path = Path(state)/'live_progress.json'
    previous = read(path) if path.exists() else {}
    atomic_write_json(path, {**previous, **fields, 'updated_at': utc_now()})
