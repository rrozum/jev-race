"""Serve precompressed engine files, keeping their original MIME types."""
import mimetypes
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse


class CompressedFiles(StaticFiles):
    async def get_response(self, path, scope):
        headers = dict(scope["headers"])
        encodings = headers.get(b"accept-encoding", b"").decode().split(",")
        allowed = set()
        for entry in encodings:
            parts = entry.strip().split(";")
            try:
                quality = float(parts[1].strip().removeprefix("q=")) if len(parts) > 1 else 1
            except ValueError:
                continue
            if quality > 0:
                allowed.add(parts[0])
        for encoding, suffix in (("br", ".br"), ("gzip", ".gz")):
            if encoding not in allowed or not path.endswith((".wasm", ".pck", ".js", ".css")):
                continue
            full, stat = self.lookup_path(path + suffix)
            if stat:
                kind = "application/wasm" if path.endswith(".wasm") else mimetypes.guess_type(path)[0]
                return FileResponse(full, media_type=kind or "application/octet-stream",
                    headers={"Content-Encoding": encoding, "Vary": "Accept-Encoding",
                             "Cache-Control": "public, max-age=3600, must-revalidate"})
        return await super().get_response(path, scope)
