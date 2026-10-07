"""Build live local rounds from sealed inputs and independent arm state."""
from pathlib import Path
from r3e.protocol.hashing import hash_payload, atomic_write_json
from r3e.pilot.real_integrated_shadow import _population_config
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from competition.adapters.policy_provider import PolicyCandidateProvider
from competition.adapters.competition_red_adapter import CompetitionGroundedRedAdapter
from competition.adapters.competition_evolution_adapter import CompetitionEvolutionAdapter
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.services.adversarial_arena_service import AdversarialArenaService
from competition.arena.baseline import load_runtime, source_identity
from competition.arena.evidence import read, freeze
from competition.arena.isolation import require_evolution_manifest, check_separation


def validate_client(client, baseline):
    cfg = client.config
    identity = {"provider_id":cfg.provider_id, "model_id":cfg.model_id,
                "model_version":cfg.model_version, "temperature":cfg.temperature}
    if "client_config_hash" in baseline["provider"]:
        identity["client_config_hash"] = cfg.config_hash
    if identity != baseline["provider"]:
        raise ValueError("provider/model differs from shared baseline")


def build_arena_service(root, state_root, config, round_id, client, evolve, regression):
    root, state = Path(root).resolve(), Path(state_root).resolve()
    if (state/"final_evaluation_started.json").exists():
        raise ValueError("evolution is sealed after final evaluation starts")
    runtime, machine, baseline = load_runtime(state)
    if config.arm != "adversarial" or machine["arm"] != "adversarial" or machine["config_hash"] != config.config_hash:
        raise ValueError("only matching Machine B config may run local evolution")
    if source_identity(root)["source_hash"] != baseline["source_hash"]:
        raise ValueError("source changed after baseline")
    validate_client(client, baseline)
    require_evolution_manifest(evolve); require_evolution_manifest(regression)
    if evolve["split"] != "evolve" or regression["split"] != "non_target":
        raise ValueError("evolve and non_target manifests required")
    check_separation(evolve, regression, design_disjoint=True)
    # Compare only sealed membership identities; the evolution runner never loads heldout RTL.
    separation = read(state / "separation.json")
    from competition.arena.evidence import verify_signed
    verify_signed(separation)
    if separation["evolve_hash"] != evolve["manifest_hash"] or separation["regression_hash"] != regression["manifest_hash"] or separation["evaluation_manifests"] != baseline["evaluation_manifests"]:
        raise ValueError("data split certificate mismatch")
    freeze(state/"evolve.json", evolve); freeze(state/"regression.json", regression)
    red = CompetitionGroundedRedAdapter(root=root, manifest=evolve, client=client,
        artifact_root=state/"rounds"/round_id/"artifacts", round_id=round_id)
    population = _population_config(red)
    count = int(config.raw["red"].get("proposal_budget", 4))
    population["scheduler_id"] = "r3e-competition-m3-population-v1"
    population["total_assignment_budget"] = count
    profile = population["provider_profiles"][0]
    profile["max_assignments"] = count
    for field in ("total_input_token_budget", "total_output_token_budget", "total_wall_time_budget_ms"):
        population[field] *= count
    population["config_hash"] = hash_payload({k:v for k,v in population.items() if k != "config_hash"})
    freeze(state/"population.json", population)
    verifier = PublicManifestOracleVerifier(project_root=root, workspace=state/"blue_verifier"/round_id,
        allowed_case_artifact_roots=(state/"rounds",), run_context_hash=hash_payload({"baseline":baseline["baseline_hash"],"round":round_id}))
    provider = PolicyCandidateProvider(client, verifier_id=verifier.verifier_id, verifier_version=verifier.verifier_version, adapter_version="m3-policy-v1")
    evaluator = ArenaEvaluationService(root, state/"replays", provider=provider, artifact_roots=(state/"rounds",))
    adapter = CompetitionEvolutionAdapter(red_adapter=red, evaluator=evaluator, cases=evolve, regression=regression,
        index_path=state/"generated_cases.json", screening_seeds=baseline["seeds"])
    repair = evaluator.repair
    round_cfg = {"schema_version":"r3e-round-interface-v1", "phase":"competition_m3", "project_root":str(root),
        "experiment_id":machine["experiment_id"], "baseline_hash":baseline["baseline_hash"],
        "validity_authority":"grounded_runtime_authority_v1", "blue_evaluation_authority":"candidate_portfolio_v1",
        "policy_registry":str(state/"registry.json"), "policy_search_space":str(root/"competition/configs/arena/policy_search_space_v1.json"),
        "rounds_root":str(state/"rounds"), "events_root":str(state/"events"), "decision_ledger":str(state/"decision_ledger.jsonl"),
        "round_ledger":str(state/"round_ledger.jsonl"), "red_archive":str(state/"red_residual_archive.jsonl"),
        "covered_archive":str(state/"red_covered_archive.jsonl"), "red_rejected_archive":str(state/"red_rejected_archive.jsonl"),
        "memory_root":str(state/"memory"), "non_target_manifest":str(state/"regression.json"),
        "grounded_coverage_state":str(state/"coverage.json"), "grounded_population_config":str(state/"population.json"),
        "grounded_pre_generation_planner":True, "grounded_population_scheduler":True,
        "grounded_red_proposal_budget":count, "grounded_family_quota":2, "grounded_archive_quota":count,
        "grounded_maximum_difficulty_band":"D3",
        "grounded_operator_registry":"competition/configs/arena/grounded_operator_registry.json", "grounded_allow_controlled_composition":False,
        "blue_lens_registry":str(repair.config.paths["lens_registry"]),
        "blue_candidate_portfolio":str(repair.config.paths["portfolio"]),
        "blue_descriptor_router":str(repair.config.paths["descriptor_router"]),
        "blue_candidate_provider_toolchain_fingerprint":provider.toolchain_fingerprint,
        "blue_candidate_verifier_hash":verifier.verifier_hash,
        "blue_semantic_signature_provider_hash":repair.portfolio.semantic_signature_provider_hash,
        "challenge_seeds":baseline["seeds"], "promotion_seeds":baseline["seeds"],
        "policy_promotion_enabled":True, "residual_preserve_designs":True, "memory_qualification_enabled":False,
        "grounded_timeout_seconds":30, "grounded_formal_timeout_seconds":30,
        "adaptation_fraction":0.5, "split_seed":4, "policy_search_seed":5,
        "code_version":baseline["git_commit"] or baseline["source_hash"]}
    return AdversarialArenaService(arena_config=config, project_root=root, runtime=runtime,
        adapter=adapter, provider=provider, verifier=verifier), round_cfg
