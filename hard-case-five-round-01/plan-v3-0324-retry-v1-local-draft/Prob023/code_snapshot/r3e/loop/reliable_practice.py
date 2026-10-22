"""Public-only reserved exercises. Human-seeded fallback is never labeled online Red success."""
import json
import tempfile
from pathlib import Path

ASSETS=Path(__file__).parent/'assets/reliable_practice'


def fixtures(public):
    key=next((k for k in ('Prob001','Prob023','Prob003') if k.lower() in public['carrier_id'].lower()),None)
    if key is None:
        raise ValueError('no qualified fallback pool for public carrier')
    return json.loads((ASSETS/(key+'.json')).read_text())


def pool(public, materialize, identity):
    result=[]
    for edits in fixtures(public):
        proposal=materialize(dict(edits=edits,violated_requirement='Human-seeded public practice defect',
                                 spec_basis='Unchanged public carrier specification'),public)
        if proposal['status']!='proposal':
            raise ValueError('fallback cannot be materialized')
        result.append({'identity':identity(public,proposal['buggy_rtl']),'proposal':proposal})
    if len({r['identity'] for r in result})!=len(result):
        raise ValueError('fallback pool must contain distinct implementations')
    return result


def qualify(carrier, rows, check, read):
    with tempfile.TemporaryDirectory(prefix='r3e-fallback-') as temp:
        for index,row in enumerate(rows):
            admitted=check(Path(carrier['package']),read(carrier['suite_freeze']),row['proposal'],
                           Path(temp)/str(index),seen=set())
            if admitted['status']!='admitted':
                raise ValueError('fallback exercise failed public qualification: '+str(index))
