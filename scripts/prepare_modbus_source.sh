#!/bin/sh
set -eu

SRC_DIR=${1:-/usr/src/beremiz-modbus}
DEST_DIR=${2:-.deps/Modbus}

if [ ! -f "$SRC_DIR/mb_slave_and_master.h" ]; then
	echo "Modbus source not found in $SRC_DIR" >&2
	echo "Install beremiz-modbus-source first." >&2
	exit 1
fi

rm -rf "$DEST_DIR"
mkdir -p "$(dirname "$DEST_DIR")"
cp -a "$SRC_DIR" "$DEST_DIR"

python3 - "$DEST_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
for path in root.glob("*.c"):
	text = path.read_text(encoding="utf-8")
	text = text.replace("#include <termio.h>", "#include <termios.h>")
	path.write_text(text, encoding="utf-8")
PY

make -C "$DEST_DIR"

echo "Prepared Modbus library in $DEST_DIR"
