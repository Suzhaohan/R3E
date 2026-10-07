"""Import supplied RTL and build versioned, design-separated arena inputs.

No model calls. Original RTL/TBs remain byte-identical. Grounded combinational
wrappers enumerate all binary inputs and prove equivalence to the supplied
reference implementation; this is not an independent specification proof.
"""
from pathlib import Path
import argparse
import json
import re

from competition.arena.evidence import read
from competition.arena.isolation import check_separation
from r3e.arena.manifests import make_manifest, freeze_manifest
from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
from r3e.protocol.hashing import hash_file, hash_payload


def write_frozen(path, content):
    path = Path(path)
    data = content.encode() if isinstance(content, str) else content
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to overwrite input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)


def import_assignments(root, source):
    manifest = root / "datasets/manifests/assignment4v57.jsonl"
    if manifest.exists():
        rows = [json.loads(line) for line in manifest.read_text().splitlines()]
        if len(rows) != 57:
            raise ValueError("Assignment4V membership changed")
        for row in rows:
            for asset in row["files"]:
                if hash_file(root / asset["path"]).removeprefix("sha256:") != asset["sha256"]:
                    raise ValueError("Assignment4V input hash mismatch")
            diff = (root / row["buggy_rtl"]).parent.parent / "reference.patch"
            if hash_file(diff) != row["normalized_diff_hash"]:
                raise ValueError("Assignment4V reference diff hash mismatch")
        return rows
    source = Path(source)
    rows = []
    for case in sorted((source / "dataset/Assignment4V").glob("*/*")):
        if not case.is_dir():
            continue
        family = case.parent.name
        dest = root / "datasets/cases/assignment4v" / family / case.name
        files = []
        for folder in ("buggy", "fixed"):
            for f in sorted((case / folder).glob("*.v")):
                target = dest / folder / f.name
                write_frozen(target, f.read_bytes())
                role = "testbench" if f.name.endswith("_tb.v") else ("buggy_rtl" if folder == "buggy" else "reference_rtl")
                files.append({"path": str(target.relative_to(root)), "sha256": hash_file(target).removeprefix("sha256:"),
                              "role": role, "size_bytes": target.stat().st_size})
        # Preserve upstream diff bytes as a source patch, not a runtime log.
        write_frozen(dest / "reference.patch", (case / "diff.log").read_bytes())
        rtl = next(p for p in (dest / "fixed").glob("*.v") if not p.name.endswith("_tb.v"))
        top = re.search(r"\bmodule\s+(\w+)", rtl.read_text())[1]
        rel = lambda p: str(p.relative_to(root))
        row = {"case_id": "assignment4v:" + case.name, "design": "assignment4v:" + family,
               "design_family": family, "source_kind": "public_assignment_input", "eligible": True,
               "buggy_rtl": rel(dest / "buggy" / rtl.name), "golden_rtl": rel(rtl),
               "tb_sources": [rel(next((dest / "buggy").glob("*_tb.v")))], "tb_output": "test.txt",
               "deps": [], "top_module": top, "sim_timeout": 20, "files": files,
               "source": {"project": "Assignment4V", "upstream_case": case.name,
                          "license": "not specified in supplied snapshot"},
               "poison_id": "assignment4v:" + case.name,
               "normalized_diff_hash": hash_file(dest / "reference.patch"),
               "failure_signature": hash_payload({"case": case.name, "source": "Assignment4V"})}
        row["manifest_file_hashes"] = public_case_from_manifest(row, project_root=root)["manifest_file_hashes"]
        row["case_sha256"] = hash_payload(row).removeprefix("sha256:")
        rows.append(row)
    if len(rows) != 57:
        raise ValueError("expected all 57 Assignment4V cases")
    write_frozen(root / "datasets/licenses/Assignment4V-source-README.md", (source / "README.md").read_bytes())
    write_frozen(manifest, "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


# One representative per upstream design, not one design per bug number.
# Ports: (name, width). Every combinational binary input is exercised.
SPECS = [
    ("assignment4v:fa_behavioral_1", [("a", 1), ("b", 1), ("ci", 1)], [("s", 1), ("co", 1)]),
    ("assignment4v:JG3_1", [("ABC", 3)], [("X", 1), ("Y", 1)]),
    ("assignment4v:mux21_1", [("a", 1), ("b", 1), ("s", 1)], [("y", 1)]),
    ("assignment4v:decoder3e_1", [("a", 3), ("ena", 1)], [("y", 8)]),
    ("assignment4v:decl7s_1", [("a", 4)], [("led7s", 7)]),
    ("cirfix:decoder_3_to_8", [("A", 1), ("B", 1), ("C", 1), ("en", 1)],
     [(f"Y{i}", 1) for i in range(8)]),
]


def grounded_wrapper(root, row, inputs, outputs):
    top = row["top_module"]
    golden = (root / row["golden_rtl"]).read_text()
    reference = re.sub(r"\bmodule\s+" + re.escape(top) + r"\b", "module r3e_reference", golden, count=1)
    width = sum(w for _, w in outputs)
    input_width = sum(w for _, w in inputs)
    # The selected circuits drive outputs directly from inputs in one RTL
    # assignment/always block. This is an RTL cone depth, not a gate depth.
    assignment_kind = "procedural" if re.search(r"\balways\b", golden) else "continuous"
    decl = lambda kind, name, w: f"{kind} " + (f"[{w-1}:0] " if w > 1 else "") + name + ";"
    ports = ",".join(f".{name}({name})" for name, _ in inputs)
    def output_ports(bus):
        parts, offset = [], 0
        for name, w in outputs:
            bit = f"[{offset}]" if w == 1 else f"[{offset+w-1}:{offset}]"
            parts.append(f".{name}({bus}{bit})")
            offset += w
        return ",".join(parts)
    wiring = f"wire [{width-1}:0] actual, expected;\n" + (
        f"{top} dut({ports},{output_ports('actual')});\n"
        f"r3e_reference oracle({ports},{output_ports('expected')});\n")
    drives = "{" + ",".join(name for name, _ in inputs) + "}"
    tb = "module tb;\n" + "\n".join(decl("reg", n, w) for n, w in inputs) + "\n" + wiring
    tb += f"""integer i, fd, bad, first;
initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,actual"); bad=0; first=-1;
 for(i=0;i<{2**input_width};i=i+1) begin
  {drives}=i; #1; $fdisplay(fd,"%0d,%b",i,actual);
  if(actual !== expected) begin bad=bad+1; if(first<0) first=i; end
 end
 $fclose(fd);
 if(bad==0) begin
  $display("R3E_ORACLE pass=1 signature=none first=none topology=none");
  $display("R3E_WAVEFORM signal=none first_cycle=none cycle_offset=none relation=none assignment=none cone_depth=none pattern=none");
 end else begin
  $display("R3E_ORACLE pass=0 signature=output_mismatch first=vector%0d topology=actual",first);
  $display("R3E_WAVEFORM signal=actual first_cycle=%0d cycle_offset=0 relation=same_cycle assignment={assignment_kind} cone_depth=1 pattern=output_mismatch",first);
 end
 $finish;
end
endmodule
""" + reference
    prop = "module formal_top;\n" + "\n".join("(* anyconst *) " + decl("reg", n, w) for n, w in inputs)
    prop += "\n" + wiring + "always @* assert(actual == expected);\nendmodule\n" + reference
    directory = root / "competition/manifests/imported_assets" / row["design"].replace(":", "_")
    write_frozen(directory / "tb.v", tb)
    write_frozen(directory / "property.v", prop)
    rel = lambda p: str(p.relative_to(root))
    result = {**row, "tb_sources": [rel(directory / "tb.v")], "tb_output": "output.csv",
              "grounded_testbench": rel(directory / "tb.v"),
              "grounded_formal_property": rel(directory / "property.v"),
              "grounded_formal_top_module": "formal_top", "grounded_formal_depth": 2,
              "input_vectors": 2**input_width,
              "oracle_scope": "exhaustive binary combinational equivalence to supplied reference",
              "design_group": row["design"]}
    result["grounded_asset_hashes"] = {p: hash_file(root / p) for p in (
        result["golden_rtl"], result["buggy_rtl"], result["grounded_testbench"], result["grounded_formal_property"])}
    result["manifest_file_hashes"] = public_case_from_manifest(result, project_root=root)["manifest_file_hashes"]
    return result


def build(root, assignment_source=None):
    root = Path(root).resolve()
    assignments = import_assignments(root, assignment_source or root.parent / "Assignment4V-master")
    by_id = {r["case_id"]: r for r in assignments}
    cirfix = next(json.loads(line) for line in (root / "datasets/manifests/cirfix39.jsonl").read_text().splitlines()
                  if json.loads(line)["design"] == "decoder_3_to_8__wadden_buggy1")
    cirfix = {**cirfix, "case_id": "cirfix:decoder_3_to_8", "design": "cirfix:decoder_3_to_8",
              "design_family": "decoder_3_to_8", "source_kind": "public_cirfix_input",
              "poison_id": "cirfix:decoder_3_to_8:wadden_buggy1",
              "normalized_diff_hash": hash_payload({"bug": hash_file(root / cirfix["buggy_rtl"]),
                                                     "reference": hash_file(root / cirfix["golden_rtl"])}),
              "failure_signature": hash_payload("cirfix:decoder_3_to_8:wadden_buggy1")}
    by_id[cirfix["case_id"]] = cirfix
    evolve = [grounded_wrapper(root, by_id[cid], ins, outs) for cid, ins, outs in SPECS]
    # Preserve original frozen synthetic inputs; new membership gets new filenames.
    old = {key: read(root / f"competition/manifests/{key}.json")["rows"]
           for key in ("red_evolve", "red_regression", "red_heldout")}
    evolve += old["red_evolve"]
    regression = old["red_regression"] + [r for r in assignments if r["design_family"] == "latch24"]
    heldout = old["red_heldout"] + [r for r in assignments if r["design_family"] == "counter6bit"]
    sets = {}
    for name, split, rows in (("red_evolve", "evolve", evolve), ("red_regression", "non_target", regression),
                              ("red_heldout", "evaluation", heldout)):
        rows = [{**r, "design_group": r.get("design_group", r["design"])} for r in rows]
        sets[name] = make_manifest(rows, split=split, metadata={"sealed": True,
            "allowed_usage": "final_evaluation_only" if split == "evaluation" else "evolution_only",
            "dataset": "red-heldout" if split == "evaluation" else name.replace("_", "-"),
            "dataset_version": 2, "split_level": "upstream_design_disjoint; synthetic comparator family shared",
            "design_count": len({r["design"] for r in rows})})
    for a, b in (("red_evolve", "red_regression"), ("red_evolve", "red_heldout"), ("red_regression", "red_heldout")):
        check_separation(sets[a], sets[b])
    for name, manifest in sets.items():
        freeze_manifest(root / f"competition/manifests/{name}_v2.json", manifest)
    catalog = {"schema_version": "r3e-design-catalog-v1", "assignment_case_count": len(assignments),
               "assignment_design_count": len({r["design"] for r in assignments}),
               "splits": {name: {"cases": m["row_count"], "designs": sorted({r["design"] for r in m["rows"]}),
                                 "manifest_hash": m["manifest_hash"]} for name, m in sets.items()},
               "notes": ["CirFix decoder reuses the existing public snapshot; not a new independent dataset.",
                         "All 57 Assignment4V cases are preserved; only selected designs participate in each split.",
                         "Assignment4V combined manifest is an inventory, not a heldout set after evolution."]}
    write_frozen(root / "competition/manifests/design_catalog_v2.json", json.dumps(catalog, indent=2) + "\n")
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignment-source", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[2], args.assignment_source), indent=2))
