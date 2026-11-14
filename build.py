"""Check original source files and reproduce the Mars database and atlas."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent
inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
for filename, (url, expected) in inputs.items():
    target = root / "work" / filename
    if not target.exists():
        partial = target.with_suffix(target.suffix + ".partial")
        try:
            with urlopen(url, timeout=120) as response, partial.open("wb") as sink:
                shutil.copyfileobj(response, sink)
            with partial.open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != expected:
                raise SystemExit(f"{filename}: download differs from pinned snapshot. Use the original file.")
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    with target.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise SystemExit(f"{filename}: SHA-256 mismatch. Replace it with the original file.")

(root / "outputs").mkdir(exist_ok=True)
subprocess.run([sys.executable, str(root / "work" / "build_mars.py")], check=True, cwd=root)
