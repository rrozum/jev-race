"""Precompression removes work from the web server and saves download bandwidth."""
from pathlib import Path
import gzip
import hashlib
import json
try:
    import brotli
except ImportError:
    brotli = None

root = Path(__file__).resolve().parents[1] / "web/game"
manifest = root / ".compression.json"
previous = json.loads(manifest.read_text()) if manifest.exists() else {}
current = {}


def atomic_write(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


before = after = brotli_total = 0
for path in root.iterdir():
    if path.suffix not in {".wasm", ".pck", ".js"}:
        continue
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    current[path.name] = digest
    changed = previous.get(path.name) != digest
    gzip_path = Path(str(path) + ".gz")
    if changed or not gzip_path.exists():
        atomic_write(gzip_path, gzip.compress(data, compresslevel=9, mtime=0))
    before += len(data)
    after += gzip_path.stat().st_size
    brotli_path = Path(str(path) + ".br")
    if brotli:
        if changed or not brotli_path.exists():
            atomic_write(brotli_path, brotli.compress(data, quality=11))
        brotli_total += brotli_path.stat().st_size
    elif changed:
        # Never serve an old Brotli asset alongside a newer uncompressed build.
        brotli_path.unlink(missing_ok=True)
atomic_write(manifest, json.dumps(current).encode())
print(f"Game transfer: {before / 1048576:.2f} MiB → {after / 1048576:.2f} MiB (gzip)")
if brotli:
    print(f"Brotli transfer: {brotli_total / 1048576:.2f} MiB")
