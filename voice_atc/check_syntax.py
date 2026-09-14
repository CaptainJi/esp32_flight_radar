import ast
from pathlib import Path

for name in ("main.py", "minimax_client.py", "prompt.py"):
    ast.parse(Path(name).read_text(encoding="utf-8"))
    print(name, "ok")
