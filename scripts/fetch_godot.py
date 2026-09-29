"""Install a pinned editor and only the two Web release templates.

The official template archive is >1 GB. HTTP byte ranges fetch just its ZIP
directory and the Web entries. SHA256 checks pin every installed artifact.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import struct
import sys
import urllib.request
import zipfile
import zlib

VERSION = "4.7.2-stable"
TEMPLATE_ARCHIVE_SIZE = 1281349702
BASE = f"https://github.com/godotengine/godot-builds/releases/download/{VERSION}"
EDITOR_SHA = "cadd3204e728a35d3f13adb7fd0d7902636b79f6b95c40c265eb73b6c35329e4"
TEMPLATE_SHA = {
    "web_release.zip": "02f0dca13ed3d8343fa68f8f88ac80295562408d71aa67157e8b96ddebaa67a3",
    "web_nothreads_release.zip": "d3ee2f08cef0cf3cf6678a6355a92a8db48ccdd35cbd2e8bfd5f0e8a0b4032a0",
}


def verified(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Godot artifact checksum mismatch")
    return data


def install(destination):
    destination.mkdir(parents=True, exist_ok=True)
    editor_name = f"Godot_v{VERSION}_linux.x86_64"
    with urllib.request.urlopen(f"{BASE}/{editor_name}.zip", timeout=120) as response:
        archive = verified(response.read(), EDITOR_SHA)
    with zipfile.ZipFile(BytesIO(archive)) as source:
        binary = destination / "godot"
        binary.write_bytes(source.read(editor_name))
        binary.chmod(0o755)

    url = f"{BASE}/Godot_v{VERSION}_export_templates.tpz"
    def part(start, end=None):
        request = urllib.request.Request(url, headers={"Range": f"bytes={start}" if end is None else f"bytes={start}-{end}"})
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 206:
                raise RuntimeError("Artifact host did not honor HTTP Range")
            return response.read()
    tail = part(TEMPLATE_ARCHIVE_SIZE - 65557, TEMPLATE_ARCHIVE_SIZE - 1)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0:
        raise RuntimeError("Missing ZIP directory")
    footer = struct.unpack_from("<4s4H2IH", tail, offset)
    directory = part(footer[6], footer[6] + footer[5] - 1)
    cursor, found = 0, set()
    target = Path.home() / ".local/share/godot/export_templates/4.7.2.stable"
    target.mkdir(parents=True, exist_ok=True)
    while cursor < len(directory):
        entry = struct.unpack_from("<4s6H3I5H2I", directory, cursor)
        name_len, extra_len, comment_len = entry[10:13]
        name = directory[cursor+46:cursor+46+name_len].decode()
        basename = name.rsplit("/", 1)[-1]
        if basename in TEMPLATE_SHA:
            local_offset, size, method = entry[16], entry[8], entry[4]
            header = part(local_offset, local_offset + 29)
            filename_len, local_extra = struct.unpack_from("<HH", header, 26)
            start = local_offset + 30 + filename_len + local_extra
            compressed = part(start, start + size - 1)
            content = zlib.decompress(compressed, -15) if method == 8 else compressed
            (target / basename).write_bytes(verified(content, TEMPLATE_SHA[basename]))
            found.add(basename)
        cursor += 46 + name_len + extra_len + comment_len
    if found != set(TEMPLATE_SHA):
        raise RuntimeError("Web templates not found")
    print(f"Godot ready: {binary}")


if __name__ == "__main__":
    install(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/jev-race-godot"))
