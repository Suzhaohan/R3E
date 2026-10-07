"""One local arm of the real experiment. No scripted-provider fallback."""
import argparse
import json
import platform
from pathlib import Path

from competition.arena.baseline import load_runtime, portable_toolchain, source_identity
from competition.arena.cli import main as arena, _client
from competition.arena.evidence import read, freeze, signed, verify_signed
from competition.arena_config import load_arena_config
from r3e.arena.audit import verify_frozen_round
from r3e.protocol.hashing import hash_payload
from r3e.protocol.ledger import writer_lock
from r3e.providers.openai_compatible import DEEPSEEK_FLASH_PROFILE

ROOT = Path(__file__).resolve().parents[2]
ROUND_IDS = [f"R{i:03d}" for i in range(5)]


def preflight(root, client_path):
    """Local checks only; never send a request or print credentials."""
    checks = {"tools": all(v["available"] for v in portable_toolchain().values())}
    identity = source_identity(root)
    checks["committed_source"] = bool(identity["git_commit"]) and not identity["dirty"]
    checks.update(client_config=False, credentials=False)
    sampling_note = ""
    if Path(client_path).is_file():
        try:
            raw = read(client_path)
            client = _client(client_path)
            sampling_note = client.config.sampling_note
            checks["client_config"] = (not any("__REQUIRED__" in str(v) for v in raw.values())
                                       and client.config.temperature == 0
                                       and (client.config.require_seed or
                                            client.config.request_profile == DEEPSEEK_FLASH_PROFILE))
            checks["credentials"] = client.readiness()["ready"]
        except (ValueError, RuntimeError, KeyError, TypeError):
            pass
    return {"ready": all(checks.values()), "checks": checks, "network_calls": 0,
            "rounds": 5, "candidate_budget": 3,
            **({"sampling_note": sampling_note} if sampling_note else {}),
            "message": "缺项请见《真实实验运行说明.md》；不会回退到预置答案。"}


def run(root, args, progress=print):
    report = preflight(root, args.client_config)
    if args.check:
        return report
    if not report["ready"]:
        raise ValueError("真实实验尚未就绪：" + json.dumps(report, ensure_ascii=False))
    if not args.state_root or not args.baseline or not args.arm:
        raise ValueError("运行需要 --arm、--baseline、--state-root")
    if not args.max_calls or not args.max_tokens or args.max_calls < 1 or args.max_tokens < 1:
        raise ValueError("运行前必须设置正数 --max-calls 和 --max-tokens 总预算")
    state = Path(args.state_root).resolve()
    root = Path(root).resolve()
    if state == root or root in state.parents:
        raise ValueError("正式实验输出目录必须位于源码目录之外，以保持代码冻结")
    config_path = root / f"competition/configs/arena/{args.arm}.yaml"
    config = load_arena_config(config_path)
    baseline = verify_signed(read(args.baseline), "baseline_hash")
    if baseline["dirty"] or not baseline["git_commit"] or baseline["container_image_hash"] == "unrecorded":
        raise ValueError("baseline 需要干净提交和已记录的运行环境/镜像标识")
    client = _client(args.client_config)
    from competition.arena.runtime import validate_client
    validate_client(client, baseline)
    if "client_config_hash" not in baseline["provider"]:
        raise ValueError("请用当前 arena-baseline 重新创建包含完整客户端配置绑定的 baseline")
    plan = signed({"schema_version": "r3e-aic-live-plan-v1", "arm": args.arm,
        "baseline_hash": baseline["baseline_hash"], "client_config_hash": client.config.config_hash,
        "round_ids": ROUND_IDS if args.arm == "adversarial" else [],
        "max_calls": args.max_calls, "max_tokens": args.max_tokens,
        "host_identity_hash": hash_payload(platform.node())})
    # A second launcher cannot race initialization or advance the same arm.
    with writer_lock(state.parent / (state.name + ".launcher.lock")):
        if not (state / "machine_manifest.json").exists():
            arena(["arena-init", "--config", str(config_path), "--baseline", str(args.baseline),
                   "--state-root", str(state)], root)
        _, machine, stored = load_runtime(state)
        if stored != baseline or machine["config_hash"] != config.config_hash:
            raise ValueError("existing arm differs from requested baseline/configuration")
        freeze(state / "live_plan.json", plan)
        common = ["--state-root", str(state), "--client-config", str(args.client_config),
                  "--max-calls", str(args.max_calls), "--max-tokens", str(args.max_tokens),
                  "--total-max-calls", str(args.max_calls), "--total-max-tokens", str(args.max_tokens)]
        for round_id in plan["round_ids"]:
            directory = state / "rounds" / round_id
            if (directory / "round_summary.json").exists():
                verify_frozen_round(directory)
                progress(f"{round_id}：复用已核验的完整回合", flush=True)
                continue
            progress(f"{round_id}：真实 Red 生成 → EDA → Blue 修复 → 策略门控", flush=True)
            result = arena(["arena-round", *common, "--config", str(config_path), "--round", round_id], root)
            progress(f"{round_id}：{'升级通过' if result['promoted'] else '保留原策略'}", flush=True)
        evaluations = []
        for dataset in ("strider14", "red-heldout"):
            progress(f"最终测试 {dataset}：策略已冻结，不再用于策略搜索", flush=True)
            result = arena(["arena-eval", *common, "--dataset", dataset], root)
            evaluations.extend(["--evaluation", result["output"]])
        target = state / "frozen_arm.json"
        result = arena(["arena-freeze", "--state-root", str(state), *evaluations,
                        "--output", str(target)], root)
        return {"output": str(target), "source_kind": "live_model",
                "round_count": len(result["rounds"]), "promotion_count": result["promotion_count"],
                "message": "实验记录已冻结；无晋升或无提升也如实保留，A/B 比较后再判断效果。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-config", default="competition/configs/live_client.example.json")
    parser.add_argument("--check", action="store_true", help="只检查本地配置，不调用模型")
    parser.add_argument("--arm", choices=["static", "adversarial"])
    parser.add_argument("--baseline")
    parser.add_argument("--state-root")
    parser.add_argument("--max-calls", type=int, help="本机整个实验的请求上限，含 Red、筛选、回归、最终测试")
    parser.add_argument("--max-tokens", type=int, help="本机整个实验的保守 token 预留上限，不是人民币金额")
    args = parser.parse_args()
    try:
        result = run(ROOT, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ready", True) else 2
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
