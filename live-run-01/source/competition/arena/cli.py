"""M3 commands; writes are local and require explicit runtime directories."""
import argparse
from pathlib import Path
from r3e.protocol.hashing import hash_payload
from r3e.providers.openai_compatible import OpenAICompatibleClientConfig, OpenAICompatibleJSONClient
from competition.arena_config import load_arena_config
from competition.arena.baseline import build_baseline, initialize_arm, load_runtime, source_identity
from competition.arena.evidence import read, freeze, signed
from competition.arena.isolation import check_separation, verify_evaluation_manifest
from competition.arena.runtime import build_arena_service, validate_client
from competition.arena.budget import BudgetedClient
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.arena_comparison_service import compare_arms, verify_comparison
from competition.services.arena_freeze_service import freeze_arm
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier


def _client(path):
    return OpenAICompatibleJSONClient(OpenAICompatibleClientConfig.from_dict(read(path)))


def _identity(config):
    return {"provider_id":config.provider_id,"model_id":config.model_id,"model_version":config.model_version,"temperature":config.temperature,"client_config_hash":config.config_hash}


def _split_certificate(root, baseline):
    evolve=read(root/"competition/manifests/red_evolve_v2.json")
    regression=read(root/"competition/manifests/red_regression_v2.json")
    heldout=read(root/"competition/manifests/red_heldout_v2.json")
    strider=read(root/"competition/manifests/strider14_sealed.json")
    for a,b in ((evolve,regression),(evolve,heldout),(regression,heldout)):
        check_separation(a,b)
    # Public Strider has no poison identities; compare canonical RTL contents too.
    from r3e.protocol.hashing import hash_file
    def assets(m):
        return {hash_file(root/r[k]) for r in m["rows"] for k in ("buggy_rtl","golden_rtl")}
    for training in (evolve,regression):
        if {r["case_id"] for r in training["rows"]} & {r["case_id"] for r in strider["rows"]} or assets(training)&assets(strider):
            raise ValueError("Strider final set overlaps training")
    for name,m in (("red-heldout",heldout),("strider14",strider)):
        verify_evaluation_manifest(m,root)
        if m["manifest_hash"] != baseline["evaluation_manifests"][name]:
            raise ValueError("baseline evaluation seal mismatch")
    return signed({"evolve_hash":evolve["manifest_hash"],"regression_hash":regression["manifest_hash"],
        "evaluation_manifests":baseline["evaluation_manifests"],"split_level":"upstream_design_disjoint; synthetic comparator family shared"})


def main(argv, root):
    root=Path(root)
    parser=argparse.ArgumentParser(prog="competition.cli arena")
    sub=parser.add_subparsers(dest="command",required=True)
    demo=sub.add_parser("arena-demo", help="Offline scripted model + real EDA; no network calls")
    demo.add_argument("--output-root", help="New empty directory; defaults to a unique temporary directory")
    demo.add_argument("--rounds", type=int, default=5)
    baseline=sub.add_parser("arena-baseline")
    baseline.add_argument("--client-config",required=True); baseline.add_argument("--output",required=True)
    baseline.add_argument("--seeds",nargs="+",type=int,default=[1,2,3]); baseline.add_argument("--image-hash",default="unrecorded")
    init=sub.add_parser("arena-init")
    init.add_argument("--config",required=True); init.add_argument("--baseline",required=True); init.add_argument("--state-root",required=True)
    status=sub.add_parser("arena-status"); status.add_argument("--state-root",required=True)
    for name in ("arena-round","arena-eval"):
        p=sub.add_parser(name); p.add_argument("--state-root",required=True); p.add_argument("--client-config",required=True)
        p.add_argument("--max-calls",required=True,type=int); p.add_argument("--max-tokens",required=True,type=int)
        p.add_argument("--total-max-calls",type=int); p.add_argument("--total-max-tokens",type=int)
        if name=="arena-round":
            p.add_argument("--config",required=True); p.add_argument("--round",required=True)
        else:
            p.add_argument("--dataset",choices=["strider14","red-heldout"],required=True)
    freeze_p=sub.add_parser("arena-freeze"); freeze_p.add_argument("--state-root",required=True)
    freeze_p.add_argument("--evaluation",action="append",required=True); freeze_p.add_argument("--output",required=True)
    freeze_p.add_argument("--claim-evolution",action="store_true")
    compare=sub.add_parser("arena-compare"); compare.add_argument("--left",required=True); compare.add_argument("--right",required=True); compare.add_argument("--output",required=True)
    validate=sub.add_parser("arena-validate"); validate.add_argument("path")
    args=parser.parse_args(argv)
    if args.command=="arena-demo":
        from competition.arena.demo import run_demo
        return run_demo(root, args.output_root, rounds=args.rounds)
    if args.command=="arena-baseline":
        client=_client(args.client_config)
        manifests={"strider14":read(root/"competition/manifests/strider14_sealed.json"),"red-heldout":read(root/"competition/manifests/red_heldout_v2.json")}
        value=build_baseline(root,provider_identity=_identity(client.config),evaluation_manifests=manifests,seeds=args.seeds,image_hash=args.image_hash)
        freeze(args.output,value)
        return {"baseline_hash":value["baseline_hash"],"formal_freeze_ready":not value["dirty"],"output":args.output}
    if args.command=="arena-init":
        baseline=read(args.baseline)
        certificate=_split_certificate(root,baseline)
        value=initialize_arm(root,args.state_root,load_arena_config(args.config),baseline)
        freeze(Path(args.state_root)/"separation.json",certificate)
        return value
    if args.command=="arena-compare":
        return freeze(args.output,compare_arms(read(args.left),read(args.right)))
    if args.command=="arena-validate":
        value=verify_comparison(read(args.path))
        return {"valid":True,"comparison_hash":value["comparison_hash"]}
    if args.command=="arena-freeze":
        return freeze_arm(root,args.state_root,args.evaluation,args.output,evolution_claim=args.claim_evolution)
    runtime,machine,baseline=load_runtime(args.state_root)
    state=Path(args.state_root).resolve()
    if args.command=="arena-status":
        return {"experiment_id":machine["experiment_id"],"arm":machine["arm"],"baseline_hash":baseline["baseline_hash"],
            "policy":runtime.policy_snapshot(runtime.active_policy()),"memory_fixed":True}
    if source_identity(root)["source_hash"]!=baseline["source_hash"]:
        raise ValueError("code changed after baseline")
    client=_client(args.client_config); validate_client(client,baseline)
    if not client.readiness()["ready"]:
        raise RuntimeError("live provider not ready; configure credential/base URL environment variables")
    import re
    operation=args.round if args.command=="arena-round" else args.dataset
    if not re.fullmatch(r"[A-Za-z0-9_-]+",operation): raise ValueError("unsafe operation id")
    if (state/"live_plan.json").exists():
        from competition.arena.evidence import verify_signed
        plan=verify_signed(read(state/"live_plan.json"))
        if plan["client_config_hash"] != client.config.config_hash:
            raise ValueError("live plan client changed")
        if args.command=="arena-round" and operation not in plan["round_ids"]:
            raise ValueError("round outside frozen five-round plan")
        if args.command=="arena-eval" and machine["arm"]=="adversarial":
            from r3e.arena.audit import verify_frozen_round
            for round_id in plan["round_ids"]:
                verify_frozen_round(state/"rounds"/round_id)
        args.total_max_calls, args.total_max_tokens=plan["max_calls"],plan["max_tokens"]
    client=BudgetedClient(client,state/"budgets"/(operation+".json"),max_calls=args.max_calls,max_tokens=args.max_tokens)
    if args.total_max_calls is not None or args.total_max_tokens is not None:
        if args.total_max_calls is None or args.total_max_tokens is None:
            raise ValueError("both total budget limits required")
        client=BudgetedClient(client,state/"budgets/total.json",max_calls=args.total_max_calls,max_tokens=args.total_max_tokens)
    if args.command=="arena-round":
        evolve=read(root/"competition/manifests/red_evolve_v2.json"); regression=read(root/"competition/manifests/red_regression_v2.json")
        service,round_cfg=build_arena_service(root,state,load_arena_config(args.config),args.round,client,evolve,regression)
        return service.resume_round(args.round,round_cfg,evolution_manifest=evolve,regression_manifest=regression)
    name="strider14_sealed" if args.dataset=="strider14" else "red_heldout_v2"
    manifest=read(root/f"competition/manifests/{name}.json")
    if manifest["manifest_hash"] != baseline["evaluation_manifests"][args.dataset]: raise ValueError("final seal changed")
    target=state/"eval"/(args.dataset+".json")
    if target.exists():
        from competition.services.arena_comparison_service import verify_evaluation
        from competition.arena.evidence import verify_signed
        envelope=verify_signed(read(target))
        existing=verify_evaluation(envelope["evaluation"],live_only=True)
        if envelope["baseline_hash"] != baseline["baseline_hash"] or envelope["arm"] != machine["arm"] or existing["policy_hash"] != runtime.active_policy().policy_hash or existing["manifest_hash"] != manifest["manifest_hash"]:
            raise ValueError("existing evaluation binding mismatch")
        return {"output":str(target),"reused":True,"repaired":existing["repaired"],"denominator":existing["denominator"]}
    provider=PolicyCandidateProvider(client,verifier_id=PublicManifestOracleVerifier.verifier_id,
        verifier_version=PublicManifestOracleVerifier.verifier_version,adapter_version="m3-policy-v1")
    from r3e.protocol.ledger import writer_lock
    with writer_lock(state/"execution.lock"):
        freeze(state/"final_evaluation_started.json", {"policy_hash":runtime.active_policy().policy_hash, "baseline_hash":baseline["baseline_hash"]})
        evaluation=ArenaEvaluationService(root,state/"eval"/args.dataset,provider=provider).evaluate_policy(runtime.active_policy(),manifest,baseline["seeds"],runtime=runtime)
    value=signed({"experiment_id":machine["experiment_id"],"arm":machine["arm"],"baseline_hash":baseline["baseline_hash"],"evaluation":evaluation})
    freeze(target,value)
    return {"output":str(target),"repaired":evaluation["repaired"],"denominator":evaluation["denominator"],"repair_rate":evaluation["repair_rate"]}
