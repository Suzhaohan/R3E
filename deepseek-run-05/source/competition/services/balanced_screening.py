"""Eliminate only candidates already unable to pass the unchanged final gate."""
from r3e.policy.promotion import DEFAULT_THRESHOLDS


def precheck(parent, child, target, regression, seeds, replay, thresholds=None):
    gates = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    pairs = []
    for row in target['rows']:
        for seed in seeds:
            a,b = replay(parent,row,seed), replay(child,row,seed)
            pairs.append({'split':'target', 'before':a, 'after':b})
            if a['oracle_ok'] and not b['oracle_ok'] and b.get('critical',True):
                return {'policy_id':child.policy_id, 'eligible':False, 'reason':'target_regression', 'pairs':pairs}
    recovered = [p for p in pairs if not p['before']['oracle_ok'] and p['after']['oracle_ok']]
    failures = sum(not p['before']['oracle_ok'] for p in pairs)
    designs = {p['after']['design'] for p in recovered}
    if (len(recovered) < gates['min_prior_failure_recovery'] or not failures
            or len(recovered)/failures < gates['min_target_recovery_ratio']
            or len(designs) < gates['min_covered_designs']):
        return {'policy_id':child.policy_id, 'eligible':False, 'reason':'insufficient_target_gain', 'pairs':pairs}
    # Check one repeat of the fast regression before paying for the other two.
    for row in regression['rows']:
        a,b = replay(parent,row,seeds[0]), replay(child,row,seeds[0])
        pairs.append({'split':'non_target', 'before':a, 'after':b})
        if a['oracle_ok'] and not b['oracle_ok'] and b.get('critical',True):
            return {'policy_id':child.policy_id, 'eligible':False, 'reason':'fast_regression', 'pairs':pairs}
    return {'policy_id':child.policy_id, 'eligible':True, 'reason':'continue_full_pairing', 'pairs':pairs}
