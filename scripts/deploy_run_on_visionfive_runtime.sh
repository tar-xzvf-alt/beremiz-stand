#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
RUNTIME_URI=${3:-ERPC://10.42.0.211:3000}

ssh "$TARGET" \
	"cd '$REMOTE_DIR' && \
	MODBUS_PATH='$REMOTE_DIR/.deps/Modbus' /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py \
		--project-home beremiz-project/study-plc \
		--uri '$RUNTIME_URI' \
		transfer run"
