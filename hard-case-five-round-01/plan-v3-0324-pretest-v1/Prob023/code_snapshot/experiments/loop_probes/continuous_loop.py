"""Round-boundary Red/Blue adaptation; explicit client injection, no paid CLI.

Collection never executes hidden suites. Reference and deferred anchor trials
are measurement-only. Fresh directories only; reserved-exam collisions have bounded, recorded regeneration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import difflib
import json
import os
from pathlib import Path
import shutil

from experiments.loop_probes import red907, red907_measure as measure, red907_schedule as frozen
from experiments.loop_probes import witness_matrix as wm
from r3e.loop import continuous_state as state, red_continuous as red, repo_blue as rb, red_retry
from r3e.loop.red_regression import save_new
from r3e.knowledge.verilog_utils import safe_tokenize
from r3e.protocol.hashing import atomic_write_json, hash_payload

VERSION = "continuous_loop_static_exam_first_v1"
PROMOTION_VALIDATION = []
EXAM_QUEUE = None
TRAIN_QUEUE = None
PRETEST_DECISION = None
INITIAL_EXAM_POLICY = {'version':'static_exam_first_global_gate_v1','scope':'all_selected_designs',
    'stop_when':'all planned static exam samples pass','reuse_static_exam_for_final_comparison':True,
    'expose_exam_outcomes_to_training':False,'inconclusive_samples':'stop_without_difficulty_claim'}
PROMOTION_POLICY = {"version": "cached_certificate_no_regression_v2", "repeats": 2, "require_strict_gain": True, "replay_solved_practice": False, "cache_incumbent": True, "measure_initial_baseline": True, "final_exam_for_selection": False}
ROOT = Path(__file__).resolve().parents[2]
CONFIG = rb.RepoBlueConfig(budget_k=1, max_infra_retries=0, output_reserve=16000, context_tokens=128000, format_corrections=1)


class ValidationBaselineSaturated(measure.MeasurementRefused):
    """A completed baseline with no gain headroom; skip this design, not the batch."""



def promotion_max_calls(rounds, slots_per_round, fixed_tasks, start_round=0):
    # One real B0 baseline plus candidates only; cached incumbents cost no calls.
    evaluations = max(0, rounds - max(1, start_round) + 1) + int(start_round == 0)
    return evaluations * PROMOTION_POLICY["repeats"] * fixed_tasks * (1 + CONFIG.format_corrections)


def promotion_decision(incumbent, candidate, certificates):
    if set(incumbent) != set(candidate) or not set(certificates) <= set(candidate):
        raise ValueError("paired promotion samples or certificates missing")
    losses = sorted(k for k in candidate if (incumbent[k] or k in certificates) and not candidate[k])
    gains = sorted(k for k in candidate if candidate[k] and not incumbent[k])
    accepted = not losses and bool(gains)
    return {"accepted": accepted, "reason": "strict_gain_no_regression" if accepted else
            "regression" if losses else "no_strict_gain", "losses": losses, "gains": gains,
            "incumbent_passed": sum(incumbent.values()), "candidate_passed": sum(candidate.values()),
            "scheduled_pairs": len(candidate)}


def promotion_pass(trial, task_dir, carrier):
    if trial["status"] != "fixed":
        return False
    blue = Path(trial["directory"]) / "blue"
    encounters = [json.loads(l) for l in (blue / "encounters.jsonl").read_text().splitlines()]
    endpoint = encounters[-1]["result"]["final_candidate_hash"]
    archive = next((read(p) for p in (blue / "archive").glob("*.json") if read(p)["candidate_hash"] == endpoint), None)
    if archive is None:
        return False
    ef = read(carrier["evaluator_freeze"])
    root = Path(carrier["evaluator_root"])
    if any(hash_payload((root / f).read_text()) != h for f,h in ef["files"].items()):
        raise ValueError("validation evaluator changed")
    return measure._evaluate(rb.RepoTask.load(Path(task_dir)), archive["files"], ef,
                             root / Path(next(iter(ef["files"]))).parent)["result"] == "pass"

def read(path):
    return json.loads(Path(path).read_text())


def append(path, row):
    with Path(path).open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def code_identity():
    names = set(frozen.code_identity()) | {
        str(Path(__file__).relative_to(ROOT)), "experiments/loop_probes/continuous_measure.py",
        "experiments/loop_probes/continuous_audit.py",
        "experiments/loop_probes/sequence_curriculum.py", "r3e/loop/RED_SEQUENCE_CURRICULUM.md",
        "experiments/loop_probes/continuous_launch.py",
        "experiments/loop_probes/repair_feedback.py", "r3e/loop/RED_CONTINUOUS_LOOP.md",
        "r3e/loop/CONTINUOUS_BLUE_INTERFACE.md", "r3e/loop/targeted_prompts.py", "r3e/loop/red_syntax.py", "r3e/loop/red_retry.py", "r3e/loop/online_mutation.py"}
    names |= {str(p.relative_to(ROOT)) for p in (ROOT / "r3e/loop/assets/prob003").glob("*") if p.is_file()}
    return {name: frozen._sha(ROOT / name) for name in sorted(names)}


def task_identity(task_dir):
    measure._check_export(Path(task_dir))
    return rb.public_task_hash(rb.RepoTask.load(Path(task_dir)))


def mutant_identity(public, rtl):
    # Task IDs differ between exported anchors and generated mutants; compare
    # actual code/configuration instead. Ignore formatting/comments for exclusion.
    return hash_payload({"carrier": public["carrier_id"], "manifest": public["manifest_hash"],
                         "dependencies": public["dependencies"],
                         "tokens": red_retry.canonical_tokens([t.value for t in safe_tokenize(rtl)])})


def schedule(rounds, slots_per_round, carrier_count, anchor_count, seed, *, carrier_mode="fixed", fixed_carrier_index=0,
             anchor_repeats=1):
    if type(anchor_repeats) is not int or anchor_repeats < 1:
        raise ValueError("positive anchor repeat count required")
    if carrier_mode not in {"fixed", "rotate"} or type(fixed_carrier_index) is not int or not 0 <= fixed_carrier_index < carrier_count:
        raise ValueError("invalid carrier scheduling policy")
    # A new policy has its own seed namespace; labels are not provider determinism.
    base = int(hash_payload([VERSION, seed, carrier_mode, fixed_carrier_index, anchor_repeats])[7:19], 16)
    slots = [{"round": r, "slot_id": f"r{r}_s{s}", "carrier_index": (fixed_carrier_index if carrier_mode == "fixed"
                         else ((r - 1) * slots_per_round + s) % carrier_count),
              "red_seed": base + ((r - 1) * slots_per_round + s) * 3,
              "online_seed": base + ((r - 1) * slots_per_round + s) * 3 + 1,
              "reference_seed": base + ((r - 1) * slots_per_round + s) * 3 + 2}
             for r in range(1, rounds + 1) for s in range(slots_per_round)]
    probes = [{"snapshot": r, "anchor_index": a, "repeat": k,
               "seed": base + 3 * len(slots) + (r * anchor_count + a) * anchor_repeats + k}
              for r in (0, rounds) for a in range(anchor_count) for k in range(anchor_repeats)]
    return slots, probes


def blue_identity(plan):
    return {"runner": plan["blue_config"], "client": plan["client_config"], "tokenizer": plan["tokenizer"],
            "runner_code": plan["code"]["r3e/loop/repo_blue.py"]}


def make_plan(carriers, anchors, *, counter, client_config, rounds=3, slots_per_round=1, seed=700,
              carrier_mode="fixed", fixed_carrier_index=0, anchor_repeats=1, mechanism_focus=None,
              red_output_tokens=16000, reserved_collision_retries=0):
    """anchors: [{task_dir, carrier_index}]. Freeze all material before collection."""
    if type(rounds) is not int or type(slots_per_round) is not int or min(rounds, slots_per_round) < 1:
        raise ValueError("positive fixed round/slot counts required")
    if not carriers or not anchors or type(seed) is not int or seed < 0:
        raise ValueError("carriers, anchors and nonnegative seed required")
    if client_config["maximum_output_tokens"] < max(CONFIG.output_reserve, red_output_tokens):
        raise ValueError("client output authority below Red ceiling")
    if type(red_output_tokens) is not int or not 0 < red_output_tokens <= 16000:
        raise ValueError("invalid Red output ceiling")
    if type(reserved_collision_retries) is not int or not 0 <= reserved_collision_retries < red_retry.POLICY["max_online_attempts"]:
        raise ValueError("only one corrective online request is permitted")
    items = [{k: str(Path(v).resolve()) for k, v in c.items()} for c in carriers]
    if type(fixed_carrier_index) is not int or not 0 <= fixed_carrier_index < len(items):
        raise ValueError("invalid fixed carrier index")
    ids = [frozen._carrier_identity(c) for c in items]
    if mechanism_focus is not None:
        if carrier_mode != "fixed":
            raise ValueError("mechanism focus requires a fixed carrier")
        c = items[fixed_carrier_index]
        red.validate_focus(mechanism_focus, red907.public_material(Path(c["package"]), read(c["suite_freeze"])))
    if len({i["carrier_id"] for i in ids}) != len(ids):
        raise ValueError("duplicate carrier IDs")
    qualified = []
    for c in items:
        q = wm.qualify(Path(c["package"]), read(c["suite_freeze"]))
        if not q["qualified"]:
            raise ValueError("public carrier qualification failed")
        qualified.append({k: q[k] for k in ("package_files", "tool")})
    anchor_rows = []
    for a in anchors:
        idx = a["carrier_index"]
        c = items[idx]
        public = red907.public_material(Path(c["package"]), read(c["suite_freeze"]))
        task_dir = Path(a["task_dir"]).resolve()
        task = rb.RepoTask.load(task_dir)
        setup = rb.setup(task, counter, CONFIG)
        if (setup.route != "direct" or {k: v["result"] for k, v in setup.baseline.evidence.get("suites", {}).items()}
                != {"W_bug": "visible_fail", "W_preserve": "visible_pass"}):
            raise ValueError("anchor must be a direct, public-qualified defect")
        anchor_rows.append({"task_dir": str(task_dir), "carrier_index": idx,
                            "task_hash": task_identity(task_dir),
                            "mutant_identity": mutant_identity(public, (task.repo / public["editable_file"]).read_text())})
    if len({a["task_hash"] for a in anchor_rows}) != len(anchor_rows):
        raise ValueError("duplicate anchors")
    slots, probes = schedule(rounds, slots_per_round, len(items), len(anchors), seed,
                             carrier_mode=carrier_mode, fixed_carrier_index=fixed_carrier_index, anchor_repeats=anchor_repeats)
    return {"version": VERSION, "rounds": rounds, "slots_per_round": slots_per_round, "seed": seed,
            "carrier_mode": carrier_mode, "fixed_carrier_index": fixed_carrier_index,
            "anchor_repeats": anchor_repeats, "mechanism_focus": deepcopy(mechanism_focus), "initial_exam_policy":deepcopy(INITIAL_EXAM_POLICY),
            "path_policy": "absolute_paths_preserve_original_locations",
            "carriers": items, "identities": ids, "qualifications": qualified, "anchors": anchor_rows,
            "slots": slots, "anchor_probes": probes, "blue_config": asdict(CONFIG), "red_output_tokens": red_output_tokens,
            "client_config": client_config, "tokenizer": counter.identity, "runtime": frozen.runtime_identity(),
            "learning": state.LEARNING, "retrieval": state.RETRIEVAL, "red_bank_tokens": 8192,
            "reserved_collision_retries": reserved_collision_retries, "generation_policy": deepcopy(red_retry.POLICY), "mutation_constraints":deepcopy(red.online_mutation.CONTRACT),
            "promotion": deepcopy(PROMOTION_POLICY), "validation_tasks": deepcopy(PROMOTION_VALIDATION),
            "validation_hashes": [task_identity(t) for t in PROMOTION_VALIDATION],
            "max_calls": promotion_max_calls(rounds, slots_per_round, len(PROMOTION_VALIDATION)) + (1 + reserved_collision_retries + 2 * (1 + CONFIG.format_corrections)) * len(slots) + (1 + CONFIG.format_corrections) * len(probes), "code": code_identity(),
            "authorization": "offline plan only; no paid launcher or monetary approval"}


def validate_plan(plan):
    if (plan.get("initial_exam_policy") != INITIAL_EXAM_POLICY or plan.get("mutation_constraints") != red.online_mutation.CONTRACT or plan.get("generation_policy") != red_retry.POLICY or plan.get("promotion") != PROMOTION_POLICY or plan.get("validation_tasks") != PROMOTION_VALIDATION
            or plan.get("validation_hashes") != [task_identity(t) for t in PROMOTION_VALIDATION]
            or plan["version"] != VERSION or plan["code"] != code_identity()
            or plan["runtime"] != frozen.runtime_identity() or plan["blue_config"] != asdict(CONFIG)
            or plan["learning"] != state.LEARNING or plan["retrieval"] != state.RETRIEVAL
            or type(plan["red_output_tokens"]) is not int or not 0 < plan["red_output_tokens"] <= 16000
            or plan["red_bank_tokens"] != 8192
            or plan["path_policy"] != "absolute_paths_preserve_original_locations"):
        raise ValueError("code/runtime/policy changed; create a fresh plan")
    if [frozen._carrier_identity(c) for c in plan["carriers"]] != plan["identities"]:
        raise ValueError("frozen carrier/evaluator material changed")
    if plan["mechanism_focus"] is not None:
        if plan["carrier_mode"] != "fixed":
            raise ValueError("mechanism focus requires a fixed carrier")
        c = plan["carriers"][plan["fixed_carrier_index"]]
        red.validate_focus(plan["mechanism_focus"], red907.public_material(Path(c["package"]), read(c["suite_freeze"])))
    for c, q in zip(plan["carriers"], plan["qualifications"], strict=True):
        if wm.package_files(Path(c["package"])) != q["package_files"]:
            raise ValueError("qualified package changed")
    for a in plan["anchors"]:
        if task_identity(a["task_dir"]) != a["task_hash"]:
            raise ValueError("anchor changed")
        item = plan["carriers"][a["carrier_index"]]
        public = red907.public_material(Path(item["package"]), read(item["suite_freeze"]))
        task = rb.RepoTask.load(Path(a["task_dir"]))
        if mutant_identity(public, (task.repo / public["editable_file"]).read_text()) != a["mutant_identity"]:
            raise ValueError("anchor exclusion identity changed")
    retries = plan["reserved_collision_retries"]
    if type(retries) is not int or not 0 <= retries < red_retry.POLICY["max_online_attempts"]:
        raise ValueError("invalid reserved collision retry limit")
    n = plan["rounds"] * plan["slots_per_round"]
    slots, probes = schedule(plan["rounds"], plan["slots_per_round"], len(plan["carriers"]),
                             len(plan["anchors"]), plan["seed"], carrier_mode=plan["carrier_mode"],
                             fixed_carrier_index=plan["fixed_carrier_index"], anchor_repeats=plan["anchor_repeats"])
    if (plan["slots"] != slots or plan["anchor_probes"] != probes
            or plan["max_calls"] != promotion_max_calls(plan["rounds"], plan["slots_per_round"], len(plan["validation_tasks"])) + (1 + retries + 2 * (1 + CONFIG.format_corrections)) * n + (1 + CONFIG.format_corrections) * len(probes)):
        raise ValueError("schedule/call cap mismatch")


def authenticate(snap, run, blue_config, parent):
    state.validate_snapshot(snap, blue_config, parent)
    for entry in snap["entries"]:
        source = entry["body"]["source"]
        record = read(run / "sources" / (source["encounter_hash"][7:] + ".json"))
        task = rb.RepoTask.load(Path(record["task_dir"]))
        archive = read(record["archive_path"])
        encounter_rows = [json.loads(line) for line in
                          (Path(record["archive_path"]).parent.parent / "encounters.jsonl").read_text().splitlines()]
        if (source != record["source"] or hash_payload(record["encounter"]) != source["encounter_hash"]
                or encounter_rows != [record["encounter"]]
                or hash_payload(archive) != source["archive_hash"]
                or hash_payload(record["replay"]) != source["public_replay_hash"]
                or task_identity(record["task_dir"]) != source["task_hash"]
                or state.episode_entry(source, task.spec, archive, record["public_rows"]) != entry):
            raise ValueError("experience source provenance changed")


def online_evidence(task_dir, blue_dir, *, run, slot, proposal, incoming, carrier_id):
    """Allowlist real online endpoint evidence; no reference or evaluator inputs."""
    task = rb.RepoTask.load(task_dir)
    enc, = [json.loads(l) for l in (blue_dir / "encounters.jsonl").read_text().splitlines()]
    result = enc["result"]
    if result["experience"]["snapshot_hash"] != hash_payload(incoming):
        raise ValueError("online result is bound to a different snapshot")
    attempts = [a for a in result["attempts"] if not a.get("infra_failure")]
    last = attempts[-1] if attempts else {}
    endpoint = result["final_candidate_hash"]
    archives = [(p, read(p)) for p in (blue_dir / "archive").glob("*.json")]
    matches = [(p, a) for p, a in archives if a["task_id"] == task.task["task_id"] and a["candidate_hash"] == endpoint]
    noop = endpoint is None and last.get("changed_files") == [] and last.get("tier") == "visible_fail"
    if (not noop and len(matches) != 1) or last.get("tier") in {"invalid_edit", "no_answer"}:
        return None, None, {"reason": "no_usable_materialized_endpoint", "outcome": result["outcome"]}
    archive_path, archive = (None, {"files": {}, "baseline_hashes": {}, "patch": ""}) if noop else matches[0]
    if (not noop and hash_payload(archive["files"]) != endpoint) or any(
            hash_payload((task.repo / p).read_text()) != archive["baseline_hashes"][p] for p in archive["files"]):
        raise ValueError("online archive identity mismatch")
    expected_patch = "".join("".join(difflib.unified_diff((task.repo / p).read_text().splitlines(True),
                                text.splitlines(True), "a/" + p, "b/" + p)) for p, text in sorted(archive["files"].items()))
    if expected_patch != archive["patch"]:
        raise ValueError("archive patch does not reconstruct candidate")
    replay = rb.execute(task, archive["files"])
    if replay.tier != last.get("tier"):
        return None, None, {"reason": "public_replay_mismatch"}
    rows = {k: v["result"] for k, v in replay.evidence.get("suites", {}).items()}
    passed = replay.tier == "visible_pass"
    failed = (replay.tier == "visible_fail" and any(v.get("fail_marker_found") for v in replay.evidence["suites"].values()))
    if not (passed or failed):
        return None, None, {"reason": "nonfunctional_endpoint", "tier": replay.tier}
    source = {"run_id": run.name, "round": slot["round"], "slot_id": slot["slot_id"],
              "task_hash": rb.public_task_hash(task), "carrier_id": carrier_id,
              "mutant_hash": proposal["buggy_rtl_hash"], "candidate_hash": endpoint,
              "encounter_hash": hash_payload(enc), "archive_hash": hash_payload(archive),
              "public_replay_hash": hash_payload(asdict(replay))}
    obs = {"round": slot["round"], "slot_id": slot["slot_id"], "carrier_id": carrier_id,
           "target_snapshot_hash": hash_payload(incoming), "mutant_hash": source["mutant_hash"],
           "mutation_edits": proposal["mutation_edits"], "blue_patch": archive["patch"], "public_rows": rows,
           "public_evidence": json.dumps(replay.evidence)[:CONFIG.max_evidence_chars],
           "label": (rb.EXPERIENCE_LABEL if passed else "valid_no_op_single_sample_unconfirmed" if noop
                     else "public_functional_failure_single_sample_unconfirmed"),
           "source_hash": source["encounter_hash"]}
    save_new(run / "sources" / (source["encounter_hash"][7:] + ".json"), {
        "source": source, "encounter": enc, "archive_path": str(archive_path) if archive_path else None, "task_dir": str(task_dir),
        "replay": asdict(replay), "public_rows": rows, "mutation_edits": proposal["mutation_edits"]})
    return obs, state.episode_entry(source, task.spec, archive, rows) if passed else None, {"reason": obs["label"]}


def collect(plan, out, *, client, counter):
    validate_plan(plan)
    if TRAIN_QUEUE is None or EXAM_QUEUE is None:
        raise ValueError('batch pretest/training/exam queues must be initialized before any calls')
    if (client.total_calls or client.max_calls != plan["max_calls"]
            or client.config.public_identity != plan["client_config"] or counter.identity != plan["tokenizer"]):
        raise ValueError("fresh client with exact frozen cap/configuration/tokenizer required")
    plan = deepcopy(plan)
    plan_hash = hash_payload(plan)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    save_new(out / "plan.json", plan)
    save_new(out / "plan_hash.json", {"hash": plan_hash})
    for name, digest in plan["code"].items():
        dest = out / "code_snapshot" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
        if frozen._sha(dest) != digest:
            raise ValueError("code snapshot changed while copying")
    for name in ("calls", "slots", "probes", "events", "promotions"):
        (out / f"{name}.jsonl").touch()
    client.output_caps["blue_inference"] = CONFIG.output_reserve
    label, commits, seen, completed_slots, completed_probes = {}, [], set(), set(), set()
    certificates = set()
    incumbent_cache = None
    gate = None
    initial_data = None
    accepted_promotions = 0
    prior_callback = client.on_call

    def log_call(row):
        append(out / "calls.jsonl", {**row, **label})
        if prior_callback:
            prior_callback(row)

    client.on_call = log_call
    identity = blue_identity(plan)
    b0 = state.snapshot(0, identity)

    def commit(blue, observations, decisions):
        r = blue["committed_round"]
        record = {"round": r, "promotion_hash": hash_payload(gate) if r > 0 else None, "parent_commit_hash": hash_payload(commits[-1]) if commits else None,
                  "blue": blue, "red": {"round": r, "observations": deepcopy(observations)},
                  "update_decisions": decisions}
        atomic_write_json(out / "rounds" / str(r) / "commit.json", record)
        commits.append(record)
        append(out / "events.jsonl", {"event": "round_commit", "round": r, "commit_hash": hash_payload(record)})

    def check():
        validate_plan(plan)
        if hash_payload(read(out / "plan.json")) != plan_hash:
            raise ValueError("stored plan changed")
        for i, c in enumerate(commits):
            if read(out / "rounds" / str(i) / "commit.json") != c:
                raise ValueError("committed state changed")
            authenticate(c["blue"], out, identity, commits[i - 1]["blue"] if i else None)

    def blue_trial(task_dir, directory, snap, seed, role, slot_id, *, candidate=False):
        check()
        if candidate:
            authenticate(snap, out, identity, commits[-1]["blue"])
        label.clear()
        label.update(role=role, slot_id=slot_id, snapshot_id=snap["snapshot_id"])
        task = rb.RepoTask.load(task_dir)
        envelope = state.delivery(snap, task, counter)
        directory.mkdir(parents=True, exist_ok=False)
        save_new(directory / "delivery.json", envelope)
        try:
            results = measure.run_blue(task_dir, directory / "blue", client=client, counter=counter,
                cfg=CONFIG, seed=seed, encounters=1, direct_only=True, endpoint_protocol="screening",
                experience=envelope, experience_journal=directory / "experience.jsonl",
                retrieval_policy_hash=hash_payload(state.RETRIEVAL))
            return {"status": results[0]["outcome"], "directory": str(directory),
                    "task_hash": envelope["task_hash"], "delivery_hash": hash_payload(envelope),
                    "snapshot_hash": hash_payload(snap), "online_seed": seed * 10}
        except measure.DirectContextLimit as exc:
            return {"status": "context_limit", "reason": str(exc), "directory": str(directory)}
        except measure.MeasurementRefused as exc:
            if not str(exc).startswith("baseline no longer shows the admission row:"):
                raise
            return {"status": "public_baseline_inconclusive", "reason": str(exc), "directory": str(directory)}

    status = "aborted"
    proposal_history, generation_feedback = [], []
    checked_proposals = {}
    rounds_without_experience = 0

    def stop(reason, **details):
        record = {"reason": reason, **details}
        save_new(out / "stop_reason.json", record)
        append(out / "events.jsonl", {"event": "quality_stop", **record})
        if reason == "validation_baseline_saturated":
            raise ValidationBaselineSaturated(reason)
        raise measure.MeasurementRefused(reason)
    def persist(phase_status):
        summary = {"version": VERSION, "status": phase_status, "plan_hash": plan_hash,
                   "skip_reason": "validation_baseline_saturated" if phase_status == "skipped" else None,
                   "committed_rounds": len(commits) - 1, "calls": client.total_calls,
                   "max_calls": plan["max_calls"], "scheduled_slots": len(plan["slots"]),
                   "completed_slots": len(completed_slots),
                   "qualified_practice_slots":sum(json.loads(line).get('admission')=='admitted' for line in (out/'slots.jsonl').read_text().splitlines()),
                   "empty_practice_slots":sum(json.loads(line).get('admission')!='admitted' for line in (out/'slots.jsonl').read_text().splitlines()),
                   "human_prepared_replacements":0, "uncompleted_slot_ids":
                   [s["slot_id"] for s in plan["slots"] if s["slot_id"] not in completed_slots],
                   "scheduled_probes": len(plan["anchor_probes"]), "completed_probes": len(completed_probes),
                   "uncompleted_probes": [p for p in plan["anchor_probes"]
                                          if (p["snapshot"], p["anchor_index"], p["repeat"]) not in completed_probes],
                   "evaluator_executed": initial_data is not None, "validation_evaluator_executed": incumbent_cache is not None, "confirmation_executed": False,
                   "accepted_promotions": accepted_promotions, "retained_experience_entries": len(commits[-1]["blue"]["entries"]) if commits else 0}
        atomic_write_json(out / "collection.json", summary)
        return summary

    def verify_initial_exam():
        if initial_data is None or read(out/'initial_exam.json') != initial_data:
            raise ValueError('initial static exam record changed')
        baseline_rows=[json.loads(line) for line in (out/'probes.jsonl').read_text().splitlines()
                       if json.loads(line)['snapshot']==0]
        if baseline_rows != initial_data['probe_rows']:
            raise ValueError('initial static exam trials changed or were repeated')
        for name,digest in initial_data['evidence_hashes'].items():
            if frozen._sha(out/name) != digest:
                raise ValueError('initial static exam evidence changed: '+name)

    def train():
        global PROMOTION_VALIDATION
        nonlocal incumbent_cache, accepted_promotions, rounds_without_experience, gate
        previous_validation=PROMOTION_VALIDATION
        previous_callback=client.on_call
        PROMOTION_VALIDATION=deepcopy(plan['validation_tasks'])
        client.on_call=log_call
        phase_status='aborted'
        try:
            if PRETEST_DECISION != 'continue':
                raise ValueError('training requires a complete, unsaturated batch initial exam')
            verify_initial_exam()
            append(out/'events.jsonl',{'event':'training_started_after_initial_exam_gate'})
            baseline_trials, baseline_scores = [], {}
            for task_dir in plan["validation_tasks"]:
                task_hash = task_identity(task_dir)
                for repeat in range(PROMOTION_POLICY["repeats"]):
                    sample = task_hash + ":" + str(repeat)
                    pair_seed = int(hash_payload(["promotion_validation_v1", plan["seed"], task_hash, repeat])[7:19], 16)
                    trial = blue_trial(Path(task_dir), out / "validation_baseline" / task_hash[7:19] / str(repeat),
                                       b0, pair_seed, "promotion_baseline", None)
                    passed = promotion_pass(trial, task_dir, plan["carriers"][0])
                    baseline_scores[sample] = passed
                    baseline_trials.append({"role": "baseline", "task_dir": task_dir, "repeat": repeat,
                                            "seed": pair_seed, "passed": passed, **trial})
            incumbent_cache = {"state_hash": b0["state_hash"], "scores": baseline_scores,
                               "trials": baseline_trials, "snapshot_hash": hash_payload(b0)}
            cache_path = out / "validation_baseline.json"
            save_new(cache_path, incumbent_cache)
            certificates.update(k for k,v in baseline_scores.items() if v)
            # Saturation limits promotion, not the promised training/exam schedule.
            for r in range(1, plan["rounds"] + 1):
                check()
                # Reserve this and all remaining online work plus every deferred anchor.
                remaining = promotion_max_calls(plan["rounds"], plan["slots_per_round"], len(plan["validation_tasks"]), start_round=r) + (1 + plan["reserved_collision_retries"] + 2 * (1 + CONFIG.format_corrections)) * sum(
                    s["round"] >= r for s in plan["slots"]) + (1 + CONFIG.format_corrections) * sum(p["snapshot"] != 0 for p in plan["anchor_probes"])
                if client.max_calls - client.total_calls < remaining:
                    raise ValueError("insufficient reservation for remaining schedule and probes")
                incoming = commits[-1]["blue"]
                observations = deepcopy(commits[-1]["red"]["observations"])
                added, candidates = [], []
                for slot in (s for s in plan["slots"] if s["round"] == r):
                    check()
                    item = plan["carriers"][slot["carrier_index"]]
                    public = red907.public_material(Path(item["package"]), read(item["suite_freeze"]))
                    directory = out / "rounds" / str(r) / slot["slot_id"]
                    label.clear()
                    label.update(role="red", slot_id=slot["slot_id"], snapshot_id=incoming["snapshot_id"])
                    before = client.total_calls
                    target, target_omissions = state.target_view(incoming, public["specification"], identity, counter)
                    excluded = {a["mutant_identity"]: "reserved_task_collision" for a in plan["anchors"]}
                    for task_dir in plan["validation_tasks"]:
                        item_task = rb.RepoTask.load(Path(task_dir))
                        excluded[mutant_identity(public, (item_task.repo / public["editable_file"]).read_text())] = "validation_collision"
                    if plan["mechanism_focus"] is not None:
                        from r3e.loop.blue_provider import apply_text_edits
                        seed_rtl = apply_text_edits(public["clean_rtl"], plan["mechanism_focus"]["seed_edits"])
                        excluded[mutant_identity(public, seed_rtl)] = "historical_seed_repeat"
                    rejected_edits, generations = list(proposal_history), []
                    admitted=False
                    for attempt in range(plan["reserved_collision_retries"] + 1):
                        label['generation_attempt']=attempt
                        attempt_dir=directory/('red' if attempt==0 else f'red_retry_{attempt}')
                        attempt_seed=(slot['red_seed'] if attempt==0 else int(hash_payload([slot['red_seed'],'reserved_retry',attempt])[7:19],16))
                        batch=red.propose(public,observations,round_index=r,snapshot_hash=hash_payload(incoming),
                            red_state_hash=hash_payload(commits[-1]['red']),seed=attempt_seed,directory=attempt_dir,
                            client=client,counter=counter,output_tokens=plan['red_output_tokens'],target_blue=target,
                            target_omissions=target_omissions,mechanism_focus=plan['mechanism_focus'],rejected_edits=rejected_edits,
                            generation_feedback=generation_feedback[-12:])
                        proposals=batch['candidates'] if batch['status']=='candidate_batch' else [batch]
                        for candidate_index,proposal in enumerate(proposals):
                            fingerprint = mutant_identity(public, proposal["buggy_rtl"]) if proposal["status"] == "proposal" else None
                            collision = excluded.get(fingerprint) in {"reserved_task_collision", "validation_collision"}
                            admission_dir = directory / ("admission" if attempt == 0 and candidate_index == 0 else f"admission_a{attempt}_c{candidate_index}")
                            forbidden_mechanisms=red_retry.blocked_mechanisms(generation_feedback,r)
                            repeated_mechanisms=(set(red_retry.mechanism(proposal)) & set(forbidden_mechanisms)) if proposal['status']=='proposal' else set()
                            if repeated_mechanisms:
                                admission={'status':'rejected','reason':'blocked_failed_mechanism',
                                           'blocked_mechanisms':sorted(repeated_mechanisms),
                                           'note':'A changed operand does not satisfy the mandatory mechanism switch. No EDA or Blue request is made.'}
                                save_new(admission_dir/'proposal.json',proposal)
                                save_new(admission_dir/'admission.json',admission)
                            elif fingerprint in excluded:
                                admission = {"status": "rejected", "reason": excluded[fingerprint]}
                                save_new(admission_dir / "proposal.json", proposal)
                                save_new(admission_dir / "admission.json", admission)
                            elif fingerprint is not None and fingerprint in checked_proposals:
                                previous = checked_proposals[fingerprint]
                                old = previous["admission"]
                                admission = {"status": "rejected",
                                             "reason": "duplicate_within_arm" if old["status"] == "admitted" else "repeated_rejected_proposal",
                                             "original_reason": old.get("reason"),
                                             "suites": deepcopy(old.get("suites", {})),
                                             "reused_from": previous["directory"],
                                             "reused_admission_hash": hash_payload(old),
                                             "note": "Same tokenized implementation/configuration; reuse prior public test evidence without rerunning EDA."}
                                save_new(admission_dir / "proposal.json", proposal)
                                save_new(admission_dir / "admission.json", admission)
                            else:
                                admission = red907.check_proposal(Path(item["package"]), read(item["suite_freeze"]),
                                                                  proposal, admission_dir, seen=seen)
                                stable_cells = admission.get("suites", {})
                                stable = all(stable_cells.get(s, {}).get("deterministic") is True and
                                             stable_cells[s].get("tier") in {"pass", "fail"}
                                             for s in ("W_bug", "W_preserve"))
                                if fingerprint is not None and (admission["status"] == "admitted" or stable):
                                    checked_proposals[fingerprint] = {"admission": deepcopy(admission), "directory": str(admission_dir)}
                            edits = proposal.get("mutation_edits")
                            if isinstance(edits, list) and edits:
                                proposal_history.append(edits)
                                rejected_edits.append(edits)
                            if admission["status"] != "admitted":
                                feedback = red.admission_feedback(admission, proposal, round_index=r, attempt=attempt)
                                feedback=red_retry.annotate(feedback,proposal,generation_feedback)
                                generation_feedback.append(feedback)
                                save_new(admission_dir / "generation_feedback.json", feedback)
                            generation = {"attempt": attempt, "candidate_index":candidate_index, "directory": str(attempt_dir), "seed": attempt_seed,
                                          "status": proposal["status"], "mechanisms":red_retry.mechanism(proposal), "reserved_collision": collision,
                                          "admission_directory": str(admission_dir),
                                          "admission": admission["status"], "reason": admission.get("reason")}
                            generations.append(generation)
                            append(out / "generation_attempts.jsonl", {"round": r, "slot_id": slot["slot_id"], **generation})
                            if admission["status"] == "admitted":
                                admitted=True
                                break
                        if admitted or batch['status']=='abstained':
                            break
                    generation_source='online_red' if admitted else 'no_qualified_online_challenge'
                    if not admitted:
                        append(out/'empty_practice.jsonl',{'round':r,'slot_id':slot['slot_id'],
                            'online_requests':attempt+1,'candidates_checked':len(generations),
                            'last_reason':admission.get('reason'),'replacement_used':False})
                    label.pop("generation_attempt", None)
                    row = {**slot, "carrier_id": public["carrier_id"], "incoming_snapshot_hash": hash_payload(incoming),
                           "generation_status": proposal["status"], "admission": admission["status"], "online_generation_requests":attempt+1,
                           "admission_directory": str(admission_dir),
                           "reason": admission.get("reason"), "generation_attempts": generations, "generation_source":generation_source, "trials": {}}
                    if admission["status"] == "admitted":
                        task_dir = admission_dir / "blue_task"
                        # Order is fixed from slot ordinal; both roles run even if one has an operational failure.
                        order = ("online", "reference") if (r + slot["carrier_index"]) % 2 else ("reference", "online")
                        for role in order:
                            row["trials"][role] = blue_trial(task_dir, directory / role,
                                incoming if role == "online" else b0, slot[role + "_seed"], role, slot["slot_id"])
                        if (directory / "online/blue/encounters.jsonl").exists():
                            obs, entry, decision = online_evidence(task_dir, directory / "online/blue", run=out,
                                slot=slot, proposal=proposal, incoming=incoming, carrier_id=public["carrier_id"])
                            row["learning_source"] = decision
                            if obs:
                                added.append(obs)
                            if entry:
                                candidates.append(entry)
                    row["calls"] = client.total_calls - before
                    append(out / "slots.jsonl", row)
                    completed_slots.add(slot["slot_id"])
                    # No prepared replacement: an empty slot carries state forward and never cancels exams.
                rounds_without_experience = 0 if candidates else rounds_without_experience + 1
                # Unsuccessful learning is a result; it must not cancel final exams.
                candidate, decisions = state.update(incoming, candidates, identity, counter)
                gate = {"round": r, "accepted": False, "reason": "no_new_experience", "trials": [],
                        "incumbent_state_hash": incoming["state_hash"], "candidate_state_hash": candidate["state_hash"],
                        "candidate_snapshot": candidate}
                if candidate["state_hash"] != incoming["state_hash"]:
                    if read(cache_path) != incumbent_cache or incumbent_cache["state_hash"] != incoming["state_hash"]:
                        raise ValueError("incumbent validation cache changed or belongs to another state")
                    incumbent_scores = deepcopy(incumbent_cache["scores"])
                    candidate_scores, gate_trials = {}, []
                    for task_dir in plan["validation_tasks"]:
                        task_hash = task_identity(task_dir)
                        for repeat in range(PROMOTION_POLICY["repeats"]):
                            sample = task_hash + ":" + str(repeat)
                            pair_seed = int(hash_payload(["promotion_validation_v1", plan["seed"], task_hash, repeat])[7:19], 16)
                            trial = blue_trial(Path(task_dir), out / "promotion" / str(r) / task_hash[7:19] / str(repeat) / "candidate",
                                               candidate, pair_seed, "promotion_candidate", None, candidate=True)
                            passed = promotion_pass(trial, task_dir, plan["carriers"][0])
                            candidate_scores[sample] = passed
                            gate_trials.append({"role": "candidate", "task_dir": task_dir, "repeat": repeat,
                                                "seed": pair_seed, "passed": passed, **trial})
                    decision = promotion_decision(incumbent_scores, candidate_scores, certificates)
                    gate.update(decision, trials=gate_trials, incumbent_scores=incumbent_scores,
                                candidate_scores=candidate_scores, incumbent_cache_path=str(cache_path),
                                incumbent_cache_hash=hash_payload(incumbent_cache))
                    if gate["accepted"]:
                        certificates.update(k for k,v in candidate_scores.items() if v)
                        accepted_promotions += 1
                        incumbent_cache = {"state_hash": candidate["state_hash"], "scores": candidate_scores,
                                           "trials": gate_trials, "snapshot_hash": hash_payload(candidate)}
                        cache_path = out / "promotion" / str(r) / "accepted_cache.json"
                        save_new(cache_path, incumbent_cache)
                blue = candidate if gate["accepted"] else state.snapshot(r, identity, incoming["entries"], incoming)
                gate.update(retained_state_hash=blue["state_hash"], certificates=sorted(certificates),
                            retained_entries=len(blue["entries"]), accepted_promotions=accepted_promotions,
                            retained_validation_passed=sum(incumbent_cache["scores"].values()),
                            retained_cache_path=str(cache_path), retained_cache_hash=hash_payload(incumbent_cache))
                append(out / "promotions.jsonl", gate)
                decisions.append({"promotion": gate["reason"], "accepted": gate["accepted"]})
                commit(blue, [*observations, *added], decisions)
            append(out / "events.jsonl", {"event": "online_collection_complete"})
            def final_exams():
                global PROMOTION_VALIDATION
                previous_validation=PROMOTION_VALIDATION
                previous_callback=client.on_call
                PROMOTION_VALIDATION=deepcopy(plan['validation_tasks'])
                client.on_call=log_call
                try:
                    check()
                    append(out/'events.jsonl',{'event':'final_exam_started','frozen_state_hash':commits[-1]['blue']['state_hash']})
                    verify_initial_exam()
                    for probe in plan["anchor_probes"]:
                        if probe["snapshot"] == 0:
                            continue
                        anchor = plan["anchors"][probe["anchor_index"]]
                        name = f"b{probe['snapshot']}_a{probe['anchor_index']}"
                        if plan["anchor_repeats"] > 1:
                            name += f"_repeat{probe['repeat']}"
                        result = blue_trial(Path(anchor["task_dir"]), out / "anchors" / name,
                                            commits[probe["snapshot"]]["blue"], probe["seed"], "anchor", None)
                        append(out / "probes.jsonl", {**probe, **result})
                        completed_probes.add((probe["snapshot"], probe["anchor_index"], probe["repeat"]))
                    summary=read(out/'collection.json')
                    summary.update(status='complete',calls=client.total_calls,completed_probes=len(completed_probes),uncompleted_probes=[])
                    atomic_write_json(out/'collection.json',summary)
                    append(out/'events.jsonl',{'event':'final_exam_complete'})
                except Exception:
                    summary=read(out/'collection.json')
                    summary.update(status='aborted',calls=client.total_calls,completed_probes=len(completed_probes))
                    atomic_write_json(out/'collection.json',summary)
                    raise
                finally:
                    PROMOTION_VALIDATION=previous_validation
                    client.on_call=previous_callback
            if EXAM_QUEUE is None:
                raise ValueError('batch exam queue required: final exams follow all designs training')
            EXAM_QUEUE.append(final_exams)
            phase_status='trained'
        finally:
            PROMOTION_VALIDATION=previous_validation
            client.on_call=previous_callback
            persist(phase_status)
        return read(out/'collection.json')

    try:
        commit(b0, [], [])
        scores=[]
        append(out/'events.jsonl',{'event':'initial_static_exam_started'})
        for probe in plan['anchor_probes']:
            if probe['snapshot']!=0:
                continue
            anchor=plan['anchors'][probe['anchor_index']]
            name=f"b0_a{probe['anchor_index']}_repeat{probe['repeat']}"
            result=blue_trial(Path(anchor['task_dir']),out/'anchors'/name,b0,probe['seed'],'anchor',None)
            row={**probe,**result}
            append(out/'probes.jsonl',row)
            completed_probes.add((probe['snapshot'],probe['anchor_index'],probe['repeat']))
            valid=result['status'] in {'fixed','not_fixed'}
            passed=promotion_pass(result,anchor['task_dir'],plan['carriers'][anchor['carrier_index']]) if valid else False
            scores.append({'anchor_index':probe['anchor_index'],'repeat':probe['repeat'],
                           'valid_measurement':valid,'passed':passed,'status':result['status']})
        evidence={str(p.relative_to(out)):frozen._sha(p) for directory in (out/'anchors').iterdir()
                  for p in directory.rglob('*') if p.is_file() and p.suffix in {'.json','.jsonl'}}
        initial_data={'version':INITIAL_EXAM_POLICY['version'],'passed':sum(x['passed'] for x in scores),
            'samples':len(scores),'valid_measurements':sum(x['valid_measurement'] for x in scores),'scores':scores,
            'probe_rows':[json.loads(line) for line in (out/'probes.jsonl').read_text().splitlines()],
            'evidence_hashes':evidence,'frozen_b0_snapshot_hash':hash_payload(b0),
            'reuse_for_final_comparison':True,'teaches_training':False}
        save_new(out/'initial_exam.json',initial_data)
        append(out/'events.jsonl',{'event':'initial_static_exam_finished','passed':initial_data['passed'],
                                 'samples':initial_data['samples']})
        TRAIN_QUEUE.append(train)
        status='pretested'
    finally:
        client.on_call=prior_callback
        summary=persist(status)
    return summary
