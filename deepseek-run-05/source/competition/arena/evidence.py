"""Small shared primitives for immutable evidence, never model authority."""
from pathlib import Path
import json
from r3e.protocol.hashing import hash_payload, atomic_write_json

def signed(body, field="result_hash"):
    return {**body, field: hash_payload(body)}

def verify_signed(value, field="result_hash"):
    if not isinstance(value, dict) or value.get(field) != hash_payload({k:v for k,v in value.items() if k != field}):
        raise ValueError(f"invalid {field}")
    return value

def read(path):
    return json.loads(Path(path).read_text())

def freeze(path, value):
    path = Path(path)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"refusing to overwrite evidence: {path.name}")
    else:
        atomic_write_json(path, value)
    return value
