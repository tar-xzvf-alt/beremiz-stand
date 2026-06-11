#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}

ssh "$TARGET" \
	"cd '$REMOTE_DIR' && \
	./scripts/prepare_modbus_source.sh && \
	rm -rf beremiz-project/study-plc/build && \
	MODBUS_PATH='$REMOTE_DIR/.deps/Modbus' /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc build"
