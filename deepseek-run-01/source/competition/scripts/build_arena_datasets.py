"""Build small transparent synthetic protocol inputs, not empirical results.

The sets are design-instance disjoint but share a comparator template family.
They supplement Strider; do not claim broad unseen-design generalization.
"""
from pathlib import Path
import argparse
import json
from r3e.protocol.hashing import hash_payload, hash_file
from r3e.semantic_repair_bench.oracle_gate import judge
from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
from r3e.arena.manifests import make_manifest, freeze_manifest
from competition.arena.isolation import check_separation, seal_evaluation_manifest


def build(root):
    root=Path(root).resolve()
    sets={"evolve":[], "non_target":[], "evaluation":[]}
    for i in range(18):
        split="evolve" if i<4 else "non_target" if i<6 else "evaluation"
        case_id=f"m3_synthetic_{i:02d}"
        directory=root/"competition/manifests/assets"/case_id
        directory.mkdir(parents=True,exist_ok=True)
        threshold=1+i%14
        second=1+(i*3)%13
        join="&&" if i%2==0 else "||"
        expr=f"(a < {threshold}) {join} (b > {second})"
        gold=f"module m(input wire [3:0] a, input wire [3:0] b, output wire y);\n assign y = {expr};\nendmodule\n"
        buggy=gold.replace(f"a < {threshold}",f"a <= {threshold}")
        tb=f"""module tb;
 reg [3:0] a,b; wire y; integer i,j,fd,bad,first;
 m dut(.a(a),.b(b),.y(y));
 initial begin
 fd=$fopen("output.csv","w"); $fdisplay(fd,"time,y"); bad=0; first=-1;
 for(i=0;i<16;i=i+1) begin for(j=0;j<16;j=j+1) begin
 a=i; b=j; #1; $fdisplay(fd,"%0d,%b",i*16+j,y);
 if(y !== ({expr})) begin bad=bad+1; if(first<0) first=i*16+j; end
 end end
 $fclose(fd);
 if(bad==0) begin
 $display("R3E_ORACLE pass=1 signature=none first=none topology=none");
 $display("R3E_WAVEFORM signal=none first_cycle=none cycle_offset=none relation=none assignment=none cone_depth=none pattern=none");
 end else begin
 $display("R3E_ORACLE pass=0 signature=comparator_boundary first=cycle%0d topology=y",first);
 $display("R3E_WAVEFORM signal=y first_cycle=%0d cycle_offset=0 relation=same_cycle assignment=continuous cone_depth=1 pattern=boundary_value_mismatch",first);
 end
 $finish; end
 endmodule
"""
        prop=f"module formal_top; (* anyconst *) reg [3:0] a,b; wire y; m dut(.a(a),.b(b),.y(y)); always @* assert(y == ({expr})); endmodule\n"
        for name,content in {"golden.v":gold,"buggy.v":buggy,"tb.v":tb,"property.v":prop}.items():
            path=directory/name
            if path.exists() and path.read_text()!=content: raise ValueError("refusing to change frozen synthetic source")
            path.write_text(content)
        rel=lambda n:str((directory/n).relative_to(root))
        row={"case_id":case_id,"design":case_id,"eligible":True,"buggy_rtl":rel("buggy.v"),"golden_rtl":rel("golden.v"),
            "deps":[],"tb_sources":[rel("tb.v")],"tb_output":"output.csv","top_module":"m","sim_timeout":20,
            "poison_id":case_id+":boundary", "normalized_diff_hash":hash_payload({"before":gold,"after":buggy}),
            "failure_signature":hash_payload({"design":gold,"mutation":"boundary"}),
            "grounded_testbench":rel("tb.v"),"grounded_formal_property":rel("property.v"),
            "grounded_formal_top_module":"formal_top","grounded_formal_depth":4,
            "grounded_asset_hashes":{rel(n):hash_file(directory/n) for n in ("golden.v","buggy.v","tb.v","property.v")},
            "source_kind":"synthetic_protocol_input", "generation_seed":i,
            "generalization_boundary":"distinct design instances; shared comparator template family"}
        sets[split].append(row)
    manifests={}
    for split,rows in sets.items():
        usage="final_evaluation_only" if split=="evaluation" else "evolution_only"
        from r3e.blue.portfolio.oracle_gate_verifier import public_case_from_manifest
        rows=[{**r,"manifest_file_hashes":public_case_from_manifest(r,project_root=root)["manifest_file_hashes"]} for r in rows]
        manifests[split]=make_manifest(rows,split=split,metadata={"sealed":True,"allowed_usage":usage,
            "dataset":"red-heldout" if split=="evaluation" else "red-"+split,
            "source_kind":"synthetic_protocol_input","split_level":"design_instance_disjoint_template_family_shared"})
    for a,b in (("evolve","non_target"),("evolve","evaluation"),("non_target","evaluation")):
        check_separation(manifests[a],manifests[b])
    for split,name in (("evolve","red_evolve"),("non_target","red_regression"),("evaluation","red_heldout")):
        freeze_manifest(root/f"competition/manifests/{name}.json",manifests[split])
    seal_evaluation_manifest(root/"datasets/manifests/strider14.jsonl",root/"competition/manifests/strider14_sealed.json",project_root=root,dataset="strider14")
    return {k:len(v) for k,v in sets.items()}

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    build(root)
    from competition.scripts.expand_arena_designs import build as expand
    print(json.dumps(expand(root), indent=2))
