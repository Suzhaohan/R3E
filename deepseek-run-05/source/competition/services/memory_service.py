"""Conservative presentation facade for verified experience memory."""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any


class MemoryService:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()

    def list_memories(self) -> dict[str, Any]:
        history = self.repo_root / "competition/manifests/history_memory.json"
        if history.is_file():
            from collections import Counter
            from .experience_memory import initial_bank
            bank = initial_bank(self.repo_root)
            counts = Counter(e["category"] for e in bank["entries"])
            return {
                "schema_version": "r3e-aic-memory-view-v2", "available": True,
                "message": f"历史经验检索已开启：{len(bank['entries'])} 条已核验记录。新增经验通过配对防退化检查后生效。",
                "memory_hash": bank["result_hash"], "statuses": ["Verified history"],
                "memories": [{"memory_id": name, "status": f"{count} 条经验"} for name, count in sorted(counts.items())],
            }
        path = self.repo_root / "competition" / "results" / "frozen" / "memory" / "audit.json"
        if path.is_file():
            audit = json.loads(path.read_text(encoding="utf-8"))
            if audit.get("available") is True and audit.get("status") == "verified_activation_audit":
                return {
                    "schema_version": "r3e-aic-memory-view-v2",
                    "available": True,
                    "message": "Experience memory is backed by a frozen activation audit.",
                    "statuses": ["Shadow", "Qualified", "Active", "Rejected", "Suspended"],
                    "memories": audit.get("memories", []),
                }
        return {
            "schema_version": "r3e-aic-memory-view-v2",
            "available": False,
            "message": "No verified memory activation audit is frozen; activation evidence is not fabricated.",
            "statuses": ["Shadow", "Qualified", "Active", "Rejected", "Suspended"],
            "memories": [],
        }
