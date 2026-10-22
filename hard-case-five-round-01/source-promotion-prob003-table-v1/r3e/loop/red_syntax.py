"""Conservative, local correction of a misplaced RTL if-condition suffix.

No model calls, requirement interpretation, or functional repair. Only move the
closing parenthesis around an existing chain of parenthesized operands.
"""
import re
from copy import deepcopy


def normalize_condition_edits(edits):
    if not isinstance(edits, list):
        return edits, []
    corrected = deepcopy(edits)
    audit = []
    for index, edit in enumerate(corrected):
        if not isinstance(edit, dict) or not isinstance(edit.get('replace'), str):
            continue
        lines = edit['replace'].splitlines(keepends=True)
        for number, line in enumerate(lines):
            ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
            body = line[:-len(ending)] if ending else line
            match = re.fullmatch(r'(\s*(?:else\s+)?if\s*)(\(.*\))([ \t]*)', body)
            if not match:
                continue
            expression = match[2]
            # Do not guess at comments, strings, macros, statement bodies or
            # escaped identifiers. Other compilation failures remain failures.
            if any(x in expression for x in ('//', '/*', '*/', '"', '`', '\\', ';')):
                continue
            depth = 0
            first_end = None
            valid = True
            for pos, char in enumerate(expression):
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth < 0:
                        valid = False
                        break
                    if depth == 0 and first_end is None:
                        first_end = pos + 1
            if not valid or depth or first_end is None or first_end == len(expression):
                continue
            # Accept only a chain of whole, parenthesized terms. Leave operator
            # order and operand text intact, including bitwise vs logical ops.
            remaining = expression[first_end:]
            while remaining:
                op = re.match(r'\s*(?:&&|\|\||[&|^])\s*(?=\()', remaining)
                if not op:
                    valid = False
                    break
                term = remaining[op.end():]
                depth = 0
                end = None
                for pos, char in enumerate(term):
                    depth += (char == '(') - (char == ')')
                    if depth == 0:
                        end = pos + 1
                        break
                if end is None:
                    valid = False
                    break
                remaining = term[end:]
            if valid:
                fixed = match[1] + '(' + expression + ')' + match[3] + ending
                audit.append({'edit': index, 'replacement_line': number + 1,
                              'rule': 'enclose_complete_if_condition',
                              'before': line, 'after': fixed})
                lines[number] = fixed
        edit['replace'] = ''.join(lines)
    return corrected, audit
