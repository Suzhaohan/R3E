"""Store a key locally without terminal echo or shell history exposure."""
import getpass
import os
from pathlib import Path

root = Path(__file__).resolve().parent
folder = root / '.secrets'
folder.mkdir(mode=0o700, exist_ok=True)
os.chmod(folder, 0o700)
key = getpass.getpass('OpenRouter API key（输入不回显）: ').strip()
if not key or any(c.isspace() for c in key):
    raise SystemExit('密钥为空或包含空白，未保存。')
path = folder / 'openrouter.key'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as out:
    out.write(key + '\n')
print(f'已保存到 {path}（权限 600；不显示密钥）')
