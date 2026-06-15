#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
PROJECT=${3:-beremiz-project/direct-raw-plc}

ssh "$TARGET" \
	"cd '$REMOTE_DIR' && \
	rm -rf '$PROJECT/build' && \
	/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home '$PROJECT' build"
