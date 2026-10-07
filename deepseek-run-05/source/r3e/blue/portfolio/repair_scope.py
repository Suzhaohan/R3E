"""Measure actual token edits and enclosing procedural repair blocks.

An if/case inside one always statement is not a separate repair block. Token
insertions must not turn all following unchanged tokens into charged edits.
"""
from difflib import SequenceMatcher

from r3e.red.grounded.verilog_ast import tokenize_verilog, VerilogAstViolation

PROCEDURAL = {"always", "always_comb", "always_ff", "always_latch", "initial"}


def _balanced(values, start, opening="(", closing=")"):
    depth = 0
    for index in range(start, len(values)):
        if values[index] == opening:
            depth += 1
        elif values[index] == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    raise VerilogAstViolation("unbalanced repair statement")


def _statement_end(values, start):
    if start >= len(values):
        raise VerilogAstViolation("missing repair statement")
    token = values[start]
    if token in {"@", "#"}:
        after = start + 1
        if after >= len(values):
            raise VerilogAstViolation("missing timing control")
        after = _balanced(values, after) if values[after] == "(" else after + 1
        return _statement_end(values, after)
    if token == "begin":
        return _balanced(values, start, "begin", "end")
    if token == "if":
        after = _statement_end(values, _balanced(values, start + 1))
        return _statement_end(values, after + 1) if after < len(values) and values[after] == "else" else after
    if token in {"case", "casex", "casez"}:
        depth = 1
        for index in range(start + 1, len(values)):
            if values[index] in {"case", "casex", "casez"}:
                depth += 1
            elif values[index] == "endcase":
                depth -= 1
                if depth == 0:
                    return index + 1
        raise VerilogAstViolation("unbalanced case statement")
    if token in {"for", "while", "repeat"}:
        return _statement_end(values, _balanced(values, start + 1))
    if token == "forever":
        return _statement_end(values, start + 1)
    for index in range(start, len(values)):
        if values[index] == ";":
            return index + 1
        if values[index] == "endmodule":
            break
    raise VerilogAstViolation("unterminated repair statement")


def _owners(tokens):
    values = [t.value for t in tokens]
    owners = [None] * len(tokens)
    module = ""
    ordinal = 0
    index = 0
    while index < len(tokens):
        token = values[index]
        if token == "module":
            module = values[index + 1]
            ordinal = 0
        owners[index] = (module, "module_scope")
        if token in PROCEDURAL or token == "assign":
            end = _statement_end(values, index + 1)
            owners[index:end] = [(module, f"block:{ordinal}")] * (end - index)
            ordinal += 1
            index = end
        else:
            index += 1
    return owners


def measure_repair(buggy_source, candidate_source):
    old, new = (tokenize_verilog(s) for s in (buggy_source, candidate_source))
    matcher = SequenceMatcher(a=[(t.kind, t.value) for t in old],
                              b=[(t.kind, t.value) for t in new], autojunk=False)
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    edits = sum(max(b-a, d-c) for _, a, b, c, d in changes)
    owners = (_owners(old), _owners(new))
    blocks = set()
    for _, a, b, c, d in changes:
        # Empty sides carry no modified tokens. The inserted/deleted side owns
        # the edit, avoiding a spurious second block at a statement boundary.
        for owner, start, end in ((owners[0], a, b), (owners[1], c, d)):
            blocks.update(owner[start:end])
    return edits, blocks
