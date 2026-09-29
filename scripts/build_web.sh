#!/usr/bin/env bash
set -euo pipefail
race_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
godot_bin="${GODOT_BIN:-godot}"
mkdir -p "$race_root/web/game"
build_log="$(mktemp)"
trap 'rm -f "$build_log"' EXIT
"$godot_bin" --headless --path "$race_root/game" --editor --import 2>&1 | tee "$build_log"
if grep -Eq 'SCRIPT ERROR:|Parse Error:|^ERROR:' "$build_log"; then exit 1; fi
"$godot_bin" --headless --path "$race_root/game" --export-release Web "$race_root/web/game/index.html" 2>&1 | tee "$build_log"
if grep -Eq 'SCRIPT ERROR:|Parse Error:|^ERROR:' "$build_log"; then exit 1; fi
python3 "$race_root/scripts/compress_web.py"
