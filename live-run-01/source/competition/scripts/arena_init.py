"""CLI wrapper for arena-init."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from competition.arena.cli import main
if __name__ == "__main__":
    import json
    print(json.dumps(main(["arena-init", *sys.argv[1:]], ROOT), ensure_ascii=False, indent=2))
