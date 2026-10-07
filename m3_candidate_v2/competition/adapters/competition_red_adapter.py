"""Compose existing single-target Grounded adapters under the Core schedule."""
from copy import deepcopy
from pathlib import Path
from r3e.arena.real_grounded_adapter import RealGroundedArenaAdapter
from r3e.red.grounded.operator_ast import operator_nodes
from r3e.protocol.hashing import hash_payload
from competition.arena.isolation import require_evolution_manifest
from competition.arena.evidence import freeze

class CompetitionGroundedRedAdapter:
    def __init__(self, *, root, manifest, client, artifact_root, round_id):
        require_evolution_manifest(manifest)
        self.client = client
        self.artifact_root = Path(artifact_root)
        self.round_id = round_id
        self.rows = manifest["rows"]
        if any(row.get("eligible") is not True for row in self.rows):
            raise ValueError("Grounded evolution rows must be eligible")
        self.root = Path(root)
        self.manifest_path = self.artifact_root / "targets.jsonl"
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in self.rows)
        if self.manifest_path.exists() and self.manifest_path.read_text() != content:
            raise ValueError("Red target manifest changed")
        self.manifest_path.write_text(content)
        self.adapters = [RealGroundedArenaAdapter(project_root=root, manifest_path=self.manifest_path,
            client=client, artifact_root=self.artifact_root / ("target-"+str(i)),
            case_id=row["case_id"], round_id=round_id) for i,row in enumerate(self.rows)]
        from r3e.red.grounded.registry import load_grounded_registries
        registries = load_grounded_registries(
            family_registry=self.root/"configs/red/grounded_family_registry_v1.json",
            operator_registry=self.root/"competition/configs/arena/grounded_operator_registry.json",
            effect_registry=self.root/"configs/red/grounded_effect_registry_v1.json")
        for adapter in self.adapters:
            adapter.registries = registries
        self.toolchain_fingerprint = self.adapters[0].toolchain_fingerprint

    def generate_red(self, parent, config, red_search_context):
        plan = red_search_context["grounded_proposal_plan"]
        selected = plan["selected_intent_ids"]
        if len(selected) > config["grounded_red_proposal_budget"]:
            raise ValueError("Red proposal budget exceeded")
        used = set()
        results = []
        for i, intent_id in enumerate(selected):
            intent = next(r for r in plan["candidate_intents"] if r["intent_id"] == intent_id)
            eligible = []
            for j, adapter in enumerate(self.adapters):
                case = adapter._cases[0]
                if operator_nodes(Path(case["golden_rtl"]).read_text(), module=case["top_module"], operator_id=intent["operator_id"]):
                    eligible.append(j)
            if not eligible:
                # No fabricated poison when no clean design supports this operator.
                raise ValueError("frozen Red schedule has no compatible target")
            offset = (int(self.round_id[1:]) * len(selected)) % len(self.adapters)
            ordered = sorted(eligible, key=lambda j: (j-offset) % len(self.adapters))
            j = next((j for j in ordered if j not in used), ordered[i % len(ordered)])
            used.add(j)
            adapter = self.adapters[j]
            # Unique storage/poison id for each scheduled intent and challenged policy.
            adapter._round_id = self.round_id + "-" + hash_payload({"intent":intent_id,"policy":parent.policy_hash})[-12:]
            context = deepcopy(red_search_context)
            context["grounded_proposal_plan"]["selected_intent_ids"] = [intent_id]
            results.extend(adapter.generate_red(parent, config, context))
        return results
