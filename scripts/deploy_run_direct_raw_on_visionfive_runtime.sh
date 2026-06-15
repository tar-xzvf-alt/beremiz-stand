#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
RUNTIME_URI=${3:-ERPC://10.42.0.211:3000}
PROJECT=${4:-beremiz-project/direct-raw-plc}

ssh "$TARGET" \
	"cd '$REMOTE_DIR' && \
	/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py \
		--project-home '$PROJECT' \
		--uri '$RUNTIME_URI' \
		transfer run"
