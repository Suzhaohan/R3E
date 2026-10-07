from pathlib import Path
from copy import deepcopy
import difflib
import json
import pytest

from competition.arena_config import load_arena_config, validate_arena_config
from competition.arena.baseline import build_baseline, initialize_arm, load_runtime
from competition.arena.evidence import read, signed, freeze
from competition.arena.isolation import check_separation, require_evolution_manifest, verify_evaluation_manifest
from competition.arena.cli import _split_certificate
from competition.arena.runtime import build_arena_service
from competition.services.repair_service import RepairService
from competition.services.arena_evaluation_service import ArenaEvaluationService
from competition.adapters.policy_provider import PolicyCandidateProvider
from r3e.providers.openai_compatible import OpenAICompatibleClientConfig, OpenAICompatibleJSONClient
from r3e.blue.portfolio.oracle_gate_verifier import PublicManifestOracleVerifier
from r3e.arena.audit import verify_frozen_round
from r3e.policy.search import propose_children
from r3e.arena.manifests import make_manifest
from r3e.protocol.hashing import hash_payload

ROOT=Path(__file__).resolve().parents[2]


def client(calls, *, repair_all=False):
    goldens=[(ROOT/r["golden_rtl"]).read_text()
             for name in ("demo18_red_sources", "guard_regression")
             for r in read(ROOT/f"competition/manifests/{name}.json")["rows"]]
    def transport(**request):
        calls.append(request)
        prompt=json.loads(request["messages"][1]["content"])
        if "allowed_nodes" in prompt:
            result={"target_module":prompt["target_module"], "node_ordinal":prompt["allowed_nodes"][0]["node_ordinal"], "rationale":"offline protocol fixture"}
        else:
            source=prompt["current_buggy_rtl"]
            good=repair_all or "Combine the observed" in prompt["lens_instruction"]
            replacement=max(goldens,key=lambda s:difflib.SequenceMatcher(None,source,s).ratio()) if good else source
            result={"replacement_rtl":replacement,"edit":"offline fixture candidate"}
        return {"content":json.dumps(result),"input_tokens":100,"output_tokens":20,"provider_request_id":f"test-{len(calls)}"}
    cfg=OpenAICompatibleClientConfig(provider_id="offline-test",provider_version="1",endpoint_id="test",
        model_id="offline-fixture",model_version="1",api_key_env="M3_TEST_KEY",base_url_env="M3_TEST_URL",
        timeout_seconds=30,maximum_output_tokens=4096,temperature=0,require_seed=True)
    return OpenAICompatibleJSONClient(cfg,transport=transport,environ={})


def setup_arm(tmp_path, arm="adversarial"):
    config=load_arena_config(ROOT/f"competition/configs/arena/{arm}.yaml")
    manifests={"strider-subset4":read(ROOT/"competition/manifests/demo18_strider.json"),"red-heldout":read(ROOT/"competition/manifests/demo18_heldout.json")}
    baseline=build_baseline(ROOT,provider_identity={"provider_id":"offline-test","model_id":"offline-fixture","model_version":"1","temperature":0},evaluation_manifests=manifests,seeds=[1,2,3])
    state=tmp_path/arm
    initialize_arm(ROOT,state,config,baseline)
    freeze(state/"separation.json",_split_certificate(ROOT,baseline))
    return config,baseline,state


def test_static_policy_memory_and_arm_isolation(tmp_path):
    config,baseline,state=setup_arm(tmp_path,"static")
    runtime,_,_=load_runtime(state)
    assert runtime.fixed_policy().policy_hash==baseline["initial_policy_hash"]
    with pytest.raises(ValueError,match="empty"):
        initialize_arm(ROOT,state,config,baseline)
    (state/"memory.json").write_text('{"enabled":true}')
    with pytest.raises(ValueError,match="memory"):
        load_runtime(state)


@pytest.mark.parametrize("field,value",[("red",True),("budget",4),("seeds",[1,1,2]),("memory",True)])
def test_config_rejects_unfair_experiment(field,value):
    import yaml
    raw=yaml.safe_load((ROOT/"competition/configs/arena/static.yaml").read_text())
    if field=="red": raw["red"]["enabled"]=value
    elif field=="budget": raw["repair"]["candidate_budget"]=value
    elif field=="seeds": raw["evaluation"]["seeds"]=value
    else: raw["memory"]["allow_activation"]=value
    with pytest.raises(ValueError):validate_arena_config(raw)


def test_heldout_seal_and_overlap():
    evolve=read(ROOT/"competition/manifests/demo18_red_sources.json")
    heldout=read(ROOT/"competition/manifests/demo18_heldout.json")
    check_separation(evolve,heldout)
    with pytest.raises(ValueError):require_evolution_manifest(heldout)
    with pytest.raises(ValueError):check_separation(evolve,evolve)
    altered=deepcopy(heldout);altered["rows"][0]["manifest_file_hashes"]={"missing":"sha256:"+"0"*64}
    altered=make_manifest(altered["rows"],split="evaluation",metadata=heldout["metadata"])
    with pytest.raises(ValueError):verify_evaluation_manifest(altered,ROOT)


def test_searched_policy_reaches_actual_model_and_eda(tmp_path):
    calls=[]; c=client(calls)
    provider=PolicyCandidateProvider(c,verifier_id=PublicManifestOracleVerifier.verifier_id,verifier_version=PublicManifestOracleVerifier.verifier_version,adapter_version="m3-policy-v1")
    service=ArenaEvaluationService(ROOT,tmp_path,provider=provider)
    parent=service.repair._policy()
    adaptation=make_manifest(read(ROOT/"competition/manifests/demo18_red_sources.json")["rows"],split="adaptation")
    children=propose_children(parent,adaptation,read(ROOT/"competition/configs/arena/policy_search_space_v1.json"),round_id="R001",seed=5)
    child=next(c for c in children if c.configuration["evidence_mode"]=="hybrid")
    row=adaptation["rows"][0]
    before=service.evaluate_case_with_policy(parent,row,1)
    after=service.evaluate_case_with_policy(child,row,1)
    assert before["oracle_ok"] is False
    assert after["oracle_ok"] is True
    assert before["budget_hash"]==after["budget_hash"]
    assert before["policy_hash"]!=after["policy_hash"]
    assert len(calls)==6
    assert all("golden_rtl" not in json.loads(r["messages"][1]["content"]) for r in calls)


def test_real_eda_round_is_auditable_and_resumable(tmp_path):
    config,baseline,state=setup_arm(tmp_path)
    calls=[]; c=client(calls)
    evolve=read(ROOT/"competition/manifests/demo18_red_sources.json"); regression=read(ROOT/"competition/manifests/guard_regression.json")
    service,cfg=build_arena_service(ROOT,state,config,"R000",c,evolve,regression)
    summary=service.run_round("R000",cfg,evolution_manifest=evolve,regression_manifest=regression)
    audit=verify_frozen_round(state/"rounds/R000")
    assert audit["audit_record_hash"]==summary["audit_record_hash"]
    assert calls
    count=len(calls)
    service2,cfg2=build_arena_service(ROOT,state,config,"R000",c,evolve,regression)
    assert service2.resume_round("R000",cfg2,evolution_manifest=evolve,regression_manifest=regression)==summary
    assert len(calls)==count
    assert service.active_policy().policy_hash==summary["active_policy_hash"]

    summaries=[summary]
    for round_id in ("R001","R002","R003","R004"):
        next_service,next_cfg=build_arena_service(ROOT,state,config,round_id,c,evolve,regression)
        summaries.append(next_service.run_round(round_id,next_cfg,evolution_manifest=evolve,regression_manifest=regression))
        verify_frozen_round(state/"rounds"/round_id)
    assert any(s["promoted"] for s in summaries), summaries
    assert service.active_policy().policy_hash != baseline["initial_policy_hash"]
    from competition.services.experience_memory import archive, snapshot
    saved=archive(ROOT,state)
    assert saved['entries'], 'B must retain this run’s challenge experience'
    assert read(state/'experience/R000.json')['entries']==[]
    # This fixture ignores memory; unchanged outcomes cannot qualify cases.
    assert all(not read(state/'experience'/f'{r}.json')['enabled'] for r in ['R001','R002','R003','R004'])
    assert snapshot(ROOT,state,'T1',evolving=True)==read(state/'experience/R004.json')
    active=service.active_policy()
    result=service.adapter.evaluator.evaluate_case_with_policy(active,regression["rows"][0],1)
    assert result["policy_hash"]==active.policy_hash
    assert result["oracle_ok"]
