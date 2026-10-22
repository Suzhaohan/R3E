"""Deterministic diagnostics from the current public task and submitted patches only."""
import difflib


def correction_context(baseline, current, allowed, baseline_evidence, current_evidence, history, limit):
    # Never accepts a clean carrier, answer, reference result or private evaluator.
    patches = {}
    original = {}
    for path in sorted(allowed):
        diff = ''.join(difflib.unified_diff(baseline[path].splitlines(True),
            current[path].splitlines(True), 'original_buggy/' + path, 'submitted/' + path))
        if diff:
            patches[path] = {'diff': diff[:limit], 'truncated': len(diff) > limit}
            original[path] = baseline[path]
    def rows(evidence):
        return {name: cell.get('result') for name, cell in evidence.get('suites', {}).items()}
    before, after = rows(baseline_evidence), rows(current_evidence)
    return {'source': 'current_public_task_and_actual_submissions_only',
        'original_buggy_files': original, 'patches_from_original_bug': patches,
        'unchanged_from_original_bug': not patches,
        'baseline_public_suites': before, 'current_public_suites': after,
        'regressed_public_suites': sorted(k for k in before if before[k] == 'visible_pass' and after.get(k) != 'visible_pass'),
        'repeated_public_failure': len(history) >= 2 and history[-1].get('evidence') == history[-2].get('evidence'),
        'instruction': 'The original files below are the defective task, not a solution. '
            'Compare your actual patch with the failing public diagnostics. '
            'Check whether your added changes caused a new failure or broke a previously passing suite. '
            'You may retract unsupported changes and choose a different repair; do not repeat an unchanged failed submission. '
            'Use the public specification and test evidence to justify the correction. Return local edits against the current source.'}
