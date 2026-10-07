"""Make a separate, committed source snapshot; never mutate the working tree."""
import argparse
import shutil
import subprocess
from pathlib import Path


def prepare(root, target):
    root, target = Path(root).resolve(), Path(target).resolve()
    if target.exists() or target == root or root in target.parents:
        raise ValueError("release target must be a new directory outside source")
    target.mkdir(parents=True)
    for name in ("competition", "r3e", "configs", "datasets", "scripts", "tests"):
        shutil.copytree(root / name, target / name, ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".env", ".env.*", "*.pyc", "*.log", ".venv", "runtime"))
    for name in (".gitignore", "README.md", "LICENSE", "pyproject.toml", "requirements.txt", "真实实验运行说明.md", "DeepSeek接入步骤.md"):
        if (root / name).is_file():
            shutil.copy2(root / name, target / name)
    def git(*args):
        return subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True, text=True).stdout.strip()
    git("init", "--quiet")
    git("add", ".")
    git("-c", "user.name=R3E release snapshot", "-c", "user.email=release@localhost", "-c", "commit.gpgsign=false",
        "commit", "--quiet", "-m", "Freeze standalone R3E live experiment source")
    from competition.arena.baseline import source_identity
    identity = source_identity(target)
    if identity["dirty"] or identity["source_hash"] != source_identity(root)["source_hash"]:
        raise ValueError("release source identity mismatch")
    return {"release": str(target), **identity}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(Path(__file__).resolve().parents[2], args.output), indent=2))


if __name__ == "__main__":
    main()
