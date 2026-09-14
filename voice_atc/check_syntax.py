import ast
from pathlib import Path

for name in ("main.py", "volc_client.py", "prompt.py", "radio_fx.py"):
    ast.parse(Path(name).read_text(encoding="utf-8"))
    print(name, "ok")
