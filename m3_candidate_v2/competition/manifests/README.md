# M3 data split

- `red_evolve.json`: 4 synthetic comparator designs for Grounded Red evolution.
- `red_regression.json`: 2 separate synthetic design instances for non-target replay.
- `red_heldout.json`: 12 sealed synthetic boundary defects, final evaluation only.
- `strider14_sealed.json`: the existing 14 public Strider cases with verified input hashes.

Generated sources are **protocol inputs**, not model outputs or experimental results.
The three synthetic sets have distinct design instances and normalized changes,
but share the comparator template family. Do not claim broad unseen-design or
unseen-family generalization from this small synthetic suite. Strider is the
separate external evaluation. This release supports comparator replacement and
boundary-constant mutation; the frozen operator registry describes that scope.

`python -m competition.scripts.build_arena_datasets` regenerates identical inputs
and refuses to overwrite changed frozen assets. Membership is sealed before
initializing either arm. Grounded Red mutations are materialized at runtime and
must pass the Core Icarus + formal validity authority before admission.
