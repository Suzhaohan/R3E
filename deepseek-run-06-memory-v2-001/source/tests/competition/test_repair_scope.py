"""Bound real repair size without rejecting insertions or nested branches."""
import json
from pathlib import Path
import pytest
from r3e.blue.portfolio.repair_scope import measure_repair
from r3e.red.grounded.verilog_ast import VerilogAstViolation

ROOT = Path(__file__).resolve().parents[2]


def test_inserting_missing_branch_is_not_a_whole_file_rewrite():
    old = 'module m(input a, output reg y); always @* begin if(a) y=1; end endmodule'
    new = old.replace('y=1;', 'y=1; else y=0;')
    edits, blocks = measure_repair(old, new)
    assert edits == 5
    assert blocks == {('m', 'block:0')}


def test_nested_conditions_are_one_block_but_two_processes_are_not():
    old = 'module m(input a, output reg x,y); always @* begin if(a) x=1; else x=0; if(a) y=1; else y=0; end endmodule'
    new = old.replace('x=1', 'x=0').replace('y=1', 'y=0')
    assert len(measure_repair(old, new)[1]) == 1
    old = old.replace('if(a) y=1', 'end always @* begin if(a) y=1')
    new = old.replace('x=1', 'x=0').replace('y=1', 'y=0')
    assert len(measure_repair(old, new)[1]) == 2


def test_selected_reference_repairs_fit_the_unchanged_64_token_single_block_limit():
    for name in ['demo18_supplied_assets', 'demo18_regression', 'demo18_heldout', 'demo18_strider']:
        for row in json.loads((ROOT / f'competition/manifests/{name}.json').read_text())['rows']:
            old = (ROOT / row['buggy_rtl']).read_text()
            new = (ROOT / row['golden_rtl']).read_text()
            edits, blocks = measure_repair(old, new)
            assert 0 < edits <= 64 and len(blocks) == 1, (row['case_id'], edits, blocks)


def test_unbalanced_statement_does_not_pass_scope():
    with pytest.raises(VerilogAstViolation):
        measure_repair('module m; always @* x=0; endmodule', 'module m; always @* begin x=1; endmodule')
