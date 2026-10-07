# Arena design inputs, version 2

The default offline demo runs **five rounds, R000–R004**. Live runs use the
same manifests; execute all five rounds before starting final evaluation.

| Manifest | Cases | Upstream designs / instances | Usage |
|---|---:|---|---|
| `red_evolve_v2.json` | 10 | 5 Assignment4V combinational designs, 1 CirFix decoder, 4 synthetic comparator instances | Red generation and policy evolution |
| `red_regression_v2.json` | 6 | 4 bugs from the Assignment4V 24-bit register design, 2 synthetic comparator instances | Non-target regression |
| `red_heldout_v2.json` | 35 | 23 bugs from the Assignment4V decimal counter design, 12 synthetic comparator instances | Final evaluation only |
| `strider14_sealed.json` | 14 | Existing public Strider inputs, unchanged | Final evaluation only |

`design_catalog_v2.json` records design membership and manifest hashes. A bug
variant is not a new independent design. Synthetic comparator instances still
share one template family. Assignment4V design groups are disjoint across the
three splits. The CirFix decoder is absent from Strider-14; do not add Strider's
counter/flop/FSM/shift/mux designs to evolution while claiming unseen-design
evaluation on Strider.

All **57 Assignment4V cases from 7 assignment designs** are preserved under
`datasets/cases/assignment4v/` with a hashed inventory at
`datasets/manifests/assignment4v57.jsonl`. This complete inventory is not an
independent heldout benchmark once some designs have been used in evolution.
Original RTL, testbenches and diffs are preserved; the supplied README is stored
in `datasets/licenses/Assignment4V-source-README.md` (the snapshot does not
specify a redistribution license). CirFix uses the existing MIT public snapshot,
not a second independent copy of the same benchmark.

## Grounded inputs

The six imported evolution circuits are the full adder, three-person judge,
2:1 mux, enabled decoder, seven-segment decoder, and CirFix 3:8 decoder.
`imported_assets/` supplies new Grounded testbenches and formal properties.
Simulation enumerates every binary input combination. Formal assertions compare
the candidate to an oracle-only copy of the supplied reference. These checks
establish equivalence to that reference, not correctness against an independent
specification. Original assignment testbenches remain available in the inventory.

The frozen mutation registry enables comparator replacement, boundary constant
shift, binary bitwise replacement and assignment literal bit flip. Operator
targets rotate within compatible design subsets each round. Every generated
poison still goes through Core Icarus and Yosys admission, Blue repair, replay,
promotion and audit. The UI reports actual round coverage, not the pool size.

## Rebuild and qualify

From `m3_demo_v3`, rebuild identical inputs without network/model calls:

```bash
python -m competition.scripts.build_arena_datasets
python scripts/verify_datasets.py
python -m competition.scripts.qualify_imported_designs --output /tmp/new-input-qualification
```

The first import can explicitly take `--assignment-source` when invoking
`competition.scripts.expand_arena_designs`. Subsequent rebuilds use the included
hashed snapshot and do not require the sibling downloaded repositories.
Builders refuse to overwrite changed frozen assets. Original v1 manifests are
retained for provenance; runtime entry points select the new v2 manifests.
Create a new baseline and runtime directory for this version. Existing evidence
is not upgraded or relabeled as a five-round experiment.

The offline scripted provider sees only evolution/regression solutions. Heldout
solutions are not loaded into it. Offline demo results remain engineering
evidence; live-model results require a separately budgeted run and formal freeze.
