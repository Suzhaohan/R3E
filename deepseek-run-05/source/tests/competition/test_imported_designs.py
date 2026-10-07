"""Imported design separation and real EDA checks for new mutation families."""
from pathlib import Path
import json
import subprocess

import pytest

from competition.arena.evidence import read
from competition.arena.isolation import check_separation
from competition.scripts.select_representative_cases import build
from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
from r3e.protocol.hashing import hash_payload
from r3e.red.grounded.operator_ast import operator_nodes
from r3e.red.grounded.materializers import materialize_operator, inverse_materialization
from r3e.semantic_repair_bench.oracle_gate import judge

ROOT = Path(__file__).resolve().parents[2]


def test_import_membership_is_reproducible_and_design_disjoint():
    before = read(ROOT / "competition/manifests/demo32_selection.json")
    assert build(ROOT) == before
    rows = [json.loads(s) for s in (ROOT / "datasets/manifests/assignment4v57.jsonl").read_text().splitlines()]
    assert len(rows) == 57 and len({r["design"] for r in rows}) == 7
    sets = [read(ROOT / f"competition/manifests/{name}.json")
            for name in ("demo32_red_sources", "demo32_regression", "demo32_heldout")]
    assert [len(m["rows"]) for m in sets] == [5, 2, 2]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        check_separation(sets[a], sets[b])


@pytest.mark.parametrize("case_id", [r["case_id"] for r in read(ROOT / "competition/manifests/demo32_red_sources.json")["rows"]])
def test_imported_mutation_has_real_simulation_and_formal_counterexample(case_id, tmp_path):
    row = next(r for r in read(ROOT / "competition/manifests/demo32_red_sources.json")["rows"] if r["case_id"] == case_id)
    source = (ROOT / row["golden_rtl"]).read_text()
    registry = read(ROOT / "competition/configs/arena/grounded_operator_registry.json")
    operators = [op for op in registry["operators"]
                 if operator_nodes(source, module=row["top_module"], operator_id=op["operator_id"])]
    assert operators, case_id
    case = public_case_from_manifest(row, project_root=ROOT)
    original = judge(case, case["buggy_rtl_path"], tmp_path / "original")
    assert not original.ok and original.stage == "compare", original
    for op in operators:
        node = operator_nodes(source, module=row["top_module"], operator_id=op["operator_id"])[0]
        plan = {"operator_id": op["operator_id"], "family_id": op["supported_family_ids"][0],
                "target_module": row["top_module"], "target_ast_node_hash": node.node_hash,
                "plan_hash": hash_payload({"case": case_id, "operator": op["operator_id"]})}
        mutation = materialize_operator(plan, clean_source=source)
        assert inverse_materialization(mutation.receipt, poison_source=mutation.poison_source) == source
        work = tmp_path / op["operator_id"]
        work.mkdir()
        poison = work / "poison.v"
        poison.write_text(mutation.poison_source)
        result = judge(case, poison, work / "simulation")
        assert not result.ok and result.stage == "compare", result
        for rtl, expected in ((ROOT / row["golden_rtl"], "SUCCESS"), (poison, "FAIL")):
            script = (f'read_verilog -formal -sv "{rtl}" "{ROOT / row["grounded_formal_property"]}"; '
                      'prep -top formal_top -flatten; memory_map; opt_clean; '
                      'sat -prove-asserts -seq 2 -show-ports')
            run = subprocess.run(["yosys", "-p", script], capture_output=True, text=True, timeout=30)
            assert run.returncode == 0, run.stderr
            assert f"{expected}!" in run.stdout, run.stdout[-2000:]


def test_literal_and_bitwise_operators_do_not_mutate_declarations_or_reductions():
    source = "module m(input [7:0] a, output y); parameter P=1; assign y=&a; endmodule"
    for op in ("flip_assignment_constant", "replace_bitwise_operator"):
        assert not operator_nodes(source, module="m", operator_id=op)


def test_comparator_operator_excludes_nonblocking_assignments():
    source = "module m(input clk,a, output reg q); always @(posedge clk) if(a<=1) q<=0; endmodule"
    nodes = operator_nodes(source, module="m", operator_id="replace_comparator")
    assert len(nodes) == 1 and nodes[0].metadata["left"] == "a"
