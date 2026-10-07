"""Human-readable round outcomes, without changing frozen experiment evidence."""
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from competition.arena.evidence import read
from r3e.arena.audit import verify_frozen_round
from r3e.arena.manifests import verify_manifest


NO_NEW_QUESTION = "本轮没有筛出适合改进策略的新题，保留原策略，未进行升级考试。"


def round_message(row, directory):
    reason = row.get("defer_reason", "")
    target_path = Path(directory) / "target_manifest.json"
    # The old summary loses the more specific reason. Recover it from the
    # manifest bound into that already-verified round, never from counts alone.
    if reason == "insufficient_residual_designs" and target_path.exists():
        target = verify_manifest(read(target_path))
        if target["manifest_hash"] != row.get("target_manifest_hash"):
            raise ValueError("display target manifest differs from round evidence")
        reason = target.get("metadata", {}).get("defer_reason") or reason
    if row.get("promoted"):
        message = "策略升级通过。"
    elif reason == "no_admitted_red_failure":
        message = NO_NEW_QUESTION
    elif reason == "insufficient_residual_designs":
        allocation = row.get("design_allocation", {})
        if any(allocation.get(k, 0) > 0 for k in (
                "missing_design_count", "missing_adaptation_designs", "missing_target_designs")):
            message = "可用于练习或考试的电路种类还不够，继续积累题目；本轮未进行升级考试。"
        else:
            message = "本轮未满足升级条件，保留原策略；当前记录未提供更具体的原因。"
    elif reason == "promotion_epoch_reserved":
        message = "本轮按计划不进行升级考试，保留原策略。"
    else:
        message = "本轮没有策略通过升级要求，保留原策略。"
    return {"reason": reason, "message": message}


def completed_messages(state):
    result = {}
    for path in sorted((Path(state) / "rounds").glob("R*/round_summary.json")):
        audit = verify_frozen_round(path.parent)
        row = read(path)
        if row["audit_record_hash"] != audit["audit_record_hash"]:
            raise ValueError("display summary differs from round audit")
        result[path.parent.name] = round_message(row, path.parent)
    return result


def progress_messages(state, progress):
    suppress_allocation = False

    def emit(message, **kwargs):
        nonlocal suppress_allocation
        if message.startswith("用途已固定：") and suppress_allocation:
            suppress_allocation = False
            return
        suppress_allocation = False
        match = re.match(r"^(R\d+)：(考题不足|尚未发现入选的 Red 难例|复用已核验的完整回合)", message)
        if match:
            directory = Path(state) / "rounds" / match[1]
            row = read(directory / "round_summary.json")
            display = round_message(row, directory)
            prefix = "复用已核验的完整回合；" if match[2] == "复用已核验的完整回合" else ""
            message = f"{match[1]}：{prefix}{display['message']}"
            suppress_allocation = display["reason"] == "no_admitted_red_failure"
        progress(message, **kwargs)

    return emit


def observer_snapshot(original, service, state):
    data = original(service)  # Core verifies frozen evidence first.
    if data.get("available"):
        data["round_messages"] = {
            row["round_id"]: round_message(row, Path(state) / "rounds" / row["round_id"])
            for row in data.get("rounds", [])
        }
    return data


def frontend_script(path):
    script = Path(path).read_text()
    old = "if (row.defer_reason) text('p', `原因：${reasons[row.defer_reason] || row.defer_reason}`, card);"
    new = """const display = data.round_messages?.[row.round_id];
      if (display) text('p', display.message, card);
      else if (row.defer_reason) text('p', `原因：${reasons[row.defer_reason] || row.defer_reason}`, card);"""
    if old not in script:
        raise ValueError("round display frontend changed")
    script = script.replace(old, new)
    script = script.replace("if (a.roles_frozen) text(",
        "if (a.roles_frozen && (a.missing_adaptation_designs > 0 || a.missing_target_designs > 0)) text(")
    return script


def serve_observer(run, argv):
    from competition.app.backend import api
    from competition.services.arena_telemetry_service import ArenaTelemetryService

    run = Path(run)
    original_snapshot = ArenaTelemetryService.snapshot
    original_send_file = api.Handler._send_file
    source_js = api.FRONTEND / "arena.js"
    with TemporaryDirectory(prefix="r3e-round-display-") as temp:
        display_js = Path(temp) / "arena.js"
        display_js.write_text(frontend_script(source_js))

        def snapshot(service):
            return observer_snapshot(original_snapshot, service, run / "arm-b")

        def send_file(handler, path):
            return original_send_file(handler, display_js if path == source_js else path)

        comparison = run / "comparison.json"
        evidence = ["--comparison", str(comparison)] if comparison.exists() else ["--arena-state", str(run / "arm-b")]
        with patch.object(ArenaTelemetryService, "snapshot", snapshot), \
                patch.object(api.Handler, "_send_file", send_file), \
                patch.object(sys, "argv", [sys.argv[0], "--observer", "--host", "127.0.0.1",
                    "--port", "8083", "--output-root", str(run / "ui"), *evidence, *argv]):
            return api.main()
