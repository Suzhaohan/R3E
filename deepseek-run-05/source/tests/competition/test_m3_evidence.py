from copy import deepcopy
from pathlib import Path
import io
import json
import pytest
from competition.arena.evidence import signed, freeze
from competition.services.arena_comparison_service import compare_arms, verify_evaluation, verify_arm
from competition.services.arena_telemetry_service import ArenaTelemetryService
from competition.services.arena_freeze_service import freeze_arm
from competition.app.backend.api import Handler, CompetitionContext
from competition.arena.budget import BudgetedClient
from test_m3_arena import ROOT, setup_arm, client


def arms():
    baseline=signed({"dirty":False,"git_commit":"a"*40,"initial_policy_hash":"B0", "memory_hash":"M0",
        "provider":{"model_id":"test"},"seeds":[1,2,3],"evaluation_manifests":{"strider-subset4":"manifest-1","red-heldout":"manifest-2"}},"baseline_hash")
    def arm(which):
        evals={}
        for dataset,mhash in baseline["evaluation_manifests"].items():
            rows=[signed({"case_id":"case1","seed":seed,"policy_hash":"B0","oracle_ok":seed!=2,
                "model_id":"test","budget_hash":"budget","verifier_hash":"verifier","provider_fingerprint":{},
                "case_asset_hash":"assets","source_kind":"live_model"},"receipt_hash") for seed in [1,2,3]]
            evals[dataset]=signed({"schema_version":"r3e-aic-arena-evaluation-v1","dataset":dataset,"manifest_hash":mhash,
                "policy_hash":"B0","seeds":[1,2,3],"case_ids":["case1"],"cases":rows,"denominator":3,"repaired":2,"repair_rate":2/3})
        return signed({"schema_version":"r3e-aic-frozen-arm-v1","source_kind":"live_model","experiment_id":"test",
            "arm":which,"baseline":baseline,"memory_hash":"M0","final_policy_hash":"B0","rounds":[],
            "promotion_count":0,"red_archive_count":0,"evolution_claim":False,"evaluations":evals})
    return arm("static"),arm("adversarial")


def resign(value,field="result_hash"):
    return signed({k:v for k,v in value.items() if k!=field},field)


def test_comparison_fixed_denominator_and_zero_gain():
    a,b=arms()
    c=compare_arms(a,b)
    assert c["metrics"]["strider-subset4"]["delta"]==0
    bad=deepcopy(a["evaluations"]["strider-subset4"]);bad["cases"].pop();bad=resign(bad)
    with pytest.raises(ValueError,match="denominator"):verify_evaluation(bad)
    bad=deepcopy(a["evaluations"]["strider-subset4"]);bad["repair_rate"]=1;bad=resign(bad)
    with pytest.raises(ValueError,match="rate"):verify_evaluation(bad)


@pytest.mark.parametrize("mutation",["model","budget","seed","policy","guided","unaudited"])
def test_freeze_rejects_invalid_claims(mutation):
    a,b=arms()
    if mutation in {"model","budget"}:
        b["baseline"][mutation]="different";b["baseline"]=resign(b["baseline"],"baseline_hash")
    elif mutation=="seed": b["baseline"]["seeds"]=[1,2,4];b["baseline"]=resign(b["baseline"],"baseline_hash")
    elif mutation=="policy": a["final_policy_hash"]="changed";a=resign(a)
    elif mutation=="guided":
        row=b["evaluations"]["strider-subset4"]["cases"][0];row["source_kind"]="guided"
        b["evaluations"]["strider-subset4"]["cases"][0]=resign(row,"receipt_hash")
        b["evaluations"]["strider-subset4"]=resign(b["evaluations"]["strider-subset4"])
    else:b["evolution_claim"]=True
    b=resign(b)
    with pytest.raises(ValueError):compare_arms(a,b)


def test_observer_rejects_unaudited_and_injected_evidence(tmp_path):
    a,b=arms();data=compare_arms(a,b,live_only=False)
    target=tmp_path/"comparison.json";freeze(target,data)
    assert ArenaTelemetryService(ROOT,target).snapshot()["available"] is False
    assert ArenaTelemetryService(ROOT,tmp_path/"missing.json").snapshot()["available"] is False


def test_observer_cannot_write():
    context=CompetitionContext(ROOT,Path("/tmp/m3-observer-test"),observer=True)
    handler=object.__new__(Handler);handler.context=context;handler.path="/api/arena/promote"
    sent=[];handler._send_json=lambda status,payload:sent.append((status,payload))
    handler.do_POST()
    assert sent[0][0]==405
    handler.path="/api/repair";handler.do_POST();assert sent[-1][0]==405


def test_dirty_candidate_cannot_freeze(tmp_path, monkeypatch):
    _,_,state=setup_arm(tmp_path,"static")
    from competition.services import arena_freeze_service
    source_identity = arena_freeze_service.source_identity
    monkeypatch.setattr(arena_freeze_service, "source_identity",
                        lambda root: {**source_identity(root), "dirty": True})
    with pytest.raises(ValueError,match="clean"):
        freeze_arm(ROOT,state,[],tmp_path/"frozen.json")
    assert not (tmp_path/"frozen.json").exists()


def test_call_budget_is_reserved_and_survives_restart(tmp_path):
    calls=[];c=client(calls)
    # The upstream call intentionally errors after reservation; retries still cost a slot.
    budget=BudgetedClient(c,tmp_path/"budget.json",max_calls=1,max_tokens=100000)
    with pytest.raises(Exception):budget.complete_json(messages=[])
    restarted=BudgetedClient(c,tmp_path/"budget.json",max_calls=1,max_tokens=100000)
    with pytest.raises(RuntimeError,match="budget exhausted"):restarted.complete_json(messages=[])
